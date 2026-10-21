"""Dump what the dashboard shows to JSON so a static host can serve it (no API, no admin key).

    docker compose exec api python -m scripts.export_snapshot > dashboard/data/snapshot.json
"""
import json

from app import admin, outreach_routes


def main() -> None:
    conversations = admin.list_conversations(limit=500)
    prospects = outreach_routes.list_prospects(limit=500)
    out = {
        "metrics": admin.metrics(),
        "conversations": conversations,
        "details": {str(c["id"]): admin.get_conversation(c["id"]) for c in conversations},
        "prospects": prospects,
        "prospect_details": {str(p["id"]): outreach_routes.get_prospect(p["id"]) for p in prospects},
        "queue": outreach_routes.approval_queue(),
        "outreach_metrics": outreach_routes.outreach_metrics(),
    }
    print(json.dumps(out, default=str, indent=1))


if __name__ == "__main__":
    main()
