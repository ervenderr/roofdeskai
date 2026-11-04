---
phase: 07-engine-modules-and-connectors
plan: 03
subsystem: quote
tags: [quote, decimal, drafts, services-yaml, text-validation]
requires: [07-01, 07-02]
provides: [Services pack model + Pack.services, engine.quote.build_quote, engine.quote_text.check_quote_text, POST /quotes, settings.module_llm_rate_per_min]
affects: [07-06 (reuses _chat/rate-limit pattern), 07-08 (quote evals)]
key-files:
  created: [api/app/engine/quote.py, api/app/engine/quote_text.py, api/app/quotes.py, api/app/test_quote.py, api/app/test_quotes_api.py, api/app/tests_data/packs/demo-venue/services.yaml, prompts/quote-extract.v1.md, prompts/quote-email.v1.md]
  modified: [api/app/pack.py, api/app/config.py, api/app/main.py, api/app/conftest.py, api/app/test_pack_modules.py]
requirements-completed: [MOD-01, MOD-02]
metrics: {tasks: 2, commits: [6e6ebe5, 93845db]}
---

# Phase 7 Plan 03: Quote builder and quote drafts Summary

Pure Decimal quote builder over `services.yaml`, a deterministic check that model-written quote email text only contains computed amounts, and `POST /quotes` that stores the result as a pending / needs_human draft (never sent).

## Commits
- 6e6ebe5 `feat: services pack model, quote builder and quote text check` (Task 1)
- 93845db `feat: quote builder, quote drafts and text validation` (Task 2)

## Rounding (refines D-04)
Each derived percent line (group discount, percent surcharge) is quantized at creation with `ROUND_HALF_UP` to 0.01; `total = sum(lines)` (already 2 dp, no further rounding). Recorded in the `build_quote` docstring. Test: 10% of 33.35 = 3.335 -> 3.34, total 30.01. Discount is quantized positive then negated. Corporate percent surcharge base = service + add-ons + discount line.

## Verification (real output)
- RED 1: `app/test_quote.py` -> `ModuleNotFoundError: No module named 'app.engine.quote'`.
- Task 1: `make g-test ARGS="app/test_quote.py app/test_pack_modules.py -q"` -> all dots, no failures (roofing/dental pin and new `.services is None` assertions green).
- RED 2: `app/test_quotes_api.py` failed on 404 (route absent).
- Task 2: `app/test_quotes_api.py` -> `...................` (19 passed).
- Full `make g-test`: `750 passed, 1 warning in 16.59s`.
- After the run the dev DB tenants are `summit-roofing`, `bright-smile-dental` only; `select count(*) from drafts` = 0.

## Decisions / interpretations
- Add-ons: `flat` once, any other unit scales with service qty; repeated add-on ids are charged once.
- Group discount applies to the service line only; highest tier with min_qty <= qty.
- `rule_unevaluable(customer_type)` only when the service has a surcharge rule and customer_type is missing or not consumer/corporate.
- Text check: an amount is a number next to a currency marker, a `per person|per hour|each|pp` suffix, or a bare number with exactly two decimals; dd.mm.yyyy dates are not amounts (lookaround in the number regex); plain integers are not checked. Total must appear as any number token. `%` figures must be in the service's rule percents. Foreign currency markers (USD/EUR/GBP/$ etc. vs pack currency) fail.
- `POST /quotes` with both `request` and `email_text`: `request` wins, email_text ignored. Email path stores `customer_email` in the draft payload (tenant-scoped; never logged).
- Email generation prompt receives code-formatted figures only (no customer text); extraction prompt delimits the email in `<email>` and only validated fields survive; `qty` must have its digits in the email.
- Rate limit: `ratelimit.allow(key=tenant_id, limit=module_llm_rate_per_min=30)` before every LLM call; structured/NeedsHuman requests that make no LLM call are not limited. A 429 or 502 creates no draft.
- Response = the stored draft row plus `deduped`.

## Deviations from Plan
- [Rule 3 - Blocking] `conftest.py` cleanup now also deletes `agent_events` for the `demo-venue` fixture tenant (inside the existing trigger-disabled block). Draft creation writes `draft_created` events, which otherwise pinned the demo-venue tenant row in the dev DB (the API startup PackError issue 07-02 fixed). Not in the plan's file list.
- Task 1 and Task 2 are two commits (as the plan implies); tests and implementation share each commit, RED runs done before implementing.
- Test fixture `h` deletes the venue tenant's drafts before/after each test (shared tenant row).

## Not verified / risks
- Eval (94/96, 43/43) not run: no roofing/dental pack or prompt files touched (pinned hash test green); the gate is for the end of the phase.
- Nothing hit a real LLM; both prompts are exercised only against fakes, so real-model extraction/email quality is unknown.
- Dedupe happens at insert, after the LLM calls, so a repeated identical request still spends LLM calls (rate limited).
- Zero-decimal currencies unsupported (`shortcut:` comment in quote.py). Number-word quantities ("twelve") are not grounded and become missing_input.
- Spelled-out amounts in email text ("one thousand francs") are not detected by the text check.

## Self-Check: PASSED
Files exist, both commits present.
