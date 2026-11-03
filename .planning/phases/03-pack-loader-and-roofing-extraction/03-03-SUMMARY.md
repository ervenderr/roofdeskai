---
phase: 03-pack-loader-and-roofing-extraction
plan: 03
subsystem: messages-calendar
tags: [messages, calendar, slots, pack]
requires: [03-02]
provides: [slot_instants, pack-driven ensure_slots, agent.DEMO_NOTICE, agent.CLOSED_STATES]
key-files:
  modified: [api/app/agent.py, api/app/admin.py, api/app/main.py, api/app/tools.py, api/app/test_pack.py]
metrics:
  completed: 2026-11-03
---

# Phase 3 Plan 03: Messages and calendar from the pack Summary

Reply, owner-alert, customer-confirmation and follow-up text now come from `pack.messages`; slots come from `slot_instants(pack.calendar, now)`. Roofing output is byte-identical to the old f-strings and the old SQL.

## Commits
- 8d0bcd6 test: messages and slot equivalence tests for pack-driven replies and calendar
- 117fd0a feat: reply and email text from pack messages, core CLOSED_STATES and DEMO_NOTICE
- 64c4eb0 feat: pack-driven slot generation with slot_instants

## Verification
- RED: new slot/DEMO_NOTICE/CLOSED_STATES/_fmt tests failed individually (ImportError/AttributeError/TypeError); file still collected (69 tests).
- Slot equivalence (old SELECT under UTC vs slot_instants, 8 frozen nows) passed before `ensure_slots` was switched.
- `make g-test`: 334 passed.
- Eval subset slot-none, slot-taken, slot-weekend, slot-third, slot-reject, qual-1 (local, LLM_TIMEOUT_S=300): GATE PASSED, no regressions.

## Decisions
- `ensure_slots` uses `unnest(CAST(:starts AS timestamptz[]), CAST(:ends AS timestamptz[]))`; it works under psycopg3, so the executemany fallback was not needed.
- Live golden assertions for the removed constants (closed/disqualify/nurture/no_slots replies, SLOT_HOURS, SLOT_DAYS_AHEAD) were deleted; frozen assertions remain.
- Buffer test expectation corrected (gaps 1h/3h/1h with 120 min buffer keeps 9 and 14, drops 11 and 16); my first expectation was wrong, not the code.

## Requirement deviations
- (a) The demo disclaimer stays core (`agent.DEMO_NOTICE`, business name from the pack) per D-10, so ROADMAP criterion 3 ("disclaimer from pack templates") and the PACK-04 wording are met only to that extent.
- (b) Roofing calendar timezone is Etc/UTC rather than D-11's America/Denver (legacy UTC wall-clock slot hours; pack.yaml keeps America/Denver identity). Correcting to Denver is a deliberate later behaviour change.

## Deviations from Plan
- Not mine to fix: policy-owned strings (SAFE_FALLBACK, ASK, anything_else) left for plan 04, as planned.
- `_escalate` and `_offer_slots` also gained a `pack` parameter (needed for the closed/ESCALATE and slot texts).
- test_tenancy.py needed no edits.

## Known Stubs
None.

## Self-Check: PASSED
