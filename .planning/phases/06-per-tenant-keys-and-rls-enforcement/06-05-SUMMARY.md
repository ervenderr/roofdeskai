---
phase: 06-per-tenant-keys-and-rls-enforcement
plan: 05
requirements: [SEC-02, SEC-03]
key-files:
  modified: [api/app/db.py, api/app/agent.py, api/app/tools.py, api/app/faq.py, api/app/pack.py, scripts/seed_demo.py, api/app/test_tenancy.py, api/app/test_agent.py, api/app/test_admin.py, api/app/test_chat_security.py, api/app/test_pack.py, api/app/test_service_type.py]
metrics:
  tasks: 2
  completed: 2026-11-04
---

# Phase 6 Plan 05: Explicit tenant everywhere Summary

The silent Summit fallback is gone from every tenant data path. `tx`, `record_event`, `get_pack`, `seed_faq` validate with `uuid.UUID(str(tenant_id))`, so None raises before any SQL. `handle_turn(..., *, tenant_id)` is required, `_t()` is deleted, `conversation_token` and `token_matches` take a required tenant. In `tools.py` every function has a required `tenant_id` (keyword-only where a default precedes it); `run(..., *, tenant_id)` always injects it. `tenants.py` needed no change (it already passed a tenant).

Commits: 1cc30a0 (production) , a030ec9 (tests); the tests were written first (RED: 7 new failures) in the same working session but committed after the code, per the "production first, then test threading" instruction.

## Verification (real output)

- RED: `app/test_tenancy.py` -> 7 FAILED (tx x2, record_event, get_pack/seed_faq x2, agent+tools, grep gate).
- `make g-test` -> `588 passed, 1 warning in 15.76s` (was 582; +6 new tests).
- `grep -n default_tenant_id agent.py tools.py faq.py pack.py db.py main.py` -> no output. The grep-gate test (`test_no_default_tenant_in_tenant_code`) also asserts no raw `engine` in agent/tools/faq/main.
- Smoke (run after pytest finished, slots re-seeded for both tenants via `ensure_slots`): roofing `--ids qual-1` -> qualified 1/1 (100%); dental `--pack bright-smile-dental --ids dqual-1` -> qualified 1/1 (100%). Both under RLS.

## Deviations

- **D-06 deviation (b), as planned:** `default_tenant_id` remains in admin.py (legacy admin-key fallback), triage.py (own-funnel pack) and config.py/tests.
- **[Rule 3]** `scripts/seed_demo.py` called `handle_turn` and `tx()` with no tenant; now passes `settings.default_tenant_id` (Summit demo data). Not in plan's file list. Not executed.
- `test_tenancy.py` tenant constants: `T` is defined per test file (not in conftest) to avoid conftest imports.
- The 06-04 conftest FK teardown error (faq_chunks vs tenants) did not recur in the full run; conftest untouched.
- Plan lists `tenants.py`, `test_isolation.py`, `test_logging_tenant.py`, `test_eval_gate.py` as modified; none needed changes (already explicit).

## Not verified

- Only single-scenario smokes, not the full 94/96 gate. Smoke runs wrote untracked `evals/reports/*-partial.md` (not committed).
- `scripts/seed_demo.py` and any n8n flows were not exercised.
