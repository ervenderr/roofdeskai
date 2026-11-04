"""MCP connector tools: in-process Client via anyio.run, compared with fetch_source. No DB."""
import json
from datetime import date

import anyio
import pytest
from mcp import Client

from scripts.mcp_server import mcp

from .config import settings
from .engine.connectors import TenantRef, fetch_source
from .pack import load_pack

TOOLS = {"fetch_sheet": "sheet", "fetch_accounting": "accounting", "fetch_bookings": "bookings", "fetch_ads": "ads"}
DAY = "2026-03-14"
TENANT = "demo-venue"


def _run(coro_fn):
    return anyio.run(coro_fn)


def _list():
    async def go():
        async with Client(mcp) as c:
            return (await c.list_tools()).tools
    return _run(go)


def _call(name, args):
    async def go():
        async with Client(mcp) as c:
            return await c.call_tool(name, args)
    res = _run(go)
    text = res.content[0].text if res.content else ""
    assert "Traceback" not in text
    if res.is_error:
        return None
    return res.structured_content if res.structured_content is not None else json.loads(text)


@pytest.fixture(autouse=True)
def _packs(packs_dir):
    return packs_dir


def test_list_tools():
    tools = _list()
    assert {t.name for t in tools} == set(TOOLS)
    assert all("MOCK" in (t.description or "") for t in tools)


@pytest.mark.parametrize("tool,source", TOOLS.items())
def test_matches_fetch_source(tool, source):
    pack = load_pack(TENANT)
    cfg = next(s for s in pack.connectors.sources if s.name == source)
    want = fetch_source(cfg, TenantRef(pack.slug, "mcp", pack.meta.timezone), date.fromisoformat(DAY))
    got = _call(tool, {"tenant": TENANT, "day": DAY})
    assert got["source"] == "mock" == want.source
    assert got["ok"] is want.ok
    assert got["error"] == want.error
    assert got["metrics"] == {k: str(v) for k, v in want.metrics.items()}
    assert [tuple(b) for b in got["bookings"]] == [(d.isoformat(), n) for d, n in want.bookings]


def test_unavailable_source_is_not_an_exception():
    got = _call("fetch_ads", {"tenant": TENANT, "day": DAY})
    assert got["ok"] is False and got["error"] == "Unavailable"


@pytest.mark.parametrize("tenant,day", [
    ("no-such-pack", DAY), ("../etc", DAY), ("..", DAY), ("Bad Slug", DAY), (TENANT, "14/03/2026"), (TENANT, "")])
def test_bad_input_never_traces(tenant, day):
    got = _call("fetch_sheet", {"tenant": tenant, "day": day})
    assert got is None or (got["ok"] is False and got["error"])


def test_missing_source_and_missing_connectors(packs_dir):
    (packs_dir / TENANT / "connectors.yaml").unlink()
    got = _call("fetch_sheet", {"tenant": TENANT, "day": DAY})
    assert got["ok"] is False and got["error"] == "NotConfigured"
    assert settings.businesses_dir == packs_dir
