# Failure analysis

Model: `llama3.1:8b` (local, Ollama), temperature 0. 31 scenarios. Baseline report: `evals/reports/baseline-agent.v1.md`.

| Run | Prompt | Pass | Notes |
|---|---|---|---|
| 1 | agent.v1 | 20/31 | model wrote replies, picked slots, extracted loosely |
| 2 | agent.v2 + code-chosen questions + code slot pick + address rule | 29/31 | two wrongful disqualifications |
| 3 | + grounding guard | 31/31 | |

## 1. Empty `reply` escalated a healthy conversation
- **What happened:** `qual-1` escalated at turn 3 with `validation_failure`. The model returned `"reply": ""` and the schema required one, so both attempts failed.
- **Root cause:** the reply is not needed when the code decides the next step; I had made it mandatory anyway.
- **Change:** `reply` is optional; the code writes the next question (`policy.next_question`).

## 2. The model re-asked known questions and could not choose a slot
- **What happened:** `qual-3/4/5`, `ooo-1/2`, `slot-taken` failed. Model-written replies asked for facts already given, and `chosen_slot_id` was rarely returned.
- **Root cause:** free-form generation and slot selection were left to an 8B model.
- **Change:** code picks the next question; code resolves "first/second/3" only against the slot ids it offered (`policy.pick_slot`, stored in `conversations.offered_slot_ids`). Prompt v2, temperature 0. 20/31 -> 29/31.

## 3. Address without a city disqualified a lead
- **What happened:** `slot-none`: the model extracted "1 Oak St" (dropped "Denver"); the area check read it as out of area.
- **Change:** an address with no city part is `incomplete` and the code asks for the city.

## 4. The model invented facts, causing wrongful disqualification
- **What happened:** `qual-1` and `vague-1` ended in DISQUALIFY. On a message saying nothing about ownership or timing, the model returned `is_owner=false`, `timeline_months=0`, and `service_type=other`.
- **Root cause:** extraction hallucination; DISQUALIFY is terminal, so one fabricated field ends the conversation.
- **Change:** `policy.ground` drops any extracted value the customer's message does not support. 29/31 -> 31/31.

## 5. Independent code review (found before any eval did)
A separate reviewer agent read the code cold. The evals could not have caught these:
- A stray "one" or "2" in a longer message could pick a slot. `pick_slot` now only accepts short messages without negation.
- A double-submit could roll DONE back to BOOK. `appointments.lead_id` is now UNIQUE and DONE/booked can't be overwritten.
- Grounding was too loose ("other" service, bare digits as a timeline). Tightened; addresses are parsed by city, not substring.
- "Sue" (a name) and "Court" (a street) triggered legal escalation. Patterns narrowed; safety/legal now reach a human even after the chat is closed.
- A failed escalation write still told the customer a human would follow up. It now raises instead.
- Not fixed yet: `/chat` has no per-conversation auth (any integer id works); fix with a token at deploy time.

## Week 3: 80 scenarios (baseline `evals/reports/baseline-80-agent.v2.md`: 74/80, final: 80/80)

### 6. `not_ready` over-triggered, sending people to NURTURE
- **What happened:** `vague-4/9/10` and `slot-reject` ended in NURTURE after "Hello", "hmm", "Just wondering how this works" and "None of these work for me".
- **Root cause:** the model sets `not_ready=true` whenever it is unsure. Same failure class as #4: a model flag drove a state change.
- **Change:** `not_ready` only counts if the customer's own words say so (`policy.not_ready_grounded`). 74 -> 78/80.

### 7. Invented credentials: "Yes, we are licensed and insured"
- **What happened:** `ook-licensed`. The numeric claim check could not see a non-numeric claim.
- **Change:** an FAQ answer must reuse the FAQ's words (`policy.answer_supported`). Echoing the customer's own question does not count as support (a unit test caught that bug in my first version).

### 8. Questions went unanswered
- **What happened:** `slot-question`. The model did not set `is_question`, so its answer was discarded. When it did answer, it sometimes returned an empty reply.
- **Change:** the code detects questions itself, and an empty answer triggers one focused FAQ-only call (`prompts/faq-answer.v1.md`).

### 9. My own guard broke a passing scenario
- **What happened:** the new overlap guard rejected "Yes, we serve Aurora." because the FAQ says "serves". `faq-5` regressed. Fixed by matching plain inflections. Lesson: every new guard needs the full suite re-run.

### Metric fix
- Escalation precision read 8/12 because four vague scenarios deliberately allow ESCALATE after two failed turns (spec rule). Allowed escalations are no longer counted as false alarms.

### Caveat
80/80 was reached by iterating against these same 80 scenarios, written by me, on one 8B model. Expect lower on unseen phrasing. A held-out set and a second model are the honest next test.


## Outbound copywriter (Phase 1)

Eval: `evals/outreach_runner.py`, 8 fictional prospects, first-try output, no retries. Report: `evals/reports/outreach-copy.v2.md`.

### 10. First prompt: 0/8 first try, but the retry hid it
- **What happened:** the first draft prompt (JSON with subject and body) failed the checks on every prospect: reviews mentioned with no review signal, numbers not in the facts, sender introduced twice, no paragraphs. The drafts I read in the dashboard looked fine only because the retry loop fixed them.
- **Lesson:** measure first-try output, not the output after retries, or the retry loop covers up a weak prompt.

### 11. A second prompt got worse: the model stopped returning JSON
- **What happened:** adding a four-block structure to the prompt made the model write the plain email and ignore "reply with JSON" (0/8 parseable).
- **Root cause:** asking an 8B model for structured copy and structured output at once.
- **Change:** the model now writes only the plain-text body. The code writes the subject and the signature, and strips any sign-off the model adds. 0/8 became 5/8, then 7/8.

### 12. Invented social proof got past the first checks
- **What happened:** a draft said "it's used by veterinarians in various cities." Nothing in the facts supports that, and my first checks only looked at numbers and links.
- **Change:** claim patterns (used by, trusted by, our customers, proven, awards, and similar) are rejected.
- **Follow-up bug:** the new rule matched "your customers" because "your" contains "our". Fixed with a word boundary and a test for both directions.

### 13. Smaller catches
- The guard rejected "24/7" as a number not in the facts. That is correct: we cannot promise it.
- My eval deduplicated by keeping the last duplicate row, which was a stripped copy with no reviews, so one scenario failed for a reason that had nothing to do with the model.
- `draft_pending` and `send_due` acted on every prospect in the database. They are now scoped by campaign, which also makes the tests isolated.


## First real scrape (Google Maps scraper, 20 dental clinics, one city)

### 14. My importer had never seen real data
- **What I assumed:** nested fields arrive as objects. **What arrived:** a CSV where hours, address, reviews and emails are JSON strings, so the importer would have silently dropped them.
- **Change:** `scraper.rows_from_csv` decodes those cells (and tolerates garbage without failing the row). The address now uses the scraper's own `city` field instead of guessing from the last comma, which would have given a postal code.

### 15. The review hook the outreach copy depends on mostly does not exist
- **What happened:** 0 of 20 businesses had two or more reviews about unanswered calls. The scraper returns about 5 reviews each, 76 of 96 were five-star, and the scraper's `extra_reviews` option returned nothing extra (the CLI log says "dropped 3 of 3 already present").
- **What the reviews did say:** scheduling mix-ups and long in-clinic waits, which are not the same problem as unanswered calls and which the copy must not claim.
- **Consequence:** the copywriter only mentions reviews when the signal is real, so most real drafts use the generic opening. Opening hours and web presence carry more weight than I expected.

### 16. Email is the wrong channel for this niche
- **What happened:** 5 of 20 had an email even with website crawling on, and 4 of those were free-mail addresses (personal data, scored lower and flagged). One business email in 20.
- **Consequence:** an email-first engine reaches about one in twenty here. The rest need a phone call or a Facebook message, and automated cold messages on those are restricted. A call list for the no-email prospects, with the score reasons as talking points, would be more useful than more email machinery.

### 17. Real data must not reach the public demo
- The static snapshot is built from the same database. It now exports only campaigns flagged `public_demo`; a check confirmed none of the 30 real businesses appear in it.


## Call list

### 18. A test that expired in the morning
- **What happened:** after adding the call-list tests, three older outreach tests started failing with nothing related changed. They had passed all day.
- **Root cause:** the tests used a fixed clock of 03:00 UTC on the day I wrote them, while approval stamps the message with the real database clock. Once real time passed 03:00 UTC, an approved message was scheduled "in the future" and never sent.
- **Change:** the fixed clock is now a Wednesday in 2030. That bug was in the committed tests, so anyone running them after 03:00 UTC that day would have seen failures that looked like product bugs.
