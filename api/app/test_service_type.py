"""service_type comes from the pack, with the old enum's invalid-output behaviour (retry once, then escalate)."""
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from . import agent, llm, policy
from .db import engine
from .pack import load_pack
from .schemas import LeadFields, Turn
from .test_agent import FULL, MSG, clean, script, state  # noqa: F401  (clean is an autouse fixture)

OLD_ENUM = ["repair", "replacement", "inspection", "other"]  # frozen copy of the old enum
CTX = {"service_types": OLD_ENUM}


def _turn(service, ctx=CTX):
    return Turn.model_validate({"reply": "x", "extracted": {"service_type": service}}, context=ctx)


def test_context_reaches_nested_leadfields():
    with pytest.raises(ValidationError):  # valid today, but the pack context excludes it
        _turn("repair", {"service_types": ["zzz"]})
    with pytest.raises(ValidationError):
        _turn("plumbing")


@pytest.mark.parametrize("v", OLD_ENUM)
def test_accepts_old_enum_values(v):
    assert _turn(v).extracted.service_type == v


@pytest.mark.parametrize("v", ["", "null", "none", "unknown", "n/a", None])
def test_blank_likes_become_none(v):
    assert _turn(v).extracted.service_type is None


@pytest.mark.parametrize("v", ["plumbing", "Repair", "repair ", 5, True])
def test_rejects_everything_else(v):
    with pytest.raises(ValidationError):
        _turn(v)


def test_service_types_property():
    q = load_pack("summit-roofing").qualification
    assert q.service_types == (*q.service_synonyms, "other")
    assert list(q.service_types) == OLD_ENUM


def test_is_grounded_unknown_service_does_not_raise():
    assert policy.is_grounded(load_pack("summit-roofing"), "service_type", "plumbing", "fix my plumbing") is False


def _llm_calls(monkeypatch, *outputs):
    seen = []
    it = iter(outputs)

    def fake(messages):
        seen.append([dict(m) for m in messages])
        return {"content": json.dumps(next(it)), "model": "fake", "prompt_tokens": 1, "completion_tokens": 1,
                "latency_ms": 1}

    monkeypatch.setattr(llm, "chat", fake)
    return seen


def _service_stored(cid):
    with engine.connect() as c:
        return c.execute(text("SELECT l.service_type FROM leads l JOIN conversations v ON v.lead_id = l.id "
                              "WHERE v.id=:i"), {"i": cid}).scalar()


def test_invalid_then_valid_retries_once(monkeypatch):
    seen = _llm_calls(monkeypatch, {"reply": "ok", "extracted": {"service_type": "plumbing"}}, FULL)
    cid, _ = agent.handle_turn(MSG)
    assert len(seen) == 2 and seen[1][-1]["role"] == "user" and seen[1][-1]["content"].startswith("Invalid output")
    assert state(cid).state == "BOOK"


def test_invalid_twice_escalates_and_stores_nothing(monkeypatch):
    bad = {"reply": "ok", "extracted": {"service_type": "plumbing"}}
    seen = _llm_calls(monkeypatch, bad, bad)
    cid, _ = agent.handle_turn(MSG)
    assert len(seen) == 2 and tuple(state(cid)) == ("ESCALATE", "escalated")
    assert _service_stored(cid) is None
    with engine.connect() as c:
        reason = c.execute(text("SELECT reason FROM escalations WHERE conversation_id=:i"), {"i": cid}).scalar()
    assert reason == "validation_failure"


def test_valid_other_is_stored_and_disqualifies(monkeypatch):
    script(monkeypatch, {"reply": "ok", "extracted": {"service_type": "other"}})
    cid, _ = agent.handle_turn("I need my gutters cleaned and some other roofing-unrelated work, other")
    assert _service_stored(cid) == "other" and tuple(state(cid)) == ("DISQUALIFY", "disqualified")
