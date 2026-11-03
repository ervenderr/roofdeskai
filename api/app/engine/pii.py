"""PII patterns shared by the review check (and Phase 9 log masking)."""
import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_SUFFIX = r"(?:Street|St|Strasse|Str\.|Ave|Avenue|Road|Rd|Weg|Platz|Lane|Blvd)(?!\w)"
ADDRESS_RE = re.compile(rf"\b\d{{1,5}}\s+[A-Z][A-Za-z]+\s+{_SUFFIX}|\b[A-Z][a-z]+(?:strasse|gasse|weg|platz)\s+\d{{1,5}}\b")
