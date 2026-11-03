# Requirements: RoofDesk Global

**Defined:** 2026-11-03
**Core Value:** Onboarding a new business is a config pack, not a code change, and the roofing pack keeps scoring 94/96 on evals while it moves.

Actor note: "Operator" = the RoofDesk owner (Erven). "Business owner" = a tenant's customer. "Lead" = a business's end customer chatting with the agent.

## v1 Requirements

### Baseline (BASE)
- [ ] **BASE-01**: Operator can tag the current commit `v1-roofing` and has a machine-readable per-scenario baseline of eval results
- [ ] **BASE-02**: Operator can see eval flake rate (3 runs, model tag and temperature pinned) so the regression gate has a known tolerance
- [ ] **BASE-03**: Operator can run the branch on an isolated compose project/volume so the live roofdeskai.com demo is untouched
- [ ] **BASE-04**: Every migration step reruns the eval and fails on any per-scenario-id difference from the baseline (flipped scenarios rerun twice before counting)

### Tenancy (TEN)
- [ ] **TEN-01**: Operator can apply numbered SQL migrations to a live database without recreating the volume
- [ ] **TEN-02**: Every tenant table (leads, slots, conversations, appointments, FAQ rows) carries `tenant_id`, with composite uniques so two tenants can share a slot time or external id
- [ ] **TEN-03**: All tenant data access goes through one `db.tx(tenant_id)` helper that sets a transaction-local tenant context
- [ ] **TEN-04**: Slot generation and FAQ seeding work per tenant (no tenant skipped by another tenant's rows)
- [ ] **TEN-05**: Logs and an append-only `agent_events` table are stamped with tenant id
- [ ] **TEN-06**: Operator outreach, replies and pilot flows remain outside the tenant model

### Business Pack (PACK)
- [ ] **PACK-01**: Operator can define a business as a folder of YAML files under `businesses/<slug>/` validated at load by Pydantic (`extra="forbid"`), failing with a clear error on bad packs
- [ ] **PACK-02**: Summit Roofing pack holds the values previously hardcoded in `policy.py`, `faq.py`, `agent.py`, `tools.py` and the prompts, verified by a golden test that pack values equal the old constants
- [ ] **PACK-03**: Agent prompts are templated from the pack and the roofing render is byte-identical to today's
- [ ] **PACK-04**: Reply strings, booking confirmation email and demo disclaimer come from pack `messages:` templates
- [ ] **PACK-05**: Calendar settings (hours, slot length, days ahead, buffer, timezone) come from the pack
- [ ] **PACK-06**: Roofing-specific escalation safety patterns live in the pack; generic defaults stay in code
- [ ] **PACK-07**: Pack-keyed caches include tenant and pack hash; no module-level business globals remain

### Qualification (QUAL)
- [ ] **QUAL-01**: A lead is qualified by a rule interpreter reading `qualification.yaml` (in_list, yes_no, max_number, in_area) with pack-defined questions and disqualify text
- [ ] **QUAL-02**: Service-word synonyms and the non-business word list come from the pack
- [ ] **QUAL-03**: A differential test over a large lead grid shows zero differences between the old `qualification()` and the interpreter before the old path is deleted

### Evals (EVAL)
- [ ] **EVAL-01**: Operator can run evals per pack (`--pack`) with per-pack reports that never overwrite another pack's baseline
- [ ] **EVAL-02**: Roofing pack scores 94/96 with the same two failures after every step through Phase 5
- [ ] **EVAL-03**: Dental pack has ~40 scenarios across the ten categories; no category under 90% and emergency escalation recall 100%
- [ ] **EVAL-04**: Cross-tenant retrieval and two-tenant interleaved scenarios prove no leakage between packs
- [ ] **EVAL-05**: Each new engine module has its own deterministic eval set
- [ ] **EVAL-06**: 20 held-out scenarios are written before tuning, run once, and the score is published even if low

### Access Control (SEC)
- [ ] **SEC-01**: Operator can issue, rotate and revoke per-tenant API keys; keys are hashed at rest and shown once
- [ ] **SEC-02**: Tenant is derived from the credential, never from the request body; requests without a key get 401
- [ ] **SEC-03**: Row-level security is enforced (FORCE, non-owner app role) on all tenant tables with the default-tenant column default dropped
- [ ] **SEC-04**: A cross-tenant leak test covering chat, FAQ, slots and metrics passes on an RLS-enabled database
- [ ] **SEC-05**: Admin endpoints use a separate super-admin scope and no longer return cross-tenant data to tenant keys

### Engine Modules (MOD)
- [ ] **MOD-01**: Quote builder turns a request plus `services.yaml` into line items and a Decimal total; a missing price asks or escalates, never guesses
- [ ] **MOD-02**: Quote drafts go to the existing approval queue and are validated against the computed quote, not the price-claim regex
- [ ] **MOD-03**: Capacity checker compares bookings to `capacity.yaml` and flags over/under-staffed shifts, deduplicated and re-flagged when inputs change, DST-safe
- [ ] **MOD-04**: Connector layer has one interface with mock adapters (sheet, accounting, bookings, ads), labelled as mock in output
- [ ] **MOD-05**: Daily brief merges connector data into a one-page owner summary in tenant-local time, flags numbers that disagree and shows "source unavailable" explicitly
- [ ] **MOD-06**: Review responder drafts replies in the pack tone; a deterministic post-check blocks refund, fault, compensation, unknown-fact and PII language, then one regeneration, then `needs_human`; drafts are never auto-posted
- [ ] **MOD-07**: `intake_event` webhook stores one idempotent record per person from waiver, check-in and result events using pack payload mapping

### Workflows (WF)
- [ ] **WF-01**: The 6 existing n8n workflows are tenant-aware (tenant key header, owner address returned by the API)
- [ ] **WF-02**: New workflows exist and run: quote-request, review-reply, capacity-check, daily-brief, intake-event
- [ ] **WF-03**: Scheduled workflows loop over tenants via `GET /admin/tenants`; the API decides which tenants are due in their local time
- [ ] **WF-04**: The platform runs end to end through the API with n8n switched off
- [ ] **WF-05**: A CI check fails if any n8n HTTP node calling the API lacks the tenant key header

### Onboarding, Docs, Privacy (OPS)
- [ ] **OPS-01**: `make new-business` validates a pack, loads it and runs a smoke subset of evals with cross-tenant and escalation baselines
- [ ] **OPS-02**: One SOP per workflow and a runbook are generated per pack, with a CI drift check
- [ ] **OPS-03**: PII masking filter (email, phone) applies to all logs, with a unit-tested `mask()`
- [ ] **OPS-04**: A retention setting really purges stored data and a `delete_subject` operation exists
- [ ] **OPS-05**: A data-map document lists stores, processors and the dental health-data and cross-border caveats
- [ ] **OPS-06**: A grep gate fails CI if `roof|Summit|Denver` appears in shared (non-pack) code
- [ ] **OPS-07**: README shows a per-business scorecard and the workflow catalog

### Optional Platform Extras (EXT)
- [ ] **EXT-01**: Anthropic is an optional LLM provider (local stays default); scorecard runs pin `providers=[anthropic]` so fallback cannot contaminate scores
- [ ] **EXT-02**: Connectors are exposed as MCP servers (mcp 2.x) wrapping the same adapter classes
- [ ] **EXT-03**: Third pack (venue/experience business with staff and group bookings) exercises quotes, capacity and intake and passes its own evals

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

Filled by the roadmapper.

| Requirement | Phase | Status |
|-------------|-------|--------|

**Coverage:** v1 requirements: 51 total, 0 mapped (pending roadmap)

---
*Requirements defined: 2026-11-03*
*Last updated: 2026-11-03 after initial definition*
