# Roofing Assumption Inventory (D-08, documentation only)

Generated from grep over api/app, db, prompts, clients, n8n/workflows, evals/scenarios, site (non-test source; test_*.py and scenarios follow their subject). Line numbers as of tag v1-roofing.

Destinations: pack = moves to roofing pack; core = stays core code (generic); untenanted = RoofDesk's own funnel, not a tenant; out of scope = not touched by this milestone.

| Item | file:line | Kind | Destination |
|------|-----------|------|-------------|
| RoofDesk's own sales funnel (PROFILE="roofdesk-ai", pilot-intake copy) | api/app/intake.py:1-3,16,23,146 | message / constant | untenanted |
| Pilot triage uses roofdesk-ai profile | api/app/pilot.py:61 | constant | untenanted |
| Prospect reply email ("sample roofing company") | api/app/replies.py:47,52 | message | untenanted (outreach) |
| Outreach target categories (includes "roof") | api/app/prospects.py:19 | constant | untenanted (outreach) |
| Outreach company-name cleaner example | api/app/outreach.py:49 | docstring | core |
| Default client profile "summit-roofing" | api/app/config.py:62 | constant | pack (default tenant) |
| demo_url, sender_name, sender_email (RoofDesk brand) | api/app/config.py:23,38,39 | constant | untenanted |
| Fallback message "free roof inspection" | api/app/policy.py:11 | message | pack |
| Safety regex (gas leak, collapse, electrocution...) | api/app/policy.py:17 | constant | pack (escalation rules); generic safety terms may stay core |
| service_type question "What roofing help do you need" | api/app/policy.py:84 | message | pack |
| Homeowner yes-regex ("my roof") | api/app/policy.py:116 | constant | pack |
| Service type regexes repair/replacement/inspection, non-roof list | api/app/policy.py:122-126,146 | constant | pack (qualification rules) |
| Stopword list with roof/roofing/summit | api/app/policy.py:170 | constant | pack |
| Qualification constants (service area Denver cities, owner, service type) | api/app/policy.py (qualification logic), clients/summit-roofing.yaml | constant | pack |
| Booking-confirmation email "Your free roof inspection with Summit Roofing" | api/app/admin.py:187-189 | message | pack |
| Quote-offer and booking copy ("qualify for a free roof inspection") | api/app/agent.py:96 | message | pack |
| Owner alert and customer booking emails, demo disclaimer (Summit Roofing) | api/app/agent.py:201-207 | message | pack (brand/copy); disclaimer stays core |
| Hardcoded FAQ list for fictional Summit Roofing | api/app/faq.py:10-23 | seed data | pack (faq entries) |
| FAQ seed with embeddings | db/faq_seed.sql:1-12 | seed data | pack (per-tenant FAQ rows) |
| Synthetic slots, weekdays 9/11/14/16 for 14 days | db/init.sql:23,62-63 | seed data / schema | pack (capacity/rota config); table stays core, gains tenant_id |
| Schema without tenant_id (leads, slots, conversations, bookings, faq_chunks) | db/init.sql | schema | core (add tenant_id + RLS) |
| Agent extraction + FAQ prompt, names Summit Roofing, free roof inspections | prompts/agent.v2.md:3 | prompt | pack (templated by business name/services); coupling to agent.py extraction schema stays core |
| Older agent prompt | prompts/agent.v1.md:3 | prompt | out of scope (legacy) |
| Older system prompt | prompts/system.v1.md:3 | prompt | out of scope (legacy) |
| FAQ answer prompt "Summit Roofing, a roofing company" | prompts/faq-answer.v1.md:3 | prompt | pack |
| summit-roofing client profile (business, about, triage categories) | clients/summit-roofing.yaml:1-12 | pack data | pack #1 (becomes packs/summit-roofing) |
| roofdesk-ai client profile | clients/roofdesk-ai.yaml:1,16 | pack data | untenanted |
| n8n email From/To summitroofing.test, Summit Roofing | n8n/workflows/inbound-message.json:215, escalation-alert.json:63, followup-scheduler.json:82, daily-report.json:72 | n8n | pack (sender/recipient from tenant config) |
| n8n outreach emails (RoofDesk AI outreach sender, owner@summitroofing.test) | n8n/workflows/outreach-flow.json:151,311,507,595 | n8n | untenanted |
| n8n error handler (roofdeskai.test) | n8n/workflows/error-handler.json:47 | n8n | untenanted |
| Marketing site / showcase / config | site/config.js, site/index.html, site/showcase.html | site | out of scope (live demo, roofdeskai.com) |
| Eval scenarios (qualified, disqualified, slots, faq, escalation, injection, vague, out_of_order, voice) | evals/scenarios/*.yaml | eval data | pack (roofing scenarios become pack #1 scenarios; 94/96 gate) |
| Python tests mentioning roofing/Summit | api/app/test_*.py (agent, policy, intake, outreach, mail, pilot, ...) | tests | follow their subject; update when subject moves |
