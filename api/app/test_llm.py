import httpx
import pytest
from openai import RateLimitError

from . import llm
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
