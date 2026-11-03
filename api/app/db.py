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
