from fastapi.testclient import TestClient

from .config import settings
from .main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"ok": True}


def test_chat_rejects_empty(monkeypatch):
    monkeypatch.setattr(settings, "public_demo_tenant_id", settings.default_tenant_id)  # keyless /chat needs the demo tenant
    assert TestClient(app).post("/chat", json={"message": ""}).status_code == 422


def test_bootstrap_is_a_noop_on_an_initialised_database():
    from . import bootstrap
    assert bootstrap.bootstrap_schema() is False  # tables already exist: nothing is run


def test_showcase_short_link_redirects_to_the_video_page():
    from fastapi.testclient import TestClient
    from .main import app
    r = TestClient(app).get("/showcase", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/showcase.html"
