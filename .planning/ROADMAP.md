# Roadmap: RoofDesk Global

## Overview

Turn the single-business Summit Roofing agent into a multi-business platform where a business is a validated config pack. The order protects the regression gate: freeze the baseline, add tenancy plumbing, extract roofing into pack #1, swap qualification to a data-driven interpreter, prove it with a second (dental) pack, lock down access with per-tenant keys and RLS, then add engine modules, tenant-aware n8n, docs/privacy/onboarding, and finally the held-out eval and optional extras. Roofing stays at 94/96 (same two failures) through Phase 5.

## Phases

- [x] **Phase 1: Baseline Freeze and Environment Isolation** - Frozen per-scenario baseline, flake tolerance, isolated branch environment, and the regression gate (completed 2026-11-03)
- [x] **Phase 2: Tenants, Migrations and DB Plumbing** - Numbered migrations, tenant_id everywhere, `db.tx()`, tenant-stamped logs and events (completed 2026-11-03)
- [x] **Phase 3: Pack Loader and Roofing Extraction** - Validated pack format; roofing constants, prompts and messages moved into pack #1 with zero behaviour change (completed 2026-11-03)
- [ ] **Phase 4: Rule Interpreter** - Data-driven qualification proven identical to the old code, then old path deleted
- [ ] **Phase 5: Per-Pack Eval Runner and Dental Pack** - Per-pack reports, dental pack at 90%+ per category, no cross-tenant leakage
- [ ] **Phase 6: Per-Tenant Keys and RLS Enforcement** - Hashed tenant keys, credential-derived tenant, enforced row-level security
- [ ] **Phase 7: Engine Modules and Connectors** - Quote builder, capacity checker, connectors, daily brief, review responder, intake_event, each with deterministic evals
- [ ] **Phase 8: Tenant-Aware n8n** - 11 tenant-aware workflows, API-only operation, CI header check
- [ ] **Phase 9: Docs, PII/Retention and make new-business** - Masking, retention, data map, generated SOPs, onboarding command, grep gate, README
- [ ] **Phase 10: Held-Out Eval and Optional Extras** - 20 held-out scenarios run once, then Anthropic provider, MCP connectors, venue pack

## Phase Details

### Phase 1: Baseline Freeze and Environment Isolation
**Goal**: Operator has a trustworthy, machine-checkable definition of "roofing did not change" and a safe place to work.
**Depends on**: Nothing (first phase)
**Requirements**: BASE-01, BASE-02, BASE-03, BASE-04
**Success Criteria** (what must be TRUE):
  1. `v1-roofing` tag exists and a per-scenario baseline JSON lists every scenario id with pass/fail
  2. Operator can see a flake report from 3 pinned runs (model tag and temperature) stating which scenarios are unstable
  3. Operator can start the branch stack on its own compose project and volume while roofdeskai.com is untouched
  4. Running the gate command fails with the scenario ids that differ from the baseline, rerunning flipped ones twice before counting
**Plans**: TBD

### Phase 2: Tenants, Migrations and DB Plumbing
**Goal**: The database is multi-tenant ready with no behaviour change for Summit Roofing.
**Depends on**: Phase 1
**Requirements**: TEN-01, TEN-02, TEN-03, TEN-04, TEN-05, TEN-06
**Success Criteria** (what must be TRUE):
  1. Operator can apply numbered SQL migrations to a copy of the live DB without recreating the volume
  2. Two tenants can hold the same slot time and the same external conversation id without conflict
  3. Slot generation and FAQ seeding produce rows for a second tenant even when the first already has them
  4. Logs and `agent_events` rows carry the tenant id, and roofing eval still matches the baseline
  5. Outreach, replies and pilot endpoints work unchanged and have no tenant column
**Plans**: TBD

### Phase 3: Pack Loader and Roofing Extraction
**Goal**: Summit Roofing is a pack folder, and the agent reads business values from the pack instead of code.
**Depends on**: Phase 2
**Requirements**: PACK-01, PACK-02, PACK-03, PACK-04, PACK-05, PACK-06, PACK-07
**Success Criteria** (what must be TRUE):
  1. A malformed pack (unknown key, missing field) fails at load with a clear error naming the file and field
  2. A golden test passes showing every pack value equals the old hardcoded constant
  3. The rendered roofing prompt is byte-identical to today's, and replies, confirmation email and demo disclaimer come from pack templates
  4. Hours, slot length, days ahead, buffer and timezone changes in the pack change slot generation
  5. Roofing eval matches the baseline per scenario id, and no module-level business global remains
**Plans**: TBD

### Phase 4: Rule Interpreter
**Goal**: Qualification is driven by `qualification.yaml` and demonstrably gives the same answers as the old code.
**Depends on**: Phase 3
**Requirements**: QUAL-01, QUAL-02, QUAL-03
**Success Criteria** (what must be TRUE):
  1. Editing a question, disqualify text or a rule in `qualification.yaml` changes agent behaviour with no code change
  2. Service synonyms and the non-business word list come from the pack
  3. A differential test over a large lead grid reports zero differences between old `qualification()` and the interpreter
  4. After the old path is deleted, roofing eval still matches the baseline
**Plans**: 5 plans

Plans:
- [ ] 04-01-PLAN.md — rules schema, loader validation, roofing YAML migration, compat properties
- [ ] 04-02-PLAN.md — qualify.py interpreter, dual-run differential test, edit-without-code-change tests
- [ ] 04-03-PLAN.md — switch agent.py and evals/runner.py to qualify.*, subset eval gate
- [ ] 04-04-PLAN.md — relax ServiceType (own plan, droppable alone), subset eval gate
- [ ] 04-05-PLAN.md — freeze diff digests, delete old path, full eval gate

### Phase 5: Per-Pack Eval Runner and Dental Pack
**Goal**: A second business runs on the same code, scored separately, with no leakage between businesses.
**Depends on**: Phase 4
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04
**Success Criteria** (what must be TRUE):
  1. `--pack <slug>` writes a per-pack report and never overwrites another pack's baseline
  2. Roofing scores 94/96 with the same two failures
  3. Dental pack (`bright-smile-dental`, synthetic data) has about 40 scenarios, no category under 90%, and emergency escalation recall 100%
  4. Interleaved two-tenant conversations and cross-tenant retrieval scenarios show zero leakage
**Plans**: TBD

### Phase 6: Per-Tenant Keys and RLS Enforcement
**Goal**: Tenants are isolated by credential and by the database, so multi-tenant exposure is safe.
**Depends on**: Phase 5
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, SEC-05
**Success Criteria** (what must be TRUE):
  1. Operator can issue a tenant key (shown once), rotate it, and revoke it; revoked keys get 401
  2. A request with no key gets 401, and a tenant id in the request body is ignored
  3. On an RLS-enabled DB with a non-owner app role, a query with no tenant context returns 0 rows
  4. The leak test across chat, FAQ, slots and metrics passes
  5. A tenant key cannot read cross-tenant admin data; only the super-admin scope can
**Plans**: TBD

### Phase 7: Engine Modules and Connectors
**Goal**: The platform does quotes, capacity, brief, review replies and intake deterministically, per business.
**Depends on**: Phase 6
**Requirements**: MOD-01, MOD-02, MOD-03, MOD-04, MOD-05, MOD-06, MOD-07, EVAL-05
**Success Criteria** (what must be TRUE):
  1. A quote request yields line items and a Decimal total from `services.yaml`; a missing price asks or escalates, and the draft lands in the approval queue
  2. Capacity check flags over/under-staffed shifts once, re-flags when inputs change, and is correct across a DST change
  3. The daily brief shows a one-page summary in tenant-local time, flags disagreeing numbers, and shows "source unavailable" for a failed connector; mock data is labelled as mock
  4. Review replies are drafts only; text with refund, fault, compensation, unknown-fact or PII language is blocked, regenerated once, then marked `needs_human`
  5. Posting the same waiver, check-in or result event twice stores one record per person
  6. Each module has its own deterministic eval set that passes
**Plans**: TBD

### Phase 8: Tenant-Aware n8n
**Goal**: All workflows run per tenant, and the platform still works with n8n off.
**Depends on**: Phase 7
**Requirements**: WF-01, WF-02, WF-03, WF-04, WF-05
**Success Criteria** (what must be TRUE):
  1. The 6 existing workflows send the tenant key header and take the owner address from the API
  2. quote-request, review-reply, capacity-check, daily-brief and intake-event workflows run end to end
  3. A scheduled workflow loops over `GET /admin/tenants` and acts only on tenants the API says are due in their local time
  4. With n8n stopped, the same flows complete through the API
  5. CI fails when an API-calling n8n HTTP node lacks the tenant key header
**Plans**: TBD

### Phase 9: Docs, PII/Retention and make new-business
**Goal**: A new business can be onboarded and operated with documented, privacy-safe defaults.
**Depends on**: Phase 8
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04, OPS-05, OPS-06, OPS-07
**Success Criteria** (what must be TRUE):
  1. `make new-business` validates a pack, loads it, and runs the smoke evals including cross-tenant and escalation checks
  2. Logs show masked emails and phones; `mask()` unit tests pass
  3. Setting retention purges stored data across stores, and `delete_subject` removes one person's data
  4. SOPs and a runbook are generated per pack, and CI fails on drift
  5. CI fails if `roof|Summit|Denver` appears in shared code; the data map documents stores, processors and the health-data and cross-border caveats
  6. README shows the per-business scorecard and workflow catalog
**Plans**: TBD

### Phase 10: Held-Out Eval and Optional Extras
**Goal**: An honest, published held-out score, then the optional platform extras.
**Depends on**: Phase 9
**Requirements**: EVAL-06, EXT-01, EXT-02, EXT-03
**Success Criteria** (what must be TRUE):
  1. 20 held-out scenarios, written before tuning, run once and the score is published even if low
  2. Anthropic can be selected as a provider with local still default, and scorecard runs use `providers=[anthropic]` with no fallback
  3. Connectors are callable as MCP servers wrapping the same adapter classes
  4. The venue pack (staff, group bookings) passes its own evals using quotes, capacity and intake
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Baseline Freeze and Environment Isolation | 3/3 | Complete    | 2026-11-03 |
| 2. Tenants, Migrations and DB Plumbing | 5/5 | Complete    | 2026-11-03 |
| 3. Pack Loader and Roofing Extraction | 5/5 | Complete    | 2026-11-03 |
| 4. Rule Interpreter | 0/TBD | Not started | - |
| 5. Per-Pack Eval Runner and Dental Pack | 0/TBD | Not started | - |
| 6. Per-Tenant Keys and RLS Enforcement | 0/TBD | Not started | - |
| 7. Engine Modules and Connectors | 0/TBD | Not started | - |
| 8. Tenant-Aware n8n | 0/TBD | Not started | - |
| 9. Docs, PII/Retention and make new-business | 0/TBD | Not started | - |
| 10. Held-Out Eval and Optional Extras | 0/TBD | Not started | - |
