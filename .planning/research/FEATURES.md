# Feature Research

**Domain:** Multi-business AI front-desk platform (lead agent, quotes, capacity/rota, review replies, owner brief, intake events) for SMB service and venue businesses
**Researched:** 2026-11-03
**Confidence:** MEDIUM. Grounded in the project spec and PROJECT.md plus domain knowledge of AI receptionist, quoting, workforce-scheduling and reputation-management products. No live competitor pages were fetched. Google review-gating rule comes from the spec; verify against Google's current policy before writing the review-request SOP.

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes / Guardrails | Depends on (existing) |
|---------|--------------|------------|--------------------|-----------------------|
| Business pack loader + Pydantic validation | Core value: onboarding is config, not code | MEDIUM | Fail loudly on bad pack (unknown field, missing price, bad cron/timezone). Grow `clients/*.yaml`. | triage YAML profiles, `policy.py`/`faq.py` |
| Tenant isolation (`tenant_id` everywhere) | A second business must never see the first's leads | MEDIUM | Default tenant = Summit Roofing; RLS and per-tenant keys before any public exposure. | leads/slots/conversations tables |
| Data-driven qualification (in_list, yes_no, max_number, in_area) | Different businesses ask different questions | MEDIUM | Interpreter must reproduce the 4 roofing checks exactly (94/96 gate); keep old path until it passes. Synonyms live in pack. | state machine, `policy.py` |
| Pack-driven FAQ/knowledge, grounded answers | Agent must answer only from stated facts | LOW-MED | "I don't have that information" then escalate/log; never invent hours, policies, warranties. | pgvector FAQ, `faq.py` |
| Pack-driven escalation (`always_human`, extra patterns) | Legal, injury, angry, "talk to a human" must reach a person | LOW | Generic defaults in code, pack adds domain ones (medical emergency for dental, injury/allergy for venue). Recall must stay 100%. | escalation regexes, escalation-alert workflow |
| Quote builder: line items, quantity, total from `services.yaml` | Customers ask "how much for X" | MEDIUM | Code computes every number; model only writes prose. Money as integer minor units or Decimal, never float. Stable rounding, currency in pack. | services.yaml, LLM chain (text only) |
| Quote: missing price = ask or escalate, never guess | Wrong quote is a contractual/reputational risk | LOW | Unknown service, out-of-range quantity, or unlisted add-on returns structured `needs_info` or `escalate`. Eval with a missing-price scenario per pack. | escalation |
| Quote approval queue before send | Owners will not let AI email prices unreviewed at first | MEDIUM | Draft, approve, send; record who approved and the quote snapshot. Quote has validity date and "estimate" wording from pack. | outreach approve/send pattern |
| Capacity checker: bookings vs staffing rules | Core ops question: over/under-staffed shifts | MEDIUM | Pure code over `capacity.yaml` (resource, min/max per slot, group-size ratios). Output: flag list with reason and shift. Handle timezone and DST via tenant tz. | slots/bookings, tenant tz |
| Capacity re-check on new booking and nightly | A flag raised yesterday may be stale | LOW-MED | Idempotent: same inputs produce same flags; resolved flags clear; do not re-alert unchanged flags (dedupe key). | capacity-check workflow |
| Review responder: drafts in pack tone, approval queue | Owners expect drafts, not auto-posting | MEDIUM | Draft only; human posts. Reuse outbound draft checks. Handle 1-star and 5-star differently. | outreach draft checks |
| Review guardrails: no refunds, no admitting fault/liability, no compensation promises, no invented facts, no PII of reviewer beyond first name | Legal/reputation exposure | MEDIUM | Deterministic post-check (denylist + regex + required-element checks), regenerate once, else mark `needs_human`. Offer offline channel ("please contact us at ..."). | draft-check machinery |
| Daily owner brief: one page, scheduled in tenant local time | The "daily one-pager" is the headline ask | MEDIUM | Sections fixed order; each number carries its source and as-of time. Missing connector = visible "source unavailable", not silent omission. | daily-report workflow, `/metrics` |
| Connector layer with mocks | Demo must work with no real accounts | MEDIUM | One interface (`fetch(since)` returning typed records), mock per source, `connectors.yaml` switches on/off. Read-only first. | connectors.yaml |
| Intake webhook: one record per person | Waivers, check-ins, results land in one place | MEDIUM | Generic payload mapping in pack; idempotency key; validate and reject unknown shape (HTTP 4xx, logged). Upsert by person key, events append. | tenant keys, new table |
| Tenant-aware n8n workflows (tenant id on every webhook) | n8n only triggers/sends | MEDIUM | Platform must still run without n8n; every decision in API. Auth header per tenant. | 6 existing workflows |
| `make new-business` (validate, load, smoke evals) | Repeatable onboarding is the product claim | LOW-MED | Smoke subset only; exit non-zero on any failure. | eval runner |
| Per-business eval scorecard, deterministic | Proves "no regression" and per-pack quality | MEDIUM | Per-category threshold (no category under 90%); regression gate on summit-roofing 94/96. | 96 scenarios, runner |
| PII masking in logs, retention setting, data map | Any EU/CH-facing buyer asks | LOW-MED | Mask email/phone/name in logs; retention is a per-tenant number of days with a purge job. | logging |
| Generated SOPs/runbook per pack | Non-technical owners operate it | LOW | Template rendered from pack and workflow catalog; no LLM needed. | workflow catalog |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes | Depends on |
|---------|-------------------|------------|-------|------------|
| "Model proposes, code decides" across quotes, capacity, reviews | Numbers and policies are never LLM-generated; verifiable by tests | LOW (pattern exists) | Strongest pitch vs generic AI receptionists. Publish it with eval proof. | existing agent design |
| Deterministic evals per module + held-out 20 scenarios | Rare credibility signal; most competitors show no scores | MEDIUM | Run held-out once; publish the number even if low. | eval runner |
| Disagreement flags in daily brief (e.g. bookings count vs accounting revenue vs sheet) | Owner trusts the page because it says where sources conflict | MEDIUM | Rule-based tolerance per metric in pack. | connector layer |
| Connectors as MCP servers | Claude (or any MCP client) can query the same sources | MEDIUM | Thin wrapper over the same adapters; read-only tools only; per-tenant auth. | connector layer |
| Pack-based onboarding with smoke test | Add a business in hours, not weeks | MEDIUM | Differentiates from per-client bespoke builds. | pack loader, evals |
| Side-by-side local vs Anthropic scorecard | Honest model comparison; cost and quality visible | LOW-MED | Provider added to existing chain; local stays default. | LLM chain |
| Group/corporate quote rules (tiers, minimum spend, per-head, add-ons, deposit) | Venue vertical pain point | MEDIUM | Express as declarative rule types in `services.yaml`, not code per business. | quote builder |
| Re-flagging rota with reason diff ("now short 1 host because group grew 8 to 14") | Actionable, not just a red cell | MEDIUM | Store previous result to diff. | capacity checker |
| Supplier-order draft with human approval | Closes loop from approved quote add-on to order | MEDIUM | Mock supplier only; never auto-submit. Cut first. | quote builder, approval queue |
| Knowledge-gap loop | Agent gets better from real unanswered questions | MEDIUM | Post-milestone candidate; log "no info" answers now so data exists. | FAQ grounding |
| Agent Office (live view from `agent_events`) | Demo value | HIGH | Optional; cut first; keep on localhost. | event log |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| LLM-generated prices or "ballpark" quotes | Feels helpful and fast | Wrong number becomes a commitment; unevaluable | Compute from `services.yaml`; else ask/escalate. Roofing pack keeps refusing chat prices. |
| Auto-posting review replies | Saves owner time | One bad reply to a complaint is public and permanent | Draft, approval queue, human posts |
| Review replies that offer refunds/discounts or accept blame | Calms angry reviewers | Legal admission, sets precedent, public promise | Thank, empathise, no fault language, take it offline with contact route |
| Review sentiment gating (only ask happy customers for reviews) | Boosts rating | Breaks Google review policy (per spec); account risk | Ask every customer (backlog item 6) |
| Auto-send quotes with no approval | "Fully automated" pitch | No safety net while model/prices are unproven | Approval first; consider auto-send per-tenant opt-in much later with spend cap |
| Free-form LLM decisions in capacity/rota | Natural language rota rules | Non-deterministic, un-evaluable | Structured `capacity.yaml` rules; model only phrases the alert |
| Auto-rescheduling or editing staff rota | Natural next step | Touches people's livelihoods and writes to external systems | Flag only; human changes rota |
| Write-access connectors (post journal entries, edit sheets) | "Do the work" | Data corruption, audit burden | Read-only connectors; supplier order stays a draft |
| Multi-language replies now | Zurich-type buyers | Prompt, eval and tone burden multiplies per language | `locale` field only; English first |
| Agent-decided refunds/discounts/medical or legal advice in chat | Handles complaints | Liability | Escalate via `always_human` categories (medical advice for dental, injury for venue) |
| Public multi-tenant before per-tenant keys + RLS | Quick demo of platform | Shared admin key leaks cross-tenant data | Keep internal until migration step 8 |
| Code-per-business plugins | Flexibility | Defeats core value | Add a new declarative rule type to the interpreter instead |
| Real payment/deposit collection | Group bookings want deposits | PCI scope, refunds | Quote states deposit terms as text; payment out of band |
| Outbound/scraping in customer package | Lead gen | ToS/email law risk | Keep as internal selling tool |
| Replacing `daily-report` with LLM-written analysis of numbers | Insightful briefs | Hallucinated causality | Code computes metrics and flags; model may only summarise provided facts, or skip prose |

## Feature Dependencies

```
Tenants (tenant_id, keys)
    └──requires──> Pack loader (Pydantic)
                       ├──requires──> Pack #1 extraction (94/96 gate)
                       │                  └──requires──> Data-driven qualification
                       │                                     └──requires──> Pack #2 dental + scorecard
                       ├──requires──> services.yaml ──> Quote builder ──> quote-request workflow ──> supplier-order
                       ├──requires──> capacity.yaml ──> Capacity checker ──> capacity-check workflow
                       ├──requires──> connectors.yaml ──> Connector layer ──> daily-brief ──> MCP exposure
                       ├──requires──> tone/escalation ──> Review responder ──> review-reply workflow
                       └──requires──> intake mapping ──> intake-event workflow

Approval queue (existing outreach pattern) ──enhances──> quote, review, supplier-order
Draft checks (existing) ──enhances──> review responder, quote email text
Tenant-aware n8n ──requires──> tenants + per-tenant API keys
Third pack (venue) ──requires──> quote builder + capacity checker + intake
Public exposure ──requires──> per-tenant keys + RLS
Anthropic provider ──independent── (feeds scorecard only)
```

### Dependency Notes

- **Everything requires the pack loader and tenants:** modules take the pack as input, so extraction must land first.
- **Quote builder and capacity checker are pure-code and independent of each other:** can be built in either order, and both are needed to justify the venue pack.
- **Daily brief requires connectors:** build connector interface plus mocks before the brief; the brief is the first consumer and its disagreement flags need at least two sources.
- **Approval queue is reused, not new:** quote, review, and supplier-order drafts should share the outbound approve/send machinery rather than three new queues.
- **Existing escalation and qualification changes conflict with the regression gate:** do not combine interpreter swap with new behaviour in one step.
- **Third pack and held-out set come last:** the held-out set must be written after modules exist but before tuning to it.

## MVP Definition

### Launch With (this milestone core)

- [ ] Baseline freeze, tenants, pack #1 extraction, data-driven qualification (regression gate)
- [ ] Pack #2 dental with ~40 scenarios and scorecard
- [ ] Quote builder with approval draft and missing-price tests
- [ ] Capacity checker with re-flag tests
- [ ] Connector mocks + daily brief with source-disagreement flag
- [ ] Review responder with deterministic guardrail checks
- [ ] Intake webhook with idempotent per-person record
- [ ] Tenant-aware n8n (existing 6 plus quote-request, review-reply, capacity-check, daily-brief, intake-event)
- [ ] Per-tenant keys + RLS, PII masking, retention, generated SOPs, held-out 20, `make new-business`

### Add After Validation (v1.x)

- [ ] Appointment reminders / no-show follow-up, knowledge-gap loop, nightly eval run (spec's first three backlog items)
- [ ] MCP exposure of connectors (if time, otherwise right after daily brief)
- [ ] Anthropic provider and side-by-side scorecard
- [ ] Approval digest, escalation reminder

### Future Consideration (v2+)

- [ ] Real connectors (Google Sheets first) and write actions with audit
- [ ] Multi-language, real SMS/phone line
- [ ] Post-visit review request (all customers), weekly owner report, provider health monitor, auto-onboarding
- [ ] Supplier-order, Agent Office, Flight Recorder wrap (cut first)

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Pack loader + tenants + extraction | HIGH | MEDIUM | P1 |
| Data-driven qualification | HIGH | MEDIUM | P1 |
| Pack #2 + scorecard | HIGH | MEDIUM | P1 |
| Quote builder (+ missing-price rule) | HIGH | MEDIUM | P1 |
| Capacity checker | HIGH | MEDIUM | P1 |
| Review responder + guardrails | HIGH | MEDIUM | P1 |
| Daily brief + connector mocks | HIGH | MEDIUM | P1 |
| Intake webhook | MEDIUM | MEDIUM | P1 |
| Tenant-aware workflows | HIGH | MEDIUM | P1 |
| Keys + RLS | HIGH | MEDIUM | P1 (blocks public exposure) |
| PII masking / retention / SOPs | MEDIUM | LOW | P1 |
| Held-out 20 + `make new-business` | HIGH | LOW | P1 |
| MCP-exposed connectors | MEDIUM | MEDIUM | P2 |
| Anthropic provider | MEDIUM | LOW | P2 |
| Third pack (venue) | MEDIUM | MEDIUM | P2 |
| Supplier-order | LOW | MEDIUM | P3 |
| Agent Office | LOW | HIGH | P3 |

## Expected Behavior by Module (for requirement writing)

- **Quote builder:** input = tenant, service ids, quantities, add-ons, optional date and party size. Output = `{status: ok|needs_info|escalate, lines[], subtotal, tax?, total, currency, valid_until, assumptions[]}`. Rules: unknown service/add-on = `needs_info`; missing price = `escalate`; quantity below minimum or above max = `escalate`; discounts only if defined in pack; no price displayed without a quote record. Email text from template with numbers injected, not model-written. Eval checks: totals exact, no number in email absent from computed result.
- **Capacity checker:** input = bookings in window + `capacity.yaml`. Output = per-slot `{required, scheduled, status: ok|under|over, reason}`. Triggers: booking created/changed/cancelled and nightly. Alert only on new or changed flags. Eval: boundary cases (exactly at limit), cancellation clears flag, group size rise re-flags.
- **Review responder:** input = review text, rating, platform, pack tone/signature. Output = draft + `checks{refund,fault,compensation,unknown_facts,pii}` + status `draft|needs_human`. Negative reviews with injury, legal threat, discrimination, or health claims go to `needs_human` with no draft or a minimal holding draft. Eval: adversarial reviews demanding refunds must yield no refund language.
- **Daily brief:** scheduled per tenant tz; sections: bookings today/tomorrow, new leads and conversion, flags (capacity, escalations pending), approvals waiting, money (from accounting connector), disagreements. Stale or failed connector shown explicitly.
- **Intake webhook:** authenticate tenant, validate against pack mapping, idempotency key, upsert person, append event (waiver, check-in, result). Consent and retention fields respected; health/result data flagged as sensitive in data map.
- **Qualification/agent:** unchanged contract (state machine, repair retry, escalation first). Prices in chat stay refused unless the pack enables quoting (spec: roofing refuses, `services.yaml` packs may quote computed prices).

## Competitor Feature Analysis

Category-level only (training knowledge, not freshly verified).

| Feature | AI receptionist products (voice/chat answering) | Quote/estimating tools | Reputation tools (review reply) | Our Approach |
|---------|------------------------------------------------|------------------------|-------------------------------|--------------|
| Booking/lead capture | Standard, often calendar sync | n/a | n/a | Exists; make pack-driven |
| Pricing | Usually LLM from a prompt or KB | Rule/price-book based, human sent | n/a | Code-computed from price book, approval |
| Review replies | n/a | n/a | AI drafts, often auto-post option | Draft-only plus deterministic guardrails |
| Rota/capacity | Rare | n/a | n/a | Pure-code checker with re-flag |
| Owner brief | Weekly analytics dashboards | n/a | n/a | Daily one-pager with disagreement flags |
| Evidence of quality | Marketing claims | n/a | n/a | Published deterministic per-pack scorecard |

## Sources

- `.planning/PROJECT.md` and `RoofDesk Global Platform Spec.md` (Nov 3, 2026): primary, HIGH for scope and constraints
- Domain knowledge of AI receptionist, price-book quoting, workforce scheduling and reputation-management tools: MEDIUM/LOW, not verified by live fetch
- Google review-gating prohibition: cited in spec backlog item 6; verify against Google's current review policy

---
*Feature research for: multi-business AI front-desk platform*
*Researched: 2026-11-03*
