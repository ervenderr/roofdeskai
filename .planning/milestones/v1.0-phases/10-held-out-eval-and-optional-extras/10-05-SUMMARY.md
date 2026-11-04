---
phase: 10-held-out-eval-and-optional-extras
plan: 05
subsystem: llm
tags: [anthropic, providers, evals]
requirements: [EXT-01]
key-files:
  modified: [api/app/config.py, api/app/llm.py, api/app/test_llm.py, evals/runner.py, api/app/test_eval_gate.py, docker-compose.yml, .env.example, README.md]
metrics:
  completed: 2026-11-04
---

# Phase 10 Plan 05: Anthropic optional provider (code only) Summary

Optional Anthropic provider via the openai SDK: appended last in PROVIDERS, skipped without a key, temperature omitted, loud `ProviderRejected` on 400, `llm.pinned()` ContextVar, and `--providers anthropic` runner flag with preflight and prefix guard. Fake-client tests only; no real call made.

## Commits
- bf61aea feat: optional anthropic provider with strict rejection and scorecard pin
- feat: runner providers flag for pinned scorecard runs (second commit, see git log)

## Verification
- `make g-test`: 1264 passed. `make check-shared`: OK (11 allowlisted files, runner count unchanged). `make check-n8n`: 31 passed.
- No `sk-ant` strings outside markdown; pack files, prompts, evals/heldout untouched.

## Deviations
None of substance. `--providers` uses `choices=["anthropic"]` only. `assert_local_only` is now a thin wrapper over `assert_only_provider(..., "local:")`; its abort message text changed slightly. Compose has no env_file, so the two vars were added to the api service environment explicitly.

## User action
Real run (needs key and cost approval): set `ANTHROPIC_API_KEY` in `.env`, then `make g-eval ARGS="--pack <slug> --providers anthropic"`. README says "not yet run".
Risk: setting the key in production makes Anthropic a live fallback (documented in README).

## Self-Check: PASSED
