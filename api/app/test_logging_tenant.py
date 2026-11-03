import logging

import pytest

from . import agent, llm
from .logctx import TenantFilter, current_tenant

FMT = "tenant=%(tenant_id)s %(message)s"
T = "00000000-0000-0000-0000-0000000000b4"


@pytest.fixture
def lines():
    out = []

    class H(logging.Handler):
        def emit(self, record):
            out.append(self.format(record))

    h = H()
    h.setFormatter(logging.Formatter(FMT))
    h.addFilter(TenantFilter())
    root = logging.getLogger()
    old = root.level
    root.addHandler(h)
    root.setLevel(logging.INFO)
    yield out
    root.removeHandler(h)
    root.setLevel(old)


def test_outside_turn_is_dash(lines):
    logging.getLogger("leadpilot.x").info("hi")
    assert lines == ["tenant=- hi"]


def test_inside_context_stamped_and_child_loggers(lines):
    tok = current_tenant.set(T)
    try:
        logging.getLogger("leadpilot.llm").info("call")
    finally:
        current_tenant.reset(tok)
    assert lines == [f"tenant={T} call"]


def test_handle_turn_stamps_and_resets(lines, monkeypatch):
    def fake(messages):
        logging.getLogger("leadpilot.llm").info("inside")
        return {"content": '{"reply":"x"}', "model": "f", "prompt_tokens": 1, "completion_tokens": 1, "latency_ms": 1}

    monkeypatch.setattr(llm, "chat", fake)
    monkeypatch.setattr(agent.tools.llm, "embed", lambda q: [0.1] * 384)
    from .db import system
    from sqlalchemy import text
    with system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone) VALUES (:t,'test-b4','B','UTC') ON CONFLICT DO NOTHING"), {"t": T})
    agent.handle_turn("hello", tenant_id=T)
    assert f"tenant={T} inside" in lines
    assert current_tenant.get() == "-"


def test_reset_when_handle_turn_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(agent, "_open", boom)
    with pytest.raises(RuntimeError):
        agent.handle_turn("hello", tenant_id=T)
    assert current_tenant.get() == "-"
