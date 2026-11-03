"""POST /capacity/check, GET /capacity/flags. Bookings come from the request body, else the bookings connector.
shortcut: the appointments table is not a source (no party size)."""
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from .auth import require_tenant
from .db import record_event, tx
from .drafts import require_module
from .engine.connectors import TenantRef, fetch_source
from .engine.capacity import Booking, Flag, Override, check_capacity, classify
from .pack import get_pack

router = APIRouter(prefix="/capacity", tags=["capacity"])


class CheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bookings: list[Booking] = Field(default_factory=list, max_length=5000)
    staff_overrides: list[Override] = Field(default_factory=list, max_length=500)
    first: date | None = None
    last: date | None = None


def _flag_out(f: Flag, status: str) -> dict:
    return {"flag_key": f.flag_key, "kind": f.kind, "shift_id": f.shift_id, "date": f.shift_date.isoformat(),
            "staff": f.staff, "covers": f.covers, "capacity": f.capacity, "status": status}


@router.post("/check")
def check(body: CheckBody, tenant: str = Depends(require_tenant)):
    pack = get_pack(tenant)
    cap = require_module(pack.capacity, "capacity")
    tz = ZoneInfo(pack.meta.timezone)
    first = body.first or datetime.now(tz).date()
    last = body.last or first + timedelta(days=cap.horizon_days - 1)
    if last < first or (last - first).days >= cap.horizon_days:
        raise HTTPException(422, f"date range must be ordered and span at most {cap.horizon_days} days")
    shift_ids = {s.id for s in cap.shifts}
    bad = sorted({o.shift_id for o in body.staff_overrides} - shift_ids)
    if bad:
        raise HTTPException(422, f"unknown shift_id in staff_overrides: {bad}")
    bookings = body.bookings
    if not bookings:
        src = next((s for s in pack.connectors.sources if s.name == "bookings"), None) if pack.connectors else None
        if src is None:  # missing data must never look like "all clear" and resolve open flags
            raise HTTPException(422, "no booking source: send bookings in the request body")
        bookings = _connector_bookings(src, TenantRef(pack.slug, tenant, pack.meta.timezone), first, last)
        if bookings is None:  # flags are left untouched
            return {"source_unavailable": "bookings", "source": "mock", "checked_shifts": 0, "flags": [], "resolved": []}

    flags = check_capacity(cap, tz, bookings, first, last, body.staff_overrides)
    by_key = {f.flag_key: f for f in flags}
    checked = sum(1 for d in range((last - first).days + 1) for s in cap.shifts
                  if ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[(first + timedelta(days=d)).weekday()] in s.days)
    with tx(tenant) as c:
        # lock the rows this run can touch; absent rows are guarded by ON CONFLICT DO NOTHING below
        rs = c.execute(text("SELECT flag_key, input_hash, resolved_at IS NOT NULL AS resolved FROM capacity_flags "
                            "WHERE tenant_id=:t AND shift_date BETWEEN :a AND :b FOR UPDATE"),
                       {"t": tenant, "a": first, "b": last}).all()
        cls = classify({r.flag_key: (r.input_hash, r.resolved) for r in rs}, flags, first, last)
        for key in cls["new"]:
            f = by_key[key]
            c.execute(text("INSERT INTO capacity_flags (tenant_id, flag_key, kind, shift_id, shift_date, input_hash, details) "
                           "VALUES (:t, :k, :kind, :s, :d, :h, CAST(:det AS jsonb)) ON CONFLICT (tenant_id, flag_key) DO NOTHING"),
                      {"t": tenant, "k": key, "kind": f.kind, "s": f.shift_id, "d": f.shift_date, "h": f.input_hash,
                       "det": json.dumps(_details(f))})
        for key in cls["reflagged"]:
            f = by_key[key]
            c.execute(text("UPDATE capacity_flags SET input_hash=:h, details=CAST(:det AS jsonb), reflagged_at=now(), resolved_at=NULL "
                           "WHERE tenant_id=:t AND flag_key=:k"), {"t": tenant, "k": key, "h": f.input_hash, "det": json.dumps(_details(f))})
        for key in cls["resolved"]:
            c.execute(text("UPDATE capacity_flags SET resolved_at=now() WHERE tenant_id=:t AND flag_key=:k"), {"t": tenant, "k": key})
        record_event(c, tenant, None, "capacity_checked",
                     {"first": first.isoformat(), "last": last.isoformat(), "new": cls["new"], "reflagged": cls["reflagged"], "resolved": cls["resolved"]})
    status = {k: s for s, keys in cls.items() if s != "resolved" for k in keys}
    return {"checked_shifts": checked, "flags": [_flag_out(f, status[f.flag_key]) for f in flags], "resolved": cls["resolved"]}


def _connector_bookings(src, ref, first: date, last: date) -> list[Booking] | None:
    """Bookings for each local day from the connector; None if any day's fetch fails. An empty list is a real, checkable answer."""
    out = []
    for d in range((last - first).days + 1):
        r = fetch_source(src, ref, first + timedelta(days=d))
        if not r.ok:
            return None
        out += [Booking(start=s, covers=c) for s, c in r.bookings]
    return out


def _details(f: Flag) -> dict:
    return {"staff": f.staff, "covers": f.covers, "capacity": f.capacity, "min_staff": f.min_staff}


@router.get("/flags")
def list_flags(open: bool = False, tenant: str = Depends(require_tenant)):
    require_module(get_pack(tenant).capacity, "capacity")
    with tx(tenant) as c:
        rows = c.execute(text(
            "SELECT flag_key, kind, shift_id, shift_date, details, first_flagged_at, reflagged_at, resolved_at FROM capacity_flags "
            "WHERE tenant_id=:t AND (NOT :o OR resolved_at IS NULL) ORDER BY shift_date, flag_key LIMIT 500"),
            {"t": tenant, "o": open}).mappings().all()
    iso = lambda v: v.isoformat() if v else None
    return [{**r, "shift_date": r["shift_date"].isoformat(), "first_flagged_at": iso(r["first_flagged_at"]),
             "reflagged_at": iso(r["reflagged_at"]), "resolved_at": iso(r["resolved_at"])} for r in rows]
