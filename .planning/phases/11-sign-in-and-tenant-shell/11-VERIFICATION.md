---
phase: 11-sign-in-and-tenant-shell
verified: 2026-11-05T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 11: Sign-in and Tenant Shell Verification Report

**Phase Goal:** An owner signs in with their tenant key and sees their own business, with the old roofing pages still working.
**Status:** passed. **Re-verification:** No.

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Valid key lands on overview with business name; wrong/revoked key shows error, no session | VERIFIED | `session-actions.ts` signIn: `checkKey` bad -> `/login?error=1` before any cookie set; ok -> cookie then `/`. `checkKey` hits `/tenant/me` (rd_live_ keys) or `/admin/tenants`. Layout shows `session.name`. Plan 11-03 curl checks plus orchestrator browser checkpoint (Summit Roofing header). |
| 2 | Key never in HTML, JS, URLs; cookie httpOnly and encrypted | VERIFIED | `session.ts` AES-256-GCM, random IV, auth tag; `httpOnly`, sameSite lax, secure off localhost. Key read only server-side in `data.ts`. No NEXT_PUBLIC usage. Login input is `type=password`, submitted via Server Action POST. 11-03 grep of HTML/static JS clean. |
| 3 | Signed out redirects to login; sign out clears session | VERIFIED | `data.ts call()` redirects to `/login` with no session; `signOut` deletes cookie and redirects. Curl and browser checks passed. |
| 4 | Overview/conversations work on tenant key; calls/outreach/prospects operator-only, hidden from tenants | VERIFIED | All `/admin/*` fetchers use `operator: true` -> `notFound()` for tenant sessions; `NAV` flags them `operatorOnly`; `navFor` filters. Curl: tenant sees 2 nav items, 404 on operator pages; admin sees 5. |
| 5 | Nav hides screens for modules the pack does not enable | VERIFIED (mechanism) | `NavItem.module` filtered against `session.modules` from `/tenant/me.enabled_modules`; `session.check.mjs` covers it. No current screen carries a `module` tag, so it is exercised by tests only; later phases add module screens. |

## Behavioral Spot-Checks (run by verifier)

| Check | Result |
|-------|--------|
| `cd dashboard && npm run check` | `session check ok` |
| `python3 -m scripts.check_shared` | `check-shared OK: 11 allowlisted files` |
| `env -u API_URL EXPORT=1 npm run export` | EXIT=0, static export built |

`make g-test` (1277 passed) and live curl checks a-h taken from plan 11-03 evidence; not re-run (stack not started).

## Requirements

AUTH-01..07 and KEEP-01 all SATISFIED per the truths above. No orphaned requirements.

## Known accepted gaps (not blocking)

- No rate limit on the login action (key length capped at 256 only).
- Overview subtitle still says "Summit Roofing" for all tenants.
- Truth 5 has no real module-gated screen yet.

## Anti-patterns

No TBD/FIXME/XXX in the verified files. No stubs found.

## Human Verification

None outstanding; browser checkpoint was done by the orchestrator.

_Verifier: Claude (gsd-verifier)_
