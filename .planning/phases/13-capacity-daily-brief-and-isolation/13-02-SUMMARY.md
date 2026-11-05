---
phase: 13-capacity-daily-brief-and-isolation
plan: 02
subsystem: dashboard
tags: [capacity, daily-brief, helpers, nextjs]
requires: [13-01, 12-01]
provides: [lib/ops.ts helpers, getCapacityFlags, getBrief, Capacity and Daily brief nav items]
affects: [dashboard/lib/data.ts, dashboard/lib/session.ts]
key-files:
  created: [dashboard/lib/ops.ts, dashboard/lib/ops.check.mjs]
  modified: [dashboard/lib/session.ts, dashboard/lib/session.check.mjs, dashboard/package.json, dashboard/lib/types.ts, dashboard/lib/data.ts]
requirements: [CAP-01, BRF-02, KEEP-02]
completed: 2026-11-05
---

# Phase 13 Plan 02: Ops helpers and tenant-only reads Summary

Import-free `lib/ops.ts` (showAll, flagsRoute, flag labels/state/tone/details, sourceStatus, sourceLabel, metricEntries, isBriefResponse), two nav items (Capacity/capacity, Daily brief/connectors), and `getCapacityFlags`/`getBrief` over `call()` with `tenant: true`, validated at the boundary.

## Commits
- c011acf feat: ops helpers, node check and Capacity/Daily brief nav items
- ecc4ddc feat: tenant-only capacity flag and daily brief reads

## Verification
- RED observed: after adding ops.check.mjs, the session nav cases and the `check` script change, `npm run check` failed with ERR_ASSERTION (nav assertion in session.check.mjs, before ops.ts was reached; ops.ts did not exist).
- GREEN: `npm run check` exit 0, prints `session check ok`, `drafts check ok`, `ops check ok` (including the sourceStatus ok/error/null-error cases).
- `npm run build` exit 0. `env -u API_URL EXPORT=1 npm run export` exit 0.
- `python3 -m scripts.check_shared` exit 0: `check-shared OK: 11 allowlisted files, no other hits`.
- `git diff --stat -- api/` empty. `grep -c '^import' lib/ops.ts` = 0. `tenant: true` count in data.ts 2 -> 4. BriefPayload has no html field.
- Not exercised: live API calls (plan 03 renders and live-checks).

## Deviations from Plan
- **[Rule 1 - stale test]** Existing `session.check.mjs` asserted `navFor(tenant)` equals `["/", "/conversations"]`, but the fixture tenant already has module `capacity`, so it now also gets `/capacity`. Updated that expectation.
- Commit messages follow `<type>: <description>` and carry the Co-Authored-By line per the caller.

## Known Stubs
None.

## Self-Check: PASSED
