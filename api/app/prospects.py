"""Prospects: import from the Google Maps scraper, score, and the status machine."""
import hashlib
import json
import re

from sqlalchemy import text

from .db import engine

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PAIN_RE = re.compile(
    r"(nobody|no ?one|never)\s+(answer|pick|call|return|got back|respond)|didn'?t\s+(answer|pick up|call back|return|respond)|"
    r"(hard|impossible|difficult) to (reach|get (a hold|hold|through))|goes to voicemail|unreturned|no (response|reply)|"
    r"ignored (my|our) (call|message|email)|never (called|answered|replied) (me )?back", re.I)
FREE_MAIL = ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "proton.me", "protonmail.com", "live.com")
TARGET_CATEGORIES = ("dent", "clinic", "roof", "hvac", "air con", "aircon", "plumb", "salon", "spa", "clean", "repair", "contractor")
TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")

# Allowed status moves. Unsubscribe and bounce are accepted from any state (see set_status).
# A phone call can settle a prospect at any stage, so interested / not_interested are allowed from the early ones too.
FLOW = {
    "scored": {"drafted", "skipped", "interested", "not_interested"}, "no_email": {"skipped", "interested", "not_interested"},
    "drafted": {"approved", "skipped", "interested", "not_interested"},
    "approved": {"sent", "drafted", "skipped", "interested", "not_interested"},
    "sent": {"replied", "interested", "not_interested", "bounced"},
    "replied": {"interested", "not_interested", "booked"}, "interested": {"booked", "not_interested"},
    "booked": set(), "not_interested": set(), "skipped": set(), "unsubscribed": set(), "bounced": set(),
}
ALWAYS_ALLOWED = {"unsubscribed", "bounced"}


def _clean(s: str) -> str:
    return re.sub(r"[   ]", " ", s)


def _text_of(v) -> str:
    return _clean(", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)).strip()


def normalize(row: dict) -> dict | None:
    """Map one scraper row to our columns. Shapes the scraper may vary (hours, reviews, address) are read
    defensively: anything unrecognised is dropped, never an exception. shortcut: field shapes inferred from the
    scraper docs, check against a real export."""
    name = (row.get("title") or "").strip()
    if not name:
        return None
    address = row.get("address") or row.get("complete_address") or ""
    if isinstance(address, dict):
        address = ", ".join(str(v) for v in address.values() if v)
    ca = row.get("complete_address")
    city = (ca.get("city") or "").strip()[:100] or None if isinstance(ca, dict) else None
    emails = row.get("emails") or row.get("email") or []
    emails = [emails] if isinstance(emails, str) else emails
    email = next((e.strip().lower() for e in emails if isinstance(e, str) and EMAIL_RE.match(e.strip())), None)
    hours = row.get("open_hours")
    hours = {str(d): _text_of(v) for d, v in hours.items()} if isinstance(hours, dict) else None
    reviews = []
    for r in row.get("user_reviews") or []:
        t = r if isinstance(r, str) else next((r.get(k) for k in ("Description", "description", "text", "Text") if isinstance(r, dict) and r.get(k)), "")
        if t:
            reviews.append(_clean(str(t))[:300])
    place = row.get("place_id") or row.get("cid") or row.get("data_id")
    try:
        rating = float(row["review_rating"]) if row.get("review_rating") not in (None, "") else None
        review_count = int(row["review_count"]) if row.get("review_count") not in (None, "") else None
    except (ValueError, TypeError):
        rating = review_count = None
    return {
        "external_id": str(place) if place else hashlib.sha1(f"{name}|{address}".lower().encode()).hexdigest(),
        "name": name[:200], "city": city, "category": (row.get("category") or "")[:100] or None, "address": str(address)[:300] or None,
        "phone": (row.get("phone") or "")[:40] or None, "email": email, "website": (row.get("website") or "")[:300] or None,
        "maps_url": (row.get("link") or "")[:500] or None, "rating": rating, "review_count": review_count,
        "hours": hours, "review_texts": reviews[:20],
    }


def pain_mentions(review_texts: list[str]) -> int:
    return sum(1 for t in review_texts if PAIN_RE.search(t))


def _close_hour(day_text: str) -> int | None:
    times = TIME_RE.findall(_clean(day_text))
    if not times or "closed" in day_text.lower():
        return None
    h, _, ap = times[-1]
    return int(h) % 12 + (12 if ap.lower() == "pm" else 0)


def after_hours_gap(hours: dict | None) -> bool:
    """True if closed on a weekend day, or closing by 6 PM on most weekdays (enquiries pile up unanswered)."""
    if not hours:
        return False
    low = {d.lower(): v for d, v in hours.items()}
    if any("closed" in low.get(d, "").lower() for d in ("saturday", "sunday")):
        return True
    closes = [_close_hour(low[d]) for d in WEEKDAYS if d in low]
    return sum(1 for c in closes if c is not None and c <= 18) >= 3


DAY_ORDER = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
CALL_OUTCOMES = {"no_answer", "callback", "wrong_number", "interested", "not_interested", "do_not_contact"}


def closed_days(hours: dict | None) -> list[str]:
    low = {d.lower(): v for d, v in (hours or {}).items()}
    return [d for d in DAY_ORDER if "closed" in low.get(d.lower(), "").lower()]


def talking_points(p: dict) -> list[str]:
    """Plain-language reasons to call, built only from the scraped facts (no model, nothing invented)."""
    pts = []
    closed = closed_days(p.get("hours") or p.get("hours_json"))
    if closed:
        pts.append(f"Closed on {', '.join(closed)}: enquiries arriving then go unanswered.")
    elif after_hours_gap(p.get("hours") or p.get("hours_json")):
        pts.append("Closes early on weekdays, so evening enquiries wait until the next day.")
    if (p.get("pain_mentions") or 0) >= 1:
        pts.append("A customer review mentions an unanswered call or message.")
    if (p.get("review_count") or 0) >= 50:
        pts.append(f"Busy: {p['review_count']} reviews" + (f", rated {float(p['rating']):.1f}." if p.get("rating") else "."))
    if not p.get("website"):
        pts.append("No website, so customers can only reach them by phone or social media.")
    elif not p.get("email"):
        pts.append("Has a website but no public email.")
    return pts[:4]


def opener(p: dict) -> str:
    return (f"Hi, is this {p['name']}? I'll be quick: when your team is busy or you are closed, who answers customer "
            "enquiries? We built an AI assistant that replies instantly and books appointments. Would a ten minute "
            "look be worth it?")


def score(p: dict) -> tuple[int, list[str]]:
    reasons, s = [], 0
    if p.get("email"):
        if p["email"].rsplit("@", 1)[-1] in FREE_MAIL:  # likely a person, not a business: personal data, so weigh less and flag it
            s += 5; reasons.append("free-mail address (a person's inbox: review before contacting)")
        else:
            s += 25; reasons.append("has a business email")
    if p.get("website"):
        s += 10; reasons.append("has a website")
    rc = p.get("review_count") or 0
    if rc >= 20:
        s += 15; reasons.append(f"{rc} reviews (a busy business)")
    elif rc >= 5:
        s += 5
    if (p.get("rating") or 0) >= 4.0:
        s += 10; reasons.append(f"rated {p['rating']}")
    pm = pain_mentions(p.get("review_texts") or [])
    if pm >= 2:
        s += 25; reasons.append(f"{pm} reviews mention unanswered calls or messages")
    elif pm == 1:
        s += 10; reasons.append("1 review mentions an unanswered call")
    if after_hours_gap(p.get("hours")):
        s += 10; reasons.append("closed evenings or weekends")
    if any(k in (p.get("category") or "").lower() for k in TARGET_CATEGORIES):
        s += 5; reasons.append("target category")
    return min(s, 100), reasons


def import_rows(campaign_id: int, rows: list[dict]) -> dict:
    out = {"imported": 0, "duplicates": 0, "invalid": 0, "no_email": 0}
    with engine.begin() as c:
        for row in rows:
            p = normalize(row) if isinstance(row, dict) else None
            if not p:
                out["invalid"] += 1
                continue
            sc, reasons = score({**p, "review_texts": p["review_texts"]})
            suppressed = p["email"] and c.execute(text("SELECT 1 FROM suppressions WHERE email=:e"), {"e": p["email"]}).first()
            status = "skipped" if suppressed else ("scored" if p["email"] else "no_email")
            r = c.execute(text("""INSERT INTO prospects (campaign_id, external_id, name, city, category, address, phone, email, website,
                    maps_url, rating, review_count, hours_json, review_texts, score, score_reasons, pain_mentions, status)
                VALUES (:cid, :external_id, :name, :city, :category, :address, :phone, :email, :website, :maps_url, :rating,
                    :review_count, CAST(:hours AS jsonb), CAST(:reviews AS jsonb), :score, CAST(:reasons AS jsonb), :pm, :status)
                ON CONFLICT (external_id) DO NOTHING RETURNING id"""),
                {**p, "cid": campaign_id, "hours": json.dumps(p["hours"]), "reviews": json.dumps(p["review_texts"]),
                 "score": sc, "reasons": json.dumps(reasons), "pm": pain_mentions(p["review_texts"]), "status": status}).first()
            if not r:
                out["duplicates"] += 1
            else:
                out["imported"] += 1
                out["no_email"] += status == "no_email"
    return out


def set_status(pid: int, new: str, conn=None) -> None:
    """Move a prospect along FLOW. Raises ValueError on an illegal move (a bug, not user input)."""
    def run(c):
        cur = c.execute(text("SELECT status FROM prospects WHERE id=:i FOR UPDATE"), {"i": pid}).scalar()
        if cur is None:
            raise LookupError("prospect not found")
        if cur == new:
            return
        if new not in FLOW[cur] and new not in ALWAYS_ALLOWED:
            raise ValueError(f"illegal status move {cur} -> {new}")
        c.execute(text("UPDATE prospects SET status=:s WHERE id=:i"), {"s": new, "i": pid})
    if conn is not None:
        run(conn)
    else:
        with engine.begin() as c:
            run(c)
