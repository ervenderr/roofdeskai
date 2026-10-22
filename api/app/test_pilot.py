from fastapi.testclient import TestClient
from sqlalchemy import text

from . import mailer, ratelimit, triage
from .config import settings
from .db import engine
from .main import app

GOOD = {"name": "Dana Cruz", "business": "Cruz Roofing", "email": "dana@pilot.test", "phone": "+1 512 555 0100", "message": "Interested"}


def _client(monkeypatch, sent=None):
    ratelimit._hits.clear()
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")
    monkeypatch.setattr(mailer, "send", lambda *a, **k: sent.append(a) if sent is not None else None)
    monkeypatch.setattr(triage.llm, "chat", lambda messages: {"content": '{"category": "pilot_interest", "confidence": 0.9, "draft": "Thanks, we will set up your pilot."}'})
    return TestClient(app)


def test_pilot_request_is_saved_as_interested_and_owner_is_emailed(monkeypatch):
    sent = []
    r = _client(monkeypatch, sent).post("/pilot-requests", json=GOOD)
    assert r.status_code == 200 and r.json() == {"ok": True}
    with engine.connect() as c:
        row = c.execute(text("SELECT name, status, phone FROM prospects WHERE email='dana@pilot.test' ORDER BY id DESC")).first()
    assert row == ("Cruz Roofing", "interested", "+1 512 555 0100")
    assert sent and sent[0][0] == "owner@example.test" and "Cruz Roofing" in sent[0][1]


def test_owner_email_carries_the_triage_and_a_draft_reply(monkeypatch):
    sent = []
    _client(monkeypatch, sent).post("/pilot-requests", json=GOOD)
    body = sent[0][2]
    assert "pilot_interest" in body and "Thanks, we will set up your pilot." in body


def test_pilot_request_still_works_when_triage_fails(monkeypatch):
    sent = []
    client = _client(monkeypatch, sent)

    def down(messages):
        raise RuntimeError("all LLM providers failed or are cooling down")

    monkeypatch.setattr(triage.llm, "chat", down)
    assert client.post("/pilot-requests", json=GOOD).json() == {"ok": True}
    assert sent and "Cruz Roofing" in sent[0][1] and "pilot_interest" not in sent[0][2]


def test_pilot_request_rejects_bad_input_and_bots(monkeypatch):
    client = _client(monkeypatch)
    assert client.post("/pilot-requests", json={**GOOD, "email": "nope"}).status_code == 422
    assert client.post("/pilot-requests", json={**GOOD, "name": ""}).status_code == 422
    assert client.post("/pilot-requests", json={**GOOD, "website": "http://spam"}).json() == {"ok": True}  # honeypot: pretend success
    with engine.connect() as c:
        assert not c.execute(text("SELECT 1 FROM prospects WHERE email='nope'")).first()


def test_pilot_requests_are_rate_limited(monkeypatch):
    client = _client(monkeypatch)
    codes = [client.post("/pilot-requests", json=GOOD).status_code for _ in range(6)]
    assert codes[-1] == 429
