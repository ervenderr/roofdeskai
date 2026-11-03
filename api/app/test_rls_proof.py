"""RLS enforcement on a scratch DB bootstrapped with the real migrations (005), queried as the real app_rw role."""
import secrets

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .bootstrap import bootstrap_schema, set_app_role_login
from .config import settings
from .db import engine, system, tx

TABLES = ("leads", "conversations", "messages", "slots", "appointments", "faq_chunks",
          "tool_calls", "escalations", "events", "llm_calls", "agent_events")
HAD_DEFAULT = TABLES[:9]
B = "00000000-0000-0000-0000-0000000000b2"
A = settings.default_tenant_id

# one valid INSERT per table, minimal columns; {t} = tenant id param, conversation/lead ids come from fixture
INSERTS = {
    "leads": "INSERT INTO leads (name, tenant_id) VALUES ('x', :t)",
    "conversations": "INSERT INTO conversations (tenant_id) VALUES (:t)",
    "messages": "INSERT INTO messages (tenant_id, conversation_id, role, content) "
                "SELECT :t, id, 'user', 'x' FROM conversations WHERE tenant_id=:t LIMIT 1",
    "slots": "INSERT INTO slots (start_time, end_time, tenant_id) VALUES (now(), now() + interval '1 hour', :t)",
    "appointments": "INSERT INTO appointments (tenant_id, lead_id, slot_id) "
                    "SELECT :t, (SELECT id FROM leads WHERE tenant_id=:t LIMIT 1), (SELECT id FROM slots WHERE tenant_id=:t LIMIT 1)",
    "faq_chunks": "INSERT INTO faq_chunks (tenant_id, source, text) VALUES (:t, 's', 'x')",
    "tool_calls": "INSERT INTO tool_calls (tenant_id, conversation_id, tool_name) "
                  "SELECT :t, id, 'x' FROM conversations WHERE tenant_id=:t LIMIT 1",
    "escalations": "INSERT INTO escalations (tenant_id, conversation_id, reason) "
                   "SELECT :t, id, 'x' FROM conversations WHERE tenant_id=:t LIMIT 1",
    "events": "INSERT INTO events (tenant_id, conversation_id, kind) "
              "SELECT :t, id, 'x' FROM conversations WHERE tenant_id=:t LIMIT 1",
    "llm_calls": "INSERT INTO llm_calls (tenant_id, model) VALUES (:t, 'm')",
    "agent_events": "INSERT INTO agent_events (tenant_id, conversation_id, kind) VALUES (:t, 1, 'turn')",
}


@pytest.fixture
def rls(scratch_db):
    bootstrap_schema(scratch_db)
    pw, db_name = secrets.token_hex(16), scratch_db.url.database
    set_app_role_login(scratch_db, pw)  # shared cluster-wide role: password restored in teardown
    with system(scratch_db) as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:b, 'rls-b', 'B', 'UTC', 'x')"), {"b": B})
        c.execute(text("DELETE FROM slots"))
        c.execute(text("DELETE FROM faq_chunks"))
        for tid in (A, B):
            for t in TABLES:
                c.execute(text(INSERTS[t]), {"t": tid})
    url = make_url(settings.database_url).set(username="app_rw", password=pw, database=db_name)
    role_eng = create_engine(url, pool_size=1, max_overflow=0)
    try:
        yield scratch_db, role_eng
    finally:
        role_eng.dispose()
        set_app_role_login(engine)  # restore the password the running API expects


def _n(c, t):
    return c.execute(text(f"SELECT count(*) FROM {t}")).scalar()


@pytest.mark.parametrize("tid", [A, B])
@pytest.mark.parametrize("t", TABLES)
def test_tenant_sees_only_own_rows(rls, tid, t):
    _, role_eng = rls
    with tx(tid, eng=role_eng) as c:
        assert _n(c, t) == 1
        assert c.execute(text(f"SELECT tenant_id::text FROM {t}")).scalar() == tid


@pytest.mark.parametrize("t", TABLES)
def test_no_tenant_set_fails_closed(rls, t):
    _, role_eng = rls
    with system(role_eng) as c:
        assert _n(c, t) == 0


SELF_CONTAINED = ("leads", "conversations", "slots", "faq_chunks", "llm_calls", "agent_events")


@pytest.mark.parametrize("t", SELF_CONTAINED)
def test_no_context_insert_rejected(rls, t):
    _, role_eng = rls
    with pytest.raises(Exception, match="row-level security"):
        with system(role_eng) as c:
            c.execute(text(INSERTS[t]), {"t": A})


def test_insert_for_other_tenant_rejected(rls):
    _, role_eng = rls
    with pytest.raises(Exception, match="row-level security"):
        with tx(A, eng=role_eng) as c:
            c.execute(text("INSERT INTO leads (name, tenant_id) VALUES ('evil', :t)"), {"t": B})


def test_setting_is_transaction_local(rls):
    _, role_eng = rls  # pool of 1: the second tx reuses the same connection
    with tx(A, eng=role_eng) as c:
        assert _n(c, "leads") == 1
    with system(role_eng) as c:
        assert _n(c, "leads") == 0
        assert not c.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar()


@pytest.mark.parametrize("t", TABLES)
def test_superuser_control_sees_all(rls, t):
    scratch, _ = rls
    with system(scratch) as c:
        assert _n(c, t) == 2


def test_catalog_rls_forced_and_defaults_dropped(rls):
    scratch, _ = rls
    with system(scratch) as c:
        tabs = {r[0] for r in c.execute(text(
            "SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='tenant_id'"))}
        assert tabs - {"tenant_api_keys"} == set(TABLES)  # keys table has tenant_id but is system-only, no RLS
        for t in TABLES:
            assert c.execute(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=CAST(:t AS regclass)"),
                             {"t": t}).scalar() is True, t
            assert c.execute(text("SELECT count(*) FROM pg_policies WHERE tablename=:t AND policyname='tenant_isolation'"),
                             {"t": t}).scalar() == 1
        for t in HAD_DEFAULT:
            assert c.execute(text("SELECT column_default FROM information_schema.columns "
                                  "WHERE table_name=:t AND column_name='tenant_id'"), {"t": t}).scalar() is None, t


def test_app_rw_role_and_privileges(rls):
    scratch, _ = rls
    with system(scratch) as c:
        assert tuple(c.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='app_rw'")).one()) == (False, False)
        assert c.execute(text("SELECT pg_get_userbyid(relowner) <> 'app_rw' FROM pg_class WHERE relname='leads'")).scalar()
        for t in ("tenants", "tenant_api_keys", "prospects", "eval_runs"):
            assert not c.execute(text("SELECT has_table_privilege('app_rw', :t, 'SELECT')"), {"t": t}).scalar(), t
        p = lambda priv: c.execute(text("SELECT has_table_privilege('app_rw', 'agent_events', :p)"), {"p": priv}).scalar()
        assert p("INSERT") and p("SELECT") and not p("UPDATE") and not p("DELETE")
