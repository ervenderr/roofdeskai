import pytest
from sqlalchemy import text

from .db import engine

CHILD_TABLES = ("events", "escalations", "tool_calls", "llm_calls", "messages")


@pytest.fixture(scope="session", autouse=True)
def remove_test_conversations():
    """Tests run against the dev database; delete what they created so dashboards and snapshots stay clean."""
    with engine.connect() as c:
        first = c.execute(text("SELECT COALESCE(max(id), 0) FROM conversations")).scalar()
    yield
    with engine.begin() as c:
        ids = {"f": first}
        for t in CHILD_TABLES:
            c.execute(text(f"DELETE FROM {t} WHERE conversation_id > :f"), ids)
        leads = [r[0] for r in c.execute(text("SELECT lead_id FROM conversations WHERE id > :f"), ids)]
        c.execute(text("DELETE FROM conversations WHERE id > :f"), ids)
        if leads:
            c.execute(text("DELETE FROM appointments WHERE lead_id = ANY(:l)"), {"l": leads})
            c.execute(text("DELETE FROM leads WHERE id = ANY(:l)"), {"l": leads})
