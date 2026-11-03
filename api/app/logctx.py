import logging
from contextvars import ContextVar

from .engine.mask import mask

current_tenant: ContextVar[str] = ContextVar("tenant", default="-")


class TenantFilter(logging.Filter):
    """Handler-level filter, so records from every logger (third parties included) carry the tenant."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.tenant_id = current_tenant.get()
        return True


def _mask_args(args):
    # keep type and length: uvicorn's AccessFormatter unpacks a 5-tuple from record.args
    if isinstance(args, tuple):
        return tuple(mask(a) if isinstance(a, str) else a for a in args)
    if isinstance(args, dict):
        return {k: mask(v) if isinstance(v, str) else v for k, v in args.items()}
    return args


class PiiMaskFilter(logging.Filter):
    """Masks email and phone in msg, each str arg and the traceback. Always lets the record through."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = mask(record.msg)
            record.args = _mask_args(record.args)
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = mask(record.exc_text)
        except Exception:
            record.msg, record.args, record.exc_info, record.exc_text = "[log withheld]", (), None, None
        return True
