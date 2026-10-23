from fastapi.testclient import TestClient
from sqlalchemy import text

from . import mailer, ratelimit, triage
from .config import settings
from .db import engine
from .main import app

FACTS = '{"category": "pricing", "confidence": 0.9, "draft": "After the pilot it is $199 per month, with no setup fee and no contract."}'


def _client(monkeypatch, sent=None, model=FACTS):
    ratelimit._hits.clear()
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")
    monkeypatch.setattr(mailer, "send", lambda *a, **k: sent.append(a) if sent is not None else None)

    def chat(messages):
        if isinstance(model, Exception):
            raise model
        return {"content": model}

    monkeypatch.setattr(triage.llm, "chat", chat)
    return TestClient(app)


def _say(client, message, data=None):
    r = client.post("/intake", json={"message": message, "data": data or {}})
    assert r.status_code == 200, r.text
    return r.json()


def _walk(client, answers):
    out = {"data": {}}
    for a in answers:
        out = _say(client, a, out["data"])
    return out


def test_collects_each_answer_in_order_then_saves_a_pilot_request(monkeypatch):
    sent = []
    client = _client(monkeypatch, sent)
    out = _say(client, "Dana Cruz")
    assert out["data"] == {"name": "Dana Cruz"} and "business" in out["reply"] and not out["closed"]
    out = _walk(client, ["Dana Cruz", "Cruz Roofing", "dana@intake.test", "+1 512 555 0100", "We miss calls on the roof"])
    assert out["closed"] and "dana@intake.test" in out["reply"]
    with engine.connect() as c:
        row = c.execute(text("SELECT name, status, phone FROM prospects WHERE email='dana@intake.test' ORDER BY id DESC")).first()
        note = c.execute(text("SELECT detail FROM prospect_events WHERE kind='pilot_request' ORDER BY id DESC")).scalar()
    assert row == ("Cruz Roofing", "interested", "+1 512 555 0100") and "[via chat]" in note
    assert sent and sent[0][0] == "owner@example.test" and "Cruz Roofing" in sent[0][1]


def test_phone_and_need_can_be_skipped(monkeypatch):
    out = _walk(_client(monkeypatch), ["my name is Lee", "Lee Roofing", "lee@intake.test", "skip", "skip"])
    assert out["closed"] and out["data"]["phone"] == "" and out["data"]["need"] == ""


def test_a_bad_email_is_asked_again_without_the_model(monkeypatch):
    client = _client(monkeypatch, model=RuntimeError("must not be called"))
    out = _walk(client, ["Dana", "Cruz Roofing", "nope"])
    assert "email" not in out["data"] and "didn't catch" in out["reply"] and "email" in out["reply"]


def test_a_question_is_answered_from_the_facts_and_the_step_is_asked_again(monkeypatch):
    out = _say(_client(monkeypatch), "how much does it cost?")
    assert "$199" in out["reply"] and out["reply"].endswith("What's your name?") and out["data"] == {}


def test_an_unsupported_answer_is_replaced_by_the_safe_draft(monkeypatch):
    lie = '{"category": "question", "confidence": 0.9, "draft": "It integrates with WhatsApp and Slack."}'
    out = _say(_client(monkeypatch, model=lie), "does it work with whatsapp?")
    assert "WhatsApp" not in out["reply"] and "by email" in out["reply"] and "reply shortly" not in out["reply"]


def test_questions_still_get_a_reply_when_the_model_is_down(monkeypatch):
    out = _say(_client(monkeypatch, model=RuntimeError("all LLM providers failed")), "how much does it cost?")
    assert "by email" in out["reply"] and out["reply"].endswith("What's your name?")


def test_the_form_limit_applies_to_finished_chats(monkeypatch):
    client = _client(monkeypatch)
    answers = ["Dana", "Cruz Roofing", "dana@intake.test", "skip", "skip"]
    codes = [client.post("/intake", json={"message": answers[-1], "data": {"name": "Dana", "business": "Cruz Roofing", "email": "dana@intake.test", "phone": ""}}).status_code for _ in range(6)]
    assert codes[-1] == 429


def test_a_malformed_email_in_the_data_is_rejected(monkeypatch):
    r = _client(monkeypatch).post("/intake", json={"message": "hi", "data": {"email": "nope"}})
    assert r.status_code == 422


def _extracting(monkeypatch, extraction):
    """A model that extracts for the intake prompt and triages for everything else."""
    client = _client(monkeypatch)

    def chat(messages):
        return {"content": extraction if "Extract contact details" in messages[0]["content"] else FACTS}

    monkeypatch.setattr(triage.llm, "chat", chat)
    return client


def test_a_sentence_with_a_name_and_a_business_fills_both(monkeypatch):
    client = _extracting(monkeypatch, '{"name": "John", "business": "computer parts selling", "question": false}')
    out = _say(client, "my name is John and my business is computer parts selling")
    assert out["data"] == {"name": "John", "business": "computer parts selling"} and "email" in out["reply"]


def test_a_business_sentence_before_the_name_is_kept_and_the_name_is_still_asked(monkeypatch):
    client = _extracting(monkeypatch, '{"name": null, "business": "computer parts selling", "question": false}')
    out = _say(client, "So my business is about computer parts selling.")
    assert out["data"] == {"business": "computer parts selling"} and out["reply"].endswith("What's your name?")


def test_extracted_words_the_visitor_never_wrote_are_dropped(monkeypatch):
    client = _extracting(monkeypatch, '{"name": "Dana Cruz", "business": "Cruz Roofing", "question": false}')
    out = _say(client, "I want to try the pilot for my shop please")
    assert "name" not in out["data"] and "business" not in out["data"]


def test_an_email_and_phone_inside_a_sentence_are_picked_up(monkeypatch):
    client = _extracting(monkeypatch, '{"name": null, "business": null, "question": false}')
    out = _say(client, "you can reach me at dana@intake.test or +1 512 555 0100 anytime", {"name": "Dana", "business": "Cruz Roofing"})
    assert out["data"]["email"] == "dana@intake.test" and out["data"]["phone"] == "+1 512 555 0100"
