"""One conversation turn. The LLM proposes (reply + extracted fields); this code decides."""
import hmac
import json
import logging
from datetime import datetime

from sqlalchemy import text

from . import llm, mailer, policy, speech, tools
from .config import settings
from .db import engine
from .schemas import Turn

log = logging.getLogger("leadpilot.agent")

PROMPT = "agent.v2"

CLOSED_REPLY = {
    "DONE": "Your inspection is booked. If you need to change it, a team member will help you.",
    "DISQUALIFY": "Thanks again for your interest. Unfortunately we can't help with this one.",
    "ESCALATE": "A team member has your details and will follow up with you shortly.",
}
DISQUALIFY_REPLY = (
    "Thanks for the details. Unfortunately we can only book inspections for property owners "
    "with a repair, replacement or inspection need in our service area within the next 6 months, "
    "so we can't help with this one. We appreciate you reaching out!"
)
NURTURE_REPLY = "No problem at all! We'll check back with you later. Reach out any time you're ready for a free inspection."
NO_SLOTS_REPLY = "You qualify for a free inspection, but we have no openings right now. We'll reach out as soon as new times open up."


def handle_turn(message: str, cid: int | None = None, external_id: str | None = None,
                channel: str = "web") -> tuple[int, str]:
    """Process one user message; returns (conversation_id, reply). Raises LookupError for an unknown conversation.
    `external_id` (e.g. an SMS contact) finds or creates the conversation instead of `cid`."""
    cid = _open(cid, external_id, channel)
    message = speech.normalize(message)
    _save(cid, "user", message)
    reply = _decide(cid, message)
    _save(cid, "assistant", reply)
    return cid, reply


def _decide(cid: int, message: str) -> str:
    convo = _row("SELECT * FROM conversations WHERE id=:i", cid)
    state, lead_id = convo["state"], convo["lead_id"]
    if state == "ESCALATE":
        return CLOSED_REPLY[state]
    # Safety and legal messages reach a human even after the conversation is closed.
    reason = policy.escalation_reason(message, only=("safety", "legal") if state in CLOSED_REPLY else None)
    if reason:
        return _escalate(cid, reason)
    if state in CLOSED_REPLY:
        return CLOSED_REPLY[state]

    ok, res = tools.run(cid, "lookup_faq", {"query": message}, tools.lookup_faq)
    faq = res["chunks"] if ok else []

    turn = _ask_llm(cid, state, _row("SELECT * FROM leads WHERE id=:i", lead_id), faq)
    if turn is None:
        return _escalate(cid, "validation_failure")
    if turn.escalate_reason:
        return _escalate(cid, turn.escalate_reason)

    asked = next((m["content"] for m in reversed(_history(cid)[:-1]) if m["role"] == "assistant"), "")
    fields, dropped = policy.ground(turn.extracted.model_dump(exclude_none=True, mode="json"), message, asked)
    if dropped:
        log.warning("conversation %s: dropped ungrounded fields %s", cid, dropped)
    if fields and not tools.run(cid, "update_lead", {"lead_id": lead_id, "fields": fields}, tools.update_lead)[0]:
        return _escalate(cid, "validation_failure")

    lead = _row("SELECT * FROM leads WHERE id=:i", lead_id)
    verdict = policy.qualification(lead)

    if verdict == "disqualified":
        _set_lead_status(lead_id, "disqualified")
        _set_state(cid, "DISQUALIFY", "disqualified")
        return DISQUALIFY_REPLY
    if turn.not_ready and policy.not_ready_grounded(message):
        _set_lead_status(lead_id, "nurture")
        _set_state(cid, "NURTURE", "nurture")
        return NURTURE_REPLY

    slot_id = policy.pick_slot(message, convo["offered_slot_ids"]) if state == "BOOK" else None
    is_question = turn.is_question or policy.looks_like_question(message)
    made_progress = bool(fields) or is_question or slot_id is not None or state == "GREETING"
    failed = 0 if made_progress else convo["failed_turns"] + 1
    _exec("UPDATE conversations SET failed_turns=:f WHERE id=:i", f=failed, i=cid)
    if failed >= policy.MAX_FAILED_TURNS:
        return _escalate(cid, "repeated_misunderstanding")

    if verdict == "qualified" and policy.has_contact(lead):
        _set_lead_status(lead_id, "qualified")
        if state != "BOOK":
            return _offer_slots(cid, lead_id, "Good news, you qualify for a free roof inspection! ")
        if slot_id is not None:
            ok, res = tools.run(cid, "book_appointment", {"lead_id": lead_id, "slot_id": slot_id},
                                tools.book_appointment)
            if ok:
                _set_state(cid, "DONE", "booked")
                _notify_booking(lead_id, _fmt(res["start"]))
                return f"You're booked for {_fmt(res['start'])}. We'll see you then!"
            return _offer_slots(cid, lead_id, "Sorry, that time isn't available. ")
        return _answer(cid, turn, is_question, faq, message, "Which of those openings works for you? Just say first, second, and so on.")

    if state == "GREETING":
        _set_state(cid, "COLLECT")
    return _answer(cid, turn, is_question, faq, message, policy.next_question(lead))


def _answer(cid: int, turn: Turn, is_question: bool, faq: list[str], message: str, follow_up: str) -> str:
    """FAQ answer (if the customer asked a question) followed by the code's next question. The model's answer
    must stick to the FAQ; if it is empty, a second focused call tries. Anything unsupported -> safe fallback."""
    answer = ""
    if is_question:
        answer = turn.reply.strip() or _faq_answer(cid, message, faq)
        if not answer or not faq or policy.unsupported_claim(answer, faq) or not policy.answer_supported(answer, faq):
            if answer:
                log.warning("conversation %s: FAQ answer not supported by the knowledge base; replaced", cid)
            answer = policy.SAFE_FALLBACK
    return f"{answer} {follow_up}".strip()


def _faq_answer(cid: int, question: str, faq: list[str]) -> str:
    """Second-chance plain-text answer built only from the retrieved FAQ. Returns '' if it cannot answer."""
    if not faq:
        return ""
    version, template = llm.load_prompt("faq-answer.v1")
    system = template.replace("<<faq>>", "\n".join(f"- {t}" for t in faq))
    out = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": question}])
    _log_llm(cid, out, version, None)
    text_ = out["content"].strip()
    return "" if "NO_ANSWER" in text_ else text_


def _offer_slots(cid: int, lead_id: int, prefix: str) -> str:
    slots = tools.run(cid, "get_available_slots", {}, tools.get_available_slots)[1].get("slots", [])
    if not slots:
        _set_lead_status(lead_id, "nurture")
        _set_state(cid, "NURTURE", "nurture")
        return NO_SLOTS_REPLY
    _exec("UPDATE conversations SET offered_slot_ids=:ids WHERE id=:i", ids=[s["id"] for s in slots], i=cid)
    _set_state(cid, "BOOK")
    options = "; ".join(f"{i}) {_fmt(s['start'])}" for i, s in enumerate(slots, 1))
    return f"{prefix}Here are the next openings: {options}. Which one works for you?"


def _ask_llm(cid: int, state: str, lead: dict, faq: list[str]) -> Turn | None:
    """Parse the model output against the Turn schema; one repair retry, then give up (caller escalates)."""
    version, template = llm.load_prompt(PROMPT)
    known = {k: v for k, v in lead.items() if k in _KNOWN_KEYS and v is not None}
    history = _history(cid)
    asked = next((m["content"] for m in reversed(history[:-1]) if m["role"] == "assistant"), "(nothing yet)")
    system = (template.replace("<<asked>>", asked)
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
        _log_llm(cid, out, version, error is None)
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


def _escalate(cid: int, reason: str) -> str:
    ok, _ = tools.run(cid, "escalate_to_human", {"conversation_id": cid, "reason": reason}, tools.escalate_to_human)
    if not ok:  # never promise a handoff that was not recorded
        raise RuntimeError("escalation could not be recorded")
    return CLOSED_REPLY["ESCALATE"]


def _notify_booking(lead_id: int, when: str) -> None:
    """Email the owner, and the lead if they gave an address. A failed email never blocks the booking."""
    lead = _row("SELECT name, phone, email, address, service_type FROM leads WHERE id=:i", lead_id)
    messages = []
    if settings.owner_email:
        messages.append((settings.owner_email, f"New booking: {lead['name']} ({when})",
                         f"{lead['name']} booked a free roof inspection for {when}.\nPhone: {lead['phone'] or '-'}\n"
                         f"Email: {lead['email'] or '-'}\nAddress: {lead['address']}\nNeed: {lead['service_type']}"))
    if lead["email"]:
        messages.append((lead["email"], f"Your inspection is booked: {when}",
                         f"Hi {lead['name']},\n\nYour free roof inspection is booked for {when}.\n\n"
                         "This was a demo of RoofDesk AI with a sample company (Summit Roofing). No one will visit, "
                         "and nothing was scheduled.\n\nTo try RoofDesk AI for your own business, reply to this email.\n\n"
                         f"{settings.sender_name}\n{settings.sender_address}"))
    for to, subject, body in messages:
        try:
            mailer.send(to, subject, body)
        except mailer.MailError:
            log.exception("booking saved but an email failed")


def _fmt(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%a %b %d, %I:%M %p")


# --- persistence helpers -------------------------------------------------------------------------

def _open(cid: int | None, external_id: str | None = None, channel: str = "web") -> int:
    with engine.begin() as c:
        if cid is None and external_id:
            cid = c.execute(text("SELECT id FROM conversations WHERE external_id=:e"), {"e": external_id}).scalar()
        if cid is None:
            lead_id = c.execute(text("INSERT INTO leads DEFAULT VALUES RETURNING id")).scalar_one()
            return c.execute(text("INSERT INTO conversations (lead_id, channel, external_id) VALUES (:l, :ch, :e) "
                                  "RETURNING id"), {"l": lead_id, "ch": channel, "e": external_id}).scalar_one()
        if not c.execute(text("SELECT 1 FROM conversations WHERE id=:i"), {"i": cid}).first():
            raise LookupError("conversation not found")
    return cid


def conversation_token(cid: int) -> str:
    return _row("SELECT token FROM conversations WHERE id=:i", cid)["token"]


def token_matches(cid: int, token: str | None) -> bool:
    """Constant-time check; a missing conversation and a wrong token look the same to the caller."""
    with engine.connect() as c:
        real = c.execute(text("SELECT token FROM conversations WHERE id=:i"), {"i": cid}).scalar()
    return bool(real and token and hmac.compare_digest(real, token))


def _row(sql: str, i: int) -> dict:
    with engine.connect() as c:
        return dict(c.execute(text(sql), {"i": i}).mappings().one())


def _exec(sql: str, **params) -> None:
    with engine.begin() as c:
        c.execute(text(sql), params)


def _save(cid: int, role: str, content: str) -> None:
    _exec("INSERT INTO messages (conversation_id, role, content) VALUES (:c, :r, :m)", c=cid, r=role, m=content)


def _history(cid: int) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text("SELECT role, content FROM messages WHERE conversation_id=:c ORDER BY id"),
                         {"c": cid}).mappings().all()
    return [dict(r) for r in rows]


def _set_state(cid: int, state: str, outcome: str | None = None) -> None:
    _exec("UPDATE conversations SET state=:s, outcome=COALESCE(:o, outcome), "
          "ended_at=CASE WHEN :o IS NULL THEN ended_at ELSE now() END WHERE id=:i AND state <> 'DONE'", s=state, o=outcome, i=cid)


def _set_lead_status(lead_id: int, status: str) -> None:
    _exec("UPDATE leads SET status=:s WHERE id=:i AND status <> 'booked'", s=status, i=lead_id)


def _log_llm(cid: int, out: dict, prompt_version: str, schema_valid: bool) -> None:
    _exec("INSERT INTO llm_calls (conversation_id, model, prompt_version, prompt_tokens, completion_tokens, "
          "latency_ms, schema_valid) VALUES (:c, :m, :v, :p, :o, :l, :ok)",
          c=cid, m=out["model"], v=prompt_version, p=out["prompt_tokens"], o=out["completion_tokens"],
          l=out["latency_ms"], ok=schema_valid)
