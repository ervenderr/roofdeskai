import re
from pathlib import Path

import pytest
from sqlalchemy import text

from . import bootstrap
from .config import settings


def _baseline(eng):
    with eng.begin() as c:
        for f in ("init.sql", "outreach.sql"):
            c.exec_driver_sql((settings.db_dir / f).read_text())


def _versions(eng):
    with eng.begin() as c:
        return [r[0] for r in c.execute(text("SELECT version FROM schema_migrations ORDER BY 1"))]


def test_empty_db_gets_baseline_and_001(scratch_db):
    assert bootstrap.bootstrap_schema(scratch_db) is True
    assert "001_tenants" in _versions(scratch_db)


def test_existing_baseline_skips_baseline_applies_migrations(scratch_db):
    _baseline(scratch_db)
    assert bootstrap.bootstrap_schema(scratch_db) is False
    assert "001_tenants" in _versions(scratch_db)


def test_second_run_applies_nothing(scratch_db):
    bootstrap.bootstrap_schema(scratch_db)
    before = _versions(scratch_db)
    bootstrap.bootstrap_schema(scratch_db)
    assert _versions(scratch_db) == before


def test_missing_migrations_dir_raises(scratch_db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "db_dir", tmp_path)
    with pytest.raises(FileNotFoundError):
        bootstrap.apply_migrations(scratch_db)


def test_migration_filenames_sorted_unique():
    names = [p.name for p in (settings.db_dir / "migrations").glob("*.sql")]
    assert names and all(re.match(r"^\d{3}_", n) for n in names)
    prefixes = [n[:3] for n in sorted(names)]
    assert len(set(prefixes)) == len(prefixes)


def test_001_seeds_summit_tenant(scratch_db):
    bootstrap.bootstrap_schema(scratch_db)
    with scratch_db.begin() as c:
        row = c.execute(text("SELECT id::text, slug, timezone FROM tenants")).one()
    assert tuple(row) == (settings.default_tenant_id, "summit-roofing", "America/Denver")


def test_001_advances_faq_sequence(scratch_db):
    _baseline(scratch_db)
    with scratch_db.begin() as c:
        c.exec_driver_sql((Path(settings.db_dir) / "faq_seed.sql").read_text())
    bootstrap.bootstrap_schema(scratch_db)
    with scratch_db.begin() as c:
        nxt = c.execute(text("SELECT nextval(pg_get_serial_sequence('faq_chunks','id'))")).scalar()
        mx = c.execute(text("SELECT max(id) FROM faq_chunks")).scalar()
    assert nxt > mx


# ---- data-bearing upgrade (002-003) ----
def _seed_baseline(eng, dup=False):
    _baseline(eng)
    with eng.begin() as c:
        c.execute(text("DELETE FROM slots"))
        c.execute(text("INSERT INTO leads (name) VALUES ('l')"))
        c.execute(text("INSERT INTO conversations (lead_id, external_id) SELECT id, 'e' FROM leads"))
        c.execute(text("INSERT INTO messages (conversation_id, role, content) SELECT id, 'user', 'hi' FROM conversations"))
        c.execute(text("INSERT INTO llm_calls (conversation_id, model) SELECT id, 'm' FROM conversations"))
        c.execute(text("INSERT INTO llm_calls (model) VALUES ('outreach')"))
        c.execute(text("INSERT INTO slots (start_time, end_time) VALUES ('2030-01-01', '2030-01-01')"))
        if dup:
            c.execute(text("INSERT INTO slots (start_time, end_time) VALUES ('2030-01-01', '2030-01-01')"))


def test_upgrade_preserves_and_backfills(scratch_db):
    _seed_baseline(scratch_db)
    bootstrap.bootstrap_schema(scratch_db)
    with scratch_db.begin() as c:
        for t in ("leads", "conversations", "messages", "slots"):
            assert c.execute(text(f"SELECT count(*), count(*) FILTER (WHERE tenant_id=:d) FROM {t}"),
                             {"d": settings.default_tenant_id}).one() == (1, 1), t
        assert c.execute(text("SELECT count(*) FROM llm_calls WHERE tenant_id=:d"), {"d": settings.default_tenant_id}).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM llm_calls WHERE tenant_id IS NULL")).scalar() == 1


def test_duplicate_slots_abort_003(scratch_db):
    _seed_baseline(scratch_db, dup=True)
    with pytest.raises(Exception, match="duplicate slot"):
        bootstrap.bootstrap_schema(scratch_db)
    v = _versions(scratch_db)
    assert "002_tenant_columns" in v and "003_tenant_keys" not in v
    with scratch_db.begin() as c:
        assert c.execute(text("SELECT count(*) FROM slots")).scalar() == 2


def test_005_006_applied_idempotent_and_role_exists(scratch_db):
    bootstrap.bootstrap_schema(scratch_db)
    assert {"005_rls", "006_tenant_api_keys"} <= set(_versions(scratch_db))
    assert bootstrap.apply_migrations(scratch_db) == []
    with scratch_db.begin() as c:
        assert c.execute(text("SELECT count(*) FROM pg_roles WHERE rolname='app_rw'")).scalar() == 1
