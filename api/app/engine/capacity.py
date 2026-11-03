"""Capacity checker: pure functions, integer math, no I/O. Bookings come from the caller.
Windows are built from local wall time and converted to UTC; instants are compared in UTC (never local timedelta)."""
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..pack import Capacity, Shift

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # date.weekday() order


class Booking(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: AwareDatetime  # naive would be read in the server tz
    covers: int = Field(ge=1, le=1000)


class Override(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    shift_id: str
    date: date
    staff: int = Field(ge=0, le=1000)


@dataclass(frozen=True)
class Flag:
    kind: str
    shift_id: str
    shift_date: date
    staff: int
    covers: int
    capacity: int
    min_staff: int
    input_hash: str

    @property
    def flag_key(self) -> str:
        return f"{self.kind}:{self.shift_id}:{self.shift_date.isoformat()}"


def window_utc(d: date, start: time, end: time, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[start, end) of a local-date shift as UTC instants. A start inside a spring-forward gap resolves with fold=0."""
    f = lambda t: datetime.combine(d, t, tzinfo=tz).astimezone(timezone.utc)
    return f(start), f(end)


def _hash(shift: Shift, staff: int, covers: int, in_window: Sequence[Booking]) -> str:
    doc = {"staff": staff, "min_staff": shift.min_staff, "per_staff": shift.max_covers_per_staff,
           "max_covers": shift.max_covers, "covers": covers,
           "bookings": sorted((b.start.astimezone(timezone.utc).isoformat(), b.covers) for b in in_window)}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_capacity(cap: Capacity, tz: ZoneInfo, bookings: Sequence[Booking], first: date, last: date,
                   overrides: Sequence[Override] = ()) -> list[Flag]:
    rota = {(o.shift_id, o.date): o.staff for o in overrides}
    flags: list[Flag] = []
    d = first
    while d <= last:
        for sh in cap.shifts:
            if DAYS[d.weekday()] not in sh.days:
                continue
            lo, hi = window_utc(d, sh.start, sh.end, tz)
            mine = [b for b in bookings if lo <= b.start < hi]
            covers = sum(b.covers for b in mine)
            staff = rota.get((sh.id, d), sh.staff)
            capacity = staff * sh.max_covers_per_staff
            if sh.max_covers is not None:
                capacity = min(capacity, sh.max_covers)
            kinds = []
            if covers > capacity:
                kinds.append("over_capacity")
            if staff < sh.min_staff and covers > 0:
                kinds.append("understaffed")
            if staff > max(sh.min_staff, -(-covers // sh.max_covers_per_staff)):
                kinds.append("under_utilised")
            h = _hash(sh, staff, covers, mine) if kinds else ""
            flags += [Flag(k, sh.id, d, staff, covers, capacity, sh.min_staff, h) for k in kinds]
        d += timedelta(days=1)
    return flags


def classify(existing: dict[str, tuple[str, bool]], computed: Sequence[Flag], first: date, last: date) -> dict[str, list[str]]:
    """existing: flag_key -> (input_hash, is_resolved). Only unresolved flags dated inside [first, last] can resolve."""
    out: dict[str, list[str]] = {"new": [], "unchanged": [], "reflagged": [], "resolved": []}
    now = set()
    for f in computed:
        now.add(f.flag_key)
        old = existing.get(f.flag_key)
        if old is None:
            out["new"].append(f.flag_key)
        elif old[1] or old[0] != f.input_hash:
            out["reflagged"].append(f.flag_key)
        else:
            out["unchanged"].append(f.flag_key)
    for key, (_, resolved) in existing.items():
        if not resolved and key not in now and first <= date.fromisoformat(key.rsplit(":", 1)[1]) <= last:
            out["resolved"].append(key)
    return out
