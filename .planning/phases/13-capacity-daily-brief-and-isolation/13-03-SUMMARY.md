---
phase: 13-capacity-daily-brief-and-isolation
plan: 03
subsystem: dashboard
tags: [capacity, daily-brief, nextjs]
requires: [13-02]
provides: [/capacity page, /brief page]
key-files:
  created: [dashboard/app/capacity/page.tsx, dashboard/app/brief/page.tsx]
requirements: [CAP-01, BRF-02, KEEP-02]
completed: 2026-11-05
---

# Phase 13 Plan 03: Capacity and brief screens Summary

Read-only `/capacity` (open flags by default, `?all=1` for all, fixed hrefs) and `/brief` (latest brief as JSX text, sources table using `sourceStatus` so unavailable sources show their error, recent runs list). Static export shows "not available in the static demo" for both.

## Commits
- feat: capacity flags page
- feat: daily brief page with source status

## Verification
- `npm run check` exit 0; `npm run build` exit 0; `.next/server/app/capacity.html` and `brief.html` do not exist (dynamic).
- `env -u API_URL EXPORT=1 npm run export` exit 0; both out pages contain the static block; `out/index.html` emitted with no `/capacity` or `/brief` links.
- `python3 -m scripts.check_shared` exit 0.
- Greps: dangerouslySetInnerHTML 0, `<form` 0 in capacity, `.html` 0 in brief, parseFloat/Number/toFixed 0. "mock data" appears once in brief page (note text); the per-source label also comes from `sourceLabel`.
- `git diff --stat` for globals.css and api/ empty.
- Not exercised: live rendering against the API (no live session).

## Deviations from Plan
None.

## Known Stubs
None.

## Self-Check: PASSED
