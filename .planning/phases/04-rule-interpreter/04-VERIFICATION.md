---
phase: 04-rule-interpreter
verified: 2026-11-04T00:00:00Z
status: passed
score: 4/4 success criteria, 3/3 requirements
---

# Phase 4: Rule Interpreter Verification Report

**Goal:** Qualification is driven by `qualification.yaml` and demonstrably gives the same answers as the old code.
**Status:** passed (two non-blocking follow-ups below)

## Success criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Editing question, disqualify text or rule changes behaviour with no code change | VERIFIED | `qualify.py` (68 lines) dispatches `CHECKS: dict[type, Callable]` over InList/YesNo/MaxNumber/InArea; rules read from `pack.qualification.rules` in file order. `test_qualify.py`: `test_edit_rule_changes_verdict`, `test_edit_cities_changes_verdict`, `test_remove_rule`, `test_edit_question_and_order_change_next_question`, `test_edit_disqualify_text` all pass. |
| 2 | Synonyms and non-business list come from the pack | VERIFIED | `qualification.yaml` holds `service_synonyms`, `non_business_pattern`, owner patterns, `extra_stopwords`; `policy.py` reads `pack.qualification.*` (lines 73-126). `test_edit_synonyms_changes_grounding`, `test_edit_non_business_pattern_changes_grounding` pass. |
| 3 | Differential test over large grid, zero differences | VERIFIED | Dual-run diff done in 04-02; old path was then frozen to digests. `test_qualify_diff.py::test_frozen_digest_new` compares interpreter output (verdict, missing, next question over 84,720 leads; address status over 10,052 addresses) to `frozen_qualify.py` SHA256s. `test_grid_not_shrunk` pins the counts. `test_rule_params_frozen` pins cities/services/max. |
| 4 | After old path deleted, roofing eval matches baseline | VERIFIED (by artifact) | `gate.txt`: 94 PASS, 2 FAIL (voice-over-explainer, voice-indecisive, same as baseline), regressions [], new [], flaky [], "GATE PASSED", exit=0. `evals/reports/latest.md`: 94/96, git SHA 28fb575 (the delete commit), booking validity 100%, escalation 11/11 and 11/11, local model only. Not re-run by me. |

## Requirements

| Req | Status | Evidence |
|-----|--------|----------|
| QUAL-01 | SATISFIED | Interpreter + pack-defined questions (`messages.ask`) and disqualify text (`messages.disqualify`); loader rejects duplicate id/field, reserved `name`, unknown rule fields, values not in synonyms (`pack.py` 160-175); rule union is discriminated on `rule`. |
| QUAL-02 | SATISFIED | See criterion 2. Service enum removed: `schemas.py` has `service_type: str`, validated against pack via validation context (`pack_service`); `ServiceType` has no remaining references. |
| QUAL-03 | SATISFIED | See criterion 3. |

## Other checks

- Old `qualification`, `address_status`, `missing_fields`, `next_question` are absent from `policy.py`; no remaining `policy.<old>` references in `api` or `evals`. `agent.py` (lines 84, 119) and `evals/runner.py` (line 97) use `qualify.*`.
- Invalid service_type: `test_invalid_then_valid_retries_once`, `test_invalid_twice_escalates_and_stores_nothing` (state ESCALATE, reason validation_failure, nothing stored), `test_valid_other_is_stored_and_disqualifies` pass.
- `make g-test`: **441 passed, 1 warning (third-party DeprecationWarning), 7.76s**.
- Debt markers (TBD/FIXME/XXX) not scanned beyond phase files read; none seen.

## Assessments

1. **Deleted `test_agent_uses_qualify_not_policy`: no meaningful guard lost.** It monkeypatched the old `policy` functions to raise. Those functions no longer exist, so any call would raise AttributeError. Its end-to-end assertions (book path, rent -> DISQUALIFY) are covered by the remaining agent tests and the eval gate. Residual: nothing stops someone re-adding a parallel policy path, but the frozen digests would catch behavioural drift.
2. **Hardcoded "6 months" in the disqualify text: acceptable gap, log as follow-up.** Editing `max_number.max` changes the verdict but not the sentence. The text is pack data, so the pack author owns keeping them consistent; criterion 1 is met. Cheap fix for a later phase: a `{max}` placeholder or a loader check that warns when text and rule disagree.
3. **`test_service_type.py` is adequate.** It covers context propagation into nested LeadFields, old enum values accepted, blank-likes to None, arbitrary values rejected, retry once, double failure to ESCALATE with nothing stored, and `other`. This is deterministic and covers the invalid path the eval subset barely touches. Gap: it only uses "plumbing" as the invalid value in the agent-level tests; the unit test covers other values.

## Follow-ups (non-blocking)

- Disqualify text vs `max_number` consistency (item 2).
- The gate run was read from `gate.txt`, not re-executed.
