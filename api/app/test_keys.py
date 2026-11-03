"""SEC-01/SEC-05: per-tenant key lifecycle, scope dependencies and super-admin tenant/key endpoints."""
import hashlib
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import auth, db
from .config import settings
from .main import app

ADMIN = {"X-Admin-Key": "test-key"}
UNAUTH = {"detail": "unauthorized"}

probe = FastAPI()


@probe.get("/t")
def _t(t: str = Depends(auth.require_tenant)):
    return {"tenant": t}


@probe.get("/s")
def _s(s: auth.Scope = Depends(auth.require_scope)):
    return {"tenant": s.tenant_id, "admin": s.is_admin}


@probe.get("/c")
def _c(t: str = Depends(auth.chat_tenant)):
    return {"tenant": t}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-key")
    monkeypatch.setattr(settings, "public_demo_tenant_id", "")
    return TestClient(app)


@pytest.fixture
def pc(client):
    return TestClient(probe)


def _tenant() -> str:
    tid = str(uuid.uuid4())
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:i, :s, :s, 'UTC', 'summit-roofing')"),
                  {"i": tid, "s": f"test-keys-{tid[:8]}"})
    return tid


@pytest.fixture
def tid():
    return _tenant()


def _hashes(tenant):
    with db.system() as c:
        return [r[0] for r in c.execute(text("SELECT key_hash FROM tenant_api_keys WHERE tenant_id=:t"), {"t": tenant})]


def test_issue_key_stores_only_sha256(tid):
    k = auth.issue_key(tid, "ci")
    assert k["key"].startswith("rd_live_") and k["label"] == "ci"
    assert _hashes(tid) == [hashlib.sha256(k["key"].encode()).hexdigest()]
    with db.system() as c:
        assert c.execute(text("SELECT count(*) FROM tenant_api_keys WHERE label=:k OR key_hash=:k"), {"k": k["key"]}).scalar() == 0


def test_two_issues_differ(tid):
    assert auth.issue_key(tid)["key"] != auth.issue_key(tid)["key"]


def test_rotate_revokes_old_and_new_works(pc, tid):
    old = auth.issue_key(tid)
    new = auth.rotate_key(tid, old["id"])
    assert pc.get("/t", headers={"X-API-Key": new["key"]}).json() == {"tenant": tid}
    assert pc.get("/t", headers={"X-API-Key": old["key"]}).status_code == 401
    with pytest.raises(auth.HTTPException) as e:
        auth.rotate_key(tid, old["id"])
    assert e.value.status_code == 404


def test_revoke_then_401_and_wrong_tenant_404(pc, tid):
    k = auth.issue_key(tid)
    with pytest.raises(auth.HTTPException) as e:
        auth.revoke_key(_tenant(), k["id"])
    assert e.value.status_code == 404
    auth.revoke_key(tid, k["id"])
    assert pc.get("/t", headers={"X-API-Key": k["key"]}).status_code == 401
    with pytest.raises(auth.HTTPException):
        auth.revoke_key(tid, k["id"])


def test_require_tenant_failures_are_identical(pc, tid):
    k = auth.issue_key(tid)
    auth.revoke_key(tid, k["id"])
    live = auth.issue_key(tid)["key"]
    bad = [{}, {"X-API-Key": "rd_live_nope"}, {"X-API-Key": k["key"]}, {"X-API-Key": live[len("rd_live_"):]},
           {"X-API-Key": "rd_live_" + "a" * 200}]
    for h in bad:
        r = pc.get("/t", headers=h)
        assert (r.status_code, r.json()) == (401, UNAUTH), h
    assert pc.get("/t", headers={"X-API-Key": live}).json() == {"tenant": tid}


def test_scope_admin_bad_tenant_header_is_400(pc):
    assert pc.get("/s", headers={**ADMIN, "X-Tenant-Id": "not-a-uuid"}).status_code == 400


def test_scope_tenant_key_ignores_tenant_header(pc, tid):
    k = auth.issue_key(tid)["key"]
    r = pc.get("/s", headers={"X-API-Key": k, "X-Tenant-Id": str(uuid.uuid4())})
    assert r.json() == {"tenant": tid, "admin": False}
    assert pc.get("/s", headers={"X-API-Key": k, "X-Tenant-Id": "garbage"}).status_code == 200


def test_scope_admin_none_or_header(pc):
    assert pc.get("/s", headers=ADMIN).json() == {"tenant": None, "admin": True}
    t = str(uuid.uuid4())
    assert pc.get("/s", headers={**ADMIN, "X-Tenant-Id": t}).json() == {"tenant": t, "admin": True}


def test_scope_invalid_key_never_falls_through_to_admin(pc):
    r = pc.get("/s", headers={**ADMIN, "X-API-Key": "rd_live_bogus"})
    assert (r.status_code, r.json()) == (401, UNAUTH)


def test_scope_no_credentials_is_403(pc):
    assert pc.get("/s").status_code == 403
    assert pc.get("/s", headers={"X-Admin-Key": "wrong"}).status_code == 403


def test_chat_tenant_unset_is_401(pc):
    assert pc.get("/c").status_code == 401


def test_chat_tenant_demo_fallback_and_invalid_key(pc, tid, monkeypatch):
    monkeypatch.setattr(settings, "public_demo_tenant_id", tid)
    assert pc.get("/c").json() == {"tenant": tid}
    assert pc.get("/c", headers={"X-API-Key": "rd_live_bogus"}).status_code == 401
    monkeypatch.setattr(settings, "public_demo_tenant_id", "not-a-uuid")
    assert pc.get("/c").status_code == 401


def test_chat_tenant_valid_key_beats_demo(pc, tid, monkeypatch):
    monkeypatch.setattr(settings, "public_demo_tenant_id", str(uuid.uuid4()))
    assert pc.get("/c", headers={"X-API-Key": auth.issue_key(tid)["key"]}).json() == {"tenant": tid}


def test_http_nonexistent_tenant_is_404(client):
    ghost, base = str(uuid.uuid4()), None
    base = f"/admin/tenants/{ghost}/keys"
    assert client.post(base, headers=ADMIN).status_code == 404
    assert client.get(base, headers=ADMIN).status_code == 404
    assert client.post(f"{base}/1/rotate", headers=ADMIN).status_code == 404
    assert client.post(f"{base}/1/revoke", headers=ADMIN).status_code == 404
    assert client.post("/admin/tenants/nope/keys", headers=ADMIN).status_code == 400


def test_http_issue_list_rotate_revoke(client, pc, tid):
    r = client.post(f"/admin/tenants/{tid}/keys", json={"label": "n8n"}, headers=ADMIN)
    assert r.status_code == 200 and set(r.json()) == {"id", "key", "label"}
    k = r.json()
    ls = client.get(f"/admin/tenants/{tid}/keys", headers=ADMIN).json()
    assert [set(x) for x in ls] == [{"id", "label", "created_at", "revoked_at"}]
    assert k["key"] not in str(ls)
    n = client.post(f"/admin/tenants/{tid}/keys/{k['id']}/rotate", headers=ADMIN)
    assert n.status_code == 200 and n.json()["key"] != k["key"]
    assert pc.get("/t", headers={"X-API-Key": k["key"]}).status_code == 401
    assert client.post(f"/admin/tenants/{tid}/keys/{n.json()['id']}/revoke", headers=ADMIN).status_code == 200
    assert pc.get("/t", headers={"X-API-Key": n.json()["key"]}).status_code == 401
    assert client.post(f"/admin/tenants/{tid}/keys/{n.json()['id']}/revoke", headers=ADMIN).status_code == 404


def test_http_key_and_tenant_endpoints_reject_tenant_key(client, tid):
    h = {"X-API-Key": auth.issue_key(tid)["key"]}
    for method, path in (("post", f"/admin/tenants/{tid}/keys"), ("get", f"/admin/tenants/{tid}/keys"),
                         ("post", f"/admin/tenants/{tid}/keys/1/rotate"), ("post", f"/admin/tenants/{tid}/keys/1/revoke"),
                         ("get", "/admin/tenants"), ("post", "/admin/tenants")):
        assert getattr(client, method)(path, headers=h).status_code in (401, 403), path


def test_http_list_tenants(client, tid):
    rows = client.get("/admin/tenants", headers=ADMIN).json()
    mine = [r for r in rows if r["id"] == tid]
    assert mine and set(mine[0]) == {"id", "slug", "name", "timezone", "pack_slug"}
