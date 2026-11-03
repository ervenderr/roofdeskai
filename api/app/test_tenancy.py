import uuid

import pytest
from sqlalchemy import create_engine, text

from .config import settings
from .db import system, tx

SETTING = text("SELECT current_setting('app.tenant_id', true)")


def test_tx_sets_tenant():
    t = str(uuid.uuid4())
    with tx(t) as c:
        assert c.execute(SETTING).scalar() == t


def test_tx_default_tenant():
    with tx() as c:
        assert c.execute(SETTING).scalar() == settings.default_tenant_id


def test_tx_rejects_bad_uuid():
    with pytest.raises(ValueError):
        with tx("not-a-uuid"):
            pytest.fail("body must not run")


def test_no_leak_on_reused_connection():
    eng = create_engine(settings.database_url, pool_size=1, max_overflow=0)
    try:
        with tx(str(uuid.uuid4()), eng=eng):
            pass
        with eng.begin() as c:
            assert not c.execute(SETTING).scalar()
        with system(eng=eng) as c:
            assert not c.execute(SETTING).scalar()
    finally:
        eng.dispose()
