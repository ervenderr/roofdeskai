---
phase: 06-per-tenant-keys-and-rls-enforcement
verified: 2026-11-04T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Confirm production deploy sets PUBLIC_DEMO_TENANT_ID, a non-default APP_DB_PASSWORD and POSTGRES_PASSWORD"
    expected: "roofdeskai.com /chat works keyless only via the env; app_rw password is not app_rw_dev"
    why_human: "Deploy config is outside the repo; compose defaults are dev values"
  - test: "Accept or reject the D-06 admin fallback and the keyless /chat demo path as deliberate deviations"
    expected: "Owner decision recorded"
    why_human: "Policy decision"
---

# Phase 6 Verification

Goal: tenants isolated by credential and by the database. Verified by reading code and tests. pytest and evals were NOT re-run; counts (615 passed, roofing 94/96, dental 43/43) are recorded evidence from 06-06-SUMMARY only.

## Success criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Issue (shown once), rotate, revoke; revoked gets 401 | VERIFIED | `auth.py` `issue_key`: `rd_live_`+`token_urlsafe(32)`, only sha256 hex inserted, plaintext returned only in the issue/rotate response. `list_keys` selects id/label/created_at/revoked_at, no hash. `rotate_key` revokes old and inserts new in one `system()` transaction (404 on missing old key rolls back the insert). `_resolve` filters `revoked_at IS NULL`. Routes in `tenant_admin.py` (admin-key gated). Tests: `test_keys.py` (issue stores only sha256, rotate, revoke, http lifecycle). |
| 2 | No key -> 401; body tenant ignored | VERIFIED | `_resolve` raises one generic 401 for missing prefix, oversize, unknown, revoked. `ChatIn` has no tenant field; tenant comes from `chat_tenant`/`require_scope`. A tenant key ignores `X-Tenant-Id` (`require_scope` returns before reading it). Tests: `test_routes_scope.py` body/header-ignored, `test_leak.py::test_chat_lands_in_credential_tenant...`. Exception: `/chat` keyless when `PUBLIC_DEMO_TENANT_ID` is set (see deviations). Invalid key never falls through to the demo or admin path. |
| 3 | RLS on, non-owner app role, no context -> 0 rows | VERIFIED | `005_rls.sql`: `app_rw` NOSUPERUSER NOBYPASSRLS, explicit grants (no ALL TABLES, `agent_events` is SELECT/INSERT only, `tenant_api_keys` and outreach tables not granted), ENABLE+FORCE RLS on 11 tables, policy USING and WITH CHECK on `NULLIF(current_setting('app.tenant_id', true),'')::uuid` (unset or empty means NULL means 0 rows), `tenant_id` DEFAULT dropped on 9 tables. `db.tx` uses transaction-local `set_config` on `app_engine`. `assert_rls_enforced()` in lifespan fails startup if the app role is superuser, BYPASSRLS, or owns `leads`. Tests: `test_rls_proof.py` (catalog FORCE/defaults/role shape, fail-closed, insert rejected), `test_leak.py::test_app_role_without_context_sees_zero_rows` (11 tables) and insert-without-context rejected. Note: `assert_rls_enforced` checks only `leads` ownership, not the other 10 tables. |
| 4 | Leak test across chat, FAQ, slots, metrics | VERIFIED | `test_leak.py` covers lists, metrics (tenant vs admin), chat, cross-tenant conversation 404, 401 cases, `lookup_faq`, slots/booking, zero-context rows. Recorded result: 27 cases pass, full suite 615 passed. Not re-run by me. |
| 5 | Tenant key cannot read cross-tenant admin data | VERIFIED | `tenant_admin` router has `dependencies=[Depends(auth.require_admin)]`; a tenant key sends no `X-Admin-Key`, so 403. Read routes use `require_scope`: tenant key -> `tx(tenant)` via the RLS engine; only the admin key without `X-Tenant-Id` uses `system()` (cross-tenant). `test_leak.py::test_tenant_key_rejected_on_admin_only_routes`, `test_metrics_tenant_scoped_admin_cross_tenant`. Outreach/pilot/intake stay on the admin key and the owner engine (D-08, tables not granted to `app_rw`). |

## Requirements

| Req | Status | Note |
|-----|--------|------|
| SEC-01 | PASS | hashed at rest, shown once, rotate/revoke implemented and tested |
| SEC-02 | PASS with caveat | tenant from credential; keyless `/chat` demo path and admin fallback are deliberate exceptions |
| SEC-03 | PASS | FORCE RLS, non-owner role, defaults dropped, startup assert, catalog test |
| SEC-04 | PASS | leak test present and substantive (recorded green) |
| SEC-05 | PASS | admin scope separate; tenant keys 403 on admin routes and are RLS-scoped on reads |

REQUIREMENTS.md still shows SEC-01..05 as `[ ]` / Pending; update it.

## Deviations (flag)

1. **D-06 not fully met.** `admin.py:_write_tenant` falls back to `settings.default_tenant_id` (Summit Roofing) when the admin key is used on write routes (`inbound`, `resolve_escalation`, `draft_followup`) with no `X-Tenant-Id`; logs a warning. `triage.py:64` also uses the default tenant pack. Intentional until n8n moves to tenant keys (Phase 8); a writes-to-wrong-tenant risk exists for any admin caller that omits the header. Config constant retained.
2. **D-10 second engine.** `db.engine` (owner) and `app_engine` (app_rw). `system()` defaults to the owner engine, which bypasses RLS. Many untenanted modules use `engine.begin()` directly (outreach, prospects, scrapes, pilot, bootstrap); none are tenant tables, acceptable per D-08. Risk: nothing mechanically stops tenant code from using `system()`; enforced by convention and tests only. If `APP_DATABASE_URL` is empty, `app_engine` falls back to the owner URL, but `assert_rls_enforced` then aborts startup (good).
3. **D-05 keyless `/chat`.** `PUBLIC_DEMO_TENANT_ID` set means unauthenticated `/chat` is served for that tenant. Default unset; not set in compose in the repo. Protected only by the per-IP in-process rate limiter. Expected and documented; deploy must set it for the live demo.

## Security concerns (non-blocking, WARNING)

- No rate limit or lockout on key guesses: `chat_rate_limit` covers `/chat` only; `X-API-Key` on other routes and `X-Admin-Key` are unthrottled. Keys are 256-bit, so brute force is infeasible, but add edge limiting before public exposure. Limiter is also per-process and keyed on `request.client.host` (proxy IP behind a tunnel unless forwarded headers are handled).
- Key-hash lookup is by indexed equality on sha256, then `compare_digest` on equal strings (redundant but harmless).
- Shared `app_rw` role and password across all tenants: isolation relies on RLS plus `set_config`, not per-tenant DB credentials (the design choice). Password comes from `APP_DB_PASSWORD`, applied at bootstrap via `ALTER ROLE ... %L`.
- Compose dev defaults: `APP_DB_PASSWORD:-app_rw_dev`, `POSTGRES_PASSWORD:-leadpilot` (docker-compose.yml lines 6, 21-23). Must be overridden in any exposed deploy.
- `assert_rls_enforced` only checks ownership of `leads`; a table owned by `app_rw` elsewhere would escape RLS unnoticed (FORCE RLS mitigates; `test_rls_proof` catalog test covers FORCE).
- CORS `allow_headers=["content-type"]` and `allow_methods=["POST"]`: browsers cannot send `X-API-Key` cross-origin. Fine for the keyless demo page; server-to-server and n8n unaffected.
- Admin key compare: `hmac.compare_digest(str, str)` raises TypeError on non-ASCII header values (possible 500, not a bypass). Minor.

## Anti-patterns

No TBD/FIXME/XXX checked beyond targeted files read; none seen in the files read. One documented `shortcut:` comment in `bootstrap.py` (no migration checksum).

## Gaps

None blocking. Status is `human_needed` only for the deploy-config and deviation-acceptance items in the frontmatter.

---
_Verifier: Claude (gsd-verifier). Tests and evals not executed in this verification._
