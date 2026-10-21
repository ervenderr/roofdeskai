"""Scrape runs: start a Google Maps scraper job for a campaign, then import its results once it finishes."""
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from . import prospects, scraper
from .config import settings
from .db import engine

log = logging.getLogger("leadpilot.scrapes")

MAX_QUERIES, MAX_DEPTH = 10, 5
BASE_TIME_S, PER_QUERY_S = 120, 90  # scraper max_time = base + per query per depth level; email crawling adds more
EMAIL_EXTRA_S = 240


class DailyLimit(Exception):
    pass


def start_run(campaign_id: int, queries: list[str], depth: int = 1, email: bool = False) -> dict:
    """Start a scraper job. Raises scraper.ScraperError if the service is down, DailyLimit past the polite cap."""
    queries = [q.strip() for q in queries if q.strip()]
    with engine.connect() as c:
        used = c.execute(text("SELECT COALESCE(sum(jsonb_array_length(queries)), 0) FROM scrape_runs "
                              "WHERE created_at > now() - interval '24 hours'")).scalar()
    if used + len(queries) > settings.scrape_queries_per_day:
        raise DailyLimit(f"{used} queries already run in the last 24 hours (limit {settings.scrape_queries_per_day})")
    max_time = BASE_TIME_S + PER_QUERY_S * len(queries) * depth + (EMAIL_EXTRA_S if email else 0)
    job_id = scraper.start_job(f"leadpilot-{campaign_id}", queries, depth, email, max_time)
    with engine.begin() as c:
        rid = c.execute(text("INSERT INTO scrape_runs (campaign_id, job_id, queries, depth, email) "
                             "VALUES (:c, :j, CAST(:q AS jsonb), :d, :e) RETURNING id"),
                        {"c": campaign_id, "j": job_id, "q": json.dumps(queries), "d": depth, "e": email}).scalar_one()
    return {"id": rid, "job_id": job_id, "max_time_s": max_time}


def _finish(run_id: int, status: str, result: dict | None = None, error: str | None = None) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE scrape_runs SET status=:s, result_json=CAST(:r AS jsonb), error=:e, finished_at=now() "
                       "WHERE id=:i AND status='running'"),
                  {"s": status, "r": json.dumps(result) if result else None, "e": error, "i": run_id})


def sync_runs(now: datetime | None = None) -> dict:
    """Check every running job; import finished ones into their campaign (once), mark failed or stuck ones."""
    now = now or datetime.now(timezone.utc)
    with engine.connect() as c:
        runs = [dict(r) for r in c.execute(text(
            "SELECT id, campaign_id, job_id, depth, email, created_at, jsonb_array_length(queries) AS n "
            "FROM scrape_runs WHERE status='running' ORDER BY id")).mappings()]
    out = {"running": 0, "imported_runs": 0, "failed": 0, "prospects_imported": 0, "duplicates": 0, "no_email": 0}
    for r in runs:
        deadline = r["created_at"] + timedelta(seconds=2 * (BASE_TIME_S + PER_QUERY_S * r["n"] * r["depth"]
                                                           + (EMAIL_EXTRA_S if r["email"] else 0)))
        try:
            status = scraper.job_status(r["job_id"])
            if status in scraper.DONE:
                counts = prospects.import_rows(r["campaign_id"], scraper.download_rows(r["job_id"]))
                _finish(r["id"], "imported", counts)
                out["imported_runs"] += 1
                for k, key in (("prospects_imported", "imported"), ("duplicates", "duplicates"), ("no_email", "no_email")):
                    out[k] += counts[key]
                continue
            if status not in scraper.RUNNING:
                _finish(r["id"], "failed", error=f"scraper job ended with status '{status}'")
                out["failed"] += 1
                continue
        except scraper.ScraperError as e:
            log.warning("scrape run %s: %s", r["id"], e)
        if now > deadline:
            _finish(r["id"], "failed", error="timed out waiting for the scraper")
            out["failed"] += 1
        else:
            out["running"] += 1
    return out


def list_runs(limit: int = 50) -> list[dict]:
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(
            """SELECT s.id, s.campaign_id, cm.name AS campaign, s.job_id, s.queries, s.depth, s.email, s.status,
                      s.result_json, s.error, s.created_at, s.finished_at
               FROM scrape_runs s JOIN campaigns cm ON cm.id = s.campaign_id ORDER BY s.id DESC LIMIT :n"""),
            {"n": limit}).mappings()]
