# Phase 11: Sign-in and Tenant Shell - Context

**Gathered:** 2026-11-05
**Status:** Ready for planning
**Source:** User-approved defaults (no discuss-phase)

<domain>
## Phase Boundary

Login page, encrypted session, tenant header/nav, and moving the existing dashboard data calls onto the signed-in key. No new data screens (drafts, capacity, brief are phases 12 and 13). Local only; no deploy.
</domain>

<decisions>
## Implementation Decisions

### Locked
- Session cookie is sealed with Node `crypto` (AES-256-GCM) using `SESSION_SECRET` env var; httpOnly, SameSite=Lax, Secure when not on localhost. No new npm dependency.
- Login is a server action. It validates a pasted key by calling `GET /tenant/me` with `X-API-Key`. Wrong or revoked key: plain error, no cookie. The key is never in HTML, client JS or URLs.
- Pasting the admin key (does not start with `rd_live_`) starts an OPERATOR session, validated against an admin-only route. Operator session = today's behaviour: sees Overview, Conversations, Calls, Outreach, Prospects, using `X-Admin-Key`.
- Tenant session sees Overview and Conversations only (the `/metrics` and `/conversations` routes accept tenant keys via `require_scope`). Calls, Outreach and Prospects are admin-only API routes with no tenant column (`outreach_routes.py` uses `require_admin`) and are hidden from tenant sessions; direct URL gives redirect or 404.
- Header shows the business name from `GET /tenant/me`. Nav hides screens for modules the pack does not enable (`enabled_modules` in `/tenant/me`). Phase 12 and 13 screens do not exist yet, so only the nav gating mechanism ships now.
- Unauthenticated page request redirects to `/login`. Sign out clears the cookie.
- `lib/data.ts` currently reads `ADMIN_API_KEY` from env at module level. Replace with a per-request credential read from the session (server side only).

### Static demo (KEEP-02 groundwork)
- `EXPORT=1` builds a static site from `data/snapshot.json`: no cookies, middleware or server actions work there. In static/demo mode (no `API_URL`) there is no sign-in and no redirect; pages read the snapshot as today. Sign-in applies only when `API_URL` is set (live mode). Next `middleware` is not allowed with `output: "export"`, so gating must not run in export builds.

### Claude's Discretion
- File layout under `dashboard/lib` and `dashboard/app/login`; use Next 15 `cookies()` from `next/headers` (async in Next 15).
- Test approach: the dashboard has no test setup; use small node-runnable checks for seal/unseal and a manual `curl`/browser check against the local stack. Do not add a test framework unless trivial.
- Secrets: `SESSION_SECRET` goes in `.env.example` with no real value; never print env values.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` - AUTH-01..07, KEEP-01
- `.planning/ROADMAP.md` - Phase 11 success criteria
- `dashboard/lib/data.ts` - current API access and snapshot mode
- `dashboard/app/layout.tsx` - header and nav
- `dashboard/next.config.mjs` - export mode and review-actions stub
- `api/app/auth.py` - `require_scope`, `require_tenant`, key prefix `rd_live_`
- `api/app/tenant_routes.py` - `GET /tenant/me`
- `api/app/admin.py` - which routes accept tenant keys
- `api/app/outreach_routes.py` - admin-only routes
</canonical_refs>

<specifics>
## Specific Ideas

Local stack: `make g-up` starts the branch stack (volumes kept). A tenant key is issued by the existing operator script/endpoint; check `Makefile` and `api/app/tenant_admin.py`.
</specifics>

<deferred>
## Deferred Ideas

- Key issue/rotate from the UI, multi-user accounts, roles (future requirements)
- Drafts, capacity and brief screens (phases 12, 13)
</deferred>

---

*Phase: 11-sign-in-and-tenant-shell*
*Context gathered: 2026-11-05*
