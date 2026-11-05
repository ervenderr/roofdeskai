# Phase 12: Quote and Review Drafts - Context

**Gathered:** 2026-11-05
**Status:** Ready for planning
**Source:** Defaults carried from phase 11 (no discuss-phase, no research, no UI-SPEC)

<domain>
## Phase Boundary

Dashboard screens to list quote drafts and review-reply drafts and approve/reject them, on the existing tenant `/drafts` API. No API changes expected. Capacity flags and the daily brief are phase 13. Local only; no deploy.
</domain>

<decisions>
## Implementation Decisions

### Locked
- Data comes from `GET /drafts?kind=quote|review_reply&status=...` and `POST /drafts/{id}/approve|reject` (api/app/drafts.py). These routes use `require_tenant` (X-API-Key only): they work for TENANT sessions, not operator (admin-key) sessions. Screens are tenant-only; operator sessions get no nav link and a direct URL gives 404 (same pattern as `operator: true` in `dashboard/lib/data.ts`, inverted: add a tenant-only option to `call()`/`api()`).
- Two pages: `/quotes` (kind=quote, nav module tag `services`) and `/reviews` (kind=review_reply, nav module tag `reviews`), added to the nav list in `dashboard/lib/session.ts` (`NavItem.module` already exists and gates by `session.modules` from `/tenant/me` `enabled_modules`). A tenant whose pack lacks the module sees no link; direct URL gives 404.
- Payload shapes (from api/app/quotes.py, reviews_routes.py):
  - quote: `payload.request`, `payload.quote` (line items and Decimal total via `quote_to_payload`), `payload.email_text`, `payload.check_failures`, `payload.contact_email`, or `payload.needs_human = {reason, missing[]}` when status is `needs_human`.
  - review_reply: `payload.review_text`, `payload.rating`, `payload.platform`, `payload.reply_text` (pending) or `payload.violations` + `payload.attempts` (needs_human; failed text is never stored).
  - statuses: pending, approved, rejected, needs_human, sent. Approve allowed from pending only; reject from pending or needs_human; other transitions return 409 (show a plain message, do not crash).
- Approve/reject are Server Actions that mark a decision only; the UI must say nothing is sent or posted. No send button in this phase.
- Money is shown exactly as the API returns it (strings/Decimals); do not recompute or float-convert totals in the UI.
- Customer text (quote `customer_email`, review text) is tenant-scoped PII: render as text only (React escaping), never in URLs, never logged.
- Static export (`EXPORT=1`): server actions are not allowed; follow the existing pattern (`session-actions` stub, `review-actions` stub in `next.config.mjs`). In static/demo mode these pages show a short "not available in the static demo" block (no snapshot data for drafts) and the nav does not list them (session is null in static mode, modules empty, so the module gate already hides them). Static export build must stay green.
- Reuse existing look: `card draft`, `head`, `badge`, `btn primary` classes from `dashboard/app/globals.css`; keep CSS additions minimal.

### Claude's Discretion
- File layout for components; a small shared draft list/card component is fine if two pages would otherwise duplicate it.
- Tests: no dashboard test framework. Use node-runnable checks for pure helpers (e.g. status label/transition helper) in the style of `dashboard/lib/session.check.mjs`, plus a live curl/browser check against the local stack (API on 127.0.0.1:18000, tenant keys issued via the existing operator endpoint; never print keys; revoke test keys afterwards). To create sample drafts for the live check, call the existing `POST /quotes` and `POST /reviews/draft` (these may call the LLM; if the local model is unavailable, insert via the API with `request` input for quotes, or note that live data could not be produced).
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` - DRAFT-01..05
- `.planning/ROADMAP.md` - Phase 12 success criteria
- `.planning/phases/11-sign-in-and-tenant-shell/11-0{1,2,3}-SUMMARY.md` - session, nav, data-layer patterns
- `api/app/drafts.py`, `api/app/quotes.py`, `api/app/reviews_routes.py` - API and payloads
- `dashboard/lib/data.ts`, `dashboard/lib/session.ts`, `dashboard/lib/session-actions.ts(.stub.ts)`, `dashboard/app/layout.tsx`, `dashboard/next.config.mjs`, `dashboard/app/outreach/page.tsx` (existing approve/reject UI pattern)
</canonical_refs>

<specifics>
## Specific Ideas

Local stack is running (API on 127.0.0.1:18000). Dashboard live mode: `API_URL=http://localhost:18000 SESSION_SECRET=<random> npm run dev` from `dashboard/`.
</specifics>

<deferred>
## Deferred Ideas

- Send/post from the dashboard, editing draft text, filters beyond status, pagination beyond the API's 200 limit
- Capacity flags and daily brief (phase 13)
</deferred>

---

*Phase: 12-quote-and-review-drafts*
*Context gathered: 2026-11-05*
