"""OPS-04: retention purge and delete_subject. Test tenants only (`test-*`, removed by conftest); never purge_all on real tenants."""
import ast
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from . import db, retention

NOW = datetime.now(timezone.utc)
CHILD_TABLES = ("messages", "tool_calls", "escalations", "events", "llm_calls")
ZERO = {k: 0 for k in retention.PURGED}


def _tenant() -> str:
    tid = str(uuid.uuid4())
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:i, :s, :s, 'UTC', 'summit-roofing')"),
                  {"i": tid, "s": f"test-ret-{tid[:8]}"})
    return tid


def _ago(days):
    return NOW - timedelta(days=days)


def _lead(c, t, created_days, email=None, phone=None):
    return c.execute(text("INSERT INTO leads (tenant_id, name, email, phone, created_at) VALUES (:t, 'N', :e, :p, :c) RETURNING id"),
                     {"t": t, "e": email, "p": phone, "c": _ago(created_days)}).scalar_one()


def _convo(c, t, lead, started_days, ended_days=None, ext=None):
    cid = c.execute(text("INSERT INTO conversations (tenant_id, lead_id, external_id, started_at, ended_at) "
                         "VALUES (:t, :l, :x, :s, :e) RETURNING id"),
                    {"t": t, "l": lead, "x": ext, "s": _ago(started_days), "e": None if ended_days is None else _ago(ended_days)}).scalar_one()
    p = {"t": t, "c": cid}
    c.execute(text("INSERT INTO messages (tenant_id, conversation_id, role, content) VALUES (:t, :c, 'user', 'hi')"), p)
    c.execute(text("INSERT INTO tool_calls (tenant_id, conversation_id, tool_name) VALUES (:t, :c, 'x')"), p)
    c.execute(text("INSERT INTO escalations (tenant_id, conversation_id, reason) VALUES (:t, :c, 'r')"), p)
    c.execute(text("INSERT INTO events (tenant_id, conversation_id, kind) VALUES (:t, :c, 'k')"), p)
    c.execute(text("INSERT INTO llm_calls (tenant_id, conversation_id, model) VALUES (:t, :c, 'm')"), p)
    return cid


def _slot(c, t, start_days, booked=True):
    s = _ago(-start_days)
    return c.execute(text("INSERT INTO slots (tenant_id, start_time, end_time, is_booked) VALUES (:t, :s, :s + interval '1 hour', :b) RETURNING id"),
                     {"t": t, "s": s, "b": booked}).scalar_one()


def _appt(c, t, lead, start_days):
    sid = _slot(c, t, start_days)
    c.execute(text("INSERT INTO appointments (tenant_id, lead_id, slot_id) VALUES (:t, :l, :s)"), {"t": t, "l": lead, "s": sid})
    return sid


def _engine_rows(c, t, days, key, email=None):
    c.execute(text("INSERT INTO drafts (tenant_id, kind, status, payload, input_hash, created_at) VALUES (:t, 'quote', 'sent', CAST(:p AS jsonb), :h, :c)"),
              {"t": t, "p": json.dumps({"contact_email": email} if email else {}), "h": f"{key}{uuid.uuid4().hex}", "c": _ago(days)})
    c.execute(text("INSERT INTO intake_people (tenant_id, person_key, created_at) VALUES (:t, :k, :c)"), {"t": t, "k": key, "c": _ago(days)})
    c.execute(text("INSERT INTO capacity_flags (tenant_id, flag_key, kind, shift_id, shift_date, input_hash, first_flagged_at) "
                   "VALUES (:t, :k, 'over_capacity', 's', current_date, 'h', :c)"), {"t": t, "k": key, "c": _ago(days)})
    c.execute(text("INSERT INTO brief_runs (tenant_id, run_date, created_at) VALUES (:t, :d, :c)"),
              {"t": t, "d": _ago(days).date() - timedelta(days=len(key)), "c": _ago(days)})


def _ids(t, table, col="id"):
    with db.system() as c:
        return {r[0] for r in c.execute(text(f"SELECT {col} FROM {table} WHERE tenant_id = :t"), {"t": t})}


def _n(t, table):
    return len(_ids(t, table))


def _seed_all(t):
    """Old/new mix; returns ids by role."""
    r = {}
    with db.system() as c:
        r["old_lead"] = _lead(c, t, 60)
        r["old_convo"] = _convo(c, t, r["old_lead"], 60, ext="old-ext")
        r["new_lead"] = _lead(c, t, 1)
        r["new_convo"] = _convo(c, t, r["new_lead"], 1)
        r["mixed_lead"] = _lead(c, t, 60)  # old lead, old convo + recent convo -> survives
        r["mixed_old"] = _convo(c, t, r["mixed_lead"], 60)
        r["mixed_new"] = _convo(c, t, r["mixed_lead"], 1)
        r["fut_lead"] = _lead(c, t, 60)  # old lead with a future appointment -> survives, its old convo goes
        r["fut_convo"] = _convo(c, t, r["fut_lead"], 60)
        r["fut_slot"] = _appt(c, t, r["fut_lead"], 5)
        r["past_lead"] = _lead(c, t, 90)  # purged lead with a past appointment
        r["past_convo"] = _convo(c, t, r["past_lead"], 90)
        r["past_slot"] = _appt(c, t, r["past_lead"], -80)
        r["ended_convo"] = _convo(c, t, None, 60, ended_days=1)  # started old but ended recently -> survives
        for days, key in ((60, "old"), (1, "new")):
            _engine_rows(c, t, days, key)
    with db.system() as c:
        r["events_before"] = c.execute(text("SELECT count(*) FROM agent_events WHERE tenant_id=:t"), {"t": t}).scalar()
    return r


def test_purge_tenant_ages_out_and_keeps_recent():
    t = _tenant()
    r = _seed_all(t)
    counts = retention.purge_tenant(t, 30)
    assert _ids(t, "conversations") == {r["new_convo"], r["mixed_new"], r["ended_convo"]}
    assert _ids(t, "leads") == {r["new_lead"], r["mixed_lead"], r["fut_lead"]}
    for tb in CHILD_TABLES:  # children of purged conversations are gone, children of kept ones remain
        assert _ids(t, tb, "conversation_id") == {r["new_convo"], r["mixed_new"], r["ended_convo"]}, tb
    assert _ids(t, "appointments", "slot_id") == {r["fut_slot"]}
    with db.system() as c:
        booked = dict(c.execute(text("SELECT id, is_booked FROM slots WHERE tenant_id=:t"), {"t": t}).all())
    assert booked[r["past_slot"]] is False and booked[r["fut_slot"]] is True
    assert _ids(t, "drafts", "kind") and _n(t, "drafts") == 1 and _ids(t, "intake_people", "person_key") == {"new"}
    assert _n(t, "capacity_flags") == 1 and _n(t, "brief_runs") == 1
    with db.system() as c:
        assert c.execute(text("SELECT count(*) FROM agent_events WHERE tenant_id=:t"), {"t": t}).scalar() == r["events_before"]
    assert counts["conversations"] == 4 and counts["leads"] == 2 and counts["appointments"] == 1 and counts["messages"] == 4
    assert counts["drafts"] == counts["intake_people"] == counts["capacity_flags"] == counts["brief_runs"] == 1


def test_purge_does_not_touch_other_tenant():
    a, b = _tenant(), _tenant()
    _seed_all(a)
    rb = _seed_all(b)
    before = {tb: _n(b, tb) for tb in retention.PURGED}
    retention.purge_tenant(a, 30)
    assert {tb: _n(b, tb) for tb in retention.PURGED} == before
    assert rb["old_convo"] in _ids(b, "conversations")


def test_purge_zero_days_is_noop():
    t = _tenant()
    _seed_all(t)
    before = {tb: _n(t, tb) for tb in retention.PURGED}
    assert retention.purge_tenant(t, 0) == ZERO
    assert retention.purge_tenant(t, -3) == ZERO
    assert {tb: _n(t, tb) for tb in retention.PURGED} == before


def test_purge_all_noop_never_lists_or_purges(monkeypatch):
    called = []
    monkeypatch.setattr(retention, "list_tenant_ids", lambda: called.append("list") or [])
    monkeypatch.setattr(retention, "purge_tenant", lambda *a, **k: called.append("purge"))
    assert retention.purge_all(0) == {} and retention.purge_all(-5) == {}
    assert called == []


def test_purge_all_calls_purge_per_listed_tenant(monkeypatch):
    seen = []
    monkeypatch.setattr(retention, "list_tenant_ids", lambda: ["t1", "t2"])
    monkeypatch.setattr(retention, "purge_tenant", lambda tid, days: seen.append((tid, days)) or {"x": 1})
    assert retention.purge_all(7) == {"t1": {"x": 1}, "t2": {"x": 1}} and seen == [("t1", 7), ("t2", 7)]


# ---- delete_subject ----
def _seed_subject(t, email="Jane.Doe@Example.com", phone="+1 (303) 555-0142", ext="sms-jane"):
    r = {}
    with db.system() as c:
        r["lead"] = _lead(c, t, 1, email=email, phone=phone)
        r["convo"] = _convo(c, t, r["lead"], 1)
        r["ext_convo"] = _convo(c, t, None, 1, ext=ext)
        r["past_slot"] = _appt(c, t, r["lead"], -2)
        r["other_lead"] = _lead(c, t, 1, email="other@example.com", phone="+1 303 555 9999")
        r["other_convo"] = _convo(c, t, r["other_lead"], 1)
        r["other_slot"] = _appt(c, t, r["other_lead"], 3)
        r["orphan_convo"] = _convo(c, t, None, 1, ext="nobody")
        _engine_rows(c, t, 1, "jane.doe@example.com", email="jane.doe@example.com")
        _engine_rows(c, t, 1, "other@example.com", email="other@example.com")
        c.execute(text("INSERT INTO drafts (tenant_id, kind, status, payload, input_hash) VALUES (:t, 'quote', 'sent', '{}', :h)"),
                  {"t": t, "h": uuid.uuid4().hex})  # unlinked draft
    return r


@pytest.mark.parametrize("ident", ["jane.doe@example.com", "  JANE.DOE@EXAMPLE.COM ", "1-303-555-0142", "+1 (303) 555.0142", "sms-jane"])
def test_delete_subject_by_each_identifier(ident):
    t, other = _tenant(), _tenant()
    r, ro = _seed_subject(t), _seed_subject(other)
    counts = retention.delete_subject(t, ident)
    assert counts["leads"] >= 0 and set(counts) == set(retention.PURGED)
    if ident == "sms-jane":  # external_id only reaches the conversation without a lead
        assert r["ext_convo"] not in _ids(t, "conversations") and r["convo"] in _ids(t, "conversations")
        return
    assert r["convo"] not in _ids(t, "conversations") and r["lead"] not in _ids(t, "leads")
    assert r["past_slot"] not in _ids(t, "appointments", "slot_id")
    with db.system() as c:
        assert c.execute(text("SELECT is_booked FROM slots WHERE id=:s"), {"s": r["past_slot"]}).scalar() is False
    assert counts["leads"] == 1 and counts["appointments"] == 1 and counts["conversations"] == 1 and counts["messages"] == 1
    emailish = "@" in ident  # drafts and intake people are keyed by email, so a phone does not reach them
    assert counts["intake_people"] == counts["drafts"] == int(emailish)
    # others in the same tenant stay
    assert {r["other_lead"]} <= _ids(t, "leads") and {r["other_convo"], r["orphan_convo"]} <= _ids(t, "conversations")
    assert r["other_slot"] in _ids(t, "appointments", "slot_id") and "other@example.com" in _ids(t, "intake_people", "person_key")
    assert _n(t, "drafts") == (2 if emailish else 3)  # other person's + unlinked (+ Jane's when reached only by phone)
    # same data in another tenant stays
    assert {ro["lead"], ro["convo"]} <= (_ids(other, "leads") | _ids(other, "conversations"))
    assert _n(other, "drafts") == 3 and _n(other, "intake_people") == 2


def test_delete_subject_future_appointment_removed_and_slot_freed():
    t = _tenant()
    with db.system() as c:
        lead = _lead(c, t, 1, email="f@example.com")
        slot = _appt(c, t, lead, 4)
    retention.delete_subject(t, "f@example.com")
    assert _n(t, "appointments") == 0
    with db.system() as c:
        assert c.execute(text("SELECT is_booked FROM slots WHERE id=:s"), {"s": slot}).scalar() is False


def test_delete_subject_audit_row_has_hash_only():
    t = _tenant()
    _seed_subject(t)
    ident = "Jane.Doe@Example.com"
    counts = retention.delete_subject(t, ident)
    with db.system() as c:
        rows = c.execute(text("SELECT kind, conversation_id, payload::text FROM agent_events WHERE tenant_id=:t AND kind='subject_deleted'"),
                         {"t": t}).all()
    assert len(rows) == 1 and rows[0][1] is None
    blob = rows[0][2]
    h = hashlib.sha256(ident.lower().encode()).hexdigest()[:16]
    assert h in blob and len(json.loads(blob)["id_hash"]) == 16 and json.loads(blob)["counts"] == counts
    for leak in (ident.lower(), "jane.doe", "example.com", "0142"):
        assert leak not in blob.lower()


def test_delete_subject_best_effort_limits():
    """W4: only linked rows are found. Unlinked drafts, lead-less conversations without the external id, and free text stay."""
    t = _tenant()
    with db.system() as c:
        lead = _lead(c, t, 1, email="z@example.com")
        c.execute(text("INSERT INTO drafts (tenant_id, kind, status, payload, input_hash) VALUES (:t, 'quote', 'sent', '{}', 'u1')"), {"t": t})
        noleadconvo = _convo(c, t, None, 1, ext="other-ext")
        c.execute(text("INSERT INTO events (tenant_id, conversation_id, kind, detail) VALUES (:t, :c, 'k', 'mentions z@example.com')"),
                  {"t": t, "c": noleadconvo})
    retention.delete_subject(t, "z@example.com")
    assert lead not in _ids(t, "leads")
    assert _n(t, "drafts") == 1 and noleadconvo in _ids(t, "conversations") and _n(t, "events") == 2


@pytest.mark.parametrize("bad", ["", "   ", "x" * 255])
def test_delete_subject_rejects_bad_identifier(bad):
    with pytest.raises(ValueError):
        retention.delete_subject(str(uuid.uuid4()), bad)


# ---- coverage and payload allowlist ----
def test_every_tenant_table_is_classified():
    with db.system() as c:
        tables = set(c.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'")).scalars())
    assert tables, "introspection found nothing"
    assert not (tables - set(retention.PURGED) - set(retention.KEPT)), tables - set(retention.PURGED) - set(retention.KEPT)
    assert not set(retention.PURGED) & set(retention.KEPT)
    assert all(isinstance(v, str) and v.strip() for v in retention.KEPT.values())
    assert {"tenant_api_keys", "agent_events", "slots", "faq_chunks"} <= set(retention.KEPT)


ALLOWED_PAYLOAD_KEYS = {"draft_id", "kind", "status", "channel", "run_date", "force", "event", "person_id",
                        "first", "last", "new", "reflagged", "resolved"}  # last five: capacity_routes capacity_checked
EXEMPT = {("tools.py", "_safe_event")}  # payload is built by tools.py callers from ids/names/flags (see record_event contract)


def test_record_event_payload_keys_are_allowlisted():
    root = Path(__file__).parent
    seen = 0
    for f in sorted(root.glob("*.py")):
        if f.name.startswith("test_") or f.name == "db.py":
            continue
        tree = ast.parse(f.read_text())
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Module))]:
            for call in [n for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "record_event"]:
                if isinstance(fn, ast.FunctionDef) and call not in [x for s in fn.body for x in ast.walk(s)]:
                    continue
                payload = call.args[4] if len(call.args) > 4 else next(k.value for k in call.keywords if k.arg == "payload")
                seen += 1
                if isinstance(payload, ast.Dict):
                    keys = {k.value for k in payload.keys}
                    assert keys <= ALLOWED_PAYLOAD_KEYS, (f.name, keys - ALLOWED_PAYLOAD_KEYS)
                else:
                    owners = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                              and any(c is call for c in ast.walk(n))}
                    assert any((f.name, o) in EXEMPT for o in owners), f"non-literal record_event payload in {f.name}"
    assert seen >= 7
