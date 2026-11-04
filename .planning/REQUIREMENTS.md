# Requirements: RoofDesk Global

**Defined:** 2026-11-03
**Core Value:** Onboarding a new business is a config pack, not a code change, and the roofing pack keeps scoring 94/96 on evals while it moves.

Actor note: "Operator" = the RoofDesk owner (Erven). "Business owner" = a tenant's customer. "Lead" = a business's end customer chatting with the agent.

## v1 Requirements

### Baseline (BASE)
- [x] **BASE-01**: Operator can tag the current commit `v1-roofing` and has a machine-readable per-scenario baseline of eval results
- [x] **BASE-02**: Operator can see eval flake rate (3 runs, model tag and temperature pinned) so the regression gate has a known tolerance
- [x] **BASE-03**: Operator can run the branch on an isolated compose project/volume so the live roofdeskai.com demo is untouched
- [x] **BASE-04**: Every migration step reruns the eval and fails on any per-scenario-id difference from the baseline (flipped scenarios rerun twice before counting)

### Tenancy (TEN)
- [x] **TEN-01**: Operator can apply numbered SQL migrations to a live database without recreating the volume
- [x] **TEN-02**: Every tenant table (leads, slots, conversations, appointments, FAQ rows) carries `tenant_id`, with composite uniques so two tenants can share a slot time or external id
- [x] **TEN-03**: All tenant data access goes through one `db.tx(tenant_id)` helper that sets a transaction-local tenant context
- [x] **TEN-04**: Slot generation and FAQ seeding work per tenant (no tenant skipped by another tenant's rows)
- [x] **TEN-05**: Logs and an append-only `agent_events` table are stamped with tenant id
- [x] **TEN-06**: Operator outreach, replies and pilot flows remain outside the tenant model

### Business Pack (PACK)
- [x] **PACK-01**: Operator can define a business as a folder of YAML files under `businesses/<slug>/` validated at load by Pydantic (`extra="forbid"`), failing with a clear error on bad packs
- [x] **PACK-02**: Summit Roofing pack holds the values previously hardcoded in `policy.py`, `faq.py`, `agent.py`, `tools.py` and the prompts, verified by a golden test that pack values equal the old constants
- [x] **PACK-03**: Agent prompts are templated from the pack and the roofing render is byte-identical to today's
- [x] **PACK-04**: Reply strings, booking confirmation email and demo disclaimer come from pack `messages:` templates
- [x] **PACK-05**: Calendar settings (hours, slot length, days ahead, buffer, timezone) come from the pack
- [x] **PACK-06**: Roofing-specific escalation safety patterns live in the pack; generic defaults stay in code
- [x] **PACK-07**: Pack-keyed caches include tenant and pack hash; no module-level business globals remain

### Qualification (QUAL)
- [x] **QUAL-01**: A lead is qualified by a rule interpreter reading `qualification.yaml` (in_list, yes_no, max_number, in_area) with pack-defined questions and disqualify text
- [x] **QUAL-02**: Service-word synonyms and the non-business word list come from the pack
- [x] **QUAL-03**: A differential test over a large lead grid shows zero differences between the old `qualification()` and the interpreter before the old path is deleted

### Evals (EVAL)
- [x] **EVAL-01**: Operator can run evals per pack (`--pack`) with per-pack reports that never overwrite another pack's baseline
- [x] **EVAL-02**: Roofing pack scores 94/96 with the same two failures after every step through Phase 5
- [x] **EVAL-03**: Dental pack has ~40 scenarios across the ten categories; no category under 90% and emergency escalation recall 100%
- [x] **EVAL-04**: Cross-tenant retrieval and two-tenant interleaved scenarios prove no leakage between packs
- [x] **EVAL-05**: Each new engine module has its own deterministic eval set
- [x] **EVAL-06**: 20 held-out scenarios are written before tuning, run once, and the score is published even if low

### Access Control (SEC)
- [x] **SEC-01**: Operator can issue, rotate and revoke per-tenant API keys; keys are hashed at rest and shown once
- [x] **SEC-02**: Tenant is derived from the credential, never from the request body; requests without a key get 401
- [x] **SEC-03**: Row-level security is enforced (FORCE, non-owner app role) on all tenant tables with the default-tenant column default dropped
- [x] **SEC-04**: A cross-tenant leak test covering chat, FAQ, slots and metrics passes on an RLS-enabled database
- [x] **SEC-05**: Admin endpoints use a separate super-admin scope and no longer return cross-tenant data to tenant keys

### Engine Modules (MOD)
- [x] **MOD-01**: Quote builder turns a request plus `services.yaml` into line items and a Decimal total; a missing price asks or escalates, never guesses
- [x] **MOD-02**: Quote drafts go to the existing approval queue and are validated against the computed quote, not the price-claim regex
- [x] **MOD-03**: Capacity checker compares bookings to `capacity.yaml` and flags over/under-staffed shifts, deduplicated and re-flagged when inputs change, DST-safe
- [x] **MOD-04**: Connector layer has one interface with mock adapters (sheet, accounting, bookings, ads), labelled as mock in output
- [x] **MOD-05**: Daily brief merges connector data into a one-page owner summary in tenant-local time, flags numbers that disagree and shows "source unavailable" explicitly
- [x] **MOD-06**: Review responder drafts replies in the pack tone; a deterministic post-check blocks refund, fault, compensation, unknown-fact and PII language, then one regeneration, then `needs_human`; drafts are never auto-posted
- [x] **MOD-07**: `intake_event` webhook stores one idempotent record per person from waiver, check-in and result events using pack payload mapping

### Workflows (WF)
- [x] **WF-01**: The existing tenant-facing n8n workflows (inbound-message, followup-scheduler, escalation-alert) are tenant-aware; outreach-flow and error-handler stay untenanted (tenant key header, owner address returned by the API)
- [x] **WF-02**: New workflows exist and run: quote-request, review-reply, capacity-check, daily-brief, intake-event
- [x] **WF-03**: Scheduled workflows loop over tenants via `GET /admin/tenants`; the API decides which tenants are due in their local time
- [x] **WF-04**: The platform runs end to end through the API with n8n switched off
- [x] **WF-05**: A CI check fails if any n8n HTTP node calling the API lacks the tenant key header

### Onboarding, Docs, Privacy (OPS)
- [x] **OPS-01**: `make new-business` validates a pack, loads it and runs a smoke subset of evals with cross-tenant and escalation baselines
- [x] **OPS-02**: One SOP per workflow and a runbook are generated per pack, with a CI drift check
- [x] **OPS-03**: PII masking filter (email, phone) applies to all logs, with a unit-tested `mask()`
- [x] **OPS-04**: A retention setting really purges stored data and a `delete_subject` operation exists
- [x] **OPS-05**: A data-map document lists stores, processors and the dental health-data and cross-border caveats
- [x] **OPS-06**: A grep gate fails CI if `roof|Summit|Denver` appears in shared (non-pack) code
- [x] **OPS-07**: README shows a per-business scorecard and the workflow catalog

### Optional Platform Extras (EXT)
- [x] **EXT-01**: Anthropic is an optional LLM provider (local stays default); scorecard runs pin `providers=[anthropic]` so fallback cannot contaminate scores
- [x] **EXT-02**: Connectors are exposed as MCP servers (mcp 2.x) wrapping the same adapter classes
- [x] **EXT-03**: Third pack (venue/experience business with staff and group bookings) exercises quotes, capacity and intake and passes its own evals

## v2 Requirements (deferred)

- **V2-01**: Supplier-order workflow with mock supplier and human approval (cut first)
- **V2-02**: Agent Office live view on an MIT base (2D), then Agent Flight Recorder wrap
- **V2-03**: Appointment reminders and no-show follow-up; knowledge-gap loop; nightly eval run (first three of the automation backlog)
- **V2-04**: Approval digest, escalation reminder, post-visit review request (all customers, no sentiment gating), weekly owner report, provider health monitor, new-business onboarding automation
- **V2-05**: Real connectors and write actions, real SMS/phone line, more languages
- **V2-06**: Clerk login; project rename away from "RoofDesk"

## Out of Scope

| Feature | Reason |
|---------|--------|
| Video editing pipeline | A tools inventory, not software |
| LLM-generated or ballpark prices | Code computes numbers; model only phrases |
| Auto-posting review replies / auto-sending quotes | Human approval required |
| Review sentiment gating | Breaks Google review rules |
| Public multi-tenant exposure before SEC-01..04 | Shared admin key unsafe |
| Outbound/scraping in the customer package | Tool for selling RoofDesk itself |
| Copying agents-office code | PolyForm Noncommercial license |
| Alembic, Presidio, structlog, rules engine, Redis/Celery | Research: plain SQL migrations and stdlib suffice |
| Real health data in the dental pack | Demo uses synthetic data until legal review |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BASE-01 | Phase 1 | Complete |
| BASE-02 | Phase 1 | Complete |
| BASE-03 | Phase 1 | Complete |
| BASE-04 | Phase 1 | Complete |
| TEN-01 | Phase 2 | Complete |
| TEN-02 | Phase 2 | Complete |
| TEN-03 | Phase 2 | Complete |
| TEN-04 | Phase 2 | Complete |
| TEN-05 | Phase 2 | Complete |
| TEN-06 | Phase 2 | Complete |
| PACK-01 | Phase 3 | Complete |
| PACK-02 | Phase 3 | Complete |
| PACK-03 | Phase 3 | Complete |
| PACK-04 | Phase 3 | Complete |
| PACK-05 | Phase 3 | Complete |
| PACK-06 | Phase 3 | Complete |
| PACK-07 | Phase 3 | Complete |
| QUAL-01 | Phase 4 | Complete |
| QUAL-02 | Phase 4 | Complete |
| QUAL-03 | Phase 4 | Complete |
| EVAL-01 | Phase 5 | Complete |
| EVAL-02 | Phase 5 | Complete |
| EVAL-03 | Phase 5 | Complete |
| EVAL-04 | Phase 5 | Complete |
| SEC-01 | Phase 6 | Complete |
| SEC-02 | Phase 6 | Complete |
| SEC-03 | Phase 6 | Complete |
| SEC-04 | Phase 6 | Complete |
| SEC-05 | Phase 6 | Complete |
| MOD-01 | Phase 7 | Complete |
| MOD-02 | Phase 7 | Complete |
| MOD-03 | Phase 7 | Complete |
| MOD-04 | Phase 7 | Complete |
| MOD-05 | Phase 7 | Complete |
| MOD-06 | Phase 7 | Complete |
| MOD-07 | Phase 7 | Complete |
| EVAL-05 | Phase 7 | Complete |
| WF-01 | Phase 8 | Complete |
| WF-02 | Phase 8 | Complete |
| WF-03 | Phase 8 | Complete |
| WF-04 | Phase 8 | Complete |
| WF-05 | Phase 8 | Complete |
| OPS-01 | Phase 9 | Complete |
| OPS-02 | Phase 9 | Complete |
| OPS-03 | Phase 9 | Complete |
| OPS-04 | Phase 9 | Complete |
| OPS-05 | Phase 9 | Complete |
| OPS-06 | Phase 9 | Complete |
| OPS-07 | Phase 9 | Complete |
| EVAL-06 | Phase 10 | Complete |
| EXT-01 | Phase 10 | Complete |
| EXT-02 | Phase 10 | Complete |
| EXT-03 | Phase 10 | Complete |

**Coverage:** v1 requirements: 53 total, 53 mapped, 0 unmapped

---
*Requirements defined: 2026-11-03*
*Last updated: 2026-11-03 after initial definition*
