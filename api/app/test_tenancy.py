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
