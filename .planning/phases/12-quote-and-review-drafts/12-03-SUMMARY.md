---
phase: 12-quote-and-review-drafts
plan: 03
subsystem: dashboard
tags: [live-check, drafts, e2e]
requires: [12-02]
requirements: [DRAFT-01, DRAFT-02, DRAFT-03, DRAFT-04, DRAFT-05]
status: partial (Task 1 done; Task 2 browser checkpoint pending)
completed: 2026-11-05
---

# Phase 12 Plan 03: Live end-to-end checks (partial) Summary

Task 1 (automatic live checks against the branch stack, API 127.0.0.1:18000, dashboard `next start` on :3100) passed a through h. Task 2 (human browser check) is pending and is run by the orchestrator. No repo code changed; `git diff --stat -- api/` empty.

## Setup
- Tenants: puzzle-peak (P) and summit-roofing (R). Keys labelled `phase12-e2e` issued: P key id 7913, R key id 7914. Key values never printed.
- Sample drafts on P (all produced by the real API, LLM available): quotes #2293 (A, total 190.00), #2294 (B, 175.00), #2295 (C, 105.00), #2296 (D, 70.00); needs_human quote #2289 (qty missing, no LLM); review replies #2290, #2291, #2292 (all pending, none blocked).
- Draft ids 2287/2288 (also needs_human) came from a first attempt without `customer_type`; the puzzle-peak surcharge rule needs it (reason `rule_unevaluable`, missing `customer_type`). Retried with `customer_type: consumer`. These two extra needs_human drafts remain in the local DB.

## Checks
| Check | Result | Evidence |
|---|---|---|
| a DRAFT-01 | PASS | P `/quotes` 200; nav has /quotes and /reviews; each quote id, "Waiting for you" label and the exact `payload.quote.total` string present |
| b DRAFT-02 | PASS | #2289 shows reason `missing_input` and missing field `qty`; Approve forms 0, Reject forms 1 |
| c DRAFT-03 | PASS | approve A -> 303 `/quotes?decided=approved`, page shows Approved and the "nothing was sent or posted" message; replay -> 303 `/quotes?decided=conflict`, page 200 with "already decided"; API A=`approved` (not sent); reject B -> 303 `?decided=rejected`, API B=`rejected` |
| d DRAFT-04 | PASS | P `/reviews` 200 lists review text and reply text. needs_human reviews: none existed, so the violation-code view was not exercised live |
| e DRAFT-05 | PASS | approve #2290 -> `/reviews?decided=approved`, reject #2291 -> `/reviews?decided=rejected`; API approved/rejected; reload shows both badges; never `sent` |
| f Isolation | PASS | P ids=10, R ids=0, intersection 0; R session: no nav links, `/quotes` 404, `/reviews` 404; replaying P's approve form for #2295 with R's cookie -> 303 `/quotes?decided=missing`, #2295 still `pending`; operator session: no nav links, `/quotes` 404, `/reviews` 404 |
| g Secrets/PII | PASS | P key occurrences: 0 in page HTML, 0 in `.next/static`; `phase12-a@example.com` and review texts: 0 in Location headers and in the dashboard server log |
| h Signed out | PASS | `/quotes` and `/reviews` -> 307 to `/login` |

## Gates
- `npm run check` exit 0; `env -u API_URL EXPORT=1 npm run export` exit 0
- `python3 -m scripts.check_shared`: `check-shared OK: 11 allowlisted files, no other hits`
- `make g-test`: 1277 passed
- `git diff --stat -- api/`: empty

## Cleanup state
- R key (id 7914) revoked (HTTP 200). `npm start` stopped; nothing listens on :3100.
- P key (label `phase12-e2e`, id 7913) is kept alive for the Task 2 browser check; revoke it after the checkpoint (`POST /admin/tenants/4b0641c2-fdc3-4e44-891d-9a5c5495613c/keys/7913/revoke`) and delete the scratchpad key file `/private/tmp/claude-501/-Users-ervenderr-Projects-roofdeskai/0c064e05-2147-4d14-9df0-2574595a5952/scratchpad/keys12.json`.
- Left pending for the browser step: quotes #2295 and #2296 (pending), #2289 (needs_human), review #2292 (pending). #2293/#2294/#2290/#2291 are already decided, so the "approve again -> already decided" step is best done on #2295 or #2296.

## Deviations
- Quote samples needed `customer_type: "consumer"` (pack rule), not in the plan's request bodies. Not a code change.
- Dashboard log written to `dash12.log` in the scratchpad.

## Pending
- Task 2 (human-verify browser checkpoint): not run.
