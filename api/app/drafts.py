"""Tenant-scoped drafts queue (quotes, review replies). Approve/reject only mark a decision; nothing is sent or posted."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from .auth import require_tenant
from .db import record_event, tx

router = APIRouter(prefix="/drafts", tags=["drafts"])

COLS = "id, kind, status, payload, input_hash, created_at, decided_at"
OPEN_STATUSES = "('pending','needs_human')"  # must match the drafts_open_dedupe partial index


def require_module(obj, name: str):
    """Absent optional pack module = disabled for this tenant."""
    if obj is None:
        raise HTTPException(404, "module not enabled")
    return obj


def create_or_get_draft(tenant_id: str, kind: str, status: str, payload: dict, input_hash: str) -> tuple[int, bool]:
    """Insert an open draft, or return the existing open draft with the same (kind, input_hash): (id, deduped)."""
    with tx(tenant_id) as c:
        new = c.execute(text(
            "INSERT INTO drafts (tenant_id, kind, status, payload, input_hash) "
            "VALUES (:t, :k, :s, CAST(:p AS jsonb), :h) "
            f"ON CONFLICT (tenant_id, kind, input_hash) WHERE status IN {OPEN_STATUSES} DO NOTHING RETURNING id"),
            {"t": tenant_id, "k": kind, "s": status, "p": json.dumps(payload), "h": input_hash}).scalar()
        if new is not None:
            record_event(c, tenant_id, None, "draft_created", {"draft_id": new, "kind": kind, "status": status})
            return new, False
        existing = c.execute(text(
            f"SELECT id FROM drafts WHERE tenant_id=:t AND kind=:k AND input_hash=:h AND status IN {OPEN_STATUSES}"),
            {"t": tenant_id, "k": kind, "h": input_hash}).scalar_one()
        return existing, True


def _row(r) -> dict:
    return {**r, "created_at": r["created_at"].isoformat(), "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None}


@router.get("")
def list_drafts(status: Literal["pending", "approved", "rejected", "needs_human", "sent"] | None = None,
                kind: Literal["quote", "review_reply"] | None = None, tenant: str = Depends(require_tenant)):
    with tx(tenant) as c:
        rows = c.execute(text(
            f"SELECT {COLS} FROM drafts WHERE tenant_id=:t AND (CAST(:s AS text) IS NULL OR status=:s) "
            "AND (CAST(:k AS text) IS NULL OR kind=:k) ORDER BY id DESC LIMIT 200"),
            {"t": tenant, "s": status, "k": kind}).mappings().all()
    return [_row(r) for r in rows]


@router.get("/{draft_id}")
def get_draft(draft_id: int, tenant: str = Depends(require_tenant)):
    with tx(tenant) as c:
        r = c.execute(text(f"SELECT {COLS} FROM drafts WHERE id=:i AND tenant_id=:t"), {"i": draft_id, "t": tenant}).mappings().first()
    if not r:
        raise HTTPException(404, "draft not found")
    return _row(r)


def _decide(tenant: str, draft_id: int, new: str, from_statuses: tuple[str, ...]) -> dict:
    with tx(tenant) as c:
        r = c.execute(text(
            f"UPDATE drafts SET status=:n, decided_at=now() WHERE id=:i AND tenant_id=:t AND status = ANY(:f) RETURNING {COLS}"),
            {"n": new, "i": draft_id, "t": tenant, "f": list(from_statuses)}).mappings().first()
        if r:
            record_event(c, tenant, None, "draft_decided", {"draft_id": draft_id, "kind": r["kind"], "status": new})
            return _row(r)
        exists = c.execute(text("SELECT 1 FROM drafts WHERE id=:i AND tenant_id=:t"), {"i": draft_id, "t": tenant}).first()
    raise HTTPException(409 if exists else 404, "draft not in a decidable state" if exists else "draft not found")


@router.post("/{draft_id}/approve")
def approve(draft_id: int, tenant: str = Depends(require_tenant)):
    return _decide(tenant, draft_id, "approved", ("pending",))


@router.post("/{draft_id}/reject")
def reject(draft_id: int, tenant: str = Depends(require_tenant)):
    return _decide(tenant, draft_id, "rejected", ("pending", "needs_human"))
