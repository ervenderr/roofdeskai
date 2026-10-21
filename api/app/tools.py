"""The only actions the agent can take. Called by code, never directly by the model."""
import json
import logging
import re
import time

import httpx
import openai
from sqlalchemy import text

from . import llm
from .config import settings
from .db import engine
from .faq import vector_literal
from .schemas import LeadFields

log = logging.getLogger("leadpilot.tools")


class ToolError(Exception):
    pass


def get_available_slots(limit: int = 5) -> dict:
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT id, start_time FROM slots WHERE NOT is_booked AND start_time > now() "
                 "ORDER BY start_time LIMIT :n"),
            {"n": limit},
        ).all()
    return {"slots": [{"id": r.id, "start": r.start_time.isoformat()} for r in rows]}


def book_appointment(lead_id: int, slot_id: int) -> dict:
    with engine.begin() as c:
        status = c.execute(text("SELECT status FROM leads WHERE id=:i"), {"i": lead_id}).scalar()
        if status != "qualified":
            raise ToolError("lead is not qualified")
        slot = c.execute(
            text("UPDATE slots SET is_booked=true WHERE id=:s AND NOT is_booked AND start_time > now() "
                 "RETURNING start_time"),
            {"s": slot_id},
        ).first()
        if not slot:
            raise ToolError("slot unavailable")
        c.execute(text("INSERT INTO appointments (lead_id, slot_id) VALUES (:l, :s)"), {"l": lead_id, "s": slot_id})
        c.execute(text("UPDATE leads SET status='booked' WHERE id=:i"), {"i": lead_id})
    return {"start": slot.start_time.isoformat()}


def update_lead(lead_id: int, fields: dict) -> dict:
    """Validated against LeadFields: unknown fields or bad values raise."""
    clean = LeadFields.model_validate(fields).model_dump(exclude_none=True, mode="json")
    if clean:
        # Column names come from the schema's own keys (extra="forbid"), never from user text.
        sets = ", ".join(f"{k}=:{k}" for k in clean)
        with engine.begin() as c:
            c.execute(text(f"UPDATE leads SET {sets} WHERE id=:_id"), {**clean, "_id": lead_id})
    return {"updated": sorted(clean)}


def lookup_faq(query: str, k: int = 3) -> dict:
    try:
        vector = vector_literal(llm.embed(query))
    except openai.OpenAIError:  # no Ollama (hosted deploy): fall back to keyword search
        return {"chunks": _faq_keywords(query, k)}
    with engine.connect() as c:
        rows = c.execute(text("SELECT text FROM faq_chunks ORDER BY embedding <=> CAST(:v AS vector) LIMIT :k"),
                         {"v": vector, "k": k}).all()
    return {"chunks": [r.text for r in rows]}


def _faq_keywords(query: str, k: int) -> list[str]:
    terms = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]  # alphanumerics only, so to_tsquery input is safe
    if not terms:
        return []
    with engine.connect() as c:
        rows = c.execute(text("SELECT text FROM faq_chunks WHERE to_tsvector('english', text) @@ to_tsquery('english', :q) "
                              "ORDER BY ts_rank(to_tsvector('english', text), to_tsquery('english', :q)) DESC LIMIT :k"),
                         {"q": " | ".join(terms), "k": k}).all()
    return [r.text for r in rows]


def escalate_to_human(conversation_id: int, reason: str) -> dict:
    with engine.begin() as c:
        c.execute(text("INSERT INTO escalations (conversation_id, reason) VALUES (:c, :r)"),
                  {"c": conversation_id, "r": reason})
        c.execute(text("UPDATE conversations SET state='ESCALATE', outcome=CASE WHEN outcome='booked' THEN outcome ELSE 'escalated' END, ended_at=now() WHERE id=:c"),
                  {"c": conversation_id})
    _notify_escalation(conversation_id, reason)
    return {"reason": reason}


def _notify_escalation(conversation_id: int, reason: str) -> None:
    """Fire-and-forget alert to n8n for web-chat escalations. Carries no customer data, only a link. A failure never blocks the handoff."""
    if not settings.escalation_webhook_url:
        return
    with engine.connect() as c:
        channel = c.execute(text("SELECT channel FROM conversations WHERE id=:i"), {"i": conversation_id}).scalar()
    if channel != "web":  # n8n-fronted channels (sms/email) branch on the inbound response instead; avoid double alerts
        return
    try:
        httpx.post(settings.escalation_webhook_url, timeout=3, json={
            "conversation_id": conversation_id, "reason": reason,
            "link": f"{settings.public_url}/conversations/{conversation_id}"})
    except httpx.HTTPError as e:
        log.warning("escalation alert for conversation %s failed: %s", conversation_id, type(e).__name__)


def run(cid: int, name: str, args: dict, fn) -> tuple[bool, dict]:
    """Execute a tool, log it to tool_calls, and return (ok, result). Tool failures are results, not crashes."""
    start = time.perf_counter()
    try:
        result, ok = fn(**args), True
    except (ToolError, ValueError) as e:  # ValueError covers pydantic ValidationError
        result, ok = {"error": str(e)[:300]}, False
    except Exception as e:  # infra failure (e.g. embedding service down): degrade, but log it
        log.error("tool %s crashed: %s", name, type(e).__name__)
        result, ok = {"error": type(e).__name__}, False
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO tool_calls (conversation_id, tool_name, args_json, result_json, ok, latency_ms) "
                 "VALUES (:c, :n, CAST(:a AS jsonb), CAST(:r AS jsonb), :ok, :l)"),
            {"c": cid, "n": name, "a": json.dumps(args, default=str), "r": json.dumps(result, default=str),
             "ok": ok, "l": int((time.perf_counter() - start) * 1000)},
        )
    return ok, result
