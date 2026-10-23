"""Read/admin endpoints for the dashboard and n8n. All require the X-Admin-Key header."""
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import outreach
from .agent import handle_turn
from .config import settings
from .db import engine

MAX_FOLLOWUPS = 3


def require_admin(x_admin_key: str = Header("")):
    if not settings.admin_api_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(403, "forbidden")


router = APIRouter(dependencies=[Depends(require_admin)])


def _rows(sql: str, **params) -> list[dict]:
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings()]


@router.get("/leads")
def list_leads(limit: int = 100):
    return _rows("SELECT * FROM leads ORDER BY id DESC LIMIT :n", n=min(limit, 500))


@router.get("/leads/{lead_id}")
def get_lead(lead_id: int):
    rows = _rows("SELECT * FROM leads WHERE id=:i", i=lead_id)
    if not rows:
        raise HTTPException(404, "lead not found")
    return {**rows[0], "appointments": _rows("SELECT * FROM appointments WHERE lead_id=:i", i=lead_id)}


@router.get("/conversations")
def list_conversations(limit: int = 100):
    return _rows(
        """SELECT c.id, c.lead_id, c.channel, c.state, c.outcome, c.started_at, c.ended_at,
                  COALESCE(sum(l.cost_estimate), 0) AS cost, count(l.id) AS llm_calls,
                  EXTRACT(EPOCH FROM (COALESCE(c.ended_at, max_msg.t) - c.started_at)) AS duration_s
           FROM conversations c
           LEFT JOIN llm_calls l ON l.conversation_id = c.id
           LEFT JOIN LATERAL (SELECT max(created_at) t FROM messages WHERE conversation_id = c.id) max_msg ON true
           WHERE c.channel <> 'eval'
           GROUP BY c.id, max_msg.t ORDER BY c.started_at DESC, c.id DESC LIMIT :n""", n=min(limit, 500))


@router.get("/conversations/{cid}")
def get_conversation(cid: int):
    convo = _rows("""SELECT c.*, (SELECT count(*) FROM llm_calls WHERE conversation_id = c.id) AS llm_calls,
                            (SELECT COALESCE(sum(cost_estimate), 0) FROM llm_calls WHERE conversation_id = c.id) AS cost
                     FROM conversations c WHERE c.id=:i""", i=cid)
    if not convo:
        raise HTTPException(404, "conversation not found")
    messages = _rows("SELECT role, content, created_at FROM messages WHERE conversation_id=:i ORDER BY id", i=cid)
    tool_calls = _rows("SELECT tool_name, args_json, result_json, ok, latency_ms, created_at FROM tool_calls "
                       "WHERE conversation_id=:i ORDER BY id", i=cid)
    return {"conversation": convo[0], "messages": messages, "tool_calls": tool_calls}


@router.get("/metrics")
def metrics():
    base = "FROM conversations WHERE channel <> 'eval'"
    outcomes = {r["outcome"] or "open": r["n"] for r in _rows(f"SELECT outcome, count(*) n {base} GROUP BY outcome")}
    total = sum(outcomes.values())
    funnel = _rows("""SELECT count(*) leads,
                             count(*) FILTER (WHERE status IN ('qualified','booked')) qualified,
                             count(*) FILTER (WHERE status = 'booked') booked
                      FROM leads WHERE id IN (SELECT lead_id FROM conversations WHERE channel <> 'eval')""")[0]
    llm = _rows("""SELECT count(*) calls,
                          percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) p50_ms,
                          percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) p95_ms,
                          COALESCE(sum(cost_estimate), 0) cost, avg((schema_valid)::int) schema_valid_rate
                   FROM llm_calls WHERE conversation_id IN (SELECT id FROM conversations WHERE channel <> 'eval')""")[0]
    daily = _rows("""SELECT date_trunc('day', started_at)::date AS day, count(*) conversations,
                            count(*) FILTER (WHERE outcome = 'escalated') escalated
                     FROM conversations WHERE channel <> 'eval' GROUP BY 1 ORDER BY 1 DESC LIMIT 30""")
    # Runs recorded only as summaries (backfilled from saved reports) carry passed/total in metrics_json.
    runs = _rows("""SELECT r.id, r.created_at, r.model, r.prompt_version, r.git_sha, r.metrics_json,
                           COALESCE((r.metrics_json->>'total')::int, count(e.id)) AS total,
                           COALESCE((r.metrics_json->>'passed')::int, count(e.id) FILTER (WHERE e.passed)) AS passed
                    FROM eval_runs r LEFT JOIN eval_results e ON e.run_id = r.id
                    GROUP BY r.id ORDER BY r.created_at DESC LIMIT 10""")
    return {
        "conversations": total,
        "outcomes": outcomes,
        "escalation_rate": outcomes.get("escalated", 0) / total if total else 0,
        "resolved_without_human_rate": 1 - outcomes.get("escalated", 0) / total if total else 0,
        "funnel": funnel,
        "llm": llm,
        "cost_per_conversation": float(llm["cost"]) / total if total else 0,
        "daily": daily,
        "eval_runs": runs,
        "outreach": outreach.metrics(),
    }


@router.get("/admin/escalations")
def list_escalations(resolved: bool = False):
    return _rows("SELECT * FROM escalations WHERE resolved=:r ORDER BY id DESC", r=resolved)


@router.post("/admin/escalations/{eid}/resolve")
def resolve_escalation(eid: int):
    with engine.begin() as c:
        if not c.execute(text("UPDATE escalations SET resolved=true WHERE id=:i RETURNING id"), {"i": eid}).first():
            raise HTTPException(404, "escalation not found")
    return {"id": eid, "resolved": True}


class InboundIn(BaseModel):
    """Normalised by n8n from an SMS / GoHighLevel-style payload."""
    contact_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    channel: str = Field("sms", max_length=20)
    message_id: str | None = Field(None, max_length=100)  # the provider's id for this message; a redelivery repeats it


def _redelivered(external_id: str, message_id: str) -> dict | None:
    """The saved reply if this provider message was already processed, else None.
    shortcut: sequential redeliveries only; two identical deliveries at the same instant could both pass. Add a unique index to close it."""
    rows = _rows("""SELECT c.id AS conversation_id,
                           (SELECT content FROM messages WHERE conversation_id = c.id AND role = 'assistant' ORDER BY id DESC LIMIT 1) AS reply
                    FROM conversations c JOIN events e ON e.conversation_id = c.id
                    WHERE c.external_id = :x AND e.kind = 'inbound_id' AND e.detail = :m LIMIT 1""", x=external_id, m=message_id)
    return rows[0] if rows else None


@router.post("/webhooks/inbound")
def inbound(body: InboundIn):
    external_id = f"{body.channel}:{body.contact_id}"
    if body.message_id and (seen := _redelivered(external_id, body.message_id)):
        # No outcome fields on purpose: n8n routes on them, and a redelivery must not repeat the booking email or the alert.
        return {**seen, "duplicate": True, "link": f"{settings.public_url}/conversations/{seen['conversation_id']}"}
    try:
        cid, reply = handle_turn(body.message, external_id=external_id, channel=body.channel)
    except RuntimeError:
        raise HTTPException(502, "The assistant is unavailable right now.")
    if body.message_id:
        with engine.begin() as c:
            c.execute(text("INSERT INTO events (conversation_id, kind, detail) VALUES (:c, 'inbound_id', :m)"), {"c": cid, "m": body.message_id})
    # Outcome details let the n8n flow branch (confirm a booking, alert a human, leave nurture to the scheduler).
    info = _rows(
        """SELECT c.state, c.outcome, l.name, l.email,
                  (SELECT s.start_time FROM appointments a JOIN slots s ON s.id = a.slot_id
                   WHERE a.lead_id = c.lead_id LIMIT 1) AS appointment_start,
                  (SELECT reason FROM escalations WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) AS escalation_reason
           FROM conversations c JOIN leads l ON l.id = c.lead_id WHERE c.id = :i""", i=cid)[0]
    return {"conversation_id": cid, "reply": reply, **info, "link": f"{settings.public_url}/conversations/{cid}"}


@router.get("/admin/followups/due")
def followups_due(hours: float = 48):
    """NURTURE leads with an email, no activity for `hours`, and fewer than MAX_FOLLOWUPS sent."""
    return _rows(
        """SELECT c.id AS conversation_id, l.name, l.email, c.followup_count
           FROM conversations c JOIN leads l ON l.id = c.lead_id
           WHERE c.state = 'NURTURE' AND c.followup_count < :m AND l.email IS NOT NULL
             AND GREATEST((SELECT max(created_at) FROM messages WHERE conversation_id = c.id),
                          (SELECT max(created_at) FROM events WHERE conversation_id = c.id AND kind = 'followup'))
                 < now() - (:h * interval '1 hour')""", m=MAX_FOLLOWUPS, h=hours)


@router.post("/admin/followups/{cid}/draft")
def draft_followup(cid: int):
    """Compose a follow-up email. Fixed template on purpose: no model-invented prices or promises."""
    with engine.begin() as c:
        row = c.execute(
            text("""UPDATE conversations SET followup_count = followup_count + 1
                    WHERE id = :i AND state = 'NURTURE' AND followup_count < :m RETURNING lead_id, followup_count"""),
            {"i": cid, "m": MAX_FOLLOWUPS}).first()
        if not row:
            raise HTTPException(409, "no follow-up due for this conversation")
        lead = c.execute(text("SELECT name, email FROM leads WHERE id=:i"), {"i": row.lead_id}).one()
        c.execute(text("INSERT INTO events (conversation_id, kind, detail) VALUES (:c, 'followup', :d)"),
                  {"c": cid, "d": f"follow-up {row.followup_count} of {MAX_FOLLOWUPS}"})
    greeting = f"Hi {lead.name}," if lead.name else "Hi,"
    return {
        "to": lead.email,
        "subject": "Your free roof inspection with Summit Roofing",
        "body": f"{greeting}\n\nThanks for your interest in a free roof inspection. Whenever you're ready, "
                "just reply to this email or message us and we'll find a time that works.\n\nSummit Roofing",
        "followup_number": row.followup_count,
    }
