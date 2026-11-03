"""Connector layer (MOD-04): a Protocol plus four deterministic MOCK adapters. Plain classes so an MCP server can wrap them later.
Every result carries source='mock'. Mock data is seeded from sha256(slug:name:day), identical across processes."""
import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Callable, Mapping, Protocol
from zoneinfo import ZoneInfo

from ..pack import SourceCfg

CENT = Decimal("0.01")


@dataclass(frozen=True)
class TenantRef:
    slug: str
    tenant_id: str
    tz: str


@dataclass(frozen=True)
class ConnectorResult:
    name: str
    source: str = "mock"
    ok: bool = True
    metrics: Mapping[str, Decimal] = field(default_factory=dict)
    error: str | None = None  # exception type name only, never its text
    bookings: tuple[tuple[datetime, int], ...] = ()  # (aware UTC start, covers); bookings adapter only


class Connector(Protocol):
    name: str

    def fetch(self, tenant: TenantRef, day: date) -> ConnectorResult: ...


class Unavailable(Exception):
    pass


def _rng(slug: str, name: str, day: date) -> random.Random:
    return random.Random(int(hashlib.sha256(f"{slug}:{name}:{day.isoformat()}".encode()).hexdigest(), 16))


def _bookings(t: TenantRef, day: date) -> tuple[tuple[datetime, int], ...]:
    r = _rng(t.slug, "bookings", day)
    tz = ZoneInfo(t.tz)
    out = []
    for _ in range(r.randint(0, 6)):
        local = datetime.combine(day, time(r.randint(10, 21), 0), tzinfo=tz)
        out.append((local.astimezone(timezone.utc), r.randint(2, 12)))
    return tuple(sorted(out))


def _money(r: random.Random, hi: int) -> Decimal:
    return (Decimal(r.randint(0, hi)) * CENT).quantize(CENT)


class _Mock:
    name = ""

    def __init__(self, cfg: SourceCfg):
        self.cfg = cfg

    def _metrics(self, t: TenantRef, day: date) -> dict[str, Decimal]:
        raise NotImplementedError

    def fetch(self, tenant: TenantRef, day: date) -> ConnectorResult:
        if self.cfg.mock.unavailable:
            raise Unavailable(self.name)
        m = {k: v + self.cfg.mock.offsets.get(k, Decimal(0)) for k, v in self._metrics(tenant, day).items()}
        return ConnectorResult(self.name, metrics=m)


class BookingsMock(_Mock):
    name = "bookings"

    def _metrics(self, t, day):
        b = _bookings(t, day)
        return {"bookings_count": Decimal(len(b)), "covers": Decimal(sum(c for _, c in b))}

    def fetch(self, tenant, day):
        res = super().fetch(tenant, day)
        return ConnectorResult(res.name, metrics=res.metrics, bookings=_bookings(tenant, day))


class SheetMock(_Mock):
    name = "sheet"

    def _metrics(self, t, day):  # same underlying count as bookings, so only an offset creates a disagreement
        r = _rng(t.slug, "sheet", day)
        return {"bookings_count": Decimal(len(_bookings(t, day))), "walk_ins": Decimal(r.randint(0, 8))}


class AccountingMock(_Mock):
    name = "accounting"

    def _metrics(self, t, day):
        r = _rng(t.slug, "accounting", day)
        return {"revenue": _money(r, 500000), "outstanding_invoices": _money(r, 200000)}


class AdsMock(_Mock):
    name = "ads"

    def _metrics(self, t, day):
        r = _rng(t.slug, "ads", day)
        return {"ad_spend": _money(r, 50000), "ad_leads": Decimal(r.randint(0, 30))}


REGISTRY: dict[str, Callable[[SourceCfg], Connector]] = {
    "bookings": BookingsMock, "sheet": SheetMock, "accounting": AccountingMock, "ads": AdsMock}

# fixed display order per source
METRICS = {"bookings": ("bookings_count", "covers"), "sheet": ("bookings_count", "walk_ins"),
           "accounting": ("revenue", "outstanding_invoices"), "ads": ("ad_spend", "ad_leads")}
MONEY_METRICS = frozenset({"revenue", "outstanding_invoices", "ad_spend"})


def fetch_source(cfg: SourceCfg, tenant: TenantRef, day: date) -> ConnectorResult:
    """Never raises: a failing adapter becomes ok=False with the exception type name."""
    try:
        return REGISTRY[cfg.name](cfg).fetch(tenant, day)
    except Exception as e:
        return ConnectorResult(cfg.name, ok=False, error=type(e).__name__)


def fetch_all(sources, tenant: TenantRef, day: date) -> list[ConnectorResult]:
    return [fetch_source(s, tenant, day) for s in sources]
