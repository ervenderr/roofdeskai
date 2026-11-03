# Phase 7 Verification

**Status:** human_needed (6/6 success criteria, 8/8 requirements verified by code reading; no blockers)
**Verifier:** gsd-verifier (read-only; report transcribed by orchestrator). Evidence from SUMMARYs, re-checked by orchestrator: pytest 1044 passed; `make g-eval-modules` quote 27/27, capacity 13/13, brief 16/16, reviews 45/45, intake 17/17; roofing 94/96 local-only (voice-over-explainer, voice-indecisive); dental 43/43; `git status businesses` empty.

| Req | Verdict |
|---|---|
| MOD-01 quote, no guess | PASS |
| MOD-02 quote drafts + text validation | PASS |
| MOD-03 capacity (dedupe, re-flag, DST) | PASS |
| MOD-04 connectors (mock, labelled) | PASS with W1 |
| MOD-05 daily brief | PASS |
| MOD-06 review responder | PASS with caveats (W2) |
| MOD-07 intake_event | PASS |
| EVAL-05 module eval sets | PASS |

## Warnings
- W1: capacity check falling back to the mock bookings connector persists flags but the success response lacks a `source: mock` field (only the unavailable path says it). Fix: add `source` to the success response.
- W2: review `unknown_fact` heuristic (40% unseen vocabulary) calibrated on fixtures only; may over-flag real output (safe direction, noisy).
- W3: quote-extract, quote-email and review-reply prompts never run against a real LLM.
- W4: roofing and dental packs have no module blocks, so every module route is 404 there; modules exercised only via demo-venue/test packs. Dental has no reviews block (health_privacy rule only exercised via fixture).
- W5: concurrent capacity runs on one range both report a new flag (one DB row; cosmetic).
- W6: `/daily-brief/due` with admin key + nonexistent tenant UUID may 500 instead of 404 (`_due_for` only catches PackError). Admin `X-Tenant-Id` default-tenant fallback (D-06 deviation) unchanged.
- W7: two-decimal rounding only; mock brief data seeded; quote text check is regex heuristic.

## Human verification items
1. Send 5-10 realistic reviews through `POST /reviews/draft` with a live LLM; check false `needs_human` rate.
2. Run `POST /quotes` with `email_text` against a live LLM for 3-5 emails.
3. Confirm roofdeskai.com demo unaffected after migration 007 is applied at deploy.
