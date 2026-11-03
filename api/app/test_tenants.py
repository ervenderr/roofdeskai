import shutil

import pytest
import yaml
from sqlalchemy import text

from . import db, faq
from .config import settings
from .pack import PackError
from .tenants import ensure_tenant, sync_faq

VEC = [0.1] * 384


def _tenant_count() -> int:
    with db.system() as c:
        return c.execute(text("SELECT count(*) FROM tenants")).scalar()


@pytest.fixture
def biz(tmp_path, monkeypatch):
    real = settings.businesses_dir / "summit-roofing"
    monkeypatch.setattr(settings, "businesses_dir", tmp_path)
    shutil.copytree(real, tmp_path / "summit-roofing")
    return tmp_path


def _clone(biz, slug):
    shutil.copytree(biz / "summit-roofing", biz / slug)
    f = biz / slug / "pack.yaml"
    d = yaml.safe_load(f.read_text())
    f.write_text(yaml.safe_dump({**d, "slug": slug}, sort_keys=False))


def test_roofing_returns_default_id_and_writes_nothing(biz):
    n = _tenant_count()
    assert ensure_tenant("summit-roofing") == str(settings.default_tenant_id)
    assert _tenant_count() == n


def test_new_pack_creates_tenant_idempotently(biz):
    _clone(biz, "test-ens")
    a = ensure_tenant("test-ens")
    assert ensure_tenant("test-ens") == a
    with db.system() as c:
        row = c.execute(text("SELECT pack_slug FROM tenants WHERE id=:i"), {"i": a}).one()
    assert row.pack_slug == "test-ens"


def test_bad_pack_raises_before_insert(biz):
    n = _tenant_count()
    with pytest.raises(PackError):
        ensure_tenant("test-no-such-pack")
    assert _tenant_count() == n


def test_tenant_bound_to_other_pack_raises(biz):
    _clone(biz, "test-ens2")
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (slug, name, timezone, pack_slug) VALUES ('test-ens2','x','UTC','summit-roofing')"))
    with pytest.raises(PackError):
        ensure_tenant("test-ens2")


def test_sync_faq_noop_then_reseed(biz, monkeypatch):
    _clone(biz, "test-ens3")
    t = ensure_tenant("test-ens3")
    monkeypatch.setattr(faq.llm, "embed", lambda x: VEC)
    sync_faq(t)  # empty -> seeds
    with db.tx(t) as c:
        ids = sorted(r[0] for r in c.execute(text("SELECT id FROM faq_chunks WHERE tenant_id=:t"), {"t": t}))
    assert len(ids) == 12
    sync_faq(t)  # equal -> no-op, same row ids
    with db.tx(t) as c:
        assert sorted(r[0] for r in c.execute(text("SELECT id FROM faq_chunks WHERE tenant_id=:t"), {"t": t})) == ids
    with db.tx(t) as c:
        c.execute(text("UPDATE faq_chunks SET text='stale' WHERE id=:i"), {"i": ids[0]})
    sync_faq(t)  # differs -> reload
    with db.tx(t) as c:
        texts = [r[0] for r in c.execute(text("SELECT text FROM faq_chunks WHERE tenant_id=:t"), {"t": t})]
    assert len(texts) == 12 and "stale" not in texts
