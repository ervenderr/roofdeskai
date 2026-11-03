"""Deterministic check of model-written quote text against the code-computed quote (D-07)."""
import re
from decimal import Decimal

from .quote import Quote

_CUR = r"(?<![A-Za-z])(?:CHF|USD|EUR|GBP|CAD|AUD|Fr\.|Fr(?![A-Za-z])|francs?|dollars?|euros?)|[$€£]"
_CODE = {"chf": "CHF", "fr": "CHF", "fr.": "CHF", "franc": "CHF", "francs": "CHF", "$": "USD", "dollar": "USD",
         "dollars": "USD", "€": "EUR", "euro": "EUR", "euros": "EUR", "£": "GBP"}
_NUM = r"(?<![\d.,])(\d{1,3}(?:[ '’ ,.]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?![\d])(?![.,]\d)"
_NUM_RE = re.compile(_NUM)
_CUR_RE = re.compile(_CUR, re.I)
_BEFORE = re.compile(r"(?:" + _CUR + r")\s*$", re.I)
_AFTER = re.compile(r"\s*(?:" + _CUR + r"|per\s+(?:person|hour)\b|/\s*(?:person|hour)\b|each\b|pp\b)", re.I)
_PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def _value(tok: str) -> tuple[Decimal, bool]:
    """(value, has_two_decimals). Last separator + 1-2 digits is the decimal mark; other separators are grouping."""
    m = re.search(r"[.,](\d{1,2})$", tok)
    whole, frac = (tok[:m.start()], m.group(1)) if m else (tok, "")
    return Decimal(re.sub(r"\D", "", whole) + ("." + frac if frac else "")), bool(m and len(frac) == 2)


def check_quote_text(text: str, quote: Quote, pack_percents) -> list[str]:
    """Failure codes (empty = ok). Integers without currency context (party size, dates, times) are not amounts."""
    allowed = {quote.total}
    for ln in quote.lines:
        allowed |= {ln.amount, abs(ln.amount)} | ({ln.unit_price} if ln.unit_price is not None else set())
    seen: set[Decimal] = set()
    bad = False
    for m in _NUM_RE.finditer(text):
        val, two_dp = _value(m.group(1))
        seen.add(val)
        if text[m.end():m.end() + 1] == "%":
            continue
        if (two_dp or _BEFORE.search(text[:m.start()]) or _AFTER.match(text, m.end())) and val not in allowed:
            bad = True
    codes = []
    if bad:
        codes.append("amount_not_in_quote")
    if quote.total not in seen:
        codes.append("total_missing")
    if any(_CODE.get(t.lower(), t.upper()) != quote.currency for t in _CUR_RE.findall(text)):
        codes.append("foreign_currency")
    pcts = {Decimal(p.replace(",", ".")) for p in _PCT.findall(text)}
    if any(p not in set(pack_percents) for p in pcts):
        codes.append("percent_not_in_rules")
    return codes
