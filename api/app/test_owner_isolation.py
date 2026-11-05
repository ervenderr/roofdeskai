"""ISO-01: two tenants with the same modules; each key sees only its own drafts, capacity flags and brief."""
import shutil
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import auth, brief_routes, db
from .main import app
from .tenants import ensure_tenant

BOOK = "2026-07-01T16:00:00Z"  # Wed evening, demo-venue capacity 30: 31 and 33 both flag over_capacity
DAY = "2026-07-01"
EMPTY_BRIEF = {"latest": None, "runs": []}


def wipe(*tids):
    with db.system() as c:
        for t in ("brief_runs", "capacity_flags", "drafts"):
            c.execute(text(f"DELETE FROM {t} WHERE tenant_id = ANY(:t)"), {"t": list(tids)})  # fixed table names


@pytest.fixture
def clock(monkeypatch):
    now = {"v": datetime(2026, 7, 1, 5, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(brief_routes, "utcnow", lambda: now["v"])
    return now


@pytest.fixture
def ab(venue_tenant, packs_dir):
    b_dir = packs_dir / "test-venue-iso"
    shutil.copytree(packs_dir / "demo-venue", b_dir)
    p = b_dir / "pack.yaml"
    p.write_text(p.read_text().replace("slug: demo-venue", "slug: test-venue-iso"))
    tb = ensure_tenant("test-venue-iso")
    wipe(venue_tenant, tb)
    yield ({"X-API-Key": auth.issue_key(venue_tenant)["key"]}, {"X-API-Key": auth.issue_key(tb)["key"]})
    wipe(venue_tenant, tb)


def ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def seed(client, h, covers):
    draft = ok(client.post("/quotes", json={"request": {"service_id": "escape_room"}}, headers=h))
    assert draft["status"] == "needs_human"
    ok(client.post("/capacity/check", json={"bookings": [{"start": BOOK, "covers": covers}], "first": DAY, "last": DAY}, headers=h))
    ok(client.post("/daily-brief", headers=h))
    return draft["id"]


def test_each_tenant_sees_only_its_own_rows(ab, clock):
    client, (ha, hb) = TestClient(app), ab

    a_id = seed(client, ha, 31)
    # B sees nothing of A
    assert ok(client.get("/drafts", headers=hb)) == []
    assert client.get(f"/drafts/{a_id}", headers=hb).status_code == 404
    assert client.post(f"/drafts/{a_id}/reject", headers=hb).status_code == 404
    assert ok(client.get(f"/drafts/{a_id}", headers=ha))["status"] == "needs_human"  # unchanged
    assert ok(client.get("/capacity/flags", headers=hb)) == []
    assert ok(client.get("/capacity/flags?open=true", headers=hb)) == []
    assert ok(client.get("/daily-brief", headers=hb)) == EMPTY_BRIEF

    clock["v"] = datetime(2026, 7, 2, 5, 0, tzinfo=timezone.utc)
    b_id = seed(client, hb, 33)
    a_ids = {d["id"] for d in ok(client.get("/drafts", headers=ha))}
    b_ids = {d["id"] for d in ok(client.get("/drafts", headers=hb))}
    assert a_ids == {a_id} and b_ids == {b_id}

    fa, fb = ok(client.get("/capacity/flags", headers=ha)), ok(client.get("/capacity/flags", headers=hb))
    assert [f["details"]["covers"] for f in fa] == [31] and [f["details"]["covers"] for f in fb] == [33]

    ba, bb = ok(client.get("/daily-brief", headers=ha)), ok(client.get("/daily-brief", headers=hb))
    assert [r["run_date"] for r in ba["runs"]] == ["2026-07-01"] and ba["latest"]["local_date"] == "2026-07-01"
    assert [r["run_date"] for r in bb["runs"]] == ["2026-07-02"] and bb["latest"]["local_date"] == "2026-07-02"
