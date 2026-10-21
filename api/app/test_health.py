from fastapi.testclient import TestClient

from .main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"ok": True}


def test_chat_rejects_empty():
    assert TestClient(app).post("/chat", json={"message": ""}).status_code == 422


def test_bootstrap_is_a_noop_on_an_initialised_database():
    from . import bootstrap
    assert bootstrap.bootstrap_schema() is False  # tables already exist: nothing is run


def test_showcase_short_link_redirects_to_the_video_page():
    from fastapi.testclient import TestClient
    from .main import app
    r = TestClient(app).get("/showcase", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/showcase.html"
