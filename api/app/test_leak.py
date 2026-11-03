"""SEC-04: two tenants on the RLS-enabled DB; nothing leaks over HTTP, tools, or raw app_rw connections.
Catalog checks (FORCE, no defaults, app_rw role shape) live in test_rls_proof.py; fixtures patterned on test_isolation/test_routes_scope."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import agent, auth, db, faq, llm, tools
from .config import settings
from .main import app
from .test_isolation import _hash_vec

ADMIN = {"X-Admin-Key": "adm"}
MSG = {"message": "let me speak to a real person"}
TABLES = ("leads", "conversations", "messages", "slots", "appointments", "faq_chunks",
          "tool_calls", "escalations", "events", "llm_calls", "agent_events")


def _mk(tag: str) -> dict:
    tid = str(uuid.uuid4())
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:i, :s, :s, 'UTC', 'summit-roofing')"),
                  {"i": tid, "s": f"test-leak-{tag}-{tid[:8]}"})
    faq.seed_faq(tid, reload=True)
    tools.ensure_slots(tid)
    token = f"zq{tag}{tid[:6]}"  # unique FAQ token
    with db.system() as c:
        lead = c.execute(text("INSERT INTO leads (name, email, tenant_id) VALUES (:n, 'x@example.com', :t) RETURNING id"),
                         {"n": f"Lead{tag}", "t": tid}).scalar_one()
        cid = c.execute(text("INSERT INTO conversations (lead_id, state, outcome, channel, tenant_id) "
                             "VALUES (:l, 'NURTURE', 'nurture', 'web', :t) RETURNING id"), {"l": lead, "t": tid}).scalar_one()
        c.execute(text("INSERT INTO messages (conversation_id, role, content, tenant_id) VALUES (:c, 'user', 'hi', :t)"), {"c": cid, "t": tid})
        esc = c.execute(text("INSERT INTO escalations (conversation_id, reason, tenant_id) VALUES (:c, 'angry', :t) RETURNING id"),
                        {"c": cid, "t": tid}).scalar_one()
        c.execute(text("INSERT INTO faq_chunks (tenant_id, source, text, embedding) VALUES (:t, 'leak', :x,CAST(:v AS vector))"),
                  {"t": tid, "x": f"fact {token}", "v": faq.vector_literal(_hash_vec(f"fact {token}"))})
    return {"id": tid, "lead": lead, "convo": cid, "esc": esc, "token": token,
            "h": {"X-API-Key": auth.issue_key(tid)["key"]}}


@pytest.fixture
def ab(monkeypatch):
    monkeypatch.setattr(llm, "embed", _hash_vec)
    monkeypatch.setattr(agent.mailer, "send", lambda *a, **k: None)
    monkeypatch.setattr(settings, "admin_api_key", "adm")
    monkeypatch.setattr(settings, "public_demo_tenant_id", "")
    monkeypatch.setattr(settings, "chat_rate_per_min", 1000)
    monkeypatch.setattr(settings, "escalation_webhook_url", "")
    return _mk("a"), _mk("b"), TestClient(app)


def _ids(client, path, headers, key="id"):
    r = client.get(path, headers=headers)
    assert r.status_code == 200, (path, r.status_code)
    return {x[key] for x in r.json()}


@pytest.mark.parametrize("own,other", [(0, 1), (1, 0)])
def test_lists_return_only_own_rows(ab, own, other):
    t = (ab[0], ab[1])
    client, me, them = ab[2], t[own], t[other]
    assert _ids(client, "/leads", me["h"]) == {me["lead"]}
    assert _ids(client, "/conversations", me["h"]) == {me["convo"]}
    assert _ids(client, "/admin/escalations", me["h"]) == {me["esc"]}
    assert _ids(client, "/admin/followups/due?hours=0", me["h"], "conversation_id") == {me["convo"]}
    assert client.get(f"/leads/{them['lead']}", headers=me["h"]).status_code == 404
    assert client.get(f"/conversations/{them['convo']}", headers=me["h"]).status_code == 404


def test_metrics_tenant_scoped_admin_cross_tenant(ab):
    a, b, client = ab
    m = client.get("/metrics", headers=a["h"]).json()
    assert m["conversations"] == 1 and m["funnel"]["leads"] == 1
    assert "outreach" not in m and m["eval_runs"] == []
    admin = client.get("/leads?limit=1000", headers=ADMIN).json()
    assert {a["lead"], b["lead"]} <= {x["id"] for x in admin}  # super-admin sees both
    assert "outreach" in client.get("/metrics", headers=ADMIN).json()


def test_chat_lands_in_credential_tenant_and_ignores_body_and_header(ab):
    a, b, client = ab
    r = client.post("/chat", json={**MSG, "tenant_id": b["id"]}, headers={**a["h"], "X-Tenant-Id": b["id"]})
    assert r.status_code == 200
    with db.system() as c:
        owner = str(c.execute(text("SELECT tenant_id FROM conversations WHERE id=:i"), {"i": r.json()["conversation_id"]}).scalar())
    assert owner == a["id"]


def test_chat_cannot_continue_other_tenants_conversation(ab):
    a, b, client = ab
    first = client.post("/chat", json=MSG, headers=a["h"]).json()
    r = client.post("/chat", json={"message": "hi", "conversation_id": first["conversation_id"],
                                   "conversation_token": first["conversation_token"]}, headers=b["h"])
    assert r.status_code == 404


def test_bad_credentials_all_401(ab):
    a, _, client = ab
    assert client.post("/chat", json=MSG).status_code == 401
    assert client.post("/chat", json=MSG, headers={"X-API-Key": "rd_live_wrong"}).status_code == 401
    old = a["h"]["X-API-Key"]
    with db.system() as c:
        kid = c.execute(text("SELECT id FROM tenant_api_keys WHERE tenant_id=:t"), {"t": a["id"]}).scalar_one()
    new = auth.rotate_key(a["id"], kid)["key"]
    assert client.post("/chat", json=MSG, headers={"X-API-Key": old}).status_code == 401  # rotated-out
    assert client.post("/chat", json=MSG, headers={"X-API-Key": new}).status_code == 200
    kid2 = auth.list_keys(a["id"])[-1]["id"]
    auth.revoke_key(a["id"], kid2)
    assert client.post("/chat", json=MSG, headers={"X-API-Key": new}).status_code == 401  # revoked


@pytest.mark.parametrize("method,path", [("get", "/admin/tenants"), ("post", "/admin/tenants"),
                                          ("get", "/admin/tenants/{t}/keys"), ("post", "/admin/tenants/{t}/keys"),
                                          ("get", "/admin/campaigns"), ("post", "/triage")])
def test_tenant_key_rejected_on_admin_only_routes(ab, method, path):
    a, _, client = ab
    r = getattr(client, method)(path.format(t=a["id"]), headers=a["h"])
    assert r.status_code in (401, 403)


def test_lookup_faq_never_returns_other_tenants_chunks(ab):
    a, b, _ = ab
    got = tools.lookup_faq(f"fact {b['token']}", k=50, tenant_id=a["id"])["chunks"]
    assert got and not any(b["token"] in x for x in got)
    assert any(b["token"] in x for x in tools.lookup_faq(f"fact {b['token']}", k=50, tenant_id=b["id"])["chunks"])


def test_slots_and_booking_never_cross(ab):
    a, b, _ = ab
    with db.system() as c:
        own = {r[0] for r in c.execute(text("SELECT id FROM slots WHERE tenant_id=:t"), {"t": a["id"]})}
        slot_b = c.execute(text("SELECT id FROM slots WHERE tenant_id=:t AND NOT is_booked LIMIT 1"), {"t": b["id"]}).scalar_one()
        c.execute(text("UPDATE leads SET status='qualified' WHERE id=:i"), {"i": a["lead"]})
    got = tools.get_available_slots(limit=50, tenant_id=a["id"])
    assert {s["id"] for s in got["slots"]} <= own
    with pytest.raises(tools.ToolError):
        tools.book_appointment(a["lead"], slot_b, tenant_id=a["id"])


@pytest.mark.parametrize("table", TABLES)
def test_app_role_without_context_sees_zero_rows(ab, table):
    with db.app_engine.begin() as c:  # no set_config: RLS must fail closed
        assert c.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0


def test_app_role_insert_without_context_rejected(ab):
    with pytest.raises(DBAPIError, match="row-level security"):
        with db.app_engine.begin() as c:
            c.execute(text("INSERT INTO leads (tenant_id) VALUES (:t)"), {"t": ab[0]["id"]})


def test_rls_is_actually_enforced_on_app_engine():
    db.assert_rls_enforced()
