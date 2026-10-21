"""Outbound prospecting endpoints. Admin-key protected, like the rest of the admin API."""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import text

from . import outreach, prospects, scraper, scrapes
from .admin import _rows, require_admin
from .db import engine

router = APIRouter(dependencies=[Depends(require_admin)])


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    auto_approve: bool = False
    daily_cap: int = Field(20, ge=1, le=500)


class CampaignPatch(BaseModel):
    auto_approve: bool | None = None
    daily_cap: int | None = Field(None, ge=1, le=500)
    active: bool | None = None


class ImportIn(BaseModel):
    rows: list[dict] = Field(max_length=2000)


class ScrapeIn(BaseModel):
    campaign_id: int
    queries: list[str] = Field(min_length=1, max_length=scrapes.MAX_QUERIES)
    depth: int = Field(1, ge=1, le=scrapes.MAX_DEPTH)
    email: bool = False  # crawl each business website for an email: much slower, but most listings have none otherwise

    @field_validator("queries")
    @classmethod
    def short_queries(cls, v):
        if any(not 3 <= len(q.strip()) <= 120 for q in v):
            raise ValueError("each query must be 3 to 120 characters, e.g. 'dentist in Davao City'")
        return v


class CallIn(BaseModel):
    outcome: str = Field(pattern="^(no_answer|callback|wrong_number|interested|not_interested|do_not_contact)$")
    note: str = Field("", max_length=500)


class EditIn(BaseModel):
    subject: str
    body: str


class EventIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    kind: str = Field(pattern="^(reply|bounce|unsubscribe)$")
    body: str = Field("", max_length=10000)


@router.post("/admin/campaigns")
def create_campaign(body: CampaignIn):
    with engine.begin() as c:
        cid = c.execute(text("INSERT INTO campaigns (name, category, city, auto_approve, daily_cap) "
                             "VALUES (:name, :category, :city, :auto_approve, :daily_cap) RETURNING id"), body.model_dump()).scalar_one()
    return {"id": cid}


@router.get("/admin/campaigns")
def list_campaigns():
    return _rows("""SELECT c.*, count(p.id) AS prospects FROM campaigns c LEFT JOIN prospects p ON p.campaign_id = c.id
                    GROUP BY c.id ORDER BY c.id DESC""")


@router.patch("/admin/campaigns/{cid}")
def patch_campaign(cid: int, body: CampaignPatch):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "nothing to change")
    sets = ", ".join(f"{k}=:{k}" for k in changes)  # keys come from the model, never from the request
    with engine.begin() as c:
        if not c.execute(text(f"UPDATE campaigns SET {sets} WHERE id=:_id RETURNING id"), {**changes, "_id": cid}).first():
            raise HTTPException(404, "campaign not found")
    return {"id": cid, **changes}


@router.post("/admin/campaigns/{cid}/import")
def import_prospects(cid: int, body: ImportIn):
    if not _rows("SELECT 1 FROM campaigns WHERE id=:i", i=cid):
        raise HTTPException(404, "campaign not found")
    return prospects.import_rows(cid, body.rows)


@router.get("/admin/prospects")
def list_prospects(status: str | None = None, campaign_id: int | None = None, limit: int = 200):
    return _rows("""SELECT id, campaign_id, name, category, address, email, website, rating, review_count, score,
                           pain_mentions, status, created_at FROM prospects
                    WHERE (CAST(:s AS TEXT) IS NULL OR status = :s) AND (CAST(:c AS INT) IS NULL OR campaign_id = :c)
                    ORDER BY score DESC, id LIMIT :n""", s=status, c=campaign_id, n=min(limit, 500))


@router.get("/admin/prospects/{pid}")
def get_prospect(pid: int):
    rows = _rows("SELECT * FROM prospects WHERE id=:i", i=pid)
    if not rows:
        raise HTTPException(404, "prospect not found")
    return {"prospect": rows[0],
            "messages": _rows("SELECT * FROM outreach_messages WHERE prospect_id=:i ORDER BY step", i=pid),
            "events": _rows("SELECT kind, detail, created_at FROM prospect_events WHERE prospect_id=:i ORDER BY id", i=pid)}


@router.get("/admin/outreach/queue")
def approval_queue():
    return _rows("""SELECT m.id, m.prospect_id, m.step, m.subject, m.body, m.source, m.created_at, p.name, p.email, p.score
                    FROM outreach_messages m JOIN prospects p ON p.id = m.prospect_id
                    WHERE m.status = 'drafted' ORDER BY p.score DESC, m.id""")


@router.post("/admin/outreach/draft-pending")
def draft_pending(limit: int = 5, campaign_id: int | None = None):
    return outreach.draft_pending(min(limit, 20), campaign_id)


def _guard(fn, mid: int):
    try:
        fn(mid)
    except LookupError:
        raise HTTPException(404, "no drafted message with that id")
    return {"id": mid, "ok": True}


@router.post("/admin/outreach/{mid}/approve")
def approve(mid: int):
    return _guard(outreach.approve, mid)


@router.post("/admin/outreach/{mid}/reject")
def reject(mid: int):
    return _guard(outreach.reject, mid)


@router.post("/admin/outreach/{mid}/edit")
def edit(mid: int, body: EditIn):
    try:
        outreach.edit(mid, body.subject, body.body)
    except ValidationError:
        raise HTTPException(422, "subject must be 3-70 characters and the body 40-900")
    except LookupError:
        raise HTTPException(404, "no drafted message with that id")
    return {"id": mid, "ok": True}


@router.post("/admin/outreach/schedule-followups")
def schedule_followups(campaign_id: int | None = None):
    return outreach.schedule_followups(campaign_id=campaign_id)


@router.post("/admin/outreach/send-due")
def send_due(campaign_id: int | None = None):
    try:
        return outreach.send_due(campaign_id=campaign_id)
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@router.get("/admin/outreach/metrics")
def outreach_metrics():
    return outreach.metrics()


@router.post("/webhooks/outreach-event")
def outreach_event(body: EventIn):
    return outreach.handle_event(body.email, body.kind, body.body)


@router.post("/admin/scrapes")
def start_scrape(body: ScrapeIn):
    if not _rows("SELECT 1 FROM campaigns WHERE id=:i", i=body.campaign_id):
        raise HTTPException(404, "campaign not found")
    try:
        return scrapes.start_run(body.campaign_id, body.queries, body.depth, body.email)
    except scrapes.DailyLimit as e:
        raise HTTPException(429, str(e))
    except scraper.ScraperError as e:
        raise HTTPException(503, f"{e}. Start it with: docker compose --profile scraper up -d scraper")


@router.get("/admin/scrapes")
def list_scrapes():
    return scrapes.list_runs()


@router.post("/admin/scrapes/sync")
def sync_scrapes():
    return scrapes.sync_runs()


CALL_CSV_COLUMNS = ["score", "name", "category", "phone", "city", "address", "website", "maps_url", "rating", "review_count",
                    "call_outcome", "talking_points", "opener"]


@router.get("/admin/call-list")
def get_call_list(campaign_id: int | None = None, scope: str = "no_email", limit: int = 100):
    if scope not in ("no_email", "all"):
        raise HTTPException(422, "scope must be no_email or all")
    return outreach.call_list(campaign_id, scope, min(limit, 500))


@router.get("/admin/call-list.csv")
def get_call_list_csv(campaign_id: int | None = None, scope: str = "no_email"):
    rows = get_call_list(campaign_id, scope, 500)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CALL_CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({**r, "talking_points": " | ".join(r["talking_points"])})
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=call-list.csv"})


@router.post("/admin/prospects/{pid}/call")
def log_call(pid: int, body: CallIn):
    try:
        return outreach.record_call(pid, body.outcome, body.note)
    except LookupError:
        raise HTTPException(404, "prospect not found")
