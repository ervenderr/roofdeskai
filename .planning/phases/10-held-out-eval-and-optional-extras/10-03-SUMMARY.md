---
phase: 10-held-out-eval-and-optional-extras
plan: 03
requirements: [EXT-03]
---

# Phase 10 Plan 03: puzzle-peak venue pack and scenarios Summary

Third pack `businesses/puzzle-peak/` (Puzzle Peak Escape, Europe/Zurich) with 9 config files and 33 chat scenarios authored before any model run, plus 11 module-eval cases and a one-line address fallback.

## Commits
- fcfd3da `fix: show a dash for a missing address in owner alert` (agent.py `or "-"`, test_notify_address.py; address-present body asserted byte-identical for roofing)
- 9a3f226 `chore: module eval loader falls back to businesses dir`
- a00ff10 `feat: add puzzle-peak venue pack and scenarios` (pack, scenarios, test_venue_pack.py)
- dbcc049 `test: add puzzle-peak module eval cases`

## Verification
- RED seen: address None case failed (`Address: None`); test_venue_pack errored (pack absent).
- `app/test_notify_address.py app/test_module_evals.py`: 125 passed (before new cases); after Task 3 test_module_evals: 134 passed.
- `app/test_venue_pack.py`: 7 passed (escalation recall 100% deterministic, no false escalation, counts, unpriced vip -> NeedsHuman, slug != demo-venue).
- `make g-eval-modules`: quote 33/33, capacity 16/16, brief 16/16, reviews 45/45, intake 19/19.
- `make check-shared` OK; roofing, dental, prompts, evals/heldout git-clean.
- Full `make g-test` intentionally NOT run (per plan, until 10-04 Task 3).

## Expected red until 10-04
`app/test_gen_docs.py`: 8 failures (no puzzle-peak baseline, so scorecard FileNotFoundError and drift). `app/test_pack_modules.py` otherwise passes (venue not in PINNED).

## Pack notes
- Counts: qualified 4, disqualified 3, slots 3, faq 4, escalation 5, injection 3, out_of_knowledge 4, out_of_order 2, vague 2, voice 3 = 33 (ids prefixed v).
- Qualification has only the service_type rule; group size is priced through services, not qualified in chat. `other` comes from non_business_pattern (gift card, voucher, job, career, hiring, wedding, catering).
- vip_experience deliberately unpriced (needs_human). Connectors: sheet source keeps a +3 bookings_count offset to exercise brief tolerance; ads available; send_hour 8. Capacity: weekday_afternoon, weekday_evening, weekend_day (max_covers 30); weekday_evening min_staff 2 can be violated by override.
- messages.yaml is the fixture with the business name swapped; emergency wording "call 144" unchanged. **Open item again: confirm "call 144" is the right Swiss emergency number.**

## Deviations
- Module cases live in per-module files (`evals/modules/{quote,capacity,intake}/cases.yaml`), not a single `evals/modules/cases.yaml` as the plan listed. 11 cases added (6 quote, 3 capacity, 2 intake) rather than about 8; brief/reviews untouched.
- Module cases passed on first run (hand-derived values matched), so no RED phase for Task 3.
- Loader fallback chooses the fixture dir when `tests_data/packs/<slug>` exists, else businesses_dir (equivalent to the plan's try/fall back).

## Unverified
- No scenario has been run against the model; wrong expectations only show in 10-04. Notable risks: vvague-1/vslot-taken/voice digit parsing, FAQ `reply_require` regexes, "hiring/job" disqualification routing.
- Escalation regex and FAQ were not tuned (no run yet).
