---
phase: 12-quote-and-review-drafts
verified: 2026-11-05T00:00:00Z
status: human_needed
score: 4/4 roadmap truths verified (1 only by code read, not live)
human_verification:
  - test: "Produce a needs_human review reply (reply that fails guardrails twice) and open /reviews"
    expected: "Card shows 'Blocked after N attempts: <violation codes>' and no reply text, no Approve button"
    why_human: "Never produced live; verified by code read and API payload shape only"
---

# Phase 12 Verification

**Goal:** Owners can review and decide quote and review-reply drafts in the browser.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Quote drafts list with status, items, total; needs_human shows reason and missing | VERIFIED | `dashboard/app/quotes/page.tsx` renders `needs_human.reason`/`missing` and `quote.total` verbatim; live check b (#2289: reason, missing qty); browser: /quotes lists drafts with API money strings |
| 2 | Approve/reject changes status on next load, nothing sent | VERIFIED | Live c/e: API status approved/rejected, never `sent`; replay gives conflict; browser approve #2296 shows Approved |
| 3 | Review drafts list, blocked ones show violation codes | VERIFIED (list live) / UNCERTAIN (violations) | `reviews/page.tsx:40-41` renders `payload.violations`; shape matches `api/app/reviews_routes.py:64`; no live needs_human review |
| 4 | Other tenant's draft never appears | VERIFIED | Live f: P ids 10, R ids 0, intersection 0; cross-tenant decide on #2295 -> missing, still pending; tenant-only `getDrafts`/`decideTenantDraft` in `lib/data.ts` |

Requirements DRAFT-01..05: satisfied (DRAFT-04's violation-code part by code read only).

Gates: `npm run check` passes (session + drafts checks); summary reports `make g-test` 1277 passed, check_shared OK, `api/` diff empty, static export OK. No TBD/FIXME markers checked beyond summaries' claims.

## Human verification
1. Needs_human review view (see frontmatter). Low risk; optional.

## Gaps
None blocking.
