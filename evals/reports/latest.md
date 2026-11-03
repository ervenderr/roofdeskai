# Eval report (2026-11-03)

- Git SHA: `eaab4ca`  Prompt: `agent.v2`  Models: local:llama3.1:8b
- Overall: **94/96** scenarios passed

| Metric | Value |
|---|---|
| Booking validity (must be 100%) | 100% |
| Escalation precision / recall | 11/11 / 11/11 |
| Schema validity (first try) | 95% over 232 LLM calls |
| Turn latency p50 / p95 | 8.8s / 11.1s |
| Tokens (prompt / completion) | 154895 / 15997 (local = $0) |

| Category | Passed |
|---|---|
| disqualified | 10/10 (100%) |
| escalation | 8/8 (100%) |
| faq | 10/10 (100%) |
| injection | 8/8 (100%) |
| out_of_knowledge | 8/8 (100%) |
| out_of_order | 8/8 (100%) |
| qualified | 12/12 (100%) |
| slots | 6/6 (100%) |
| vague | 10/10 (100%) |
| voice | 14/16 (88%) |

Gates: min category 88%, escalation recall 11/11

## Failures

- `voice-over-explainer`: state COLLECT != DONE; outcome None != booked; lead_status new != booked; missing tool call book_appointment
- `voice-indecisive`: state BOOK != DONE; outcome None != booked; lead_status qualified != booked; missing tool call book_appointment
