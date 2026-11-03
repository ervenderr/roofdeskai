import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .config import settings
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
        test_tenants = "(SELECT id FROM tenants WHERE slug LIKE 'test-%')"
        # agent_events is append-only: lift the trigger only inside this cleanup transaction.
        c.execute(text("ALTER TABLE agent_events DISABLE TRIGGER USER"))
        c.execute(text(f"DELETE FROM agent_events WHERE tenant_id IN {test_tenants}"))
        c.execute(text("ALTER TABLE agent_events ENABLE TRIGGER USER"))
        for t in ("appointments", "tool_calls", "escalations", "events", "llm_calls", "messages",
                  "conversations", "slots", "leads", "faq_chunks"):
            c.execute(text(f"DELETE FROM {t} WHERE tenant_id IN {test_tenants}"))
        c.execute(text("DO $$ BEGIN IF to_regclass('tenant_api_keys') IS NOT NULL THEN "
                       f"DELETE FROM tenant_api_keys WHERE tenant_id IN {test_tenants}; END IF; END $$"))
        c.execute(text("DELETE FROM tenants WHERE slug LIKE 'test-%'"))


@pytest.fixture(autouse=True)
def no_real_mail(monkeypatch):
    """The dev .env may point at a real mailbox; tests must never email anyone (mail tests patch their own transport)."""
    monkeypatch.setattr(settings, "mail_transport", "mailpit")


@pytest.fixture
def scratch_db():
    """Empty throwaway database inside the dev cluster; name is generated, never external input."""
    name = f"scratch_{uuid.uuid4().hex[:8]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text(f"CREATE DATABASE {name}"))
    eng = create_engine(make_url(settings.database_url).set(database=name))
    yield eng
    eng.dispose()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


@pytest.fixture(scope="module")
def roofing_pack():
    from .pack import load_pack
    return load_pack("summit-roofing")
