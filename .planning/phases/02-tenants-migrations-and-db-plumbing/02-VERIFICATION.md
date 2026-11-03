---
phase: 02-tenants-migrations-and-db-plumbing
verified: 2026-11-03
status: passed
score: 5/5 success criteria, 6/6 requirements
---

# Phase 2 Verification

**Goal:** database is multi-tenant ready with no behaviour change for Summit Roofing. **Result: achieved.**

## Success criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Numbered migrations apply to a live DB copy | VERIFIED | `db/migrations/001-004`; `bootstrap.apply_migrations` uses `schema_migrations`, advisory lock, one tx per file; `python -m app.bootstrap` entrypoint; `test_migrations.py` passes |
| 2 | Two tenants share slot time / external id | VERIFIED | 003: `slots_tenant_start_key`, `conversations_tenant_external_key`, appointments `(tenant_id, slot_id/lead_id)`; old global uniques dropped; composite FKs; `test_tenancy.py` passes |
| 3 | Slot gen and FAQ seeding per tenant | VERIFIED | `tools.ensure_slots` filters/ON CONFLICT on tenant_id; `faq.seed_faq(tenant)` checks only that tenant's rows; `main.py` startup loops all tenants; 001 fixes faq_chunks sequence |
| 4 | Logs and agent_events carry tenant; eval matches baseline | VERIFIED | `logctx.TenantFilter` on handler (`main.py:28`), contextvar set in `agent.py:38`; `agent_events` has tenant_id NOT NULL + BEFORE UPDATE/DELETE/TRUNCATE triggers (004); `record_event` called from `tools._safe_event`. gate3.log: `regressions: []`, `GATE PASSED`, exit 0; `evals/reports/latest.md`: 94/96, local:llama3.1:8b only, same two failures (voice-over-explainer, voice-indecisive) |
| 5 | Outreach/replies/pilot unchanged, no tenant column | VERIFIED | `db/outreach.sql` has 0 `tenant` references; `outreach.py`/`pilot.py` still use raw `engine` (intended untenanted); prospects/scrapes/replies have no tenant references |

## Requirements

| Req | Status | Evidence |
|-----|--------|----------|
| TEN-01 | SATISFIED | runner above, no volume recreate |
| TEN-02 | SATISFIED | 002 adds `tenant_id` to leads, conversations, messages, slots, appointments, faq_chunks, tool_calls, escalations, events (llm_calls nullable by design so outreach rows stay untenanted); 003 composites |
| TEN-03 | SATISFIED | `db.tx(tenant_id)` does `set_config('app.tenant_id', :t, true)` (transaction-local), validates UUID first; `db.system()` for explicit untenanted; tools/faq/agent/main/admin go through `tx`/`system`; `test_rls_proof.py` and call-site grep gate test |
| TEN-04 | SATISFIED | see criterion 3 |
| TEN-05 | SATISFIED | see criterion 4 |
| TEN-06 | SATISFIED | see criterion 5 |

## Checks run

- `make g-test`: **265 passed, 1 warning** (starlette deprecation only), 24.5s.
- Full eval gate not re-run (hours); confirmed by reading gate3.log and latest.md.

## Notes (not gaps)

- `tenant_id DEFAULT` Summit remains on tenant tables by design; dropped in Phase 6.
- RLS policies are not enabled yet (proof-of-pattern only, `test_rls_proof.py`); not a Phase 2 requirement. Table owner/superuser bypass applies until Phase 6.
- No migration checksum (documented shortcut in `bootstrap.py`).
- `main.py`/`admin.py` use `tx()` with the default tenant in a few single-tenant endpoints; acceptable until per-tenant API keys (later phase).
