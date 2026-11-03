"""Data-driven qualification. Pure: no DB, no LLM. Rule order is file order."""
import re
from collections.abc import Callable

from .pack import InArea, InList, MaxNumber, YesNo
from .policy import _tokens  # one-way import; policy does not import qualify


def address_status(cities, address: str | None) -> str:
    """'in'/'out' of the service area, or 'incomplete' when no city can be identified."""
    area = set(cities)
    if not address or not re.search(r"\d", address):  # a street address needs a number
        return "incomplete"
    parts = [p.strip().lower() for p in address.split(",")]
    if any(set(re.findall(r"[a-z]+", p)) & area for p in parts[1:]) or (len(parts) == 1 and _tokens(address) & area):
        return "in"
    stripped = [re.sub(r"(\s+[a-z]{2})?(\s+\d{5}(-\d{4})?)?$", "", p) for p in parts[1:]]  # drop a trailing state and ZIP
    if any(re.fullmatch(r"[a-z .'-]{3,}", p) and not re.match(r"(apt|unit|suite|ste|floor)\b", p) for p in stripped):
        return "out"
    return "incomplete"


def _in_list(r, v):
    return None if v is None else v in r.values


def _yes_no(r, v):
    return v if v is True or v is False else None  # identity: 1, 0, "yes" stay unknown


def _max_number(r, v):
    return None if v is None else v <= r.max


def _in_area(r, v):
    return {"in": True, "out": False}.get(address_status(r.cities, v))


CHECKS: dict[type, Callable] = {InList: _in_list, YesNo: _yes_no, MaxNumber: _max_number, InArea: _in_area}


def _active(pack):
    return [r for r in pack.qualification.rules if r.required]


def qualify(pack, lead: dict) -> str:
    results = [CHECKS[type(r)](r, lead.get(r.field)) for r in _active(pack)]
    if any(c is False for c in results):
        return "disqualified"
    return "qualified" if all(c is True for c in results) else "incomplete"


def _missing(r, v) -> bool:
    return v is None or v == "" or (isinstance(r, InArea) and address_status(r.cities, v) == "incomplete")


def missing_fields(pack, lead: dict) -> list[str]:
    out = [r.id for r in _active(pack) if _missing(r, lead.get(r.field))]
    if lead.get("name") is None or lead.get("name") == "":
        out.append("name")
    if not (lead.get("phone") or lead.get("email")):
        out.append("phone or email")
    return out


def next_question(pack, lead: dict) -> str:
    m = missing_fields(pack, lead)
    return pack.messages.ask[m[0]] if m else pack.messages.anything_else
