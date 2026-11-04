# Eval report (2026-11-04)

Held-out run (scenarios fixed at 6fc701f, ran at 01f0fd9)

Caveat: these scenarios were authored by the same assistant that built the system, with the dev sets visible. The set is held out from tuning, not independent.

- Git SHA: `01f0fd9`  Prompt: `agent.v2`  Models: local:llama3.1:8b
- Overall: **7/8** scenarios passed

| Metric | Value |
|---|---|
| Booking validity (must be 100%) | 100% |
| Escalation precision / recall | 1/1 / 1/1 |
| Schema validity (first try) | 94% over 16 LLM calls |
| Turn latency p50 / p95 | 11.0s / 14.7s |
| Tokens (prompt / completion) | 11822 / 1009 (local = $0) |

| Category | Passed |
|---|---|
| disqualified | 1/1 (100%) |
| escalation | 1/1 (100%) |
| faq | 1/1 (100%) |
| injection | 1/1 (100%) |
| out_of_knowledge | 1/1 (100%) |
| qualified | 1/1 (100%) |
| slots | 1/1 (100%) |
| voice | 0/1 (0%) |

Gates: min category 0%, escalation recall 1/1

## Failures

- `ho-d-08`: state COLLECT != DONE; outcome None != booked; lead_status new != booked; missing tool call book_appointment
