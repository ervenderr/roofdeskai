---
phase: 03-pack-loader-and-roofing-extraction
plan: 04
subsystem: policy
tags: [policy, pack, escalation, triage]
requires: [03-03]
provides: [pack-parameterised policy, _ESCALATION_ORDER]
key-files:
  modified: [api/app/policy.py, api/app/agent.py, api/app/faq.py, api/app/triage.py, evals/runner.py, api/app/test_pack.py, api/app/test_policy.py, api/app/test_triage.py, api/app/test_agent.py]
metrics:
  completed: 2026-11-03
---

# Phase 3 Plan 04: Policy reads the pack Summary

Policy, agent, faq, triage and the eval runner no longer hold any business constant; qualification, grounding, next question and stopwords read the pack with results identical to the frozen old values.

## Commits
- 5ebb152 test: pack-driven policy equivalence, cache isolation, no-globals and closed-state safety escalation
- b2eaa72 refactor: policy, agent, faq, triage and eval runner read business values from the pack

## Verification
- RED: new tests failed (TypeError unexpected `pack` kwarg, no-pack safety assertion, missing signatures, no_globals on policy.py/faq.py).
- `make g-test`: 389 passed.
- Grep gate (`summit|roof([^d]|$)|denver` over policy/agent/tools/faq/admin) and old-constant grep: both empty.
- Eval subset (qual-1, qual-2, esc-safety, esc-legal, esc-angry, faq-1, faq-2, slot-none, ooo-1; local, LLM_TIMEOUT_S=300): GATE PASSED, regressions [].

## Decisions
- `escalation_reason(message, only=None, pack=None)`: generic patterns in code, safety merged only with a pack, order human_request, legal, safety, angry. `_decide` passes `pack=pack` (closed states keep only=("safety","legal")); a test drives DONE and DISQUALIFY conversations with a safety message.
- `/triage` passes the default tenant's pack to both policy calls.
- Core `_GENERIC` lost roof/roofing/summit; they live in `qualification.extra_stopwords`.

## Deviations from Plan
- Docstring example "Denver" in `address_status` reworded to a non-business city so the no_globals scan passes.
- Removed `test_golden_live` and `_live()` (old constants deleted); frozen golden stays.
- Pre-existing duplicate `from app.config import settings` in evals/runner.py left alone.

## Known Stubs
None.

## Self-Check: PASSED
