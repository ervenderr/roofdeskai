"""The only actions the agent can take. Called by code, never directly by the model."""
import json
import logging
import re
import time
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import openai
from sqlalchemy import text

from . import llm
from .config import settings
from .db import record_event, tx
from .faq import vector_literal
from .pack import Calendar, get_pack
from .schemas import LeadFields

log = logging.getLogger("leadpilot.tools")


class ToolError(Exception):
    pass


def slot_instants(cal: Calendar, now: datetime) -> list[tuple[datetime, datetime]]:
    """Pure: UTC (start, end) pairs for tomorrow..days_ahead in the calendar's zone. A buffer drops starts too close to the previous slot's end."""
    tz = ZoneInfo(cal.timezone)
    today = now.astimezone(tz).date()
    out = []
    for i in range(1, cal.days_ahead + 1):
        day = today + timedelta(days=i)
        if cal.weekdays_only and day.isoweekday() >= 6:
            continue
        last_end = None
        for h in cal.slot_hours:
            start = datetime.combine(day, dtime(h), tzinfo=tz).astimezone(timezone.utc)
            if last_end and start < last_end + timedelta(minutes=cal.buffer_minutes):
                continue
            last_end = start + timedelta(minutes=cal.slot_minutes)
            out.append((start, last_end))
    return out


def _tid(tenant_id) -> str:
    return str(tenant_id)


def ensure_slots(tenant_id: str) -> None:
    """Top up the tenant's pack-defined slots; safe to repeat, so the calendar never runs dry."""
    t = _tid(tenant_id)
    rows = slot_instants(get_pack(t).calendar, datetime.now(timezone.utc))
    if not rows:
        return
    with tx(tenant_id) as c:
        c.execute(text(
            "INSERT INTO slots (tenant_id, start_time, end_time) "
            "SELECT :t, s, e FROM unnest(CAST(:starts AS timestamptz[]), CAST(:ends AS timestamptz[])) AS u(s, e) "
            "WHERE NOT EXISTS (SELECT 1 FROM slots x WHERE x.tenant_id = :t AND x.start_time = s) "
            "ON CONFLICT (tenant_id, start_time) DO NOTHING"),
            {"t": t, "starts": [r[0] for r in rows], "ends": [r[1] for r in rows]})


def get_available_slots(limit: int = 5, *, tenant_id: str) -> dict:
    ensure_slots(tenant_id)
    with tx(tenant_id) as c:
        rows = c.execute(
            text("SELECT id, start_time FROM slots WHERE tenant_id = :t AND NOT is_booked AND start_time > now() "
                 "ORDER BY start_time LIMIT :n"),
            {"n": limit, "t": _tid(tenant_id)},
        ).all()
    return {"slots": [{"id": r.id, "start": r.start_time.isoformat()} for r in rows]}


def book_appointment(lead_id: int, slot_id: int, tenant_id: str) -> dict:
    t = _tid(tenant_id)
    with tx(tenant_id) as c:
        status = c.execute(text("SELECT status FROM leads WHERE id=:i AND tenant_id=:t"), {"i": lead_id, "t": t}).scalar()
        if status != "qualified":
            raise ToolError("lead is not qualified")
        slot = c.execute(
            text("UPDATE slots SET is_booked=true WHERE id=:s AND tenant_id=:t AND NOT is_booked AND start_time > now() "
                 "RETURNING start_time"),
            {"s": slot_id, "t": t},
        ).first()
        if not slot:
            raise ToolError("slot unavailable")
        c.execute(text("INSERT INTO appointments (tenant_id, lead_id, slot_id) VALUES (:t, :l, :s)"),
                  {"t": t, "l": lead_id, "s": slot_id})
        c.execute(text("UPDATE leads SET status='booked' WHERE id=:i AND tenant_id=:t"), {"i": lead_id, "t": t})
    return {"start": slot.start_time.isoformat()}


def update_lead(lead_id: int, fields: dict, tenant_id: str) -> dict:
    """Validated against LeadFields: unknown fields or bad values raise."""
    clean = LeadFields.model_validate(fields).model_dump(exclude_none=True, mode="json")
    if clean:
        # Column names come from the schema's own keys (extra="forbid"), never from user text.
        sets = ", ".join(f"{k}=:{k}" for k in clean)
        with tx(tenant_id) as c:
            c.execute(text(f"UPDATE leads SET {sets} WHERE id=:_id AND tenant_id=:_t"),
                      {**clean, "_id": lead_id, "_t": _tid(tenant_id)})
    return {"updated": sorted(clean)}


def lookup_faq(query: str, k: int = 3, *, tenant_id: str) -> dict:
    try:
        vector = vector_literal(llm.embed(query))
    except openai.OpenAIError:  # no Ollama (hosted deploy): fall back to keyword search
        return {"chunks": _faq_keywords(query, k, tenant_id)}
    with tx(tenant_id) as c:
        rows = c.execute(text("SELECT text FROM faq_chunks WHERE tenant_id = :t ORDER BY embedding <=> CAST(:v AS vector) LIMIT :k"),
                         {"v": vector, "k": k, "t": _tid(tenant_id)}).all()
    return {"chunks": [r.text for r in rows]}


def _faq_keywords(query: str, k: int, tenant_id: str) -> list[str]:
    terms = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]  # alphanumerics only, so to_tsquery input is safe
    if not terms:
        return []
    with tx(tenant_id) as c:
        rows = c.execute(text("SELECT text FROM faq_chunks WHERE tenant_id = :t AND to_tsvector('english', text) @@ to_tsquery('english', :q) "
                              "ORDER BY ts_rank(to_tsvector('english', text), to_tsquery('english', :q)) DESC LIMIT :k"),
                         {"q": " | ".join(terms), "k": k, "t": _tid(tenant_id)}).all()
    return [r.text for r in rows]


def _safe_event(tenant_id, conversation_id, kind, payload) -> None:
    """An audit side-table must never block a booking or handoff: log and carry on."""
    try:
        with tx(tenant_id) as c:
            record_event(c, _tid(tenant_id), conversation_id, kind, payload)
    except Exception:
        log.exception("agent_events write failed (kind=%s)", kind)


def escalate_to_human(conversation_id: int, reason: str, tenant_id: str) -> dict:
    with tx(tenant_id) as c:
        c.execute(text("INSERT INTO escalations (tenant_id, conversation_id, reason) VALUES (:t, :c, :r)"),
                  {"t": _tid(tenant_id), "c": conversation_id, "r": reason})
        c.execute(text("UPDATE conversations SET state='ESCALATE', outcome=CASE WHEN outcome='booked' THEN outcome ELSE 'escalated' END, ended_at=now() WHERE id=:c AND tenant_id=:t"),
                  {"c": conversation_id, "t": _tid(tenant_id)})
    _safe_event(tenant_id, conversation_id, "escalation", {"reason": reason})
    _notify_escalation(conversation_id, reason, tenant_id)
    return {"reason": reason}


def _notify_escalation(conversation_id: int, reason: str, tenant_id: str) -> None:
    """Fire-and-forget alert to n8n for web-chat escalations. Carries no customer data, only a link. A failure never blocks the handoff."""
    if not settings.escalation_webhook_url:
        return
    with tx(tenant_id) as c:
        channel = c.execute(text("SELECT channel FROM conversations WHERE id=:i AND tenant_id=:t"),
                            {"i": conversation_id, "t": _tid(tenant_id)}).scalar()
    if channel != "web":  # n8n-fronted channels (sms/email) branch on the inbound response instead; avoid double alerts
        return
    try:
        httpx.post(settings.escalation_webhook_url, timeout=3, json={
            "conversation_id": conversation_id, "reason": reason,
            "link": f"{settings.public_url}/conversations/{conversation_id}"})
    except httpx.HTTPError as e:
        log.warning("escalation alert for conversation %s failed: %s", conversation_id, type(e).__name__)


def run(cid: int, name: str, args: dict, fn, *, tenant_id: str) -> tuple[bool, dict]:
    """Execute a tool, log it to tool_calls, and return (ok, result). Tool failures are results, not crashes.
    tenant_id is the caller's own parameter; a tenant_id inside model-supplied args is dropped."""
    start = time.perf_counter()
    kwargs = {k: v for k, v in args.items() if k != "tenant_id"}
    kwargs["tenant_id"] = tenant_id
    try:
        result, ok = fn(**kwargs), True
    except (ToolError, ValueError) as e:  # ValueError covers pydantic ValidationError
        result, ok = {"error": str(e)[:300]}, False
    except Exception as e:  # infra failure (e.g. embedding service down): degrade, but log it
        log.error("tool %s crashed: %s", name, type(e).__name__)
        result, ok = {"error": type(e).__name__}, False
    ms = int((time.perf_counter() - start) * 1000)
    with tx(tenant_id) as c:
        c.execute(
            text("INSERT INTO tool_calls (tenant_id, conversation_id, tool_name, args_json, result_json, ok, latency_ms) "
                 "VALUES (:t, :c, :n, CAST(:a AS jsonb), CAST(:r AS jsonb), :ok, :l)"),
            {"t": _tid(tenant_id), "c": cid, "n": name, "a": json.dumps(args, default=str), "r": json.dumps(result, default=str),
             "ok": ok, "l": ms},
        )
    _safe_event(tenant_id, cid, "tool_call", {"name": name, "ok": ok, "ms": ms})
    return ok, result
