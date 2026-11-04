---
phase: 07-engine-modules-and-connectors
plan: 06
subsystem: reviews
tags: [reviews, check-reply, drafts, pii]
requires: [07-02, 07-03]
provides: [Reviews pack model + PackMeta.reviews, engine.pii, engine.reviews.check_reply, POST /reviews/draft, prompts/review-reply.v1.md]
key-files:
  created: [api/app/engine/pii.py, api/app/engine/reviews.py, api/app/reviews_routes.py, api/app/test_reviews.py, prompts/review-reply.v1.md]
  modified: [api/app/pack.py, api/app/main.py, api/app/tests_data/packs/demo-venue/pack.yaml]
requirements-completed: [MOD-06]
metrics: {tasks: 2, commits: [0a717c4, e79359a]}
---

# Phase 7 Plan 06: Review responder Summary

LLM drafts a reply in the pack tone; a pure `check_reply` returns stable codes (compensation, fault, unknown_fact, pii, health_privacy, forbidden_topic, too_long, empty); one regeneration with codes only; otherwise `needs_human` with codes and no reply text. Never posted, rating never branches.

## Commits
- 0a717c4 `feat: reviews pack block and deterministic reply check`
- e79359a `feat: review responder with deterministic post-check`
- (summary commit hash recorded in the final report)

## policy.py decision: extra_vocab NOT added
policy.py is untouched. Adding the keyword changes the `answer_supported` signature and the vocab line (modified lines, not a purely additive diff), so I used the fallback: `engine/reviews._unknown_vocab` reuses `policy._tokens`, `_same_word`, `_GENERIC` (private imports, same 40% threshold) with extra vocabulary = FAQ + review text + tone + signature + offer + kind + business + `REVIEW_GENERIC`. Roofing/dental behaviour cannot change.

## Verification (real output)
- RED 1: `app/test_reviews.py` -> `ModuleNotFoundError: No module named 'app.engine.reviews'`. After implementing, one test failed (weak vocabulary test sentence, fixed the test, not the threshold).
- RED 2: after appending API tests -> collection error (`reviews_routes` missing); then 57 passed.
- `make g-test ARGS="app/test_reviews.py app/test_policy.py app/test_pack_modules.py -q"` -> all dots, green.
- Full `make g-test`: `887 passed, 1 warning in 17.84s`.
- After run: tenants `['bright-smile-dental', 'summit-roofing']`, `count(*) from drafts` = 0 (no demo-venue row left).

## Coverage highlights
Fixture cases per code (>=4 each), apology passes, business email/phone allow-list, injection review text cannot unlock a refund/email reply, review words widen vocabulary, shipped packs have `meta.reviews is None` (pinned hash test green), pending / regenerate-once / needs_human (no reply text in payload or events, retry prompt contains codes only) / 502 no row / dedupe / ratings 1..5 identical / source inspection (no comparison on rating, no http client imports) / 404 no block / admin key alone 401 / 429 / 422 bodies.

## Notes
- Dental has no `reviews` block, so its `health_privacy` rule is only exercised through the fixture pack via `model_copy`. Phase 10 should add a real pack with a reviews block.
- Tuning: bare "always" removed from the commitment regex (too many friendly false positives); "never happen again" added. Compensation also blocks "on us".
- Dedupe happens at insert, after LLM calls (same as quotes); rate limited.

## Deviations from Plan
- policy.py extra_vocab not used (see above).
- `reviews` lives on `PackMeta` (pack.yaml block, as the plan specifies), not a separate Pack field.

## Not verified / risks
- No real LLM was called; prompt quality and the 40% vocabulary check against real model output are untested and may over-flag (those go to needs_human).
- Evals (94/96, 43/43) not run: no roofing/dental files touched; end-of-phase gate.
- Private policy helpers are imported by reviews.py; a rename in policy.py would break it (tests would catch).

## Self-Check: PASSED
Files exist; commits 0a717c4 and e79359a present.
