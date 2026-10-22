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


def test_chat_says_when_the_conversation_has_ended(monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_per_min", 1000)
    out = TestClient(app).post("/chat", json={"message": "let me speak to a real person"}).json()
    assert out["closed"] is True  # handed to a human: the page should stop taking messages


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


def test_faq_lookup_falls_back_to_keywords_when_embeddings_are_down(monkeypatch):
    import httpx
    import openai

    from . import llm, tools

    def down(_):
        raise openai.APIConnectionError(request=httpx.Request("POST", "http://ollama"))

    monkeypatch.setattr(llm, "embed", down)
    assert tools.lookup_faq("how long does a roof inspection take")["chunks"]
    assert tools.lookup_faq("zzzz qqqq")["chunks"] == []
