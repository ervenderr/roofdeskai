"""Business rules enforced in code. The LLM never decides any of this."""
import re

SERVICE_AREA = ("denver", "aurora", "lakewood", "arvada", "centennial", "littleton")
QUALIFYING_SERVICES = {"repair", "replacement", "inspection"}
MAX_TIMELINE_MONTHS = 6
MAX_FAILED_TURNS = 2

SAFE_FALLBACK = (
    "I don't have that information, but a team member can confirm it for you. "
    "In the meantime, I can book you a free roof inspection."
)

_ESCALATION_PATTERNS = {
    "human_request": r"\b(real person|human being|live agent|(talk|speak|connect|transfer)\b.{0,25}\b(human|person|someone|representative|manager))\b",
    "legal": r"\b(lawyer|attorney|sue (you|us|your)|suing|lawsuit|legal action|take (you|us|this) to court)\b",
    "safety": r"\b(gas (leak|smell)|collaps\w*|electrocut\w*|exposed wires?|structural damage|injur\w*)\b",
    "angry": r"\b(furious|scam|ridiculous|unacceptable|useless|idiots?|incompetent|worst)\b|\b(fuck\w*|shit\w*)\b",
}
_CLAIM_RE = re.compile(
    r"\$\s?\d[\d,]*|\b\d[\d,]*\s*(?:dollars|usd|php|pesos|percent)\b|\b\d+\s?%|\b\d+[- ]?years?\s+(?:workmanship\s+)?(?:warranty|guarantee)",
    re.I,
)


def escalation_reason(message: str, only: tuple[str, ...] | None = None) -> str | None:
    for reason, pattern in _ESCALATION_PATTERNS.items():
        if (only is None or reason in only) and re.search(pattern, message, re.I):
            return reason
    return None


def address_status(address: str | None) -> str:
    """'in'/'out' of the service area, or 'incomplete' when no city can be identified."""
    if not address or not re.search(r"\d", address):  # a street address needs a number
        return "incomplete"
    parts = [p.strip().lower() for p in address.split(",")]
    if any(p in SERVICE_AREA for p in parts[1:]) or (len(parts) == 1 and _tokens(address) & set(SERVICE_AREA)):
        return "in"
    # a later comma part that is plain letters (not "Apt 4", "CO 80202", a bare state code) reads as a city
    if any(re.fullmatch(r"[a-z .'-]{3,}", p) and not re.match(r"(apt|unit|suite|ste|floor)\b", p) for p in parts[1:]):
        return "out"
    return "incomplete"


def qualification(lead: dict) -> str:
    """'disqualified' as soon as one known criterion fails; 'qualified' once all four pass; else 'incomplete'."""
    checks = [
        None if lead.get("service_type") is None else lead["service_type"] in QUALIFYING_SERVICES,
        lead.get("is_owner"),
        {"in": True, "out": False}.get(address_status(lead.get("address"))),
        None if lead.get("timeline_months") is None else lead["timeline_months"] <= MAX_TIMELINE_MONTHS,
    ]
    if any(c is False for c in checks):
        return "disqualified"
    return "qualified" if all(c is True for c in checks) else "incomplete"


def has_contact(lead: dict) -> bool:
    return bool(lead.get("name") and (lead.get("phone") or lead.get("email")))


def missing_fields(lead: dict) -> list[str]:
    wanted = ["service_type", "is_owner", "address", "timeline_months", "name"]
    missing = [f for f in wanted if lead.get(f) is None or lead.get(f) == ""
               or (f == "address" and address_status(lead[f]) == "incomplete")]
    if not (lead.get("phone") or lead.get("email")):
        missing.append("phone or email")
    return missing


def unsupported_claim(reply: str, faq_texts: list[str]) -> bool:
    """True if the reply states a price/warranty figure that is not in the retrieved FAQ text."""
    kb = " ".join(faq_texts)
    for m in _CLAIM_RE.finditer(reply):
        if not all(re.search(rf"(?<![\d,]){re.escape(n)}(?![\d,])", kb) for n in re.findall(r"\d[\d,]*", m.group(0))):
            return True
    return False


ASK = {
    "service_type": "What roofing help do you need: a repair, a replacement, or an inspection?",
    "is_owner": "Do you own the property?",
    "address": "What's the property address, including the city?",
    "timeline_months": "When would you like the work done?",
    "name": "May I have your name?",
    "phone or email": "What's the best phone number or email to reach you?",
}


def next_question(lead: dict) -> str:
    missing = missing_fields(lead)
    return ASK[missing[0]] if missing else "Is there anything else I can help you with?"


_ORDINALS = {"first": 0, "1st": 0, "1": 0, "one": 0, "second": 1, "2nd": 1, "2": 1, "two": 1,
             "third": 2, "3rd": 2, "3": 2, "three": 2, "fourth": 3, "4th": 3, "4": 3, "four": 3,
             "fifth": 4, "5th": 4, "5": 4, "five": 4}


def pick_slot(message: str, offered_ids: list[int]) -> int | None:
    """Resolve a short 'the second one' / '3' against the slots we actually offered. Longer messages, or ones
    with negation, are not treated as a choice."""
    tokens = re.findall(r"[a-z0-9']+", message.lower())
    if len(tokens) > 6 or {"not", "no", "except", "dont", "don't", "never", "question"} & set(tokens):
        return None
    for token in tokens:
        idx = _ORDINALS.get(token)
        if idx is not None and idx < len(offered_ids):
            return offered_ids[idx]
    return None


_OWN_YES = r"\b(own|owns|owned|owner|homeowner|my (house|home|place|roof|property)|yes|yeah|yep|yup|sure|correct)\b"
_OWN_NO = r"\b(rent|renting|renter|rented|tenant|lease|leasing|landlord|not (the )?owner|(don't|do not|dont) own)\b"
_TIMING = (r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|month|months|week|weeks|year|years|"
           r"asap|soon|now|today|tomorrow|next|this|immediately|urgent|urgently)\b")
_TIME_UNITS = r"\b(months?|weeks?|years?|asap|soon|today|tomorrow|next|immediately|urgent\w*)\b"
_SERVICE = {
    "repair": r"repair|fix|patch|leak|damage|missing shingle",
    "replacement": r"replac|new roof|re-?roof|tear.?off",
    "inspection": r"inspect|check|estimate|assess|look at",
}
_NON_ROOF = r"gutter|window|paint|solar|siding|chimney|plumb|clean|wash|fence|deck|hvac|lawn"


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def is_grounded(field: str, value, message: str, asked: str = "") -> bool:
    """Is this extracted value supported by what the customer actually wrote? Small models invent values,
    and a wrongly extracted 'renter' or 'out of area' would wrongly end the conversation."""
    msg = message.lower()
    if field == "is_owner":
        if value:
            return bool(re.search(_OWN_YES, msg)) and not re.search(_OWN_NO, msg)
        answered_no = "own" in asked.lower() and re.match(r"\W*(no|nope|nah)\b", msg)
        return bool(re.search(_OWN_NO, msg) or answered_no)
    if field == "timeline_months":
        answering_when = "when" in asked.lower() and re.search(_TIMING, msg)
        return bool(re.search(_TIME_UNITS, msg) or answering_when)
    if field == "service_type":
        return bool(re.search(_NON_ROOF if value == "other" else _SERVICE[value], msg))
    if field == "address":
        toks = [t for t in _tokens(value) if len(t) > 2 or t.isdigit()]
        return bool(toks) and sum(t in _tokens(msg) for t in toks) / len(toks) >= 0.8
    if field == "phone":
        return re.sub(r"\D", "", value) in re.sub(r"\D", "", message)
    if field == "email":
        return value.lower() in msg
    if field == "name":
        return all(t in _tokens(msg) for t in _tokens(value))
    return True


def ground(fields: dict, message: str, asked: str = "") -> tuple[dict, list[str]]:
    kept = {k: v for k, v in fields.items() if is_grounded(k, v, message, asked)}
    return kept, sorted(set(fields) - set(kept))


_QUESTION_RE = re.compile(r"\?|^\W*(what|how|when|where|why|who|which|do|does|did|is|are|can|could|will|would|should)\b", re.I)
_NOT_READY_RE = re.compile(
    r"\b(just (browsing|looking)|browsing|not ready|not yet|later|think(ing)? about it|"
    r"decid\w*|some other time|call me back|no rush|maybe next)\b", re.I)
# Words an answer may use without being in the FAQ (tone, filler, our own vocabulary).
_GENERIC = set("""that this with have from your what about would there their please thanks thank happy glad sure help
also just like need will team member members contact free roof roofing summit know information confirm unfortunately
sorry question questions time here they them when were been does into some more most only than then very well each
other which while these those after before book booking inspection inspections estimate service work works customer
anything else need ready today currently available details specific provide offer offers ours""".split())


def looks_like_question(message: str) -> bool:
    return bool(_QUESTION_RE.search(message))


def not_ready_grounded(message: str) -> bool:
    return bool(_NOT_READY_RE.search(message))


def _same_word(w: str, vocab: set[str]) -> bool:
    """Exact, or a plain inflection (serve/serves, replacement/replacements): prefix with <= 2 extra letters."""
    return w in vocab or any(abs(len(w) - len(v)) <= 2 and (v.startswith(w) or w.startswith(v)) for v in vocab if len(v) >= 4)


def answer_supported(answer: str, faq_texts: list[str]) -> bool:
    """An FAQ answer should reuse the FAQ's own words. Mostly-new content words mean the model made something up."""
    vocab = _tokens(" ".join(faq_texts)) | _GENERIC  # not the question: echoing it would confirm any premise
    words = re.findall(r"[a-z]{4,}", answer.lower())
    return not words or sum(not _same_word(w, vocab) for w in words) / len(words) <= 0.4
