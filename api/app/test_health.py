from fastapi.testclient import TestClient

from .main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"ok": True}


def test_chat_rejects_empty():
    assert TestClient(app).post("/chat", json={"message": ""}).status_code == 422
