---
phase: 08-tenant-aware-n8n
plan: 05
subsystem: n8n-workflows
tags: [n8n, daily-brief, capacity-check, intake-event]
requirements: [WF-02, WF-03]
key-files:
  created: [n8n/workflows/daily-brief.json, n8n/workflows/capacity-check.json, n8n/workflows/intake-event.json]
  modified: [api/app/test_n8n_workflows.py]
completed: 2026-11-04
---

# Phase 8 Plan 05: capacity-check, daily-brief, intake-event Summary

Three new workflows complete the catalog at ten files, all passing the CI key-header check.

## Commits
- a0a4863 feat: capacity-check, daily-brief and intake-event workflows (three JSONs plus the EXPECTED change, test edited first)

## What was built
- daily-brief: Hourly (`0 * * * *`) plus Manual -> `GET /admin/tenants` -> Each tenant -> Check key -> `/tenant/me` -> Gate (connectors module and owner_email, Filter with alwaysOutputData) -> `POST /daily-brief/due` (tenant key) -> Is due (due list non-empty AND the gate conditions again) -> `POST /daily-brief` (empty body) -> mailpit to owner_email, Subject `Daily brief {local_date}: {name}`, Text and HTML from the payload -> single Loop end -> Each tenant. The gate precedes the call that writes brief_runs. The POST /daily-brief key index is `due[0].tenant_id`, so on the empty placeholder item it has no key and no row is written. At-most-once risk (mail failure after the row exists; re-run with `POST /daily-brief {"force": true}`) is in the workflow sticky note.
- capacity-check, webhook lane: `POST /webhook/capacity-check`; Normalize validates tenant_id and passes bookings, staff_overrides, first, last (error output -> 400). `POST /capacity/check` uses full response and neverError. Respond returns the API status; on 200 it returns `{checked_shifts, flags: <new+reflagged count>}`, otherwise the API body. In parallel, the new or reflagged flags go through `/tenant/me`, Require owner and one owner mail.
- capacity-check, nightly lane (`0 3 * * *` plus Manual): tenants loop, Check key, `/tenant/me`, Gate (capacity module and owner_email), `POST /capacity/check` with body `{}` (neverError, onError continueRegularOutput), Night alerts Filter (status 200 and at least one new or reflagged flag), one mail listing date/shift/staff/covers/capacity, single Loop end -> Each tenant. No IF anywhere in the loop. A non-200 is skipped, not retried. `source_unavailable` has no flags, so nothing is sent.
- intake-event: `POST /webhook/intake-event`; Normalize validates tenant_id, event in waiver|checkin|result and an object payload, and strips tenant_id. `POST /intake_event` with `{event, payload}` (neverError, full response); Respond uses the API statusCode and body. No mail node, no logging of payload.
- Key headers are `JSON.parse($env.TENANT_API_KEYS)[id]` inline everywhere; `X-Admin-Key` appears only on `GET /admin/tenants`. All three have errorWorkflow error-handler and saveDataSuccessExecution none (T-08-05-01; retention left to Phase 9).

## Verification (real output)
- RED (EXPECTED extended, JSONs absent): `FAILED app/test_n8n_workflows.py::test_catalog`, `1 failed, 27 passed`.
- GREEN: `make check-n8n` -> `31 passed in 0.10s`. Full `make g-test` (run alone, no eval running): `1094 passed, 1 warning in 22.09s`. `git status --short businesses prompts` empty.
- Branch n8n recreated; start log: `Activated workflow "Capacity check" (ID: capacity-check)`, `"Daily brief" (ID: daily-brief)`, `"Intake event" (ID: intake-event)`. No node-parameter errors were logged. `n8n list:workflow` shows the ten ids plus the stale `daily-report` (see notes).
- Pass-through (research A1) verified live on the branch n8n: `POST /webhook/intake-event` and `/webhook/capacity-check` with a valid but unprovisioned tenant_id returned `401 {"detail":"unauthorized"}` on both. So `fullResponse` plus `neverError` (`options.response.response`) is accepted by the node, and the API status and body reach the caller. Missing tenant_id or an unknown event returns `400` from the Normalize reject on both webhooks.
- Mailpit rejects an empty recipient list: `400 {"Error":"error building message: no recipients (to, cc, bcc) set"}`. The mail nodes rely on this. When their upstream Filter passes only the placeholder item, To becomes `[]` and the send fails into continueRegularOutput.

## Not verified live
- Happy paths were not run: no tenant keys or demo tenant exist on the branch stack. The Manual lanes (daily-brief loop, nightly capacity), mail delivery, `/daily-brief/due` through n8n, a 200 pass-through body and the 422 mapping error through intake-event are all unrun. Plan 6 E2E owns them and is where an A1 or A3 surprise would show. I changed no api config and sent no mail.
- Unverified n8n behaviour that the gating depends on: (1) a Filter with alwaysOutputData emits one empty item when everything is filtered out; (2) the expression `[$json.due[0].tenant_id]` on that empty item yields no key or an error (both are safe, since the API would answer 401 or the node would fail into continueRegularOutput); (3) `$('Gate').first()` on a loop's later iterations.

## Decisions and notes
- Gated-out tenants still push an empty item through the downstream nodes (Filter alwaysOutputData is the 08-04 pattern). The mutating calls and the mails therefore carry their own guards (key index, recipient list), not just the Filter.
- A stale `daily-report` workflow remains on the existing branch n8n volume (import does not delete); `n8n unpublish:workflow --id=daily-report` or `make g-reset` clears it. Not touched.
- Webhook tenant selection stays caller-supplied on the internal port (T-08-05-03, accepted). saveDataErrorExecution was left at the default, so failed executions can still store payloads; Phase 9 retention.
- The JSONs were generated by a throwaway script in the scratchpad (not committed); the JSONs are the source of truth.

## Deviations
None.

## Self-Check: PASSED
Commit a0a4863 and all three workflow files exist; ten workflow files present.
