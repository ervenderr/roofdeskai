"""POST /reviews/draft: model drafts a reply, check_reply decides, regenerate once, else needs_human. Never posted anywhere."""
import hashlib
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import llm, ratelimit
from .auth import require_tenant
from .config import settings
from .drafts import create_or_get_draft, get_draft, require_module
from .engine.reviews import check_reply
from .pack import render, get_pack

log = logging.getLogger("leadpilot.reviews")
router = APIRouter(prefix="/reviews", tags=["reviews"])
MAX_ATTEMPTS = 2  # first try + one regeneration
PRIVACY = ("This is a health business: never confirm or imply that the reviewer was a patient or had a visit or treatment; "
           "say we cannot discuss individual cases publicly and invite them to contact us directly.")


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_text: str = Field(min_length=1, max_length=4000)
    rating: int = Field(ge=1, le=5)
    platform: Literal["google", "tripadvisor", "other"]


def _chat(tenant: str, messages: list[dict]) -> str:
    if not ratelimit.allow(tenant, settings.module_llm_rate_per_min):
        raise HTTPException(429, "Too many requests, please slow down.")
    try:
        return llm.chat(messages)["content"].strip()
    except RuntimeError:
        log.warning("review llm unavailable for tenant %s", tenant)
        raise HTTPException(502, "language model unavailable, try again later") from None


@router.post("/draft")
def draft_review(body: ReviewIn, tenant: str = Depends(require_tenant)):
    pack = get_pack(tenant)
    r = require_module(pack.meta.reviews, "reviews")
    _, tmpl = llm.load_prompt("review-reply.v1")
    system = render(tmpl, pack)
    for k, v in {"tone": r.tone, "max_words": str(r.max_words), "signature": r.signature,
                 "forbidden": ", ".join(r.forbidden_topics) or "nothing extra", "privacy": PRIVACY if r.health_privacy else ""}.items():
        system = system.replace(f"<<{k}>>", v)
    user = f"Platform: {body.platform}\nRating: {body.rating}/5\n<review>\n{body.review_text}\n</review>"
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    reply, codes = None, []
    for _ in range(MAX_ATTEMPTS):
        text_ = _chat(tenant, msgs)
        codes = check_reply(text_, pack, body.review_text)
        if not codes:
            reply = text_
            break
        msgs = msgs + [{"role": "user", "content": "Your draft was rejected (" + ", ".join(codes) + "). Write a new reply that avoids these."}]
    payload = {"review_text": body.review_text, "rating": body.rating, "platform": body.platform}
    if reply:
        status, payload["reply_text"] = "pending", reply
    else:  # failed text may hold hallucinated PII: store codes only
        status, payload["violations"], payload["attempts"] = "needs_human", codes, MAX_ATTEMPTS
    h = hashlib.sha256(json.dumps({"v": 1, "pack": pack.hash, **{k: payload[k] for k in ("platform", "rating", "review_text")}},
                                  sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    did, deduped = create_or_get_draft(tenant, "review_reply", status, payload, h)
    log.info("review draft %s status=%s deduped=%s", did, status, deduped)
    return {**get_draft(did, tenant), "deduped": deduped}
