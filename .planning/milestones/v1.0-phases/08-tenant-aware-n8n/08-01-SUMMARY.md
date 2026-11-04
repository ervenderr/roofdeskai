---
phase: 08-tenant-aware-n8n
plan: 01
subsystem: api
tags: [tenant-me, escalation-fallback, drafts, quotes, daily-brief]
requirements: [WF-01, WF-02, WF-03, WF-04]
key-files:
  created: [api/app/tenant_routes.py, api/app/test_tenant_me.py]
  modified: [api/app/tenants.py, api/app/main.py, api/app/tools.py, api/app/brief_routes.py, api/app/drafts.py, api/app/quotes.py, api/app/test_brief.py, api/app/test_drafts.py, api/app/test_quotes_api.py, api/app/test_admin.py]
completed: 2026-11-04
---

# Phase 8 Plan 01: API groundwork Summary

Owner resolver + `GET /tenant/me`, escalation mail fallback with `tenant_id` in the webhook payload, `/daily-brief/due` 404, `POST /drafts/{id}/sent`, optional quote `contact_email`. No migration, no pack/prompt change.

## Commits
- 3b285c5 feat: tenant me endpoint and escalation mail fallback
- 43a94cd feat: drafts sent transition, quote contact email, brief due 404

## Test-first evidence
Red run (before implementation): 12 failures across test_tenant_me, test_brief (2), test_drafts (`/sent` gave 405), test_quotes_api (contact_email 422 -> no payload).

**Pre-fix `/daily-brief/due` with admin key + random X-Tenant-Id (actual): HTTP 200, body `{"due":[]}`** (not 500; matches research A6). After fix: 404 `{"detail":"tenant not found"}`.

Green: `make g-test` full suite alone (no eval running): `1062 passed, 1 warning in 21.63s`. `git status --short businesses prompts` empty.

## Deviations
- [Rule 3] `test_admin.py::test_escalation_alert_only_fires_for_web_chat` mocked `httpx.post` returning None; the new `raise_for_status()` needs a response, so the mock now returns an `httpx.Response(200)`. Behaviour asserted is unchanged.
- Quote test note: the email LLM call happens before the dedupe lookup, so the dedupe test scripts three LLM outputs (existing behaviour, not changed).
- D-05 deviation (planned): no pack YAML edit; owner = `pack.meta.owner_email or OWNER_EMAIL`. No tenants.owner_email column, so no migration and no RLS catalog changes.

## Not verified
- Live mail delivery to mailpit/SMTP for the fallback (tests monkeypatch `mailer.send`).
- Nothing deployed or pushed.

## Self-Check: PASSED
Files exist, commits 3b285c5 and 43a94cd on roofdesk-global, full suite green.
