"""EVAL-04 deterministic half: two tenants (roofing + dental packs) in one process never see each other.
Both tenants are `test-` slugs (removed by conftest), so the real tenants and their embeddings are untouched."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from . import agent, db, faq, llm, tools
from .pack import get_pack

FAR = "2032-03-02 09:00+00"
TURN_TABLES = ("leads", "conversations", "messages", "tool_calls", "llm_calls", "escalations", "events", "agent_events")


def _hash_vec(s: str) -> list[float]:
    """Deterministic 384-float vector: identical text -> identical vector, so a verbatim query matches its own chunk."""
    out, i = [], 0
    while len(out) < 384:
        out += [b / 255 - 0.5 for b in hashlib.sha256(f"{i}:{s}".encode()).digest()]
        i += 1
    return out[:384]


def _mk_tenant(tid, slug, pack):
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:i, :s, :s, 'UTC', :p) "
                       "ON CONFLICT (id) DO UPDATE SET pack_slug = EXCLUDED.pack_slug"), {"i": tid, "s": slug, "p": pack})
    return tid


@pytest.fixture
def both(monkeypatch):
    monkeypatch.setattr(llm, "embed", _hash_vec)
    monkeypatch.setattr(agent.mailer, "send", lambda *a, **k: None)
    # fresh tenants per test (agent_events is append-only, so rows cannot be reset); conftest removes `test-*` at session end
    n = uuid.uuid4().hex[:8]
    tr = _mk_tenant(str(uuid.uuid4()), f"test-roofing-{n}", "summit-roofing")
    td = _mk_tenant(str(uuid.uuid4()), f"test-dental-{n}", "bright-smile-dental")
    for t in (tr, td):
        faq.seed_faq(t, reload=True)
        tools.ensure_slots(t)
    return tr, td


def _texts(t):
    return {e.text for e in get_pack(t).faq}


def _scalar(sql, **p):
    with db.system() as c:
        return c.execute(text(sql), p).scalar()


def test_faq_rows_match_pack(both):
    TR, TD = both
    for t in both:
        assert _scalar("SELECT count(*) FROM faq_chunks WHERE tenant_id=:t", t=t) == len(get_pack(t).faq) > 0
    assert _texts(TR).isdisjoint(_texts(TD))


def test_lookup_faq_never_crosses(both):
    TR, TD = both
    for own, other in ((TR, TD), (TD, TR)):
        own_t, other_t = _texts(own), _texts(other)
        got = set(tools.lookup_faq("anything", k=50, tenant_id=own)["chunks"])
        assert got == own_t and got.isdisjoint(other_t)
        for q in sorted(other_t):  # query text copied verbatim from the other tenant's FAQ
            chunks = tools.lookup_faq(q, k=50, tenant_id=own)["chunks"]
            assert chunks and set(chunks) <= own_t and len(chunks) == min(50, len(own_t))
        assert len(tools.lookup_faq(sorted(other_t)[0], k=2, tenant_id=own)["chunks"]) == 2


def test_keyword_fallback_never_crosses(both):
    TR, TD = both
    roof = tools._faq_keywords("roof inspection shingle warranty", 10, tenant_id=TD)
    assert not set(roof) & _texts(TR)
    tooth = tools._faq_keywords("tooth cleaning", 10, tenant_id=TR)
    assert not set(tooth) & _texts(TD)
    # non-empty own side: the same kind of query does hit in its own tenant
    assert tools._faq_keywords("tooth cleaning", 10, tenant_id=TD)
    assert tools._faq_keywords("roof inspection shingle warranty", 10, tenant_id=TR)


def _qualified_lead(c, t):
    return c.execute(text("INSERT INTO leads (tenant_id, status) VALUES (:t, 'qualified') RETURNING id"), {"t": t}).scalar()


def _slot_at(c, t, ts):
    return c.execute(text("INSERT INTO slots (tenant_id, start_time, end_time) VALUES (:t, :s, :s) RETURNING id"),
                     {"t": t, "s": ts}).scalar()


def test_same_instant_booked_in_both_tenants(both):
    tr, td = both
    with db.system() as c:
        lr, ld = _qualified_lead(c, tr), _qualified_lead(c, td)
        sr, sd = _slot_at(c, tr, FAR), _slot_at(c, td, FAR)
    assert tools.book_appointment(lr, sr, tenant_id=tr)["start"] == tools.book_appointment(ld, sd, tenant_id=td)["start"]
    with db.system() as c:
        rows = c.execute(text("SELECT a.tenant_id::text, l.tenant_id::text, s.tenant_id::text, s.is_booked FROM appointments a "
                              "JOIN leads l ON l.id=a.lead_id JOIN slots s ON s.id=a.slot_id WHERE a.lead_id = ANY(:l)"),
                         {"l": [lr, ld]}).all()
    assert sorted(r[0] for r in rows) == sorted([tr, td]) and all(r[0] == r[1] == r[2] and r[3] for r in rows)


def test_cannot_book_other_tenants_slot(both):
    tr, td = both
    with db.system() as c:
        ld, sr = _qualified_lead(c, td), _slot_at(c, tr, "2032-03-03 09:00+00")
    with pytest.raises(tools.ToolError):
        tools.book_appointment(ld, sr, tenant_id=td)
    assert not _scalar("SELECT is_booked FROM slots WHERE id=:i", i=sr)
    assert _scalar("SELECT count(*) FROM appointments WHERE slot_id=:i", i=sr) == 0


def _slots(t):
    with db.system() as c:
        return c.execute(text("SELECT start_time, end_time FROM slots WHERE tenant_id=:t"), {"t": t}).all()


def test_dental_slots_are_zurich_wall_clock(both):
    TR, TD = both
    cal = get_pack(TD).calendar
    zone = ZoneInfo("Europe/Zurich")
    rows = _slots(TD)
    assert cal.timezone == "Europe/Zurich" and cal.slot_minutes == 30
    for s, e in rows:
        local = s.astimezone(zone)
        assert local.hour in cal.slot_hours and local.minute == 0 and local.isoweekday() <= 5
        assert e - s == timedelta(minutes=30)
    today = datetime.now(timezone.utc).astimezone(zone).date()
    days = [today + timedelta(days=i) for i in range(1, cal.days_ahead + 1)]
    assert len(rows) == sum(d.isoweekday() <= 5 for d in days) * len(cal.slot_hours)


def test_roofing_slots_stay_utc(both):
    TR, TD = both
    cal = get_pack(TR).calendar
    rows = _slots(TR)
    assert rows and all(s.astimezone(timezone.utc).hour in cal.slot_hours and e - s == timedelta(minutes=cal.slot_minutes)
                        for s, e in rows)


def test_conversation_not_continuable_across_tenants(both):
    tr, td = both
    with db.tx(td) as c:
        lead = c.execute(text("INSERT INTO leads (tenant_id) VALUES (:t) RETURNING id"), {"t": td}).scalar()
        cid = c.execute(text("INSERT INTO conversations (tenant_id, lead_id) VALUES (:t,:l) RETURNING id"), {"t": td, "l": lead}).scalar()
    with pytest.raises(LookupError):
        agent.handle_turn("hello", cid, tenant_id=tr)
    assert _scalar("SELECT count(*) FROM messages WHERE conversation_id=:i", i=cid) == 0
    assert not agent.token_matches(cid, agent.conversation_token(cid, tenant_id=td), tenant_id=tr)


# ---- interleaved conversations (scripted model, no network) ----
ROOF_MSG = "I own 1 A St, Denver and need a repair within 1 month. Sam, 303-555-0142"
ROOF_TURN = {"reply": "", "extracted": {"service_type": "repair", "is_owner": True, "address": "1 A St, Denver",
                                         "timeline_months": 1, "name": "Sam", "phone": "303-555-0142"}}
DENT_MSG = "I'd like a teeth cleaning. Rosenweg 12, 8001 Zurich. Anna Keller, 044 555 0142"
DENT_TURN = {"reply": "", "extracted": {"service_type": "cleaning", "address": "Rosenweg 12, 8001 Zurich",
                                         "name": "Anna Keller", "phone": "044 555 0142"}}


def _script(monkeypatch):
    calls = []
    queues = {"Summit Roofing": [ROOF_TURN, {"reply": ""}], "Bright Smile Dental": [DENT_TURN, {"reply": ""}]}

    def chat(messages):
        system = messages[0]["content"]
        calls.append(system)
        biz = [b for b in queues if b in system]
        assert len(biz) == 1, "prompt must name exactly one business"
        return {"content": json.dumps(queues[biz[0]].pop(0)), "model": "fake", "prompt_tokens": 1, "completion_tokens": 1, "latency_ms": 1}

    monkeypatch.setattr(llm, "chat", chat)
    return calls


def _counts(t):
    with db.system() as c:
        return {x: c.execute(text(f"SELECT count(*) FROM {x} WHERE tenant_id=:t"), {"t": t}).scalar() for x in TURN_TABLES}


def test_interleaved_conversations_do_not_cross(both, monkeypatch):
    tr, td = both
    prompts = _script(monkeypatch)
    cr, _ = agent.handle_turn(ROOF_MSG, tenant_id=tr)
    roof_before = _counts(tr)
    cd, _ = agent.handle_turn(DENT_MSG, tenant_id=td)
    assert _counts(tr) == roof_before  # dental turn wrote nothing to roofing
    agent.handle_turn("the first one", cr, tenant_id=tr)
    roof_after = _counts(tr)
    agent.handle_turn("the first one", cd, tenant_id=td)
    assert _counts(tr) == roof_after

    for cid, t in ((cr, tr), (cd, td)):
        assert _scalar("SELECT state||'/'||outcome FROM conversations WHERE id=:i AND tenant_id=:t", i=cid, t=t) == "DONE/booked"
        assert _scalar("SELECT count(*) FROM appointments WHERE tenant_id=:t", t=t) == 1
    assert _scalar("SELECT count(*) FROM appointments a JOIN slots s ON s.id=a.slot_id WHERE a.tenant_id<>s.tenant_id") == 0
    with db.system() as c:
        for child in ("messages", "tool_calls", "llm_calls", "escalations", "agent_events"):
            bad = c.execute(text(f"SELECT count(*) FROM {child} x JOIN conversations v ON v.id=x.conversation_id "
                                 "WHERE x.tenant_id<>v.tenant_id AND v.tenant_id = ANY(CAST(:t AS uuid[]))"), {"t": [tr, td]}).scalar()
            assert bad == 0, child
        assert c.execute(text("SELECT count(*) FROM leads l JOIN conversations v ON v.lead_id=l.id WHERE l.tenant_id<>v.tenant_id")).scalar() == 0
        for t in (tr, td):
            assert c.execute(text("SELECT count(*) FROM tool_calls WHERE tenant_id=:t AND tool_name='lookup_faq'"), {"t": t}).scalar() > 0
        slot_ids = {r[0] for r in c.execute(text("SELECT id FROM slots WHERE tenant_id=:t"), {"t": td})}
        booked = c.execute(text("SELECT args_json->>'slot_id' FROM tool_calls WHERE conversation_id=:c AND tool_name='book_appointment'"), {"c": cd}).scalars().all()
        assert booked and all(int(s) in slot_ids for s in booked)
        replies = {cid: " ".join(c.execute(text("SELECT content FROM messages WHERE conversation_id=:c AND role='assistant'"), {"c": cid}).scalars())
                   for cid in (cr, cd)}
    assert not re.search(r"(?i)summit|denver|shingle|roof", replies[cd]) and "Bright Smile" not in replies[cr]
    assert not re.search(r"(?i)bright smile|zurich|twint|winterthur", replies[cr]) and replies[cd] and replies[cr]

    roof_faq, dent_faq = _texts(tr), _texts(td)
    dental_prompts = [p for p in prompts if "Bright Smile Dental" in p]
    roof_prompts = [p for p in prompts if "Summit Roofing" in p]
    assert len(dental_prompts) == 2 and len(roof_prompts) == 2
    for p in dental_prompts:
        assert "Summit Roofing" not in p and not any(x in p for x in roof_faq)
        # "Denver" appears only in the shared template's static extraction example (identical for every tenant), not from tenant data
        assert p.count("Denver") == llm.load_prompt(agent.PROMPT)[1].count("Denver")
        assert any(x in p for x in dent_faq)
    for p in roof_prompts:
        assert not re.search(r"Bright Smile Dental|Zurich", p) and not any(x in p for x in dent_faq)
        assert any(x in p for x in roof_faq)
