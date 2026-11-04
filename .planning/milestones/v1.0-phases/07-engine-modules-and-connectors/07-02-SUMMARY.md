---
phase: 07-engine-modules-and-connectors
plan: 02
subsystem: db-drafts
tags: [migration-007, rls, drafts, assert_rls_enforced]
requires: [07-01]
provides: [007_engine_modules (drafts, capacity_flags, brief_runs, intake_people), drafts.create_or_get_draft, drafts.require_module, /drafts router, assert_rls_enforced(eng) coverage check]
affects: [07-03..07-08]
key-files:
  created: [db/migrations/007_engine_modules.sql, api/app/drafts.py, api/app/test_drafts.py]
  modified: [api/app/db.py, api/app/main.py, api/app/conftest.py, api/app/test_rls_proof.py, api/app/test_leak.py, api/app/test_migrations.py]
requirements-completed: [MOD-02 (drafts queue part)]
metrics: {tasks: 2, commit: 92f0ec0}
---

# Phase 7 Plan 02: Migration 007 and drafts queue Summary

Final migration 007 (four tenant tables, grants incl. sequences, ENABLE+FORCE RLS, tenant_isolation, no tenant_id default), a startup coverage check that fails if any tenant_id table readable by app_rw lacks FORCE RLS, and a tenant-scoped drafts router with dedupe.

## Commits
- 92f0ec0 `feat: migration 007 engine tables and tenant-scoped drafts queue` (tests and implementation in one commit; RED run done first)

## Verification (real output)
- RED: `make g-test ARGS="app/test_drafts.py ..."` -> `ImportError: cannot import name 'drafts' from 'app'` (collection error).
- `make g-up`: api recreated, `Up 28 seconds` after 25s, no crash loop; log ends `Application startup complete.`; assert_rls_enforced passed at startup. psql: drafts, capacity_flags, brief_runs, intake_people all `relforcerowsecurity = t`; latest versions `007_engine_modules`, `006_tenant_api_keys`.
- Targeted (drafts, rls_proof, leak, migrations): all dots, no failures (128 tests).
- Full `make g-test`: `676 passed, 1 warning in 16.64s`.
- After the run the dev DB tenants are `bright-smile-dental`, `summit-roofing` only; `select count(*) from drafts` = 0.

## Decisions
- `DELETE` granted on `intake_people` only (subject erasure); others SELECT/INSERT/UPDATE.
- 'sent' remains in the drafts CHECK; no endpoint sets it. approve: pending only; reject: pending or needs_human; wrong state 409, absent or other tenant 404.
- Dedupe: INSERT ... ON CONFLICT ... WHERE status IN ('pending','needs_human') DO NOTHING RETURNING, else SELECT existing -> `(id, deduped)`. A decided draft does not block a new open one (tested).
- `assert_rls_enforced(eng=None)`; main.py call unchanged.
- conftest: session autouse `apply_pending_migrations`; cleanup deletes drafts/capacity_flags/brief_runs/intake_people for test-% and demo-venue tenants before tenant deletion, and `_drop_unreferenced_venue` removes the demo-venue tenant row (and its keys) only if no FK-referencing table still has rows for it. Real tenants are never touched.

## Deviations from Plan
- Cleanup of the demo-venue fixture tenant (orchestrator request), beyond plan files list.
- `test_drafts.py` imports the `rls` fixture from `test_rls_proof.py` for the coverage test.

## Not verified / risks
- The eval was not run (no pack or prompt changes).
- Before this plan's cleanup ran, a stale `demo-venue` tenant row in the dev DB made API startup log a `PackError ... demo-venue/pack.yaml: file missing` (seed_faq iterating tenants); startup still completed. The row is gone after the full test run.
- Payload is opaque jsonb; no money/Decimal handling yet (later plans).
- Rate limiting, quote/review routes not in this plan.

## Self-Check: PASSED
Files exist, commit 92f0ec0 present.
