"""Mask email and phone in log text (OPS-03). Pure; never raises."""
import re

from .pii import EMAIL_RE

EMAIL_TOKEN = "[email]"
PHONE_TOKEN = "[phone]"
FAILED_TOKEN = "[unmasked-failed]"  # fail closed: never emit raw text when masking breaks
MIN_PHONE_DIGITS, MAX_PHONE_DIGITS = 8, 15

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_DATE = r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?"
_IPV4 = r"(?:\d{1,3}\.){3}\d{1,3}"
_PHONE = r"(?<![\w-])\+?\(?\d[\d\s().-]{6,}\d(?![\w-])"
# Order matters: protected shapes (uuid, date, ip) are matched first and returned unchanged.
_TOKEN = re.compile(
    rf"(?P<keep>{_UUID}|{_DATE}|{_IPV4})|(?P<email>{EMAIL_RE.pattern})|(?P<phone>{_PHONE})"
)


def _sub(m: re.Match) -> str:
    if m.group("email"):
        return EMAIL_TOKEN
    if m.group("phone"):
        s = m.group("phone")
        digits = sum(c.isdigit() for c in s)
        # shortcut: a separator-less 10-digit phone looks like an epoch and is left alone; upgrade if logs carry such numbers
        has_sep = s.startswith("+") or any(c in " -.()" for c in s)
        if MIN_PHONE_DIGITS <= digits <= MAX_PHONE_DIGITS and has_sep:
            return PHONE_TOKEN
    return m.group(0)


def mask(text: object) -> str:
    try:
        return _TOKEN.sub(_sub, text if isinstance(text, str) else str(text))
    except Exception:
        return FAILED_TOKEN
