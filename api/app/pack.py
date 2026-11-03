"""Business pack: a validated folder of YAML under businesses/<slug>/ holding everything business-specific."""
import hashlib
import re
import sys
import threading
from pathlib import Path
from typing import Annotated, Literal
from string import Formatter
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import text

from .config import settings
from .db import system

SLUG_RE = re.compile(r"[a-z0-9-]+")
CORE_ASK = {"name", "phone or email"}
CLOSED_KEYS = {"DONE", "DISQUALIFY", "ESCALATE"}
# Required fields per template; {business} is allowed in every template.
TEMPLATE_FIELDS = {
    "offer_slots": {"prefix", "options"}, "booked": {"when"},
    "owner_alert_subject": {"name", "when"}, "owner_alert_body": {"name", "when", "phone", "email", "address", "need"},
    "customer_subject": {"when"}, "customer_intro": {"name", "when"}, "followup_body": {"greeting"},
}


class PackError(Exception):
    pass


class M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _tz(v: str) -> str:
    try:
        ZoneInfo(v)
    except Exception:
        raise ValueError(f"unknown IANA timezone {v!r}") from None
    return v


def _regex(v: str) -> str:
    try:
        re.compile(v)
    except re.error as e:
        raise ValueError(f"invalid regex: {e}") from None
    return v


def _check_template(name: str, t: str) -> None:
    try:
        parsed = list(Formatter().parse(t))
    except ValueError as e:
        raise ValueError(f"{name}: bad template: {e}") from None
    got = {f for _, f, _, _ in parsed if f is not None}
    need = TEMPLATE_FIELDS.get(name, set())
    if not (need <= got <= need | {"business"}):
        raise ValueError(f"{name}: fields must be {sorted(need)} (plus optional business), got {sorted(got)}")


class PackMeta(M):
    slug: str
    business: str
    kind: str
    offer: str
    timezone: str
    locale: str = "en-US"
    owner_email: str | None = None

    check_tz = field_validator("timezone")(_tz)

    @field_validator("business", "kind", "offer")
    @classmethod
    def _no_tokens(cls, v):
        if "{{" in v or "<<" in v:  # would be re-expanded by render() or the runtime <<...>> fills
            raise ValueError("must not contain '{{' or '<<'")
        return v


class Calendar(M):
    timezone: str
    slot_hours: tuple[int, ...] = Field(min_length=1)
    slot_minutes: int = Field(gt=0, le=480)
    days_ahead: int = Field(ge=1, le=90)
    weekdays_only: bool
    buffer_minutes: int = Field(0, ge=0)

    check_tz = field_validator("timezone")(_tz)

    @field_validator("slot_hours")
    @classmethod
    def _hours(cls, v):
        if any(h < 0 or h > 23 for h in v) or any(a >= b for a, b in zip(v, v[1:])):
            raise ValueError("hours must be 0..23 and strictly increasing")
        return v


class RuleBase(M):
    id: str = Field(pattern=r"[a-z][a-z0-9_]*")
    field: str
    required: bool = True


class InList(RuleBase):
    rule: Literal["in_list"]
    values: tuple[str, ...] = Field(min_length=1)


class YesNo(RuleBase):
    rule: Literal["yes_no"]


class MaxNumber(RuleBase):
    rule: Literal["max_number"]
    max: int = Field(ge=0)


class InArea(RuleBase):
    rule: Literal["in_area"]
    cities: tuple[str, ...] = Field(min_length=1)

    @field_validator("cities")
    @classmethod
    def _area(cls, v):
        if any(c != c.lower() or not c or re.search(r"\s", c) for c in v):
            raise ValueError("cities must be lowercase single tokens")
        return v


Rule = Annotated[InList | YesNo | MaxNumber | InArea, Field(discriminator="rule")]
# Which lead fields each rule type may read; keeps pack data from naming arbitrary fields (name/phone/email stay core).
RULE_FIELDS = {"in_list": {"service_type", "property_type", "budget_range"}, "yes_no": {"is_owner"},
               "max_number": {"timeline_months"}, "in_area": {"address"}}


class Qualification(M):
    rules: tuple[Rule, ...] = Field(min_length=1)
    service_synonyms: dict[str, str]
    non_business_pattern: str
    owner_yes_pattern: str
    owner_no_pattern: str
    extra_stopwords: frozenset[str]

    @field_validator("non_business_pattern", "owner_yes_pattern", "owner_no_pattern")
    @classmethod
    def _re(cls, v):
        return _regex(v)

    @field_validator("service_synonyms")
    @classmethod
    def _syn(cls, v):
        for pat in v.values():
            _regex(pat)
        return v

    @model_validator(mode="after")
    def _rules(self):
        ids = [r.id for r in self.rules]
        fields = [r.field for r in self.rules]
        if len(set(ids)) != len(ids):
            raise ValueError(f"rules: duplicate id in {ids}")
        if len(set(fields)) != len(fields):
            raise ValueError(f"rules: duplicate field in {fields}")
        if "name" in ids:
            raise ValueError("rules: id 'name' is reserved for the core contact question")
        syn = set(self.service_synonyms)
        for r in self.rules:
            if r.field not in RULE_FIELDS[r.rule]:
                raise ValueError(f"rules: rule {r.id!r}: field {r.field!r} is not allowed for {r.rule}")
            if isinstance(r, InList) and r.field == "service_type" and not set(r.values) <= syn:
                raise ValueError(f"rules: rule {r.id!r}: values must be a subset of service_synonyms")
        return self

    @property
    def service_types(self) -> tuple[str, ...]:
        return (*self.service_synonyms, "other")


class Escalation(M):
    safety: str
    always_human: tuple[str, ...] = ()

    check_safety = field_validator("safety")(_regex)


class FaqEntry(M):
    source: str
    text: str


class Faq(M):
    entries: tuple[FaqEntry, ...] = Field(min_length=1)


class Messages(M):
    closed: dict[str, str]
    disqualify: str
    nurture: str
    no_slots: str
    safe_fallback: str
    qualified_prefix: str
    slot_unavailable_prefix: str
    offer_slots: str
    pick_prompt: str
    booked: str
    anything_else: str
    ask: dict[str, str]
    owner_alert_subject: str
    owner_alert_body: str
    customer_subject: str
    customer_intro: str
    followup_subject: str
    followup_body: str

    @field_validator("closed")
    @classmethod
    def _closed(cls, v):
        if set(v) != CLOSED_KEYS:
            raise ValueError(f"keys must be exactly {sorted(CLOSED_KEYS)}")
        return v

    @field_validator("ask")
    @classmethod
    def _ask(cls, v):
        if not CORE_ASK <= set(v):
            raise ValueError(f"keys must include {sorted(CORE_ASK)}")
        return v


def _validate_messages(m: Messages) -> None:
    for name in Messages.model_fields:
        v = getattr(m, name)
        for t in v.values() if isinstance(v, dict) else [v]:
            _check_template(name, t)


class Pack(M):
    slug: str
    hash: str
    meta: PackMeta
    calendar: Calendar
    qualification: Qualification
    escalation: Escalation
    messages: Messages
    faq: tuple[FaqEntry, ...]


FILES = {"pack": PackMeta, "calendar": Calendar, "qualification": Qualification,
         "escalation": Escalation, "messages": Messages, "faq": Faq}


def pack_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def _parse(path: Path, model: type[M]):
    try:
        obj = model.model_validate(yaml.safe_load(path.read_text()))
        if isinstance(obj, Messages):
            _validate_messages(obj)
        return obj
    except FileNotFoundError:
        raise PackError(f"{path}: file missing") from None
    except yaml.YAMLError as e:
        raise PackError(f"{path}: invalid YAML: {e}") from None
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(map(str, first["loc"])) or "(root)"
        raise PackError(f"{path}: {loc}: {first['msg']}") from None
    except ValueError as e:  # template check
        raise PackError(f"{path}: {e}") from None


def load_pack(slug: str) -> Pack:
    """Validate and load a pack. No DB, no cache."""
    if not SLUG_RE.fullmatch(slug):  # the slug becomes a path
        raise PackError(f"invalid pack slug {slug!r}")
    root = settings.businesses_dir / slug
    parts = {name: _parse(root / f"{name}.yaml", model) for name, model in FILES.items()}
    if parts["pack"].slug != slug:
        raise PackError(f"{root / 'pack.yaml'}: slug: {parts['pack'].slug!r} does not match folder {slug!r}")
    q = parts["qualification"]
    expected = {r.id for r in q.rules} | CORE_ASK
    got = set(parts["messages"].ask)
    if got != expected:
        raise PackError(f"{root / 'messages.yaml'}: ask: missing {sorted(expected - got)}, unexpected {sorted(got - expected)}")
    return Pack(slug=slug, hash=pack_hash(root), meta=parts["pack"], calendar=parts["calendar"],
                qualification=q, escalation=parts["escalation"], messages=parts["messages"],
                faq=parts["faq"].entries)


def render(template: str, pack: Pack) -> str:
    """Fill the {{...}} pack tokens by plain replace; a leftover {{ is a template typo."""
    enum = " | ".join(f'"{s}"' for s in pack.qualification.service_synonyms) + ' | "other"'
    for k, v in {"business": pack.meta.business, "kind": pack.meta.kind, "offer": pack.meta.offer,
                 "service_enum": enum}.items():
        template = template.replace("{{" + k + "}}", v)
    if "{{" in template:
        raise PackError(f"unresolved placeholder in prompt: {template[template.index('{{'):][:40]!r}")
    return template


_CACHE: dict[tuple[str, str], Pack] = {}  # (tenant_id, pack_hash) -> Pack; not business data
_LOCK = threading.Lock()


def get_pack(tenant_id=None) -> Pack:
    t = str(tenant_id or settings.default_tenant_id)
    with system() as c:  # tenants is directory data, read in the explicit system context
        slug = c.execute(text("SELECT pack_slug FROM tenants WHERE id = :t"), {"t": t}).scalar()
    if not slug:
        raise PackError(f"tenant {t} has no pack_slug")
    if not SLUG_RE.fullmatch(slug):
        raise PackError(f"invalid pack slug {slug!r}")
    key = (t, pack_hash(settings.businesses_dir / slug))
    pack = _CACHE.get(key)
    if pack is None:
        pack = load_pack(slug)
        with _LOCK:
            _CACHE[key] = pack
            for old in [k for k in _CACHE if k[0] == t and k != key]:
                del _CACHE[old]
    return pack


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.pack <slug>", file=sys.stderr)
        return 1
    try:
        p = load_pack(argv[0])
    except PackError as e:
        print(f"PackError: {e}", file=sys.stderr)
        return 1
    c = p.calendar
    print(f"slug: {p.slug}\nhash: {p.hash[:12]}\nservices: {', '.join(s for s in p.qualification.service_synonyms)}\n"
          f"faq: {len(p.faq)}\ncalendar: {c.timezone} hours={list(c.slot_hours)} {c.slot_minutes}min "
          f"{c.days_ahead}d buffer={c.buffer_minutes}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
