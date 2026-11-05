---
phase: 13-capacity-daily-brief-and-isolation
plan: 04
subsystem: dashboard
tags: [live-check, capacity, daily-brief, isolation, e2e]
requires: [13-01, 13-03]
requirements: [CAP-01, BRF-01, BRF-02, ISO-01, KEEP-02]
status: partial (Task 1 done; Task 2 browser checkpoint pending)
completed: 2026-11-05
---

# Phase 13 Plan 04: Live end-to-end checks (partial) Summary

Task 1 (automatic live checks against the branch stack, API 127.0.0.1:18000, dashboard `next start` on :3100) passed a through h and all gates. Task 2 (human browser check) is pending and is run by the orchestrator and user. No repo code changed. The API already served `GET /daily-brief` (401 without a key), so `make g-up` was not needed.

## Setup
- Tenants: puzzle-peak (P, 4b0641c2-...), summit-roofing (R), bright-smile-dental (D). Keys labelled `phase13-e2e`: P id 8694, R id 8695, D id 8696. Values never printed; stored in a chmod-600 scratchpad file.
- Seeded on P with explicit first/last: d1 = 2026-11-06 (40 covers, over_capacity, cap 30, staff 3, new, left open), d2 = 2026-11-09 (40 covers, then 25 covers -> `resolved` contains d2's key; no under_utilised flag appeared). `POST /daily-brief` created today's run (2026-11-05, 4 mock sources).
- Drafts already present from phase 12 (10 on P): pending #2295 (quote), #2292 (review); needs_human #2287, #2288, #2289; the rest decided. No new drafts needed.

## Checks
| Check | Result | Evidence |
|---|---|---|
| a BRF-01 | PASS | P `GET /daily-brief` 200, `latest.local_date` 2026-11-05, 4 sources, `runs` 1 item, `runs[0].run_date` 2026-11-05; R 404, D 404, admin key 401. `GET /daily-brief/due` is 404, not 405 (the StaticFiles mount answers unmatched GETs; same deviation as 13-01) |
| b | PASS | `?open=true` returns only d1's key; unfiltered returns d1 (resolved_at null) and d2 (resolved_at set); R 404, D 404 |
| c | PASS | R and D `GET /drafts` 200 with 0 rows, intersection with P's 10 ids is 0; `GET /drafts/2289` R 404, D 404, P 200 |
| d CAP-01 | PASS | P nav has `/capacity` and `/brief` (1 each). `/capacity` 200: d1 row "Over capacity", "Staff 3 - Min staff 2 - Covers 40 - Capacity 30" (equals API details), "Open"; d2 absent; `/capacity?all=1` link present. `?all=1` 200: d2 shown with "Resolved", `/capacity` link present. `?all=yes` 200, identical to open view (only the echoed URL in the RSC payload differs). The page has no page-level `<form`; the single `<form` is the sign-out form in the layout (the home page has the same one) |
| e BRF-02 | PASS | `/brief` 200: "Brief for 2026-11-05", 40-char slice of `latest.text` found (HTML-escaped), 4 sources each "mock data" and "OK", metric strings present (e.g. covers 19, revenue 1724.56), recent runs list, no "unavailable". No page-level form; no POST in dash13.log |
| f ISO-01 live | PASS | R, D and operator sessions: nav links for /capacity, /brief, /quotes 0; those three routes 404 for each; HTML has 0 of P's flag dates/keys, 0 draft ids `#228x/#229x`, 0 brief slice matches. Replay of P's reject form for #2295 with R's cookie: 303 `/quotes?decided=missing`; API #2295 still `pending`. (First replay attempt returned 500 because my script dropped the valueless `$ACTION_REF` field; corrected, the 500 was the harness, not the app) |
| g Secrets | PASS | P, R, D keys and the admin key: 0 occurrences in all fetched HTML, Location headers, `.next/static` and dash13.log |
| h Signed out | PASS | `/capacity` and `/brief` -> 307 to `/login` |

Unavailable source: none exists on live puzzle-peak (all 4 sources ok). The pack was not edited; the unavailable branch is covered by the 13-01 pytest and the 13-02 `ops.check.mjs` case.

## Gates
- `npm run check` exit 0; `npm run build` exit 0
- `env -u API_URL EXPORT=1 npm run export` exit 0; `out/capacity.html` and `out/brief.html` each contain "not available in the static demo"; `out/index.html` has 0 matches for `/capacity`, `/brief`, `/login`
- `python3 -m scripts.check_shared`: `check-shared OK: 11 allowlisted files, no other hits`
- `make g-test`: 1284 passed, 1 warning, exit 0
- `git diff --stat abdcb21..HEAD -- api/app/agent.py prompts/ evals/runner.py`: empty

## Limits stated plainly
- Live isolation compares puzzle-peak (modules enabled) with tenants lacking the modules (R, D, operator): 404s and zero P identifiers. The two-tenants-both-with-modules proof is the 13-01 Python test (`test_owner_isolation.py`) using API keys.
- The roofing 94/96 eval was NOT re-run. It is covered only by the empty agent-path diff plus `make g-test`.

## Cleanup state
- R (id 8695) and D (id 8696) keys revoked, HTTP 200 each (both now 401).
- P key (label `phase13-e2e`, id 8694) is kept active for Task 2. Revoke afterwards: `POST /admin/tenants/4b0641c2-fdc3-4e44-891d-9a5c5495613c/keys/8694/revoke`, then delete `/private/tmp/claude-501/-Users-ervenderr-Projects-roofdeskai/0c064e05-2147-4d14-9df0-2574595a5952/scratchpad/keys13.json`.
- Dashboard left running on :3100: `cd dashboard && API_URL=http://localhost:18000 SESSION_SECRET=<random, in scratchpad ss13.txt> npm start` (production build, live mode), log `.../scratchpad/dash13b.log`.
- Seeded rows (flags d1/d2, today's brief run) stay in the local branch DB.

## Deviations from Plan
- `GET /daily-brief/due` answers 404 rather than 405 (see a).

## Pending
- Task 2 (human-verify browser checkpoint): not run.
