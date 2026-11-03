"""MOD-04: mock connectors (deterministic, labelled), pack model, disagreement and brief text."""
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from .engine import brief as briefmod
from .engine.brief import build_brief, find_disagreements, is_due
from .engine.connectors import REGISTRY, ConnectorResult, TenantRef, fetch_all, fetch_source
from .pack import PackError, SourceCfg, Tolerance, load_pack

FIXTURES = Path(__file__).parent / "tests_data" / "packs"
REF = TenantRef("demo-venue", "00000000-0000-0000-0000-000000000001", "Europe/Zurich")
DAY = date(2026, 7, 1)


@pytest.fixture(scope="module")
def pack():
    return load_pack("demo-venue", base=FIXTURES)


def test_all_results_are_mock_and_cover_every_source(pack):
    rs = fetch_all(pack.connectors.sources, REF, DAY)
    assert [r.name for r in rs] == ["bookings", "sheet", "accounting", "ads"]
    assert all(r.source == "mock" for r in rs)
    assert [r.ok for r in rs] == [True, True, True, False] and rs[3].error == "Unavailable"


def test_deterministic_across_processes():
    code = ("from datetime import date; from app.engine.connectors import *; from app.pack import SourceCfg;"
            "t=TenantRef('demo-venue','x','Europe/Zurich');"
            "print([dict(fetch_source(SourceCfg(name=n),t,date(2026,7,1)).metrics) for n in REGISTRY])")
    a, b = (subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=Path(__file__).parents[1],
                           env={**os.environ, "PYTHONHASHSEED": s}).stdout for s in ("1", "2"))
    assert a and a == b
    assert a != subprocess.run([sys.executable, "-c", code.replace("demo-venue", "other")], capture_output=True, text=True,
                               cwd=Path(__file__).parents[1]).stdout


def test_bookings_metrics_match_list_and_sheet_offset(pack):
    b = REGISTRY["bookings"](SourceCfg(name="bookings")).fetch(REF, DAY)
    assert b.metrics["bookings_count"] == len(b.bookings)
    assert b.metrics["covers"] == sum(c for _, c in b.bookings)
    assert all(s.tzinfo is not None for s, _ in b.bookings)
    plain = REGISTRY["sheet"](SourceCfg(name="sheet")).fetch(REF, DAY)
    assert plain.metrics["bookings_count"] == b.metrics["bookings_count"]
    s = fetch_source(pack.connectors.sources[1], REF, DAY)
    assert s.metrics["bookings_count"] == b.metrics["bookings_count"] + 3


def test_unknown_kind_and_source_rejected():
    with pytest.raises(ValueError):
        SourceCfg(name="bookings", kind="real")
    with pytest.raises(ValueError):
        SourceCfg(name="crm")


def test_yaml_float_tolerance_rejected():
    with pytest.raises(ValueError):
        Tolerance(abs=0.5)


def rs(**kw):
    return [ConnectorResult(n, metrics={"bookings_count": D(v)}) for n, v in kw.items()]


def test_disagreement_text_shape():
    assert find_disagreements(rs(bookings=14, sheet=17), {"bookings_count": Tolerance(abs=D(1))}) == \
        ["bookings_count: bookings=14 vs sheet=17 (diff 3, tolerance 1)"]


def test_within_tolerance_and_pct_no_flag():
    assert find_disagreements(rs(bookings=14, sheet=15), {"bookings_count": Tolerance(abs=D(1))}) == []
    assert find_disagreements(rs(bookings=100, sheet=105), {"bookings_count": Tolerance(pct=D(5))}) == []
    assert find_disagreements(rs(bookings=100, sheet=106), {"bookings_count": Tolerance(pct=D(5))}) != []


def test_unavailable_is_never_a_disagreement():
    r = rs(bookings=14) + [ConnectorResult("sheet", ok=False, error="Unavailable")]
    assert find_disagreements(r, {}) == []


def test_brief_labels_unavailable_and_disagreement(pack):
    rs_ = fetch_all(pack.connectors.sources, REF, DAY)
    b = build_brief(pack, rs_, date(2026, 7, 2))
    assert len(b.sections) == 4  # nothing silently omitted
    assert all("(mock data)" in s for s in b.sections if "unavailable" not in s)
    assert "ads: source unavailable" in b.sections and "ads: source unavailable (mock data)" not in b.text
    assert "bookings=" in b.disagreements[0] and "sheet=" in b.disagreements[0]
    assert "Report day 2026-07-01" in b.text and b.html.startswith("<pre>")


def test_brief_money_decimal_with_currency(pack):
    r = [ConnectorResult("accounting", metrics={"revenue": D("1234.5"), "outstanding_invoices": D("0")})]
    b = build_brief(pack, r, date(2026, 7, 2))
    assert "revenue=CHF 1234.50" in b.text


def test_brief_html_escaped(pack):
    p = pack.model_copy(update={"meta": pack.meta.model_copy(update={"business": "<b>X</b>"})})
    assert "<b>X" not in build_brief(p, [], date(2026, 7, 2)).html


def test_exception_text_never_leaks(pack):
    class Boom:
        def __init__(self, cfg): ...
        def fetch(self, t, d): raise RuntimeError("secret-dsn://pw")
    old = REGISTRY["ads"]
    REGISTRY["ads"] = Boom
    try:
        r = fetch_source(SourceCfg(name="ads"), REF, DAY)
    finally:
        REGISTRY["ads"] = old
    assert (r.ok, r.error) == (False, "RuntimeError")
    assert "secret" not in build_brief(pack, [r], DAY).text


def u(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


@pytest.mark.parametrize("now,send,ran,want", [
    (u(2026, 7, 1, 4, 59), 7, False, False),   # Zurich 06:59 (CEST)
    (u(2026, 7, 1, 5, 0), 7, False, True),     # 07:00
    (u(2026, 7, 1, 7, 59), 7, False, True),    # 09:59
    (u(2026, 7, 1, 8, 0), 7, False, False),    # 10:00
    (u(2026, 7, 1, 5, 0), 7, True, False),     # already ran
    (u(2026, 3, 29, 0, 59), 2, False, False),  # spring-forward: local 01:59
    (u(2026, 3, 29, 1, 0), 2, False, True),    # local 03:00, hour 2 never exists
    (u(2026, 10, 25, 0, 30), 2, False, True),  # fall-back: first 02:30 (CEST)
    (u(2026, 10, 25, 1, 30), 2, True, False),  # second 02:30 (CET) blocked by the run row
    (u(2026, 10, 25, 1, 30), 2, False, True),  # without a run it is still in the window
])
def test_is_due(now, send, ran, want):
    assert is_due(now, "Europe/Zurich", send, ran) is want


def test_grace_constant():
    assert briefmod.BRIEF_GRACE_HOURS == 3
