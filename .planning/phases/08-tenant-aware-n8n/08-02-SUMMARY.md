---
phase: 08-tenant-aware-n8n
plan: 02
subsystem: n8n
tags: [n8n, tenant-keys, split-in-batches, compose]
requirements: [WF-01, WF-03]
key-files:
  modified: [n8n/workflows/inbound-message.json, n8n/workflows/followup-scheduler.json, n8n/workflows/escalation-alert.json, docker-compose.yml, .env.example, README.md]
  deleted: [n8n/workflows/daily-report.json]
completed: 2026-11-04
---

# Phase 8 Plan 02: Tenant-aware existing workflows Summary

inbound-message, followup-scheduler and escalation-alert now send `X-API-Key` computed inline from `JSON.parse($env.TENANT_API_KEYS)[tenant_id]`; owner address and business name come from `GET /tenant/me`; daily-report is retired; n8n pinned to 2.18.5.

## Commits
- 4e7914a feat: tenant-aware inbound, follow-up and escalation workflows
- e197dd1 chore: pin n8n and pass tenant key map

## What changed
- inbound-message: Normalize requires a UUID `tenant_id` (body or query; missing -> existing 400 branch); Call agent body built explicitly (no tenant_id sent); booking path adds Tenant me, neutral text, From name = business; escalated path adds a Build alert node (tenant_id, reason, conversation_id, link) before escalation-alert.
- escalation-alert: Normalize throws without a valid tenant_id; Tenant me -> Require owner (throws if no owner_email, error-handler mails the operator) -> Notify human.
- followup-scheduler: Nightly + Manual -> GET /admin/tenants (only X-Admin-Key left) -> Each tenant (Split v3, batch 1) -> Check key -> Tenant me -> Find due (alwaysOutputData) -> Has work (Filter, alwaysOutputData) -> Draft -> Send email (both onError continueRegularOutput) -> single Loop end (run-once, alwaysOutputData) -> Each tenant. `saveDataSuccessExecution: none`.
- daily-report.json removed (`git rm`).
- docker-compose: `n8nio/n8n:2.18.5`, `TENANT_API_KEYS: ${TENANT_API_KEYS:-}`; `.env.example` placeholders (`TENANT_API_KEYS={}`, `OWNER_EMAIL=`); README catalog, key map, must-set-before-deploy note, webhook trust note, daily-report retirement.

## Verification (real output)
- Plan JSON assertion: `ok` (one X-Admin-Key, no summitroofing.test, no rd_live_). Compose config valid, tag count 1, no rd_live_ in .env.example/README/compose.
- `make g-test ARGS="app/test_admin.py -q"`: `............ [100%]` (12 passed, no failures). `git status --short businesses prompts` empty.

## Live drive on the branch stack (project roofdesk-global only)
- daily-report: `n8n unpublish:workflow --id=daily-report` in a one-off container on the n8ndata volume -> "Workflow unpublished successfully". After recreate, `list:workflow` still lists daily-report (no delete command) but the n8n log shows 5 activated workflows (error-handler, escalation-alert, followup-scheduler, inbound-message, outreach-flow) and "5 published workflows"; daily-report is not among them.
- Keys: issued a fresh key per tenant (label phase8-plan2-e2e) on the branch DB, held only in a scratchpad file and shell env, never printed or committed. For the run the api was recreated with `MAIL_TRANSPORT=mailpit OWNER_EMAIL=owner@example.test` (the branch api was configured with real SMTP and a real owner address) and recreated again afterwards without overrides.
- Webhook inbound-message, no tenant_id: HTTP 400 `payload needs a message, a contact id and a valid tenant_id`.
- Webhook inbound-message "let me speak to a real person" for summit-roofing and bright-smile-dental: 200; mailpit shows one escalation mail each, To owner@example.test, From name "Summit Roofing" / "Bright Smile Dental" (per-tenant key and name worked).
- Webhook escalation-alert with web-shaped payload for dental: mail with From "Bright Smile Dental". With an unknown tenant uuid: 200 from onReceived, the run fails at Tenant me and error-handler sends "Workflow failed: Escalation alert".
- followup-scheduler via `n8n execute --id=followup-scheduler --rawOutput` (one-off container with n8n stopped; `execute` against the running server fails on the task-broker port 5679): inserted one due NURTURE conversation for summit-roofing only. Tenants run in slug order, so dental (nothing due, placeholder item through Filter and Loop end) ran first, then summit-roofing: status success, exactly 1 mail ("Your free roof inspection with Summit Roofing" to the test lead, From "Summit Roofing"), none from the dental placeholder. Re-run with nothing due: status success, no new mail. Execution output contained none of the issued keys (checked programmatically).

## Not verified
- Booking branch (Tenant me + confirmation email) was not driven: it needs the LLM to complete a booking. Static JSON only.
- The trigger recorded in the CLI run was "Nightly"; the Manual Trigger exists and is wired to List tenants but the CLI did not pick it, so the Manual path itself was not separately exercised.
- Mixed due/empty ordering was proven for 2 tenants (empty first, due second); not a run where a due tenant precedes an empty one (plan 6 E2E).
- A real failure in Draft is swallowed by continueRegularOutput (by design per the plan); only the placeholder case was observed.
- Escalation link in the booking-to-escalation path is the API's `link` (uses `PUBLIC_URL`); not checked against a real public URL.
- `daily-report` remains in the n8n DB, unpublished (no delete command). Live stack untouched. Nothing pushed or deployed.
- Test data left on the branch DB: conversation 8629 and the e2e leads/conversations 8627, 8628.

## Deviations
None to the plan. Note: stopping and recreating the branch n8n/api was needed for the live run; api env was restored.

## Self-Check: PASSED
Commits 4e7914a and e197dd1 on roofdesk-global; daily-report.json absent; JSON assertion ok.
