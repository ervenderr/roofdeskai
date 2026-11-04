---
phase: 04-rule-interpreter
plan: 03
subsystem: qualification
tags: [call-site-switch, subset-gate]
requires: [04-02]
provides: [agent and eval runner qualify via qualify.py]
key-files:
  modified: [api/app/agent.py, evals/runner.py, api/app/test_agent.py]
metrics:
  tests: "422 passed"
---

# Phase 4 Plan 03: Switch call sites Summary

`agent._decide` and the runner's invalid_booking check now call `qualify.qualify` / `qualify.next_question`; policy.py old functions are untouched (oracle until plan 05).

## Commits
- 77fb092 test: agent path must use qualify not policy (red)
- 0c08040 refactor: agent and eval runner qualify through the interpreter

## Red run
`test_agent_uses_qualify_not_policy` failed with `AssertionError: old path called` at `agent.py: verdict = policy.qualification(pack, lead)`.

## Green
`make g-test`: 422 passed.

## Subset gate (local-only, git sha 0c08040)
Models: local:llama3.1:8b. 22/22 passed (qualified 12/12, disqualified 10/10), booking validity 100%, schema validity 100% over 72 LLM calls. improvements [], new [], flaky-pass [], regressions []. GATE PASSED, exit 0. No baseline changes.

## Deviations
- runner.py no longer needs `policy`, so its import was replaced with `qualify` (not just added).

## Known Stubs
None.

## Self-Check: PASSED
