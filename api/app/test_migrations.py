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
