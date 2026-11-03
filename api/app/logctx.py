import logging
from contextvars import ContextVar

current_tenant: ContextVar[str] = ContextVar("tenant", default="-")


class TenantFilter(logging.Filter):
    """Handler-level filter, so records from every logger (third parties included) carry the tenant."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.tenant_id = current_tenant.get()
        return True
