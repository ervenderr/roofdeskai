"""Super-admin only (X-Admin-Key): tenant directory and per-tenant API key lifecycle."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import auth
from .db import system
from .pack import PackError
from .tenants import ensure_tenant

router = APIRouter(prefix="/admin/tenants", dependencies=[Depends(auth.require_admin)])


class KeyIn(BaseModel):
    label: str | None = Field(None, max_length=100)


class TenantIn(BaseModel):
    pack_slug: str = Field(min_length=1, max_length=100)


def _tenant(tid: str) -> str:
    try:
        tid = str(uuid.UUID(tid))
    except ValueError:
        raise HTTPException(400, "invalid tenant id") from None
    with system() as c:
        if not c.execute(text("SELECT 1 FROM tenants WHERE id=:t"), {"t": tid}).first():
            raise HTTPException(404, "tenant not found")
    return tid


@router.get("")
def list_tenants():
    with system() as c:
        return [{**r, "id": str(r["id"])} for r in c.execute(
            text("SELECT id, slug, name, timezone, pack_slug FROM tenants ORDER BY slug")).mappings()]


@router.post("")
def create_tenant(body: TenantIn):
    try:
        return {"id": ensure_tenant(body.pack_slug)}
    except PackError as e:
        raise HTTPException(400, str(e)) from None


@router.post("/{tid}/keys")
def issue(tid: str, body: KeyIn | None = None):
    return auth.issue_key(_tenant(tid), body.label if body else None)


@router.get("/{tid}/keys")
def keys(tid: str):
    return auth.list_keys(_tenant(tid))


@router.post("/{tid}/keys/{kid}/rotate")
def rotate(tid: str, kid: int, body: KeyIn | None = None):
    return auth.rotate_key(_tenant(tid), kid, body.label if body else None)


@router.post("/{tid}/keys/{kid}/revoke")
def revoke(tid: str, kid: int):
    auth.revoke_key(_tenant(tid), kid)
    return {"revoked": kid}
