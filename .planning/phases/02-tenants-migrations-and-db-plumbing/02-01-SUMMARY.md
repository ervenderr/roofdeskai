---
phase: 02-tenants-migrations-and-db-plumbing
plan: 01
subsystem: database
tags: [migrations, tenancy, postgres]
requires: []
provides: [migration runner, tenants table, db.tx, db.system, g-test, scratch_db fixture]
affects: [api/app/db.py, api/app/bootstrap.py, Makefile]
key-files:
  created: [db/migrations/001_tenants.sql, api/app/test_migrations.py, api/app/test_tenancy.py]
  modified: [Makefile, api/app/config.py, api/app/db.py, api/app/bootstrap.py, api/app/conftest.py]
requirements-completed: [TEN-01, TEN-03]
completed: 2026-11-03
---

# Phase 2 Plan 01: Migration runner and tenant helpers Summary

Numbered SQL migration runner (advisory-locked, per-file transaction, schema_migrations) with the baseline guard fixed, migration 001 (tenants + Summit default + faq_chunks sequence fix), and `db.tx()`/`db.system()`.

- Pre-migration dump taken before any new code ran on the branch DB: scratchpad `branch-pre.dump`; `pg_restore -l | grep -c "TABLE public tenants"` = 0.
- Commits: f501e0a (Task 1), see git log for Task 2.
- Verification: `make g-test` full suite 224 passed; `-k migrations` 7 passed; `-k tenancy` 4 passed; no leftover scratch_ databases; `python -m app.bootstrap` prints `migrations: ['001_tenants']`.

## Deviations from Plan

- Task 1: tests and implementation were written in one step, so the RED run for tx() was not observed (Task 2 RED was: 7 failed before implementation).
- The api container bind-mounts `api/app` and `db`, so `make g-up` (rebuild) was not needed; tests ran directly against the running branch container. The branch DB had migration 001 applied by `python -m app.bootstrap` (branch stack only).

## Known Stubs
None.

## Self-Check: PASSED
