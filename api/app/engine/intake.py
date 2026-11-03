"""MOD-07: pure intake_event normalisation and merge. No DB, no logging; errors name mapping paths, never values."""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

MISSING = object()
MAX_KEY = MAX_NAME = 200
MAX_STR = 500
_PHONE = re.compile(r"^\+?[\d\s().\-]+$")


@dataclass(frozen=True)
class FieldError:
    event: str
    field: str
    tried: tuple[str, ...]
    msg: str


@dataclass(frozen=True)
class NormalisedEvent:
    event: str
    person_key: str
    name: str | None
    occurred_at: datetime
    fields: dict


def get_path(obj, path: str):
    for seg in path.split("."):
        if not isinstance(obj, dict) or seg not in obj:
            return MISSING
        obj = obj[seg]
    return obj


def _empty(v) -> bool:
    return v is MISSING or v is None or (isinstance(v, str) and not v.strip())


def _key(v) -> str | None:
    if isinstance(v, bool) or not isinstance(v, (str, int)):
        return None
    s = str(v).strip()
    if not s or len(s) > MAX_KEY:
        return None
    if "@" in s:
        return s.lower()
    if _PHONE.match(s) and sum(c.isdigit() for c in s) >= 7:
        return ("+" if s.startswith("+") else "") + "".join(c for c in s if c.isdigit())
    return s.lower()


def _when(v, now: datetime) -> datetime:
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.strip())
        except ValueError:
            return now
        if d.tzinfo is not None:
            return d.astimezone(timezone.utc)
    return now


def normalise_event(emap, event: str, payload: dict, now: datetime | None = None) -> NormalisedEvent | list[FieldError]:
    now = now or datetime.now(timezone.utc)
    tried = tuple(emap.person_key)
    vals = [v for v in (get_path(payload, p) for p in tried) if not _empty(v)]
    if not vals:
        return [FieldError(event, "person_key", tried, "missing")]
    key = _key(vals[0])
    if key is None:
        return [FieldError(event, "person_key", tried, "invalid")]
    errs: list[FieldError] = []
    name = None
    if emap.name:
        v = get_path(payload, emap.name)
        if not _empty(v):
            if not isinstance(v, str) or len(v.strip()) > MAX_NAME:
                errs.append(FieldError(event, "name", (emap.name,), "invalid"))
            else:
                name = v.strip()
    fields = {}
    for k, path in emap.fields.items():
        v = get_path(payload, path)
        if v is MISSING:
            continue
        if v is not None and (not isinstance(v, (str, int, float, bool)) or (isinstance(v, str) and len(v) > MAX_STR)):
            errs.append(FieldError(event, f"fields.{k}", (path,), "invalid"))
        else:
            fields[k] = v
    if errs:
        return errs
    at = _when(get_path(payload, emap.occurred_at), now) if emap.occurred_at else now
    return NormalisedEvent(event, key, name, at, fields)


def apply_event(person: dict | None, ev: NormalisedEvent) -> dict:
    """Mirrors the SQL upsert: COALESCE name, earliest waiver/checkin, newest result wins (ties replace)."""
    p = {"person_key": ev.person_key, "name": None, "waiver_at": None, "checkin_at": None, "result": None, "result_at": None, **(person or {})}
    out = {**p, "name": p["name"] if p["name"] is not None else ev.name}
    if ev.event in ("waiver", "checkin"):
        col = f"{ev.event}_at"
        out[col] = ev.occurred_at if p[col] is None else min(p[col], ev.occurred_at)
    elif p["result_at"] is None or ev.occurred_at >= p["result_at"]:
        out["result"], out["result_at"] = dict(ev.fields), ev.occurred_at
    return out
