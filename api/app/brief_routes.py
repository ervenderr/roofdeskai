"""POST /daily-brief (tenant key, idempotent per tenant-local date) and POST /daily-brief/due (scope: tenant or admin)."""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from .auth import Scope, require_scope, require_tenant
from .db import record_event, system, tx
from .drafts import require_module
from .engine.brief import build_brief, is_due
from .engine.connectors import TenantRef, fetch_all
from .pack import Pack, PackError, get_pack

log = logging.getLogger("leadpilot.brief")
router = APIRouter(prefix="/daily-brief", tags=["daily-brief"])


def utcnow() -> datetime:  # the single clock; tests patch this
    return datetime.now(timezone.utc)


class BriefBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    force: bool = False


def _local_date(pack: Pack, now: datetime) -> date:
    return now.astimezone(ZoneInfo(pack.meta.timezone)).date()


def _payload(pack: Pack, tenant: str, local: date) -> dict:
    ref = TenantRef(pack.slug, tenant, pack.meta.timezone)
    results = fetch_all(pack.connectors.sources, ref, local - timedelta(days=1))
    b = build_brief(pack, results, local)
    return {"local_date": local.isoformat(), "text": b.text, "html": b.html, "sections": list(b.sections),
            "disagreements": list(b.disagreements),
            "sources": [{"name": r.name, "source": r.source, "ok": r.ok, "error": r.error,
                         "metrics": {k: str(v) for k, v in r.metrics.items()}} for r in results]}


@router.post("")
def daily_brief(body: BriefBody | None = None, tenant: str = Depends(require_tenant)):
    pack = get_pack(tenant)
    require_module(pack.connectors, "connectors")
    local = _local_date(pack, utcnow())
    force = bool(body and body.force)
    with tx(tenant) as c:
        row = None if force else c.execute(text("SELECT payload FROM brief_runs WHERE tenant_id=:t AND run_date=:d"),
                                           {"t": tenant, "d": local}).scalar()
        if row is not None:
            return row
        payload = _payload(pack, tenant, local)
        c.execute(text("INSERT INTO brief_runs (tenant_id, run_date, payload) VALUES (:t, :d, CAST(:p AS jsonb)) "
                       "ON CONFLICT (tenant_id, run_date) DO UPDATE SET payload = EXCLUDED.payload WHERE :f"),
                  {"t": tenant, "d": local, "p": json.dumps(payload), "f": force})
        stored = c.execute(text("SELECT payload FROM brief_runs WHERE tenant_id=:t AND run_date=:d"), {"t": tenant, "d": local}).scalar()
        record_event(c, tenant, None, "daily_brief", {"run_date": local.isoformat(), "force": force})
    return stored


def _due_for(tenant: str, now: datetime) -> dict | None:
    try:
        pack = get_pack(tenant)
    except PackError:
        return None
    if pack.connectors is None:
        return None
    local = _local_date(pack, now)
    with tx(tenant) as c:
        ran = c.execute(text("SELECT 1 FROM brief_runs WHERE tenant_id=:t AND run_date=:d"), {"t": tenant, "d": local}).first() is not None
    send = pack.connectors.brief.send_hour
    if not is_due(now, pack.meta.timezone, send, ran):
        return None
    return {"tenant_id": tenant, "local_date": local.isoformat(), "send_hour": send}


@router.post("/due")
def due(scope: Scope = Depends(require_scope)):
    now = utcnow()
    if scope.tenant_id:
        if scope.is_admin:
            with system() as c:
                if c.execute(text("SELECT 1 FROM tenants WHERE id=:t"), {"t": scope.tenant_id}).first() is None:
                    raise HTTPException(404, "tenant not found")
        tids = [scope.tenant_id]
    else:
        with system() as c:
            tids = [str(r[0]) for r in c.execute(text("SELECT id FROM tenants ORDER BY slug"))]
    out = []
    for t in tids:
        try:
            d = _due_for(t, now)
        except Exception:  # one broken tenant must not 500 the whole listing
            log.exception("due check failed for tenant %s", t)
            continue
        if d:
            out.append(d)
    return {"due": out}
