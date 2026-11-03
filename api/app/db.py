import json
import uuid
from contextlib import contextmanager

from sqlalchemy import create_engine, text

from .config import settings

# System/owner engine (bypasses RLS): bootstrap, migrations, outreach, admin. Never use it in tenant code.
engine = create_engine(settings.database_url, pool_pre_ping=True)
# Tenant engine: app_rw, subject to RLS.
app_engine = create_engine(settings.app_database_url or settings.database_url, pool_pre_ping=True)


@contextmanager
def tx(tenant_id, eng=None):
    """Tenant transaction. set_config(..., true) is transaction-local because the pool reuses connections."""
    tid = str(uuid.UUID(str(tenant_id)))  # None or bad input raises before any SQL
    with (eng or app_engine).begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tid})
        yield c


@contextmanager
def system(eng=None):
    """Explicit untenanted context: bootstrap, outreach, pilot, cross-tenant admin."""
    with (eng or engine).begin() as c:
        yield c


def record_event(c, tenant_id, conversation_id, kind: str, payload: dict) -> None:
    """Append to agent_events on the caller's open connection. Payload holds ids, names and flags only: never PII or free text from users."""
    c.execute(text("INSERT INTO agent_events (tenant_id, conversation_id, kind, payload) "
                   "VALUES (:t, :c, :k, CAST(:p AS jsonb))"),
              {"t": str(uuid.UUID(str(tenant_id))), "c": conversation_id, "k": kind, "p": json.dumps(payload)})


def assert_rls_enforced() -> None:
    """Fail startup if the tenant connection would bypass RLS (superuser, BYPASSRLS, or owner of leads)."""
    with app_engine.connect() as c:
        bad = c.execute(text(
            "SELECT r.rolsuper OR r.rolbypassrls OR pg_get_userbyid(cl.relowner) = current_user "
            "FROM pg_roles r, pg_class cl WHERE r.rolname = current_user AND cl.oid = 'public.leads'::regclass")).scalar()
    if bad is not False:
        raise RuntimeError("RLS not enforced: APP_DATABASE_URL must be a non-superuser, non-BYPASSRLS role that does not own the tables")
