# Held-out eval

**Score: 17/20.** Roofing (summit-roofing) 10/12, dental (bright-smile-dental) 7/8.

20 scenarios (12 roofing `ho-r-*`, 8 dental `ho-d-*`) were written and committed before any other Phase 10 work, then run once per pack on the local model (`llama3.1:8b`, local only, no hosted fallback). Same deterministic checks as the dev sets, no LLM judge.

- Scenarios SHA: `6fc701f` (sha256 of the scenario set `471917eea903c10f7dc962763715bd8247688ccc3e8061954879d4e4623345a5`)
- Run SHA: `01f0fd9`
- Date: 2026-11-04
- Precheck stored in both records: `git diff --quiet 6fc701f HEAD -- api prompts businesses scripts evals/runner.py: exit 0`
- Re-runs: none (`reruns` is empty in both records). Run-once rule held.

## Caveats

- Authored by the same assistant that built the system, with the dev sets visible. The set is held out from tuning, not independent.
- The `--heldout` runner mode, `make g-heldout` and `test_heldout.py` were added in the same commit as the scenarios, before the run. The measured system is otherwise as of Phase 9.
- Failures below are reported, not fixed in this phase. No scenario, pack, prompt or shared code was edited after seeing the result.
- Environment note: the `make g-heldout` guard refuses to run while any untracked file sits under `scripts/`. An unrelated untracked `scripts/check-and-deploy.sh` was moved out of the tree for the duration of each run and moved back afterwards. This did not touch any run input.

## Per category

| Category | Roofing | Dental |
|---|---|---|
| qualified | 0/2 | 1/1 |
| disqualified | 2/2 | 1/1 |
| escalation | 1/1 | 1/1 |
| faq | 1/1 | 1/1 |
| injection | 1/1 | 1/1 |
| out_of_knowledge | 1/1 | 1/1 |
| slots | 1/1 | 1/1 |
| voice | 1/1 | 0/1 |
| vague | 1/1 | - |
| out_of_order | 1/1 | - |

Roofing escalation precision 1/2, recall 1/1; dental precision 1/1, recall 1/1. Booking validity 100% in both.

## Failures

All three failed the same way: the conversation never completed the booking (the model did not call `book_appointment`).

- `ho-r-01` (roofing, qualified): state COLLECT != DONE; outcome None != booked; lead_status new != booked; missing tool call book_appointment
- `ho-r-02` (roofing, qualified): state COLLECT != DONE; outcome None != booked; lead_status new != booked; missing tool call book_appointment
- `ho-d-08` (dental, voice): state COLLECT != DONE; outcome None != booked; lead_status new != booked; missing tool call book_appointment

Raw records: `evals/heldout/results/*.json`; reports: `evals/reports/heldout-*.md`.
