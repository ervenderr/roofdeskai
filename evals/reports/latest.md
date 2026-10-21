# Eval report (2026-10-21)

- Git SHA: `88319aa`  Prompt: `agent.v2`  Models: local:llama3.1:8b
- Overall: **94/96** scenarios passed

| Metric | Value |
|---|---|
| Booking validity (must be 100%) | 100% |
| Escalation precision / recall | 11/11 / 11/11 |
| Schema validity (first try) | 95% over 232 LLM calls |
| Turn latency p50 / p95 | 6.7s / 14.4s |
| Tokens (prompt / completion) | 154892 / 16006 (local = $0) |

| Category | Passed |
|---|---|
| disqualified | 10/10 |
| escalation | 8/8 |
| faq | 10/10 |
| injection | 8/8 |
| out_of_knowledge | 8/8 |
| out_of_order | 8/8 |
| qualified | 12/12 |
| slots | 6/6 |
| vague | 10/10 |
| voice | 14/16 |

## Failures

- `voice-over-explainer`: state COLLECT != DONE; outcome None != booked; lead_status new != booked; missing tool call book_appointment
- `voice-indecisive`: state BOOK != DONE; outcome None != booked; lead_status qualified != booked; missing tool call book_appointment
