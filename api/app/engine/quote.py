"""Pure quote builder (MOD-01). Money is Decimal end to end; no float, no LLM, no I/O."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from ..pack import CustomerSurcharge, GroupDiscount, Pack, Service

# shortcut: two-decimal currencies only (CHF, EUR, USD...); zero-decimal ones like JPY need a per-currency exponent.
CURRENCY_EXP = Decimal("0.01")
CUSTOMER_TYPES = ("consumer", "corporate")
Reason = Literal["missing_input", "unknown_service", "unknown_add_on", "missing_price", "qty_below_min",
                 "qty_not_applicable", "rule_unevaluable"]


@dataclass(frozen=True)
class QuoteRequest:
    service_id: str | None
    qty: int | None
    add_on_ids: tuple[str, ...] = ()
    customer_type: str | None = None


@dataclass(frozen=True)
class Line:
    kind: Literal["service", "add_on", "discount", "surcharge"]
    ref: str
    label: str
    qty: int
    unit_price: Decimal | None
    amount: Decimal


@dataclass(frozen=True)
class Quote:
    currency: str
    lines: tuple[Line, ...]
    total: Decimal


@dataclass(frozen=True)
class NeedsHuman:
    reason: Reason
    missing: tuple[str, ...]


def fmt(d: Decimal) -> str:
    return format(d, "f")


def _q(d: Decimal) -> Decimal:
    return d.quantize(CURRENCY_EXP, rounding=ROUND_HALF_UP)


def rule_percents(service: Service) -> set[Decimal]:
    out: set[Decimal] = set()
    for r in service.rules:
        if isinstance(r, GroupDiscount):
            out |= {t.percent for t in r.tiers}
        elif r.percent is not None:
            out.add(r.percent)
    return out


def build_quote(pack: Pack, req: QuoteRequest) -> Quote | NeedsHuman:
    """Rounding (refines D-04): each derived percent line is quantized at creation with ROUND_HALF_UP and
    total = sum of lines, so the amounts an email quotes always add up and nothing is rounded twice."""
    cfg = pack.services
    missing = tuple(n for n, v in (("service_id", req.service_id), ("qty", req.qty)) if v is None)
    if missing:
        return NeedsHuman("missing_input", missing)
    svc = next((s for s in cfg.services if s.id == req.service_id), None)
    if svc is None:
        return NeedsHuman("unknown_service", ("service_id",))
    qty = req.qty
    if qty < svc.min_qty:
        return NeedsHuman("qty_below_min", ("qty",))
    if svc.unit == "flat" and qty != 1:
        return NeedsHuman("qty_not_applicable", ("qty",))
    if svc.price is None:
        return NeedsHuman("missing_price", ("price",))
    add_ons = {a.id: a for a in svc.add_ons}
    wanted = tuple(dict.fromkeys(req.add_on_ids))  # a repeated id is not charged twice
    unknown = tuple(i for i in wanted if i not in add_ons)
    if unknown:
        return NeedsHuman("unknown_add_on", unknown)
    unpriced = tuple(f"add_on:{i}" for i in wanted if add_ons[i].price is None)
    if unpriced:
        return NeedsHuman("missing_price", unpriced)
    surcharge = next((r for r in svc.rules if isinstance(r, CustomerSurcharge)), None)
    if surcharge and req.customer_type not in CUSTOMER_TYPES:
        return NeedsHuman("rule_unevaluable", ("customer_type",))

    svc_amount = _q(svc.price * qty)
    lines = [Line("service", svc.id, svc.name, qty, svc.price, svc_amount)]
    for i in wanted:
        a = add_ons[i]
        n = 1 if a.unit == "flat" else qty
        lines.append(Line("add_on", a.id, a.name, n, a.price, _q(a.price * n)))
    disc = next((r for r in svc.rules if isinstance(r, GroupDiscount)), None)
    tier = max((t for t in disc.tiers if t.min_qty <= qty), key=lambda t: t.min_qty, default=None) if disc else None
    if tier:  # applies to the service line only, not add-ons
        lines.append(Line("discount", "group_discount", f"Group discount {tier.percent}%", 1, None,
                          -_q(svc_amount * tier.percent / 100)))
    if surcharge and req.customer_type == surcharge.customer_type:
        base = sum((ln.amount for ln in lines), Decimal(0))  # discounted subtotal
        amt = _q(base * surcharge.percent / 100) if surcharge.percent is not None else surcharge.fixed
        label = f"{surcharge.customer_type.capitalize()} surcharge" + (f" {surcharge.percent}%" if surcharge.percent is not None else "")
        lines.append(Line("surcharge", "customer_surcharge", label, 1, None, amt))
    return Quote(cfg.currency, tuple(lines), sum((ln.amount for ln in lines), Decimal(0)))


def quote_to_payload(quote: Quote) -> dict:
    """JSON/jsonb form: every amount is a string (FastAPI/json would turn Decimal into float)."""
    return {"currency": quote.currency, "total": fmt(quote.total),
            "lines": [{"kind": ln.kind, "ref": ln.ref, "label": ln.label, "qty": ln.qty,
                       "unit_price": fmt(ln.unit_price) if ln.unit_price is not None else None,
                       "amount": fmt(ln.amount)} for ln in quote.lines]}
