from fastapi.testclient import TestClient

from . import ratelimit
from .config import settings
from .main import app


def test_continuing_a_conversation_needs_its_token(monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_per_min", 1000)
    client = TestClient(app)
    first = client.post("/chat", json={"message": "let me speak to a real person"}).json()
    cid, token = first["conversation_id"], first["conversation_token"]
    assert len(token) >= 16
    assert client.post("/chat", json={"message": "hi", "conversation_id": cid}).status_code == 404
    assert client.post("/chat", json={"message": "hi", "conversation_id": cid, "conversation_token": "nope"}).status_code == 404
    ok = client.post("/chat", json={"message": "hi", "conversation_id": cid, "conversation_token": token})
    assert ok.status_code == 200 and ok.json()["conversation_id"] == cid


def test_rate_limit_window():
    assert [ratelimit.allow("k", 2, now=t) for t in (0, 1, 2)] == [True, True, False]
    assert ratelimit.allow("k", 2, now=61)  # window slid past the first hit


def test_chat_is_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_per_min", 2)
    ratelimit._hits.clear()
    client = TestClient(app)
    codes = [client.post("/chat", json={"message": "let me speak to a real person"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    ratelimit._hits.clear()
