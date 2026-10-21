"""Agent flow with a scripted fake LLM against the real Postgres (run inside the api container)."""
import json

import pytest
from sqlalchemy import text

from . import agent, llm, tools
from .config import settings
from .db import engine


SENT: list[tuple] = []  # mail captured instead of sent


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    SENT.clear()
    monkeypatch.setattr(agent.mailer, "send", lambda *a, **k: SENT.append(a))
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")
    with engine.begin() as c:
        c.execute(text("DELETE FROM appointments"))
        c.execute(text("UPDATE slots SET is_booked=false"))
    monkeypatch.setattr(tools.llm, "embed", lambda q: [1.0] + [0.0] * 383)


def script(monkeypatch, *turns: dict):
    it = iter(turns)

    def fake_chat(messages):
        return {"content": json.dumps(next(it)), "model": "fake", "prompt_tokens": 1, "completion_tokens": 1,
                "latency_ms": 1}

    monkeypatch.setattr(llm, "chat", fake_chat)


def state(cid):
    with engine.connect() as c:
        return c.execute(text("SELECT state, outcome FROM conversations WHERE id=:i"), {"i": cid}).one()


MSG = "I own 1 A St, Denver and need a repair within 1 month. Sam, 303-555-0142"
FULL = {"reply": "ok", "extracted": {"service_type": "repair", "is_owner": True, "address": "1 A St, Denver",
                                      "timeline_months": 1, "name": "Sam", "phone": "303-555-0142"}}


def test_qualified_lead_books(monkeypatch):
    script(monkeypatch, FULL, {"reply": "ok"})
    cid, reply = agent.handle_turn(MSG)
    assert "next openings" in reply and state(cid).state == "BOOK"
    _, reply = agent.handle_turn("the first", cid)
    assert "booked" in reply and tuple(state(cid)) == ("DONE", "booked")


def test_renter_is_disqualified_and_cannot_book(monkeypatch):
    script(monkeypatch, {"reply": "ok", "extracted": {"is_owner": False}})
    cid, _ = agent.handle_turn("I rent")
    assert tuple(state(cid)) == ("DISQUALIFY", "disqualified")
    ok, res = tools.run(cid, "book_appointment", {"lead_id": 1, "slot_id": 1}, tools.book_appointment)
    assert not ok


def test_taken_slot_is_not_double_booked(monkeypatch):
    script(monkeypatch, FULL, {"reply": "ok"})
    cid, _ = agent.handle_turn(MSG)
    with engine.begin() as c:
        c.execute(text("UPDATE slots SET is_booked=true WHERE id=1"))
    _, reply = agent.handle_turn("first", cid)
    assert "isn't available" in reply and state(cid).state == "BOOK"


def test_invalid_output_twice_escalates(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda m: {"content": "not json", "model": "fake", "prompt_tokens": 1,
                                                 "completion_tokens": 1, "latency_ms": 1})
    cid, _ = agent.handle_turn("hello")
    assert tuple(state(cid)) == ("ESCALATE", "escalated")


def test_regex_escalation_skips_llm(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda m: pytest.fail("LLM must not be called"))
    cid, _ = agent.handle_turn("let me speak to a real person")
    assert state(cid).state == "ESCALATE"


def test_price_in_reply_is_replaced(monkeypatch):
    script(monkeypatch, {"reply": "A new roof costs $12,000.", "is_question": True})
    _, reply = agent.handle_turn("how much?")
    assert "$" not in reply


def test_empty_reply_falls_back_to_next_question(monkeypatch):
    script(monkeypatch, {"reply": "", "extracted": {"service_type": "repair"}})
    _, reply = agent.handle_turn("repair please")
    assert "own the property" in reply


def test_question_is_answered_even_if_model_forgets_the_flag(monkeypatch):
    script(monkeypatch, {"reply": "The inspection is free and takes about 45 to 60 minutes."})
    monkeypatch.setattr(tools, "lookup_faq", lambda query, k=3: {"chunks": ["The roof inspection is free and takes about 45 to 60 minutes."]})
    _, reply = agent.handle_turn("How long does the inspection take?")
    assert "45" in reply


def test_empty_model_answer_gets_a_second_focused_call(monkeypatch):
    calls = iter([json.dumps({"reply": "", "is_question": True}), "It takes about 45 to 60 minutes."])
    monkeypatch.setattr(llm, "chat", lambda m: {"content": next(calls), "model": "fake", "prompt_tokens": 1,
                                                 "completion_tokens": 1, "latency_ms": 1})
    monkeypatch.setattr(tools, "lookup_faq", lambda query, k=3: {"chunks": ["The roof inspection is free and takes about 45 to 60 minutes."]})
    _, reply = agent.handle_turn("How long does the inspection take?")
    assert "45" in reply


def test_invented_credentials_become_fallback(monkeypatch):
    monkeypatch.setattr(tools, "lookup_faq", lambda query, k=3: {"chunks": ["The roof inspection is free."]})
    script(monkeypatch, {"reply": "Yes, we are fully licensed and insured.", "is_question": True})
    _, reply = agent.handle_turn("Are you licensed and insured?")
    assert "licensed" not in reply and "don't have that information" in reply


def test_booking_emails_the_owner_and_confirms_to_the_lead(monkeypatch):
    full = {**FULL, "extracted": {**FULL["extracted"], "email": "sam@lead.test"}}
    script(monkeypatch, full, {"reply": "ok"})
    cid, _ = agent.handle_turn(MSG + ", sam@lead.test")  # the agent only keeps details that appear in the message
    agent.handle_turn("the first", cid)
    to = {m[0]: m for m in SENT}
    assert set(to) == {"owner@example.test", "sam@lead.test"}
    assert "Sam" in to["owner@example.test"][1] and "303-555-0142" in to["owner@example.test"][2]
    assert "demo" in to["sam@lead.test"][2].lower()  # a visitor must know this booking is a demo


def test_booking_without_a_lead_email_only_alerts_the_owner(monkeypatch):
    script(monkeypatch, FULL, {"reply": "ok"})
    cid, _ = agent.handle_turn(MSG)
    agent.handle_turn("the first", cid)
    assert [m[0] for m in SENT] == ["owner@example.test"]


def test_a_failing_email_never_blocks_the_booking(monkeypatch):
    def boom(*a, **k):
        raise agent.mailer.MailError("down")
    monkeypatch.setattr(agent.mailer, "send", boom)
    script(monkeypatch, FULL, {"reply": "ok"})
    cid, _ = agent.handle_turn(MSG)
    _, reply = agent.handle_turn("the first", cid)
    assert "booked" in reply and tuple(state(cid)) == ("DONE", "booked")
