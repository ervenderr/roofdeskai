"""MOD-02: tenant-scoped drafts queue, require_module guard, assert_rls_enforced coverage check."""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import auth, db, drafts
from .config import settings
from .main import app
from .test_rls_proof import rls  # noqa: F401  (fixture)


def _tenant(tag: str) -> dict:
    tid = str(uuid.uuid4())
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:i, :s, :s, 'UTC', 'summit-roofing')"),
                  {"i": tid, "s": f"test-drafts-{tag}-{tid[:8]}"})
    return {"id": tid, "h": {"X-API-Key": auth.issue_key(tid)["key"]}}


@pytest.fixture
def ab():
    return _tenant("a"), _tenant("b"), TestClient(app)


def _mk(t, status="pending", h=None, kind="quote"):
    return drafts.create_or_get_draft(t["id"], kind, status, {"x": 1}, h or uuid.uuid4().hex)


# ---- coverage check ----
def test_assert_rls_enforced_names_table_missing_rls(rls):  # noqa: F811
    scratch, role_eng = rls
    db.assert_rls_enforced(role_eng)  # control: the real schema passes
    with db.system(scratch) as c:
        c.execute(text("CREATE TABLE bad_t (tenant_id uuid)"))
        c.execute(text("GRANT SELECT ON bad_t TO app_rw"))
    with pytest.raises(RuntimeError, match="bad_t"):
        db.assert_rls_enforced(role_eng)


# ---- require_module ----
def test_require_module():
    assert drafts.require_module("x", "services") == "x"
    with pytest.raises(HTTPException) as e:
        drafts.require_module(None, "services")
    assert e.value.status_code == 404 and e.value.detail == "module not enabled"


# ---- drafts API ----
def test_list_get_own_and_other_tenant_404(ab):
    a, b, client = ab
    did, deduped = _mk(a)
    assert deduped is False
    r = client.get("/drafts", headers=a["h"])
    assert r.status_code == 200 and [d["id"] for d in r.json()] == [did]
    assert client.get(f"/drafts/{did}", headers=a["h"]).json()["status"] == "pending"
    assert client.get("/drafts", headers=b["h"]).json() == []
    assert client.get(f"/drafts/{did}", headers=b["h"]).status_code == 404
    assert client.post(f"/drafts/{did}/approve", headers=b["h"]).status_code == 404
    assert client.post(f"/drafts/{did}/reject", headers=b["h"]).status_code == 404
    assert client.get(f"/drafts/{did}", headers=a["h"]).json()["status"] == "pending"  # untouched


def test_filters(ab):
    a, _, client = ab
    q, _ = _mk(a)
    r, _ = _mk(a, kind="review_reply", status="needs_human")
    assert {d["id"] for d in client.get("/drafts?kind=review_reply", headers=a["h"]).json()} == {r}
    assert {d["id"] for d in client.get("/drafts?status=pending", headers=a["h"]).json()} == {q}


def test_approve_pending_then_409(ab):
    a, _, client = ab
    did, _ = _mk(a)
    r = client.post(f"/drafts/{did}/approve", headers=a["h"])
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["decided_at"]
    assert client.post(f"/drafts/{did}/approve", headers=a["h"]).status_code == 409
    assert client.post(f"/drafts/{did}/reject", headers=a["h"]).status_code == 409


def test_needs_human_only_rejectable(ab):
    a, _, client = ab
    did, _ = _mk(a, status="needs_human")
    assert client.post(f"/drafts/{did}/approve", headers=a["h"]).status_code == 409
    r = client.post(f"/drafts/{did}/reject", headers=a["h"])
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_unknown_draft_404(ab):
    a, _, client = ab
    assert client.post("/drafts/999999999/approve", headers=a["h"]).status_code == 404


def test_identical_open_request_is_deduped(ab):
    a, b, _ = ab
    first, d1 = _mk(a, h="same")
    again, d2 = _mk(a, h="same")
    assert (again, d1, d2) == (first, False, True)
    other, d3 = _mk(b, h="same")  # other tenant: its own draft
    assert other != first and d3 is False
    with db.tx(a["id"]) as c:
        assert c.execute(text("SELECT count(*) FROM drafts")).scalar() == 1


def test_decided_draft_does_not_block_new_open_one(ab):
    a, _, client = ab
    first, _ = _mk(a, h="h2")
    client.post(f"/drafts/{first}/approve", headers=a["h"])
    second, deduped = _mk(a, h="h2")
    assert second != first and deduped is False


def test_events_hold_ids_only(ab):
    a, _, client = ab
    did, _ = _mk(a)
    client.post(f"/drafts/{did}/approve", headers=a["h"])
    with db.system() as c:
        kinds = {r[0] for r in c.execute(text("SELECT kind FROM agent_events WHERE tenant_id=:t"), {"t": a["id"]})}
    assert {"draft_created", "draft_decided"} <= kinds


def test_admin_key_alone_is_401(ab, monkeypatch):
    _, _, client = ab
    monkeypatch.setattr(settings, "admin_api_key", "adm")
    assert client.get("/drafts", headers={"X-Admin-Key": "adm"}).status_code == 401
    assert client.get("/drafts").status_code == 401
