"""Outreach engine. The model drafts copy and classifies replies; code owns every status, cap and send."""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import text

from . import llm, mailer, prospects
from .config import settings
from .db import engine

log = logging.getLogger("leadpilot.outreach")

MAX_STEPS = 3
FOLLOWUP_DELAY_DAYS = {2: 3, 3: 7}  # days after the previous send
COPY_PROMPT, REPLY_PROMPT = "outreach-copy.v2", "outreach-reply.v1"
BANNED = re.compile(r"guarantee|100\s?%|free trial|risk[- ]free|act now|limited time|\$\s?\d|\d\s?%|#1|best in|"
                    r"as (we )?discussed|we spoke|our (call|chat|conversation)|following up on our|http|www\.|@|"
                    r"used by|trusted by|loved by|proven|case stud|award|years of experience|\b(our|other|many|several) "
                    r"(clients|customers)|clients like|(we|we've) (have )?(worked|helped)|helped (other|many)", re.I)
UNSUB_RE = re.compile(r"\b(unsubscribe|remove me|take me off|stop (emailing|contacting|sending)|do not (contact|email)|"
                      r"don'?t (contact|email))\b", re.I)
OOO_RE = re.compile(r"\b(out of (the )?office|automatic reply|auto-?reply|on (annual )?leave|on vacation)\b", re.I)


class Draft(BaseModel):
    subject: str = Field(min_length=3, max_length=70)
    body: str = Field(min_length=40, max_length=900)


class ReplyLabel(BaseModel):
    label: Literal["interested", "not_interested", "question", "out_of_office", "other"]


# --- copy -----------------------------------------------------------------------------------------

def localize(text_: str, locale: str) -> str:
    """US campaigns say 'inquiry'; the default copy uses 'enquiry'. Case is preserved."""
    if locale != "en-US":
        return text_
    return re.sub(r"\b([Ee])nquir(y|ies)\b", lambda m: ("I" if m.group(1) == "E" else "i") + "nquir" + m.group(2), text_)


def facts_for(p: dict) -> dict:
    city = p.get("city") or ((p.get("address") or "").split(",")[-1].strip() if "," in (p.get("address") or "") else None)
    f = {"name": p["name"], "category": p.get("category") or "local business", "city": city,
         "review_signal": (p.get("pain_mentions") or 0) >= 2, "has_website": bool(p.get("website"))}
    if p.get("rating"):
        f["rating"] = float(p["rating"])
    if p.get("review_count"):
        f["review_count"] = int(p["review_count"])
    return {k: v for k, v in f.items() if v is not None}


def check_draft(d: Draft, facts: dict) -> list[str]:
    """Rule checks on model copy. Empty list = acceptable."""
    issues, both = [], f"{d.subject} {d.body}"
    short = " ".join(facts["name"].split()[:2]).lower()  # the model may shorten "Smile Dental Clinic" to "Smile Dental"
    if short not in both.lower():
        issues.append("does not mention the business name")
    if BANNED.search(both):
        issues.append("contains a banned claim, link or contact detail")
    allowed = set(re.findall(r"\d+(?:\.\d+)?", f"{facts.get('rating', '')} {facts.get('review_count', '')}"))
    if any(n not in allowed for n in re.findall(r"\d+(?:\.\d+)?", both)):
        issues.append("contains a number that is not in the facts")
    if "review" in both.lower() and not facts["review_signal"]:
        issues.append("mentions reviews without a review signal")
    if len(d.body.split()) > 130:
        issues.append("too long")
    return issues


def template_draft(facts: dict, locale: str = "en-PH") -> Draft:
    kind = facts["category"].lower()
    where = f" in {facts['city']}" if facts.get("city") else ""
    return Draft(
        subject=f"A quick idea for {facts['name']}"[:70],
        body=localize(f"Hi {facts['name']} team,\n\nI came across {facts['name']}, a {kind}{where}. Many {kind} businesses lose "
                      f"enquiries that arrive when nobody is free to reply. We built {settings.offer_summary}.\n\n"
                      "Would it be worth a quick look at how it could work for you?", locale))


SIGNOFF_RE = re.compile(r"\n+\s*(best regards|kind regards|regards|sincerely|thanks|thank you|cheers|warm regards)\b.*$", re.I | re.S)


def subject_for(facts: dict) -> str:
    return f"A quick idea for {facts['name']}"[:70]


def parse_body(raw: str) -> str:
    """The model writes only the body. Strip code fences, a stray subject line or sign-off; the code owns both."""
    body = raw.strip().strip("`").strip()
    body = re.sub(r"^subject:.*\n+", "", body, flags=re.I)
    return SIGNOFF_RE.sub("", body).strip()


def _parse_json(raw: str) -> dict:
    a, b = raw.find("{"), raw.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no JSON object")
    return json.loads(raw[a:b + 1])


def draft_copy(p: dict, locale: str = "en-PH") -> tuple[Draft, str]:
    """LLM draft, one retry with the issues named, then the fixed template. Returns (draft, 'llm' | 'template')."""
    facts = facts_for(p)
    version, tpl = llm.load_prompt(COPY_PROMPT)
    system = (tpl.replace("<<sender>>", settings.sender_name).replace("<<offer>>", localize(settings.offer_summary, locale))
              .replace("<<facts>>", json.dumps(facts)))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": "Write the email."}]
    for _ in range(2):
        try:
            out = llm.chat(messages)
        except RuntimeError:
            log.warning("prospect %s: no LLM available, using the template", p["id"])
            break
        _log_llm(out, version, p["id"])
        try:
            d = Draft(subject=subject_for(facts), body=localize(parse_body(out["content"]), locale))
            issues = check_draft(d, facts)
        except ValueError as e:
            d, issues = None, [str(e).splitlines()[0][:120]]
        if d and not issues:
            return d, "llm"
        log.warning("prospect %s: draft rejected (%s)", p["id"], "; ".join(issues))
        messages += [{"role": "assistant", "content": out["content"]},
                     {"role": "user", "content": f"Rejected: {'; '.join(issues)}. Fix it and reply with ONLY the email body."}]
    return template_draft(facts, locale), "template"


def followup_copy(step: int, name: str, first_subject: str, locale: str = "en-PH") -> Draft:
    if step == 2:
        return Draft(subject=f"Re: {first_subject}"[:70], body=localize(
            f"Hi {name} team,\n\nJust floating my earlier note back to the top in case it got buried. "
            "Happy to show how it works in a few minutes if that would be useful.\n\nIf not, no worries at all.", locale))
    return Draft(subject=f"Last note: {first_subject}"[:70], body=localize(
        f"Hi {name} team,\n\nI'll stop here so I don't clutter your inbox. If handling customer enquiries ever "
        "becomes a headache, just reply and I'll send the details.", locale))


def with_footer(body: str, step: int = 2, locale: str = "en-PH") -> str:
    """Added by code at send time, so neither the model nor an edit can remove the opt-out.
    The first email also gets the fixed 'what it does' list (follow-ups stay short)."""
    if step == 1 and settings.service_points:
        points = "\n".join(f"  • {localize(pt, locale)}" for pt in settings.service_points)
        body = f"{body}\n\nWhat it does:\n{points}"
    return (f"{body}\n\n--\n{settings.sender_name}\n{settings.sender_address}\n"
            "Not interested? Reply \"unsubscribe\" and I won't contact you again.")


# --- workflow -------------------------------------------------------------------------------------

def _event(c, pid: int, kind: str, detail: str | None = None) -> None:
    c.execute(text("INSERT INTO prospect_events (prospect_id, kind, detail) VALUES (:p, :k, :d)"),
              {"p": pid, "k": kind, "d": detail})


def _log_llm(out: dict, version: str, pid: int) -> None:
    with engine.begin() as c:
        c.execute(text("INSERT INTO llm_calls (prospect_id, model, prompt_version, prompt_tokens, completion_tokens, "
                       "latency_ms) VALUES (:p, :m, :v, :pt, :ct, :l)"),
                  {"p": pid, "m": out["model"], "v": version, "pt": out["prompt_tokens"],
                   "ct": out["completion_tokens"], "l": out["latency_ms"]})


def draft_pending(limit: int = 5, campaign_id: int | None = None) -> dict:
    """Draft the first email for scored prospects in active campaigns. Campaign auto_approve skips the queue."""
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(text(
            """SELECT p.*, c.auto_approve, c.locale AS campaign_locale FROM prospects p JOIN campaigns c ON c.id = p.campaign_id
               WHERE p.status = 'scored' AND p.email IS NOT NULL AND c.active
                 AND (CAST(:cid AS INT) IS NULL OR p.campaign_id = :cid)
                 AND NOT EXISTS (SELECT 1 FROM suppressions s WHERE s.email = p.email)
               ORDER BY p.score DESC, p.id LIMIT :n"""), {"n": limit, "cid": campaign_id}).mappings()]
    drafted = approved = 0
    for p in rows:
        d, source = draft_copy(p, p["campaign_locale"])
        with engine.begin() as c:
            c.execute(text("""INSERT INTO outreach_messages (prospect_id, step, subject, body, source, status, scheduled_for)
                              VALUES (:p, 1, :s, :b, :src, :st, :when) ON CONFLICT (prospect_id, step) DO NOTHING"""),
                      {"p": p["id"], "s": d.subject, "b": d.body, "src": source,
                       "st": "approved" if p["auto_approve"] else "drafted", "when": datetime.now(timezone.utc) if p["auto_approve"] else None})
            prospects.set_status(p["id"], "drafted", c)
            if p["auto_approve"]:
                prospects.set_status(p["id"], "approved", c)
            _event(c, p["id"], "drafted", source)
        drafted += 1
        approved += bool(p["auto_approve"])
    return {"drafted": drafted, "auto_approved": approved, "awaiting_approval": drafted - approved}


def approve(mid: int) -> None:
    with engine.begin() as c:
        row = c.execute(text("UPDATE outreach_messages SET status='approved', scheduled_for=COALESCE(scheduled_for, now()) "
                             "WHERE id=:i AND status='drafted' RETURNING prospect_id, step"), {"i": mid}).first()
        if not row:
            raise LookupError("no drafted message with that id")
        if row.step == 1:
            prospects.set_status(row.prospect_id, "approved", c)
        _event(c, row.prospect_id, "approved", f"step {row.step}")


def reject(mid: int) -> None:
    with engine.begin() as c:
        row = c.execute(text("UPDATE outreach_messages SET status='rejected' WHERE id=:i AND status='drafted' "
                             "RETURNING prospect_id, step"), {"i": mid}).first()
        if not row:
            raise LookupError("no drafted message with that id")
        if row.step == 1:
            prospects.set_status(row.prospect_id, "skipped", c)
        _event(c, row.prospect_id, "rejected", f"step {row.step}")


def edit(mid: int, subject: str, body: str) -> None:
    d = Draft(subject=subject, body=body)  # same length rules; a human edit may say more than the model may
    with engine.begin() as c:
        if not c.execute(text("UPDATE outreach_messages SET subject=:s, body=:b, source='human' WHERE id=:i AND status='drafted' "
                              "RETURNING id"), {"i": mid, "s": d.subject, "b": d.body}).first():
            raise LookupError("no drafted message with that id")


def schedule_followups(now: datetime | None = None, campaign_id: int | None = None) -> dict:
    """Create the next sequence step for prospects who were emailed, have not replied, and are past the delay."""
    now = now or datetime.now(timezone.utc)
    made = 0
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(text(
            """SELECT p.id, p.name, p.email, cm.auto_approve, cm.locale,
                      (SELECT max(step) FROM outreach_messages WHERE prospect_id = p.id) AS last_step,
                      (SELECT subject FROM outreach_messages WHERE prospect_id = p.id AND step = 1) AS first_subject,
                      (SELECT max(sent_at) FROM outreach_messages WHERE prospect_id = p.id AND status = 'sent') AS last_sent
               FROM prospects p JOIN campaigns cm ON cm.id = p.campaign_id
               WHERE p.status = 'sent' AND cm.active AND (CAST(:cid AS INT) IS NULL OR p.campaign_id = :cid)
                 AND NOT EXISTS (SELECT 1 FROM suppressions s WHERE s.email = p.email)"""), {"cid": campaign_id}).mappings()]
    for p in rows:
        step = (p["last_step"] or 0) + 1
        delay = FOLLOWUP_DELAY_DAYS.get(step)
        if delay is None or step > MAX_STEPS or not p["last_sent"] or now < p["last_sent"] + timedelta(days=delay):
            continue
        with engine.begin() as c:
            if c.execute(text("SELECT 1 FROM outreach_messages WHERE prospect_id=:p AND status IN ('drafted','approved')"),
                         {"p": p["id"]}).first():
                continue  # the previous step is still waiting
            d = followup_copy(step, p["name"], p["first_subject"], p["locale"])
            c.execute(text("""INSERT INTO outreach_messages (prospect_id, step, subject, body, source, status, scheduled_for)
                              VALUES (:p, :st, :s, :b, 'template', :status, :when) ON CONFLICT (prospect_id, step) DO NOTHING"""),
                      {"p": p["id"], "st": step, "s": d.subject, "b": d.body,
                       "status": "approved" if p["auto_approve"] else "drafted", "when": now if p["auto_approve"] else None})
            _event(c, p["id"], "followup_drafted", f"step {step}")
        made += 1
    return {"followups_drafted": made}


def in_send_window(now: datetime, tz: str | None = None) -> bool:
    """Weekday business hours in the campaign's own timezone (a US campaign must not send at Manila's 9 to 5)."""
    start, end = (int(x) for x in settings.outreach_send_hours.split("-"))
    local = now.astimezone(ZoneInfo(tz or settings.outreach_timezone))
    return local.weekday() < 5 and start <= local.hour < end


def send_due(now: datetime | None = None, campaign_id: int | None = None) -> dict:
    """Send approved messages that are due. Every guard here is code: window, daily cap, suppression, status."""
    now = now or datetime.now(timezone.utc)
    result = {"sent": 0, "failed": 0, "skipped": {}, "window_open": True}
    day_starts: dict[str, datetime] = {}

    def skip(reason: str) -> None:
        result["skipped"][reason] = result["skipped"].get(reason, 0) + 1

    if not settings.sender_address:
        raise RuntimeError("SENDER_ADDRESS is not set; refusing to send mail without a postal address in the footer")
    with engine.connect() as c:
        due = [dict(r) for r in c.execute(text(
            """SELECT m.id, m.prospect_id, m.step, m.subject, m.body, p.email, p.status AS pstatus, p.campaign_id, cm.daily_cap, cm.timezone, cm.locale
               FROM outreach_messages m JOIN prospects p ON p.id = m.prospect_id JOIN campaigns cm ON cm.id = p.campaign_id
               WHERE m.status = 'approved' AND COALESCE(m.scheduled_for, now()) <= :now AND cm.active
                 AND (CAST(:cid AS INT) IS NULL OR p.campaign_id = :cid)
               ORDER BY m.scheduled_for NULLS FIRST, m.id"""), {"now": now, "cid": campaign_id}).mappings()]
    for m in due:
        if settings.outreach_enforce_window and not in_send_window(now, m["timezone"]):
            skip("outside_send_window")
            result["window_open"] = False
            continue
        day_start = day_starts.setdefault(m["timezone"], now.astimezone(ZoneInfo(m["timezone"])).replace(hour=0, minute=0, second=0, microsecond=0))
        with engine.begin() as c:
            if c.execute(text("SELECT 1 FROM suppressions WHERE email=:e"), {"e": m["email"]}).first():
                c.execute(text("UPDATE outreach_messages SET status='cancelled' WHERE id=:i"), {"i": m["id"]})
                skip("suppressed")
                continue
            if m["pstatus"] not in ("approved", "sent"):
                c.execute(text("UPDATE outreach_messages SET status='cancelled' WHERE id=:i"), {"i": m["id"]})
                skip("prospect_not_sendable")
                continue
            sent_today = c.execute(text(
                """SELECT count(*) FROM outreach_messages m JOIN prospects p ON p.id = m.prospect_id
                   WHERE p.campaign_id = :c AND m.status = 'sent' AND m.sent_at >= :d"""),
                {"c": m["campaign_id"], "d": day_start}).scalar()
            if sent_today >= m["daily_cap"]:
                skip("daily_cap_reached")
                continue
            try:
                mailer.send(m["email"], m["subject"], with_footer(m["body"], m["step"], m["locale"]))
            except mailer.MailError as e:
                c.execute(text("UPDATE outreach_messages SET status='failed', error=:e WHERE id=:i"), {"e": str(e), "i": m["id"]})
                _event(c, m["prospect_id"], "send_failed", str(e))
                result["failed"] += 1
                continue
            c.execute(text("UPDATE outreach_messages SET status='sent', sent_at=:n WHERE id=:i"), {"n": now, "i": m["id"]})
            if m["pstatus"] == "approved":
                prospects.set_status(m["prospect_id"], "sent", c)
            _event(c, m["prospect_id"], "sent", f"step {m['step']}")
            result["sent"] += 1
    return result


# --- replies, bounces, unsubscribes ----------------------------------------------------------------

def suppress(c, email: str, reason: str) -> None:
    c.execute(text("INSERT INTO suppressions (email, reason) VALUES (:e, :r) ON CONFLICT (email) DO NOTHING"),
              {"e": email.lower(), "r": reason})


def _cancel_pending(c, pid: int) -> None:
    c.execute(text("UPDATE outreach_messages SET status='cancelled' WHERE prospect_id=:p AND status IN ('drafted','approved')"),
              {"p": pid})


def classify_reply(body: str, pid: int) -> str:
    """Code decides the safety-critical labels first; the model only sorts the rest."""
    if UNSUB_RE.search(body):
        return "unsubscribe"
    if OOO_RE.search(body):
        return "out_of_office"
    version, tpl = llm.load_prompt(REPLY_PROMPT)
    try:
        out = llm.chat([{"role": "system", "content": tpl}, {"role": "user", "content": body[:2000]}])
        _log_llm(out, version, pid)
        return ReplyLabel.model_validate(_parse_json(out["content"])).label
    except (RuntimeError, ValueError):
        log.warning("prospect %s: reply could not be classified; leaving it for a human", pid)
        return "other"


def handle_event(email: str, kind: str, body: str = "") -> dict:
    email = email.strip().lower()
    with engine.connect() as c:
        p = c.execute(text("SELECT id, name, status FROM prospects WHERE email=:e ORDER BY id DESC LIMIT 1"), {"e": email}).mappings().first()
    if not p:
        return {"matched": False}
    pid = p["id"]
    label = {"bounce": "bounce", "unsubscribe": "unsubscribe"}.get(kind) or classify_reply(body, pid)
    with engine.begin() as c:
        if label in ("unsubscribe", "bounce"):
            suppress(c, email, label)
            _cancel_pending(c, pid)
            prospects.set_status(pid, "unsubscribed" if label == "unsubscribe" else "bounced", c)
        elif label == "out_of_office":
            pass  # not a real reply: the sequence carries on
        else:
            _cancel_pending(c, pid)
            if label == "not_interested":
                suppress(c, email, "not_interested")
            new = {"interested": "interested", "not_interested": "not_interested"}.get(label, "replied")
            if p["status"] in ("sent", "replied", "interested"):  # a reply to something we never sent is just logged
                try:
                    prospects.set_status(pid, new, c)
                except ValueError:  # e.g. an interested prospect asks another question: keep the stronger status
                    log.info("prospect %s: kept status %s on a %s reply", pid, p["status"], label)
        _event(c, pid, f"reply:{label}" if kind == "reply" else kind)
        status = c.execute(text("SELECT status FROM prospects WHERE id=:i"), {"i": pid}).scalar()
    return {"matched": True, "prospect_id": pid, "name": p["name"], "label": label, "status": status,
            "needs_human": label in ("interested", "question", "other")}


def record_call(pid: int, outcome: str, note: str = "") -> dict:
    """Log a phone call. A firm yes/no settles the prospect and stops any email; a no also suppresses their address."""
    if outcome not in prospects.CALL_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(prospects.CALL_OUTCOMES)}")
    with engine.begin() as c:
        row = c.execute(text("SELECT email FROM prospects WHERE id=:i FOR UPDATE"), {"i": pid}).first()
        if not row:
            raise LookupError("prospect not found")
        c.execute(text("UPDATE prospects SET call_outcome=:o, call_note=:n, called_at=now() WHERE id=:i"),
                  {"o": outcome, "n": note[:500] or None, "i": pid})
        _event(c, pid, f"call:{outcome}", note[:200] or None)
        if outcome in ("interested", "not_interested", "do_not_contact"):
            _cancel_pending(c, pid)
            if outcome != "interested" and row.email:
                suppress(c, row.email, outcome)
            try:
                prospects.set_status(pid, "interested" if outcome == "interested" else "not_interested", c)
            except ValueError:  # already unsubscribed, bounced or booked: keep that
                log.info("prospect %s: kept status after a %s call", pid, outcome)
        status = c.execute(text("SELECT status FROM prospects WHERE id=:i"), {"i": pid}).scalar()
    return {"prospect_id": pid, "outcome": outcome, "status": status}


def call_list(campaign_id: int | None = None, scope: str = "no_email", limit: int = 100) -> list[dict]:
    """Prospects worth phoning: have a phone, are still open, and were not settled by an earlier call.
    scope 'no_email' (default) is the ones email cannot reach; 'all' adds everyone still in play."""
    statuses = ("no_email",) if scope == "no_email" else ("no_email", "scored", "drafted", "approved", "sent", "replied")
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(text(
            """SELECT prospects.id, campaign_id, name, category, city, address, phone, email, website, maps_url, rating,
                      review_count, pain_mentions, hours_json, score, status, call_outcome, call_note, called_at,
                      (SELECT locale FROM campaigns WHERE campaigns.id = campaign_id) AS locale
               FROM prospects
               WHERE COALESCE(phone, '') <> '' AND status = ANY(:st)
                 AND (call_outcome IS NULL OR call_outcome IN ('no_answer', 'callback'))
                 AND (CAST(:cid AS INT) IS NULL OR campaign_id = :cid)
               ORDER BY score DESC, prospects.id LIMIT :n"""), {"st": list(statuses), "cid": campaign_id, "n": limit}).mappings()]
    for r in rows:
        r["talking_points"] = [localize(t, r["locale"]) for t in prospects.talking_points(r)]
        r["opener"] = localize(prospects.opener(r), r["locale"])
        r.pop("hours_json")
        r.pop("locale")
    return rows


def metrics() -> dict:
    with engine.connect() as c:
        by_status = {r[0]: r[1] for r in c.execute(text("SELECT status, count(*) FROM prospects GROUP BY status"))}
        msgs = {r[0]: r[1] for r in c.execute(text("SELECT status, count(*) FROM outreach_messages GROUP BY status"))}
        awaiting = msgs.get("drafted", 0)
        suppressed = c.execute(text("SELECT count(*) FROM suppressions")).scalar()
    return {"prospects": by_status, "messages": msgs, "awaiting_approval": awaiting, "suppressed": suppressed}
