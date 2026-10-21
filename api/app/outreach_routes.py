"""Outbound prospecting endpoints. Admin-key protected, like the rest of the admin API."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from . import outreach, prospects
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
