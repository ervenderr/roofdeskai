"""Review reply post-check. Pure: the model drafts, this decides. Returns stable violation codes (empty = pass)."""
import re

from .. import policy
from ..pack import Pack
from .pii import ADDRESS_RE, EMAIL_RE, PHONE_RE

# Words a natural reply may use without being in the FAQ (tune this list, not the 40% threshold).
REVIEW_GENERIC = set("""appreciate appreciated feedback wonderful experience sharing shared glad enjoyed enjoy hear
mentioning mentioned telling told reaching visit visiting again soon directly talk through discuss individual cases publicly
apologise apologize delay delayed start started great kind words welcome welcomed hope guests thoughtful taking
review reviews comments comment sorry understand situation concern concerns issue looking forward""".split())

_COMPENSATION = re.compile(
    r"refund|reimburs|compensat|discount|voucher|credit note|free (?:visit|session|game|entry|drink|meal|ticket)"
    r"|money back|on the house|make it up to you|gift card|complimentary|\bfree\b.{0,20}\bon us\b|\bon us\b", re.I)
_FAULT = re.compile(
    r"\b(?:our|my) (?:fault|mistake|error)\b|we (?:made a mistake|messed up|dropped the ball|were (?:wrong|at fault|negligent)|failed (?:to|you))"
    r"|(?:was|were) (?:our|my) (?:fault|responsibility)|we (?:accept|admit|take) (?:full )?(?:responsibility|blame)"
    r"|\bshould have\b|that (?:was|is) (?:unacceptable|inexcusable)", re.I)
# "always" alone is too common in friendly replies; only concrete commitments are blocked.
_COMMITMENT = re.compile(
    r"we have (?:now )?(?:fixed|changed|replaced|retrained|dismissed)|has been (?:fixed|resolved)"
    r"|going forward we will|we (?:guarantee|promise)|never happen again", re.I)
_HEALTH = re.compile(
    r"\byour (?:visit|appointment|treatment|procedure|filling|cleaning|check-?up|teeth|tooth|gums|x-?rays?|records?|chart|dentist|doctor)\b"
    r"|\bas (?:our|a) patient\b|\bwhen you (?:came|visited)\b|\bwe (?:treated|saw|examined) you\b|\byou (?:were|are) (?:a|our) patient\b", re.I)


def _allowed_contacts(pack: Pack) -> list[str]:
    """Business contact strings (owner email, emails/phones already in the FAQ) that may appear in a reply."""
    kb = " ".join(e.text for e in pack.faq)
    found = EMAIL_RE.findall(kb) + [m.strip() for m in PHONE_RE.findall(kb)]
    return [c for c in [pack.meta.owner_email, *found] if c]


def _unknown_vocab(reply: str, pack: Pack, review_text: str) -> bool:
    """policy.answer_supported with extra vocabulary (policy.py stays untouched so packs cannot change)."""
    r = pack.meta.reviews
    known = " ".join([*(e.text for e in pack.faq), review_text, r.tone, r.signature, pack.meta.offer, pack.meta.kind, pack.meta.business])
    vocab = policy._tokens(known) | policy._GENERIC | REVIEW_GENERIC | set(pack.qualification.extra_stopwords)
    words = re.findall(r"[a-z]{4,}", reply.lower())
    return bool(words) and sum(not policy._same_word(w, vocab) for w in words) / len(words) > 0.4


def check_reply(text: str, pack: Pack, review_text: str = "") -> list[str]:
    r = pack.meta.reviews
    if r is None:
        raise ValueError("pack has no reviews block")
    if not text.strip():
        return ["empty"]
    out: list[str] = []
    faq = [e.text for e in pack.faq]
    if _COMPENSATION.search(text) or policy.unsupported_claim(text, faq):
        out.append("compensation")
    if _FAULT.search(text):
        out.append("fault")
    if _COMMITMENT.search(text) or _unknown_vocab(text, pack, review_text):
        out.append("unknown_fact")
    scrubbed = text
    for c in _allowed_contacts(pack):
        scrubbed = scrubbed.replace(c, " ")
    if any(rx.search(scrubbed) for rx in (EMAIL_RE, PHONE_RE, ADDRESS_RE)):
        out.append("pii")
    if r.health_privacy and _HEALTH.search(text):
        out.append("health_privacy")
    if any(re.search(rf"\b{re.escape(t.lower())}\b", text.lower()) for t in r.forbidden_topics):
        out.append("forbidden_topic")
    if len(text.split()) > r.max_words:
        out.append("too_long")
    return out
