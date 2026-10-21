# Session Handover: 2026-10-21

**Project:** `~/Projects/leadpilot` (LeadPilot: AI lead-qualification agent plus outbound prospecting engine)
**State:** 120 unit tests pass. 5 local commits (`0b6f67b` .. `13dbfe2`), nothing pushed, nothing deployed.

## Completed This Session
- Roofing receptionist agent: model proposes JSON, code decides (qualification, state machine, booking, escalation). 80-scenario eval, 80/80 on `llama3.1:8b` (self-written and tuned against, so a regression suite, not a held-out score).
- Provider failover across free open-weight LLM APIs, FAQ retrieval (pgvector), n8n connected lead flow, Mailpit, admin API, Next.js dashboard (live API mode or static snapshot), README, `docs/failure-analysis.md` (21 entries), `docs/deploy.md`.
- Outbound engine: Google Maps scraper (opt-in compose service) -> import + score -> guarded AI email drafts -> approval queue -> capped sending -> follow-ups (3 days, 7 days, max 3) -> reply/bounce/unsubscribe handling. n8n "Outreach flow" has six lanes (scrape, import, draft, send, replies, call sheet).
- Phone call list for prospects with no email, outcome tracking, CSV export, daily n8n call sheet.
- US market support: per-campaign `timezone` and `locale` (en-US says "inquiries"); `usable_email()` filter for scraper junk (image filenames like `x@2x.png`).
- Research: Resend's acceptable-use policy prohibits cold outreach and scraped contact data; free/open-source cold email tools (Warmbly, AgentSDR, Email-automation, mailmerge) all need your own mailbox.

## Current State
Uncommitted (in the working tree/index): US timezone + locale, junk-email filter, their tests, and doc corrections (README.md, docs/deploy.md say cold email must NOT go through Resend). `git status` shows 9 files staged plus `docs/deploy.md` / `README.md` with further unstaged edits. Run `git add -A` and re-scan before committing.

Services running: api, db, mailpit, n8n (port 5679). Scraper is stopped (`make scraper` to start). Dashboard servers are not running.

## Open Items
1. **Build the SMTP sender and IMAP reader (user approved).** Details below.
2. Commit the pending work (user approves commits one at a time; scan for secrets and for real business names first).
3. Resend for customer-facing and owner mail: owner alerts/reports/call sheet can go through `onboarding@resend.dev` to the user's own address with no domain; confirmations to leads and receiving replies need a verified domain (user plans to buy one on Cloudflare). Not built.
4. Delete the local real scraped data before any real send (campaigns "Real: dentists Davao (test)" and "Real: roofers Austin TX", their prospects and unsent drafts).
5. Deploy the static dashboard demo to Cloudflare Pages (`docs/deploy.md`); ask first, user creates the Pages project.
6. Later: demo video, held-out eval set, second model, Clerk login, per-business "client pack" config, booking agent for sales calls.

## SMTP + IMAP spec (open item 1)
- `api/app/mailer.py` has one function `send(to, subject, body)` posting to Mailpit. Add a transport switch `MAIL_TRANSPORT=mailpit|smtp` with env `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, STARTTLS, and keep `From` = `SENDER_EMAIL`. Keep the `List-Unsubscribe` header and the footer (`outreach.with_footer`, requires `SENDER_ADDRESS`). Return a Message-ID so replies can be matched (`In-Reply-To` / `References`); consider storing it on `outreach_messages`.
- IMAP reader: poll a mailbox, match replies by `In-Reply-To`/`References` or sender address, call `outreach.handle_event(email, "reply", body)`. Detect bounce notices (delivery-status messages) -> `kind="bounce"`. Either an API-side poller (`/admin/outreach/poll-replies` + a schedule lane in `n8n/workflows/outreach-flow.json`) or n8n's IMAP trigger posting to `/webhooks/outreach-event`.
- Tests: fake `smtplib`/`imaplib`; real test only by emailing the user's OWN inbox.
- Open question for the user: which mailbox? (a NEW outreach Gmail, their personal Gmail, or a mailbox on a domain). Gmail needs an app password and Google actively blocks automation, so keep to about 20 a day with manual approval.

## Key Decisions
- **The model proposes, the code decides.** Status moves, suppression, caps, send window, claims checks and bookings are all code. Reason: small models invent facts.
- **Cold outreach does not go through Resend** (its AUP bans it); use the user's own mailbox over SMTP/IMAP. Resend is for opted-in customer mail.
- **Real scraped businesses never reach the public snapshot:** only campaigns flagged `public_demo` are exported; never commit real business names or scraped data (a scan for names is part of every commit).
- **Call list for phone-only prospects:** email reached 5/20 clinics in Davao (4 were personal inboxes) but 9/20 roofers in Austin; the "calls go unanswered" review hook was rare (0/20 and 1/20).
- **Per-campaign timezone/locale** instead of globals (a Manila window would email Austin at night).
- Campaigns default to manual approval; the API refuses to send without `SENDER_ADDRESS`; unsubscribe works by regex with no model involved.
- Commit format `type: description`, no attribution lines (global CLAUDE.md overrides the reminder).

## Files Modified (key)
- `api/app/`: `agent.py`, `policy.py`, `tools.py`, `llm.py`, `admin.py`, `prospects.py`, `outreach.py`, `outreach_routes.py`, `scraper.py`, `scrapes.py`, `mailer.py`, `ratelimit.py`, plus tests (`test_*.py`, `conftest.py` cleans up after itself).
- `prompts/` (agent, faq-answer, outreach-copy.v2, outreach-reply), `evals/` (runner, outreach_runner, scenarios, reports), `scripts/` (seed_demo, export_snapshot, sample_prospects.json).
- `db/init.sql`, `db/outreach.sql`, `docker-compose.yml`, `Makefile`, `n8n/workflows/*.json` (5 workflows, auto-imported on `docker compose up`).
- `dashboard/` (Next.js: Overview, Conversations, Prospects, Outreach, Calls), `README.md`, `docs/`.

## Gotchas
- n8n is on host port **5679** (the user's own process holds 5678).
- Run `make eval` only when nothing else uses the DB (it resets appointments); seed demo data AFTER eval.
- After `next dev`, run a clean `rm -rf .next && npm run build` before `next start`. Static export: `EXPORT=1 npm run build` (Server Actions are stubbed).
- Tests use a fixed future clock (Wed 2030-10-23); never use today's date in time-dependent tests.
- The Resend/Cloudflare/GitHub research notes are in `docs/deploy.md` and memory (`leadpilot.md`).

## Next Action
> Ask the user which mailbox the SMTP/IMAP transport should use, then add the `smtp` transport to `api/app/mailer.py` with unit tests (fake `smtplib`), and verify by sending one email to the user's own inbox.

---
## Session Opener (paste at start of next session)

```
Continuing LeadPilot at ~/Projects/leadpilot. Built so far: the roofing receptionist agent (80/80 own eval),
n8n flows, a Next.js dashboard, and an outbound engine (Google Maps scraper -> scored prospects -> guarded
email drafts -> approval -> capped sending -> follow-ups -> reply handling) plus a phone call list and
US/PH market support. 120 tests pass; 5 local commits; some work (US timezone/locale, junk-email filter,
doc fixes) is uncommitted. Key rule: Resend bans cold outreach, so cold email must go through the user's own
mailbox. Start by reading HANDOVER.md, asking which mailbox to use, then add the SMTP sender in
api/app/mailer.py and the IMAP reply reader (user already approved this).
```
