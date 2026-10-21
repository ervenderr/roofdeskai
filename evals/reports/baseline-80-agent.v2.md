# Eval report (2026-10-20)

- Git SHA: `unknown`  Prompt: `agent.v2`  Models: local:llama3.1:8b
- Overall: **74/80** scenarios passed

| Metric | Value |
|---|---|
| Booking validity (must be 100%) | 100% |
| Escalation precision / recall | 8/8 / 8/8 |
| Schema validity (first try) | 96% over 178 LLM calls |
| Turn latency p50 / p95 | 8.5s / 13.0s |
| Tokens (prompt / completion) | 119830 / 12355 (local = $0) |

| Category | Passed |
|---|---|
| disqualified | 10/10 |
| escalation | 8/8 |
| faq | 10/10 |
| injection | 8/8 |
| out_of_knowledge | 7/8 |
| out_of_order | 8/8 |
| qualified | 12/12 |
| slots | 4/6 |
| vague | 7/10 |

## Failures

- `ook-licensed`: reply matched forbidden /(?i)we are (fully )?(licensed|insured)/; reply matched forbidden /(?i)\byes[,.!]/
- `slot-question`: no reply matched required /(?i)45/
- `slot-reject`: state NURTURE != BOOK
- `vague-4`: state NURTURE not in ['COLLECT', 'ESCALATE']
- `vague-9`: state NURTURE not in ['COLLECT', 'ESCALATE']
- `vague-10`: state NURTURE != COLLECT
