---
phase: 06-per-tenant-keys-and-rls-enforcement
plan: 04
requirements: [SEC-02, SEC-05]
key-files:
  created: [api/app/test_routes_scope.py]
  modified: [api/app/admin.py, api/app/main.py, api/app/test_chat_security.py, api/app/test_health.py]
metrics:
  tasks: 2
  completed: 2026-11-04
---

# Phase 6 Plan 04: Credentials wired into routes Summary

/chat takes `Depends(chat_tenant)` and passes the tenant to `handle_turn`, `token_matches`, `conversation_token` and the closing `tx`; body `tenant_id` and `X-Tenant-Id` are ignored. `admin.py` drops the router-level `require_admin` dependency; the ten listed routes each take `Depends(require_scope)` (read routes pass `_tenant=scope.tenant_id` to `_rows`; admin without header stays cross-tenant). `/metrics` for a tenant scope omits `outreach` and returns `eval_runs=[]`. Write paths (resolve, inbound x3, draft incl. `get_pack`, `_redelivered`) use `_write_tenant`: scope tenant, else `default_tenant_id` with `log.warning`. followups-due now also returns `tenant_id`. `require_admin` is still importable from `.admin`. Outreach/pilot/intake/triage routes untouched (D-08).

Commits: 406bfb1 (tests, RED), then feat commit "derive tenant from credential on chat and admin routes" a8fd869.

## Verification (real output)

- RED: `make g-test ARGS="app/test_routes_scope.py -q"` -> 14 FAILED (22 tests in file).
- GREEN: `app/test_routes_scope.py app/test_admin.py app/test_chat_security.py` -> 40 passed.
- `make g-test` -> `582 passed, 1 warning in 14.03s` (was 560).
- `grep -n default_tenant_id api/app/main.py` -> no output. `grep dependencies=\[Depends(require_admin)\] admin.py` -> no output. `grep -c "Depends(require_scope)" admin.py` -> 10.
- In the api container: `from app.admin import require_admin` -> `import ok`. test_triage / test_outreach are part of the full 582.

## Deviations

- **D-06 deviation (b), as planned:** admin-key callers of inbound, followup draft and escalation resolve accept optional `X-Tenant-Id`, else fall back to `default_tenant_id` with a logged warning until Phase 8 migrates n8n to tenant keys. `default_tenant_id` also stays for triage.
- **(c) DEPLOY ACTION REQUIRED:** keyless /chat only works with `PUBLIC_DEMO_TENANT_ID` set (default unset). Set it to `00000000-0000-0000-0000-000000000001` at deploy or roofdeskai.com /chat returns 401. Not deployed or set by me.
- **[Rule 3]** `test_chat_security.py` (autouse fixture sets demo tenant) and `test_health.py::test_chat_rejects_empty` (now sets demo tenant; 401 precedes 422 without a key) needed updating for the new /chat contract. test_health.py was not in the plan's file list.

## Not verified

- No live HTTP check against the running API or n8n flows; TestClient only. n8n workflows still call with the admin key and rely on the default-tenant fallback (not exercised against real n8n).
- No eval run (none required). CORS allow_headers unchanged on purpose.
- One earlier -k partial run hit a teardown FK error (`faq_chunks` on tenants delete) in conftest cleanup; it did not recur in the three subsequent runs, including the full suite, and I did not investigate the cause.
