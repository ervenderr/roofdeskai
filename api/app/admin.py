"""Read/admin endpoints for the dashboard and n8n. All require the X-Admin-Key header."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import outreach
from .auth import Scope, require_admin, require_scope  # require_admin re-exported: triage.py and outreach_routes.py import it from here
from .agent import handle_turn
from .config import settings
from .db import system, tx
from .pack import get_pack

MAX_FOLLOWUPS = 3


log = logging.getLogger("leadpilot.admin")
router = APIRouter()  # per-route auth: require_scope below, so tenant keys work on the read/write routes


def _write_tenant(scope: Scope, route: str) -> str:
    """Tenant for write paths. Admin callers without X-Tenant-Id get the default tenant until n8n moves to tenant keys (Phase 8)."""
    if scope.tenant_id:
        return scope.tenant_id
    log.warning("%s called with the admin key and no X-Tenant-Id; using default tenant", route)
    return settings.default_tenant_id


def _rows(sql: str, *, _tenant: str | None = None, **params) -> list[dict]:
    """_tenant=None reads untenanted/cross-tenant (system); pass a tenant id to read inside that tenant."""
    with (tx(_tenant) if _tenant else system()) as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings()]


@router.get("/leads")
def list_leads(limit: int = 100, scope: Scope = Depends(require_scope)):
    return _rows("SELECT * FROM leads ORDER BY id DESC LIMIT :n", n=min(limit, 500), _tenant=scope.tenant_id)


@router.get("/leads/{lead_id}")
def get_lead(lead_id: int, scope: Scope = Depends(require_scope)):
    t = scope.tenant_id
    rows = _rows("SELECT * FROM leads WHERE id=:i", i=lead_id, _tenant=t)
    if not rows:
        raise HTTPException(404, "lead not found")
    return {**rows[0], "appointments": _rows("SELECT * FROM appointments WHERE lead_id=:i", i=lead_id, _tenant=t)}


@router.get("/conversations")
def list_conversations(limit: int = 100, scope: Scope = Depends(require_scope)):
    return _rows(
        """SELECT c.id, c.lead_id, c.channel, c.state, c.outcome, c.started_at, c.ended_at,
                  COALESCE(sum(l.cost_estimate), 0) AS cost, count(l.id) AS llm_calls,
                  EXTRACT(EPOCH FROM (COALESCE(c.ended_at, max_msg.t) - c.started_at)) AS duration_s
           FROM conversations c
           LEFT JOIN llm_calls l ON l.conversation_id = c.id
           LEFT JOIN LATERAL (SELECT max(created_at) t FROM messages WHERE conversation_id = c.id) max_msg ON true
           WHERE c.channel <> 'eval'
           GROUP BY c.id, max_msg.t ORDER BY c.started_at DESC, c.id DESC LIMIT :n""", n=min(limit, 500), _tenant=scope.tenant_id)


@router.get("/conversations/{cid}")
def get_conversation(cid: int, scope: Scope = Depends(require_scope)):
    t = scope.tenant_id
    convo = _rows("""SELECT c.*, (SELECT count(*) FROM llm_calls WHERE conversation_id = c.id) AS llm_calls,
                            (SELECT COALESCE(sum(cost_estimate), 0) FROM llm_calls WHERE conversation_id = c.id) AS cost
                     FROM conversations c WHERE c.id=:i""", i=cid, _tenant=t)
    if not convo:
        raise HTTPException(404, "conversation not found")
    messages = _rows("SELECT role, content, created_at FROM messages WHERE conversation_id=:i ORDER BY id", i=cid, _tenant=t)
    tool_calls = _rows("SELECT tool_name, args_json, result_json, ok, latency_ms, created_at FROM tool_calls "
                       "WHERE conversation_id=:i ORDER BY id", i=cid, _tenant=t)
    return {"conversation": convo[0], "messages": messages, "tool_calls": tool_calls}


@router.get("/metrics")
def metrics(scope: Scope = Depends(require_scope)):
    t = scope.tenant_id
    base = "FROM conversations WHERE channel <> 'eval'"
    outcomes = {r["outcome"] or "open": r["n"] for r in _rows(f"SELECT outcome, count(*) n {base} GROUP BY outcome", _tenant=t)}
    total = sum(outcomes.values())
    funnel = _rows("""SELECT count(*) leads,
                             count(*) FILTER (WHERE status IN ('qualified','booked')) qualified,
                             count(*) FILTER (WHERE status = 'booked') booked
                      FROM leads WHERE id IN (SELECT lead_id FROM conversations WHERE channel <> 'eval')""", _tenant=t)[0]
    llm = _rows("""SELECT count(*) calls,
                          percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) p50_ms,
                          percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) p95_ms,
                          COALESCE(sum(cost_estimate), 0) cost, avg((schema_valid)::int) schema_valid_rate
                   FROM llm_calls WHERE conversation_id IN (SELECT id FROM conversations WHERE channel <> 'eval')""", _tenant=t)[0]
    daily = _rows("""SELECT date_trunc('day', started_at)::date AS day, count(*) conversations,
                            count(*) FILTER (WHERE outcome = 'escalated') escalated
                     FROM conversations WHERE channel <> 'eval' GROUP BY 1 ORDER BY 1 DESC LIMIT 30""", _tenant=t)
    # eval_runs and outreach are global tables (no app_rw grant), so only the admin view carries them.
    # Runs recorded only as summaries (backfilled from saved reports) carry passed/total in metrics_json.
    runs = [] if t else _rows("""SELECT r.id, r.created_at, r.model, r.prompt_version, r.git_sha, r.metrics_json,
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
        **({} if t else {"outreach": outreach.metrics()}),
    }


@router.get("/admin/escalations")
def list_escalations(resolved: bool = False, scope: Scope = Depends(require_scope)):
    return _rows("SELECT * FROM escalations WHERE resolved=:r ORDER BY id DESC", r=resolved, _tenant=scope.tenant_id)


@router.post("/admin/escalations/{eid}/resolve")
def resolve_escalation(eid: int, scope: Scope = Depends(require_scope)):
    with tx(_write_tenant(scope, "resolve_escalation")) as c:
        if not c.execute(text("UPDATE escalations SET resolved=true WHERE id=:i RETURNING id"), {"i": eid}).first():
            raise HTTPException(404, "escalation not found")
    return {"id": eid, "resolved": True}


class InboundIn(BaseModel):
    """Normalised by n8n from an SMS / GoHighLevel-style payload."""
    contact_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    channel: str = Field("sms", max_length=20)
    message_id: str | None = Field(None, max_length=100)  # the provider's id for this message; a redelivery repeats it


def _redelivered(external_id: str, message_id: str, tenant: str) -> dict | None:
    """The saved reply if this provider message was already processed, else None.
    shortcut: sequential redeliveries only; two identical deliveries at the same instant could both pass. Add a unique index to close it."""
    rows = _rows("""SELECT c.id AS conversation_id,
                           (SELECT content FROM messages WHERE conversation_id = c.id AND role = 'assistant' ORDER BY id DESC LIMIT 1) AS reply
                    FROM conversations c JOIN events e ON e.conversation_id = c.id
                    WHERE c.external_id = :x AND e.kind = 'inbound_id' AND e.detail = :m LIMIT 1""", x=external_id, m=message_id, _tenant=tenant)
    return rows[0] if rows else None


@router.post("/webhooks/inbound")
def inbound(body: InboundIn, scope: Scope = Depends(require_scope)):
    tenant = _write_tenant(scope, "inbound")
    external_id = f"{body.channel}:{body.contact_id}"
    if body.message_id and (seen := _redelivered(external_id, body.message_id, tenant)):
        # No outcome fields on purpose: n8n routes on them, and a redelivery must not repeat the booking email or the alert.
        return {**seen, "duplicate": True, "link": f"{settings.public_url}/conversations/{seen['conversation_id']}"}
    try:
        cid, reply = handle_turn(body.message, external_id=external_id, channel=body.channel, tenant_id=tenant)
    except RuntimeError:
        raise HTTPException(502, "The assistant is unavailable right now.")
    if body.message_id:
        with tx(tenant) as c:
            c.execute(text("INSERT INTO events (tenant_id, conversation_id, kind, detail) VALUES (:t, :c, 'inbound_id', :m)"),
                      {"t": tenant, "c": cid, "m": body.message_id})
    # Outcome details let the n8n flow branch (confirm a booking, alert a human, leave nurture to the scheduler).
    info = _rows(
        """SELECT c.state, c.outcome, l.name, l.email,
                  (SELECT s.start_time FROM appointments a JOIN slots s ON s.id = a.slot_id
                   WHERE a.lead_id = c.lead_id LIMIT 1) AS appointment_start,
                  (SELECT reason FROM escalations WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) AS escalation_reason
           FROM conversations c JOIN leads l ON l.id = c.lead_id WHERE c.id = :i""", i=cid, _tenant=tenant)[0]
    return {"conversation_id": cid, "reply": reply, **info, "link": f"{settings.public_url}/conversations/{cid}"}


@router.get("/admin/followups/due")
def followups_due(hours: float = 48, scope: Scope = Depends(require_scope)):
    """NURTURE leads with an email, no activity for `hours`, and fewer than MAX_FOLLOWUPS sent."""
    return _rows(
        """SELECT c.id AS conversation_id, c.tenant_id, l.name, l.email, c.followup_count
           FROM conversations c JOIN leads l ON l.id = c.lead_id
           WHERE c.state = 'NURTURE' AND c.followup_count < :m AND l.email IS NOT NULL
             AND GREATEST((SELECT max(created_at) FROM messages WHERE conversation_id = c.id),
                          (SELECT max(created_at) FROM events WHERE conversation_id = c.id AND kind = 'followup'))
                 < now() - (:h * interval '1 hour')""", m=MAX_FOLLOWUPS, h=hours, _tenant=scope.tenant_id)


@router.post("/admin/followups/{cid}/draft")
def draft_followup(cid: int, scope: Scope = Depends(require_scope)):
    """Compose a follow-up email. Fixed template on purpose: no model-invented prices or promises."""
    tenant = _write_tenant(scope, "draft_followup")
    with tx(tenant) as c:
        row = c.execute(
            text("""UPDATE conversations SET followup_count = followup_count + 1
                    WHERE id = :i AND state = 'NURTURE' AND followup_count < :m RETURNING lead_id, followup_count"""),
            {"i": cid, "m": MAX_FOLLOWUPS}).first()
        if not row:
            raise HTTPException(409, "no follow-up due for this conversation")
        lead = c.execute(text("SELECT name, email FROM leads WHERE id=:i"), {"i": row.lead_id}).one()
        c.execute(text("INSERT INTO events (tenant_id, conversation_id, kind, detail) VALUES (:t, :c, 'followup', :d)"),
                  {"t": tenant, "c": cid, "d": f"follow-up {row.followup_count} of {MAX_FOLLOWUPS}"})
    greeting = f"Hi {lead.name}," if lead.name else "Hi,"
    pack = get_pack(tenant)
    kw = dict(greeting=greeting, business=pack.meta.business)
    return {
        "to": lead.email,
        "subject": pack.messages.followup_subject.format(**kw),
        "body": pack.messages.followup_body.format(**kw),
        "followup_number": row.followup_count,
    }
