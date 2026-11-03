"""Daily brief (MOD-05): pure, LLM-free. Numbers come from connector results; text is templated."""
import html as _html
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..pack import Pack
from .connectors import METRICS, MONEY_METRICS, ConnectorResult
from .quote import fmt

BRIEF_GRACE_HOURS = 3
MOCK = "(mock data)"
UNAVAILABLE = "source unavailable"


@dataclass(frozen=True)
class Brief:
    sections: tuple[str, ...]
    disagreements: tuple[str, ...]
    text: str
    html: str


def find_disagreements(results, tolerance) -> list[str]:
    """Same metric from >= 2 ok sources differing beyond tolerance. Unavailable sources never count."""
    by_metric: dict[str, list[tuple[str, Decimal]]] = {}
    for r in results:
        if r.ok:
            for k, v in r.metrics.items():
                by_metric.setdefault(k, []).append((r.name, v))
    out = []
    for k, vals in by_metric.items():
        tol = tolerance.get(k)
        allowed = max(tol.abs, max(v for _, v in vals) * tol.pct / 100) if tol else Decimal(0)
        for i, (na, a) in enumerate(vals):
            for nb, b in vals[i + 1:]:
                if abs(a - b) > allowed:
                    out.append(f"{k}: {na}={fmt(a)} vs {nb}={fmt(b)} (diff {fmt(abs(a - b))}, tolerance {fmt(allowed)})")
    return out


def _value(k: str, v: Decimal, currency: str) -> str:
    return f"{currency} {v:.2f}".strip() if k in MONEY_METRICS else f"{int(v)}"


def build_brief(pack: Pack, results: list[ConnectorResult], local_date: date) -> Brief:
    report_day = local_date - timedelta(days=1)  # the closed previous local day
    cur = pack.services.currency if pack.services else ""
    sections = []
    for r in results:
        if not r.ok:
            sections.append(f"{r.name}: {UNAVAILABLE}")
            continue
        body = ", ".join(f"{k}={_value(k, r.metrics[k], cur)}" for k in METRICS[r.name] if k in r.metrics)
        sections.append(f"{r.name}: {body} {MOCK}" if r.source == "mock" else f"{r.name}: {body}")
    dis = find_disagreements(results, pack.connectors.brief.tolerance if pack.connectors else {})
    lines = [f"Daily brief for {pack.meta.business}", f"Report day {report_day.isoformat()} ({pack.meta.timezone}), prepared {local_date.isoformat()}", ""]
    lines += sections
    lines += ["", "Disagreements:"] + (dis or ["none"])
    text = "\n".join(lines)
    return Brief(tuple(sections), tuple(dis), text, "<pre>" + _html.escape(text) + "</pre>")


def is_due(now_utc: datetime, tz: str, send_hour: int, already_ran: bool) -> bool:
    if already_ran:
        return False
    h = now_utc.astimezone(ZoneInfo(tz)).hour
    return send_hour <= h < send_hour + BRIEF_GRACE_HOURS
