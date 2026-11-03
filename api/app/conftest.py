import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .config import settings
from .db import engine

CONVO_CHILDREN = ("events", "escalations", "tool_calls", "llm_calls", "messages")


def _max(c, table: str) -> int:
    return c.execute(text(f"SELECT COALESCE(max(id), 0) FROM {table}")).scalar()


@pytest.fixture(scope="session", autouse=True)
def apply_pending_migrations():
    """Idempotent: the dev DB may predate new migration files."""
    from .bootstrap import apply_migrations
    apply_migrations()


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
        # the demo-venue fixture tenant is test-owned too: its rows go, the tenant row goes only if nothing else references it
        fixture_tenants = "(SELECT id FROM tenants WHERE slug LIKE 'test-%' OR slug = 'demo-venue')"
        for t in ("drafts", "capacity_flags", "brief_runs", "intake_people"):
            c.execute(text(f"DELETE FROM {t} WHERE tenant_id IN {fixture_tenants}"))
        for t in ("appointments", "tool_calls", "escalations", "events", "llm_calls", "messages",
                  "conversations", "slots", "leads", "faq_chunks"):
            c.execute(text(f"DELETE FROM {t} WHERE tenant_id IN {test_tenants}"))
        c.execute(text("DO $$ BEGIN IF to_regclass('tenant_api_keys') IS NOT NULL THEN "
                       f"DELETE FROM tenant_api_keys WHERE tenant_id IN {test_tenants}; END IF; END $$"))
        c.execute(text("DELETE FROM tenants WHERE slug LIKE 'test-%'"))
        _drop_unreferenced_venue(c)


def _drop_unreferenced_venue(c) -> None:
    """Remove the demo-venue tenant row (and its keys) if no data table still references it; real tenants are never touched."""
    tid = c.execute(text("SELECT id FROM tenants WHERE slug = 'demo-venue'")).scalar()
    if tid is None:
        return
    refs = c.execute(text(
        "SELECT c.relname FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid "
        "WHERE k.contype = 'f' AND k.confrelid = 'tenants'::regclass")).scalars().all()
    for t in refs:
        if t != "tenant_api_keys" and c.execute(text(f"SELECT 1 FROM {t} WHERE tenant_id = :t LIMIT 1"), {"t": tid}).first():
            return
    c.execute(text("DELETE FROM tenant_api_keys WHERE tenant_id = :t"), {"t": tid})
    c.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tid})


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


@pytest.fixture
def packs_dir(tmp_path, monkeypatch):
    """Tmp businesses_dir holding copies of the real roofing pack and the demo-venue fixture pack (copied, not symlinked)."""
    real = settings.businesses_dir
    shutil.copytree(real / "summit-roofing", tmp_path / "summit-roofing", ignore=shutil.ignore_patterns("scenarios"))
    shutil.copytree(Path(__file__).parent / "tests_data" / "packs" / "demo-venue", tmp_path / "demo-venue")
    monkeypatch.setattr(settings, "businesses_dir", tmp_path)
    return tmp_path


@pytest.fixture
def venue_tenant(packs_dir):
    """Tenant id of the demo-venue fixture pack (tenant row slug 'demo-venue' persists in the dev DB)."""
    from .tenants import ensure_tenant
    return ensure_tenant("demo-venue")


@pytest.fixture
def roofing_tenant(packs_dir):
    from .tenants import ensure_tenant
    return ensure_tenant("summit-roofing")
