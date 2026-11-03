---
phase: 06-per-tenant-keys-and-rls-enforcement
plan: 03
requirements: [SEC-01, SEC-05]
key-files:
  created: [api/app/auth.py, api/app/tenant_admin.py, api/app/test_keys.py]
  modified: [api/app/admin.py, api/app/main.py]
metrics:
  tasks: 2
  completed: 2026-11-04
---

# Phase 6 Plan 03: Per-tenant keys and admin endpoints Summary

`auth.py` holds `require_admin` (moved, re-exported from `admin.py`), `Scope`, `require_tenant`, `require_scope`, `chat_tenant`, and `issue_key`/`rotate_key`/`revoke_key`/`list_keys`. Keys are `rd_live_` + `token_urlsafe(32)`, stored as sha256 hex, looked up in `system()` with `revoked_at IS NULL` plus `hmac.compare_digest`; prefix/length (128) precheck before any DB call; every failure is `401 {"detail":"unauthorized"}`. Rotate is one transaction (revoke old, 404 rolls back the insert). `tenant_admin.py` (admin-key only): `GET/POST /admin/tenants`, `POST/GET /admin/tenants/{tid}/keys`, `.../keys/{kid}/rotate`, `.../revoke`; bad uuid 400, unknown tenant 404, hash never returned. No existing route's auth was changed (plan 04).

Commits: 28d114a (tests, RED: collection error, auth module missing), then feat commit "add per-tenant API keys and super-admin tenant endpoints".

## Verification (real output)

- RED: `make g-test ARGS="app/test_keys.py -q"` -> `ERROR app/test_keys.py ... Interrupted: 1 error during collection`.
- GREEN: `app/test_keys.py` 17 tests all passed (17 dots).
- `make g-test` -> `560 passed, 1 warning in 13.97s` (was 543; +17).
- `grep key_hash api/app/tenant_admin.py` -> no hits; `compare_digest` present in auth.py.

## Deviations

None to the plan. Tests exercise the dependencies through a small probe FastAPI app in test_keys.py.

## Not verified

- No eval run (none required). No live HTTP check against the running API beyond TestClient (no lifespan).
- `POST /admin/tenants` (ensure_tenant) is only checked for tenant-key rejection, not for a successful create.
- No brute-force rate limiting on X-API-Key (out of plan scope).
