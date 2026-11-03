"""RLS pattern proof on a scratch DB (D-11). Test-only: no policies exist on real tables or in db/migrations.
Production switch to a non-owner app role, a separate migration owner role and real policies are Phase 6."""
import secrets
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .bootstrap import bootstrap_schema
from .config import settings
from .db import engine, system, tx

TABLES = ("leads", "slots")
B = "00000000-0000-0000-0000-0000000000b2"
A = settings.default_tenant_id


@pytest.fixture
def rls(scratch_db):
    bootstrap_schema(scratch_db)
    role, pw = f"rls_probe_{secrets.token_hex(4)}", secrets.token_hex(16)
    db_name = scratch_db.url.database
    with system(engine) as c:  # roles are cluster-wide
        c.execute(text(f"CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{pw}'"))
    try:
        with system(scratch_db) as c:
            c.execute(text(f"INSERT INTO tenants (id, slug, name, timezone, pack_slug) "
                           f"VALUES ('{B}', 'rls-b', 'B', 'UTC', 'x')"))
            c.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
            c.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TABLES)} TO {role}"))
            c.execute(text(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {role}"))
            for t in TABLES:
                c.execute(text(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY"))
                c.execute(text(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY"))
                c.execute(text(f"CREATE POLICY tenant_isolation ON {t} "
                               "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
                               "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"))
            c.execute(text("DELETE FROM slots"))  # baseline seeds demo slots; start from a known count
            for tid in (A, B):
                c.execute(text("INSERT INTO leads (name, tenant_id) VALUES ('x', :t)"), {"t": tid})
                c.execute(text("INSERT INTO slots (start_time, end_time, tenant_id) "
                               "VALUES (now(), now() + interval '1 hour', :t)"), {"t": tid})
        url = make_url(settings.database_url).set(username=role, password=pw, database=db_name)
        role_eng = create_engine(url, pool_size=1, max_overflow=0)
        yield scratch_db, role_eng
        role_eng.dispose()
    finally:
        scratch_db.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))  # DROP ROLE needs the db gone first
            c.execute(text(f"DROP ROLE IF EXISTS {role}"))


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


def test_superuser_control_sees_all(rls):
    scratch, _ = rls
    with system(scratch) as c:
        assert _n(c, "leads") == 2
        assert _n(c, "slots") == 2
