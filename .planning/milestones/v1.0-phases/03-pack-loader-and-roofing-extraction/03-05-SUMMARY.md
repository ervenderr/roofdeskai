---
phase: 03-pack-loader-and-roofing-extraction
plan: 05
subsystem: verification
tags: [gate, eval, pytest]
requires: [03-04]
provides: [phase 3 proof]
key-files:
  modified: []
metrics:
  completed: 2026-11-03
---

# Phase 3 Plan 05: Phase gate Summary

Phase 3 proven: full pytest green, no business words in core files, pack CLI ok, and the local-only eval gate holds at baseline (94/96, same two failures, no regressions). No product code changed.

## Evidence
- `pytest -q` in branch api container: 389 passed.
- Grep gate `summit|roof([^d]|$)|denver` over policy/agent/tools/faq/admin: empty.
- `python -m app.pack summit-roofing`: exit 0 (hash b1cd84986bea, 3 services, 12 faq, Etc/UTC 9/11/14/16, 60min, 14d).
- `test_pack.py`: 45 tests, groups for malformed, golden_frozen, render, messages, slots, escalation, cache, no_globals.
- `evals/baselines/` unchanged since freeze (last commits 34af1b2, de64fd9).
- Gate (`LLM_TIMEOUT_S=300`, local llama3.1:8b warmed, keep_alive 6h): exit 0, `GATE PASSED`.
  - Git SHA 58d4264, Prompt agent.v2, Models: local:llama3.1:8b
  - Overall 94/96; booking validity 100%; escalation 11/11 and 11/11; schema validity 95% over 232 calls; p50/p95 7.9s/10.3s
  - Failures: voice-over-explainer, voice-indecisive (only)
  - improvements [], new [], flaky-pass [], regressions []

## Flags
- Root Dockerfile now has `COPY businesses businesses`; any deploy requires it. Never deployed from this branch.
- tzdata pinned in api/requirements.txt (`tzdata==2026.6`, per 03-01).
- Demo disclaimer stays core per D-10.
- Roofing calendar timezone is Etc/UTC (legacy quirk); Denver correction is a later, deliberate behaviour change.

## Deviations from Plan
None. Pre-existing dirty files left unstaged.

## Self-Check: PASSED
