# Phase 3: Pack Loader and Roofing Extraction - Research

**Researched:** 2026-11-03
**Domain:** Config-pack extraction in an existing FastAPI/SQLAlchemy/Postgres agent (Pydantic v2, YAML, zoneinfo, prompt templating)
**Confidence:** HIGH (everything below was read from the repo, the running branch stack, or PyPI; nothing here rests on library docs that changed)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** A pack is `businesses/<slug>/` with YAML files: `pack.yaml` (identity, brand, locale, timezone, owner contact), `calendar.yaml`, `qualification.yaml`, `escalation.yaml`, `messages.yaml`, `faq.yaml`, plus `prompts/` overrides only if needed. One Pydantic v2 model per file, `ConfigDict(extra="forbid", frozen=True)`; the loader assembles an immutable `Pack`.
- **D-02:** Loader errors name the file and field path (e.g. `businesses/x/calendar.yaml: slot_hours.0: ...`) and raise a single `PackError`; `yaml.safe_load` only. A CLI entry `python -m app.pack <slug>` validates and prints a summary (used later by `make new-business`).
- **D-03:** Resolution: `tenants.pack_slug` selects the pack; `get_pack(tenant_id)` returns a cached immutable Pack. Cache key is `(tenant_id, pack_hash)` where hash covers all pack file bytes, so an edited pack reloads. No module-level business globals remain after this phase (PACK-07).
- **D-04:** The pack is passed explicitly (parameter), not via contextvar, following the Phase 2 pattern. Default tenant keeps working through the existing default-tenant parameter.
- **D-05:** `qualification.yaml` in this phase holds the VALUES only (service area cities, qualifying services, max timeline months, service synonyms, non-business word list, owner yes/no phrases, ask/disqualify text). `policy.qualification()` keeps its current code but reads them from the pack. Rule-type schema comes in Phase 4.
- **D-06:** 3a first: write the pack YAML with the exact current values and a golden test asserting every pack value equals the old constant (imported from the still-present module constants). 3b then rewires call sites; after rewiring, the golden test compares against a frozen copy of the old values (a literal fixture in the test) so the old constants can be deleted.
- **D-07:** Regex constants move verbatim as strings in YAML (no rewriting, no DSL). Escalation: generic patterns (human_request, legal, angry) stay in code as defaults; roofing safety pattern lives in the pack (`escalation.yaml: safety`) and `always_human` categories stay per pack.
- **D-08:** `prompts/agent.v2.md` and `faq-answer.v1.md` become templates with placeholders (`{{business}}`, `{{about}}`, `{{services}}`, etc.) rendered by plain string replace (no Jinja). Test: rendered roofing prompt is byte-identical to the current file contents (captured at tag `v1-roofing`). Prompt version names do not change, so eval metadata is stable.
- **D-09:** The extraction JSON schema in the prompt stays core (agent.py coupling); only business wording and the service enum text are pack-driven. Relaxing the `ServiceType` enum is Phase 4.
- **D-10:** Reply strings (CLOSED_REPLY, DISQUALIFY_REPLY, NURTURE_REPLY, NO_SLOTS_REPLY, SAFE_FALLBACK, ask questions, owner alert and customer booking emails, admin confirmation email) move to `messages.yaml` as named templates using `str.format`-style named fields; missing fields fail at load, not at chat time. The demo disclaimer text stays core code (D-per inventory) but the business name in it comes from the pack.
- **D-11:** `calendar.yaml`: `timezone` (America/Denver), `slot_hours` [9,11,14,16], `slot_minutes` 60, `days_ahead` 14, `weekdays_only`, `buffer_minutes` 0 (new, default no effect). `ensure_slots` generates from these. Slots are generated in the tenant timezone; the existing UTC-based behaviour must be preserved for the roofing pack, verified by a test that compares generated slot instants to the old SQL output. `tzdata` added to requirements.
- **D-12:** `faq.yaml` holds the Summit FAQ entries (source, text). `seed_faq(tenant_id)` loads them from the tenant's pack; `db/faq_seed.sql` remains for empty-DB bootstrap only and a test asserts it matches the pack content.
- **D-13:** Each plan ends with in-container pytest; the final plan runs the full `make eval-gate` with `LLM_TIMEOUT_S=300` and requires 94/96 with only voice-over-explainer and voice-indecisive failing. Mid-phase plans may use `--ids` subsets.

### Claude's Discretion
YAML key names beyond the above, exact placeholder syntax, test layout, whether `app/pack.py` splits into a package.

### Deferred Ideas (OUT OF SCOPE)
- Rule-type schema and interpreter for qualification (Phase 4)
- Relaxing the ServiceType enum (Phase 4)
- Dental pack and `--pack` eval runner (Phase 5)
- Moving triage `clients/*.yaml` profiles into packs
- n8n sender/recipient addresses from tenant config (Phase 8)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PACK-01 | Folder of YAML under `businesses/<slug>/`, Pydantic `extra="forbid"`, clear load errors | Section 2 (models), `PackError` pattern, slug regex, regex-compile validators |
| PACK-02 | Roofing pack holds values from policy/faq/agent/tools/prompts; golden test | Section 1 (inventory), Section 2 (exact values), golden test design in Validation |
| PACK-03 | Prompts templated; roofing render byte-identical | Section 3 |
| PACK-04 | Reply strings, booking email, disclaimer from pack `messages:` | Section 1 table C, Section 2 messages.yaml; disclaimer conflict in Open Questions |
| PACK-05 | Calendar (hours, slot length, days ahead, buffer, tz) from pack | Section 4 |
| PACK-06 | Roofing safety patterns in pack; generic defaults in code | Section 1 table A, order-preservation pitfall |
| PACK-07 | Pack caches keyed by tenant + pack hash; no module-level business globals | Section 5, grep test |
</phase_requirements>

## Summary

Everything roofing-specific is concentrated in five source files plus two prompt files, one client YAML and one SQL seed. The code is already tenant-parameterised (Phase 2), so extraction is mostly: (a) add `app/pack.py` (loader, models, cache), (b) add `businesses/summit-roofing/*.yaml` with verbatim values, (c) thread an explicit `pack` argument into the ~9 policy functions and agent helpers that read a business constant, (d) replace the module constants. The tests that call `policy.*` today (`test_policy.py`, ~40 call sites) need the pack passed in; `test_tenancy.py` has a `tb` fixture tenant with `pack_slug` NULL that must now get a pack.

Four findings change how the plan should be written. (1) **The branch DB runs in `Etc/UTC` and the existing slot hours 9/11/14/16 are UTC wall-clock** (live rows: `2026-11-04 09:00+00`), not Denver time. So "generate in America/Denver" would shift every roofing slot by 6-7 hours and break the equivalence test; the roofing calendar must be interpreted in UTC to stay identical (Open Question 1). (2) **The prompts already use `<<asked>>`, `<<known>>`, `<<faq>>` runtime placeholders**, so pack placeholders must use a different token (`{{...}}`, verified absent from both files today). Only one sentence in each prompt (plus the service enum on line 19) needs templating. (3) **`businesses/` is not mounted in the api container and not copied by either Dockerfile**; the root (Railway) `Dockerfile` would crash the live demo on start if this branch were deployed without a `COPY businesses`. (4) **`triage.py` calls `policy.escalation_reason` and `policy.answer_supported` without a tenant**; once the safety regex and the "roof/roofing/summit" stopwords leave `policy.py` the `/triage` endpoint silently loses them unless it passes the default tenant's pack.

**Primary recommendation:** Build `app/pack.py` with frozen Pydantic models and `get_pack(tenant_id)` (DB lookup of `pack_slug` + sha256 of all pack file bytes, dict cache keyed `(tenant_id, hash)`); write the pack YAML verbatim and prove it against the old constants first (3a); then rewire with `pack` as a required first positional argument of the pack-dependent policy functions (no default, so no hidden roofing global), a `roofing_pack` pytest fixture, and a frozen literal fixture in the golden test (3b).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Pack parsing, validation, hashing, cache | API / Backend (`app/pack.py`) | Filesystem (`businesses/`) | Decisions stay in FastAPI; n8n untouched |
| Qualification, grounding, escalation (reads pack values) | API / Backend (`policy.py`) | — | "Model proposes, code decides" |
| Reply and email text | API / Backend (`agent.py`, `admin.py`) rendering pack templates | Pack YAML | Code renders, pack owns wording |
| Prompt rendering | API / Backend (`agent.py`) | `prompts/*.md` templates + pack vars | Replace `{{}}` first, then runtime `<<>>` |
| Slot generation | API / Backend (`tools.ensure_slots`) computing instants | Database (insert, uniqueness) | Python computes instants (tz + DST + buffer); SQL only inserts |
| FAQ seed | API / Backend (`faq.seed_faq`) | Database (`faq_chunks`) | Reads pack entries, embeds, inserts |
| Pack-to-tenant resolution | Database (`tenants.pack_slug`) | API cache | Column already exists |

## Standard Stack

### Core (all already in `api/requirements.txt`)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | `2.*` (installed in container) | Pack models, `extra="forbid"`, `frozen=True` | Already used in `schemas.py`; STACK.md recommendation [CITED: .planning/research/STACK.md] |
| pyyaml | `6.*` | `yaml.safe_load` of pack files | Already used by `triage.load_profile` [VERIFIED: api/app/triage.py:34-37] |
| zoneinfo (stdlib) | py3.12.14 | Slot instants in a named zone, tz validation | stdlib; container resolves `America/Denver` today [VERIFIED: docker exec on roofdesk-global-api-1] |
| hashlib, re, string.Formatter (stdlib) | — | Pack hash; regex compile check; template field check | No dependency needed |

### Supporting (new)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tzdata | 2026.6 (PyPI, uploaded 2026-10-28, source github.com/python/tzdata) | IANA db when the system one is absent | D-11 requires it. NOTE: the current container already has `/usr/share/zoneinfo` (system tzdata present, `pip show tzdata` = not found), so it works today; the pip package makes it independent of the base image. Pin `tzdata` (unpinned or `tzdata>=2025.1`). |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `{{x}}` str.replace | Jinja2 | Locked out by D-08; no loops needed |
| Hand-written `str.format` field checking | pydantic-validated template classes | `string.Formatter().parse` is 6 lines; keep it |

**Installation:** add one line `tzdata` to `api/requirements.txt`; rebuild image (`make g-up` rebuilds; `docker compose up -d --build`).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| tzdata | PyPI | long-lived (PSF) | not fetched | github.com/python/tzdata | NOT RUN (install of slopcheck was denied by the sandbox) | `[ASSUMED]` legitimacy: registry JSON confirms 2026.6 and the python/tzdata repo, but per protocol the planner should gate the install behind a `checkpoint:human-verify` (trivial for a PSF package named in STACK.md and in the Python docs for zoneinfo) |

**Packages removed:** none. **Packages flagged [SUS]:** none (slopcheck unavailable; treated as `[ASSUMED]`).

## Architecture Patterns

### System Architecture Diagram

```
chat/eval/sms request -> main.py -> agent.handle_turn(message, cid, tenant_id)
                                         |
                       packs.get_pack(tenant_id)  (once per turn)
                         |  SELECT pack_slug FROM tenants WHERE id=:t   (DB)
                         |  sha256(all bytes in businesses/<slug>/**)   (files)
                         |  cache[(tenant_id, hash)] hit -> Pack | miss -> load+validate -> PackError on bad pack
                         v
                      Pack (frozen)  -------------------------------+
                         |                                          |
   policy.*(pack, ...)  agent: pack.messages.* .format(...)   prompts: load_prompt -> replace {{k}} (pack) -> replace <<asked>>/<<known>>/<<faq>>
   (escalation, address,    tools.ensure_slots(tenant)                faq.seed_faq(tenant) -> pack.faq -> embed -> faq_chunks
    qualification, ground,    pack.calendar -> python instants -> INSERT ... unnest ... NOT EXISTS ON CONFLICT
    next_question, answer_supported)
```

### Recommended Project Structure
```
businesses/summit-roofing/{pack,calendar,qualification,escalation,messages,faq}.yaml
api/app/pack.py          # models, load_pack, get_pack, hash, render, CLI (python -m app.pack <slug>)
api/app/test_pack.py     # loader errors, golden, frozen fixture, render, slots, seed, no-globals grep
prompts/agent.v2.md, faq-answer.v1.md   # edited in place (names/versions unchanged)
```
`app/pack.py` as one file is fine (<400 lines: 6 small models + loader + cache + render); no package split needed.

### Pattern 1: Loader with a single PackError naming file and field path
```python
# Source: pydantic v2 ValidationError.errors() -> loc tuple (standard API); mirrors triage.load_profile
def _load(slug: str) -> Pack:
    if not re.fullmatch(r"[a-z0-9-]+", slug):          # slug becomes a path (same guard as triage.load_profile)
        raise PackError(f"invalid pack slug {slug!r}")
    root = settings.businesses_dir / slug
    parts = {}
    for name, model in FILES.items():                   # {"pack": PackMeta, "calendar": Calendar, ...}
        path = root / f"{name}.yaml"
        try:
            parts[name] = model.model_validate(yaml.safe_load(path.read_text()))
        except FileNotFoundError:
            raise PackError(f"{path}: file missing") from None
        except yaml.YAMLError as e:
            raise PackError(f"{path}: invalid YAML: {e}") from None
        except ValidationError as e:
            first = e.errors()[0]
            raise PackError(f"{path}: {'.'.join(map(str, first['loc']))}: {first['msg']}") from None
    return Pack(slug=slug, **parts)                     # cross-file validators here (e.g. qualifying services subset of services)
```
Empty YAML file yields `None` -> `model_validate(None)` raises ValidationError (caught, message "Input should be a valid dictionary"); fine.

### Pattern 2: Template field validation at load
```python
from string import Formatter
def _fields(t: str) -> set[str]:
    return {f for _, f, _, _ in Formatter().parse(t) if f}
# in a model_validator: assert _fields(value) == REQUIRED[name] (or subset of ALLOWED); else raise ValueError(f"{name}: needs {sorted(REQUIRED)}, has {sorted(got)}")
```
Literal braces in text must be written `{{`/`}}` for `str.format`; the validator rejects positional fields (`{}` / `{0}`) because `Formatter().parse` yields an empty/numeric field name.

### Anti-Patterns to Avoid
- **Default `pack=None` that silently loads roofing:** that is a hidden business global (PACK-07). Pack-dependent functions take `pack` as a required first positional argument; only `answer_supported`/`escalation_reason` take an optional `pack` (None = core-only) because `triage`/`intake` are untenanted.
- **Evaluating pack regex on every call with `re.compile` caches keyed outside `re`:** just pass the string to `re.search`; Python's `re` cache is keyed by pattern text, so there is no cross-tenant leak and no new cache to key.
- **Hash computed from file mtimes:** use bytes (D-03).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML typo detection | manual key checks | `ConfigDict(extra="forbid")` | Typos become load errors with a field path |
| tz math / DST | UTC offset arithmetic | `zoneinfo.ZoneInfo` + `datetime.combine(date, time(h), tzinfo=tz)` | Wall-clock correctness across DST (Denver, Zurich later) |
| Prompt templating | a mini template engine | `str.replace` over a fixed key list + a "no `{{` left" assert | D-08; 2 prompts, 3-4 keys |
| Format-string safety | eval/regex scraping of `{x}` | `string.Formatter().parse` | Exact field names, handles escapes |
| Pack hash | per-file mtimes | `hashlib.sha256` over sorted `(relpath, bytes)` | Stable, edit-sensitive |

## Section 1: Exact inventory (file:line at current HEAD `a0515cb`; prompts and FAQ identical to tag `v1-roofing` [VERIFIED: `git show v1-roofing:... | cmp`])

### A. `api/app/policy.py` (constant -> destination)
| Name | Line | Type | Value summary | Destination | Readers (non-test) |
|------|------|------|---------------|-------------|--------------------|
| `SERVICE_AREA` | 4 | tuple[str] | denver, aurora, lakewood, arvada, centennial, littleton | pack `qualification.service_area` | `address_status` (39) |
| `QUALIFYING_SERVICES` | 5 | set[str] | repair, replacement, inspection | pack `qualification.qualifying_services` | `qualification` (51) |
| `MAX_TIMELINE_MONTHS` | 6 | int | 6 | pack `qualification.max_timeline_months` | `qualification` (54) |
| `MAX_FAILED_TURNS` | 7 | int | 2 | **stays core** (engine rule, not roofing) | `agent._decide` (105) |
| `SAFE_FALLBACK` | 9-12 | str | "I don't have that information, ... free roof inspection." | pack `messages.safe_fallback` | `agent._answer` (136) |
| `_ESCALATION_PATTERNS` | 14-19 | dict[str,regex] | human_request, legal, safety, angry | human_request/legal/angry **stay core**; `safety` -> pack `escalation.safety` | `escalation_reason` (26); also `triage.triage` (69) |
| `_CLAIM_RE` | 20-23 | compiled regex | $, dollars/usd/php/pesos/percent, N%, N-year warranty | **core** (generic; "php/pesos" is the Manila operator, not roofing) | `unsupported_claim`; also `triage` (63) |
| `ASK` | 83-90 | dict[str,str] (6 keys) | service_type, is_owner, address, timeline_months, name, "phone or email" | pack `messages.ask` | `next_question` (95); NOT the same as `intake.ASK` (untenanted, leave) |
| "Is there anything else I can help you with?" | 95 | literal in `next_question` | -- | pack `messages.anything_else` | -- |
| `_ORDINALS` | 98-101 | dict | first..fifth | **core** | `pick_slot` |
| `_OWN_YES` | 116 | regex str | own/owner/.../`my (house\|home\|place\|roof\|property)`/yes/yeah/... | pack `qualification.owner_yes_pattern` (D-05; contains "roof") | `is_grounded` (139) |
| `_OWN_NO` | 117 | regex str | rent/renter/tenant/lease/landlord/not owner/don't own | pack `qualification.owner_no_pattern` (D-05 says "owner yes/no phrases") | `is_grounded` (139,141) |
| `_TIMING`, `_TIME_UNITS` | 118-120 | regex | numbers, months, asap... | **core** (English time words) | `is_grounded` (143-144) |
| `_SERVICE` | 121-125 | dict[str,regex] (3) | repair/replacement/inspection synonyms | pack `qualification.service_synonyms` | `is_grounded` (146) |
| `_NON_ROOF` | 126 | regex str | gutter\|window\|paint\|... \|lawn | pack `qualification.non_business_pattern` (rename; "non_roof" is roofing-named) | `is_grounded` (146) |
| `_QUESTION_RE`, `_NOT_READY_RE` | 164-168 | compiled | generic English | **core** | `looks_like_question` (also `intake.py:127`), `not_ready_grounded` |
| `_GENERIC` | 169-174 | set[str] ~95 words | filler words incl. **roof roofing summit** | split: roofing/brand words (`roof`, `roofing`, `summit`, plus `inspection`, `inspections`, `estimate`, `book`, `booking`, `service`? see note) -> pack `qualification.extra_stopwords`; rest core | `answer_supported` (191); also `triage` (63) |

Note on `_GENERIC`: only `roof`, `roofing`, `summit` are roofing/brand-named (matches the Phase 1 inventory "Stopword list with roof/roofing/summit"). Move exactly those three to `qualification.extra_stopwords` and leave the rest core; the golden test asserts `core_generic | pack.extra_stopwords == frozen old _GENERIC`, which holds for any split. [ASSUMED: planner may cut wider.]

Functions that read a pack-owned value, hence need `pack`:
`escalation_reason` (safety), `address_status` (SERVICE_AREA), `qualification` (via address_status + two constants), `missing_fields` (via address_status), `next_question` (ASK, anything_else), `is_grounded`/`ground` (owner patterns, service synonyms, non-business), `answer_supported` (stopwords). Pure core, no change: `has_contact`, `unsupported_claim`, `pick_slot`, `looks_like_question`, `not_ready_grounded`, `_same_word`, `_tokens`.

### B. `api/app/agent.py`
| Name | Line | Value | Destination |
|------|------|-------|-------------|
| `PROMPT = "agent.v2"` | 17 | prompt name | **core** (versioned name stays; `evals/runner.py:22,272` imports it) |
| `CLOSED_REPLY` | 19-23 | dict DONE/DISQUALIFY/ESCALATE | text -> pack `messages.closed`; the key set `{DONE, DISQUALIFY, ESCALATE}` is state-machine vocabulary, keep as core `CLOSED_STATES` (used by `main.py:19,98,99` for `state in CLOSED_REPLY` and by `_decide` 63-70, 64) |
| `DISQUALIFY_REPLY` | 24-28 | str (mentions "6 months", "inspections", "service area") | pack `messages.disqualify` |
| `NURTURE_REPLY` | 29 | str | pack `messages.nurture` |
| `NO_SLOTS_REPLY` | 30 | str | pack `messages.no_slots` |
| inline prefix | 111 | "Good news, you qualify for a free roof inspection! " | pack `messages.qualified_prefix` (trailing space preserved) |
| inline | 118 | `f"You're booked for {when}. We'll see you then!"` | pack `messages.booked` |
| inline | 119 | "Sorry, that time isn't available. " | pack `messages.slot_unavailable_prefix` |
| inline | 120 | "Which of those openings works for you? Just say first, second, and so on." | pack `messages.pick_prompt` |
| inline | 161 | `f"{prefix}Here are the next openings: {options}. Which one works for you?"` | pack `messages.offer_slots` (fields `prefix`, `options`); `"; "` joiner and `"{i}) {when}"` stay code |
| `_notify_booking` owner email | 215-217 | subject `New booking: {name} ({when})`; body 5 lines "booked a free roof inspection for {when}" | pack `messages.owner_alert_subject/body` (fields name, when, phone, email, address, need; code supplies `'-'` fallbacks) |
| customer email | 219-223 | subject `Your inspection is booked: {when}`; body intro "Hi {name},\n\nYour free roof inspection is booked for {when}.\n\n" | pack `messages.customer_subject`, `customer_intro` |
| demo disclaimer | 221-222 | "This was a demo of RoofDesk AI with a sample company (Summit Roofing). No one will visit, and nothing was scheduled.\n\nTo try RoofDesk AI for your own business, reply to this email.\n\n" | **core constant with `{business}`** (D-10); see Open Question 2 |
| signature | 223 | `settings.sender_name` + `settings.sender_address` | core/settings (RoofDesk brand; untouched) |
| `_fmt` | 231-232 | `strftime("%a %b %d, %I:%M %p")` on the ISO string from the DB | core format; add tz conversion to `pack.calendar.timezone` (identical for roofing, see Section 4) |
| `_KNOWN_KEYS` | 192-193 | lead field names | core (schema coupling) |
| `_faq_answer` | 144-145 | loads `faq-answer.v1` | add pack render step |
| `_ask_llm` | 166-172 | loads `agent.v2` | add pack render step |

### C. `api/app/tools.py`
| Name | Line | Value | Destination |
|------|------|-------|-------------|
| `SLOT_HOURS` | 24 | (9, 11, 14, 16) | pack `calendar.slot_hours` |
| `SLOT_DAYS_AHEAD` | 25 | 14 | pack `calendar.days_ahead` |
| `ensure_slots` | 32-43 | SQL; 3600 s length implied by `h + 1`; weekdays via `isodow < 6` | Section 4 |
| docstring | 33 | "(9/11/14/16) ... 14 days" | reword (the PACK-07 grep must not see roofing numbers/words) |

### D. `api/app/faq.py`
`FAQ` (lines 11-24, 12 `(source, text)` tuples) -> `faq.yaml`. `seed_faq` (28-45) iterates it. Comment on line 10 names "Summit Roofing" (delete). Readers of `faq.FAQ`: `test_tenancy.py:191` only. `vector_literal` stays.

### E. `api/app/admin.py`
Lines 189-191, `draft_followup`: subject `"Your free roof inspection with Summit Roofing"`; body `f"{greeting}\n\nThanks for your interest in a free roof inspection. Whenever you're ready, just reply to this email or message us and we'll find a time that works.\n\nSummit Roofing"` -> pack `messages.followup_subject`, `followup_body` (fields `greeting`; `{business}` allowed everywhere). This is what D-10 calls the "admin confirmation email" (it is the NURTURE follow-up draft, not a booking confirmation). The endpoint has no tenant parameter (`settings.default_tenant_id` at line ~183); resolve `get_pack(settings.default_tenant_id)` there (Phase 6 scopes admin per tenant). Existing admin tests that hit this endpoint: grep `followups`/`draft` in `test_admin.py` before editing (not enumerated here).

### F. Prompts, client profile, SQL
- `prompts/agent.v2.md:3` (business sentence), `:19` (service enum). `prompts/faq-answer.v1.md:3`.
- `clients/summit-roofing.yaml` (triage profile): untouched (CONTEXT). But its `about` ("... in the Denver area"), `facts`, `always_human: [complaint]` duplicate pack values; the pack `about` for prompts must be the **prompt** wording ("a roofing company that books free roof inspections"), which differs from the profile (so do not derive one from the other).
- `db/faq_seed.sql` rows 1-12: 12 INSERTs with explicit ids 1-12; texts equal `faq.FAQ` [VERIFIED: sources/text prefixes match; no `''` escapes present, so a simple regex parser works].
- `db/migrations/001_tenants.sql` seeds `tenants.pack_slug='summit-roofing'` for the default tenant.

### G. Call sites and tests that read these
| Caller | What | Change |
|--------|------|--------|
| `agent.py` `_decide` | policy.escalation_reason(66), ground(82), qualification(89), not_ready_grounded(95), pick_slot(100), looks_like_question(101), MAX_FAILED_TURNS(105), has_contact(108), next_question(124), plus reply constants | resolve `pack = get_pack(t)` once in `handle_turn` and pass down (`_decide(cid, message, t, pack)`, `_answer`, `_offer_slots`, `_ask_llm`, `_faq_answer`, `_notify_booking`) |
| `agent.py` `_answer` | `policy.SAFE_FALLBACK`, `unsupported_claim`, `answer_supported` | `pack.messages.safe_fallback`, `answer_supported(a, faq, pack)` |
| `main.py:19,98,99` | `CLOSED_REPLY` membership | import `CLOSED_STATES` |
| `main.py:23,40` | `seed_faq(tenant)` for every tenant | tenant with NULL `pack_slug` or bad pack raises `PackError`; the existing `except Exception: pass` swallows it silently. Add `log.exception`/skip-with-warning, do not crash start (tests create `test-*` tenants without a pack) |
| `evals/runner.py:21,96` | `policy.qualification(lead)` | `policy.qualification(get_pack(settings.default_tenant_id), lead)` (Phase 5 adds `--pack`) |
| `evals/runner.py:22,26,272` | `PROMPT`, `load_prompt(PROMPT)[0]` | unchanged (version header only) |
| `triage.py:63,69` | `answer_supported`, `escalation_reason` | pass `pack=get_pack(settings.default_tenant_id)` to keep roofing safety/stopwords (see Pitfall 4) |
| `intake.py:127` | `looks_like_question` | unchanged (core) |
| `test_policy.py` (all `policy.*` calls, lines 11-138) | | add pack argument; `GOOD` and params unchanged |
| `test_tenancy.py:157` `tb` fixture | INSERT tenants without `pack_slug` | add `pack_slug` `'summit-roofing'` (otherwise `handle_turn`/`ensure_slots`/`seed_faq` for `tb` raise PackError) |
| `test_tenancy.py:191` | `len(faq.FAQ)` | `len(pack.faq)` or the frozen count 12 |
| `test_tenancy.py:167-175,244,254,270` | `ensure_slots`, `get_available_slots` for `tb` | works if `tb` has a pack; `tb.timezone='UTC'` is the tenants column, unrelated to the pack calendar |
| `test_agent.py` | asserts on reply text ("Which of those...", booked replies) via `handle_turn` | no edit if text is byte-identical (that is the point); `lookup_faq` monkeypatches keep working |
| `test_migrations.py:57` | asserts the default tenant row | unchanged |
| `test_tenancy.py:337` `test_no_raw_engine_calls` | scans `tools.py faq.py agent.py main.py` | pack.py must not use `engine.begin()`; use `db.system()` for the `pack_slug` lookup |

## Section 2: Pack file schemas with exact roofing values

Quoting rules: regexes in YAML single quotes (`\b` literal; a literal `'` is written `''`) or `|-` blocks. YAML 1.1 bool footgun: never leave bare `yes`/`no`/`on`/`off` as scalars (list items in `service_area` are cities, safe; use quotes anyway for words). The golden test is the safety net for any escape mistake.

```python
# api/app/pack.py (models; all: model_config = ConfigDict(extra="forbid", frozen=True))
class PackMeta(M):
    slug: str                      # must equal folder name (cross-check)
    business: str                  # "Summit Roofing"
    kind: str                      # prompt wording: "a roofing company"
    offer: str                     # prompt wording: "books free roof inspections"
    timezone: str                  # IANA, validated via ZoneInfo: "America/Denver" (business-local identity)
    locale: str = "en-US"
    owner_email: str | None = None # optional; runtime owner mail still comes from settings.owner_email in this phase
class Calendar(M):
    timezone: str                  # zone in which slot_hours are interpreted; validated via ZoneInfo
    slot_hours: tuple[int, ...] = Field(min_length=1)   # each 0..23, strictly increasing
    slot_minutes: int = Field(gt=0, le=480)
    days_ahead: int = Field(ge=1, le=90)
    weekdays_only: bool
    buffer_minutes: int = Field(0, ge=0)
class Qualification(M):
    service_area: tuple[str, ...]            # lowercase single tokens (validator: == lower, no spaces)
    qualifying_services: frozenset[ServiceType]   # reuse schemas.ServiceType (D-09: enum stays core)
    max_timeline_months: int = Field(ge=0)
    service_synonyms: dict[ServiceType, str]      # regex, compiled in a validator
    non_business_pattern: str                     # regex
    owner_yes_pattern: str                        # regex
    owner_no_pattern: str                         # regex
    extra_stopwords: frozenset[str]
class Escalation(M):
    safety: str                                   # regex, compiled in a validator
    always_human: tuple[str, ...] = ()            # mirrors clients/summit-roofing.yaml; validated, unused in code until triage moves (D-07)
class FaqEntry(M):  source: str; text: str
class Faq(M):       entries: tuple[FaqEntry, ...] = Field(min_length=1)
class Messages(M):  # see below; validator checks each template's field set
    ...
class Pack(M):
    slug: str; hash: str
    meta: PackMeta; calendar: Calendar; qualification: Qualification; escalation: Escalation; messages: Messages; faq: tuple[FaqEntry, ...]
    @model_validator(mode="after")  # cross-file: qualifying_services <= keys(service_synonyms); meta.slug == folder
```
`ServiceType` needs `str` Enum keys; YAML gives plain strings so pydantic coerces. `frozenset`/`tuple` keep `frozen=True` truly immutable (lists would still be mutable inside a frozen model).

**businesses/summit-roofing/pack.yaml**
```yaml
slug: summit-roofing
business: Summit Roofing
kind: a roofing company
offer: books free roof inspections
timezone: America/Denver
locale: en-US
```

**calendar.yaml** (see Open Question 1 for `timezone`)
```yaml
# Legacy-faithful: v1 inserted these hours as UTC wall-clock (DB TimeZone=Etc/UTC). Changing this to America/Denver
# shifts every roofing slot by 6-7h and is a behaviour change, so it is deliberately NOT done in Phase 3.
timezone: Etc/UTC
slot_hours: [9, 11, 14, 16]
slot_minutes: 60
days_ahead: 14
weekdays_only: true
buffer_minutes: 0
```

**qualification.yaml**
```yaml
service_area: [denver, aurora, lakewood, arvada, centennial, littleton]
qualifying_services: [repair, replacement, inspection]
max_timeline_months: 6
service_synonyms:
  repair: 'repair|fix|patch|leak|damage|missing shingle'
  replacement: 'replac|new roof|re-?roof|tear.?off'
  inspection: 'inspect|check|estimate|assess|look at'
non_business_pattern: 'gutter|window|paint|solar|siding|chimney|plumb|clean|wash|fence|deck|hvac|lawn'
owner_yes_pattern: '\b(own|owns|owned|owner|homeowner|my (house|home|place|roof|property)|yes|yeah|yep|yup|sure|correct)\b'
owner_no_pattern: '\b(rent|renting|renter|rented|tenant|lease|leasing|landlord|not (the )?owner|(don''t|do not|dont) own)\b'
extra_stopwords: [roof, roofing, summit]
```
(`owner_no_pattern` shows the `''` escape; verify against `policy.py:117` character-for-character with the golden test, since the file was only displayed truncated in places.)

**escalation.yaml**
```yaml
safety: '\b(gas (leak|smell)|collaps\w*|electrocut\w*|exposed wires?|structural damage|injur\w*)\b'
always_human: [complaint]
```

**faq.yaml** (12 entries, verbatim from `faq.py:12-23`)
```yaml
entries:
  - {source: inspection, text: "The roof inspection is free and takes about 45 to 60 minutes."}
  - {source: inspection, text: "An inspection covers shingles, flashing, gutters and attic ventilation, and ends with a photo report."}
  - {source: inspection, text: "After the inspection you get a written estimate at no cost and with no obligation."}
  - {source: warranty, text: "Roof replacements carry a 10-year workmanship warranty. Roof repairs carry a 1-year workmanship warranty. Manufacturer shingle warranties are separate."}
  - {source: area, text: "Summit Roofing serves Denver, Aurora, Lakewood, Arvada, Centennial and Littleton."}
  - {source: eligibility, text: "Inspections are booked for property owners only. Renters need the owner to contact us."}
  - {source: process, text: "Our process: free inspection, written estimate, scheduling, installation, then a final walkthrough."}
  - {source: timeline, text: "A typical roof replacement takes 1 to 3 days depending on roof size."}
  - {source: pricing, text: "Pricing depends on roof size, materials and condition. Exact pricing is only given in the written estimate after an inspection; we do not quote prices in chat."}
  - {source: hours, text: "Inspections are available Monday to Friday between 8am and 5pm."}
  - {source: insurance, text: "We provide a photo report that you can submit to your insurer. We do not file insurance claims for customers."}
  - {source: materials, text: "We install asphalt shingle, metal and tile roofs."}
```
Flow-mapping values containing `: ` or `,` (e.g. "Our process: free inspection, ...", "...only given in the written estimate...; we do not...") are inside double quotes, so safe. Prefer block style (`- source: x` / `  text: "..."`) in the real file to avoid flow-style surprises.

**messages.yaml** (template field sets enforced at load; `{business}` allowed in every template)
```yaml
closed:
  DONE: "Your inspection is booked. If you need to change it, a team member will help you."
  DISQUALIFY: "Thanks again for your interest. Unfortunately we can't help with this one."
  ESCALATE: "A team member has your details and will follow up with you shortly."
disqualify: "Thanks for the details. Unfortunately we can only book inspections for property owners with a repair, replacement or inspection need in our service area within the next 6 months, so we can't help with this one. We appreciate you reaching out!"
nurture: "No problem at all! We'll check back with you later. Reach out any time you're ready for a free inspection."
no_slots: "You qualify for a free inspection, but we have no openings right now. We'll reach out as soon as new times open up."
safe_fallback: "I don't have that information, but a team member can confirm it for you. In the meantime, I can book you a free roof inspection."
qualified_prefix: "Good news, you qualify for a free roof inspection! "
slot_unavailable_prefix: "Sorry, that time isn't available. "
offer_slots: "{prefix}Here are the next openings: {options}. Which one works for you?"   # fields: prefix, options
pick_prompt: "Which of those openings works for you? Just say first, second, and so on."
booked: "You're booked for {when}. We'll see you then!"                                # fields: when
anything_else: "Is there anything else I can help you with?"
ask:
  service_type: "What roofing help do you need: a repair, a replacement, or an inspection?"
  is_owner: "Do you own the property?"
  address: "What's the property address, including the city?"
  timeline_months: "When would you like the work done?"
  name: "May I have your name?"
  "phone or email": "What's the best phone number or email to reach you?"
owner_alert_subject: "New booking: {name} ({when})"
owner_alert_body: "{name} booked a free roof inspection for {when}.\nPhone: {phone}\nEmail: {email}\nAddress: {address}\nNeed: {need}"
customer_subject: "Your inspection is booked: {when}"
customer_intro: "Hi {name},\n\nYour free roof inspection is booked for {when}.\n\n"
followup_subject: "Your free roof inspection with {business}"
followup_body: "{greeting}\n\nThanks for your interest in a free roof inspection. Whenever you're ready, just reply to this email or message us and we'll find a time that works.\n\n{business}"
```
Important: double-quoted YAML interprets `\n` as a newline (what we want); the `ask` key `phone or email` must keep the exact string because `missing_fields` appends that literal. `Messages.ask` must require exactly the six keys `{service_type, is_owner, address, timeline_months, name, phone or email}` (the keys are field names defined by `policy.missing_fields`' `wanted` list: core).

Core disclaimer (stays in `agent.py`, one module constant allowed because it is not business data):
`DEMO_NOTICE = "This was a demo of RoofDesk AI with a sample company ({business}). No one will visit, and nothing was scheduled.\n\nTo try RoofDesk AI for your own business, reply to this email.\n\n"`. Customer body = `customer_intro.format(...) + DEMO_NOTICE.format(business=...) + f"{settings.sender_name}\n{settings.sender_address}"`.

## Section 3: Byte-identical prompts

**How `load_prompt` works** [VERIFIED: llm.py:34-37]: reads `prompts_dir/<name>.md`, `partition("\n")` -> first line `version: agent.v2` becomes version `"agent.v2"`; body = rest `.strip()`ed (so the leading blank line and trailing newline vanish). The eval runner stores only `load_prompt(PROMPT)[0]`. Other prompts (triage, intake, outreach) use `<<x>>` replace too and go through the same function; do not change its signature.

**Placeholder design**
- Keep runtime tokens `<<asked>> <<known>> <<faq>>` exactly as they are.
- Add pack tokens `{{business}}`, `{{kind}}`, `{{offer}}`, `{{service_enum}}`. Verified: neither prompt file contains `{{` or `}}` today (grep count 0), and the JSON example only has single braces, so there is no collision.
- Edits (in place; version header lines unchanged so `prompt_version` metadata is stable):
  - `agent.v2.md:3`: `... for {{business}}, {{kind}} that {{offer}}, and you answer FAQ questions. ...` renders to "Summit Roofing, a roofing company that books free roof inspections, and you answer".
  - `agent.v2.md:19`: `"service_type": {{service_enum}},` renders to `"repair" | "replacement" | "inspection" | "other"` (built as `" | ".join(f'"{s}"' for s in services) + ' | "other"'`; the order must be repair, replacement, inspection, other; take it from `qualification.service_synonyms` key order or an explicit `services` list; pick the explicit order of `service_synonyms` insertion (dict order is preserved by pydantic/YAML)). The "other" literal stays core (D-09).
  - `faq-answer.v1.md:3`: `You answer one customer question for {{business}}, {{kind}}.` renders to "Summit Roofing, a roofing company."
- Render function: `def render(template: str, pack: Pack) -> str:` replaces the four keys, then `assert "{{" not in out` (raise `PackError`/`ValueError`) so a typo'd placeholder fails loudly. Order: pack render first, then the existing `<<...>>` replaces (pack values could in theory contain `<<`; none do; a load validator can forbid `<<`/`{{` in pack strings used by prompts).
- Wire as `agent._render(template, pack)` called in `_ask_llm` (line 166) and `_faq_answer` (144); keep `llm.load_prompt` untouched. `eval runner` untouched.

**Byte-identity test:** `FROZEN_AGENT_V2 = <literal body at tag v1-roofing, post-strip>` stored in the test as a literal (or read once via `git show v1-roofing:prompts/agent.v2.md` is NOT acceptable: no git in container). Assert `render(load_prompt("agent.v2")[1], roofing_pack) == FROZEN_AGENT_V2` for both prompts. Generate the literals now (this phase's 3a plan) by dumping `load_prompt(...)[1]` BEFORE editing the prompt files. Also assert that after the `<<...>>` replaces with sample values, the full system message is identical between old and new templates.

## Section 4: Slot generation

### Current SQL behaviour [VERIFIED: tools.py:32-43; DB probed]
```sql
INSERT INTO slots (tenant_id, start_time, end_time)
SELECT :t, d + make_interval(hours => h), d + make_interval(hours => h + 1)
FROM generate_series(date_trunc('day', now()) + interval '1 day',
                     date_trunc('day', now()) + make_interval(days => :n), interval '1 day') d,
     unnest(:hours) h
WHERE extract(isodow FROM d) < 6
AND NOT EXISTS (SELECT 1 FROM slots s WHERE s.tenant_id = :t AND s.start_time = d + make_interval(hours => h))
ON CONFLICT (tenant_id, start_time) DO NOTHING
```
Semantics: `now()` is `timestamptz`; `date_trunc('day', timestamptz)` truncates in the **session** TimeZone. Branch DB: `show timezone` = `Etc/UTC` (also `pg_settings`) [VERIFIED: psql on roofdesk-global-db-1]. So `d` = UTC midnights for tomorrow .. today+14 (inclusive: `days => 14` gives D+14), `isodow < 6` = Mon-Fri of the UTC date, start = UTC midnight + h hours, end = start + 1 hour. Live data confirms: 40 rows, `min 2026-11-04 09:00+00`, `max 2026-11-17 16:00+00` (10 weekdays x 4). **Hours are UTC, i.e. 02:00-09:00 in Denver**, an existing quirk (the FAQ says "8am to 5pm" and `_fmt` prints the UTC wall time). `NOT EXISTS` is kept so repeated calls do not burn `slots.id` serial values (ON CONFLICT alone would consume sequence numbers on every conflict).

The session TimeZone is a property of the DB/role/connection default, not set by the app (`db.tx` only sets `app.tenant_id`). Production (Railway) DB TZ is not verified here [ASSUMED UTC]; generating in Python with an explicit zone removes that dependence, which is itself a benefit.

### Recommended implementation
Pure function (testable with a frozen "now"), then one SQL insert:
```python
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

def slot_instants(cal: Calendar, now: datetime) -> list[tuple[datetime, datetime]]:
    tz = ZoneInfo(cal.timezone)
    today = now.astimezone(tz).date()                       # == date_trunc('day', now()) when tz == session tz
    out, last_end = [], None
    for i in range(1, cal.days_ahead + 1):                  # tomorrow .. today+days_ahead inclusive
        day = today + timedelta(days=i)
        if cal.weekdays_only and day.isoweekday() >= 6:
            continue
        last_end = None
        for h in cal.slot_hours:
            start = datetime.combine(day, time(h), tzinfo=tz).astimezone(timezone.utc)
            end = start + timedelta(minutes=cal.slot_minutes)           # absolute duration
            if last_end and start < last_end + timedelta(minutes=cal.buffer_minutes):
                continue                                              # buffer: skip a start too close to the previous slot
            out.append((start, end)); last_end = end
    return out

# ensure_slots: pack = get_pack(tenant_id); rows = slot_instants(pack.calendar, datetime.now(timezone.utc))
# INSERT INTO slots (tenant_id, start_time, end_time)
# SELECT :t, s, e FROM unnest(CAST(:starts AS timestamptz[]), CAST(:ends AS timestamptz[])) AS u(s, e)
# WHERE NOT EXISTS (SELECT 1 FROM slots x WHERE x.tenant_id = :t AND x.start_time = s)
# ON CONFLICT (tenant_id, start_time) DO NOTHING
```
`unnest(:hours)` is already used with a Python list under psycopg3, so list params work; timestamptz[] via `CAST` is the same pattern (verify in the first task with a one-row experiment; fallback: `executemany` of single-row INSERT ... WHERE NOT EXISTS).

Buffer semantics (new, PACK-05 requires it to change generation): buffer = minimum gap after a slot ends before the next slot may start; hours that violate it are dropped. For roofing (gaps 2h/3h/2h, length 1h, buffer 0) nothing changes. Validate at load that `slot_hours` strictly increasing; a model validator may also reject `slot_minutes` longer than every gap if desired (optional).

DST note: `datetime.combine(day, time(h), tzinfo=ZoneInfo)` is wall-clock correct; non-existent/ambiguous local times (02:00-03:00 on transition days) resolve by `fold=0`; irrelevant for 9-16.

Display: `agent._fmt(iso)` parses the ISO string emitted by Postgres in the session TZ (UTC) and prints that wall time. Make it `datetime.fromisoformat(iso).astimezone(ZoneInfo(pack.calendar.timezone)).strftime(...)`: for roofing (`Etc/UTC`) output is byte-identical; for any other pack the shown time equals the zone the slots were generated in. `strftime("%I")` unchanged.

### Equivalence test (D-11)
Replicate the old SELECT in the test with `now()` replaced by `CAST(:now AS timestamptz)` inside `SET LOCAL TimeZone='UTC'` (read-only SELECT, no inserts), and assert `sorted(old) == sorted(slot_instants(roofing.calendar, now))` for frozen `now` values covering: a Monday, a Friday, a Saturday, a Sunday, a month end, a year end, 23:59 UTC, and 00:00 UTC. Plus one live check: `ensure_slots()` then `SELECT start_time` for tenant A equals the pure function output with `now = SELECT now()` (existing rows may be from earlier days; compare the subset >= tomorrow). Plus changes-propagate tests for PACK-05: copy the pack to `tmp_path`, edit hours/slot_minutes/days_ahead/buffer/timezone, assert `slot_instants` changes (pure, no DB).

Existing rows are never revised by a pack edit (stale slots at old hours stay until booked/expired); document, do not "fix" in Phase 3.

## Section 5: Cache design and policy signatures

```python
_CACHE: dict[tuple[str, str], Pack] = {}          # (tenant_id, pack_hash) -> Pack ; module state but not business data
_LOCK = threading.Lock()                          # sync endpoints run in a threadpool

def pack_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode()); h.update(b"\0"); h.update(p.read_bytes())
    return h.hexdigest()

def get_pack(tenant_id: str | None = None) -> Pack:
    t = str(tenant_id or settings.default_tenant_id)
    with system() as c:                                            # tenants rows are outside tenant RLS scope; db.system() is the explicit context
        slug = c.execute(text("SELECT pack_slug FROM tenants WHERE id = :t"), {"t": t}).scalar()
    if not slug:
        raise PackError(f"tenant {t} has no pack_slug")
    key = (t, pack_hash(settings.businesses_dir / slug))
    if (pack := _CACHE.get(key)) is None:
        pack = _load(slug, key[1])
        with _LOCK:
            _CACHE[key] = pack
            for old in [k for k in _CACHE if k[0] == t and k != key]:  # evict superseded versions of this tenant
                del _CACHE[old]
    return pack
```
Notes: (a) hashing ~7 tiny files per turn costs well under a millisecond-scale and adds one cheap indexed query; no mtime tricks (D-03). (b) The only module-level mutable is the cache, keyed by tenant+hash, so a two-tenant interleave test is straightforward (PACK-07). (c) A pack edited mid-conversation changes later turns for open conversations (PITFALLS 17); accepted for this phase, but cheaply mitigated by adding `"pack": pack.hash[:12]` to the `turn_start` event payload (payload is ids/flags only, which a hash satisfies); optional. (d) `tenants.pack_slug` is read through `system()` not `tx()` because it is tenant-directory data; confirm `tenants` has no RLS policy (Phase 6 scope) before relying on it. (e) `get_pack` must not be called inside an open `tx()` of the same turn unnecessarily (separate connection, fine with the pool).

**Signature policy (answers D-04 "keep stable vs thread a parameter"):** thread `pack` as a **required first positional** argument for pack-dependent functions; no default. Concretely:
`escalation_reason(message, only=None, pack=None)` where `pack=None` means generic patterns only (needed for untenanted callers), ordering preserved; likewise `answer_supported(answer, faq_texts, pack=None)`. All of `address_status(pack, address)`, `qualification(pack, lead)`, `missing_fields(pack, lead)`, `next_question(pack, lead)`, `is_grounded(pack, field, value, message, asked="")`, `ground(pack, fields, message, asked="")` take `pack` first. Test impact: `test_policy.py` ~35 call sites: add a `roofing_pack` fixture (module-scoped, `load_pack("summit-roofing")` bypassing the DB) in `conftest.py` and edit each call (mechanical). Parametrised cases and `GOOD` stay as they are. The functions' bodies keep their code (D-05).

Escalation order must be preserved. Today dict order is human_request, legal, safety, angry; a message matching safety and angry ("this is ridiculous, part of my roof collapsed") returns `safety`. Implement with an explicit order tuple:
```python
_ESCALATION_ORDER = ("human_request", "legal", "safety", "angry")
_GENERIC_ESCALATION = {"human_request": r"...", "legal": r"...", "angry": r"..."}   # verbatim
def escalation_reason(message, only=None, pack=None):
    patterns = {**_GENERIC_ESCALATION, **({"safety": pack.escalation.safety} if pack else {})}
    for reason in _ESCALATION_ORDER:
        if reason in patterns and (only is None or reason in only) and re.search(patterns[reason], message, re.I): return reason
```
Test: for every sample in the old parametrisation plus mixed safety+angry, new == old (old kept in the frozen fixture).

## Section 6: `tenants.pack_slug` state [VERIFIED: db/migrations/001_tenants.sql; psql on branch DB]
Column exists: `pack_slug text` (nullable, no FK, no CHECK). Branch DB: one row `00000000-0000-0000-0000-000000000001 | summit-roofing | America/Denver | summit-roofing`. Test tenants (`tb`, other `test-*`) are inserted without it (NULL). So no migration is required for Phase 3. Decisions: (1) NULL/unknown slug -> `PackError` (fail loud; no silent roofing default). (2) Update `tb`-style fixtures to set `pack_slug`. (3) Optionally a migration `005_pack_slug_check.sql` adding a slug-format CHECK; not needed, skip (YAGNI) since the loader validates `[a-z0-9-]+`. (4) `tenants.timezone` ('America/Denver') and `pack.yaml: timezone` are intentionally two sources; add a load-time warning log (not an error) if they differ, or leave; Phase 7 daily-brief will pick one.

## Section 7: Docker / mounts / tzdata [VERIFIED: docker-compose.yml:40-47, api/Dockerfile, root Dockerfile]
- api service volumes: `./api/app:/srv/app`, `./prompts:/srv/prompts:ro`, `./clients:/srv/clients:ro`, `./site`, `./db:/srv/db:ro`, `./evals`, `./scripts`. **There is no `businesses` mount**, and `api/Dockerfile` only `COPY app app`. `settings.prompts_dir=/srv/prompts`, `clients_dir=/srv/clients`: add `businesses_dir: Path = Path("/srv/businesses")` in `config.py` and the mount `- ./businesses:/srv/businesses:ro` to the api service in `docker-compose.yml` (the `-f docker-compose.global.yml` overlay only overrides ports, so one edit covers the branch stack). Adding a mount requires re-creating the container: `make g-up` (up -d --build) not just a restart; `app` is a live bind mount so new `.py` files appear instantly, but `--reload` does not watch `/srv/businesses`; a pack edit is picked up by the hash on the next turn, no reload needed.
- Root `Dockerfile` (Railway production build) copies `api/app prompts clients site db` only. **It needs `COPY businesses businesses`** or the live demo crashes on its first chat/start the moment this branch is deployed (the `scripts/check-and-deploy.sh` flow uses `railway up`). Make this part of the Phase 3 plan as an explicit task and never deploy from the branch without it (the user also requires asking before deploying).
- `.dockerignore` excludes `.git .env dashboard n8n evals docs scripts` etc.; `businesses` is not ignored. OK.
- Tests run in-container (`make g-test`); pack path comes from settings so tests see `/srv/businesses/summit-roofing` through the mount. A `tmp_path` copy (via `monkeypatch.setattr(settings, "businesses_dir", tmp_path)`) is used for malformed-pack tests.
- tzdata: container already resolves `ZoneInfo("America/Denver")` (system `/usr/share/zoneinfo` present; pip `tzdata` absent) [VERIFIED]. Add `tzdata` to `api/requirements.txt` anyway (D-11; base-image independence). Calendar timezone `Etc/UTC` resolves via zoneinfo as well (tested name; `UTC` also works).

## Common Pitfalls

### Pitfall 1: Slots shifted by the Denver offset
**What goes wrong:** Pack says `America/Denver` + hours 9/11/14/16 -> instants 15:00/17:00/20:00/22:00 UTC; roofing eval (`slots`, `out_of_order`) and the booking text change; baseline drift.
**How to avoid:** roofing `calendar.timezone: Etc/UTC` (Section 4); the frozen-now equivalence test is mandatory in the same plan that changes `ensure_slots`.
**Warning signs:** `SELECT min(start_time)` for a fresh tenant not on 09:00+00.

### Pitfall 2: Placeholder token collision
`<<faq>>` etc. are runtime tokens; reusing `<<business>>` (triage's style) in `agent.v2` would be consumed or left behind depending on replace order. Use `{{}}` for pack tokens and assert none remain.

### Pitfall 3: Escalation order and `only=`
Merging dicts changes iteration order -> a mixed message flips from `safety` to `angry`. Use the explicit order tuple; keep `only=("safety","legal")` semantic for closed conversations; the pack-less path (`pack=None`) has no `safety`.

### Pitfall 4: Untenanted callers silently lose roofing behaviour
`triage.triage` uses `escalation_reason` (safety) and `answer_supported` (roof/roofing/summit stopwords). Pass `get_pack(settings.default_tenant_id)` there (triage profile `summit-roofing` is the default `client_profile`), or the `/triage` endpoint stops escalating "gas leak" messages. `intake` only uses `looks_like_question` (core).

### Pitfall 5: YAML escaping of regexes and 'quotes'
Single quotes inside single-quoted scalars need `''` (`don''t`); double-quoted scalars would eat `\b`. The golden test compares every value to the old constant; also compile every regex at load so a bad escape fails at load. YAML 1.1 turns bare `yes`/`no`/`on`/`off` into booleans: quote any such scalar.

### Pitfall 6: Template format hazards
`str.format` raises `KeyError`/`IndexError`/`ValueError` at chat time if a template has an unknown field or a stray brace. The load-time field-set validator (Pattern 2) is the whole defence; test with a deliberately broken template. Literal braces in text -> `{{ }}`.

### Pitfall 7: Trailing spaces in prefix templates
`qualified_prefix`/`slot_unavailable_prefix` end with a space the reply concatenation relies on; YAML double-quoted preserves it. Do not let an editor strip it; golden test compares exactly. Do not `.strip()` messages at load.

### Pitfall 8: Silent FAQ seeding failure
`main.py` lifespan swallows seed exceptions (`except Exception: pass`). With per-tenant packs a bad pack is a PackError at startup: log it with tenant id; do not crash startup for other tenants.

### Pitfall 9: Deleting old constants too early
Order is fixed by D-06: golden test against live constants first, then rewire, then switch the golden test to a literal fixture (`api/app/test_pack.py::FROZEN_OLD`) and delete constants. Capture the frozen literals before deleting (copy via a one-off script run in the container that prints repr of each old constant; do not retype by hand).

### Pitfall 10: Docs/comments count as globals
PACK-07 verification is a grep. Strip "Summit", "roof", "Denver", slot-hour comments from `policy.py agent.py tools.py faq.py admin.py` (the admin.py grep must be scoped to the follow-up function or the whole file, which has no other roofing text).

## Code Examples

### Golden test (3a, against live constants), shape
```python
def test_pack_equals_old_constants(roofing_pack):
    q = roofing_pack.qualification
    assert set(q.service_area) == set(policy.SERVICE_AREA)
    assert set(q.qualifying_services) == policy.QUALIFYING_SERVICES
    assert q.max_timeline_months == policy.MAX_TIMELINE_MONTHS
    assert q.owner_yes_pattern == policy._OWN_YES and q.owner_no_pattern == policy._OWN_NO
    assert q.non_business_pattern == policy._NON_ROOF
    assert {k.value: v for k, v in q.service_synonyms.items()} == policy._SERVICE
    assert roofing_pack.escalation.safety == policy._ESCALATION_PATTERNS["safety"]
    assert roofing_pack.messages.ask == policy.ASK
    assert roofing_pack.messages.safe_fallback == policy.SAFE_FALLBACK
    assert tuple((e.source, e.text) for e in roofing_pack.faq) == tuple(faq.FAQ)
    assert tuple(roofing_pack.calendar.slot_hours) == tools.SLOT_HOURS and roofing_pack.calendar.days_ahead == tools.SLOT_DAYS_AHEAD
    assert roofing_pack.messages.closed == agent.CLOSED_REPLY   # + DISQUALIFY/NURTURE/NO_SLOTS
    assert q.extra_stopwords | CORE_GENERIC == policy._GENERIC
```
3b: replace each right-hand side with a literal in `FROZEN_OLD = {...}`.

### CLI
`python -m app.pack summit-roofing` -> `load_pack(slug)` (no DB) -> print `slug, hash[:12], services, #faq, calendar summary`; exit 1 with the `PackError` message on failure. Provide `load_pack(slug)` (no tenant, no cache) separately from `get_pack(tenant_id)`; tests and the CLI use `load_pack`.

## State of the Art
| Old | Current | Impact |
|-----|---------|--------|
| Module constants per business | frozen Pydantic pack passed explicitly | testable, per-tenant |
| `date_trunc` in SQL session tz | explicit zone in Python (zoneinfo) | independent of DB TimeZone; DST-safe |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | tzdata package is legitimate (slopcheck not run; PyPI JSON confirms 2026.6 and python/tzdata repo) | Standard Stack | Low; planner gates install with `checkpoint:human-verify` |
| A2 | Production (Railway) Postgres TimeZone is UTC, so Python-UTC generation equals prod's old SQL output | Section 4 | Only affects whether the live DB's existing slots align; branch DB is verified UTC |
| A3 | Stopword split: move only `roof roofing summit` into the pack | Section 1A | Low; the union-equals-old test holds for any split |
| A4 | `tenants` has no RLS policy so `system()` can read `pack_slug` (Phase 2 plans say RLS is Phase 6 only) | Section 5 | If wrong, `get_pack` returns None; verify with one query in task 1 |
| A5 | Buffer semantics (min gap after slot end; drop violating starts) | Section 4 | Spec does not define it; purely my design; only affects non-roofing packs |
| A6 | Existing admin follow-up tests exist and may assert subject/body text | Section 1E | Mechanical; byte-identical text keeps them green |

## Open Questions (RESOLVED)

1. **Roofing `calendar.timezone`: `Etc/UTC` or `America/Denver`?**
   - Known: D-11 lists `timezone: America/Denver` AND requires UTC-equivalent instants for roofing; these are contradictory because today's hours are UTC wall-clock.
   - Recommendation: `timezone: Etc/UTC` in `calendar.yaml` (slot-interpretation zone) while `pack.yaml: timezone: America/Denver` carries business identity. Document the legacy quirk in the YAML comment; correcting roofing to local hours is a separate, deliberately behaviour-changing step after the gate (Phase 5+). Planner should confirm with the user.
   - **RESOLVED:** `calendar.yaml` timezone = `Etc/UTC` (slot interpretation zone); `pack.yaml` keeps `America/Denver` as business identity. This deviates from D-11's listed Denver value and is surfaced in the 03-01 and 03-03 SUMMARY requirement deviations (plans 03-01, 03-03).
2. **Demo disclaimer: core (D-10) or pack (ROADMAP success criterion 3 and PACK-04 say "from pack templates")?**
   - Recommendation: follow locked D-10 (core constant, `{business}` from pack); mention the discrepancy in the verification doc.
   - **RESOLVED:** Disclaimer stays core (`agent.DEMO_NOTICE`) with the business name from the pack, per D-10. Deviation from ROADMAP criterion 3 wording surfaced in the 03-03 SUMMARY (plan 03-03 Task 2).
3. **`_fmt` time zone display.** Recommendation above (convert to `pack.calendar.timezone`); identical for roofing.
   - **RESOLVED:** Plans do this: `_fmt(iso, pack)` converts to `pack.calendar.timezone` (Etc/UTC for roofing, so output is identical) (plan 03-03 Task 2).
4. **Add `pack` hash to `turn_start` event payload?** Optional, cheap; skipped unless planner wants Pitfall-17 traceability now.
   - **RESOLVED:** Skipped: no plan adds the pack hash to the `turn_start` payload (03-02 leaves `_turn_start` unchanged); revisit when pack traceability is needed.
5. **`always_human` in `escalation.yaml` has no consumer in Phase 3** (triage keeps reading `clients/*.yaml`). Recommendation: include and validate it (D-07), add a golden assertion against `clients/summit-roofing.yaml`.
   - **RESOLVED:** Included and validated in `escalation.yaml` with a golden assertion against `clients/summit-roofing.yaml` `always_human` (plan 03-01 Task 3); no runtime consumer in Phase 3.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker branch stack (`roofdesk-global` project: api, db, n8n, mailpit) | in-container pytest, eval gate | yes (api up 2h, db healthy) | api python 3.12.14 | `make g-up` |
| Postgres | slots/FAQ tests | yes; `TimeZone=Etc/UTC` | -- | -- |
| zoneinfo db | tz tests | yes (system tzdata); pip `tzdata` absent | -- | add `tzdata` |
| Ollama (local LLM + embeddings) | `make eval-gate`, real `seed_faq` embeddings | not probed here | -- | gate guard aborts non-local answers (Phase 2 note); unit tests monkeypatch `llm.embed` |
| slopcheck | package audit | no (install denied) | -- | `[ASSUMED]` + human-verify |

**Missing, blocking:** none known. The api container must be recreated after the compose mount edit.

## Validation Architecture

(`workflow.nyquist_validation: true` in `.planning/config.json`.)

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.* (in `api/requirements.txt`), run in the api container; tests live beside code as `api/app/test_*.py`; `api/app/conftest.py` provides DB cleanup fixtures |
| Config file | none (no pytest.ini; `python -m pytest` from `/srv`) |
| Quick run command | `make g-test ARGS="app/test_pack.py app/test_policy.py -x"` |
| Full suite command | `make g-test` (DB-backed; conftest removes `test-*` tenants afterwards) |
| Regression gate | `LLM_TIMEOUT_S=300 make eval-gate` (94/96, only voice-over-explainer and voice-indecisive fail); mid-phase `ARGS="--ids ..."` subsets |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PACK-01 | unknown key / missing field / bad regex / bad tz / bad template field fail with file + field path; slug traversal rejected; empty YAML | unit (tmp_path copy of pack) | `make g-test ARGS="app/test_pack.py -k malformed"` | Wave 0 |
| PACK-02 | every pack value equals old constant (3a), then frozen literal (3b); `faq_seed.sql` rows == pack faq | unit | `... -k golden` | Wave 0 |
| PACK-03 | rendered `agent.v2` and `faq-answer.v1` == frozen literals; no `{{` left; full system message identical after `<<>>` fill | unit | `... -k render` | Wave 0 |
| PACK-04 | each reply/email template renders to the old f-string output for sample data; customer email incl. disclaimer + signature identical; admin follow-up body identical | unit | `... -k messages` | Wave 0 |
| PACK-05 | `slot_instants` == old SQL output for frozen nows; edits to hours/minutes/days/buffer/timezone change output; `ensure_slots` idempotent and tenant-scoped (existing `test_tenancy` tests) | unit + DB | `... -k slots` and `app/test_tenancy.py -k slots` | Wave 0 / exists |
| PACK-06 | escalation reasons identical old vs new incl. mixed safety+angry and `only=`; pack-less call has no `safety` | unit | `... -k escalation` | Wave 0 |
| PACK-07 | two tenants with different packs interleaved in one process get their own pack objects; edit file -> new hash -> reload and old entry evicted; grep/AST test: no roofing words or module-level business constants in `policy agent tools faq admin` source | unit + static | `... -k cache` / `-k no_globals` | Wave 0 |
| (regression) | `policy.*` behaviours unchanged | existing | `make g-test ARGS="app/test_policy.py app/test_agent.py app/test_tenancy.py"` | exists, edited |
| (regression) | roofing eval = baseline per scenario id | gate | `make eval-gate` | exists |

### Sampling Rate
- Per task commit: `make g-test ARGS="app/test_pack.py app/test_policy.py -x"` (seconds; DB only for slots/seed tests)
- Per wave merge: `make g-test` (full suite) plus `eval-gate --ids` subset covering qualified, disqualified, slots, faq, escalation
- Phase gate: full `make eval-gate` 94/96 same two failures, full pytest green, `git grep -niE "summit|roof|denver" -- api/app/{policy,agent,tools,faq,admin}.py` empty

### Wave 0 Gaps
- [ ] `api/app/test_pack.py` (all tests above) and `roofing_pack` fixture in `api/app/conftest.py`
- [ ] frozen literals for old constants and the two prompt bodies, captured BEFORE edits
- [ ] `businesses/summit-roofing/` mounted in compose; `tzdata` in requirements; `businesses_dir` setting
- [ ] edit `tb` fixture in `test_tenancy.py` to set `pack_slug`

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Pydantic `extra="forbid"`; slug `[a-z0-9-]+` (path traversal); `yaml.safe_load` only |
| V12 Files/Resources | yes | pack dir read-only mount; slug never contains `/` or `..` |
| V2/V3/V4/V6 | no | no auth/session/crypto change (RLS and keys are Phase 6) |
| V14 Config | yes | pack hash content-addressing; no secrets in pack files |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via `pack_slug` from DB | Tampering | slug regex before building the path |
| Malicious/catastrophic regex in a pack (ReDoS) | DoS | packs are operator-authored; compile at load; no user-supplied packs this phase; note for `make new-business` |
| YAML object construction | Tampering/RCE | `safe_load` only |
| Cross-tenant pack bleed via cache | Information disclosure | key `(tenant_id, hash)`; no pack in module globals; interleaved-tenant test |
| Template injection via customer text into `str.format` | Tampering | only fixed code-controlled fields are formatted; customer strings are values, never format strings |

## Sources

### Primary (HIGH)
- Repo reads: `api/app/{policy,agent,tools,faq,admin,llm,triage,config,db,bootstrap,main,conftest}.py`, `api/app/test_{policy,agent,tenancy}.py`, `prompts/agent.v2.md`, `prompts/faq-answer.v1.md`, `clients/summit-roofing.yaml`, `db/faq_seed.sql`, `db/migrations/001-004`, `docker-compose*.yml`, `api/Dockerfile`, root `Dockerfile`, `Makefile`, `evals/runner.py`, `.planning/{ROADMAP,REQUIREMENTS}.md`, `.planning/research/{STACK,PITFALLS}.md`, phase 1 inventory, phase 2 CONTEXT
- Live probes on the branch stack: `show timezone` = Etc/UTC; slot rows 2026-11-04 09:00+00 .. 2026-11-17 16:00+00 (40); `tenants` row; `ZoneInfo("America/Denver")` works; `pip show tzdata` absent
- `git show v1-roofing:prompts/*` equals working-tree prompts
- https://pypi.org/pypi/tzdata/json (2026.6, 2026-10-28)

### Secondary / Tertiary
- Pydantic v2 `ValidationError.errors()` loc tuples, `frozen`, `extra="forbid"`; `string.Formatter.parse`; `zoneinfo`: stdlib/pydantic behaviour from training knowledge, not re-fetched this session [ASSUMED, MEDIUM-HIGH]; each is exercised by the Wave 0 tests so a wrong assumption fails fast.

## Metadata
**Confidence breakdown:** Standard stack HIGH (all in repo); Inventory HIGH (read line by line; a few long regexes were displayed truncated in my probe, hence the golden-test-first plan); Slot semantics HIGH (SQL read + DB probed); Docker findings HIGH; Prod DB TZ LOW (A2).
**Research date:** 2026-11-03. **Valid until:** ~30 days (stable code; invalidated by edits to the listed files).
