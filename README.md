# LeadPilot

An AI agent a small business could run on. It qualifies inbound leads by chat, checks a calendar, books roof inspections, updates a CRM, and hands off to a human when it should. An automated eval suite of 80 scenarios tests it, with published pass rates, latency and cost, and a write-up of what failed and how I fixed it.

The business is **Summit Roofing**, a made-up company. Every name, number and address in this repo is synthetic. Nothing comes from a client or employer.

![Dashboard overview](docs/img/overview.png)

| Conversations | Transcript with tool calls inline |
|---|---|
| ![Conversations](docs/img/conversations.png) | ![Transcript](docs/img/transcript.png) |

> **Key design rule: the model proposes, the code decides.** The LLM extracts facts and writes FAQ answers. Plain code validates every output, runs the conversation state machine, applies the qualification rules, and is the only thing allowed to book, update a lead or escalate. A bad generation cannot book a bad slot.

## What it looks like

```
Customer: Hi, I need a roof repair. I own the house at 15 Pine St, Denver, and want it done within a month.
Agent:    May I have your name?
Customer: Sam Reyes, sam.reyes@example.com
Agent:    Good news, you qualify for a free roof inspection! Here are the next openings: 1) Wed Oct 21, 09:00 AM; 2) ...
Customer: The first one.
Agent:    You're booked for Wed Oct 21, 09:00 AM. We'll see you then!
```

That ran through the n8n flow below and sent a real confirmation email (to Mailpit in dev).

## Scorecard

Latest run: **80/80 scenarios**, 2026-10-21, commit `0b6f67b`, prompt `agent.v2`, model `llama3.1:8b` (local, Ollama, temperature 0).

| Metric | Result |
|---|---|
| Booking validity (must be 100%) | **100%** |
| Escalation precision / recall | 100% / 100% |
| Schema validity (first try) | 95% over 181 model calls |
| Turn latency p50 / p95 | 6.8s / 9.8s (16 GB laptop, no GPU server) |
| Tokens | 121k prompt / 12k completion; cost $0 (local) |

| Category | Passed |
|---|---|
| Clear qualified lead | 12/12 |
| Clear disqualified lead | 10/10 |
| Vague / incomplete answers | 10/10 |
| Information given out of order | 8/8 |
| FAQ questions | 10/10 |
| Out-of-knowledge questions | 8/8 |
| Escalation required | 8/8 |
| Prompt injection / jailbreak | 8/8 |
| Slot edge cases | 6/6 |

**Read this with the right amount of salt.** I wrote all 80 scenarios while building, and I fixed failures against those same scenarios, so this is a regression suite and not a held-out test. The first full run scored 74/80 (`evals/reports/baseline-80-agent.v2.md`). An unseen test set would score lower. Everything ran on one 8B model. Cost is "$0" because the model is local; hosted-API cost is not estimated.

## Architecture

```
 Web chat ──┐
 SMS / GHL- │
 style      ┴─► n8n (lead flow, schedules) ─► Agent API (FastAPI) ─► LLM (provider chain, all OpenAI-compatible)
 webhook                                          │                   local Ollama → Groq → NVIDIA NIM → OpenRouter → OVH
                                                  ├─► Postgres + pgvector: leads, conversations, slots, FAQ chunks,
                                                  │    tool/LLM call logs, escalations, eval results
                                                  ├─► Tool layer: get_available_slots, book_appointment, update_lead,
                                                  │    lookup_faq, escalate_to_human
                                                  └─► Dashboard (Next.js) + eval runner
```

Conversation states: `GREETING → COLLECT → (BOOK → DONE | NURTURE | DISQUALIFY)`, and any state can go to `ESCALATE`. Qualification: owner, in the service area, repair/replacement/inspection, within 6 months. Budget is recorded but never disqualifies.

### n8n flow

`n8n/workflows/` holds four exported workflows, all imported and activated automatically by `docker compose up`.

- **Lead flow:** webhook, normalize the SMS/GHL payload, call the agent, send the reply immediately, then branch on the outcome: booked sends a confirmation email, escalated runs the Escalation alert workflow, nurture is left to the nightly scheduler.
- **Follow-up scheduler** (nightly): nurture leads with no activity for 48 hours get a follow-up email, at most 3 per lead.
- **Escalation alert:** emails a human with a link to the transcript.
- **Daily report:** emails a summary of `/metrics`.

All logic lives in the FastAPI service; n8n only triggers and sends. The project runs without it.

**License note:** n8n uses the Sustainable Use License (fair-code, not OSI open source). It is free to self-host for your own use, as here. If you need strictly open source, **Activepieces** (MIT core) is the alternative. Everything else here is MIT, BSD, Apache 2.0 or PostgreSQL License.

## How I check the output

**Guardrails in code** (`api/app/`):
- Model output is parsed against Pydantic schemas. Invalid output gets one repair retry, then the conversation escalates.
- Extracted facts are dropped unless the customer's own message supports them. Small models invent facts, and one wrong "renter" ends a conversation.
- Booking runs in one transaction: the slot must be open, the lead qualified, one appointment per lead. The customer picks from the slots the system offered, never by typing an id.
- FAQ answers must reuse the knowledge base's words; prices, warranties and other claims that are not in it are replaced by a safe fallback.
- Customer text is data, never instructions; the tool allowlist is fixed.
- Escalation triggers: angry or distressed customer, legal or safety issue, request for a human, two failed turns, any validation failure.
- `/chat` needs a per-conversation token and is rate limited. Admin endpoints need a key.

**Evals** (`evals/`): `make eval` runs every scenario through the real agent and scores it with deterministic checks (final state, tool calls, forbidden actions, reply regexes). No LLM judge. Each run records git SHA, model and prompt version in Postgres, writes `evals/reports/latest.md`, and appears as a trend on the dashboard. Prompts are versioned files in `prompts/`.

## Failures I found and fixed

Full write-up with before/after: [`docs/failure-analysis.md`](docs/failure-analysis.md). Highlights:

- The model returned an empty `reply` and the strict schema escalated a healthy conversation. Fix: the code writes the next question.
- The model invented `is_owner=false` from a message that never mentioned ownership, and disqualified the lead. Fix: grounding check on extracted facts.
- The model confidently answered "yes, we are licensed and insured". The number-only claim check could not see it. Fix: answers must reuse the knowledge base's words.
- An independent code review found a stray "one" in a longer message could book a slot, a double-submit could undo a booking, and "Sue" (a name) and "Court" (a street) triggered legal escalations. None of these were in the eval set.

## Run it

Needs Docker and [Ollama](https://ollama.com) on the host (Docker on Mac cannot use the GPU).

```bash
ollama pull llama3.1:8b && ollama pull all-minilm
cp .env.example .env            # optional: add free-tier API keys for fallback providers
docker compose up -d --build    # Postgres, API, Mailpit, n8n
make eval                       # about 20 to 25 minutes on a laptop; writes evals/reports/latest.md
```

| Service | URL |
|---|---|
| API | http://localhost:8000 (`/docs`, `/health`) |
| n8n | http://localhost:5679 |
| Mailpit (caught emails) | http://localhost:8025 |
| Dashboard | `cd dashboard && npm i && API_URL=http://localhost:8000 ADMIN_API_KEY=dev-admin-key npm run dev` then http://localhost:3100 |

Try it:
```bash
curl -s -X POST localhost:5679/webhook/inbound-message -H 'content-type: application/json' \
  -d '{"contactId":"demo-1","body":"I want to talk to a real person"}'    # escalates; alert lands in Mailpit
```

The LLM client is provider-agnostic. If a provider is rate limited, times out or errors, the next one in the chain takes over, and the provider that answered is recorded on every call. Deploy notes (Cloudflare Pages, Neon, Resend, and so on) are in [`docs/deploy.md`](docs/deploy.md).

## Limitations and what I'd do next

- The eval set is self-written and was tuned against; build a held-out set and measure the gap.
- One model so far. Run the suite through a second model and publish a side-by-side scorecard.
- Hosted-API cost is not estimated, only local ($0).
- No real SMS or phone integration; the channel is simulated by a webhook.
- Admin pages use a shared key. Clerk login and Resend email are planned, not built.
- The rate limiter is in-process, so it is per instance.
- Embeddings need an Ollama-compatible endpoint, which complicates hosting the API on a free tier.
- n8n is local only (a free host would sleep), so it is shown in the demo instead of hosted.
