"""Run the platform flows without a workflow engine: the same API call sequences as the scheduled and webhook
workflows, mail through app.mailer. Env: API_URL, ADMIN_API_KEY (GET /admin/tenants only), TENANT_API_KEYS."""
import json
import os
import sys

from app import mailer

NEW_FLAGS = ("new", "reflagged")


def _k(keys: dict, tid: str) -> dict:
    return {"X-API-Key": keys[tid]}


def _ok(r):
    r.raise_for_status()
    return r.json()


def _tenants(client, admin_key: str, keys: dict) -> list[dict]:
    rows = _ok(client.get("/admin/tenants", headers={"X-Admin-Key": admin_key}))
    return [t for t in rows if t["id"] in keys]  # a tenant without a key is skipped, like the workflows


def _me(client, keys: dict, tid: str) -> dict:
    return _ok(client.get("/tenant/me", headers=_k(keys, tid)))


def escalation_alert(client, keys, mail, tid, conversation_id, reason, link) -> None:
    owner = _me(client, keys, tid).get("owner_email")
    if not owner:
        raise RuntimeError(f"tenant {tid} has no owner email")
    mail(owner, f"Escalation ({reason}): conversation {conversation_id}", f"A customer needs a human.\nConversation: {link}")


def inbound(client, keys, mail, tid, contact_id, message, channel="sms", message_id=None) -> dict:
    body = {"contact_id": contact_id, "message": message, "channel": channel, "message_id": message_id}
    d = _ok(client.post("/webhooks/inbound", json=body, headers=_k(keys, tid)))
    if d.get("outcome") == "escalated" and d.get("escalation_reason") and not d.get("duplicate"):
        escalation_alert(client, keys, mail, tid, d["conversation_id"], d["escalation_reason"], d["link"])
    elif d.get("outcome") == "booked" and d.get("email") and not d.get("duplicate"):
        mail(d["email"], "Your appointment is booked",
             f"Hi {d.get('name') or 'there'},\n\nYour appointment is booked for {d['appointment_start']}.\n\n{_me(client, keys, tid)['name']}")
    return d


def followups(client, admin_key, keys, mail) -> int:
    n = 0
    for t in _tenants(client, admin_key, keys):
        for due in _ok(client.get("/admin/followups/due?hours=48", headers=_k(keys, t["id"]))):
            d = _ok(client.post(f"/admin/followups/{due['conversation_id']}/draft", headers=_k(keys, t["id"])))
            mail(d["to"], d["subject"], d["body"])
            n += 1
    return n


def daily_brief(client, admin_key, keys, mail) -> int:
    n = 0
    for t in _tenants(client, admin_key, keys):
        me = _me(client, keys, t["id"])
        if "connectors" not in me["enabled_modules"] or not me["owner_email"]:
            continue
        if not _ok(client.post("/daily-brief/due", headers=_k(keys, t["id"])))["due"]:
            continue
        b = _ok(client.post("/daily-brief", headers=_k(keys, t["id"])))
        mail(me["owner_email"], f"Daily brief {b['local_date']}: {me['name']}", b["text"], b.get("html"))
        n += 1
    return n


def capacity_nightly(client, admin_key, keys, mail) -> int:
    n = 0
    for t in _tenants(client, admin_key, keys):
        me = _me(client, keys, t["id"])
        if "capacity" not in me["enabled_modules"] or not me["owner_email"]:
            continue
        r = client.post("/capacity/check", json={}, headers=_k(keys, t["id"]))
        flags = [f for f in (r.json().get("flags", []) if r.status_code == 200 else []) if f["status"] in NEW_FLAGS]
        if flags:
            lines = [f"{f['date']} {f['shift_id']}: staff {f['staff']}, covers {f['covers']}, capacity {f['capacity']} [{f['status']}]" for f in flags]
            mail(me["owner_email"], f"Capacity flags: {len(flags)}", f"Capacity flags ({len(flags)}):\n" + "\n".join(lines))
            n += 1
    return n


def send_approved(client, keys, mail, admin_key=None) -> int:
    """Mail approved quote drafts to the customer and review replies to the owner, then mark them sent."""
    n = 0
    for tid in keys:
        me = _me(client, keys, tid)
        for kind in ("quote", "review_reply"):
            for d in _ok(client.get(f"/drafts?status=approved&kind={kind}", headers=_k(keys, tid))):
                p = d["payload"]
                if kind == "quote":
                    to, subject, body = p.get("contact_email"), f"Your quote from {me['name']}", p.get("email_text")
                else:
                    to, subject, body = me["owner_email"], f"Approved review reply #{d['id']} (paste into the review site)", p.get("reply_text")
                if not to or not body:
                    continue  # stays approved
                mail(to, subject, body)
                _ok(client.post(f"/drafts/{d['id']}/sent", headers=_k(keys, tid)))
                n += 1
    return n


def main(argv: list[str]) -> None:
    import httpx
    client = httpx.Client(base_url=os.environ.get("API_URL", "http://localhost:8000"), timeout=130)
    admin, keys = os.environ.get("ADMIN_API_KEY", ""), json.loads(os.environ.get("TENANT_API_KEYS") or "{}")
    steps = {"followups": lambda: followups(client, admin, keys, mailer.send),
             "daily_brief": lambda: daily_brief(client, admin, keys, mailer.send),
             "capacity_nightly": lambda: capacity_nightly(client, admin, keys, mailer.send),
             "send_approved": lambda: send_approved(client, keys, mailer.send)}
    for name in argv or steps:
        print(f"{name}: {steps[name]()} sent")


if __name__ == "__main__":
    main(sys.argv[1:])
