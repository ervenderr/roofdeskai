# Phase 3: Pack Loader and Roofing Extraction - Context

**Gathered:** 2026-11-03
**Status:** Ready for planning
**Mode:** --auto (recommended defaults chosen, logged below)

<domain>
## Phase Boundary

Summit Roofing becomes pack #1: a validated folder `businesses/summit-roofing/` that holds every business value now hardcoded in `policy.py`, `faq.py`, `agent.py`, `tools.py`, `admin.py` and `prompts/`. The agent reads those values from the pack resolved per tenant. Zero behaviour change: the golden test, byte-identical prompt render and per-scenario eval gate (94/96, same two failures) prove it. Qualification logic stays as today's Python code reading pack values; the data-driven rule interpreter is Phase 4. Triage profiles in `clients/*.yaml`, outreach, intake, and the marketing site are untouched.

</domain>

<decisions>
## Implementation Decisions

### Pack format and loader
- **D-01:** [auto] A pack is `businesses/<slug>/` with YAML files: `pack.yaml` (identity, brand, locale, timezone, owner contact), `calendar.yaml`, `qualification.yaml`, `escalation.yaml`, `messages.yaml`, `faq.yaml`, plus `prompts/` overrides only if needed. One Pydantic v2 model per file, `ConfigDict(extra="forbid", frozen=True)`; the loader assembles an immutable `Pack`.
- **D-02:** [auto] Loader errors name the file and field path (e.g. `businesses/x/calendar.yaml: slot_hours.0: ...`) and raise a single `PackError`; `yaml.safe_load` only. A CLI entry `python -m app.pack <slug>` validates and prints a summary (used later by `make new-business`).
- **D-03:** [auto] Resolution: `tenants.pack_slug` selects the pack; `get_pack(tenant_id)` returns a cached immutable Pack. Cache key is `(tenant_id, pack_hash)` where hash covers all pack file bytes, so an edited pack reloads. No module-level business globals remain after this phase (PACK-07).
- **D-04:** [auto] The pack is passed explicitly (parameter), not via contextvar, following the Phase 2 pattern. Default tenant keeps working through the existing default-tenant parameter.
- **D-05:** [auto] `qualification.yaml` in this phase holds the VALUES only (service area cities, qualifying services, max timeline months, service synonyms, non-business word list, owner yes/no phrases, ask/disqualify text). `policy.qualification()` keeps its current code but reads them from the pack. Rule-type schema comes in Phase 4.

### Extraction order (3a data, 3b rewire)
- **D-06:** [auto] 3a first: write the pack YAML with the exact current values and a golden test asserting every pack value equals the old constant (imported from the still-present module constants). 3b then rewires call sites; after rewiring, the golden test compares against a frozen copy of the old values (a literal fixture in the test) so the old constants can be deleted.
- **D-07:** [auto] Regex constants move verbatim as strings in YAML (no rewriting, no DSL). Escalation: generic patterns (human_request, legal, angry) stay in code as defaults; roofing safety pattern lives in the pack (`escalation.yaml: safety`) and `always_human` categories stay per pack.

### Prompts
- **D-08:** [auto] `prompts/agent.v2.md` and `faq-answer.v1.md` become templates with placeholders (`{{business}}`, `{{about}}`, `{{services}}`, etc.) rendered by plain string replace (no Jinja). Test: rendered roofing prompt is byte-identical to the current file contents (captured at tag `v1-roofing`). Prompt version names do not change, so eval metadata is stable.
- **D-09:** [auto] The extraction JSON schema in the prompt stays core (agent.py coupling); only business wording and the service enum text are pack-driven. Relaxing the `ServiceType` enum is Phase 4.

### Messages
- **D-10:** [auto] Reply strings (CLOSED_REPLY, DISQUALIFY_REPLY, NURTURE_REPLY, NO_SLOTS_REPLY, SAFE_FALLBACK, ask questions, owner alert and customer booking emails, admin confirmation email) move to `messages.yaml` as named templates using `str.format`-style named fields; missing fields fail at load, not at chat time. The demo disclaimer text stays core code (D-per inventory) but the business name in it comes from the pack.

### Calendar
- **D-11:** [auto] `calendar.yaml`: `timezone` (America/Denver), `slot_hours` [9,11,14,16], `slot_minutes` 60, `days_ahead` 14, `weekdays_only`, `buffer_minutes` 0 (new, default no effect). `ensure_slots` generates from these. Slots are generated in the tenant timezone; the existing UTC-based behaviour must be preserved for the roofing pack, verified by a test that compares generated slot instants to the old SQL output. `tzdata` added to requirements.

### FAQ
- **D-12:** [auto] `faq.yaml` holds the Summit FAQ entries (source, text). `seed_faq(tenant_id)` loads them from the tenant's pack; `db/faq_seed.sql` remains for empty-DB bootstrap only and a test asserts it matches the pack content.

### Regression gate
- **D-13:** [auto] Each plan ends with in-container pytest; the final plan runs the full `make eval-gate` with `LLM_TIMEOUT_S=300` (see Phase 2 notes: local-only guard now enforced) and requires 94/96 with only voice-over-explainer and voice-indecisive failing. Mid-phase plans may use `--ids` subsets.

### Claude's Discretion
YAML key names beyond the above, exact placeholder syntax, test layout, whether `app/pack.py` splits into a package.

</decisions>

<canonical_refs>
## Canonical References

- `RoofDesk Global Platform Spec.md` (/Users/ervenderr/Downloads/) — business pack section and migration step 3
- `.planning/ROADMAP.md` — Phase 3 goal and success criteria; `.planning/REQUIREMENTS.md` — PACK-01..07
- `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` (pitfall 5 globals/regex drift), `.planning/research/STACK.md` (Pydantic, tzdata)
- `.planning/phases/01-baseline-freeze-and-environment-isolation/01-ROOFING-INVENTORY.md` — every roofing assumption and its destination
- `.planning/phases/02-tenants-migrations-and-db-plumbing/02-CONTEXT.md` — tenant passing pattern, db.tx
- `api/app/policy.py`, `agent.py`, `tools.py`, `faq.py`, `admin.py`, `llm.py` (load_prompt), `config.py`
- `prompts/agent.v2.md`, `prompts/faq-answer.v1.md`, `clients/summit-roofing.yaml`, `db/faq_seed.sql`
- `evals/baselines/v1-roofing.json`, `Makefile` (`g-test`, `eval-gate`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `clients/*.yaml` + `triage.load_profile`: existing YAML profile pattern with Pydantic validation to mirror.
- `llm.load_prompt(name)`: returns (version, template); extend rather than replace.
- Phase 2 `get tenant -> tenants.pack_slug` column and `db.tx(tenant_id)`.

### Established Patterns
- Business constants as module-level names in `policy.py` (SERVICE_AREA, QUALIFYING_SERVICES, MAX_TIMELINE_MONTHS, SAFE_FALLBACK, `_ESCALATION_PATTERNS`, `_SERVICE`, `_NON_ROOF`, `_OWN_YES`, `_GENERIC`, `ASK`); reply strings in `agent.py`; `SLOT_HOURS`, `SLOT_DAYS_AHEAD` in `tools.py`; FAQ list in `faq.py`.
- Many policy functions are pure and unit-tested (`test_policy.py`); keep their signatures stable or thread a `pack` parameter with the roofing pack as test default.

### Integration Points
- `handle_turn` resolves the pack once per turn and passes it to policy/agent helpers.
- `ensure_slots(tenant_id)` and `seed_faq(tenant_id)` read from the pack.

</code_context>

<specifics>
## Specific Ideas

No specific requirements, open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

- Rule-type schema and interpreter for qualification (Phase 4)
- Relaxing the ServiceType enum (Phase 4)
- Dental pack and `--pack` eval runner (Phase 5)
- Moving triage `clients/*.yaml` profiles into packs — later, not required
- n8n sender/recipient addresses from tenant config (Phase 8)

</deferred>

---

*Phase: 03-pack-loader-and-roofing-extraction*
*Context gathered: 2026-11-03*
