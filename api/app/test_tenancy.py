import uuid

import pytest
from sqlalchemy import create_engine, text

from .config import settings
from .db import system, tx

SETTING = text("SELECT current_setting('app.tenant_id', true)")


def test_tx_sets_tenant():
    t = str(uuid.uuid4())
    with tx(t) as c:
        assert c.execute(SETTING).scalar() == t


def test_tx_default_tenant():
    with tx() as c:
        assert c.execute(SETTING).scalar() == settings.default_tenant_id


def test_tx_rejects_bad_uuid():
    with pytest.raises(ValueError):
        with tx("not-a-uuid"):
            pytest.fail("body must not run")


def test_no_leak_on_reused_connection():
    eng = create_engine(settings.database_url, pool_size=1, max_overflow=0)
    try:
        with tx(str(uuid.uuid4()), eng=eng):
            pass
        with eng.begin() as c:
            assert not c.execute(SETTING).scalar()
        with system(eng=eng) as c:
            assert not c.execute(SETTING).scalar()
    finally:
        eng.dispose()


# ---- schema (migrations 002-004) ----
from sqlalchemy.exc import IntegrityError, DBAPIError

from . import bootstrap

TENANT_TABLES = ("leads", "conversations", "messages", "slots", "appointments",
                 "faq_chunks", "tool_calls", "escalations", "events")
UNTENANTED = ("campaigns", "prospects", "outreach_messages", "suppressions", "prospect_events", "scrape_runs")
B = "00000000-0000-0000-0000-0000000000b2"
A = settings.default_tenant_id


@pytest.fixture
def two(scratch_db):
    bootstrap.bootstrap_schema(scratch_db)
    with scratch_db.begin() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone) VALUES (:b, 'test-b', 'B', 'UTC')"), {"b": B})
    return scratch_db


def _slot(c, t, ts="2030-01-01 09:00+00"):
    return c.execute(text("INSERT INTO slots (tenant_id, start_time, end_time) VALUES (:t, :s, :s) RETURNING id"),
                     {"t": t, "s": ts}).scalar()


def _lead(c, t):
    return c.execute(text("INSERT INTO leads (tenant_id) VALUES (:t) RETURNING id"), {"t": t}).scalar()


def test_same_slot_time_two_tenants_ok_same_tenant_rejected(two):
    with two.begin() as c:
        _slot(c, A); _slot(c, B)
    with pytest.raises(IntegrityError), two.begin() as c:
        _slot(c, A)


def test_same_external_id_two_tenants(two):
    q = text("INSERT INTO conversations (tenant_id, external_id) VALUES (:t, 'x')")
    with two.begin() as c:
        c.execute(q, {"t": A}); c.execute(q, {"t": B})
    with pytest.raises(IntegrityError), two.begin() as c:
        c.execute(q, {"t": A})


def test_cross_tenant_appointment_rejected(two):
    with two.begin() as c:
        la, sa, sb = _lead(c, A), _slot(c, A), _slot(c, B)
    ins = text("INSERT INTO appointments (tenant_id, lead_id, slot_id) VALUES (:t, :l, :s)")
    with pytest.raises(IntegrityError), two.begin() as c:
        c.execute(ins, {"t": B, "l": la, "s": sb})  # lead belongs to A
    with pytest.raises(IntegrityError), two.begin() as c:
        c.execute(ins, {"t": B, "l": _lead(c, B), "s": sa})  # slot belongs to A


def test_one_appointment_per_slot_and_lead_per_tenant(two):
    with two.begin() as c:
        l1, l2, s1, s2 = _lead(c, A), _lead(c, A), _slot(c, A), _slot(c, A, "2030-01-01 11:00+00")
        c.execute(text("INSERT INTO appointments (tenant_id, lead_id, slot_id) VALUES (:t,:l,:s)"), {"t": A, "l": l1, "s": s1})
    for l, s in ((l2, s1), (l1, s2)):
        with pytest.raises(IntegrityError), two.begin() as c:
            c.execute(text("INSERT INTO appointments (tenant_id, lead_id, slot_id) VALUES (:t,:l,:s)"), {"t": A, "l": l, "s": s})


def test_cross_tenant_message_rejected(two):
    with two.begin() as c:
        cid = c.execute(text("INSERT INTO conversations (tenant_id) VALUES (:t) RETURNING id"), {"t": A}).scalar()
    with pytest.raises(IntegrityError), two.begin() as c:
        c.execute(text("INSERT INTO messages (tenant_id, conversation_id, role, content) VALUES (:t,:c,'user','hi')"), {"t": B, "c": cid})


def test_tenant_id_columns(two):
    with two.begin() as c:
        rows = {r[0]: r[1:] for r in c.execute(text(
            "SELECT table_name, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema='public' AND column_name='tenant_id'"))}
    for t in TENANT_TABLES:
        assert rows[t][0] == "NO" and A in rows[t][1], t
    assert tuple(rows["llm_calls"]) == ("YES", None)


def test_llm_calls_outreach_row_keeps_null_tenant(two):
    with two.begin() as c:
        c.execute(text("INSERT INTO llm_calls (model) VALUES ('m')"))
        assert c.execute(text("SELECT tenant_id FROM llm_calls")).scalar() is None


def test_untenanted_tables_have_no_tenant_id(two):
    with two.begin() as c:
        n = c.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' "
                           "AND column_name='tenant_id' AND table_name = ANY(:t)"), {"t": list(UNTENANTED)}).scalar()
    assert n == 0


def test_agent_events_append_only(two):
    with two.begin() as c:  # no FK to conversations
        c.execute(text("INSERT INTO agent_events (tenant_id, conversation_id, kind) VALUES (:t, 999999, 'turn')"), {"t": A})
        assert c.execute(text("SELECT payload FROM agent_events")).scalar() == {}
    for sql in ("UPDATE agent_events SET kind='x'", "DELETE FROM agent_events", "TRUNCATE agent_events"):
        with pytest.raises(DBAPIError, match="append-only"), two.begin() as c:
            c.execute(text(sql))


# ---- tools / faq per tenant (plan 02-03); runs on the dev DB, conftest removes test-* tenants ----
import logging

from . import db, faq, tools

TB = "00000000-0000-0000-0000-0000000000b3"
VEC = [0.1] * 384


@pytest.fixture
def tb():
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone) VALUES (:b, 'test-b3', 'B', 'UTC') "
                       "ON CONFLICT DO NOTHING"), {"b": TB})
    return TB


def _count(table, t, where=""):
    with db.system() as c:
        return c.execute(text(f"SELECT count(*) FROM {table} WHERE tenant_id=:t {where}"), {"t": t}).scalar()


def test_ensure_slots_second_tenant(tb):
    tools.ensure_slots()  # A already has slots
    a = _count("slots", A)
    assert _count("slots", tb) == 0 and a > 0
    tools.ensure_slots(tenant_id=tb)
    b = _count("slots", tb)
    assert b > 0 and _count("slots", A) == a
    tools.ensure_slots(tenant_id=tb)
    assert _count("slots", tb) == b


def test_get_available_slots_scoped(tb):
    with db.tx(tb) as c:
        sid = _slot(c, tb, "2031-01-01 09:00+00")
    ids = {s["id"] for s in tools.get_available_slots(limit=1000, tenant_id=tb)["slots"]}
    assert sid in ids
    assert sid not in {s["id"] for s in tools.get_available_slots(limit=1000)["slots"]}


def test_seed_faq_per_tenant(tb, monkeypatch):
    monkeypatch.setattr(faq.llm, "embed", lambda t: VEC)
    a = _count("faq_chunks", A)
    faq.seed_faq(tenant_id=tb)
    n = _count("faq_chunks", tb)
    assert n == len(faq.FAQ) and _count("faq_chunks", A) == a
    faq.seed_faq(tenant_id=tb)
    assert _count("faq_chunks", tb) == n
    with db.system() as c:
        old = {r[0] for r in c.execute(text("SELECT id FROM faq_chunks WHERE tenant_id=:t"), {"t": tb})}
    faq.seed_faq(tenant_id=tb, reload=True)
    with db.system() as c:
        new = {r[0] for r in c.execute(text("SELECT id FROM faq_chunks WHERE tenant_id=:t"), {"t": tb})}
    assert len(new) == n and not (old & new) and _count("faq_chunks", A) == a


def test_lookup_faq_scoped(tb, monkeypatch):
    monkeypatch.setattr(tools.llm, "embed", lambda t: VEC)
    with db.tx(tb) as c:
        c.execute(text("DELETE FROM faq_chunks WHERE tenant_id=:t"), {"t": tb})
        c.execute(text("INSERT INTO faq_chunks (tenant_id, source, text, embedding) VALUES (:t,'x','zebra only here',CAST(:e AS vector))"),
                  {"t": tb, "e": faq.vector_literal(VEC)})
    assert tools.lookup_faq("q", tenant_id=tb)["chunks"] == ["zebra only here"]
    assert "zebra only here" not in tools.lookup_faq("q", k=50)["chunks"]
    assert tools._faq_keywords("zebra", 5, tenant_id=tb) == ["zebra only here"]
    assert tools._faq_keywords("zebra", 5) == []


def _convo(tenant, **kw):
    with db.tx(tenant) as c:
        lead = _lead(c, tenant)
        return lead, c.execute(text("INSERT INTO conversations (tenant_id, lead_id) VALUES (:t,:l) RETURNING id"),
                               {"t": tenant, "l": lead}).scalar()


def test_cross_tenant_lead_untouched(tb):
    lead_a, _ = _convo(A)
    with db.tx(tb) as c:
        slot_b = _slot(c, tb, "2031-02-01 09:00+00")
    with db.system() as c:
        c.execute(text("UPDATE leads SET status='qualified' WHERE id=:i"), {"i": lead_a})
    with pytest.raises(tools.ToolError):
        tools.book_appointment(lead_a, slot_b, tenant_id=tb)
    tools.update_lead(lead_a, {"name": "Hacked"}, tenant_id=tb)
    with db.system() as c:
        assert c.execute(text("SELECT name FROM leads WHERE id=:i"), {"i": lead_a}).scalar() is None
        assert c.execute(text("SELECT status FROM leads WHERE id=:i"), {"i": lead_a}).scalar() == "qualified"
        assert not c.execute(text("SELECT is_booked FROM slots WHERE id=:i"), {"i": slot_b}).scalar()


def _events(t, cid):
    with db.system() as c:
        return c.execute(text("SELECT kind, payload FROM agent_events WHERE tenant_id=:t AND conversation_id=:c ORDER BY id"),
                         {"t": t, "c": cid}).all()


def test_run_writes_tool_call_event(tb):
    _, cid = _convo(tb)
    ok, _ = tools.run(cid, "get_available_slots", {"limit": 1}, tools.get_available_slots, tenant_id=tb)
    assert ok
    [(kind, payload)] = _events(tb, cid)
    assert kind == "tool_call" and set(payload) == {"name", "ok", "ms"} and payload["name"] == "get_available_slots"
    with db.system() as c:
        assert c.execute(text("SELECT tenant_id::text FROM tool_calls WHERE conversation_id=:c"), {"c": cid}).scalar() == tb


def test_run_ignores_model_supplied_tenant(tb):
    _, cid = _convo(tb)
    ok, res = tools.run(cid, "get_available_slots", {"limit": 1, "tenant_id": A}, tools.get_available_slots, tenant_id=tb)
    assert ok and _events(tb, cid) and not _events(A, cid)


def test_escalation_event_stamped(tb):
    _, cid = _convo(tb)
    tools.escalate_to_human(cid, "wants human", tenant_id=tb)
    assert [(k, p) for k, p in _events(tb, cid)] == [("escalation", {"reason": "wants human"})]


def test_event_failure_does_not_block_tool(tb, monkeypatch, caplog):
    _, cid = _convo(tb)
    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(tools, "record_event", boom)
    with caplog.at_level(logging.ERROR, logger="leadpilot.tools"):
        ok, _ = tools.run(cid, "get_available_slots", {"limit": 1}, tools.get_available_slots, tenant_id=tb)
    assert ok and "agent_events" in caplog.text
