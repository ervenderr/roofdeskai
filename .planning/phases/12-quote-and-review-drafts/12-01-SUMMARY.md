---
phase: 12-quote-and-review-drafts
plan: 01
subsystem: dashboard
tags: [drafts, server-action, nextjs]
requires: [11-01]
provides: [lib/drafts.ts helpers, getDrafts, decideTenantDraft, requireTenantModule, decideDraft action, Quotes/Reviews nav]
affects: [dashboard/lib/data.ts, dashboard/lib/session.ts]
key-files:
  created: [dashboard/lib/drafts.ts, dashboard/lib/drafts.check.mjs]
  modified: [dashboard/lib/session.ts, dashboard/lib/session.check.mjs, dashboard/package.json, dashboard/lib/types.ts, dashboard/lib/data.ts, dashboard/lib/review-actions.ts, dashboard/lib/review-actions.stub.ts]
requirements: [DRAFT-01, DRAFT-02, DRAFT-03, DRAFT-04, DRAFT-05]
completed: 2026-11-05
---

# Phase 12 Plan 01: Draft data layer and decideDraft action Summary

Pure draft helpers (button rules, 200/409/404 mapping, bound-arg whitelist, fixed-word messages), tenant-only `call()` option, `getDrafts`/`decideTenantDraft`/`requireTenantModule`, and a `decideDraft` server action with a static-export stub.

## Commits
- 132c647 feat: draft status helpers, decision validation and Quotes/Reviews nav items
- e84d29d feat: tenant-only draft reads and decideDraft server action

## Verification
- RED observed: after adding checks (and the `check` script change) but before drafts.ts/nav items existed, `npm run check` failed with ERR_ASSERTION (nav assertion in session.check.mjs).
- GREEN: `npm run check` prints `session check ok` and `drafts check ok`.
- `npm run build` and `env -u API_URL EXPORT=1 npm run export` completed with route tables and no errors.
- `python3 -m scripts.check_shared`: `check-shared OK: 11 allowlisted files, no other hits`.
- `git diff --stat -- api/` empty. `drafts.ts` has 0 imports.
- Not exercised: live API calls (plan 02/03 cover the pages and live check).

## Deviations from Plan
- Per the caller's note, the `decidedMessage` "nothing was sent or posted" check is case-insensitive (`/nothing was sent or posted/i`), since the message begins "Nothing".
- Commit messages follow `<type>: <description>` per user rules (not the `type(phase-plan):` scope form) and carry the Co-Authored-By line.

## Known Stubs
None.

## Self-Check: PASSED
