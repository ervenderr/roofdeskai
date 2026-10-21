import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import llm, mailer, outreach, prospects
from .config import settings
from .db import engine
from .main import app

NOW = datetime(2030, 10, 23, 3, 0, tzinfo=timezone.utc)  # a future Wednesday, 11:00 in Manila: inside the send window and never in the past
SAMPLE = next(p for p in (Path(__file__).parents[1] / "scripts" / "sample_prospects.json",
                         Path(__file__).parents[2] / "scripts" / "sample_prospects.json") if p.exists())  # container vs host
GOOD_COPY = {"subject": "A quick idea for Acme Dental", "body": (
    "Hi Acme Dental team,\n\nI came across Acme Dental, a dentist in Davao City. Many clinics lose enquiries that "
    "arrive when nobody is free to reply, and we built an assistant that answers instantly and books appointments.\n\n"
    "Would it be worth a quick look at how it could work for you?")}


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(settings, "sender_address", "1 Test St, Davao City")
    monkeypatch.setattr(settings, "outreach_enforce_window", False)
    monkeypatch.setattr(mailer, "send", lambda *a, **k: None)
    monkeypatch.setattr(llm, "chat", lambda m: pytest.fail("no LLM call expected"))


def sample_rows() -> list[dict]:
    suffix = uuid.uuid4().hex[:6]
    return [{**r, "place_id": f"{r['place_id']}-{suffix}"} if "place_id" in r else r for r in json.loads(SAMPLE.read_text())]


def llm_returns(monkeypatch, *outputs: str):
    it = iter(outputs)
    monkeypatch.setattr(llm, "chat", lambda m: {"content": next(it), "model": "fake", "prompt_tokens": 1,
                                                 "completion_tokens": 1, "latency_ms": 1})


def campaign(auto=False, cap=20, tz="Asia/Manila", locale="en-PH") -> int:
    with engine.begin() as c:
        return c.execute(text("INSERT INTO campaigns (name, auto_approve, daily_cap, timezone, locale) "
                              "VALUES ('t', :a, :c, :tz, :l) RETURNING id"), {"a": auto, "c": cap, "tz": tz, "l": locale}).scalar_one()


def prospect(cid: int, name="Acme Dental", email=None, **extra) -> tuple[int, str]:
    email = email if email is not None else f"{uuid.uuid4().hex[:8]}@outreach.test"
    row = {"title": name, "category": "Dentist", "address": "1 A St, Davao City", "emails": [email],
           "place_id": uuid.uuid4().hex, "review_rating": 4.5, "review_count": 50, **extra}
    prospects.import_rows(cid, [row])
    with engine.connect() as c:
        return c.execute(text("SELECT id FROM prospects WHERE external_id=:e"), {"e": row["place_id"]}).scalar_one(), email


def status(pid: int) -> str:
    with engine.connect() as c:
        return c.execute(text("SELECT status FROM prospects WHERE id=:i"), {"i": pid}).scalar()


def msgs(pid: int) -> list[tuple]:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text("SELECT step, status FROM outreach_messages WHERE prospect_id=:p ORDER BY step"), {"p": pid})]


def sent_prospect(monkeypatch, auto=True, cap=20, **kw) -> tuple[int, str, int]:
    """A prospect with step 1 sent at NOW."""
    llm_returns(monkeypatch, GOOD_COPY["body"])
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    cid = campaign(auto, cap)
    pid, email = prospect(cid, **kw)
    outreach.draft_pending(50, cid)
    outreach.send_due(NOW, cid)
    return pid, email, cid


# --- import and scoring -----------------------------------------------------------------------------

def test_normalize_reads_scraper_row_defensively():
    p = prospects.normalize({"title": " Bright Smile ", "emails": ["bad", "Hello@Acme.CO"], "review_rating": "4.6",
                             "review_count": "182", "place_id": "p1", "complete_address": {"street": "1 A St", "city": "Davao"},
                             "open_hours": {"Monday": ["8 AM–5 PM"]}, "user_reviews": [{"Description": "ok"}, "plain", {}]})
    assert p["name"] == "Bright Smile" and p["email"] == "hello@acme.co" and p["rating"] == 4.6
    assert p["address"] == "1 A St, Davao" and p["review_texts"] == ["ok", "plain"] and p["external_id"] == "p1"
    assert prospects.normalize({"title": ""}) is None
    assert prospects.normalize({"title": "X", "review_rating": "n/a"})["rating"] is None


def test_hours_gap_detection():
    nb = " "
    full = {d: f"8 AM{nb}–{nb}5 PM" for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")}
    assert prospects.after_hours_gap({**full, "Saturday": "Closed"})
    assert prospects.after_hours_gap({**full, "Saturday": "9 AM–5 PM", "Sunday": "9 AM–5 PM"})  # weekday closes at 5 PM
    late = {d: "10 AM–9 PM" for d in full} | {"Saturday": "10 AM–9 PM", "Sunday": "10 AM–6 PM"}
    assert not prospects.after_hours_gap(late)
    assert not prospects.after_hours_gap(None)


def test_score_rewards_pain_and_email():
    base = {"email": "a@b.co", "website": "x", "review_count": 100, "rating": 4.5, "category": "Dentist",
            "hours": {"Saturday": "Closed"}}
    pain = ["nobody answers the phone", "goes to voicemail"]
    s, reasons = prospects.score({**base, "review_texts": pain})
    s0, _ = prospects.score({**base, "review_texts": []})
    assert s > s0 and any("unanswered" in r for r in reasons)
    assert prospects.score({**base, "email": None, "review_texts": []})[0] < s0
    assert prospects.score({"review_texts": []})[0] == 0


def test_import_dedupes_and_flags_missing_email():
    cid = campaign()
    rows = sample_rows()
    first = prospects.import_rows(cid, rows)
    assert first["imported"] == 8 and first["duplicates"] == 1 and first["invalid"] == 1 and first["no_email"] == 2
    assert prospects.import_rows(cid, rows)["imported"] == 0  # idempotent


def test_suppressed_email_is_imported_as_skipped():
    with engine.begin() as c:
        outreach.suppress(c, "gone@outreach.test", "unsubscribe")
    pid, _ = prospect(campaign(), email="gone@outreach.test")
    assert status(pid) == "skipped"


def test_status_machine_rejects_illegal_moves_but_always_allows_unsubscribe():
    pid, _ = prospect(campaign())
    with pytest.raises(ValueError):
        prospects.set_status(pid, "sent")  # scored -> sent skips the approval steps
    prospects.set_status(pid, "unsubscribed")
    assert status(pid) == "unsubscribed"


# --- copy -------------------------------------------------------------------------------------------

FACTS = {"name": "Acme Dental Clinic", "category": "Dentist", "review_signal": False, "rating": 4.5, "review_count": 50}


@pytest.mark.parametrize("body,fragment", [
    ("Hi Acme Dental team, we cut missed calls by 40 percent for clinics like yours, worth a chat about it today?", "number"),
    ("Hi Acme Dental team, see https://x.io for how an assistant could answer your enquiries around the clock.", "banned"),
    ("Hi Acme Dental team, we guarantee more bookings for your clinic with an assistant answering every enquiry.", "banned"),
    ("Hi Acme Dental team, your reviews say calls go unanswered so an assistant could really help your clinic.", "reviews"),
    ("Hi there, an assistant could answer enquiries for your clinic around the clock, worth a short chat about it?", "name"),
])
def test_check_draft_rejects_unsafe_copy(body, fragment):
    issues = outreach.check_draft(outreach.Draft(subject="Quick idea for Acme", body=body), FACTS)
    assert any(fragment in i for i in issues), issues


def test_check_draft_accepts_shortened_name_and_supported_numbers():
    body = ("Hi Acme Dental team, with a 4.5 rating from 50 reviews of happy patients, an assistant could answer every "
            "enquiry instantly. Would a quick look be useful for you?")
    assert outreach.check_draft(outreach.Draft(subject="Idea for Acme Dental", body=body), {**FACTS, "review_signal": True}) == []


def test_draft_copy_retries_then_uses_template(monkeypatch):
    p = {"id": 1, "name": "Acme Dental", "category": "Dentist", "address": "1 A St, Davao City", "pain_mentions": 0,
         "rating": 4.5, "review_count": 50, "website": None}
    bad = "We guarantee 50% more patients for Acme Dental, reply today please."
    llm_returns(monkeypatch, bad, GOOD_COPY["body"] + "\n\nBest regards,\nThe Team")
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    d, source = outreach.draft_copy(p)
    assert source == "llm" and "guarantee" not in d.body and "Best regards" not in d.body and d.subject == "A quick idea for Acme Dental"
    llm_returns(monkeypatch, bad, bad)
    assert outreach.draft_copy(p)[1] == "template"
    monkeypatch.setattr(llm, "chat", lambda m: (_ for _ in ()).throw(RuntimeError("down")))
    assert outreach.draft_copy(p)[1] == "template"


def test_footer_is_added_by_code():
    out = outreach.with_footer("Hello there")
    assert "unsubscribe" in out and "1 Test St, Davao City" in out


# --- queue, approval, sending -----------------------------------------------------------------------

def test_draft_then_manual_approval_then_send(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, body, html=None: sent.append((to, subject, body)))
    llm_returns(monkeypatch, GOOD_COPY["body"])
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    cid = campaign(auto=False)
    pid, email = prospect(cid)
    assert outreach.draft_pending(50, cid)["awaiting_approval"] == 1 and status(pid) == "drafted"
    assert outreach.send_due(NOW, cid)["sent"] == 0  # nothing approved yet
    with engine.connect() as c:
        mid = c.execute(text("SELECT id FROM outreach_messages WHERE prospect_id=:p"), {"p": pid}).scalar_one()
    outreach.approve(mid)
    assert status(pid) == "approved"
    assert outreach.send_due(NOW, cid)["sent"] == 1 and status(pid) == "sent"
    to, subject, body = next(s for s in sent if s[0] == email)
    assert "Reply \"unsubscribe\"" in body and "1 Test St" in body
    assert msgs(pid) == [(1, "sent")]


def test_auto_approve_campaign_skips_the_queue(monkeypatch):
    llm_returns(monkeypatch, GOOD_COPY["body"])
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    cid = campaign(auto=True)
    pid, _ = prospect(cid)
    outreach.draft_pending(50, cid)
    assert status(pid) == "approved" and msgs(pid) == [(1, "approved")]


def test_reject_skips_the_prospect(monkeypatch):
    llm_returns(monkeypatch, GOOD_COPY["body"])
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    cid = campaign()
    pid, _ = prospect(cid)
    outreach.draft_pending(50, cid)
    with engine.connect() as c:
        mid = c.execute(text("SELECT id FROM outreach_messages WHERE prospect_id=:p"), {"p": pid}).scalar_one()
    outreach.reject(mid)
    assert status(pid) == "skipped" and msgs(pid) == [(1, "rejected")]
    with pytest.raises(LookupError):
        outreach.approve(mid)


def test_daily_cap_is_enforced(monkeypatch):
    llm_returns(monkeypatch, *[GOOD_COPY["body"]] * 3)
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    cid = campaign(auto=True, cap=2)
    ids = [prospect(cid)[0] for _ in range(3)]
    outreach.draft_pending(50, cid)
    result = outreach.send_due(NOW, cid)
    assert result["sent"] == 2 and result["skipped"] == {"daily_cap_reached": 1}
    assert sorted(status(i) for i in ids) == ["approved", "sent", "sent"]


def test_suppressed_prospect_is_never_emailed(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, *a: sent.append(to))
    llm_returns(monkeypatch, GOOD_COPY["body"])
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    cid = campaign(auto=True)
    pid, email = prospect(cid)
    outreach.draft_pending(50, cid)
    with engine.begin() as c:
        outreach.suppress(c, email, "unsubscribe")  # unsubscribes after drafting, before sending
    outreach.send_due(NOW, cid)
    assert email not in sent and msgs(pid) == [(1, "cancelled")]


def approved_message(monkeypatch, tz: str, locale="en-PH") -> tuple[int, int]:
    llm_returns(monkeypatch, GOOD_COPY["body"])
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    cid = campaign(auto=True, tz=tz, locale=locale)
    pid, _ = prospect(cid)
    outreach.draft_pending(50, cid)
    return cid, pid


def test_send_window_follows_the_campaigns_timezone(monkeypatch):
    monkeypatch.setattr(settings, "outreach_enforce_window", True)
    # NOW is Wed 11:00 in Manila but Tue 22:00 in Chicago: the same instant is inside one window and outside the other.
    assert outreach.in_send_window(NOW, "Asia/Manila") and not outreach.in_send_window(NOW, "America/Chicago")
    assert outreach.in_send_window(NOW + timedelta(hours=12), "America/Chicago")  # Wed 10:00 in Chicago
    cid, pid = approved_message(monkeypatch, "America/Chicago")
    blocked = outreach.send_due(NOW, cid)
    assert blocked["sent"] == 0 and blocked["window_open"] is False and status(pid) == "approved"
    assert outreach.send_due(NOW + timedelta(hours=12), cid)["sent"] == 1 and status(pid) == "sent"


def test_weekend_is_blocked_and_missing_address_refuses(monkeypatch):
    monkeypatch.setattr(settings, "outreach_enforce_window", True)
    cid, pid = approved_message(monkeypatch, "Asia/Manila")
    assert outreach.send_due(NOW + timedelta(days=3), cid)["sent"] == 0 and status(pid) == "approved"  # Saturday
    assert not outreach.in_send_window(NOW.replace(hour=16))
    monkeypatch.setattr(settings, "sender_address", "")
    with pytest.raises(RuntimeError):
        outreach.send_due(NOW, cid)


def test_us_campaigns_say_inquiry_everywhere(monkeypatch):
    assert outreach.localize("Enquiries and enquiry, an enquiries desk", "en-US") == "Inquiries and inquiry, an inquiries desk"
    assert outreach.localize("enquiries", "en-PH") == "enquiries"
    facts = {"name": "Acme Roofing", "category": "Roofing contractor", "city": "Austin"}
    assert "inquiries" in outreach.template_draft(facts, "en-US").body and "enquir" not in outreach.template_draft(facts, "en-US").body
    assert "enquir" not in outreach.followup_copy(3, "Acme", "Idea", "en-US").body
    llm_returns(monkeypatch, "Hi Acme Dental team, many clinics lose enquiries when nobody can reply, and we built an assistant "
                             "that answers customer enquiries instantly. Would a quick look be useful for you?")
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    d, _ = outreach.draft_copy({"id": 1, "name": "Acme Dental", "category": "Dentist", "address": "1 A St, Austin", "pain_mentions": 0,
                                "rating": None, "review_count": None, "website": None}, "en-US")
    assert "inquiries" in d.body and "enquir" not in d.body


def test_mail_failure_marks_message_failed_and_keeps_prospect_approved(monkeypatch):
    llm_returns(monkeypatch, GOOD_COPY["body"])
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    monkeypatch.setattr(mailer, "send", lambda *a: (_ for _ in ()).throw(mailer.MailError("ConnectError")))
    cid = campaign(auto=True)
    pid, _ = prospect(cid)
    outreach.draft_pending(50, cid)
    assert outreach.send_due(NOW, cid)["failed"] == 1
    assert status(pid) == "approved" and msgs(pid) == [(1, "failed")]


# --- follow-ups -------------------------------------------------------------------------------------

def test_followup_sequence_timing_and_cap(monkeypatch):
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    pid, _, cid = sent_prospect(monkeypatch)
    assert outreach.schedule_followups(NOW + timedelta(days=2), cid)["followups_drafted"] == 0
    outreach.schedule_followups(NOW + timedelta(days=3), cid)
    assert msgs(pid) == [(1, "sent"), (2, "approved")]
    outreach.send_due(NOW + timedelta(days=3), cid)
    outreach.schedule_followups(NOW + timedelta(days=9), cid)  # 6 days after step 2: not yet
    assert len(msgs(pid)) == 2
    outreach.schedule_followups(NOW + timedelta(days=10), cid)
    outreach.send_due(NOW + timedelta(days=10), cid)
    outreach.schedule_followups(NOW + timedelta(days=60), cid)
    assert msgs(pid) == [(1, "sent"), (2, "sent"), (3, "sent")]  # never a 4th


def test_manual_campaign_followups_wait_for_approval(monkeypatch):
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    cid = campaign(auto=False)
    pid, email = prospect(cid)
    with engine.begin() as c:
        c.execute(text("INSERT INTO outreach_messages (prospect_id, step, subject, body, status, sent_at) VALUES (:p, 1, 'Quick idea', 'x', 'sent', :t)"),
                  {"p": pid, "t": NOW})
        c.execute(text("UPDATE prospects SET status='sent' WHERE id=:p"), {"p": pid})
    outreach.schedule_followups(NOW + timedelta(days=4), cid)
    assert msgs(pid) == [(1, "sent"), (2, "drafted")]
    assert outreach.send_due(NOW + timedelta(days=4), cid)["sent"] == 0


# --- replies ----------------------------------------------------------------------------------------

def test_unsubscribe_reply_works_without_the_llm(monkeypatch):
    pid, email, cid = sent_prospect(monkeypatch)
    outreach.schedule_followups(NOW + timedelta(days=4), cid)
    monkeypatch.setattr(llm, "chat", lambda m: pytest.fail("unsubscribe must not depend on the model"))
    r = outreach.handle_event(email.upper(), "reply", "Please remove me from your list")
    assert r["label"] == "unsubscribe" and status(pid) == "unsubscribed" and r["needs_human"] is False
    with engine.connect() as c:
        assert c.execute(text("SELECT reason FROM suppressions WHERE email=:e"), {"e": email}).scalar() == "unsubscribe"
    assert (2, "cancelled") in msgs(pid)
    outreach.send_due(NOW + timedelta(days=4), cid)
    assert status(pid) == "unsubscribed"


def test_bounce_suppresses_and_stops_the_sequence(monkeypatch):
    pid, email, cid = sent_prospect(monkeypatch)
    assert outreach.handle_event(email, "bounce")["status"] == "bounced"
    assert outreach.schedule_followups(NOW + timedelta(days=30), cid)["followups_drafted"] == 0


def test_interested_reply_needs_a_human_and_stops_followups(monkeypatch):
    pid, email, cid = sent_prospect(monkeypatch)
    llm_returns(monkeypatch, '{"label": "interested"}')
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    r = outreach.handle_event(email, "reply", "Sounds good, can you send details and pricing?")
    assert (r["status"], r["needs_human"]) == ("interested", True)
    assert outreach.schedule_followups(NOW + timedelta(days=30), cid)["followups_drafted"] == 0
    llm_returns(monkeypatch, '{"label": "question"}')
    assert outreach.handle_event(email, "reply", "One more question")["status"] == "interested"  # stays the stronger status


def test_not_interested_is_suppressed_and_out_of_office_is_ignored(monkeypatch):
    pid, email, _ = sent_prospect(monkeypatch)
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    assert outreach.handle_event(email, "reply", "Automatic reply: I am out of office until Monday")["label"] == "out_of_office"
    assert status(pid) == "sent"
    llm_returns(monkeypatch, '{"label": "not_interested"}')
    assert outreach.handle_event(email, "reply", "No thanks")["status"] == "not_interested"
    with engine.connect() as c:
        assert c.execute(text("SELECT reason FROM suppressions WHERE email=:e"), {"e": email}).scalar() == "not_interested"


def test_garbled_classifier_output_falls_back_to_a_human(monkeypatch):
    pid, email, _ = sent_prospect(monkeypatch)
    llm_returns(monkeypatch, "I think they are interested!")
    monkeypatch.setattr(outreach, "_log_llm", lambda *a: None)
    r = outreach.handle_event(email, "reply", "Hmm, tell me more?")
    assert (r["label"], r["status"], r["needs_human"]) == ("other", "replied", True)


def test_unknown_sender_is_not_matched():
    assert outreach.handle_event("stranger@outreach.test", "reply", "hello") == {"matched": False}


# --- HTTP -------------------------------------------------------------------------------------------

def test_endpoints_require_the_admin_key_and_work(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "k")
    client, H = TestClient(app), {"X-Admin-Key": "k"}
    for path in ("/admin/prospects", "/admin/outreach/queue", "/admin/campaigns", "/admin/outreach/metrics"):
        assert client.get(path).status_code == 403
    cid = client.post("/admin/campaigns", json={"name": "Dental Davao", "daily_cap": 5}, headers=H).json()["id"]
    sample = sample_rows()
    assert client.post(f"/admin/campaigns/{cid}/import", json={"rows": sample}, headers=H).json()["imported"] == 8
    top = client.get(f"/admin/prospects?campaign_id={cid}", headers=H).json()
    assert top[0]["score"] >= top[-1]["score"] and top[0]["name"] in ("Bright Smile Dental Clinic", "Hilltop Veterinary Clinic")
    assert client.patch(f"/admin/campaigns/{cid}", json={"auto_approve": True}, headers=H).json()["auto_approve"] is True
    assert client.patch(f"/admin/campaigns/{cid}", json={}, headers=H).status_code == 422
    assert client.post("/admin/outreach/999999/approve", headers=H).status_code == 404
    assert client.get(f"/admin/prospects/{top[0]['id']}", headers=H).json()["prospect"]["name"] == top[0]["name"]
    assert client.post("/webhooks/outreach-event", json={"email": "nobody@outreach.test", "kind": "bounce"}, headers=H).json() == {"matched": False}
    assert client.post("/webhooks/outreach-event", json={"email": "a@b.co", "kind": "wat"}, headers=H).status_code == 422
    assert "outreach" in client.get("/metrics", headers=H).json()


def test_parse_body_strips_signoff_subject_and_fences():
    raw = "```\nSubject: Hello\n\nHi Acme team,\n\nBody here?\n\nBest regards,\nThe RoofDesk AI team\n```"
    assert outreach.parse_body(raw) == "Hi Acme team,\n\nBody here?"


def test_social_proof_is_banned_but_your_customers_is_fine():
    ok = outreach.Draft(subject="Idea for Acme", body="Hi Acme Dental team, an assistant lets you focus on your customers while it "
                        "answers enquiries around the clock. Would a quick look be useful for you?")
    assert outreach.check_draft(ok, FACTS) == []
    for claim in ("It is used by clinics in many cities.", "Our customers love it.", "Trusted by local businesses.", "We helped many clinics."):
        bad = outreach.Draft(subject="Idea for Acme", body=f"Hi Acme Dental team, an assistant can answer enquiries. {claim} Interested?")
        assert any("banned" in i for i in outreach.check_draft(bad, FACTS)), claim


def test_free_mail_address_is_flagged_and_weighed_less():
    biz, reasons_b = prospects.score({"email": "info@acme.example.com"})
    person, reasons_p = prospects.score({"email": "owner@gmail.com"})
    assert biz > person and any("free-mail" in r for r in reasons_p) and not any("free-mail" in r for r in reasons_b)


@pytest.mark.parametrize("email,ok", [
    ("office@acme-roofing.com", True), ("Hello@Acme.CO", True), ("info@acme-roofing.com", True),
    ("flags@2x.png", False), ("chosen-sprite@2x.png", False), ("logo@3x.webp", False), ("name@domain.com", False),
    ("abc123@sentry.wixpress.com", False), ("u003eowner@acme.com", False), ("a%20b@acme.com", False), ("not-an-email", False),
])
def test_usable_email_rejects_scraper_junk(email, ok):
    assert prospects.usable_email(email) is ok


def test_import_skips_junk_emails_and_falls_back_to_the_next_valid_one():
    cid = campaign()
    prospects.import_rows(cid, [{"title": "Junk Co", "place_id": uuid.uuid4().hex, "emails": ["flags@2x.png", "owner@junk-co.com"]},
                                {"title": "Only Junk", "place_id": uuid.uuid4().hex, "emails": ["flags@2x.png"]}])
    with engine.connect() as c:
        got = {r[0]: (r[1], r[2]) for r in c.execute(text("SELECT name, email, status FROM prospects WHERE campaign_id=:c"), {"c": cid})}
    assert got["Junk Co"] == ("owner@junk-co.com", "scored") and got["Only Junk"] == (None, "no_email")


def test_first_email_gets_service_list_and_followups_do_not():
    first = outreach.with_footer("Hi team,", 1, "en-US")
    assert "What it does:" in first and "  • Replies to customer inquiries instantly" in first
    assert "What it does:" not in outreach.with_footer("Hi team,", 2)
    assert first.rstrip().endswith('"unsubscribe" and I won\'t contact you again.')


def test_guard_rejects_invented_observations():
    facts = outreach.facts_for({"id": 1, "name": "Acme Roofing", "category": "Roofing contractor", "city": "Austin"})
    for line in ("we've noticed inquiries go unanswered", "I noticed you miss calls", "you likely get many inquiries", "you probably miss leads"):
        d = outreach.Draft(subject="Hello there", body=f"Hi Acme Roofing team,\n\nAs a business in Austin, {line}.\n\nWant a demo?")
        assert "contains a banned claim, link or contact detail" in outreach.check_draft(d, facts), line


def test_business_name_is_trimmed_for_greetings():
    assert outreach.facts_for({"id": 1, "name": "Acme Roofs - Austin"})["name"] == "Acme Roofs"
    assert outreach.facts_for({"id": 1, "name": "Austin Roofing Company | Texas Certified"})["name"] == "Austin Roofing Company"
    assert outreach.facts_for({"id": 1, "name": "Quality Exteriors"})["name"] == "Quality Exteriors"


def test_service_list_goes_before_the_closing_question():
    out = outreach.with_footer("Hi team,\n\nWe built a thing.\n\nWant a demo?", 1)
    assert out.index("What it does:") < out.index("Want a demo?") < out.index("--\n")
