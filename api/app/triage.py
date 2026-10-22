"""Sort an incoming customer message, draft a reply, and flag it for a human. The business comes from clients/<name>.yaml."""
import json
import logging
import re

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import llm, mailer, policy
from .admin import require_admin
from .config import settings

log = logging.getLogger("leadpilot.triage")
PROMPT = "triage.v1"
SAFE_DRAFT = "Thanks for your message. A team member will confirm the details and reply shortly."

router = APIRouter(dependencies=[Depends(require_admin)])


class TriageIn(BaseModel):
    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    client: str | None = None  # profile name; defaults to CLIENT_PROFILE


class TriageOut(BaseModel):
    category: str
    confidence: float
    draft: str
    needs_human: bool
    reason: str | None = None


def load_profile(name: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]+", name):  # the name becomes a file path
        raise FileNotFoundError(name)
    return yaml.safe_load((settings.clients_dir / f"{name}.yaml").read_text())


def _system(profile: dict) -> str:
    _, template = llm.load_prompt(PROMPT)
    return (template.replace("<<business>>", profile["business"]).replace("<<about>>", profile["about"])
            .replace("<<categories>>", "\n".join(f"- {k}: {v}" for k, v in profile["categories"].items()))
            .replace("<<facts>>", "\n".join(f"- {f}" for f in profile.get("facts", [])) or "- (none)"))


def _ask(message: str, profile: dict) -> tuple[str, float, str]:
    """Model output as (category, confidence, draft); anything unusable becomes ('other', 0, '')."""
    out = llm.chat([{"role": "system", "content": _system(profile)}, {"role": "user", "content": message}])
    raw = out["content"]
    try:
        data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        return str(data["category"]), min(max(float(data["confidence"]), 0.0), 1.0), str(data.get("draft", "")).strip()
    except (ValueError, KeyError, TypeError):
        log.warning("triage: unusable model output (%d chars)", len(raw))
        return "other", 0.0, ""


def triage(message: str, profile: dict) -> TriageOut:
    """The model sorts and drafts; code decides when a person must look (legal/safety/anger, low confidence, sensitive category)."""
    category, confidence, draft = _ask(message, profile)
    facts = profile.get("facts", [])
    if draft and (policy.unsupported_claim(draft, facts) or not policy.answer_supported(draft, facts)):
        log.warning("triage: draft not supported by the profile facts; replaced")
        draft = SAFE_DRAFT
    if category not in profile["categories"]:
        category, confidence = "other", 0.0
    reason = None
    if code := policy.escalation_reason(message):
        reason = f"customer message looks {code}"
    elif category == "other" or category in profile.get("always_human", []):  # "other" means we could not sort it
        reason = f"{category} goes to a person"
    elif confidence < profile.get("confidence_threshold", 0.8):
        reason = f"low confidence ({confidence:.2f})"
    return TriageOut(category=category, confidence=confidence, draft=draft, needs_human=reason is not None, reason=reason)


def _alert(message: str, profile: dict, result: TriageOut) -> None:
    if not settings.owner_email:
        return
    body = (f"{profile['business']}: a message needs a person ({result.reason}).\nCategory: {result.category}\n\n"
            f"Message:\n{message}\n\nSuggested reply (check before sending):\n{result.draft or '-'}")
    try:
        mailer.send(settings.owner_email, f"Needs a person: {result.category}", body)
    except mailer.MailError:
        log.exception("triage alert email failed")


@router.post("/triage", response_model=TriageOut)
def triage_message(body: TriageIn):
    profile = load_profile(body.client or settings.client_profile)
    result = triage(body.message, profile)
    if result.needs_human:
        _alert(body.message, profile, result)
    return result
