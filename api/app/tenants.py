"""Tenant directory helpers. Pure get-or-create; no HTTP, no keys (Phase 6)."""
from sqlalchemy import text

from .db import system, tx
from .faq import seed_faq
from .pack import PackError, get_pack, load_pack


def ensure_tenant(pack_slug: str) -> str:
    """Id of the tenant whose slug is the pack slug, creating it if absent. Idempotent and race-safe."""
    meta = load_pack(pack_slug).meta  # PackError before any insert
    with system() as c:
        c.execute(text("INSERT INTO tenants (slug, name, timezone, pack_slug) VALUES (:s, :n, :z, :s) "
                       "ON CONFLICT (slug) DO NOTHING"), {"s": pack_slug, "n": meta.business, "z": meta.timezone})
        row = c.execute(text("SELECT id, pack_slug FROM tenants WHERE slug=:s"), {"s": pack_slug}).one()
    if row.pack_slug != pack_slug:
        raise PackError(f"tenant {pack_slug!r} exists but is bound to pack {row.pack_slug!r}")
    return str(row.id)


def sync_faq(t: str) -> None:
    """Reseed only when the DB texts differ from the pack (seed_faq alone is a no-op once rows exist)."""
    want = sorted(e.text for e in get_pack(t).faq)
    with tx(t) as c:
        have = sorted(r[0] for r in c.execute(text("SELECT text FROM faq_chunks WHERE tenant_id=:t"), {"t": t}))
    if have != want:
        seed_faq(t, reload=True)
