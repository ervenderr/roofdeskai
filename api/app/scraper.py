"""Client for the gosom/google-maps-scraper web API (compose service `scraper`) and its CSV output."""
import csv
import io
import json
import re

import httpx

from .config import settings

RUNNING = {"working", "pending", "queued", "running", ""}
DONE = {"ok"}
JSON_COLUMNS = ("open_hours", "complete_address", "user_reviews", "user_reviews_extended", "emails")
csv.field_size_limit(20_000_000)  # review columns are large


class ScraperError(Exception):
    pass


def _request(method: str, path: str, **kw) -> httpx.Response:
    try:
        r = httpx.request(method, f"{settings.scraper_url}{path}", timeout=60, **kw)
    except httpx.HTTPError as e:
        raise ScraperError(f"scraper unreachable ({type(e).__name__})") from e
    if r.status_code >= 400:
        raise ScraperError(f"scraper returned {r.status_code} for {method} {path}")
    return r


def start_job(name: str, keywords: list[str], depth: int, email: bool, max_time_s: int, lang: str = "en") -> str:
    r = _request("POST", "/api/v1/jobs", json={"name": name, "keywords": keywords, "lang": lang, "depth": depth,
                                               "email": email, "max_time": max_time_s})
    job_id = r.json().get("id")
    if not job_id:
        raise ScraperError("scraper did not return a job id")
    return job_id


def job_status(job_id: str) -> str:
    d = _request("GET", f"/api/v1/jobs/{job_id}").json()
    return str(d.get("Status") or d.get("status") or "").lower()


def rows_from_csv(text: str) -> list[dict]:
    """The scraper's CSV stores nested fields as JSON strings. Decode them so `prospects.normalize` sees real
    structures. `emails` may be JSON or a delimited string. Unparseable cells become None, never an error."""
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        for col in JSON_COLUMNS:
            v = row.get(col)
            if v is None or v in ("", "null"):
                row[col] = None
            elif v[:1] in "[{":
                try:
                    row[col] = json.loads(v)
                except ValueError:
                    row[col] = None
            elif col == "emails":
                row[col] = [e for e in re.split(r"[,;\s]+", v) if e]
        rows.append(row)
    return rows


def download_rows(job_id: str) -> list[dict]:
    return rows_from_csv(_request("GET", f"/api/v1/jobs/{job_id}/download").text)
