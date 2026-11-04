"""OPS-05: docs/data-map.md must name every tenant table and the retention classification."""
import re
from pathlib import Path

from sqlalchemy import text

from . import db, retention

MAP = Path(__file__).resolve().parents[2] / "docs" / "data-map.md"
if not MAP.exists():  # container mount: /srv/docs
    MAP = Path("/srv/docs/data-map.md")

ANCHORS = ["D-04 override: agent_events kept", "best-effort", "contact_email", "synthetic", "Art. 9", "nFADP",
           "cross-border", "n8n", "needs review", "RETENTION_DAYS", "delete_subject"]


def _words(body: str) -> set[str]:
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body))


def test_every_tenant_table_and_retention_key_is_documented():
    with db.system() as c:
        tables = set(c.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'")).scalars())
    assert tables
    want = tables | {"tenants", "tenant_api_keys"} | set(retention.PURGED) | set(retention.KEPT)
    missing = want - _words(MAP.read_text())
    assert not missing, sorted(missing)


def test_caveat_anchors_present():
    body = MAP.read_text()
    assert [a for a in ANCHORS if a not in body] == []
