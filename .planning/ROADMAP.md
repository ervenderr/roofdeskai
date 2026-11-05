# Roadmap: RoofDesk Global

## Overview

Turn the single-business Summit Roofing agent into a multi-business platform where a business is a validated config pack. The order protects the regression gate: freeze the baseline, add tenancy plumbing, extract roofing into pack #1, swap qualification to a data-driven interpreter, prove it with a second (dental) pack, lock down access with per-tenant keys and RLS, then add engine modules, tenant-aware n8n, docs/privacy/onboarding, and finally the held-out eval and optional extras. Roofing stays at 94/96 (same two failures) through Phase 5.

## Milestones

- ✅ **v1.0 RoofDesk Global** — Phases 1-10 (shipped 2026-11-04, local branch, not deployed)
- 🚧 **v1.1 Tenant-aware dashboard** — Phases 11-13 (planning)

## Phases

<details>
<summary>✅ v1.0 RoofDesk Global (Phases 1-10) — SHIPPED 2026-11-04</summary>

- [x] **Phase 1: Baseline Freeze and Environment Isolation** - Frozen per-scenario baseline, flake tolerance, isolated branch environment, and the regression gate (completed 2026-11-03)
- [x] **Phase 2: Tenants, Migrations and DB Plumbing** - Numbered migrations, tenant_id everywhere, `db.tx()`, tenant-stamped logs and events (completed 2026-11-03)
- [x] **Phase 3: Pack Loader and Roofing Extraction** - Validated pack format; roofing constants, prompts and messages moved into pack #1 with zero behaviour change (completed 2026-11-03)
- [x] **Phase 4: Rule Interpreter** - Data-driven qualification proven identical to the old code, then old path deleted (completed 2026-11-03)
- [x] **Phase 5: Per-Pack Eval Runner and Dental Pack** - Per-pack reports, dental pack at 90%+ per category, no cross-tenant leakage (completed 2026-11-03)
- [x] **Phase 6: Per-Tenant Keys and RLS Enforcement** - Hashed tenant keys, credential-derived tenant, enforced row-level security (completed 2026-11-03)
- [x] **Phase 7: Engine Modules and Connectors** - Quote builder, capacity checker, connectors, daily brief, review responder, intake_event, each with deterministic evals (completed 2026-11-03)
- [x] **Phase 8: Tenant-Aware n8n** - 10 tenant-aware workflow files (3 migrated + 2 untenanted + 5 new), API-only operation, CI header check (completed 2026-11-03)
- [x] **Phase 9: Docs, PII/Retention and make new-business** - Masking, retention, data map, generated SOPs, onboarding command, grep gate, README (completed 2026-11-04)
- [x] **Phase 10: Held-Out Eval and Optional Extras** - 20 held-out scenarios run once, then Anthropic provider, MCP connectors, venue pack (completed 2026-11-04)

</details>

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
- [x] 04-01-PLAN.md — rules schema, loader validation, roofing YAML migration, compat properties
- [x] 04-02-PLAN.md — qualify.py interpreter, dual-run differential test, edit-without-code-change tests
- [x] 04-03-PLAN.md — switch agent.py and evals/runner.py to qualify.*, subset eval gate
- [x] 04-04-PLAN.md — relax ServiceType (own plan, droppable alone), subset eval gate
- [x] 04-05-PLAN.md — freeze diff digests, delete old path, full eval gate

### Phase 5: Per-Pack Eval Runner and Dental Pack
**Goal**: A second business runs on the same code, scored separately, with no leakage between businesses.
**Depends on**: Phase 4
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04
**Success Criteria** (what must be TRUE):
  1. `--pack <slug>` writes a per-pack report and never overwrites another pack's baseline
  2. Roofing scores 94/96 with the same two failures
  3. Dental pack (`bright-smile-dental`, synthetic data) has about 40 scenarios, no category under 90%, and emergency escalation recall 100%
  4. Interleaved two-tenant conversations and cross-tenant retrieval scenarios show zero leakage
**Plans**: 6 plans
Plans:
- [x] 05-01-PLAN.md — per-pack runner, ensure_tenant, scenario move, roofing gate subset
- [x] 05-02-PLAN.md — dental pack YAML, loader and deterministic emergency-recall tests, CHF claim guard
- [x] 05-03-PLAN.md — 43 dental scenarios with validation tests
- [x] 05-04-PLAN.md — two-tenant isolation tests
- [x] 05-05-PLAN.md — dental full run, bounded tuning, baseline if gates met
- [x] 05-06-PLAN.md — roofing full gate 94/96, dental gate/flake, phase summary

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
  1. The 3 tenant-keyed existing workflows send the tenant key header (outreach-flow and error-handler are untenanted, allowlisted) and take the owner address from the API
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
**Plans**: 7 plans
Plans:
- [x] 10-01-PLAN.md — held-out scenarios (20) and --heldout tooling, committed before any run
- [x] 10-02-PLAN.md — run held-out once per pack, publish score
- [x] 10-03-PLAN.md — puzzle-peak venue pack, scenarios, module cases, address fallback
- [x] 10-04-PLAN.md — venue run, bounded tuning, baseline, pin, generated docs
- [x] 10-05-PLAN.md — optional Anthropic provider, pin, --providers flag (fakes only)
- [x] 10-06-PLAN.md — mcp 2.3 dependency and connector MCP server
- [x] 10-07-PLAN.md — final gates

## v1.1 Tenant-aware dashboard

- [ ] **Phase 11: Sign-in and Tenant Shell** - Key login, encrypted session, tenant header, existing pages on the tenant key
- [ ] **Phase 12: Quote and Review Drafts** - Draft lists with approve/reject on the existing `/drafts` API
- [ ] **Phase 13: Capacity, Daily Brief and Isolation** - Flags screen, brief read API and screen, two-tenant test, snapshot demo intact

### Phase 11: Sign-in and Tenant Shell
**Goal**: An owner signs in with their tenant key and sees their own business, with the old roofing pages still working.
**Depends on**: Phase 10
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, KEEP-01
**Success Criteria** (what must be TRUE):
  1. Pasting a valid key on the login page lands on the overview with the business name in the header; a wrong or revoked key shows an error and no session
  2. Page source, client JS bundles and URLs never contain the key; the cookie is httpOnly and encrypted
  3. Visiting any page signed out redirects to login; Sign out clears the session
  4. Overview and conversations render for the roofing tenant using that tenant's key; calls, outreach and prospects (operator tools) show only in an admin-key operator session and are hidden from tenant sessions
  5. Nav hides screens for modules the signed-in pack does not enable
**Plans**: TBD

### Phase 12: Quote and Review Drafts
**Goal**: Owners can review and decide quote and review-reply drafts in the browser.
**Depends on**: Phase 11
**Requirements**: DRAFT-01, DRAFT-02, DRAFT-03, DRAFT-04, DRAFT-05
**Success Criteria** (what must be TRUE):
  1. Quote drafts list with status, items and total; a `needs_human` draft shows reason and missing fields
  2. Approving or rejecting a pending draft changes its status on the next load, and nothing is sent or posted
  3. Review reply drafts list, with blocked ones showing violation codes
  4. A draft from another tenant never appears
**Plans**: TBD

### Phase 13: Capacity, Daily Brief and Isolation
**Goal**: Owners see capacity flags and the daily brief, and isolation between tenants is proven end to end.
**Depends on**: Phase 12
**Requirements**: CAP-01, BRF-01, BRF-02, ISO-01, KEEP-02
**Success Criteria** (what must be TRUE):
  1. Capacity screen shows open flags by default and all flags on toggle
  2. A tenant-scoped `GET` returns the latest brief and recent runs; the screen shows mock data labelled and unavailable sources
  3. A test signed in as two tenants shows each only its own drafts, flags and brief
  4. The static snapshot demo still builds and renders without sign-in
  5. Roofing eval gate and `make g-test` still pass
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Baseline Freeze and Environment Isolation | 3/3 | Complete    | 2026-11-03 |
| 2. Tenants, Migrations and DB Plumbing | 5/5 | Complete    | 2026-11-03 |
| 3. Pack Loader and Roofing Extraction | 5/5 | Complete    | 2026-11-03 |
| 4. Rule Interpreter | 5/5 | Complete    | 2026-11-03 |
| 5. Per-Pack Eval Runner and Dental Pack | 6/6 | Complete    | 2026-11-03 |
| 6. Per-Tenant Keys and RLS Enforcement | 6/6 | Complete    | 2026-11-03 |
| 7. Engine Modules and Connectors | 8/8 | Complete    | 2026-11-03 |
| 8. Tenant-Aware n8n | 6/6 | Complete    | 2026-11-03 |
| 9. Docs, PII/Retention and make new-business | 6/6 | Complete    | 2026-11-04 |
| 10. Held-Out Eval and Optional Extras | 7/7 | Complete    | 2026-11-04 |
