import pytest
from sqlalchemy import text

from .db import engine

CONVO_CHILDREN = ("events", "escalations", "tool_calls", "llm_calls", "messages")


def _max(c, table: str) -> int:
    return c.execute(text(f"SELECT COALESCE(max(id), 0) FROM {table}")).scalar()


@pytest.fixture(scope="session", autouse=True)
def remove_test_data():
    """Tests run against the dev database; delete what they created so dashboards and snapshots stay clean."""
    with engine.connect() as c:
        first = {t: _max(c, t) for t in ("conversations", "prospects", "campaigns")}
    yield
    with engine.begin() as c:
        f = {"c": first["conversations"], "p": first["prospects"], "k": first["campaigns"]}
        for t in CONVO_CHILDREN:
            c.execute(text(f"DELETE FROM {t} WHERE conversation_id > :c"), f)
        leads = [r[0] for r in c.execute(text("SELECT lead_id FROM conversations WHERE id > :c"), f)]
        c.execute(text("DELETE FROM conversations WHERE id > :c"), f)
        if leads:
            c.execute(text("DELETE FROM appointments WHERE lead_id = ANY(:l)"), {"l": leads})
            c.execute(text("DELETE FROM leads WHERE id = ANY(:l)"), {"l": leads})
        c.execute(text("DELETE FROM scrape_runs WHERE campaign_id > :k"), f)
        for t in ("prospect_events", "outreach_messages", "llm_calls"):
            c.execute(text(f"DELETE FROM {t} WHERE prospect_id > :p"), f)
        c.execute(text("DELETE FROM prospects WHERE id > :p"), f)
        c.execute(text("DELETE FROM campaigns WHERE id > :k"), f)
        c.execute(text("DELETE FROM suppressions WHERE email LIKE '%@outreach.test'"))
