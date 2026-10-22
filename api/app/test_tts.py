import base64
import io
import wave

import httpx
from fastapi.testclient import TestClient

from . import ratelimit, tts
from .config import settings
from .main import app

PCM = b"\x01\x00" * 2400  # 0.1 s of 24 kHz 16-bit mono


def _gemini(monkeypatch, status=200, data=PCM):
    body = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                                                                  "data": base64.b64encode(data).decode()}}]}}]}

    def post(url, **kw):
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(tts.httpx, "post", post)
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    ratelimit._hits.clear()


def test_speak_returns_a_playable_wav(monkeypatch):
    _gemini(monkeypatch)
    r = TestClient(app).post("/speak", json={"text": "You're booked."})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(r.content)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (24000, 1, 2, 2400)


def test_speak_fails_cleanly_when_the_provider_errors(monkeypatch):
    _gemini(monkeypatch, status=429)
    assert TestClient(app).post("/speak", json={"text": "hi"}).status_code == 502


def test_speak_is_unavailable_without_a_key(monkeypatch):
    _gemini(monkeypatch)
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert TestClient(app).post("/speak", json={"text": "hi"}).status_code == 503


def test_speak_limits_length_and_rate(monkeypatch):
    _gemini(monkeypatch)
    client = TestClient(app)
    assert client.post("/speak", json={"text": "x" * 601}).status_code == 422
    assert client.post("/speak", json={"text": ""}).status_code == 422
    codes = [client.post("/speak", json={"text": "hi"}).status_code for _ in range(tts.PER_MINUTE + 1)]
    assert codes[-1] == 429
