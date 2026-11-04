import httpx
import pytest
from openai import BadRequestError, RateLimitError

from . import llm
from .config import settings
from .llm import Provider


def _rate_limit():
    req = httpx.Request("POST", "http://x")
    return RateLimitError("limit", response=httpx.Response(429, request=req), body=None)


def _fake(fail: set[str]):
    def call(p, messages):
        if p.name in fail:
            raise _rate_limit()
        return {"content": "ok", "model": p.name}
    return call


def test_fails_over_and_cools_down(monkeypatch):
    a, b = Provider("a", "u", "k", "m"), Provider("b", "u", "k", "m")
    monkeypatch.setattr(llm, "_call", _fake({"a"}))
    assert llm.chat([], [a, b])["model"] == "b"
    assert a.cooldown_until > 0
    monkeypatch.setattr(llm, "_call", _fake(set()))
    assert llm.chat([], [a, b])["model"] == "b"  # a still cooling down


def test_skips_keyless_and_raises_when_all_fail(monkeypatch):
    monkeypatch.setattr(llm, "_call", _fake({"a"}))
    with pytest.raises(RuntimeError):
        llm.chat([], [Provider("a", "u", "k", "m"), Provider("nokey", "u", "", "m")])


# --- optional anthropic provider: request shaping, strict rejection, pin ---

def _bad_request():
    req = httpx.Request("POST", "http://x")
    return BadRequestError("secret-body", response=httpx.Response(400, request=req), body=None)


class _FakeOpenAI:
    """Recorder standing in for openai.OpenAI; never touches the network."""
    calls: list[dict] = []

    def __init__(self, **kw):
        pass

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kw):
        _FakeOpenAI.calls.append(kw)
        msg = type("M", (), {"content": "ok"})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()


def test_temperature_sent_only_when_enabled(monkeypatch):
    monkeypatch.setattr(llm, "OpenAI", _FakeOpenAI)
    _FakeOpenAI.calls = []
    llm._call(Provider("a", "u", "k", "m"), [])
    llm._call(Provider("b", "u", "k", "m", send_temperature=False), [])
    assert _FakeOpenAI.calls[0]["temperature"] == 0
    assert "temperature" not in _FakeOpenAI.calls[1]
    for kw in _FakeOpenAI.calls:
        assert not {"response_format", "tool_choice", "n"} & kw.keys()


def test_strict_provider_400_raises_without_leaking(monkeypatch):
    def call(p, messages):
        raise _bad_request()
    monkeypatch.setattr(llm, "_call", call)
    a = Provider("a", "u", "sk-secret", "m", strict=True)
    with pytest.raises(llm.ProviderRejected) as ei:
        llm.chat([], [a, Provider("b", "u", "k", "m")])
    assert "a" in str(ei.value) and "400" in str(ei.value)
    assert "sk-secret" not in str(ei.value) and "secret-body" not in str(ei.value)
    assert a.cooldown_until == 0.0


def test_non_strict_400_falls_through(monkeypatch):
    def call(p, messages):
        if p.name == "a":
            raise _bad_request()
        return {"content": "ok", "model": p.name}
    monkeypatch.setattr(llm, "_call", call)
    a = Provider("a", "u", "k", "m")
    assert llm.chat([], [a, Provider("b", "u", "k", "m")])["model"] == "b"
    assert a.cooldown_until == 0.0


def test_pinned_uses_only_pin_and_resets(monkeypatch):
    a, b = Provider("a", "u", "k", "m"), Provider("b", "u", "k", "m")
    seen = []
    monkeypatch.setattr(llm, "PROVIDERS", [b])
    monkeypatch.setattr(llm, "_call", lambda p, m: seen.append(p.name) or {"content": "ok", "model": p.name})
    with llm.pinned([a]):
        llm.chat([])
    assert seen == ["a"]
    llm.chat([])
    assert seen == ["a", "b"]  # pin reset, default resolved at call time


def test_pinned_cooldown_never_falls_back(monkeypatch):
    a, b = Provider("a", "u", "k", "m"), Provider("b", "u", "k", "m")
    monkeypatch.setattr(llm, "PROVIDERS", [b])
    seen = []
    monkeypatch.setattr(llm, "_call", lambda p, m: seen.append(p.name) or (_ for _ in ()).throw(_rate_limit()))
    with llm.pinned([a]):
        with pytest.raises(RuntimeError):
            llm.chat([])
        with pytest.raises(RuntimeError):  # a is now cooling down
            llm.chat([])
    assert seen == ["a"]


def test_anthropic_is_last_strict_and_skipped_without_key():
    last = llm.PROVIDERS[-1]
    assert llm.PROVIDERS[0].name == "local"
    assert last.name == "anthropic" and last.strict and not last.send_temperature
    assert last.model == settings.anthropic_model
    assert last.api_key == settings.anthropic_api_key


def test_settings_repr_masks_anthropic_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-value")
    assert "sk-test-value" not in repr(settings)
