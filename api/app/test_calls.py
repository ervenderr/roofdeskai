import csv
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import outreach, prospects
from .config import settings
from .db import engine
from .main import app

H = {"X-Admin-Key": "k"}
NB = " "


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "k")


def campaign() -> int:
    with engine.begin() as c:
        return c.execute(text("INSERT INTO campaigns (name) VALUES ('call-test') RETURNING id")).scalar_one()


def add(cid: int, name="Acme Clinic", phone="0900 000 0000", email=None, **extra) -> int:
    row = {"title": name, "category": "Clinic", "address": "1 A St, Davao City", "phone": phone, "place_id": uuid.uuid4().hex,
           "review_rating": 4.5, "review_count": 80, "website": "", "emails": [email] if email else [], **extra}
    prospects.import_rows(cid, [row])
    with engine.connect() as c:
        return c.execute(text("SELECT id FROM prospects WHERE external_id=:e"), {"e": row["place_id"]}).scalar_one()


def row(pid: int) -> dict:
    with engine.connect() as c:
        return dict(c.execute(text("SELECT status, call_outcome, call_note FROM prospects WHERE id=:i"), {"i": pid}).mappings().one())


def test_closed_days_and_talking_points_use_only_scraped_facts():
    hours = {"Monday": "9 AM–5 PM", "Saturday": "Closed", "Sunday": "Closed"}
    assert prospects.closed_days(hours) == ["Saturday", "Sunday"]
    pts = prospects.talking_points({"name": "A", "hours": hours, "pain_mentions": 1, "review_count": 120, "rating": 4.55,
                                    "website": None, "email": None})
    assert pts[0].startswith("Closed on Saturday, Sunday") and any("unanswered call" in p for p in pts) and len(pts) <= 4
    assert any("rated 4.5" in p or "rated 4.6" in p for p in pts) or any("Busy: 120" in p for p in pts)
    assert prospects.talking_points({"name": "A"}) == ["No website, so customers can only reach them by phone or social media."]
    assert "Acme" in prospects.opener({"name": "Acme"})


def test_call_list_contains_only_phoned_open_prospects():
    cid = campaign()
    keep = add(cid, "Keep Me")
    add(cid, "No Phone", phone="")
    add(cid, "Has Email", email="a@call.example.com")  # scored, not no_email: only in scope=all
    done = add(cid, "Already Settled")
    outreach.record_call(done, "wrong_number")
    names = [r["name"] for r in outreach.call_list(cid)]
    assert names == ["Keep Me"]
    assert {r["name"] for r in outreach.call_list(cid, "all")} == {"Keep Me", "Has Email"}
    assert outreach.call_list(cid)[0]["talking_points"] and outreach.call_list(cid)[0]["opener"]
    outreach.record_call(keep, "no_answer", "rang 5 times")  # retryable outcomes stay on the list
    assert [r["name"] for r in outreach.call_list(cid)] == ["Keep Me"]


def test_interested_call_settles_the_prospect_and_stops_email():
    cid = campaign()
    pid = add(cid, email="x@call.example.com")
    with engine.begin() as c:
        c.execute(text("UPDATE prospects SET status='approved' WHERE id=:i"), {"i": pid})
        c.execute(text("INSERT INTO outreach_messages (prospect_id, step, subject, body, status) VALUES (:i, 1, 's', 'b', 'approved')"), {"i": pid})
    assert outreach.record_call(pid, "interested", "wants a demo")["status"] == "interested"
    with engine.connect() as c:
        assert c.execute(text("SELECT status FROM outreach_messages WHERE prospect_id=:i"), {"i": pid}).scalar() == "cancelled"
    assert row(pid)["call_note"] == "wants a demo"
    assert pid not in [r["id"] for r in outreach.call_list(cid, "all")]


@pytest.mark.parametrize("outcome", ["not_interested", "do_not_contact"])
def test_a_no_on_the_phone_suppresses_their_email_too(outcome):
    cid = campaign()
    email = f"{uuid.uuid4().hex[:8]}@outreach.test"
    pid = add(cid, email=email)
    assert outreach.record_call(pid, outcome)["status"] == "not_interested"
    with engine.connect() as c:
        assert c.execute(text("SELECT reason FROM suppressions WHERE email=:e"), {"e": email}).scalar() == outcome


def test_no_answer_and_wrong_number_do_not_change_status():
    pid = add(campaign())
    assert outreach.record_call(pid, "no_answer")["status"] == "no_email"
    assert outreach.record_call(pid, "callback", "after 3pm")["status"] == "no_email"
    with pytest.raises(ValueError):
        outreach.record_call(pid, "maybe")
    with pytest.raises(LookupError):
        outreach.record_call(999999, "no_answer")


def test_a_call_does_not_undo_an_unsubscribe():
    cid = campaign()
    pid = add(cid, email=f"{uuid.uuid4().hex[:8]}@outreach.test")
    prospects.set_status(pid, "unsubscribed")
    assert outreach.record_call(pid, "interested")["status"] == "unsubscribed"


def test_call_endpoints():
    client, cid = TestClient(app), campaign()
    add(cid, "Csv Clinic")
    assert client.get("/admin/call-list").status_code == 403
    assert client.get(f"/admin/call-list?campaign_id={cid}&scope=bad", headers=H).status_code == 422
    rows = client.get(f"/admin/call-list?campaign_id={cid}", headers=H).json()
    assert rows[0]["name"] == "Csv Clinic"
    r = client.get(f"/admin/call-list.csv?campaign_id={cid}", headers=H)
    assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    parsed = list(csv.DictReader(io.StringIO(r.text)))
    assert parsed[0]["name"] == "Csv Clinic" and parsed[0]["phone"] and " | " in parsed[0]["talking_points"] or parsed[0]["talking_points"]
    pid = rows[0]["id"]
    assert client.post(f"/admin/prospects/{pid}/call", json={"outcome": "callback", "note": "later"}, headers=H).json()["status"] == "no_email"
    assert client.post(f"/admin/prospects/{pid}/call", json={"outcome": "nope"}, headers=H).status_code == 422
    assert client.post("/admin/prospects/999999/call", json={"outcome": "callback"}, headers=H).status_code == 404
