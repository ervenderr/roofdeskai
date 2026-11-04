"""Owner alert address: unchanged when present, a dash (never 'None') when a pack has no address."""
import pytest

from . import agent
from .config import settings
from .pack import load_pack


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(agent.mailer, "send", lambda to, s, b: out.append((to, s, b)))
    monkeypatch.setattr(settings, "owner_email", "owner@example.test")
    return out


def _alert(monkeypatch, sent, address):
    pack = load_pack("summit-roofing")
    monkeypatch.setattr(agent, "_row", lambda *a, **k: dict(
        name="Ann", phone="303-555-0142", email=None, address=address, service_type="repair"))
    agent._notify_booking(1, "W", settings.default_tenant_id, pack)
    return next(b for to, _, b in sent if to == "owner@example.test")


def test_address_present_is_byte_identical(monkeypatch, sent):
    assert _alert(monkeypatch, sent, "123 Test St") == (
        "Ann booked a free roof inspection for W.\nPhone: 303-555-0142\nEmail: -\n"
        "Address: 123 Test St\nNeed: repair")


def test_missing_address_is_a_dash(monkeypatch, sent):
    body = _alert(monkeypatch, sent, None)
    assert "Address: -" in body and "None" not in body
