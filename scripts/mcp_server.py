"""MCP stdio server: the four MOCK connector adapters as tools. Run: python -m scripts.mcp_server
Wraps engine.connectors.fetch_source with the pack's own source config. Never print to stdout (it is the protocol)."""
from datetime import date

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from app.engine.connectors import TenantRef, fetch_source
from app.pack import PackError, load_pack

mcp = MCPServer("connectors")


class ConnectorOut(BaseModel):
    source: str = "mock"
    ok: bool
    error: str | None = None
    metrics: dict[str, str] = {}
    bookings: list[tuple[str, int]] = []  # (ISO UTC start, covers)


def _fail(error: str) -> ConnectorOut:
    return ConnectorOut(ok=False, error=error)


def _fetch(source: str, tenant: str, day: str) -> ConnectorOut:
    try:
        pack = load_pack(tenant)
        when = date.fromisoformat(day)
    except (PackError, ValueError) as e:
        return _fail(type(e).__name__)
    cfg = next((s for s in (pack.connectors.sources if pack.connectors else []) if s.name == source), None)
    if cfg is None:
        return _fail("NotConfigured")
    res = fetch_source(cfg, TenantRef(pack.slug, "mcp", pack.meta.timezone), when)
    return ConnectorOut(source=res.source, ok=res.ok, error=res.error,
                        metrics={k: str(v) for k, v in res.metrics.items()},
                        bookings=[(d.isoformat(), n) for d, n in res.bookings])


def _register(source: str) -> None:
    def tool(tenant: str, day: str) -> ConnectorOut:
        return _fetch(source, tenant, day)
    mcp.tool(name=f"fetch_{source}", description=f"MOCK {source} data for a tenant pack slug and an ISO date (YYYY-MM-DD).")(tool)


for _s in ("sheet", "accounting", "bookings", "ads"):
    _register(_s)

if __name__ == "__main__":
    mcp.run(transport="stdio")
