"""MOD-05 routes: /daily-brief idempotency, /daily-brief/due scoping, capacity connector fallback."""
import shutil
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import auth, brief_routes, capacity_routes, db
from .config import settings
from .engine import connectors
from .main import app

ADMIN = {"X-Admin-Key": "test-key"}
# Zurich is CEST in July: 05:00Z = 07:00 local, 2026-07-01
NOW = datetime(2026, 7, 1, 5, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-key")
    monkeypatch.setattr(brief_routes, "utcnow", lambda: NOW)
    return TestClient(app)


def wipe(*tids):
    with db.system() as c:
        c.execute(text("DELETE FROM brief_runs WHERE tenant_id = ANY(:t)"), {"t": list(tids)})
        c.execute(text("DELETE FROM capacity_flags WHERE tenant_id = ANY(:t)"), {"t": list(tids)})


@pytest.fixture
def h(venue_tenant):
    wipe(venue_tenant)
    yield {"X-API-Key": auth.issue_key(venue_tenant)["key"]}
    wipe(venue_tenant)


def runs(tid):
    with db.tx(tid) as c:
        return c.execute(text("SELECT run_date, payload FROM brief_runs")).all()


def test_brief_creates_run_and_is_idempotent(client, h, venue_tenant, monkeypatch):
    r1 = client.post("/daily-brief", headers=h)
    assert r1.status_code == 200, r1.text
    j = r1.json()
    assert j["local_date"] == "2026-07-01" and len(runs(venue_tenant)) == 1
    assert all(s["source"] == "mock" for s in j["sources"])
    assert {"name": "ads", "source": "mock", "ok": False, "error": "Unavailable", "metrics": {}} in j["sources"]
    assert "ads: source unavailable" in j["text"] and "(mock data)" in j["text"]
    monkeypatch.setattr(brief_routes, "build_brief", lambda *a: pytest.fail("recomputed"))
    assert client.post("/daily-brief", headers=h).json() == j


def test_force_recomputes(client, h, venue_tenant):
    client.post("/daily-brief", headers=h)
    with db.system() as c:
        c.execute(text("UPDATE brief_runs SET payload='{\"stale\": 1}' WHERE tenant_id=:t"), {"t": venue_tenant})
    assert client.post("/daily-brief", json={"force": False}, headers=h).json() == {"stale": 1}
    r = client.post("/daily-brief", json={"force": True}, headers=h)
    assert r.json()["local_date"] == "2026-07-01" and len(runs(venue_tenant)) == 1


def test_roofing_404_and_admin_only_401(client, h, roofing_tenant):
    key = auth.issue_key(roofing_tenant)["key"]
    assert client.post("/daily-brief", headers={"X-API-Key": key}).status_code == 404
    assert client.post("/daily-brief", headers=ADMIN).status_code == 401


def test_due_tenant_key(client, h, venue_tenant, monkeypatch):
    assert client.post("/daily-brief/due", headers=h).json() == {
        "due": [{"tenant_id": venue_tenant, "local_date": "2026-07-01", "send_hour": 7}]}
    monkeypatch.setattr(brief_routes, "utcnow", lambda: datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc))  # 10:00 local
    assert client.post("/daily-brief/due", headers=h).json() == {"due": []}
    monkeypatch.setattr(brief_routes, "utcnow", lambda: NOW)
    client.post("/daily-brief", headers=h)
    assert client.post("/daily-brief/due", headers=h).json() == {"due": []}  # already ran


def test_due_no_key_401(client):
    assert client.post("/daily-brief/due").status_code == 403  # require_scope: no credential at all
    assert client.post("/daily-brief/due", headers={"X-API-Key": "rd_live_nope"}).status_code == 401


def test_due_admin_iterates_tenants_and_skips_no_connectors(client, h, venue_tenant, packs_dir, roofing_tenant):
    from .tenants import ensure_tenant
    v2 = packs_dir / "test-venue2"
    shutil.copytree(packs_dir / "demo-venue", v2)
    p = v2 / "pack.yaml"
    p.write_text(p.read_text().replace("slug: demo-venue", "slug: test-venue2"))
    t2 = ensure_tenant("test-venue2")
    try:
        got = {d["tenant_id"] for d in client.post("/daily-brief/due", headers=ADMIN).json()["due"]}
        assert got == {venue_tenant, t2} and roofing_tenant not in got
        one = client.post("/daily-brief/due", headers={**ADMIN, "X-Tenant-Id": t2}).json()["due"]
        assert [d["tenant_id"] for d in one] == [t2]
    finally:
        wipe(t2)


def test_tenant_b_cannot_read_a_runs(client, h, venue_tenant, roofing_tenant):
    client.post("/daily-brief", headers=h)
    assert len(runs(venue_tenant)) == 1 and runs(roofing_tenant) == []


# ---- capacity fallback ----
def cap(client, h, **kw):
    return client.post("/capacity/check", json={"first": "2026-07-01", "last": "2026-07-03", **kw}, headers=h)


def test_capacity_uses_connector_when_no_body(client, h, venue_tenant):
    r = cap(client, h)
    assert r.status_code == 200 and "source_unavailable" not in r.json()
    # connector is deterministic, so a rerun is unchanged
    assert {f["status"] for f in cap(client, h).json()["flags"]} <= {"unchanged"}


def test_capacity_explicit_empty_connector_day_is_checkable(client, h, venue_tenant, monkeypatch):
    class Empty:
        def __init__(self, cfg): ...
        def fetch(self, t, d): return connectors.ConnectorResult("bookings", bookings=())
    monkeypatch.setitem(connectors.REGISTRY, "bookings", Empty)
    r = cap(client, h)
    assert r.status_code == 200 and {f["kind"] for f in r.json()["flags"]} == {"under_utilised"}


def test_capacity_connector_unavailable_leaves_flags(client, h, venue_tenant, monkeypatch):
    first = cap(client, h, bookings=[{"start": "2026-07-01T16:00:00Z", "covers": 31}])
    assert first.json()["flags"]
    class Down:
        def __init__(self, cfg): ...
        def fetch(self, t, d): raise RuntimeError("boom")
    monkeypatch.setitem(connectors.REGISTRY, "bookings", Down)
    r = cap(client, h)
    assert r.json() == {"source_unavailable": "bookings", "source": "mock", "checked_shifts": 0, "flags": [], "resolved": []}
    with db.tx(venue_tenant) as c:
        assert c.execute(text("SELECT count(*) FROM capacity_flags WHERE resolved_at IS NOT NULL")).scalar() == 0


def test_due_unknown_tenant_404(client):
    import uuid
    r = client.post("/daily-brief/due", headers={**ADMIN, "X-Tenant-Id": str(uuid.uuid4())})
    print("PRE-FIX due status", r.status_code, r.text)
    assert r.status_code == 404 and r.json() == {"detail": "tenant not found"}


def test_due_skips_broken_pack(client, h, venue_tenant, roofing_tenant, monkeypatch):
    real = brief_routes.get_pack

    def flaky(t):
        if t == roofing_tenant:
            raise RuntimeError("boom")
        return real(t)
    monkeypatch.setattr(brief_routes, "get_pack", flaky)
    r = client.post("/daily-brief/due", headers=ADMIN)
    assert r.status_code == 200 and venue_tenant in [d["tenant_id"] for d in r.json()["due"]]


# ---- GET /daily-brief (BRF-01) ----
def test_get_brief_empty(client, h):
    r = client.get("/daily-brief", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"latest": None, "runs": []}


def test_get_brief_after_post(client, h):
    posted = client.post("/daily-brief", headers=h)
    assert posted.status_code == 200, posted.text
    r = client.get("/daily-brief", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["latest"] == posted.json()
    assert len(j["runs"]) == 1 and set(j["runs"][0]) == {"run_date", "created_at"}
    assert j["runs"][0]["run_date"] == "2026-07-01"
    datetime.fromisoformat(j["runs"][0]["created_at"])


def test_get_brief_keeps_14_newest(client, h, venue_tenant):
    with db.system() as c:
        for i in range(1, 17):
            c.execute(text("INSERT INTO brief_runs (tenant_id, run_date, payload) VALUES (:t, :d, CAST(:p AS jsonb))"),
                      {"t": venue_tenant, "d": f"2026-06-{i:02d}", "p": f'{{"n": {i}}}'})
    r = client.get("/daily-brief", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    dates = [x["run_date"] for x in j["runs"]]
    assert len(dates) == 14 and dates == sorted(dates, reverse=True) and dates[0] == "2026-06-16"
    assert j["latest"] == {"n": 16}


def test_get_brief_module_and_auth(client, h, roofing_tenant):
    key = auth.issue_key(roofing_tenant)["key"]
    r = client.get("/daily-brief", headers={"X-API-Key": key})
    assert r.status_code == 404 and r.json()["detail"] == "module not enabled"
    assert client.get("/daily-brief", headers=ADMIN).status_code == 401


def test_get_brief_shows_unavailable_source(client, h):
    assert client.post("/daily-brief", headers=h).status_code == 200
    r = client.get("/daily-brief", headers=h)
    assert r.status_code == 200, r.text
    srcs = r.json()["latest"]["sources"]
    ads = [s for s in srcs if s["name"] == "ads"]
    assert ads and ads[0]["ok"] is False and ads[0]["error"]
    assert all(s["source"] == "mock" for s in srcs)


def test_get_due_is_not_a_route_collision(client, h):
    # the "/" StaticFiles mount answers unmatched GETs, so 404 (not 405); the point is GET /due is not the GET "" handler
    assert client.get("/daily-brief/due", headers=h).status_code in (404, 405)
    assert client.post("/daily-brief/due", headers=h).status_code == 200
