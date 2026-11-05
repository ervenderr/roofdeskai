# RoofDesk Global

## What This Is

RoofDesk is an AI lead-booking agent (chat + voice) with evals, outbound, n8n workflows and a dashboard, today hardcoded to one business, Summit Roofing. RoofDesk Global makes it a multi-business platform: everything business-specific moves into a per-business config pack, so one agent, one set of n8n workflows and one eval suite serve any business. Roofing becomes pack #1.

Source spec: `RoofDesk Global Platform Spec.md` (Nov 3, 2026). Repo: `ervenderr/roofdeskai`, master.

## Current Milestone: v1.1 Tenant-aware dashboard

**Goal:** Give owners a front end for RoofDesk Global: sign in as one business and see its own data, including the v1.0 engine output that today only exists in the API and n8n.

**Target features:**
- Sign in with a tenant API key (checked server-side; the key never reaches the browser); every page shows only that tenant's data
- Existing roofing pages (overview, conversations, calls, outreach, prospects) keep working
- New screens: quote drafts (approve/reject), review reply drafts, capacity flags, daily brief
- Local only; no deploy, no push

**Key context:** The dashboard has a static-snapshot demo mode and a live mode that uses one shared admin key. Only `GET /capacity/flags` and `GET /tenant/me` exist as tenant read routes; quotes, review drafts and briefs need read endpoints added to the API.

## Core Value

Onboarding a new business is a config pack, not a code change, and the roofing pack keeps scoring 94/96 on evals while it moves.

## Requirements

### Validated

- ✓ Lead agent: chat state machine (GREETING, COLLECT, BOOK, NURTURE, DISQUALIFY, ESCALATE), model proposes / code decides — existing
- ✓ Evals: 96 scenarios, 94 pass, deterministic checks, no LLM judge — existing
- ✓ Message triage (`POST /triage`) with YAML client profiles (roofing, dental clinic, RoofDesk) — existing
- ✓ Outbound: scrape, import, score, draft, approve, send, follow up, classify replies, call list — existing
- ✓ 6 n8n workflows (inbound-message, followup-scheduler, escalation-alert, daily-report, outreach-flow, error-handler); logic stays in API — existing
- ✓ Voice: `/transcribe`, `/chat`, `/speak` — existing
- ✓ Next.js dashboard (conversations, calls, outreach, prospects, eval trend) — existing
- ✓ FastAPI + Postgres/pgvector + Docker Compose + provider-agnostic LLM chain (local Ollama first) — existing

### Active

- [ ] Baseline frozen (`v1-roofing` tag, saved eval report) and a rerun-and-compare gate on every step
- [ ] Multi-tenancy: `tenants` table, `tenant_id` on leads/slots/conversations/FAQ, default tenant Summit Roofing, no behaviour change
- [ ] `businesses/summit-roofing/` pack extracted from `policy.py`, `faq.py`, `agent.py`, `tools.py`, validated by Pydantic; eval stays 94/96
- [ ] Data-driven qualification: rule interpreter reading `qualification.yaml` (in_list, yes_no, max_number, in_area); service synonyms in pack
- [ ] Pack #2 `bright-smile-dental` with ~40 scenarios and per-business scorecard (no category under 90%)
- [ ] Engine modules, each with deterministic evals: quote builder, capacity checker, connector layer (mocks, MCP-exposed), review responder, daily brief, intake webhook
- [ ] Anthropic provider added to the LLM chain (local stays default)
- [ ] 12 tenant-aware n8n workflows (6 existing + quote-request, review-reply, capacity-check, daily-brief, intake-event, supplier-order); n8n only triggers and sends
- [ ] Third business pack (venue/experience business with staff and group bookings)
- [ ] Per-tenant API keys and row-level security on `tenant_id`
- [ ] Generated SOPs + runbook per pack; PII masking in logs; retention setting; data map doc
- [ ] 20 held-out scenarios run once, score published; README with per-business scorecard and workflow catalog
- [ ] `make new-business` command: validate pack, load it, run smoke subset of evals
- [ ] Optional/cut-first: supplier-order, Agent Office page (MIT base, 2D), third pack, Anthropic provider, Flight Recorder wrap

### Out of Scope

- Video editing pipeline — a tools inventory, not software
- Real SMS/phone line — later, via provider webhook into `inbound-message`
- Multi-language replies — English first, `locale` field only
- Public multi-tenant exposure before per-tenant keys + RLS (migration step 8) — shared admin key is unsafe
- Copying agents-office code (PolyForm Noncommercial) — use MIT base or build from scratch
- Outbound/scraping in the customer package — kept as a tool for selling RoofDesk itself
- Post-milestone n8n automation backlog (9 items; first three — appointment reminders, knowledge-gap loop, nightly eval run — are the next candidates)

## Context

- Brownfield: Python/FastAPI API (`api/app/`), Next.js dashboard, n8n workflows, evals runner, live site roofdeskai.com (Summit Roofing demo must stay up; build on a branch).
- Roofing assumptions live in `policy.py`, `faq.py`, `agent.py`, `tools.py`, the DB schema, and roofing-leaning escalation regexes. `intake.py` and `prompts/` were NOT read for the spec; read them before migration step 3.
- Local 8B model may score lower in new domains; report per-pack honestly.
- n8n is fair-code (Sustainable Use License); Gemini voice free tier may not allow paid production use.
- Planned 4-week schedule: W1 steps 1-4, W2 step 5 + quote/capacity + Anthropic, W3 connectors/workflows/third pack, W4 security/docs/held-out.

## Constraints

- **Regression gate**: `summit-roofing` stays at 94/96 with the same two failures until step 5 — eval is the safety net for every step
- **Architecture**: n8n triggers and sends; all decisions in FastAPI; platform must run without n8n
- **Determinism**: code computes numbers (quotes, capacity); model only writes text around them; evals deterministic
- **Simplicity**: smallest change per step; keep old code path until the rule interpreter passes
- **Live demo**: do not break roofdeskai.com; work on a branch

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Config pack per business (grow `clients/*.yaml`) | Reuses triage profile pattern; nothing thrown away | — Pending |
| Roofing extracted as pack #1 under eval gate | Proves no behaviour change | — Pending |
| Keep "RoofDesk" name for now | roofdeskai.com is live; rename later | — Pending (user decision) |
| Local model default, Anthropic optional provider | Free default, employers ask for Claude; side-by-side scorecard | — Pending |
| Third pack: venue/experience business | Exercises capacity, quotes, intake | — Pending (user decision) |
| Build on a branch, keep live demo running | Protects the live site | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-11-05 after v1.1 milestone start*
