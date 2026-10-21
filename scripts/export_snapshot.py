"""Dump what the dashboard shows to JSON so a static host can serve it (no API, no admin key).

    docker compose exec api python -m scripts.export_snapshot > dashboard/data/snapshot.json
"""
import json

from app import admin, outreach, outreach_routes


def main() -> None:
    conversations = admin.list_conversations(limit=500)
    # Real scraped businesses must never reach the public snapshot: only campaigns flagged public_demo are exported.
    demo = {c["id"] for c in outreach_routes.list_campaigns() if c["public_demo"]}
    prospects = [p for p in outreach_routes.list_prospects(limit=500) if p["campaign_id"] in demo]
    ids = {p["id"] for p in prospects}
    details = {str(p["id"]): outreach_routes.get_prospect(p["id"]) for p in prospects}
    by_status: dict[str, int] = {}
    for p in prospects:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1
    queue = [m for m in outreach_routes.approval_queue() if m["prospect_id"] in ids]
    sent = sum(1 for d in details.values() for m in d["messages"] if m["status"] == "sent")
    outreach_metrics = {"prospects": by_status, "messages": {"sent": sent, "drafted": len(queue)}, "awaiting_approval": len(queue),
                        "suppressed": sum(by_status.get(k, 0) for k in ("unsubscribed", "bounced", "not_interested"))}
    calls = [c for c in outreach.call_list(limit=500) if c["campaign_id"] in demo]
    metrics = admin.metrics()
    metrics.pop("outreach", None)  # counts every campaign, including real ones
    out = {
        "metrics": metrics,
        "conversations": conversations,
        "details": {str(c["id"]): admin.get_conversation(c["id"]) for c in conversations},
        "prospects": prospects,
        "prospect_details": details,
        "queue": queue,
        "outreach_metrics": outreach_metrics,
        "calls": calls,
    }
    print(json.dumps(out, default=str, indent=1))


if __name__ == "__main__":
    main()
