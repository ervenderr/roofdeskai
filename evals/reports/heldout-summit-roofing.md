# Eval report (2026-11-04)

Held-out run (scenarios fixed at 6fc701f, ran at 01f0fd9)

Caveat: these scenarios were authored by the same assistant that built the system, with the dev sets visible. The set is held out from tuning, not independent.

- Git SHA: `01f0fd9`  Prompt: `agent.v2`  Models: local:llama3.1:8b
- Overall: **10/12** scenarios passed

| Metric | Value |
|---|---|
| Booking validity (must be 100%) | 100% |
| Escalation precision / recall | 1/2 / 1/1 |
| Schema validity (first try) | 93% over 29 LLM calls |
| Turn latency p50 / p95 | 13.3s / 16.3s |
| Tokens (prompt / completion) | 18373 / 1996 (local = $0) |

| Category | Passed |
|---|---|
| disqualified | 2/2 (100%) |
| escalation | 1/1 (100%) |
| faq | 1/1 (100%) |
| injection | 1/1 (100%) |
| out_of_knowledge | 1/1 (100%) |
| out_of_order | 1/1 (100%) |
| qualified | 0/2 (0%) |
| slots | 1/1 (100%) |
| vague | 1/1 (100%) |
| voice | 1/1 (100%) |

Gates: min category 0%, escalation recall 1/1

## Failures

- `ho-r-01`: state COLLECT != DONE; outcome None != booked; lead_status new != booked; missing tool call book_appointment
- `ho-r-02`: state COLLECT != DONE; outcome None != booked; lead_status new != booked; missing tool call book_appointment
