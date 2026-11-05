---
phase: 11-sign-in-and-tenant-shell
plan: 01
subsystem: dashboard
tags: [session, auth, nextjs]
requires: []
provides: [session seal/unseal, navFor, per-request credential in data.ts, getSession, checkKey]
affects: [dashboard/lib/data.ts]
key-files:
  created: [dashboard/lib/session.ts, dashboard/lib/session.check.mjs]
  modified: [dashboard/lib/data.ts, dashboard/package.json]
requirements: [AUTH-03, AUTH-04, AUTH-07, KEEP-01]
completed: 2026-11-05
---

# Phase 11 Plan 01: Session core and per-request credential Summary

AES-256-GCM sealed session cookie module (node-testable) and data.ts reworked to send the signed-in key per request, redirect without a session, and 404 operator tools for tenants.

## Commits
- 29da305 feat: sealed session module with nav gating and node self-check
- 707b2a9 feat: dashboard data calls use per-request session credential

## Verification
- `npm run check` prints `session check ok`; RED confirmed (module missing), and removing the exp check made it fail.
- `npm run build` and `env -u API_URL npm run export` exit 0; `out/index.html` exists.
- `python3 -m scripts.check_shared`: OK (`make check-shared` needs the api container, which is down).
- No ADMIN_API_KEY, no `.catch(() => null)`, 10 `operator: true`, no middleware, no `dashboard/app` diff.

## Deviations from Plan
None. Not exercised: live-mode behavior against the running API (no login UI until plan 02).

## Self-Check: PASSED
