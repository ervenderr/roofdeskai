"""Public 'get a free pilot' form on the demo page. Saved as an interested prospect and emailed to the owner."""
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from . import mailer, triage
from .config import settings
from .db import engine
from .ratelimit import allow
from .schemas import EMAIL_RE

log = logging.getLogger("leadpilot.pilot")
CAMPAIGN = "Inbound pilot requests"
PER_HOUR = 5

router = APIRouter()


class PilotIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    business: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120)
    phone: str | None = Field(None, max_length=30)
    message: str | None = Field(None, max_length=500)
    website: str | None = None  # honeypot: real visitors never see this field

    @field_validator("email")
    @classmethod
    def valid_email(cls, v):
        if not EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v.lower()


def pilot_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not allow(f"pilot:{ip}", PER_HOUR, window=3600):
        raise HTTPException(429, "Too many requests, please try again later.")


def _save(body: PilotIn) -> None:
    with engine.begin() as c:
        cid = c.execute(text("SELECT id FROM campaigns WHERE name=:n"), {"n": CAMPAIGN}).scalar()
        if cid is None:
            cid = c.execute(text("INSERT INTO campaigns (name, active) VALUES (:n, false) RETURNING id"), {"n": CAMPAIGN}).scalar_one()
        pid = c.execute(text("INSERT INTO prospects (campaign_id, external_id, name, email, phone, status) "
                             "VALUES (:c, :x, :n, :e, :p, 'interested') RETURNING id"),
                        {"c": cid, "x": f"pilot-{uuid.uuid4()}", "n": body.business, "e": body.email, "p": body.phone}).scalar_one()
        c.execute(text("INSERT INTO prospect_events (prospect_id, kind, detail) VALUES (:p, 'pilot_request', :d)"),
                  {"p": pid, "d": f"{body.name}: {body.message or ''}"[:500]})


def _triage_note(body: PilotIn) -> str:
    """Category and a draft reply for the owner's email; a failed model call just leaves the note out."""
    if not body.message:
        return ""
    try:
        r = triage.triage(body.message, triage.load_profile("roofdesk-ai"))
    except RuntimeError:
        log.exception("pilot request triage failed")
        return ""
    return f"\nSorted as: {r.category} (confidence {r.confidence:.2f})\nSuggested reply (check before sending):\n{r.draft or '-'}\n"


def _notify(body: PilotIn) -> None:
    if not settings.owner_email:
        return
    subject = f"Pilot request: {body.business}".replace("\n", " ")[:100]
    text_ = (f"{body.name} from {body.business} asked for a free pilot.\nEmail: {body.email}\nPhone: {body.phone or '-'}\n"
             f"Message: {body.message or '-'}\n{_triage_note(body)}\nReply from your own inbox.")
    try:
        mailer.send(settings.owner_email, subject, text_)
    except mailer.MailError:
        log.exception("pilot request saved but the owner email failed")


@router.post("/pilot-requests", dependencies=[Depends(pilot_rate_limit)])
def pilot_request(body: PilotIn, background: BackgroundTasks):
    if body.website:
        return {"ok": True}  # a bot filled the honeypot: say yes, store nothing
    _save(body)
    background.add_task(_notify, body)  # the model call can take seconds; the visitor should not wait for it
    return {"ok": True}
