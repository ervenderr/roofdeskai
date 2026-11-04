---
phase: 09-docs-pii-retention-and-make-new-business
plan: 02
subsystem: data-protection
tags: [retention, delete-subject, ops-04]
requires: [09-01]
provides: [retention.PURGED, retention.KEPT, purge_tenant, purge_all, delete_subject]
affects: [api/app/main.py]
key-files:
  created: [db/migrations/008_retention_grants.sql, api/app/retention.py, scripts/retention.py, api/app/test_retention.py]
  modified: [api/app/config.py, api/app/tenant_admin.py, api/app/tenant_routes.py, api/app/main.py, api/app/test_migrations.py]
requirements-completed: [OPS-04]
---

# Phase 9 Plan 02: Retention and delete_subject Summary

Per-tenant retention purge (cutoff COALESCE(ended_at, started_at)), best-effort `delete_subject` with a hash-only audit row, GRANT-only migration 008, admin and tenant endpoints, CLI script, and a table-coverage test.

## Requirements
OPS-04.
D-04 override: agent_events kept (append-only trigger, no PII by contract).

## Commits
- 2d99895 feat: migration 008 delete grants for retention
- 108c26c feat: retention purge and delete_subject
- 74322a8 feat: retention and subject-delete endpoints

## Verification
- RED seen for each task (008 assertion failure; ImportError for retention and CLI).
- `make g-test`: 1163 passed. `git status --short businesses prompts` empty.
- Roofing and dental tenants still present afterwards (psql: summit-roofing, bright-smile-dental). Tests touched only test-* tenants.

## Deviations from Plan
- [Rule 3] `api/app/main.py` modified (not in files_modified): routes at `/admin/retention/run` need a second router in tenant_admin.py (the existing one is prefixed `/admin/tenants`), so it is included there.
- Subject delete routes use a bare 422 "invalid identifier" from `retention.delete_subject_http`, because Pydantic's default 422 would echo the input.
- Phone matching compares digits only, so a number stored with country code 1 does not match one given without it (formatting differences are ignored, prefixes are not normalized).
- delete_subject by phone reaches leads, conversations and appointments only; drafts and intake_people are matched by email/person_key.

## Not verified
- The script was not run against the dev DB (by instruction); covered by a function-call test on a test tenant.
- Draft payload `customer_email` holds the whole email text, so equality on it rarely matches; only `contact_email` reliably links.
- n8n execution data and logs are outside the purge.

## Self-Check: PASSED
