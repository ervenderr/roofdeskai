"""Onboard a business pack: python -m scripts.new_business <slug> (make new-business PACK=<slug>).
Validates the pack, registers the tenant, runs the escalation and injection scenarios in-process (local LLM only,
no report written), then a deterministic cross-tenant check. Exit 0 pass, 1 failure, 2 usage."""
import re
import sys

from evals import runner
from evals.runner import assert_local_only, load_scenarios, run_suite
from sqlalchemy import text

from app import tools
from app.config import settings
from app.db import system, tx
from app.pack import PackError, get_pack, load_pack
from app.tenants import ensure_tenant, sync_faq
from app.tools import ensure_slots

SMOKE = ("escalation", "injection")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")


class SmokeError(Exception):
    pass


def select_smoke(scenarios: list[dict]) -> list[dict]:
    for cat in SMOKE:
        if not any(s["category"] == cat for s in scenarios):
            raise SmokeError(f"pack has no {cat} scenarios")
    return [s for s in scenarios if s["category"] in SMOKE]


def evaluate(results: list) -> list[str]:
    return [sc["id"] for sc, _, failed in results if failed]


def reminder(tenant_id: str) -> str:
    return (f"tenant {tenant_id} registered.\n"
            "Every tenant needs a key in TENANT_API_KEYS (POST /admin/tenants/{id}/keys). "
            "Without one the n8n loop aborts at Check key.\n"
            "Next: run make gen-docs")


def cross_tenant_check(tenant_id: str) -> list[str]:
    """No-LLM isolation check; returns problems (empty = pass)."""
    own = {e.text for e in get_pack(tenant_id).faq}
    probe = sorted(own)[0] if own else ""
    got = tools.lookup_faq(probe, k=50, tenant_id=tenant_id)["chunks"]
    if not got or probe not in got:
        return ["own-tenant FAQ lookup did not return the tenant's own chunk (check is not meaningful)"]
    with system() as c:
        others = [str(r[0]) for r in c.execute(text("SELECT id FROM tenants WHERE pack_slug IS NOT NULL AND id <> :t"), {"t": tenant_id})]
    problems = []
    for o in others:
        try:
            queries = sorted({e.text for e in get_pack(o).faq})
        except PackError:  # a tenant whose pack is gone has no FAQ to probe with
            continue
        for q in queries:
            if not set(tools.lookup_faq(q, k=50, tenant_id=tenant_id)["chunks"]) <= own:
                problems.append(f"lookup_faq for tenant {tenant_id} returned a chunk outside its own FAQ (query from tenant {o})")
                break
    with tx(tenant_id) as c:
        n = c.execute(text("SELECT count(*) FROM leads WHERE tenant_id <> :t"), {"t": tenant_id}).scalar()
    if n:
        problems.append(f"RLS: {n} foreign lead rows visible")
    return problems


def main(slug: str) -> int:
    if not SLUG.fullmatch(slug):
        print(f"invalid pack slug {slug!r}")
        return 2
    settings.mail_transport = "mailpit"  # smoke bookings must not reach a real mailbox
    try:
        load_pack(slug)
        t = ensure_tenant(slug)
        ensure_slots(t)
        sync_faq(t)
        smoke = select_smoke(load_scenarios(slug))
    except (PackError, SmokeError) as e:
        print(e)
        return 1
    results, cids = run_suite(smoke, t)
    assert_local_only(cids, t)
    bad = evaluate(results)
    if bad:  # one rerun of the failing ids only (local model flakiness)
        again, cids = run_suite([s for s in smoke if s["id"] in bad], t)
        assert_local_only(cids, t)
        bad = evaluate(again)
    problems = [f"smoke scenario failed: {i}" for i in bad]
    problems += cross_tenant_check(t)
    if problems:
        print("\n".join(problems))
        return 1
    print(f"smoke OK: {len(smoke)} scenarios, cross-tenant check OK")
    print(reminder(t))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else (print("usage: python -m scripts.new_business <slug>") or 2))
