"""SEC-02/SEC-05 at route level: tenant comes from the credential; tenant keys see only their rows."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import auth, db
from .config import settings
from .main import app

ADMIN = {"X-Admin-Key": "test-key"}
ESCALATE = {"message": "let me speak to a real person"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-key")
    monkeypatch.setattr(settings, "public_demo_tenant_id", "")
    monkeypatch.setattr(settings, "chat_rate_per_min", 1000)
    monkeypatch.setattr(settings, "escalation_webhook_url", "")
    return TestClient(app)


def _tenant() -> str:
    tid = str(uuid.uuid4())
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:i, :s, :s, 'UTC', 'summit-roofing')"),
                  {"i": tid, "s": f"test-scope-{tid[:8]}"})
    return tid


def _seed(tid: str, n: int, state: str = "NURTURE") -> dict:
    """n conversations (each with a lead and an escalation) in tenant tid."""
    out = {"leads": [], "convos": [], "escs": []}
    with db.system() as c:
        for i in range(n):
            lead = c.execute(text("INSERT INTO leads (name, email, tenant_id) VALUES (:n, 's@example.com', :t) RETURNING id"),
                             {"n": f"L{tid[:4]}{i}", "t": tid}).scalar_one()
            cid = c.execute(text("INSERT INTO conversations (lead_id, state, outcome, channel, tenant_id) "
                                 "VALUES (:l, :s, 'nurture', 'web', :t) RETURNING id"), {"l": lead, "s": state, "t": tid}).scalar_one()
            c.execute(text("INSERT INTO messages (conversation_id, role, content, tenant_id) VALUES (:c, 'user', 'hi', :t)"), {"c": cid, "t": tid})
            eid = c.execute(text("INSERT INTO escalations (conversation_id, reason, tenant_id) VALUES (:c, 'angry', :t) RETURNING id"),
                            {"c": cid, "t": tid}).scalar_one()
            out["leads"].append(lead), out["convos"].append(cid), out["escs"].append(eid)
    return out


@pytest.fixture
def two():
    a, b = _tenant(), _tenant()
    return {"a": a, "b": b, "ka": {"X-API-Key": auth.issue_key(a)["key"]}, "kb": {"X-API-Key": auth.issue_key(b)["key"]},
            "da": _seed(a, 2), "db": _seed(b, 1)}


def _tenant_of(table: str, rid: int) -> str:
    with db.system() as c:
        return str(c.execute(text(f"SELECT tenant_id FROM {table} WHERE id=:i"), {"i": rid}).scalar())


# ---- /chat ----

def test_chat_no_key_is_401_without_demo(client):
    assert client.post("/chat", json=ESCALATE).status_code == 401


def test_chat_invalid_key_is_401(client):
    assert client.post("/chat", json=ESCALATE, headers={"X-API-Key": "rd_live_nope"}).status_code == 401


def test_chat_revoked_key_is_401(client, two):
    kid = auth.list_keys(two["a"])[0]["id"]
    auth.revoke_key(two["a"], kid)
    assert client.post("/chat", json=ESCALATE, headers=two["ka"]).status_code == 401


def test_chat_keyless_works_when_demo_set(client, monkeypatch, two):
    monkeypatch.setattr(settings, "public_demo_tenant_id", two["a"])
    r = client.post("/chat", json=ESCALATE)
    assert r.status_code == 200 and _tenant_of("conversations", r.json()["conversation_id"]) == two["a"]


def test_chat_invalid_key_never_falls_to_demo(client, monkeypatch, two):
    monkeypatch.setattr(settings, "public_demo_tenant_id", two["a"])
    assert client.post("/chat", json=ESCALATE, headers={"X-API-Key": "rd_live_nope"}).status_code == 401


def test_chat_body_tenant_id_ignored(client, two):
    r = client.post("/chat", json={**ESCALATE, "tenant_id": two["b"]}, headers=two["ka"])
    assert r.status_code == 200 and _tenant_of("conversations", r.json()["conversation_id"]) == two["a"]


def test_chat_x_tenant_header_ignored(client, two):
    r = client.post("/chat", json=ESCALATE, headers={**two["ka"], "X-Tenant-Id": two["b"]})
    assert r.status_code == 200 and _tenant_of("conversations", r.json()["conversation_id"]) == two["a"]


def test_chat_cross_tenant_conversation_is_404(client, two):
    first = client.post("/chat", json=ESCALATE, headers=two["ka"]).json()
    r = client.post("/chat", json={"message": "hi", "conversation_id": first["conversation_id"],
                                   "conversation_token": first["conversation_token"]}, headers=two["kb"])
    assert r.status_code == 404


# ---- read routes ----

def test_leads_scoped_to_tenant_key(client, two):
    ids = {r["id"] for r in client.get("/leads", headers=two["ka"]).json()}
    assert ids == set(two["da"]["leads"])
    assert client.get(f"/leads/{two['db']['leads'][0]}", headers=two["ka"]).status_code == 404
    assert client.get(f"/leads/{two['da']['leads'][0]}", headers=two["ka"]).status_code == 200


def test_conversations_scoped_to_tenant_key(client, two):
    ids = {r["id"] for r in client.get("/conversations", headers=two["ka"]).json()}
    assert ids == set(two["da"]["convos"])
    assert client.get(f"/conversations/{two['db']['convos'][0]}", headers=two["ka"]).status_code == 404
    assert client.get(f"/conversations/{two['da']['convos'][0]}", headers=two["ka"]).status_code == 200


def test_escalations_scoped_to_tenant_key(client, two):
    ids = {r["id"] for r in client.get("/admin/escalations", headers=two["ka"]).json()}
    assert ids == set(two["da"]["escs"])


def test_followups_due_scoped_to_tenant_key(client, two):
    ids = {r["conversation_id"] for r in client.get("/admin/followups/due?hours=0", headers=two["ka"]).json()}
    assert ids == set(two["da"]["convos"])


def test_metrics_tenant_key_counts_and_no_global_sections(client, two):
    m = client.get("/metrics", headers=two["ka"])
    assert m.status_code == 200
    body = m.json()
    assert body["conversations"] == 2 and body["funnel"]["leads"] == 2
    assert "outreach" not in body and body["eval_runs"] == []
    assert client.get("/metrics", headers=two["kb"]).json()["conversations"] == 1


def test_admin_key_without_header_is_cross_tenant(client, two):
    ids = {r["id"] for r in client.get("/leads?limit=500", headers=ADMIN).json()}
    assert set(two["da"]["leads"]) | set(two["db"]["leads"]) <= ids
    assert "outreach" in client.get("/metrics", headers=ADMIN).json()


def test_read_routes_reject_no_credentials(client):
    assert client.get("/leads").status_code == 403
    assert client.get("/leads", headers={"X-API-Key": "rd_live_nope"}).status_code == 401


# ---- write routes ----

def test_resolve_escalation_by_header_tenant(client, two):
    eid = two["db"]["escs"][0]
    r = client.post(f"/admin/escalations/{eid}/resolve", headers={**ADMIN, "X-Tenant-Id": two["b"]})
    assert r.status_code == 200
    assert client.post(f"/admin/escalations/{eid}/resolve", headers={**ADMIN, "X-Tenant-Id": two["a"]}).status_code == 404


def test_resolve_escalation_tenant_key_own_only(client, two):
    assert client.post(f"/admin/escalations/{two['db']['escs'][0]}/resolve", headers=two["ka"]).status_code == 404
    assert client.post(f"/admin/escalations/{two['da']['escs'][0]}/resolve", headers={**two["ka"], "X-Tenant-Id": two["b"]}).status_code == 200


def test_inbound_lands_in_header_tenant(client, two):
    r = client.post("/webhooks/inbound", json={"contact_id": "sc-1", "message": ESCALATE["message"], "message_id": "m1"},
                    headers={**ADMIN, "X-Tenant-Id": two["b"]})
    assert r.status_code == 200 and _tenant_of("conversations", r.json()["conversation_id"]) == two["b"]
    dup = client.post("/webhooks/inbound", json={"contact_id": "sc-1", "message": "again", "message_id": "m1"},
                      headers={**ADMIN, "X-Tenant-Id": two["b"]})
    assert dup.json().get("duplicate") is True


def test_inbound_with_tenant_key_ignores_header(client, two):
    r = client.post("/webhooks/inbound", json={"contact_id": "sc-2", "message": ESCALATE["message"]},
                    headers={**two["ka"], "X-Tenant-Id": two["b"]})
    assert r.status_code == 200 and _tenant_of("conversations", r.json()["conversation_id"]) == two["a"]


def test_inbound_admin_without_header_is_400(client):
    with db.system() as c:
        before = c.execute(text("SELECT count(*) FROM conversations")).scalar_one()
    r = client.post("/webhooks/inbound", json={"contact_id": "sc-3", "message": ESCALATE["message"]}, headers=ADMIN)
    assert r.status_code == 400 and r.json()["detail"] == "tenant required: send X-API-Key, or X-Admin-Key with X-Tenant-Id"
    with db.system() as c:
        assert c.execute(text("SELECT count(*) FROM conversations")).scalar_one() == before


def test_followup_draft_by_header_tenant(client, two):
    cid = two["db"]["convos"][0]
    assert client.post(f"/admin/followups/{cid}/draft", headers={**ADMIN, "X-Tenant-Id": two["a"]}).status_code == 409
    r = client.post(f"/admin/followups/{cid}/draft", headers={**ADMIN, "X-Tenant-Id": two["b"]})
    assert r.status_code == 200 and r.json()["followup_number"] == 1


def test_followup_draft_tenant_key(client, two):
    assert client.post(f"/admin/followups/{two['db']['convos'][0]}/draft", headers=two["ka"]).status_code == 409
    assert client.post(f"/admin/followups/{two['da']['convos'][0]}/draft", headers=two["ka"]).status_code == 200
