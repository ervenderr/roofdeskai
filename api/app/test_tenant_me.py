"""08-01: owner resolver, GET /tenant/me, escalation mail fallback."""
import httpx
import pytest
from fastapi.testclient import TestClient

from . import agent, auth, mailer, tenants, tools
from .config import settings
from .main import app
from .pack import get_pack


@pytest.fixture
def client():
    return TestClient(app)


def hdr(tid):
    return {"X-API-Key": auth.issue_key(tid)["key"]}


def test_requires_key(client):
    assert client.get("/tenant/me").status_code == 401


def test_roofing_me_has_no_modules(client, roofing_tenant, venue_tenant, monkeypatch):
    monkeypatch.setattr(settings, "owner_email", "")
    j = client.get("/tenant/me", headers=hdr(roofing_tenant)).json()
    assert j["tenant_id"] == roofing_tenant and j["slug"] == "summit-roofing" and j["name"] == "Summit Roofing"
    assert j["enabled_modules"] == [] and j["owner_email"] is None
    assert {"timezone", "locale"} <= j.keys()
    other = client.get("/tenant/me", headers=hdr(venue_tenant)).json()
    assert other["slug"] == "demo-venue" and other["tenant_id"] != j["tenant_id"]


def test_venue_modules(client, venue_tenant):
    j = client.get("/tenant/me", headers=hdr(venue_tenant)).json()
    assert j["enabled_modules"] == ["services", "capacity", "connectors", "reviews", "intake"]


def test_owner_env_then_pack_override(client, venue_tenant, monkeypatch):
    monkeypatch.setattr(settings, "owner_email", "env@example.test")
    assert client.get("/tenant/me", headers=hdr(venue_tenant)).json()["owner_email"] == "env@example.test"
    pack = get_pack(venue_tenant)
    assert tenants.owner_email(pack) == "env@example.test"
    over = pack.model_copy(update={"meta": pack.meta.model_copy(update={"owner_email": "pack@example.test"})})
    assert tenants.owner_email(over) == "pack@example.test"
    monkeypatch.setattr(settings, "owner_email", "")
    assert tenants.owner_email(pack) is None


# ---- escalation fallback ----
@pytest.fixture
def mails(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, body, html=None: sent.append((to, subject, body)))
    return sent


def web_escalate(tid):
    cid, _ = agent.handle_turn("let me speak to a real person", tenant_id=tid)
    return cid


def test_unset_webhook_mails_owner(roofing_tenant, mails, monkeypatch):
    monkeypatch.setattr(settings, "escalation_webhook_url", "")
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")
    cid = web_escalate(roofing_tenant)
    assert len(mails) == 1 and mails[0][0] == "owner@example.test"
    assert f"/conversations/{cid}" in mails[0][2] and str(cid) in mails[0][1]
    assert "real person" not in mails[0][2]  # no transcript


def test_failing_webhook_falls_back(roofing_tenant, mails, monkeypatch):
    monkeypatch.setattr(settings, "escalation_webhook_url", "http://n8n.test/hook")
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")

    def boom(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(tools.httpx, "post", boom)
    web_escalate(roofing_tenant)
    assert len(mails) == 1


def test_webhook_success_carries_tenant_id_no_mail(roofing_tenant, mails, monkeypatch):
    monkeypatch.setattr(settings, "escalation_webhook_url", "http://n8n.test/hook")
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")
    posted = []

    def ok(url, **kw):
        posted.append(kw["json"])
        return httpx.Response(200, request=httpx.Request("POST", url))
    monkeypatch.setattr(tools.httpx, "post", ok)
    web_escalate(roofing_tenant)
    assert posted[0]["tenant_id"] == roofing_tenant and mails == []


def test_no_owner_logs_and_sends_nothing(roofing_tenant, mails, monkeypatch, caplog):
    monkeypatch.setattr(settings, "escalation_webhook_url", "")
    monkeypatch.setattr(settings, "owner_email", "")
    web_escalate(roofing_tenant)
    assert mails == [] and "no owner email" in caplog.text


def test_mail_error_is_swallowed(roofing_tenant, monkeypatch):
    monkeypatch.setattr(settings, "escalation_webhook_url", "")
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")

    def bad(*a, **k):
        raise mailer.MailError("x")
    monkeypatch.setattr(mailer, "send", bad)
    web_escalate(roofing_tenant)  # must not raise


def test_non_web_channel_returns_early(roofing_tenant, mails, monkeypatch):
    monkeypatch.setattr(settings, "escalation_webhook_url", "")
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")
    agent.handle_turn("let me speak to a real person", external_id="sms:me-test", channel="sms", tenant_id=roofing_tenant)
    assert mails == []
