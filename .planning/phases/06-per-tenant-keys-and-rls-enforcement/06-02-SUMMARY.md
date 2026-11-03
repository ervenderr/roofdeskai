---
phase: 06-per-tenant-keys-and-rls-enforcement
plan: 02
requirements: [SEC-03]
key-files:
  created: [db/migrations/005_rls.sql, db/migrations/006_tenant_api_keys.sql]
  modified: [api/app/db.py, api/app/bootstrap.py, api/app/config.py, api/app/main.py, docker-compose.yml, api/app/test_rls_proof.py, api/app/test_migrations.py, api/app/test_tenancy.py, api/app/test_admin.py, api/app/test_chat_security.py, api/app/test_eval_gate.py]
metrics:
  tasks: 2
  completed: 2026-11-04
---

# Phase 6 Plan 02: RLS enforcement Summary

Migration 005 creates non-owner role `app_rw`, explicit grants, FORCE RLS + `tenant_isolation` policy (with NULLIF) on 11 tables, and drops the 9 tenant_id defaults; 006 adds hash-only `tenant_api_keys`. `tx()` now runs on `app_engine` (app_rw); `engine` stays the owner/system engine. `assert_rls_enforced()` runs in the lifespan after bootstrap.

Commits: 259d66f (tests), 8b04835 (feat).

## Verification (real output)

- RED: first run of the new tests errored on the missing role/migrations (before implementation).
- `make g-up` applied 005/006 to the existing branch volume (no recreation); API log: `Application startup complete.`, zero "RLS not enforced" lines.
- `select count(*) from pg_class where relforcerowsecurity` -> `11`.
- `grep -c "ALTER DEFAULT" db/migrations/005_rls.sql` -> `0`.
- `make g-test` twice: `543 passed, 1 warning in 10.80s` and `543 passed, 1 warning in 11.47s` (was 497; +46 parametrized RLS tests).
- Eval smoke (after pytest, not concurrent), branch stack, roofing: `--ids disq-area,disq-8months` -> disqualified 2/2; `--category qualified` -> 12/12, schema validity 100% over 53 LLM calls. Full 94/96 gate and dental eval NOT run in this plan.

## Deviations

1. [Rule 1] `_run` in bootstrap.py now escapes `%` as `%%`: psycopg parses `%` in `exec_driver_sql` even without params, which broke `format('%I')` in 005. Applies to all migration files (no existing one used `%`).
2. [Rule 1] Research snippet `format(..., :p)` fails with IndeterminateDatatype; helper uses `CAST(:p AS text)`. `set_app_role_login(eng, password=None)` also lets tests reuse it.
3. [Rule 1] `test_eval_gate.test_run_scenario_detects_wrong_tenant_conversation` now accepts `NoResultFound` as well as `AssertionError`: under RLS the other tenant's row is invisible before the runner's guard fires (isolation is stronger, not weaker).
4. Catalog test excludes `tenant_api_keys` from the tenant_id column set (it has the column but is system-only, no RLS, by design D-03).
5. Reworded a comment in 005 so the acceptance grep for the forbidden phrase prints 0.
6. `tenants` grant: not needed; FK checks passed under app_rw, no grant added.

## Notes / not verified

- app_rw is a cluster-wide role: `test_rls_proof` resets its password in scratch use and restores `APP_DB_PASSWORD` in teardown (pytest and a running API share it; tests passed with the API up).
- `tx(None)` default-tenant fallback intentionally unchanged (plan 05 removes it).
- `test_slots_are_topped_up...` still deletes unbooked far-future slots for all tenants; dental slots must be re-seeded (ensure_slots) before a dental eval. Not touched here.
- Full roofing 94/96 gate and `--pack bright-smile-dental` not run; compose dev default `app_rw_dev` password is in git (dev only).
- Tenant key issuance/lookup code (`tenant_api_keys` use) is not in this plan.
