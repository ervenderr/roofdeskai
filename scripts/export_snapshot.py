"""Dump what the dashboard shows to JSON so a static host can serve it (no API, no admin key).

    docker compose exec api python -m scripts.export_snapshot > dashboard/data/snapshot.json
"""
import json

from app import admin


def main() -> None:
    conversations = admin.list_conversations(limit=500)
    out = {
        "metrics": admin.metrics(),
        "conversations": conversations,
        "details": {str(c["id"]): admin.get_conversation(c["id"]) for c in conversations},
    }
    print(json.dumps(out, default=str, indent=1))


if __name__ == "__main__":
    main()
