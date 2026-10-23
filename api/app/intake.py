"""The 'RoofDesk's own assistant' mode of the demo: it answers questions about the service and collects a pilot request.
Code asks the questions in a fixed order and validates every answer; the model is only used to answer questions from the
RoofDesk facts (clients/roofdesk-ai.yaml). The page holds the answers so far, so nothing is stored until the request is complete."""
import logging
import re

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field, field_validator

from . import pilot, policy, triage
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


def _side_reply(message: str, step: str) -> str:
    """The visitor asked something (or wrote a sentence) instead of answering: answer from the facts, then ask again."""
    if not (policy.looks_like_question(message) or len(message.split()) > 4):
        return f"Sorry, I didn't catch that. {ASK[step]}"
    try:
        answer = triage.triage(message, triage.load_profile(PROFILE)).draft
        if not answer or answer == triage.SAFE_DRAFT:  # the safe draft promises a reply nobody will send from a chat
            answer = NO_ANSWER
    except RuntimeError:
        log.exception("intake: could not answer a question")
        answer = NO_ANSWER
    return f"{answer} {ASK[step]}"


@router.post("/intake", response_model=IntakeOut, response_model_exclude_none=True, dependencies=[Depends(chat_rate_limit)])
def intake(body: IntakeIn, request: Request, background: BackgroundTasks):
    data = body.data.model_dump(exclude_none=True)
    step = _next(data)
    value = None if policy.looks_like_question(body.message) else PARSE[step](body.message)
    if value is None:
        return IntakeOut(reply=_side_reply(body.message, step), data=body.data, closed=False)
    data = {**data, step: value}
    following = _next(data)
    if following:
        return IntakeOut(reply=ASK[following], data=IntakeData(**data), closed=False)
    pilot.pilot_rate_limit(request)  # same hourly cap as the form: a finished chat is a pilot request
    req = pilot.PilotIn(name=data["name"], business=data["business"], email=data["email"], phone=data["phone"] or None,
                        message=f"[via chat] {data['need']}"[:500])
    pilot._save(req)
    background.add_task(pilot._notify, req)
    return IntakeOut(reply=f"Thanks {data['name']}! Your free pilot request is in. We'll email you at {data['email']} within one business day.",
                     data=IntakeData(**data), closed=True)
