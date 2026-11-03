---
phase: 05-per-pack-eval-runner-and-dental-pack
plan: 02
subsystem: packs
tags: [dental, pack, safety, claims]
requires: [05-01]
provides: [bright-smile-dental pack, CHF claim guard, deterministic emergency recall test]
key-files:
  created: [businesses/bright-smile-dental/*.yaml (6), api/app/test_dental_pack.py]
  modified: [api/app/policy.py, api/app/test_policy.py, clients/bright-smile-dental.yaml]
requirements: [EVAL-03]
metrics:
  completed: 2026-11-04
---

# Phase 5 Plan 02: Dental pack Summary

Six-file `bright-smile-dental` pack (Europe/Zurich, Mon-Fri, 30-minute slots, 12 FAQ entries, two rules) loads with the real loader; emergency recall is 14/14 deterministic (regex, no model); `_CLAIM_RE` now also catches CHF amounts.

## Commits
- ebf81f6 test: add failing dental pack and CHF claim tests
- 36fa89c feat: add bright-smile-dental pack and CHF claim guard

## Verification
- Red: pack-missing errors (5) and CHF assertion failures (2).
- Green: `make g-test` 474 passed. No `test-%` tenants left in the branch DB afterwards.

## Deviations from Plan
- **[Rule 1] Safety regex recall gap:** the research regex missed "My front tooth is loose after a fall." (only matched "loose tooth"). Added `(tooth|teeth)\b.{0,15}\bloose` to `escalation.yaml`; recall is now 14/14 and the 22 negatives still do not escalate.
- Test emergency/negative lists include extra sentences beyond the research scenarios (abscess, unbearable pain, ibuprofen, antibiotics, loose tooth, "medication history" negative).

## Requirement deviations
- (a) D-05 Mon-Sat: engine supports only weekdays_only or all seven days, so dental is Mon-Fri and the FAQ says Monday to Friday. `clients/bright-smile-dental.yaml` facts changed to Monday to Friday to match (no test pins it).
- (b) **"call 144" flag:** the Swiss emergency number 144 is ASSUMED from training knowledge (kept in `closed.ESCALATE` and the emergency FAQ; ESCALATE is one string for every escalation reason, so it also shows for angry/human requests). User should confirm.
- (c) `always_human` is stored data only; insurance is answered from the FAQ, not escalated.
- (d) D-13: no roofing iso-* eval scenarios; pytest only (plan 04).

## Known Stubs
None. No scenarios dir yet (plan 03).

## Self-Check: PASSED
