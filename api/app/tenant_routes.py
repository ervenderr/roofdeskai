"""GET /tenant/me: what a workflow needs to know about its own tenant (tenant key)."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from .auth import require_tenant
from .db import system
from .pack import get_pack
from .tenants import owner_email

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("/me")
def me(tenant: str = Depends(require_tenant)):
    pack = get_pack(tenant)
    with system() as c:
        slug = c.execute(text("SELECT slug FROM tenants WHERE id=:t"), {"t": tenant}).scalar_one()
    blocks = {"services": pack.services, "capacity": pack.capacity, "connectors": pack.connectors,
              "reviews": pack.meta.reviews, "intake": pack.meta.intake}
    return {"tenant_id": tenant, "slug": slug, "name": pack.meta.business, "owner_email": owner_email(pack),
            "timezone": pack.meta.timezone, "locale": pack.meta.locale,
            "enabled_modules": [k for k, v in blocks.items() if v is not None]}
