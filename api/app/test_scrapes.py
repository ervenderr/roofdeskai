import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import prospects, scraper, scrapes
from .config import settings
from .db import engine
from .main import app

H = {"X-Admin-Key": "k"}
NB = " "


def csv_text(rows: list[dict]) -> str:
    """A CSV shaped like the scraper's real output: nested fields are JSON strings."""
    cols = ["title", "category", "address", "phone", "website", "review_count", "review_rating", "place_id", "open_hours",
            "complete_address", "user_reviews", "user_reviews_extended", "emails"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue()


def sample_row(**kw) -> dict:
    return {"title": "Acme Dental", "category": "Dental clinic", "address": "1 A St, Agdao, Davao City", "phone": "0909 000 0000",
            "website": "https://acme.example.com", "review_count": "40", "review_rating": "4.600000", "place_id": uuid.uuid4().hex,
            "open_hours": json.dumps({"Monday": ["Closed"], "Friday": [f"9{NB}AM–4{NB}PM"], "Saturday": ["Closed"]}),
            "complete_address": json.dumps({"street": "1 A St", "city": "Davao City", "country": "PH"}),
            "user_reviews": json.dumps([{"Name": "X", "Rating": 1, "Description": "Nobody answers the phone here"}]),
            "user_reviews_extended": "null", "emails": "", **kw}


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "k")
    monkeypatch.setattr(scraper, "start_job", lambda *a, **k: f"job-{uuid.uuid4().hex[:8]}")


def campaign() -> int:
    with engine.begin() as c:
        return c.execute(text("INSERT INTO campaigns (name) VALUES ('scrape-test') RETURNING id")).scalar_one()


def run_status(rid: int) -> str:
    with engine.connect() as c:
        return c.execute(text("SELECT status FROM scrape_runs WHERE id=:i"), {"i": rid}).scalar()


def clean_runs():
    with engine.begin() as c:
        c.execute(text("DELETE FROM scrape_runs WHERE campaign_id IN (SELECT id FROM campaigns WHERE name='scrape-test')"))


@pytest.fixture(autouse=True)
def fresh():
    clean_runs()
    yield
    clean_runs()


# --- CSV decoding -----------------------------------------------------------------------------------

def test_rows_from_csv_decodes_json_cells_and_email_forms():
    rows = scraper.rows_from_csv(csv_text([sample_row(emails='["a@x.co","b@x.co"]'), sample_row(emails="c@x.co; d@x.co"),
                                          sample_row(open_hours="{not json", emails="")]))
    assert rows[0]["emails"] == ["a@x.co", "b@x.co"] and rows[1]["emails"] == ["c@x.co", "d@x.co"]
    assert rows[0]["open_hours"]["Monday"] == ["Closed"] and rows[0]["complete_address"]["city"] == "Davao City"
    assert rows[2]["open_hours"] is None and rows[2]["emails"] is None  # garbage cell becomes None, never an error
    assert rows[0]["user_reviews_extended"] is None


def test_scraped_row_normalizes_with_city_hours_and_reviews():
    p = prospects.normalize(scraper.rows_from_csv(csv_text([sample_row(emails='["Hello@Acme.example.com"]')]))[0])
    assert p["city"] == "Davao City" and p["email"] == "hello@acme.example.com" and p["rating"] == 4.6
    assert prospects.after_hours_gap(p["hours"]) and prospects.pain_mentions(p["review_texts"]) == 1


# --- runs -------------------------------------------------------------------------------------------

def test_start_run_records_the_job_and_enforces_the_daily_limit(monkeypatch):
    cid = campaign()
    r = scrapes.start_run(cid, ["dentist in Davao City", "  "], depth=2, email=True)
    assert run_status(r["id"]) == "running" and r["max_time_s"] > 0
    with engine.connect() as c:
        used = c.execute(text("SELECT COALESCE(sum(jsonb_array_length(queries)), 0) FROM scrape_runs "
                              "WHERE created_at > now() - interval '24 hours'")).scalar()
    monkeypatch.setattr(settings, "scrape_queries_per_day", used)
    with pytest.raises(scrapes.DailyLimit):
        scrapes.start_run(cid, ["one more"])


def test_sync_imports_a_finished_job_exactly_once(monkeypatch):
    cid = campaign()
    r = scrapes.start_run(cid, ["dentist in Davao City"])
    rows = scraper.rows_from_csv(csv_text([sample_row(emails="x@acme.example.com"), sample_row(emails=""), sample_row(title="")]))
    monkeypatch.setattr(scraper, "job_status", lambda j: "ok")
    monkeypatch.setattr(scraper, "download_rows", lambda j: rows)
    out = scrapes.sync_runs()
    assert out["imported_runs"] >= 1 and run_status(r["id"]) == "imported"
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM prospects WHERE campaign_id=:c"), {"c": cid}).scalar() == 2
    monkeypatch.setattr(scraper, "download_rows", lambda j: pytest.fail("a finished run must not be imported twice"))
    assert scrapes.sync_runs()["imported_runs"] == 0
    with engine.begin() as c:
        c.execute(text("DELETE FROM prospects WHERE campaign_id=:c"), {"c": cid})


def test_sync_leaves_running_jobs_and_fails_dead_or_stuck_ones(monkeypatch):
    cid = campaign()
    r = scrapes.start_run(cid, ["dentist in Davao City"])
    monkeypatch.setattr(scraper, "job_status", lambda j: "working")
    assert scrapes.sync_runs()["running"] >= 1 and run_status(r["id"]) == "running"
    monkeypatch.setattr(scraper, "job_status", lambda j: (_ for _ in ()).throw(scraper.ScraperError("down")))
    assert scrapes.sync_runs()["running"] >= 1 and run_status(r["id"]) == "running"  # a blip is not a failure
    later = datetime.now(timezone.utc) + timedelta(hours=3)
    assert scrapes.sync_runs(later)["failed"] >= 1 and run_status(r["id"]) == "failed"
    r2 = scrapes.start_run(cid, ["dentist in Davao City"])
    monkeypatch.setattr(scraper, "job_status", lambda j: "failed")
    scrapes.sync_runs()
    assert run_status(r2["id"]) == "failed"


# --- HTTP -------------------------------------------------------------------------------------------

def test_scrape_endpoints(monkeypatch):
    client = TestClient(app)
    cid = campaign()
    body = {"campaign_id": cid, "queries": ["dentist in Davao City"]}
    assert client.post("/admin/scrapes", json=body).status_code == 403
    assert client.post("/admin/scrapes", json=body, headers=H).status_code == 200
    assert client.post("/admin/scrapes", json={**body, "queries": []}, headers=H).status_code == 422
    assert client.post("/admin/scrapes", json={**body, "queries": ["x"]}, headers=H).status_code == 422
    assert client.post("/admin/scrapes", json={**body, "depth": 9}, headers=H).status_code == 422
    assert client.post("/admin/scrapes", json={**body, "campaign_id": 999999}, headers=H).status_code == 404
    assert any(r["campaign_id"] == cid for r in client.get("/admin/scrapes", headers=H).json())
    monkeypatch.setattr(scraper, "start_job", lambda *a, **k: (_ for _ in ()).throw(scraper.ScraperError("scraper unreachable")))
    down = client.post("/admin/scrapes", json=body, headers=H)
    assert down.status_code == 503 and "--profile scraper" in down.json()["detail"]
    monkeypatch.setattr(settings, "scrape_queries_per_day", 0)
    assert client.post("/admin/scrapes", json=body, headers=H).status_code == 429
