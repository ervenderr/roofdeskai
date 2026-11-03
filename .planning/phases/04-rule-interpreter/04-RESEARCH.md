# Phase 4: Rule Interpreter - Research

**Researched:** 2026-11-03
**Domain:** Pure-Python rule interpreter replacing hardcoded qualification, proven by a differential test
**Confidence:** HIGH (all findings are from reading the repo source; address outputs in section 4 were produced by running the old `address_status`)

<user_constraints>
## User Constraints (from 04-CONTEXT.md)

### Locked Decisions
- D-01 `qualification.yaml` gains `rules:` (list). Each rule: `id`, `field` (LeadFields name), `rule` (`in_list|yes_no|max_number|in_area`), `question` (ask text key or inline), type params (`in_list.values`, `max_number.max`, `in_area.cities`; `yes_no` none), `required: true` default. Pydantic discriminated union on `rule`, `extra="forbid"`, unknown rule type fails at load naming file and field.
- D-02 Result semantics identical to today: True/False/None; `disqualified` as soon as any known rule is False; `qualified` only when all True; else `incomplete`. File order = question order.
- D-03 `in_area` ports `address_status` UNCHANGED; only the city list becomes a parameter.
- D-04 `LeadFields` fixed; no custom fields. Contact capture (`name`, phone or email) stays core.
- D-05 Disqualify text and ask questions stay in `messages.yaml`, referenced by rule `id`; loader validates every rule id has an ask message.
- D-06 `qualify.py`: dispatch dict of four pure functions; `qualify(pack, lead)`, `missing_fields(pack, lead)`, `next_question(pack, lead)`. policy.py keeps non-qualification logic.
- D-07 Dual-run: old and new coexist; delete old only after zero differences AND full roofing eval gate matches baseline.
- D-08 Deterministic grid (service x owner x timeline x ~40 addresses) + seeded fuzz of address strings. Zero differences.
- D-09 Relax `ServiceType`: `LeadFields.service_type` becomes a validated string; pack declares service types. Must prove (test + eval subset) invalid-enum model output ends in the same state; if not removable, keep enum for roofing and defer to Phase 5.
- D-10 Prompt `{{service_enum}}` stays.
- D-11 `service_synonyms` / `non_business_pattern` stay in pack; add tests that editing them changes grounding with no code change.
- D-12 Each plan ends with in-container pytest; mid-phase may run the subset gate (`-e LLM_TIMEOUT_S=300`, qual-1..qual-12 + disqualified ids); final plan runs the full gate (94/96, same two failures, local-only guard).

### Claude's Discretion
YAML key names beyond the above, module/file naming, grid size, whether `missing_fields` order is rule order or an explicit `ask_order`.

### Deferred Ideas (OUT OF SCOPE)
Custom lead fields (Phase 5), demo-disclaimer pack flag (Phase 5/9), roofing calendar tz flip to America/Denver.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUAL-01 | Rule interpreter reading `qualification.yaml` with pack-defined questions/disqualify text | Sections 2, 3 |
| QUAL-02 | Synonyms and non-business words come from the pack | Already true (Phase 3); Section 5 grounding KeyError hazard; D-11 tests |
| QUAL-03 | Differential test, zero differences, before old path deleted | Section 4 |
</phase_requirements>

## Summary

The old logic is four small functions in `api/app/policy.py` (lines 29-81). Everything the interpreter must reproduce is a handful of identity/None/"" subtleties (section 1). The rule schema maps one-to-one onto the four existing checks; with `id == field name` for roofing, `messages.yaml` needs no edit and `ask` keys stay identical. The only structural wrinkle is `Messages.ask` currently demands exactly the 6 ASK_KEYS at model level; that check must move to `load_pack` (needs rule ids).

The ServiceType relaxation is feasible with identical behaviour IF the "enum-invalid" rejection is kept at the same point (inside `_parse`, so the existing one-retry-then-ESCALATE path runs). Do it with a pydantic validator reading `info.context` supplied by `agent._parse(raw, pack)`. A second hazard: `policy.is_grounded` does `service_synonyms[value]`, which would `KeyError` on an unknown string that slips through; the parse-time check prevents it, and a defensive `.get` is cheap.

**Primary recommendation:** Replace the three legacy qualification keys with `rules:` and expose `service_area`/`qualifying_services`/`max_timeline_months` as read-only properties on `Qualification` (derived from rules) so the OLD functions stay callable unchanged for the dual run; call `qualify.*` directly from `agent.py` and `evals/runner.py`; before deleting old code, freeze a SHA-256 of the old grid results so the zero-diff proof survives deletion.

## Architectural Responsibility Map

| Capability | Primary Tier | Rationale |
|------------|-------------|-----------|
| Rule evaluation, missing fields, next question | API / Backend (`qualify.py`, pure) | "All decisions in FastAPI"; no DB, no LLM |
| Rule/pack validation | API / Backend (`pack.py` loader) | Fails at load, not chat time |
| Service value validation of model output | API / Backend (`agent._parse` via LeadFields validator) | Same retry/escalate path as today |
| Ask / disqualify wording | Pack data (`messages.yaml`) | D-05 |

## Standard Stack

No new libraries. Pydantic v2 (already pinned `2.*`), stdlib `re`, `hashlib`, `random`, pytest. Nothing to install; Package Legitimacy Audit: not applicable (no external packages). [VERIFIED: api/requirements.txt scope per CLAUDE.md STACK.md; "Pydantic union + dispatch dict, no new library"]

## 1. Exact current semantics (the interpreter must reproduce these)

Source: `api/app/policy.py` lines 29-81. [VERIFIED: source read]

### address_status(pack, address) -> "in" | "out" | "incomplete"
1. `not address` (None, "") or no `\d` anywhere (`re.search(r"\d")`, Unicode digits count) -> `incomplete`.
2. `parts = [p.strip().lower() for p in address.split(",")]`.
3. IN if: any comma part AFTER the first has a word (`[a-z]+` runs) in the city set; OR (only when there is exactly one part, i.e. no comma) any `[a-z0-9]+` token of the whole string is a city. So the street part (parts[0]) never matches when commas exist, but with no comma a street named after a city matches ("12 Denver Ave" -> in).
4. OUT if any later part, after stripping a trailing `(\s+[a-z]{2})?(\s+\d{5}(-\d{4})?)?$` (state, ZIP), fullmatches `[a-z .'-]{3,}` and does not start with `apt|unit|suite|ste|floor` (word boundary).
5. Else `incomplete`.
Consequences: "Apt 4" and bare state/ZIP parts are incomplete; "CO" (2 letters) fails `{3,}`; non-ASCII letters fail `[a-z .'-]` in step 4 but pass step 3 only via `[a-z]+` runs ("ño Denver" -> in because "denver" is a run); "Denverton" is not "denver" (whole-word) -> out; `;` is not a separator, so "12 Oak St; Denver" is a single part -> in via tokens.

### qualification(pack, lead) -> str
Four checks in this order, each True/False/None:
- service: `None` if `lead.get("service_type") is None`, else `value in qualifying_services` (so `""`, `"other"`, `"plumbing"`, `"Repair"` are all **False -> disqualified**; `""` is NOT unknown here).
- owner: raw `lead.get("is_owner")`, then tested by IDENTITY (`c is False`, `c is True`). `1`, `0`, `"yes"` are neither -> behave as unknown. DB gives only True/False/None.
- address: `{"in": True, "out": False}.get(status)`; incomplete -> None.
- timeline: `None` if None else `value <= max_timeline_months` (0 passes; negative passes).
Verdict: any `False` -> `disqualified`; else all `True` -> `qualified`; else `incomplete`. Budget, property_type, name, phone, email never affect it. A False in one rule wins even when other fields are unknown.

### missing_fields(pack, lead) -> list[str]
`wanted = [service_type, is_owner, address, timeline_months, name]`, in that order. A field is missing if `lead.get(f) is None or == ""`, or (address only) `address_status == "incomplete"` (so whitespace-only "   " and "12 Oak St" are missing; an `out` address is NOT missing). `False` and `0` are not missing. Then `"phone or email"` appended iff `not (phone or email)` (truthiness: "" counts as absent). Note: `service_type=""` is missing here but False in `qualification` - an inconsistency the interpreter must keep (cannot come from the DB because `LeadFields.blank_to_none` strips "", but the grid should include it). `name=" "` is not missing (truthy-ness not tested, only None/"").

### next_question(pack, lead)
`pack.messages.ask[missing[0]]` if anything missing else `pack.messages.anything_else`. Keys are field names plus `"phone or email"`.

### How agent.py uses them (`_decide`, lines 83-119)
After grounding and `update_lead`, the lead row is re-read; `verdict = policy.qualification(pack, lead)`.
- `disqualified` -> lead status disqualified, state DISQUALIFY, return `pack.messages.disqualify` (one text for all rules).
- `qualified and policy.has_contact(lead)` -> offer slots / book (`has_contact` = name and (phone or email); stays in policy).
- Otherwise (incomplete, or qualified but no contact) -> `policy.next_question(pack, lead)` appended to the FAQ answer. So a fully qualified lead with no name/contact is asked for `name`/`phone or email` via `missing_fields`.
Other call site: `evals/runner.py:97` (`invalid_booking` check). Tests: `test_policy.py` lines 11, 21, 25-26, 37, 41, 100, 141-146.

## 2. Proposed `qualification.yaml` schema

```yaml
# rules are evaluated and asked in file order; name and phone-or-email are core and always asked after them
service_synonyms: {...unchanged...}
non_business_pattern: ...
owner_yes_pattern: ...
owner_no_pattern: ...
extra_stopwords: [roof, roofing, summit]
rules:
  - {id: service_type,    field: service_type,    rule: in_list,    values: [repair, replacement, inspection]}
  - {id: is_owner,        field: is_owner,        rule: yes_no}
  - {id: address,         field: address,         rule: in_area,    cities: [denver, aurora, lakewood, arvada, centennial, littleton]}
  - {id: timeline_months, field: timeline_months, rule: max_number, max: 6}
```
`service_area`, `qualifying_services`, `max_timeline_months` are REMOVED from the YAML (single source of truth). Rule ids equal field names so `messages.ask` keys and text are untouched.

### Models (pack.py, replace the three fields)
```python
class RuleBase(M):
    id: str = Field(pattern=r"[a-z][a-z0-9_]*")
    field: str
    required: bool = True

class InList(RuleBase):
    rule: Literal["in_list"]
    values: tuple[str, ...] = Field(min_length=1)

class YesNo(RuleBase):
    rule: Literal["yes_no"]

class MaxNumber(RuleBase):
    rule: Literal["max_number"]
    max: int = Field(ge=0)

class InArea(RuleBase):
    rule: Literal["in_area"]
    cities: tuple[str, ...] = Field(min_length=1)   # reuse the existing lowercase single-token validator

Rule = Annotated[InList | YesNo | MaxNumber | InArea, Field(discriminator="rule")]

class Qualification(M):
    rules: tuple[Rule, ...] = Field(min_length=1)
    service_synonyms: dict[str, str]  # keys were ServiceType
    ... (patterns, extra_stopwords unchanged)
```
Pydantic reports an unknown `rule:` as `rules.<i>: Input tag 'x' found using 'rule' does not match any of the expected tags`; `_parse` already prefixes `qualification.yaml:`, satisfying D-01 "naming file and field". Extra/typo keys fail via `extra="forbid"` (loc includes the tag, e.g. `rules.2.in_area.citys`). [CITED: pydantic v2 discriminated unions; behaviour known from Pack loader tests `unknown_key`]

### Validations
Model-level (`model_validator(mode="after")` on Qualification):
- ids unique; `field` unique across rules (old code has one check per field).
- `RULE_FIELDS = {"in_list": {"service_type","property_type","budget_range"}, "yes_no": {"is_owner"}, "max_number": {"timeline_months"}, "in_area": {"address"}}`; `field` must be in `RULE_FIELDS[rule]` (this is the "field names vs LeadFields" check, and it excludes `name/phone/email`, which are core per D-04). Implement against `LeadFields.model_fields` for the existence message only if wanted; the map alone suffices.
- id must not be `name` or `phone or email` (regex already blocks the latter).
- InList on `service_type`: `values` must be a subset of `service_synonyms` keys (this replaces the old `qualifying_services <= service_synonyms` check at pack.py:239-240; the old error message wording stays acceptable, but `test_malformed_qualifying_not_in_synonyms` must be rewritten for rules).
Cross-file (in `load_pack`, where both parsed objects exist):
- `set(messages.ask) == {r.id for r in rules} | {"name", "phone or email"}` else `PackError("messages.yaml: ask: ...")` naming missing/extra keys. The `Messages._ask` validator must be relaxed to only require `{"name","phone or email"} <= set(v)` (the old exact-ASK_KEYS check becomes the load_pack check). `ASK_KEYS` constant is then deleted. `_validate_messages` templating needs no change.

### `required`
Locked by D-01; semantics (recommended, cheapest): a rule with `required: false` is skipped everywhere (verdict, missing_fields). Implementation is one filter `[r for r in rules if r.required]`; one unit test. Not exercised by roofing.

### `question` key (conflict to flag)
D-01 lists `question (ask text key or inline)`; D-05 says ask text stays in messages.yaml keyed by rule id. Recommendation: follow D-05, do NOT add `question` (it would be a second place for the same text; `extra="forbid"` then rejects it, which is a feature). Same for disqualify: stays the single `messages.disqualify` text (today's one message covers all criteria). Planner/discuss should confirm [ASSUMED: D-05 prevails over D-01 wording].

### Legacy-compat properties (enables dual-run with zero edits to old code)
```python
@property
def service_area(self): return next((r.cities for r in self.rules if isinstance(r, InArea)), ())
@property
def qualifying_services(self): return frozenset(next((r.values for r in self.rules if isinstance(r, InList) and r.field == "service_type"), ()))
@property
def max_timeline_months(self): return next((r.max for r in self.rules if isinstance(r, MaxNumber)), 0)
@property
def service_types(self): return (*self.service_synonyms, "other")   # D-09 "declared service types"
```
Old `policy.address_status/qualification` read exactly these names, so they keep working. All four are deleted in the final plan (except `service_types`).
D-09 says the pack "declares `service_types`". Today the synonyms keys already declare them (and `render()` builds the enum from them + "other"). A separate YAML list would be pure duplication; recommend the computed property above and flag as a small interpretation of D-09 [ASSUMED].

## 3. `qualify.py` design

```python
"""Data-driven qualification. Pure: no DB, no LLM. Rule order is file order."""
import re
from collections.abc import Callable
from .pack import InArea, InList, MaxNumber, Pack, YesNo
from .policy import _tokens          # one-way import; policy does not import qualify

def address_status(cities: tuple[str, ...], address: str | None) -> str:
    ...  # policy.address_status body verbatim, with pack.qualification.service_area -> cities (set(cities) computed once)

def _in_list(r, v):    return None if v is None else v in r.values
def _yes_no(r, v):     return v if v is True or v is False else None     # identity, like old `is True/False`
def _max_number(r, v): return None if v is None else v <= r.max
def _in_area(r, v):    return {"in": True, "out": False}.get(address_status(r.cities, v))

CHECKS: dict[type, Callable] = {InList: _in_list, YesNo: _yes_no, MaxNumber: _max_number, InArea: _in_area}

def _active(pack): return [r for r in pack.qualification.rules if r.required]

def qualify(pack, lead) -> str:
    results = [CHECKS[type(r)](r, lead.get(r.field)) for r in _active(pack)]
    if any(c is False for c in results): return "disqualified"
    return "qualified" if all(c is True for c in results) else "incomplete"

def _missing(r, v) -> bool:        # exact old predicate: None / "" / (address) incomplete
    return v is None or v == "" or (isinstance(r, InArea) and address_status(r.cities, v) == "incomplete")

def missing_fields(pack, lead) -> list[str]:
    out = [r.id for r in _active(pack) if _missing(r, lead.get(r.field))]
    if lead.get("name") is None or lead.get("name") == "": out.append("name")
    if not (lead.get("phone") or lead.get("email")): out.append("phone or email")
    return out

def next_question(pack, lead) -> str:
    m = missing_fields(pack, lead)
    return pack.messages.ask[m[0]] if m else pack.messages.anything_else
```
Notes for the planner:
- Order: rule ids in file order, then `name`, then `phone or email`. For roofing this equals old `[service_type, is_owner, address, timeline_months, name, phone or email]`. `name` stays core and sits after all rules; it is intentionally not interleaved.
- `_in_list` must keep "" -> False (not None) and `_missing` must keep "" -> missing, to match the old inconsistency (section 1).
- `_yes_no` must NOT use truthiness (`0`/`1` stay unknown).
- Three-valued results are plain `True/False/None`; no enum needed.
- Loader guarantees every `type(rule)` is in `CHECKS` only if the union and dict stay in sync: add a test `set(get_args(Rule union)) == set(CHECKS)`.
- Call sites: `agent.py` lines 84 and 119, `evals/runner.py:97` switch to `qualify.qualify/next_question`; `policy.has_contact` stays. No wrapper functions in policy (deviation from D-06's "delegates", simpler; confirm) [ASSUMED]. Keep `policy.address_status` etc. until the final plan.
- Quirk preserved: `address_status` single-part branch uses `_tokens` (`[a-z0-9]+`); policy keeps `_tokens` because `is_grounded` needs it, so qualify imports it (do not copy).

## 4. Differential test design

Location: `api/app/test_qualify_diff.py` (new). Old oracle = `policy.qualification/missing_fields/next_question/address_status` on the loaded `roofing_pack` (the compat properties make them work). Run in the container (`make` equivalent: `docker compose exec api python -m pytest -q app/test_qualify_diff.py`).

### Lead grid (fast: about 50k leads, pure functions)
| Dimension | Values |
|---|---|
| service_type | `"repair","replacement","inspection","other", None` plus edge `"", "plumbing", "Repair"` |
| is_owner | `True, False, None` plus edge `0, 1` |
| timeline_months | `None, 0, 1, 5, 6, 7, 24` plus edge `-1` |
| address | curated list below (+ None) |
| name | `None, "", "Sam"` |
| contact (phone,email) | `(None,None), ("303-555-0100",None), (None,"a@b.co"), ("","")` |
Use two product tiers to keep it fast: main grid = core values x all addresses x name x contact (about 5*3*7*50*3*4 = 63k); edge values crossed with 5 representative addresses only. Comparisons per lead: `qualify.qualify == policy.qualification`, `qualify.missing_fields == policy.missing_fields`, `qualify.next_question == policy.next_question`. Collect mismatches in a list and `assert not diffs, diffs[:10]` (zero differences is the pass criterion). Also assert `address_status` equality on curated + fuzz strings directly.

### Curated addresses (current old-code result, generated by running `policy.address_status`)
```
None, "", "   "                                  -> incomplete
"Denver"                                         -> incomplete   (no digit)
"123 Main St"                                    -> incomplete
"123 Main St, Denver"                            -> in
"123 main st, DENVER"                            -> in
"123 Main St, Denver CO"                         -> in
"123 Main St, Denver, CO"                        -> in
"123 Main St, Denver, CO 80202"                  -> in
"123 Main St, Denver CO 80202-1234"              -> in
"123 Main St Denver CO 80202"                    -> in
"1 Oak St Denver"                                -> in
"12 Denver Ave"                                  -> in   (street named for a city, no comma)
"12 Denver Ave, Boulder"                         -> out
"12 Aurora Ave, Austin TX"                       -> out
"123 Main St, Apt 4"                             -> incomplete
"123 Main St, Apt 4, Denver"                     -> in
"123 Main St, Unit 5, Aurora CO"                 -> in
"123 Main St, Suite 100"                         -> incomplete
"123 Main St, Ste 2"                             -> incomplete
"123 Main St, Floor 3, Austin"                   -> out
"14 Congress Ave, Austin"                        -> out
"14 Congress Ave, Austin, TX 78701"              -> out
"9 Elm St, Boulder CO 80302"                     -> out
"somewhere in Denver"                            -> incomplete
"Denver, 12 Oak"                                 -> incomplete
"12 Oak St,"                                     -> incomplete
"12 Oak St, ,Denver"                             -> in
"12 Oak St , Denver"                             -> in
"12 Oak St,Denver"                               -> in
"12 Oak St, CO 80202"                            -> incomplete
"12 Oak St, CO"                                  -> incomplete
"12 Oak St, 80202"                               -> incomplete
"12 Oak St, St. Louis"                           -> out
"12 Oak St, Fort Collins CO"                     -> out
"12 Oak St, Littleton, Colorado"                 -> in
"12 O'Brien Ln, Arvada"                          -> in
"12 Oak St, Lakewood Colorado 80226"             -> in
"12 Oak St, Centennial."                         -> in
"12 Oak St, Denver-Aurora"                       -> in
"12 Oak St, ño Denver"                           -> in
"12 Oak St, Lo"                                  -> incomplete
"12 Oak St, LA"                                  -> incomplete
"12 Oak St, Ft. Worth TX"                        -> out
"Apt 4, Denver"                                  -> in
"12 Oak St, Highlands Ranch CO 80126"            -> out
"12 Oak St; Denver"                              -> in
"12 Oak St, Denver 80202, CO"                    -> in
"12 Oak St, West Denver"                         -> in
"12 Oak St, Denverton"                           -> out
```
(Existing `test_policy` also covers `"5 Main St, Austin"`, `"12 Denver Ave, Boulder"`.) The expected column is documentation; the test compares new vs old, and the frozen digest (below) pins results after deletion.

### Deterministic fuzz (fixed seed, no hypothesis)
`rng = random.Random(20261103)`; generate 5,000 composed strings by joining random picks from pools: number (`"", "12", "4B", "1600"`), street word (`"Oak St","Main Street","Denver Ave","O'Brien Ln","St. Paul Rd"`), separator (`", ", ",", " , ", ", , ", " ", "; "`), city (6 area cities + `austin, boulder, fort collins, ño, lo, highlands ranch`), state (`"", "CO", "TX", "Colorado", "co"`), ZIP (`"", "80202", "80202-1234", "8020"`), unit (`"", "Apt 4", "Unit 5", "Suite 100", "ste 2"`), random casing; plus 5,000 raw strings from alphabet `ascii_letters + digits + ", .'-;"`, length 0-30. Assert `qualify.address_status(cities, a) == policy.address_status(pack, a)` for all. Use only `rng.randrange`/`rng.random`-derived indexing (stable across Python 3.12 patch releases; image is `python:3.12-slim`).

### Keeping the old path available
Old functions are untouched in `policy.py` and read the compat properties, so no shim, no flags. The new test imports both modules. Plan order: (1) pack models + loader + properties + YAML migration, (2) `qualify.py` + diff test, (3) switch `agent.py`/`runner.py` to `qualify` (old still present), subset eval gate, (4) freeze digest then delete old + properties + legacy tests, full gate.

### Zero-diff proof that survives deletion
Before deleting, add `api/app/tests_data/frozen_qualify.py` containing `GRID_SHA256 = "<hex>"` computed from the OLD functions over the whole grid+fuzz: `hashlib.sha256("\n".join(f"{i}|{verdict}|{missing}|{question}" ...))`. After deletion the test recomputes the same hash from `qualify.*` and asserts equality. (The tests_data convention is already "frozen oracle, never imported from product modules"; see `frozen_old.py`.) Also add the pack-parameter check mirroring `test_pack._check`: rule params equal `FROZEN_SERVICE_AREA`, `FROZEN_QUALIFYING_SERVICES`, `FROZEN_MAX_TIMELINE_MONTHS` (this is what stops the properties from making the diff test circular on parameters).

## 5. ServiceType relaxation

### Every use of the enum
| Place | Use | Change |
|---|---|---|
| `schemas.py:11-15, 27` | `ServiceType` enum; `LeadFields.service_type: ServiceType \| None` | enum removed; `service_type: str \| None = Field(None, max_length=50)` + validator |
| `pack.py:16, 103, 105` | `qualifying_services: frozenset[ServiceType]`, `service_synonyms: dict[ServiceType,str]` | `dict[str,str]`; qualifying moves to rules |
| `pack.py:248` | `render`: `s.value for s in service_synonyms` | `for s in service_synonyms` (keys are str) |
| `pack.py:290` | CLI print `s.value` | drop `.value` |
| `policy.py:47, 122` | membership; `service_synonyms[value]` | membership unchanged (str in frozenset[str]); line 122 gets KeyError on an unknown string -> use `.get(value)` guard or rely on parse-time check (see below) |
| `agent.py:162, 187, 207-212` | `_KNOWN_KEYS`; `need=lead["service_type"]` (already a DB str) | none |
| `agent.py:191-195` `_parse` | `Turn.model_validate(...)` | pass `context` (below) |
| `tools.py:97` `update_lead` | `LeadFields.model_validate(fields)` | none; no context -> no pack check (fields already parse-validated and grounded) |
| `db/init.sql:6` | `service_type TEXT` | none |
| `prompts/agent.v2.md:19` | `{{service_enum}}` | none (D-10); `agent.v1.md:23` is a legacy file with a literal enum, unused (`PROMPT = "agent.v2"`) |
| tests | `test_pack.py:165-166` `k.value`; `test_pack.py:250-251` render; `test_pack.py` MIN_PACK keys; `test_policy.py` GOOD etc. use plain strings | edit `.value` uses; rest unchanged |
| evals | `injection.yaml:23` payload string only; no scenario references the enum | none |
`ServiceType` has no JSON-schema consumer (the prompt schema is hand-written text).

### What an invalid-enum model output does TODAY (trace)
1. `_ask_llm` loop (2 attempts): `llm.chat` -> `_parse(raw)` -> `Turn.model_validate(json)` -> `LeadFields` rejects e.g. `"plumbing"`, `"Repair"`, `"repair "`, 5 (enum is exact-match, case-sensitive). Blank-like strings (`""`, `"null"`, `"none"`, `"unknown"`, `"n/a"`) pass through `blank_to_none` -> None (valid). `extra="forbid"` makes any other bad field fail the whole Turn too.
2. `pydantic.ValidationError` (a `ValueError`) -> `turn=None, error=str(e)[:300]`; `_log_llm(..., schema_valid=False)`; warning logged.
3. Attempt 1 failure: appends the model output plus `Invalid output ({error}). Reply with ONLY the JSON object.` and calls the LLM again.
4. If attempt 2 parses -> normal turn. If attempt 2 also fails -> `_ask_llm` returns None -> `_decide` -> `_escalate(cid, "validation_failure")` -> state ESCALATE, closed message.
No fields are stored; nothing is coerced to `other`. (D-09's phrase "normalized to `other`-equivalent handling" is inaccurate: today it is retry-then-escalate, and that is what must be preserved. Behaviour for a VALID `other` is: grounded against `non_business_pattern`, stored, qualification False.)

### Concrete plan to relax with identical behaviour
1. `schemas.py`: `service_type: str | None = Field(None, max_length=50)`; add
```python
@field_validator("service_type")
@classmethod
def pack_service(cls, v, info):
    allowed = (info.context or {}).get("service_types")
    if v is not None and allowed is not None and v not in allowed:
        raise ValueError(f"Input should be {', '.join(map(repr, allowed))}")
    return v
```
(runs after `blank_to_none`, so blank-likes still become None; `str` type already rejects non-strings in pydantic v2 lax mode, matching the enum's rejection of ints.)
2. `agent.py`: `_parse(raw, pack)`: `Turn.model_validate(json.loads(...), context={"service_types": pack.qualification.service_types})`; `_ask_llm` passes `pack`. Context propagates to nested `LeadFields`. [CITED: pydantic v2 validation context via `model_validate(context=)` and `info.context`; ASSUMED to nest through `Turn.extracted` as documented - Wave 0 test must prove it]
3. Error text sent back to the model differs slightly from the enum message ("Input should be 'repair', 'replacement', 'inspection' or 'other'"): mimic that wording to stay as close as possible; it is only LLM-visible repair text.
4. `policy.is_grounded` line 122: `pack.qualification.service_synonyms.get(value)`; if None (unknown value), return False. Unreachable from `_decide` after step 2 but removes the KeyError hazard for any other caller.
5. `pack.py`: loader types become `str`; `service_types` property (section 2).

Proof (D-09 requirement):
- Unit tests (container, no LLM): `Turn.model_validate({"extracted": {"service_type": X}}, context=...)` raises for `plumbing`, `Repair`, `"repair "`, `5`, `True`; accepts `repair`, `other`, `None`, `"unknown"`->None; same acceptance set as the old enum (parametrize against `ServiceType` kept ONLY in the test file as a frozen list `["repair","replacement","inspection","other"]`).
- Agent tests with scripted fake LLM (existing `script()` helper): (a) invalid then valid -> proceeds; two LLM calls observed, second message list ends with "Invalid output"; (b) invalid twice -> `("ESCALATE","escalated")` (extend `test_invalid_output_twice_escalates` pattern); (c) valid `other` -> same lead state as before.
- Eval subset gate: qual-1..qual-12 plus disq-service, disq-solar (the two scenarios where the model emits `other`) after the change; compare with baseline per-scenario pass/fail.
Fallback (D-09): if any unremovable difference appears, keep `ServiceType` enum in roofing path, still land the interpreter (the properties/rules do not depend on it), and defer relaxation to Phase 5. The interpreter plans must therefore not depend on relaxation: do the relaxation as its own plan AFTER the diff test is green, so it can be dropped alone.

## 6. Test impact and risks

### Call sites / tests to update
- `test_pack.py`: `MIN_PACK["qualification"]` -> replace three keys with `rules` (and keep `service_synonyms`), `ask` keys must equal rule ids + name + phone or email; CASES `missing_field` (pops `max_timeline_months`) -> pop `rules`; `service_area_not_lower` -> mutate `rules[i].cities`; `test_malformed_qualifying_not_in_synonyms` -> in_list values not in synonyms; `ask_missing_key` still fails (name); `_check` (lines 160-166) -> read params from rules and drop `.value`; `test_render_service_enum`. Add cases: unknown rule type, wrong field for rule, duplicate id, ask key missing for a rule id, ask key not matching any rule, empty rules.
- `test_policy.py`: stays untouched through the dual run (old functions); in the final plan the qualification/address tests re-point to `qualify.*` (or are deleted where the digest test supersedes them).
- `test_agent.py`, `test_tenancy.py`: scripted turns use plain strings, no change; they exercise `qualify` through `_decide`.
- `evals/runner.py:97` -> `qualify.qualify`.
- New: `test_qualify.py` (unit: each rule type incl. required=false, three-valued results, ordering, loader errors), `test_qualify_diff.py`, grounding-edit tests (D-11: write a tmp pack with changed `service_synonyms`/`non_business_pattern`, assert `is_grounded` changes with no code change), a "edit rule/ask text changes behaviour" test (modify `max` or `ask.address` in a tmp pack, assert verdict/question change) for success criterion 1.
- Tenant pack cache is keyed by pack hash so YAML edits are picked up automatically.

### Pitfalls
1. **Circular proof:** compat properties make old and new read the same params; guard with the frozen-constants check (section 4).
2. **`""` and non-bool `is_owner` inconsistencies** (section 1) are easy to "clean up" accidentally; the edge grid exists to catch it.
3. **`Messages._ask` exact-key validator** blocks any pack whose rule ids differ from the roofing set; move to `load_pack` and update MIN_PACK or ALL pack tests fail at once.
4. **KeyError in grounding** for unknown strings once the enum is gone (section 5 step 4).
5. **Pydantic context not propagated** (or `update_lead` called with no context silently accepts anything): acceptable by design, but test it.
6. **Eval is LLM-nondeterministic:** a 94/96 flake is not a regression signal for qualification logic; the diff digest is the deterministic proof, the eval gate is the integration check (baseline has 2 known failures; compare against `evals/baselines/v1-roofing.json`).
7. **`policy._tokens` private import** from qualify; fine, but do not delete it with the old path (grounding uses it).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (in the `api` container, real Postgres for agent tests) |
| Config file | none beyond `api/app/conftest.py` |
| Quick run | `docker compose exec api python -m pytest -q app/test_qualify.py app/test_qualify_diff.py app/test_pack.py app/test_policy.py` (use the project's `GCOMPOSE` wrapper / `make test ARGS=...` for the roofdesk-global stack) |
| Full suite | `make test` (see Makefile line 10/28) |
| Eval subset | explicit `docker compose exec -e LLM_TIMEOUT_S=300 api python -m evals.runner` limited to qual-1..12 + disqualified ids (D-12) |

### Phase Requirements -> Test Map
| Req | Behavior | Type | Command | File exists? |
|-----|----------|------|---------|--------------|
| QUAL-01 | rule models, loader errors, interpreter semantics, editing a rule/question changes behaviour | unit | `pytest app/test_qualify.py app/test_pack.py` | Wave 0 (new) / update |
| QUAL-02 | editing synonyms / non-business pattern changes grounding | unit | `pytest app/test_pack.py -k grounding` | Wave 0 |
| QUAL-03 | zero diff old vs new over grid + fuzz; frozen digest after deletion | unit (about 70k leads, seconds) | `pytest app/test_qualify_diff.py` | Wave 0 |
| D-09 | invalid service output retry/escalate unchanged | unit with fake LLM | `pytest app/test_agent.py -k service` | Wave 0 |
| Success 4 | roofing eval matches baseline after deletion | eval | full gate, 94/96 same two failures | existing |

### Sampling Rate
- Per task commit: quick run above. Per wave: full pytest. Phase gate: full pytest + full eval gate before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `api/app/test_qualify.py`, `api/app/test_qualify_diff.py`, `api/app/tests_data/frozen_qualify.py` (digest, generated before deletion)
- [ ] MIN_PACK and CASES rewrite in `test_pack.py`
- [ ] context-propagation test for `LeadFields` inside `Turn`

## Security Domain

Applicable ASVS: V5 Input Validation only. Pack YAML loads with `yaml.safe_load` (existing), `extra="forbid"`; regexes in pack are compiled/validated at load (existing); rule `field` is restricted to a fixed map so it can never become a column or attribute name from pack data (note `update_lead` builds SQL column names from `LeadFields` keys, not rules, unchanged). Model output (`service_type`) is validated against the pack list at the trust boundary. No new secrets, auth, or network surface. Threat: pack-supplied ids reaching `messages.ask[...]` -> mitigated by the load-time key equality check (no KeyError at chat time).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | D-05 (ask text in messages.yaml by id) prevails over D-01's `question` key; no `question` key added | 2 | Planner adds an unused key or user wanted inline questions |
| A2 | `service_types` as computed property (synonyms keys + `other`) satisfies D-09 "declares" | 2, 5 | User wanted an explicit YAML list |
| A3 | Calling `qualify.*` directly (no policy wrappers) satisfies D-06 | 3 | User wants policy to remain the facade |
| A4 | Pydantic `context` propagates into nested `LeadFields` under `Turn` | 5 | Need to validate in `_parse` after model_validate instead (same retry path) |
| A5 | `required: false` = rule skipped entirely | 2 | Different intended semantics; roofing unaffected |

## Open Questions
1. Do we want `required:false` at all now (D-01 says yes; no consumer)? Recommend implement the filter and one test, nothing more.
2. Eval ids for the subset gate: confirm names of "disqualified ids" (`disq-*`, ten scenarios) vs qual-1..12; the gate command lives in the Phase 3 summary/verification.

## Sources
- Repo (read in full): `api/app/policy.py`, `pack.py`, `schemas.py`, `agent.py`, `tools.py` (update_lead), `businesses/summit-roofing/{qualification,messages,pack}.yaml`, `api/app/test_policy.py`, `test_pack.py`, `test_agent.py`, `conftest.py`, `evals/scenarios/{qualified,disqualified}.yaml`, `evals/runner.py`, `prompts/agent.v2.md`, `api/app/tests_data/frozen_old.py`, `.planning/phases/04-rule-interpreter/04-CONTEXT.md`, Makefile.
- Address table: produced by executing the old `address_status` against the roofing city list (this session).
- `.planning/research/*.md` were not re-read in full (CLAUDE.md embeds STACK.md conclusions: dispatch dict, Pydantic union, no new library).
- Pydantic v2 discriminated-union and validation-context behaviour: training knowledge, not re-fetched [ASSUMED] (A4 gates on a test).

## Metadata
**Confidence:** Semantics HIGH (source + executed); schema/design HIGH; relaxation MEDIUM (context propagation unverified until tested).
**Research date:** 2026-11-03 **Valid until:** until policy.py/pack.py change.
