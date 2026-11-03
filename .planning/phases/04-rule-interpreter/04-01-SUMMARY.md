---
phase: 04-rule-interpreter
plan: 01
subsystem: qualification
tags: [pydantic, rules, pack-loader]
requires: [03-pack-loader-and-roofing-extraction]
provides: [Qualification.rules, Rule union, load_pack ask-key check, compat properties]
affects: [api/app/pack.py, api/app/test_pack.py, businesses/summit-roofing/qualification.yaml]
key-files:
  modified: [api/app/pack.py, api/app/test_pack.py, businesses/summit-roofing/qualification.yaml]
decisions:
  - "A1: no `question` key on rules; ask text stays in messages.yaml keyed by rule id (D-05 over D-01 wording); extra=forbid rejects `question`"
  - "A2: service_types not added in this plan (relaxation is plan 04); D-09 wording deferred"
  - "A5: required:false means rule skipped (interpreter honours it in plan 02); loader only accepts it"
metrics:
  tasks: 3
  tests: "401 passed"
---

# Phase 4 Plan 01: Rules schema and roofing YAML migration Summary

Roofing qualification is now four ordered rules (in_list, yes_no, in_area, max_number) in a Pydantic discriminated union, validated at load; the old policy.py path still works through read-only compat properties.

## Commits
- 75767d2 test: pack tests for data-driven qualification rules (red)
- 4c492ab feat: rules schema, loader checks and roofing qualification rules

## Red run
Before pack.py changed, `make g-test ARGS="app/test_pack.py -q"` showed 24 failures, all from the old schema (`qualification.yaml: service_area: Field required`, missing `rules`), not ImportError/SyntaxError.

## Green
`make g-test`: 401 passed. `python -m app.pack summit-roofing` exit 0. test_policy.py, messages.yaml, baselines untouched.

## Deviations from Plan
- **A1 (D-01 wording):** no `question` field on rules; asks stay in messages.yaml by rule id (D-05). Tested via `rule_question_key` case.
- **A5 (D-01 `required`):** `required: false` loads; skipping semantics live in plan 02 interpreter.
- **A2/A3 (D-09/D-06 wording):** `service_types` property not added here; no policy wrappers planned (qualify.* called directly in plan 03). Out of scope for this plan.
- Model-level validator errors (duplicate id/field, wrong field, in_list not in synonyms) are prefixed `rules: ` because pydantic gives empty loc for them (plan-checker note).
- `qualifying_services` compat property returns `frozenset[ServiceType]` (not str) so the old `policy.qualification` membership test keeps working while ServiceType remains an enum.
- No other tests needed edits in Task 3.

## Known Stubs
None.

## Self-Check: PASSED
Commits 75767d2 and 4c492ab exist; changed files only pack.py, test_pack.py, qualification.yaml.
