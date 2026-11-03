"""POST /quotes: structured request (or extracted from an email) -> code-computed quote -> validated email text -> draft.
The model only extracts fields and writes text around code-formatted figures; every number is recomputed or checked by code."""
import hashlib
import json
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import llm, ratelimit
from .auth import require_tenant
from .config import settings
from .drafts import create_or_get_draft, get_draft, require_module
from .engine.quote import NeedsHuman, QuoteRequest, build_quote, fmt, quote_to_payload, rule_percents
from .engine.quote_text import check_quote_text
from .pack import Pack, get_pack, render

log = logging.getLogger("leadpilot.quotes")
router = APIRouter(prefix="/quotes", tags=["quotes"])
MAX_ATTEMPTS = 2  # first try + one regeneration


class QuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: str | None = Field(None, max_length=64)
    qty: int | None = Field(None, ge=1, le=10_000)
    add_on_ids: list[str] = Field(default_factory=list, max_length=20)
    customer_type: Literal["consumer", "corporate"] | None = None


class QuoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: QuoteIn | None = None
    email_text: str | None = Field(None, min_length=1, max_length=4000)  # ignored when request is given

    @model_validator(mode="after")
    def _one(self):
        if self.request is None and self.email_text is None:
            raise ValueError("send request or email_text")
        return self


def _chat(tenant: str, messages: list[dict]) -> str:
    if not ratelimit.allow(tenant, settings.module_llm_rate_per_min):
        raise HTTPException(429, "Too many requests, please slow down.")
    try:
        return llm.chat(messages)["content"].strip()
    except RuntimeError:
        log.warning("quote llm unavailable for tenant %s", tenant)
        raise HTTPException(502, "language model unavailable, try again later") from None


def _extract(tenant: str, pack: Pack, email: str) -> QuoteIn:
    _, body = llm.load_prompt("quote-extract.v1")
    catalog = "\n".join(f"- {s.id} ({s.name}); add-ons: {', '.join(a.id for a in s.add_ons) or 'none'}"
                        for s in pack.services.services)
    system = render(body, pack).replace("<<catalog>>", catalog)
    raw = _chat(tenant, [{"role": "system", "content": system}, {"role": "user", "content": f"<email>\n{email}\n</email>"}])
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    digits = set(re.findall(r"\d+", email))
    out: dict = {}
    for k in ("service_id", "qty", "add_on_ids", "customer_type"):
        try:
            v = QuoteIn.model_validate({k: data[k]}).model_dump()[k] if k in data else None
        except ValidationError:
            v = None
        if k == "qty" and v is not None and str(v) not in digits:  # grounding: the digits must be in the email
            v = None
        if v is not None:
            out[k] = v
    return QuoteIn(**out)


def _figures(pack: Pack, quote) -> str:
    lines = [f"- {ln.label}: {quote.currency} {fmt(ln.amount)}" + (f" ({ln.qty} x {quote.currency} {fmt(ln.unit_price)})" if ln.unit_price is not None else "")
             for ln in quote.lines]
    return "\n".join(["Lines:", *lines, f"Total: {quote.currency} {fmt(quote.total)}"])


def _email(tenant: str, pack: Pack, quote, percents) -> tuple[str | None, list[str]]:
    _, body = llm.load_prompt("quote-email.v1")
    system = render(body, pack).replace("<<figures>>", _figures(pack, quote))
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": "Write the email."}]
    codes: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        text_ = _chat(tenant, msgs)
        codes = check_quote_text(text_, quote, percents)
        if not codes:
            return text_, []
        msgs = msgs + [{"role": "user", "content": "Your draft was rejected (" + ", ".join(codes) + "). Rewrite it using only the listed figures."}]
    return None, codes


@router.post("")
def create_quote(body: QuoteBody, tenant: str = Depends(require_tenant)):
    pack = get_pack(tenant)
    require_module(pack.services, "services")
    payload: dict = {}
    if body.request is not None:
        req_in, basis = body.request, {"request": body.request.model_dump()}
    else:
        req_in, basis = _extract(tenant, pack, body.email_text), {"email_text": body.email_text}
        payload["customer_email"] = body.email_text  # kept so a human can resolve needs_human; tenant-scoped, never logged
    req = QuoteRequest(req_in.service_id, req_in.qty, tuple(req_in.add_on_ids), req_in.customer_type)
    payload["request"] = req_in.model_dump()
    result = build_quote(pack, req)
    if isinstance(result, NeedsHuman):
        status, payload["needs_human"] = "needs_human", {"reason": result.reason, "missing": list(result.missing)}
    else:
        payload["quote"] = quote_to_payload(result)
        svc = next(s for s in pack.services.services if s.id == req.service_id)
        text_, codes = _email(tenant, pack, result, rule_percents(svc))
        payload["email_text"] = text_
        status = "pending" if text_ else "needs_human"
        if codes:
            payload["check_failures"] = codes
    h = hashlib.sha256(json.dumps({"v": 1, "pack": pack.hash, **basis}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    did, deduped = create_or_get_draft(tenant, "quote", status, payload, h)
    log.info("quote draft %s status=%s deduped=%s", did, status, deduped)
    return {**get_draft(did, tenant), "deduped": deduped}
