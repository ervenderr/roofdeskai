# Phase 4: Rule Interpreter - Context

**Gathered:** 2026-11-03
**Status:** Ready for planning
**Mode:** --auto (recommended defaults chosen, logged below)

<domain>
## Phase Boundary

Qualification is driven by data in `businesses/<slug>/qualification.yaml`: an ordered list of rules using four rule types (`in_list`, `yes_no`, `max_number`, `in_area`), pack-defined questions and disqualify text. A new pure module (`api/app/qualify.py`) interprets them. The old hardcoded `policy.qualification()` / `missing_fields()` / `address_status()` logic is kept until a differential test over a large lead grid reports zero differences, then deleted. Service-word synonyms and the non-business word list already live in the pack (Phase 3); this phase makes sure they are consumed through the interpreter path and relaxes the fixed service enum so a second business can have its own service types. No dental pack yet (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### Rule schema
- **D-01:** [auto] `qualification.yaml` gains `rules:` as a list. Each rule: `id`, `field` (a LeadFields name), `rule` (discriminator: `in_list | yes_no | max_number | in_area`), `question` (ask text key or inline), type-specific params (`in_list.values`, `max_number.max`, `in_area.cities`; `yes_no` needs none), and `required: true` default. Pydantic discriminated union on `rule`, `extra="forbid"`, unknown rule type fails at load naming file and field.
- **D-02:** [auto] Result semantics identical to today: a rule yields True / False / None (unknown); `disqualified` as soon as any known rule is False; `qualified` only when all rules True; otherwise `incomplete`. Rule order is file order and also fixes the order of questions (`missing_fields`).
- **D-03:** [auto] `in_area` ports `address_status` UNCHANGED (street number required, comma-part city match, 'in'/'out'/'incomplete'); only the city list becomes a parameter. No new address heuristics.
- **D-04:** [auto] Fixed `LeadFields` stay (name, phone, email, address, service_type, property_type, is_owner, timeline_months, budget_range): rules reference existing fields; no custom fields in this phase. Contact capture (`name`, phone or email) stays core, not a pack rule.
- **D-05:** [auto] The disqualify text and ask questions stay in `messages.yaml` (Phase 3) and are referenced by rule `id`; editing them changes behaviour with no code change (success criterion 1). Loader validates every rule id has an ask message.

### Dispatch and module layout
- **D-06:** [auto] `qualify.py`: `dict[type, Callable]` dispatch of four pure functions, `qualify(pack, lead) -> "qualified"|"disqualified"|"incomplete"`, `missing_fields(pack, lead)`, `next_question(pack, lead)`. `policy.py` keeps non-qualification logic (grounding, escalation, claims, slot picking) and delegates to `qualify.py` after the switch.
- **D-07:** [auto] Dual-run period: old and new functions coexist; a differential test compares them. The old path is deleted only after the diff test shows zero differences AND the roofing eval gate (full) matches the baseline.

### Differential test
- **D-08:** [auto] A deterministic grid over lead dicts: service_type (all enum values + None), is_owner (True/False/None), timeline_months (None, 0, 1, 5, 6, 7, 24), addresses (a curated list of ~40 strings covering in-area cities, case variants, ZIP/state suffixes, apt lines, out-of-area, no number, empty, None, odd punctuation) — thousands of combinations — comparing `qualification`, `missing_fields`, `next_question`. Plus a hypothesis-free randomized fuzz of address strings with a fixed seed. Zero differences required.

### Service enum
- **D-09:** [auto] Relax `ServiceType` so the field accepts pack-declared service types: `LeadFields.service_type` becomes a validated string; the pack's `qualification.yaml` declares `service_types` (roofing: repair, replacement, inspection, other). Values outside the pack list are normalized to `other`-equivalent handling exactly as an enum-invalid value behaved before: the plan must prove (test + eval subset) that model output that previously failed enum validation still ends in the same state. If any eval or differential difference appears that cannot be removed, keep the enum for roofing and defer relaxation to Phase 5.
- **D-10:** [auto] Prompt `{{service_enum}}` text already comes from the pack; keep it.

### Synonyms and non-business words
- **D-11:** [auto] `service_synonyms` and `non_business_pattern` stay in the pack and are read by the grounding code via the pack (already true after Phase 3); add tests that editing them changes grounding behaviour with no code change.

### Regression gate
- **D-12:** [auto] Each plan ends with in-container pytest; mid-phase plans may run the subset gate (explicit compose exec with `-e LLM_TIMEOUT_S=300`, qualification ids qual-1..qual-12, disqualified ids); the final plan runs the full gate (94/96, same two failures, local-only guard) after the old path is deleted.

### Claude's Discretion
Exact YAML key names beyond the above, module/file naming, grid size, whether `missing_fields` order is expressed by rule order or an explicit `ask_order`.

</decisions>

<canonical_refs>
## Canonical References

- `RoofDesk Global Platform Spec.md` (/Users/ervenderr/Downloads/) — data-driven qualification, migration step 4
- `.planning/ROADMAP.md` Phase 4; `.planning/REQUIREMENTS.md` QUAL-01..03
- `.planning/research/STACK.md` (dispatch dict, Pydantic union), `PITFALLS.md` (pitfall 5), `ARCHITECTURE.md`
- `.planning/phases/03-pack-loader-and-roofing-extraction/03-CONTEXT.md`, `03-VERIFICATION.md`
- `api/app/policy.py`, `api/app/pack.py`, `api/app/schemas.py`, `api/app/agent.py`, `api/app/tools.py`
- `businesses/summit-roofing/qualification.yaml`, `messages.yaml`
- `api/app/tests_data/frozen_old.py` (frozen old values), `evals/scenarios/qualified.yaml`, `disqualified.yaml`, `evals/baselines/v1-roofing.json`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `policy.qualification(pack, lead)`, `address_status(pack, address)`, `missing_fields(pack, lead)`, `next_question(pack, lead)` — the old path and the differential reference.
- Pack models in `pack.py` (frozen Pydantic, `PackError` with file+field messages) — extend `QualificationConfig`.
- Frozen old-value fixtures for golden checks.

### Established Patterns
- Policy functions take `pack` first; tests use a `roofing_pack` fixture.
- Loader validation with `extra="forbid"`.

### Integration Points
- `agent._decide` calls `policy.qualification`, `next_question`, `missing_fields`.
- Prompt rendering reads `service_enum` from the pack.

</code_context>

<specifics>
## Specific Ideas

No specific requirements, open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

- Custom lead fields beyond LeadFields (dental needs insurance/treatment fields?) — decide in Phase 5 if required
- Optional pack flag for the demo disclaimer (verifier follow-up from Phase 3) — Phase 5 or 9
- Flipping roofing calendar timezone to America/Denver — a deliberate behaviour change, later

</deferred>

---

*Phase: 04-rule-interpreter*
*Context gathered: 2026-11-03*
