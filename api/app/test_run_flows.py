"""WF-04: the platform completes its flows through the API and mailer with n8n absent (scripts/run_flows.py)."""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from scripts import run_flows

from . import agent, auth, brief_routes, db, llm, tools
from .config import settings
from .main import app

ADMIN = "test-key"
NOW = datetime(2026, 7, 1, 5, 0, tzinfo=timezone.utc)  # 07:00 in Zurich
MSG = "I own 1 A St, Denver and need a repair within 1 month. Sam, 303-555-0142, sam@example.test"
FULL = {"reply": "ok", "extracted": {"service_type": "repair", "is_owner": True, "address": "1 A St, Denver",
                                      "timeline_months": 1, "name": "Sam", "phone": "303-555-0142",
                                      "email": "sam@example.test"}}


class Rec:
    """TestClient wrapper that records (method, path, header names) of every call."""
    def __init__(self):
        self.c, self.calls = TestClient(app), []

    def _do(self, verb, path, **kw):
        self.calls.append((verb, path.split("?")[0], set(kw.get("headers", {}))))
        return getattr(self.c, verb)(path, **kw)

    def get(self, path, **kw): return self._do("get", path, **kw)
    def post(self, path, **kw): return self._do("post", path, **kw)


@pytest.fixture
def env(monkeypatch, roofing_tenant, venue_tenant):
    sent = []
    monkeypatch.setattr(settings, "admin_api_key", ADMIN)
    monkeypatch.setattr(settings, "escalation_webhook_url", "")  # n8n absent
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")
    monkeypatch.setattr(tools.mailer, "send", lambda to, subject, body, html=None: sent.append((to, subject, body)))
    monkeypatch.setattr(tools.llm, "embed", lambda q: [1.0] + [0.0] * 383)
    monkeypatch.setattr(brief_routes, "utcnow", lambda: NOW)
    keys = {t: auth.issue_key(t, "test-run-flows")["key"] for t in (roofing_tenant, venue_tenant)}
    with db.system() as c:
        c.execute(text("DELETE FROM brief_runs WHERE tenant_id=:t"), {"t": venue_tenant})
        c.execute(text("DELETE FROM drafts WHERE tenant_id=:t"), {"t": venue_tenant})
    tools.ensure_slots(roofing_tenant)
    yield sent, keys, Rec(), roofing_tenant, venue_tenant
    with db.system() as c:
        c.execute(text("UPDATE slots SET is_booked=false WHERE tenant_id=:t"), {"t": roofing_tenant})
        c.execute(text("DELETE FROM brief_runs WHERE tenant_id=:t"), {"t": venue_tenant})
        c.execute(text("DELETE FROM drafts WHERE tenant_id=:t"), {"t": venue_tenant})
        c.execute(text("DELETE FROM capacity_flags WHERE tenant_id=:t"), {"t": venue_tenant})
        c.execute(text("DELETE FROM tenant_api_keys WHERE label='test-run-flows'"))


def script(monkeypatch, *turns):
    it = iter(turns)
    monkeypatch.setattr(llm, "chat", lambda m: {"content": json.dumps(next(it)), "model": "fake", "prompt_tokens": 1,
                                                "completion_tokens": 1, "latency_ms": 1})


def test_booking_and_confirmation_mail(env, monkeypatch):
    sent, keys, cl, roof, _ = env
    script(monkeypatch, FULL, {"reply": "ok"})
    run_flows.inbound(cl, keys, lambda *a: sent.append(a), roof, "rf-book-1", MSG)
    d = run_flows.inbound(cl, keys, lambda *a: sent.append(a), roof, "rf-book-1", "the first")
    assert (d["state"], d["outcome"]) == ("DONE", "booked")
    with db.tx(roof) as c:
        assert c.execute(text("SELECT count(*) FROM appointments")).scalar() >= 1
    assert [m[0] for m in sent if m[1] == "Your appointment is booked"] == ["sam@example.test"]


def test_escalation_mails_owner_without_n8n(env):
    sent, keys, cl, roof, _ = env
    agent.handle_turn("let me speak to a real person", tenant_id=roof)  # web chat: API fallback mail
    assert [m[0] for m in sent] == ["owner@example.test"]
    sent.clear()
    d = run_flows.inbound(cl, keys, lambda *a: sent.append(a), roof, "rf-esc-1", "let me speak to a real person")
    assert d["outcome"] == "escalated"
    assert [m[0] for m in sent] == ["owner@example.test"] and sent[0][1].startswith("Escalation (")


def test_escalation_with_dead_webhook_still_mails(env, monkeypatch):
    sent, _, _, roof, _ = env
    monkeypatch.setattr(settings, "escalation_webhook_url", "http://127.0.0.1:9/hook")  # closed port
    agent.handle_turn("let me speak to a real person", tenant_id=roof)
    assert [m[0] for m in sent] == ["owner@example.test"]


def test_followup_once_then_nothing(env):
    sent, keys, cl, roof, _ = env
    with db.system() as c:
        lead = c.execute(text("INSERT INTO leads (name, email, tenant_id) VALUES ('Pat', 'pat@example.test', :t) RETURNING id"), {"t": roof}).scalar_one()
        cid = c.execute(text("INSERT INTO conversations (lead_id, state, outcome, channel, tenant_id) "
                             "VALUES (:l, 'NURTURE', 'nurture', 'eval', :t) RETURNING id"), {"l": lead, "t": roof}).scalar_one()
        c.execute(text("INSERT INTO messages (conversation_id, role, content, tenant_id, created_at) "
                       "VALUES (:c, 'user', 'later', :t, now() - interval '72 hours')"), {"c": cid, "t": roof})
    assert run_flows.followups(cl, ADMIN, keys, lambda *a: sent.append(a)) == 1
    assert [m[0] for m in sent] == ["pat@example.test"]
    with db.tx(roof) as c:
        assert c.execute(text("SELECT followup_count FROM conversations WHERE id=:i"), {"i": cid}).scalar() == 1
    assert run_flows.followups(cl, ADMIN, keys, lambda *a: sent.append(a)) == 0
    assert len(sent) == 1


def test_daily_brief_once(env):
    sent, keys, cl, _, venue = env
    mail = lambda *a: sent.append(a)  # noqa: E731
    assert run_flows.daily_brief(cl, ADMIN, keys, mail) == 1
    assert len(sent) == 1 and sent[0][1].startswith("Daily brief 2026-07-01")
    assert run_flows.daily_brief(cl, ADMIN, keys, mail) == 0
    assert len(sent) == 1


def _draft(tenant, kind, status, payload):
    with db.system() as c:
        return c.execute(text("INSERT INTO drafts (tenant_id, kind, status, payload, input_hash) VALUES (:t, :k, :s, CAST(:p AS jsonb), :h) RETURNING id"),
                         {"t": tenant, "k": kind, "s": status, "p": json.dumps(payload), "h": f"h{len(json.dumps(payload))}{status}"}).scalar_one()


def test_send_approved_mixed_items(env):
    sent, keys, cl, _, venue = env
    a = _draft(venue, "quote", "approved", {"contact_email": "c@example.test", "email_text": "Total CHF 315.00"})
    b = _draft(venue, "quote", "approved", {"email_text": "no address on file"})
    assert run_flows.send_approved(cl, keys, lambda *a_: sent.append(a_)) == 1
    assert [(m[0], m[2]) for m in sent] == [("c@example.test", "Total CHF 315.00")]
    st = {d["id"]: d["status"] for d in cl.get("/drafts", headers={"X-API-Key": keys[venue]}).json()}
    assert (st[a], st[b]) == ("sent", "approved")
    assert run_flows.send_approved(cl, keys, lambda *a_: sent.append(a_)) == 0


def test_capacity_nightly(env):
    sent, keys, cl, _, _ = env
    n = run_flows.capacity_nightly(cl, ADMIN, keys, lambda *a: sent.append(a))
    assert n == len(sent)
    again = run_flows.capacity_nightly(cl, ADMIN, keys, lambda *a: sent.append(a))
    assert again == 0  # unchanged flags are not re-mailed


def test_admin_key_only_on_tenant_list(env):
    sent, keys, cl, _, _ = env
    mail = lambda *a: sent.append(a)  # noqa: E731
    run_flows.followups(cl, ADMIN, keys, mail)
    run_flows.daily_brief(cl, ADMIN, keys, mail)
    run_flows.capacity_nightly(cl, ADMIN, keys, mail)
    run_flows.send_approved(cl, keys, mail)
    run_flows.inbound(cl, keys, mail, env[3], "rf-esc-2", "let me speak to a real person")
    admin_calls = {(v, p) for v, p, h in cl.calls if "X-Admin-Key" in h}
    assert admin_calls == {("get", "/admin/tenants")}
    assert all("X-API-Key" in h for v, p, h in cl.calls if p != "/admin/tenants")
