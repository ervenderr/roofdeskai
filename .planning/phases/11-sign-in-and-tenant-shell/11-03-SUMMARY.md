---
phase: 11-sign-in-and-tenant-shell
plan: 03
subsystem: dashboard
tags: [e2e, verification]
requires: ["11-02"]
key-files:
  modified: [docker-compose.global.yml]
requirements: [AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, KEEP-01]
status: partial (Task 1 done; Task 2 browser checkpoint pending)
completed: 2026-11-05
---

# Phase 11 Plan 03: Live end-to-end verification (partial)

Task 1 done: API published on 127.0.0.1:18000 for the host-run dashboard; checks a-h all pass against the branch stack. Task 2 (browser) pending.

## Commits
- chore: publish branch-stack API on 127.0.0.1:18000 for host-run dashboard (docker-compose.global.yml only; api/ untouched)

## Evidence (no key values recorded)
- a AUTH-04 pass: `/`, `/conversations`, `/calls` signed out -> 307 to /login.
- b AUTH-02 pass: wrong tenant key and wrong admin key -> 303 /login?error=1, 0 rd_session cookies.
- c AUTH-01/03/06 pass: roofing key -> 303 /, cookie HttpOnly + SameSite=lax; `/` 200 with "Summit Roofing" (matches /tenant/me); nav has /conversations only (no /calls, /outreach, /prospects).
- d AUTH-03 pass: key occurs 0 times in login body, `/` HTML, headers, `.next/static`; cookie is ciphertext. Admin key: 0 in HTML, headers, static.
- e KEEP-01 pass: tenant /conversations 200 (5 rows), /conversations/5120 200 with transcript; /calls, /outreach, /prospects, /prospects/1 all 404. Admin: all five nav links, /calls 200, /outreach 200.
- f AUTH-07 pass (degenerate): roofing 5 conversations, dental 0, overlap 0; roofing count equals direct `GET /conversations` (5). Dental has no data, so disjointness is not strongly exercised.
- g Revocation pass: sign in with X 200, revoke 200, then `/` -> 307 /login?expired=1; re-sign-in -> /login?error=1, no cookie.
- h AUTH-05 pass: sign-out action -> 303 /login, rd_session cleared (Expires 1970); following `/` -> 307 /login.
- Gates: static export succeeds; `check-shared OK`; `make g-test` 1277 passed.

## Deviations
- No-JS action POST worked first time; no cookie-minting fallback used.
- Keys: D and X revoked. One roofing key (label phase11-e2e, id 7675) kept alive for the browser check; revoke it after approval.
- Stack left running; dashboard stopped. Session credentials written to chmod-600 files in the scratchpad.

## Pending
- Task 2: browser check by the user/orchestrator.
