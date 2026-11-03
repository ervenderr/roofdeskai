---
phase: 03-pack-loader-and-roofing-extraction
plan: 02
subsystem: prompts-faq
tags: [prompt-template, render, faq-seed, tenancy]
requires: [03-01]
provides: [pack.render, templated prompts, pack-driven seed_faq, per-turn get_pack in handle_turn]
affects: [03-03, 03-04]
key-files:
  modified: [api/app/pack.py, api/app/test_pack.py, prompts/agent.v2.md, prompts/faq-answer.v1.md, api/app/agent.py, api/app/faq.py, api/app/main.py, api/app/test_tenancy.py, api/app/test_logging_tenant.py]
metrics:
  completed: 2026-11-03
---

# Phase 3 Plan 02: Templated prompts and pack-driven FAQ Summary

Prompts use `{{business}} {{kind}} {{offer}} {{service_enum}}` filled by `pack.render()` (plain replace, PackError on leftover `{{`); roofing renders byte-identical to the frozen literals. `seed_faq` reads `get_pack(t).faq`; `handle_turn` resolves the pack once per turn (inside the `try`, after `_open`) and threads it to `_decide`, `_answer`, `_faq_answer`, `_ask_llm`.

## Commits
- ee68db5 feat: prompt render() with placeholder validation and render tests
- 35f0879 feat: templated prompts, pack-driven FAQ seeding, per-turn pack resolution

## Verification
- Prompt diff: agent.v2.md lines 3 and 19, faq-answer.v1.md line 3 only; version headers unchanged.
- `make g-test`: 310 passed.
- Eval subset (qual-1,qual-2,faq-1,faq-2,esc-safety,esc-legal,ooo-1, local llama3.1:8b, LLM_TIMEOUT_S=300): 7/7, GATE PASSED, no regressions.

## Deviations
- [Rule 3] Test fixtures for tenants test-b3 and test-b4 used `ON CONFLICT DO NOTHING`, so rows left over in the dev DB kept `pack_slug` NULL; changed to `ON CONFLICT (id) DO UPDATE SET pack_slug = EXCLUDED.pack_slug`.
- TDD note: the render byte-identity tests passed immediately after Task 1 (prompts had no placeholders yet, so render was identity); they became meaningful once the prompts were edited (container confirmed to see `{{`). The RED proof shown for Task 1 was the ImportError on `render`. `test_handle_turn_missing_pack` and `test_seed_faq_from_pack` were written alongside the wiring, not shown red separately.
- Old `faq.FAQ` constant left in place (golden live test still uses it); removed in 03-03/04.

## Known Stubs
None.

## Self-Check: PASSED
Commits ee68db5 and 35f0879 present; files verified via git.
