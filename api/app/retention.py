"""OPS-04: age out PII per tenant and erase one person. Every statement carries tenant_id = :t and runs under db.tx(tenant_id)."""
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from . import db

log = logging.getLogger("leadpilot.retention")

# table -> how it is purged (single source of truth; coverage and data-map tests read it)
PURGED = {
    "conversations": "COALESCE(ended_at, started_at) older than cutoff",
    "messages": "via conversation", "tool_calls": "via conversation", "escalations": "via conversation",
    "events": "via conversation", "llm_calls": "via conversation",
    "leads": "created_at older than cutoff, no remaining conversation, no future appointment",
    "appointments": "via purged lead (past only: leads with a future appointment are kept)",
    "drafts": "created_at", "intake_people": "created_at", "capacity_flags": "first_flagged_at", "brief_runs": "created_at",
}
KEPT = {
    "slots": "config; freed (is_booked=false) when its appointment is purged",
    "faq_chunks": "config",
    "agent_events": "append-only audit, no PII by contract; trigger blocks delete",
    "tenant_api_keys": "credential hashes, not subject data",
}
CONVO_CHILDREN = ("tool_calls", "events", "escalations", "llm_calls", "messages")
MAX_ID = 254


def list_tenant_ids() -> list[str]:
    with db.system() as c:
        return [str(r[0]) for r in c.execute(text("SELECT id FROM tenants ORDER BY slug"))]


def _ids(conn, sql: str, **p) -> list[int]:
    return [r[0] for r in conn.execute(text(sql), p)]


def _erase(c, t: str, cids: list[int], lids: list[int], counts: dict) -> None:
    """Delete conversations and leads with their dependents, in FK order. Slots of removed appointments are freed first."""
    for tb in CONVO_CHILDREN:
        counts[tb] += c.execute(text(f"DELETE FROM {tb} WHERE tenant_id = :t AND conversation_id = ANY(:c)"), {"t": t, "c": cids}).rowcount
    c.execute(text("UPDATE slots SET is_booked = false WHERE tenant_id = :t AND id IN "
                   "(SELECT slot_id FROM appointments WHERE tenant_id = :t AND lead_id = ANY(:l))"), {"t": t, "l": lids})
    counts["appointments"] += c.execute(text("DELETE FROM appointments WHERE tenant_id = :t AND lead_id = ANY(:l)"), {"t": t, "l": lids}).rowcount
    counts["conversations"] += c.execute(text("DELETE FROM conversations WHERE tenant_id = :t AND id = ANY(:c)"), {"t": t, "c": cids}).rowcount
    counts["leads"] += c.execute(text("DELETE FROM leads WHERE tenant_id = :t AND id = ANY(:l)"), {"t": t, "l": lids}).rowcount


def purge_tenant(tenant_id: str, days: int, now: datetime | None = None) -> dict[str, int]:
    counts = dict.fromkeys(PURGED, 0)
    if days <= 0:
        return counts
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    with db.tx(tenant_id) as c:
        t = str(tenant_id)
        cids = _ids(c, "SELECT id FROM conversations WHERE tenant_id = :t AND COALESCE(ended_at, started_at) < :x", t=t, x=cutoff)
        lids = _ids(c, "SELECT l.id FROM leads l WHERE l.tenant_id = :t AND l.created_at < :x "
                       "AND NOT EXISTS (SELECT 1 FROM conversations v WHERE v.tenant_id = :t AND v.lead_id = l.id AND v.id <> ALL(:c)) "
                       "AND NOT EXISTS (SELECT 1 FROM appointments a JOIN slots s ON s.tenant_id = a.tenant_id AND s.id = a.slot_id "
                       "WHERE a.tenant_id = :t AND a.lead_id = l.id AND s.start_time >= :n)", t=t, x=cutoff, c=cids, n=now)
        _erase(c, t, cids, lids, counts)
        for tb, col in (("drafts", "created_at"), ("intake_people", "created_at"),
                        ("capacity_flags", "first_flagged_at"), ("brief_runs", "created_at")):
            counts[tb] += c.execute(text(f"DELETE FROM {tb} WHERE tenant_id = :t AND {col} < :x"), {"t": t, "x": cutoff}).rowcount
    log.info("retention purge tenant=%s days=%s counts=%s", tenant_id, days, counts)
    return counts


def purge_all(days: int) -> dict[str, dict[str, int]]:
    if days <= 0:
        return {}
    return {tid: purge_tenant(tid, days) for tid in list_tenant_ids()}


def delete_subject(tenant_id: str, identifier: str) -> dict[str, int]:
    """Best effort: finds rows linked by lead email/phone, conversation external_id, draft contact email, intake person_key.
    Unlinked drafts, lead-less conversations without the external id and free text are not scanned."""
    v = (identifier or "").strip()
    if not v or len(v) > MAX_ID:
        raise ValueError("identifier must be 1-254 characters")
    digits = re.sub(r"\D", "", v)
    if len(digits) < 7:
        digits = ""  # too short to be a phone: never match on it
    counts = dict.fromkeys(PURGED, 0)
    with db.tx(tenant_id) as c:
        t = str(tenant_id)
        lids = _ids(c, "SELECT id FROM leads WHERE tenant_id = :t AND (lower(email) = lower(:v) "
                       "OR (:d <> '' AND regexp_replace(phone, '\\D', '', 'g') = :d))", t=t, v=v, d=digits)
        cids = _ids(c, "SELECT id FROM conversations WHERE tenant_id = :t AND (lead_id = ANY(:l) OR external_id = :v)", t=t, l=lids, v=v)
        _erase(c, t, cids, lids, counts)
        counts["drafts"] += c.execute(text("DELETE FROM drafts WHERE tenant_id = :t AND (lower(payload->>'contact_email') = lower(:v) "
                                           "OR lower(payload->>'customer_email') = lower(:v))"), {"t": t, "v": v}).rowcount
        counts["intake_people"] += c.execute(text("DELETE FROM intake_people WHERE tenant_id = :t AND lower(person_key) = lower(:v)"),
                                             {"t": t, "v": v}).rowcount
        db.record_event(c, t, None, "subject_deleted", {"id_hash": hashlib.sha256(v.lower().encode()).hexdigest()[:16], "counts": counts})
    log.info("subject deleted tenant=%s counts=%s", tenant_id, counts)
    return counts
