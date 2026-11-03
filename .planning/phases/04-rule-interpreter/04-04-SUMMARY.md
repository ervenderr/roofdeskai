---
phase: 04-rule-interpreter
plan: 04
subsystem: qualification
tags: [service-type, pydantic-context, subset-gate]
requires: [04-03]
provides: [service_type validated against pack.qualification.service_types; ServiceType enum removed]
key-files:
  created: [api/app/test_service_type.py]
  modified: [api/app/schemas.py, api/app/pack.py, api/app/agent.py, api/app/policy.py, api/app/test_pack.py]
metrics:
  tests: "443 passed"
---

# Phase 4 Plan 04: ServiceType relaxation Summary

`LeadFields.service_type` is now `str | None` validated against the pack's `service_types` (synonym keys + "other") via Pydantic validation context passed by `agent._parse`. Invalid values keep the old path: one repair retry, then ESCALATE validation_failure, nothing stored. Relaxation kept (not reverted).

## Commits
- e9fc8de test: service_type from pack with retry/escalate on invalid (red)
- aa78221 refactor: service_type validated against the pack, enum removed

## Red run
`make g-test ARGS="app/test_service_type.py -q"`: 3 failed (context test, `service_types` property AttributeError, `is_grounded` `KeyError: 'plumbing'`). The accept/reject and retry/escalate tests already passed against the enum, as intended: they pin the behaviour the relaxation must preserve.

## Green
`make g-test`: 443 passed. `python -m app.pack summit-roofing` exit 0. `git diff prompts/` and `git diff evals/baselines/` empty.

## Wave 0 (A4)
Context DOES reach the nested LeadFields inside Turn. The `_parse` fallback was not needed.

## Subset gate (local-only, llama3.1:8b warmed, git sha aa78221)
22/22 passed (qualified 12/12, disqualified 10/10), booking validity 100%, schema validity 100% over 72 LLM calls. improvements [], new [], flaky-pass [], regressions []. GATE PASSED, exit 0.

Caveat: the eval subset barely exercises invalid service values. The real proof of the relaxation is `test_service_type.py` (accept/reject set vs the frozen enum list, context propagation, retry-then-valid with exactly two LLM calls, invalid-twice escalation with `validation_failure` and nothing stored, valid "other" stored and disqualified).

## Deviations
- 04-01's `qualifying_services` compat property returned `frozenset[ServiceType]`; now `frozenset[str]` (str-enum and str hash/compare equal, so `policy.qualification` is unchanged).
- `tools.update_lead` left context-free by design (T-04-12 accepted).

## Known Stubs
None.

## Self-Check: PASSED
Commits e9fc8de and aa78221 exist; no `ServiceType` references remain in api/ or evals/ code.
