import pytest
from fastapi.testclient import TestClient

from . import triage
from .config import settings
from .main import app

PROFILE = triage.load_profile("summit-roofing")


def _llm(monkeypatch, content: str):
    monkeypatch.setattr(triage.llm, "chat", lambda messages: {"content": content})


def test_confident_category_needs_no_human(monkeypatch):
    _llm(monkeypatch, '{"category": "new_lead", "confidence": 0.95, "draft": "Happy to help."}')
    r = triage.triage("I need my roof repaired", PROFILE)
    assert (r.category, r.needs_human, r.draft) == ("new_lead", False, "Happy to help.")


def test_low_confidence_goes_to_a_human(monkeypatch):
    _llm(monkeypatch, '{"category": "question", "confidence": 0.5, "draft": "x"}')
    r = triage.triage("hmm", PROFILE)
    assert r.needs_human and "confidence" in r.reason


def test_always_human_category(monkeypatch):
    _llm(monkeypatch, '{"category": "complaint", "confidence": 0.99, "draft": "Sorry."}')
    assert triage.triage("the job was bad", PROFILE).needs_human


def test_draft_with_an_invented_claim_is_replaced(monkeypatch):
    _llm(monkeypatch, '{"category": "question", "confidence": 0.95, "draft": "Yes, we guarantee a 25 year warranty and a $500 discount."}')
    assert triage.triage("any discount?", PROFILE).draft == triage.SAFE_DRAFT


def test_confident_other_still_goes_to_a_human(monkeypatch):
    _llm(monkeypatch, '{"category": "other", "confidence": 1.0, "draft": "x"}')
    assert triage.triage("asdf maybe", PROFILE).needs_human


def test_unknown_category_becomes_other(monkeypatch):
    _llm(monkeypatch, '{"category": "hacking", "confidence": 0.99, "draft": "x"}')
    r = triage.triage("x", PROFILE)
    assert r.category == "other" and r.needs_human


def test_garbage_model_output_fails_safe(monkeypatch):
    _llm(monkeypatch, "sure! here you go")
    r = triage.triage("x", PROFILE)
    assert (r.category, r.confidence, r.needs_human) == ("other", 0.0, True)


def test_legal_threat_is_decided_by_code_not_model(monkeypatch):
    _llm(monkeypatch, '{"category": "question", "confidence": 0.99, "draft": "x"}')
    r = triage.triage("I will sue you", PROFILE)
    assert r.needs_human and "legal" in r.reason


def test_profile_changes_the_categories(monkeypatch):
    dental = triage.load_profile("bright-smile-dental")
    _llm(monkeypatch, '{"category": "emergency", "confidence": 0.9, "draft": "Call us now."}')
    r = triage.triage("my tooth got knocked out", dental)
    assert r.category == "emergency" and r.needs_human


def test_unknown_profile_is_rejected():
    with pytest.raises(FileNotFoundError):
        triage.load_profile("../etc/passwd")


def test_endpoint_requires_admin_key(monkeypatch):
    c = TestClient(app)
    assert c.post("/triage", json={"message": "hi"}).status_code == 403
    _llm(monkeypatch, '{"category": "new_lead", "confidence": 0.9, "draft": "Hi"}')
    r = c.post("/triage", json={"message": "need a quote"}, headers={"x-admin-key": settings.admin_api_key})
    assert r.status_code == 200 and r.json()["category"] == "new_lead"
