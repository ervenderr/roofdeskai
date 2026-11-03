"""POST /intake_event (tenant key): pack-mapped waiver/check-in/result events, one idempotent row per person. Distinct from untenanted /intake. Ids only in logs and events."""
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from .auth import require_tenant
from .db import record_event, tx
from .drafts import require_module
from .engine.intake import NormalisedEvent, normalise_event
from .pack import get_pack

log = logging.getLogger("leadpilot.intake_event")
router = APIRouter(tags=["intake_event"])
MAX_PAYLOAD_BYTES = 32_768

_BASE = "INSERT INTO intake_people (tenant_id, person_key, name, {cols}) VALUES (:t, :k, :n, {vals}) ON CONFLICT (tenant_id, person_key) DO UPDATE SET name = COALESCE(intake_people.name, EXCLUDED.name), {sets}, updated_at = now() RETURNING id, (xmax = 0) AS created"
SQL = {
    e: text(_BASE.format(cols=f"{e}_at", vals=":at", sets=f"{e}_at = LEAST(intake_people.{e}_at, EXCLUDED.{e}_at)"))
    for e in ("waiver", "checkin")
}
SQL["result"] = text(_BASE.format(
    cols="result, result_at", vals="CAST(:r AS jsonb), :at",
    sets="result = CASE WHEN intake_people.result_at IS NULL OR EXCLUDED.result_at >= intake_people.result_at THEN EXCLUDED.result ELSE intake_people.result END, "
         "result_at = CASE WHEN intake_people.result_at IS NULL OR EXCLUDED.result_at >= intake_people.result_at THEN EXCLUDED.result_at ELSE intake_people.result_at END"))


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["waiver", "checkin", "result"]
    payload: dict


def _422(errs) -> HTTPException:
    return HTTPException(422, [{"event": e.event, "field": e.field, "tried": list(e.tried), "msg": e.msg} for e in errs])


def _upsert(tenant: str, ev: NormalisedEvent) -> tuple[int, bool]:
    params = {"t": tenant, "k": ev.person_key, "n": ev.name, "at": ev.occurred_at}
    if ev.event == "result":
        params["r"] = json.dumps(ev.fields)
    with tx(tenant) as c:
        pid, created = c.execute(SQL[ev.event], params).one()
        record_event(c, tenant, None, "intake_event", {"event": ev.event, "person_id": pid})
    return pid, created


@router.post("/intake_event")
def intake_event(body: EventIn, tenant: str = Depends(require_tenant)):
    pack = get_pack(tenant)
    intake = require_module(pack.meta.intake, "intake")
    emap = getattr(intake, body.event)
    if emap is None:
        raise HTTPException(422, [{"event": body.event, "field": "event", "tried": [], "msg": "event not mapped"}])
    if len(json.dumps(body.payload)) > MAX_PAYLOAD_BYTES:
        raise HTTPException(422, [{"event": body.event, "field": "payload", "tried": [], "msg": "too large"}])
    ev = normalise_event(emap, body.event, body.payload)
    if isinstance(ev, list):
        raise _422(ev)
    pid, created = _upsert(tenant, ev)
    log.info("intake_event tenant=%s event=%s person_id=%s created=%s", tenant, ev.event, pid, created)
    return {"person_id": pid, "created": created}
