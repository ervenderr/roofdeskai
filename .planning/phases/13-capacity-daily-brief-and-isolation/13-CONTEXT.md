# Phase 13: Capacity, Daily Brief and Isolation - Context

**Gathered:** 2026-11-05
**Status:** Ready for planning
**Source:** Defaults carried from phases 11 and 12 (no discuss-phase, no research, no UI-SPEC)

<domain>
## Phase Boundary

Capacity flags screen, a tenant-scoped read endpoint for the daily brief plus its screen, a two-tenant isolation test, static demo intact, roofing gate intact. Local only; no deploy.
</domain>

<decisions>
## Implementation Decisions

### Locked
- Capacity: `GET /capacity/flags?open=true|false` (api/app/capacity_routes.py, `require_tenant`, module `capacity`). Rows: flag_key, kind, shift_id, shift_date, details (jsonb), first_flagged_at, reflagged_at, resolved_at. Page `/capacity`, nav module tag `capacity`, tenant-session only (same pattern as `/quotes`: `tenant: true` in `call()`, `requireTenantModule`, 404 otherwise). Default view = open flags (`?open=true` in the API call); a link/toggle `?all=1` shows all. Read-only screen; no resolve action. Show details fields as text; do not invent figures (details come from the API: staff, covers, capacity).
- Brief: the ONLY api change in v1.1. Add `GET /daily-brief` in api/app/brief_routes.py (`require_tenant`, module `connectors` via `require_module`, tenant-scoped `tx(tenant)`), returning `{latest: <payload or null>, runs: [{run_date, created_at}...]}` for the latest 14 runs from `brief_runs` (RLS covered). Must be registered so it does not collide with `POST /daily-brief/due`. Test first (api tests use the existing fixtures, see api/app/test_capacity_api.py). Existing POST behaviour unchanged.
- Brief screen `/brief` (nav module tag `connectors`, tenant-only). Show `local_date`, `text` as plain text (React escaping; never `dangerouslySetInnerHTML` for `html`), and `sources[]` with name, `source` label (mock data labelled "mock data"), `ok`/`error` (unavailable sources shown with their error), metrics as API strings. Empty state when no run exists ("No brief yet"); the screen does not trigger POST (no generate button).
- Isolation test (ISO-01): a Python test in api (two tenants, each with its own key: drafts, flags, brief visible only to the owner) AND a live curl check through the dashboard with two tenant sessions (extend the 12-03 style). Use packs that enable the modules; seed minimal rows via existing POST endpoints (`POST /capacity/check` with bookings, `POST /daily-brief`), mock connectors only.
- Static export (`EXPORT=1`): `/capacity` and `/brief` show "not available in the static demo" (same pattern as quotes); export build stays green and has no nav links to them.
- Tenant keys for live checks: issue via existing operator endpoint, store only in the scratchpad, never print values, revoke afterwards. Browser sign-in is done by the user pasting the key (the assistant may not read key values into the conversation).
- Gates at the end: `npm run check`, `npm run build`, static export, `python3 -m scripts.check_shared`, `make g-test` (mandatory). The agent path is not touched, so the roofing eval gate is unchanged.

### Claude's Discretion
- Component layout, minimal CSS additions using existing classes, pure helper in `dashboard/lib` with node checks like `drafts.check.mjs`.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` CAP-01, BRF-01, BRF-02, ISO-01, KEEP-02
- `.planning/phases/12-quote-and-review-drafts/12-0{1,2,3}-SUMMARY.md` (patterns, nav, tenant-only data calls)
- `api/app/capacity_routes.py`, `api/app/brief_routes.py`, `db/migrations/007_engine_modules.sql`, `api/app/engine/connectors.py` (mock labelling)
- `dashboard/app/quotes/page.tsx`, `dashboard/lib/data.ts`, `dashboard/lib/session.ts`
</canonical_refs>

<deferred>
## Deferred Ideas

- Resolve/ack flags from the UI, generate-brief button, brief history browsing beyond the run list, rate limit on login
</deferred>

---

*Phase: 13-capacity-daily-brief-and-isolation*
*Context gathered: 2026-11-05*
