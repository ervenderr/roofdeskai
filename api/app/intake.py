"""The 'RoofDesk's own assistant' mode of the demo: it answers questions about the service and collects a pilot request.
Code asks the questions in a fixed order and validates every answer; the model is only used to answer questions from the
RoofDesk facts (clients/roofdesk-ai.yaml). The page holds the answers so far, so nothing is stored until the request is complete."""
import json
import logging
import re

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field, field_validator

from . import llm, pilot, policy, triage
from .ratelimit import chat_rate_limit
from .schemas import EMAIL_RE

log = logging.getLogger("leadpilot.intake")
PROFILE = "roofdesk-ai"
STEPS = ("name", "business", "email", "phone", "need")
ASK = {
    "name": "What's your name?",
    "business": "What's your business called?",
    "email": "What's the best email to reach you?",
    "phone": "And a phone number? Say skip if you'd rather not.",
    "need": "Last one: what enquiries do you get, and what should RoofDesk AI handle for you? Say skip if you're not sure.",
}
NO_ANSWER = "I'm not sure about that one, but the team can answer it by email once I have your details."
_SKIP = re.compile(r"^\s*(skip|no|none|n/?a|nope|rather not)\W*$", re.I)
_PREFIX = re.compile(r"^(?:my name is|my name's|i am|i'm|it's|this is|my business is|my business is called|we are|we're|it's called)\s+", re.I)
_EMAIL_IN_TEXT = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+")

router = APIRouter()


class IntakeData(BaseModel):
    name: str | None = Field(None, max_length=100)
    business: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=30)  # "" means asked and skipped
    need: str | None = Field(None, max_length=500)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v):
        if v is not None and not EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v


class IntakeIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    data: IntakeData = IntakeData()


class IntakeOut(BaseModel):
    reply: str
    data: IntakeData
    closed: bool  # the pilot request was saved: the page stops taking messages


def _text(message: str, max_words: int) -> str | None:
    m = _PREFIX.sub("", message.strip()).strip(" .!")
    return m if m and len(m.split()) <= max_words and len(m) <= 100 else None


def _name(message: str) -> str | None:
    m = _text(message, 4)
    return m if m and not re.search(r"[\d@]", m) else None


def _email(message: str) -> str | None:
    found = _EMAIL_IN_TEXT.search(message)
    return found.group().lower() if found and len(found.group()) <= 120 else None


def _phone(message: str) -> str | None:
    if _SKIP.match(message):
        return ""
    m = message.strip()
    return m if re.fullmatch(r"[\d+()\-. ]{7,30}", m) and 7 <= len(re.sub(r"\D", "", m)) <= 15 else None


def _need(message: str) -> str | None:
    return "" if _SKIP.match(message) else message.strip()


PARSE = {"name": _name, "business": lambda m: _text(m, 8), "email": _email, "phone": _phone, "need": _need}


def _next(data: dict) -> str | None:
    return next((s for s in STEPS if data.get(s) is None), None)


_PHONE_IN_TEXT = re.compile(r"\+?\d[\d\-. ()]{5,}\d")


def _phone_in(message: str) -> str | None:
    found = _PHONE_IN_TEXT.search(message)
    return found.group().strip() if found and 7 <= len(re.sub(r"\D", "", found.group())) <= 15 and len(found.group()) <= 30 else None


def _words(text_: str) -> set[str]:
    return set(re.findall(r"[\w']+", text_.lower()))


def _extract(message: str) -> tuple[dict, bool]:
    """Name and business from a sentence, via the model. Only words the visitor actually wrote are kept.
    A model failure returns nothing: the caller then just asks again."""
    _, system = llm.load_prompt("intake.v1")
    try:
        raw = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": message}])["content"]
        data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    except (RuntimeError, ValueError):
        log.warning("intake: could not extract details from a sentence")
        return {}, False
    if not isinstance(data, dict):
        return {}, False
    found = {}
    for key in ("name", "business"):
        v = data.get(key)
        if isinstance(v, str) and 0 < len(v.strip()) <= 100 and _words(v) <= _words(message) and not re.search(r"[\d@]", v if key == "name" else ""):
            found[key] = v.strip()
    return found, data.get("question") is True


def _fill(message: str, step: str) -> tuple[dict, bool]:
    """What this message tells us, as (new fields, whether it asked a question). A short answer goes to the
    current step; a longer message is read by the model so 'my name is John and I sell computer parts' fills two."""
    asked = policy.looks_like_question(message)
    found = {}
    if email := _email(message):
        found["email"] = email
    if phone := _phone_in(message):
        found["phone"] = phone
    if len(message.split()) <= 4 and not asked:
        if (v := PARSE[step](message)) is not None:
            found.setdefault(step, v)
    elif not asked:
        extracted, model_asked = _extract(message)
        found.update(extracted)
        asked = model_asked and not extracted  # a small model flags statements as questions; trust it only when nothing was captured
        if step == "need" and not found:
            found["need"] = message.strip()
    return found, asked


def _answer(message: str) -> str:
    """Answer from the RoofDesk facts. The safe draft promises a reply nobody will send from a chat, so it is not used."""
    try:
        answer = triage.triage(message, triage.load_profile(PROFILE)).draft
    except RuntimeError:
        log.exception("intake: could not answer a question")
        return NO_ANSWER
    return NO_ANSWER if not answer or answer == triage.SAFE_DRAFT else answer


@router.post("/intake", response_model=IntakeOut, response_model_exclude_none=True, dependencies=[Depends(chat_rate_limit)])
def intake(body: IntakeIn, request: Request, background: BackgroundTasks):
    known = body.data.model_dump(exclude_none=True)
    step = _next(known)
    found, asked = _fill(body.message, step)
    data = {**{k: v for k, v in found.items() if k not in known}, **known}
    answer = _answer(body.message) if asked or (not found and len(body.message.split()) > 4) else ""
    following = _next(data)
    if following:
        lead_in = "" if found or answer else "Sorry, I didn't catch that. "
        greeting = f"Nice to meet you, {data['name']}. " if "name" in found and "name" not in known and not answer else ""
        return IntakeOut(reply=f"{answer} {lead_in}{greeting}{ASK[following]}".strip(), data=IntakeData(**data), closed=False)
    pilot.pilot_rate_limit(request)  # same hourly cap as the form: a finished chat is a pilot request
    req = pilot.PilotIn(name=data["name"], business=data["business"], email=data["email"], phone=data["phone"] or None,
                        message=f"[via chat] {data['need']}"[:500])
    pilot._save(req)
    background.add_task(pilot._notify, req)
    return IntakeOut(reply=f"Thanks {data['name']}! Your free pilot request is in. We'll email you at {data['email']} within one business day.",
                     data=IntakeData(**data), closed=True)
