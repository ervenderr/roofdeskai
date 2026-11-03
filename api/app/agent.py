"""One conversation turn. The LLM proposes (reply + extracted fields); this code decides."""
import hmac
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from . import llm, mailer, policy, speech, tools
from .config import settings
from .db import record_event, tx
from .logctx import current_tenant
from .pack import Pack, get_pack, render
from .schemas import Turn

log = logging.getLogger("leadpilot.agent")

PROMPT = "agent.v2"

CLOSED_STATES = ("DONE", "DISQUALIFY", "ESCALATE")
# Core text: only the business name comes from the pack (D-10).
DEMO_NOTICE = ("This was a demo of RoofDesk AI with a sample company ({business}). No one will visit, "
               "and nothing was scheduled.\n\nTo try RoofDesk AI for your own business, reply to this email.\n\n")


def handle_turn(message: str, cid: int | None = None, external_id: str | None = None,
                channel: str = "web", tenant_id: str | None = None) -> tuple[int, str]:
    """Process one user message; returns (conversation_id, reply). Raises LookupError for an unknown conversation.
    `external_id` (e.g. an SMS contact) finds or creates the conversation instead of `cid`."""
    t = str(tenant_id or settings.default_tenant_id)
    token = current_tenant.set(t)  # set here, not in middleware: sync endpoints run in a threadpool
    try:
        cid = _open(cid, external_id, channel, t)
        pack = get_pack(t)
        _turn_start(t, cid, channel)
        message = speech.normalize(message)
        if _last_message(cid, t) != ("user", message):  # a retry after a failed turn (502) must not repeat the customer's message
            _save(cid, "user", message, t)
        reply = _decide(cid, message, t, pack)
        _save(cid, "assistant", reply, t)
        return cid, reply
    finally:
        current_tenant.reset(token)


def _turn_start(t: str, cid: int, channel: str) -> None:
    try:
        with tx(t) as c:
            record_event(c, t, cid, "turn_start", {"channel": channel})
    except Exception:
        log.exception("agent_events write failed (turn_start)")


def _decide(cid: int, message: str, t: str, pack: Pack) -> str:
    convo = _row("SELECT * FROM conversations WHERE id=:i", cid, t)
    state, lead_id = convo["state"], convo["lead_id"]
    if state == "ESCALATE":
        return pack.messages.closed[state]
    # Safety and legal messages reach a human even after the conversation is closed.
    reason = policy.escalation_reason(message, only=("safety", "legal") if state in CLOSED_STATES else None, pack=pack)
    if reason:
        return _escalate(cid, reason, t, pack)
    if state in CLOSED_STATES:
        return pack.messages.closed[state]

    ok, res = tools.run(cid, "lookup_faq", {"query": message}, tools.lookup_faq, tenant_id=t)
    faq = res["chunks"] if ok else []

    turn = _ask_llm(cid, state, _row("SELECT * FROM leads WHERE id=:i", lead_id, t), faq, t, pack)
    if turn is None:
        return _escalate(cid, "validation_failure", t, pack)
    if turn.escalate_reason:
        return _escalate(cid, turn.escalate_reason, t, pack)

    asked = next((m["content"] for m in reversed(_history(cid, t)[:-1]) if m["role"] == "assistant"), "")
    fields, dropped = policy.ground(pack, turn.extracted.model_dump(exclude_none=True, mode="json"), message, asked)
    if dropped:
        log.warning("conversation %s: dropped ungrounded fields %s", cid, dropped)
    if fields and not tools.run(cid, "update_lead", {"lead_id": lead_id, "fields": fields}, tools.update_lead, tenant_id=t)[0]:
        return _escalate(cid, "validation_failure", t, pack)

    lead = _row("SELECT * FROM leads WHERE id=:i", lead_id, t)
    verdict = policy.qualification(pack, lead)

    if verdict == "disqualified":
        _set_lead_status(lead_id, "disqualified", t)
        _set_state(cid, "DISQUALIFY", "disqualified", t=t)
        return pack.messages.disqualify
    if turn.not_ready and policy.not_ready_grounded(message):
        _set_lead_status(lead_id, "nurture", t)
        _set_state(cid, "NURTURE", "nurture", t=t)
        return pack.messages.nurture

    slot_id = policy.pick_slot(message, convo["offered_slot_ids"]) if state == "BOOK" else None
    is_question = turn.is_question or policy.looks_like_question(message)
    made_progress = bool(fields) or is_question or slot_id is not None or state == "GREETING"
    failed = 0 if made_progress else convo["failed_turns"] + 1
    _exec("UPDATE conversations SET failed_turns=:f WHERE id=:i", t, f=failed, i=cid)
    if failed >= policy.MAX_FAILED_TURNS:
        return _escalate(cid, "repeated_misunderstanding", t, pack)

    if verdict == "qualified" and policy.has_contact(lead):
        _set_lead_status(lead_id, "qualified", t)
        if state != "BOOK":
            return _offer_slots(cid, lead_id, pack.messages.qualified_prefix, t, pack)
        if slot_id is not None:
            ok, res = tools.run(cid, "book_appointment", {"lead_id": lead_id, "slot_id": slot_id},
                                tools.book_appointment, tenant_id=t)
            if ok:
                _set_state(cid, "DONE", "booked", t=t)
                _notify_booking(lead_id, _fmt(res["start"], pack), t, pack)
                return pack.messages.booked.format(when=_fmt(res["start"], pack))
            return _offer_slots(cid, lead_id, pack.messages.slot_unavailable_prefix, t, pack)
        return _answer(cid, turn, is_question, faq, message, pack.messages.pick_prompt, t, pack)

    if state == "GREETING":
        _set_state(cid, "COLLECT", t=t)
    return _answer(cid, turn, is_question, faq, message, policy.next_question(pack, lead), t, pack)


def _answer(cid: int, turn: Turn, is_question: bool, faq: list[str], message: str, follow_up: str, t: str, pack: Pack) -> str:
    """FAQ answer (if the customer asked a question) followed by the code's next question. The model's answer
    must stick to the FAQ; if it is empty, a second focused call tries. Anything unsupported -> safe fallback."""
    answer = ""
    if is_question:
        answer = turn.reply.strip() or _faq_answer(cid, message, faq, t, pack)
        if not answer or not faq or policy.unsupported_claim(answer, faq) or not policy.answer_supported(answer, faq, pack):
            if answer:
                log.warning("conversation %s: FAQ answer not supported by the knowledge base; replaced", cid)
            answer = pack.messages.safe_fallback
    return f"{answer} {follow_up}".strip()


def _faq_answer(cid: int, question: str, faq: list[str], t: str, pack: Pack) -> str:
    """Second-chance plain-text answer built only from the retrieved FAQ. Returns '' if it cannot answer."""
    if not faq:
        return ""
    version, template = llm.load_prompt("faq-answer.v1")
    system = render(template, pack).replace("<<faq>>", "\n".join(f"- {t}" for t in faq))
    out = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": question}])
    _log_llm(cid, out, version, None, t)
    text_ = out["content"].strip()
    return "" if "NO_ANSWER" in text_ else text_


def _offer_slots(cid: int, lead_id: int, prefix: str, t: str, pack: Pack) -> str:
    slots = tools.run(cid, "get_available_slots", {}, tools.get_available_slots, tenant_id=t)[1].get("slots", [])
    if not slots:
        _set_lead_status(lead_id, "nurture", t)
        _set_state(cid, "NURTURE", "nurture", t=t)
        return pack.messages.no_slots
    _exec("UPDATE conversations SET offered_slot_ids=:ids WHERE id=:i", t, ids=[s["id"] for s in slots], i=cid)
    _set_state(cid, "BOOK", t=t)
    options = "; ".join(f"{i}) {_fmt(s['start'], pack)}" for i, s in enumerate(slots, 1))
    return pack.messages.offer_slots.format(prefix=prefix, options=options)


def _ask_llm(cid: int, state: str, lead: dict, faq: list[str], t: str, pack: Pack) -> Turn | None:
    """Parse the model output against the Turn schema; one repair retry, then give up (caller escalates)."""
    version, template = llm.load_prompt(PROMPT)
    known = {k: v for k, v in lead.items() if k in _KNOWN_KEYS and v is not None}
    history = _history(cid, t)
    asked = next((m["content"] for m in reversed(history[:-1]) if m["role"] == "assistant"), "(nothing yet)")
    system = (render(template, pack).replace("<<asked>>", asked)
              .replace("<<known>>", json.dumps(known))
              .replace("<<faq>>", "\n".join(f"- {t}" for t in faq) or "- (no relevant entries)"))
    messages = [{"role": "system", "content": system}, *history]
    for _ in range(2):
        out = llm.chat(messages)
        try:
            turn = _parse(out["content"])
            error = None
        except ValueError as e:
            turn, error = None, str(e)[:300]
        _log_llm(cid, out, version, error is None, t)
        if error:
            log.warning("conversation %s: invalid model output (%d chars): %.120s", cid, len(out["content"]),
                        error.splitlines()[0])
        if turn:
            return turn
        messages += [{"role": "assistant", "content": out["content"]},
                     {"role": "user", "content": f"Invalid output ({error}). Reply with ONLY the JSON object."}]
    return None


_KNOWN_KEYS = {"name", "phone", "email", "address", "service_type", "property_type", "is_owner",
               "timeline_months", "budget_range"}


def _parse(raw: str) -> Turn:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object found")
    return Turn.model_validate(json.loads(raw[start:end + 1]))  # pydantic ValidationError is a ValueError


def _escalate(cid: int, reason: str, t: str, pack: Pack) -> str:
    ok, _ = tools.run(cid, "escalate_to_human", {"conversation_id": cid, "reason": reason}, tools.escalate_to_human, tenant_id=t)
    if not ok:  # never promise a handoff that was not recorded
        raise RuntimeError("escalation could not be recorded")
    return pack.messages.closed["ESCALATE"]


def _notify_booking(lead_id: int, when: str, t: str, pack: Pack) -> None:
    """Email the owner, and the lead if they gave an address. A failed email never blocks the booking."""
    lead = _row("SELECT name, phone, email, address, service_type FROM leads WHERE id=:i", lead_id, t)
    m = pack.messages
    messages = []
    if settings.owner_email:
        kw = dict(name=lead["name"], when=when, phone=lead["phone"] or "-", email=lead["email"] or "-",
                  address=lead["address"], need=lead["service_type"])
        messages.append((settings.owner_email, m.owner_alert_subject.format(**kw), m.owner_alert_body.format(**kw)))
    if lead["email"]:
        messages.append((lead["email"], m.customer_subject.format(when=when),
                         m.customer_intro.format(name=lead["name"], when=when)
                         + DEMO_NOTICE.format(business=pack.meta.business)
                         + f"{settings.sender_name}\n{settings.sender_address}"))
    for to, subject, body in messages:
        try:
            mailer.send(to, subject, body)
        except mailer.MailError:
            log.exception("booking saved but an email failed")


def _fmt(iso: str, pack: Pack) -> str:
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(pack.calendar.timezone)).strftime("%a %b %d, %I:%M %p")


# --- persistence helpers -------------------------------------------------------------------------

def _open(cid: int | None, external_id: str | None, channel: str, t: str) -> int:
    with tx(t) as c:
        if cid is None and external_id:
            cid = c.execute(text("SELECT id FROM conversations WHERE external_id=:e AND tenant_id=:t"),
                            {"e": external_id, "t": t}).scalar()
        if cid is None:
            lead_id = c.execute(text("INSERT INTO leads (tenant_id) VALUES (:t) RETURNING id"), {"t": t}).scalar_one()
            return c.execute(text("INSERT INTO conversations (tenant_id, lead_id, channel, external_id) "
                                  "VALUES (:t, :l, :ch, :e) RETURNING id"),
                             {"t": t, "l": lead_id, "ch": channel, "e": external_id}).scalar_one()
        if not c.execute(text("SELECT 1 FROM conversations WHERE id=:i AND tenant_id=:t"), {"i": cid, "t": t}).first():
            raise LookupError("conversation not found")
    return cid


def conversation_token(cid: int, tenant_id: str | None = None) -> str:
    return _row("SELECT token FROM conversations WHERE id=:i", cid, _t(tenant_id))["token"]


def token_matches(cid: int, token: str | None, tenant_id: str | None = None) -> bool:
    """Constant-time check; a missing conversation and a wrong token look the same to the caller."""
    t = _t(tenant_id)
    with tx(t) as c:
        real = c.execute(text("SELECT token FROM conversations WHERE id=:i AND tenant_id=:t"), {"i": cid, "t": t}).scalar()
    return bool(real and token and hmac.compare_digest(real, token))


def _t(tenant_id: str | None) -> str:
    return str(tenant_id or settings.default_tenant_id)


def _row(sql: str, i: int, t: str) -> dict:
    with tx(t) as c:
        return dict(c.execute(text(sql), {"i": i}).mappings().one())


def _exec(sql: str, tenant: str, **params) -> None:
    with tx(tenant) as c:
        c.execute(text(sql), params)


def _save(cid: int, role: str, content: str, t: str) -> None:
    _exec("INSERT INTO messages (tenant_id, conversation_id, role, content) VALUES (:t, :c, :r, :m)", t,
          t=t, c=cid, r=role, m=content)


def _last_message(cid: int, t: str) -> tuple[str, str] | None:
    with tx(t) as c:
        row = c.execute(text("SELECT role, content FROM messages WHERE conversation_id=:c ORDER BY id DESC LIMIT 1"), {"c": cid}).first()
    return (row.role, row.content) if row else None


def _history(cid: int, t: str) -> list[dict]:
    with tx(t) as c:
        rows = c.execute(text("SELECT role, content FROM messages WHERE conversation_id=:c ORDER BY id"),
                         {"c": cid}).mappings().all()
    return [dict(r) for r in rows]


def _set_state(cid: int, state: str, outcome: str | None = None, *, t: str) -> None:
    _exec("UPDATE conversations SET state=:s, outcome=COALESCE(:o, outcome), "
          "ended_at=CASE WHEN :o IS NULL THEN ended_at ELSE now() END WHERE id=:i AND state <> 'DONE'", t, s=state, o=outcome, i=cid)


def _set_lead_status(lead_id: int, status: str, t: str) -> None:
    _exec("UPDATE leads SET status=:s WHERE id=:i AND status <> 'booked'", t, s=status, i=lead_id)


def _log_llm(cid: int, out: dict, prompt_version: str, schema_valid: bool, t: str) -> None:
    _exec("INSERT INTO llm_calls (tenant_id, conversation_id, model, prompt_version, prompt_tokens, completion_tokens, "
          "latency_ms, schema_valid) VALUES (:t, :c, :m, :v, :p, :o, :l, :ok)", t,
          t=t, c=cid, m=out["model"], v=prompt_version, p=out["prompt_tokens"], o=out["completion_tokens"],
          l=out["latency_ms"], ok=schema_valid)
