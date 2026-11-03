"""Credentials: super-admin key (X-Admin-Key) and per-tenant API keys (X-API-Key, sha256 at rest)."""
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException
from sqlalchemy import text

from .config import settings
from .db import system

KEY_PREFIX = "rd_live_"
MAX_KEY_LEN = 128


@dataclass(frozen=True)
class Scope:
    tenant_id: str | None
    is_admin: bool


def require_admin(x_admin_key: str = Header("")):
    if not settings.admin_api_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(403, "forbidden")


def _unauthorized() -> HTTPException:
    return HTTPException(401, "unauthorized")


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _resolve(key: str) -> str:
    """Tenant id for an active key; the same generic 401 for every failure."""
    if not key.startswith(KEY_PREFIX) or len(key) > MAX_KEY_LEN:
        raise _unauthorized()
    digest = _hash(key)
    with system() as c:
        row = c.execute(text("SELECT tenant_id, key_hash FROM tenant_api_keys WHERE key_hash=:h AND revoked_at IS NULL"),
                        {"h": digest}).first()
    if not row or not hmac.compare_digest(row.key_hash, digest):
        raise _unauthorized()
    return str(row.tenant_id)


def require_tenant(x_api_key: str = Header("")) -> str:
    return _resolve(x_api_key)


def require_scope(x_api_key: str = Header(""), x_admin_key: str = Header(""), x_tenant_id: str = Header("")) -> Scope:
    if x_api_key:  # present-but-invalid never falls through to the admin path
        return Scope(_resolve(x_api_key), False)
    require_admin(x_admin_key)
    if not x_tenant_id:
        return Scope(None, True)
    try:
        return Scope(str(uuid.UUID(x_tenant_id)), True)
    except ValueError:
        raise HTTPException(400, "invalid X-Tenant-Id") from None


def chat_tenant(x_api_key: str = Header("")) -> str:
    if x_api_key:
        return _resolve(x_api_key)
    try:
        return str(uuid.UUID(settings.public_demo_tenant_id))
    except ValueError:
        raise _unauthorized() from None


def issue_key(tenant_id: str, label: str | None = None) -> dict:
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    with system() as c:
        kid = _insert(c, tenant_id, key, label)
    return {"id": kid, "key": key, "label": label}


def _insert(c, tenant_id, key, label) -> int:
    return c.execute(text("INSERT INTO tenant_api_keys (tenant_id, key_hash, label) VALUES (:t, :h, :l) RETURNING id"),
                     {"t": tenant_id, "h": _hash(key), "l": label}).scalar_one()


def _revoke(c, tenant_id, key_id) -> None:
    n = c.execute(text("UPDATE tenant_api_keys SET revoked_at=now() WHERE id=:i AND tenant_id=:t AND revoked_at IS NULL"),
                  {"i": key_id, "t": tenant_id}).rowcount
    if n != 1:
        raise HTTPException(404, "key not found")


def rotate_key(tenant_id: str, key_id: int, label: str | None = None) -> dict:
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    with system() as c:  # one transaction: a 404 on the old key rolls back the insert
        _revoke(c, tenant_id, key_id)
        kid = _insert(c, tenant_id, key, label)
    return {"id": kid, "key": key, "label": label}


def revoke_key(tenant_id: str, key_id: int) -> None:
    with system() as c:
        _revoke(c, tenant_id, key_id)


def list_keys(tenant_id: str) -> list[dict]:
    with system() as c:
        return [dict(r) for r in c.execute(text("SELECT id, label, created_at, revoked_at FROM tenant_api_keys "
                                                "WHERE tenant_id=:t ORDER BY id"), {"t": tenant_id}).mappings()]
