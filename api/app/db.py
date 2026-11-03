import json
import uuid
from contextlib import contextmanager

from sqlalchemy import create_engine, text

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)


@contextmanager
def tx(tenant_id=None, eng=None):
    """Tenant transaction. set_config(..., true) is transaction-local because the pool reuses connections."""
    tid = str(uuid.UUID(str(tenant_id or settings.default_tenant_id)))  # bad input raises before any SQL
    with (eng or engine).begin() as c:
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
              {"t": str(tenant_id or settings.default_tenant_id), "c": conversation_id, "k": kind, "p": json.dumps(payload)})
