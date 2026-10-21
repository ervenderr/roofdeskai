import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from .config import settings
from .db import engine
from .main import app

H = {"X-Admin-Key": "test-key"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-key")
    monkeypatch.setattr(settings, "escalation_webhook_url", "")
    return TestClient(app)


def test_admin_endpoints_need_the_key(client):
    for path in ("/leads", "/conversations", "/metrics", "/admin/escalations"):
        assert client.get(path).status_code == 403
        assert client.get(path, headers={"X-Admin-Key": "wrong"}).status_code == 403
        assert client.get(path, headers=H).status_code == 200


def test_admin_disabled_when_no_key_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "")
    assert client.get("/leads", headers={"X-Admin-Key": ""}).status_code == 403


def test_inbound_reuses_conversation_per_contact(client):
    body = {"contact_id": "c-1", "message": "I want to talk to a real person"}
    a = client.post("/webhooks/inbound", json=body, headers=H)
    assert a.status_code == 200 and "team member" in a.json()["reply"]
    assert (a.json()["state"], a.json()["outcome"], a.json()["escalation_reason"]) == ("ESCALATE", "escalated", "human_request")
    assert a.json()["link"].endswith(f"/conversations/{a.json()['conversation_id']}")
    b = client.post("/webhooks/inbound", json={**body, "message": "hello?"}, headers=H)
    assert b.json()["conversation_id"] == a.json()["conversation_id"]


def test_inbound_rejects_bad_payload(client):
    assert client.post("/webhooks/inbound", json={"contact_id": "", "message": "x"}, headers=H).status_code == 422


def _nurture_conversation() -> int:
    with engine.begin() as c:
        lead = c.execute(text("INSERT INTO leads (name, email) VALUES ('T', 't@example.com') RETURNING id")).scalar_one()
        return c.execute(text("INSERT INTO conversations (lead_id, state, outcome, channel) "
                              "VALUES (:l, 'NURTURE', 'nurture', 'eval') RETURNING id"), {"l": lead}).scalar_one()


def test_followups_stop_after_three(client):
    cid = _nurture_conversation()
    for n in (1, 2, 3):
        r = client.post(f"/admin/followups/{cid}/draft", headers=H)
        assert r.status_code == 200 and r.json()["followup_number"] == n
    assert client.post(f"/admin/followups/{cid}/draft", headers=H).status_code == 409


def test_followup_not_due_right_after_message(client):
    cid = _nurture_conversation()
    with engine.begin() as c:
        c.execute(text("INSERT INTO messages (conversation_id, role, content) VALUES (:c, 'user', 'later')"), {"c": cid})
    due = [d["conversation_id"] for d in client.get("/admin/followups/due", headers=H).json()]
    assert cid not in due
    due = [d["conversation_id"] for d in client.get("/admin/followups/due?hours=0", headers=H).json()]
    assert cid in due


def test_resolve_escalation(client):
    cid = _nurture_conversation()
    with engine.begin() as c:
        eid = c.execute(text("INSERT INTO escalations (conversation_id, reason) VALUES (:c, 'angry') RETURNING id"),
                        {"c": cid}).scalar_one()
    assert client.post(f"/admin/escalations/{eid}/resolve", headers=H).json() == {"id": eid, "resolved": True}
    assert client.post("/admin/escalations/999999/resolve", headers=H).status_code == 404


def test_metrics_shape(client):
    m = client.get("/metrics", headers=H).json()
    assert {"conversations", "outcomes", "funnel", "llm", "daily", "eval_runs", "escalation_rate"} <= m.keys()


def test_escalation_alert_only_fires_for_web_chat(client, monkeypatch):
    from . import agent, tools
    sent = []
    monkeypatch.setattr(settings, "escalation_webhook_url", "http://n8n.test/hook")
    monkeypatch.setattr(tools.httpx, "post", lambda url, **kw: sent.append(kw["json"]))
    web, _ = agent.handle_turn("let me speak to a real person")
    sms, _ = agent.handle_turn("let me speak to a real person", external_id="sms:alert-test", channel="sms")
    assert [s["conversation_id"] for s in sent] == [web]


def test_campaign_timezone_and_locale_are_validated(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "k")
    client, H2 = TestClient(app), {"X-Admin-Key": "k"}
    ok = client.post("/admin/campaigns", json={"name": "US", "timezone": "America/Chicago", "locale": "en-US"}, headers=H2)
    assert ok.status_code == 200
    assert client.post("/admin/campaigns", json={"name": "x", "timezone": "Mars/Base"}, headers=H2).status_code == 422
    assert client.post("/admin/campaigns", json={"name": "x", "locale": "fr-FR"}, headers=H2).status_code == 422
