---
phase: 12-quote-and-review-drafts
plan: 02
subsystem: dashboard
tags: [drafts, quotes, reviews, nextjs]
requires: [12-01]
provides: [/quotes page, /reviews page, DraftButtons, DecidedNote]
key-files:
  created: [dashboard/components/DraftDecision.tsx, dashboard/app/quotes/page.tsx, dashboard/app/reviews/page.tsx]
requirements: [DRAFT-01, DRAFT-02, DRAFT-03, DRAFT-04, DRAFT-05]
completed: 2026-11-05
---

# Phase 12 Plan 02: Quote and review draft screens Summary

`/quotes` and `/reviews` render tenant drafts (money strings verbatim, needs_human details, blocked violations) with Approve/Reject buttons and a "nothing is sent or posted" line; static export shows "not available" blocks.

## Commits
- feat: quotes draft page and shared decision component
- feat: review reply drafts page

## Verification (exit codes)
- `npm run check` 0; `npm run build` 0 (both pages dynamic, no quotes.html/reviews.html)
- `env -u API_URL EXPORT=1 npm run export` 0; out/quotes.html and out/reviews.html contain the static block; out/index.html has no /quotes link
- `python3 -m scripts.check_shared` 0 (OK); `git diff --stat -- api/ globals.css` empty
- Not exercised: live render against the API.

## Deviations
- `contact_email` is read from `payload.contact_email` (per types.ts), not top-level `d.contact_email` as the plan text said.

## Known Stubs
None.

## Self-Check: PASSED
