import base64

import httpx
from fastapi.testclient import TestClient

from . import ratelimit, stt
from .config import settings
from .main import app

AUDIO = b"\x1aE\xdf\xa3" + b"\x00" * 200


def _gemini(monkeypatch, text="I need a roof repair", status=200):
    body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    seen = {}

    def post(url, **kw):
        seen.update(kw)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(stt.httpx, "post", post)
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    ratelimit._hits.clear()
    return seen


def _post(client, data=AUDIO, mime="audio/webm;codecs=opus"):
    return client.post("/transcribe", content=data, headers={"content-type": mime})


def test_transcribe_returns_the_words(monkeypatch):
    seen = _gemini(monkeypatch)
    r = _post(TestClient(app))
    assert r.status_code == 200 and r.json() == {"text": "I need a roof repair"}
    part = seen["json"]["contents"][0]["parts"][1]["inlineData"]
    assert part["mimeType"] == "audio/webm" and base64.b64decode(part["data"]) == AUDIO


def test_silence_comes_back_empty(monkeypatch):
    _gemini(monkeypatch, text="NONE")
    assert _post(TestClient(app)).json() == {"text": ""}


def test_rejects_non_audio_oversize_and_empty(monkeypatch):
    _gemini(monkeypatch)
    client = TestClient(app)
    assert _post(client, mime="text/plain").status_code == 415
    assert _post(client, data=b"x" * (stt.MAX_BYTES + 1)).status_code == 413
    assert _post(client, data=b"").status_code == 400


def test_unavailable_without_key_and_clean_on_provider_error(monkeypatch):
    _gemini(monkeypatch, status=429)
    client = TestClient(app)
    assert _post(client).status_code == 502
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert _post(client).status_code == 503


def test_transcribe_is_rate_limited(monkeypatch):
    _gemini(monkeypatch)
    client = TestClient(app)
    codes = [_post(client).status_code for _ in range(stt.PER_MINUTE + 1)]
    assert codes[-1] == 429
