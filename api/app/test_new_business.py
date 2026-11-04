"""scripts/new_business.py: pure pieces and main() with fakes. No real LLM smoke runs here."""
import uuid

import pytest

from scripts import new_business as nb

from . import db, faq, llm, tools
from .config import settings
from .pack import PackError, get_pack
from .test_isolation import _hash_vec, _mk_tenant, _texts


def sc(i, cat):
    return {"id": i, "category": cat}


def test_select_smoke_keeps_only_escalation_and_injection():
    got = nb.select_smoke([sc("a", "faq"), sc("e", "escalation"), sc("i", "injection"), sc("q", "qualified")])
    assert [s["id"] for s in got] == ["e", "i"]


def test_select_smoke_requires_both_categories():
    with pytest.raises(nb.SmokeError, match="pack has no escalation scenarios"):
        nb.select_smoke([sc("i", "injection")])
    with pytest.raises(nb.SmokeError, match="pack has no injection scenarios"):
        nb.select_smoke([sc("e", "escalation")])


def test_evaluate_lists_failing_ids():
    res = [(sc("ok", "escalation"), None, []), (sc("bad", "injection"), None, ["x"])]
    assert nb.evaluate(res) == ["bad"]
    assert nb.evaluate(res[:1]) == []


def test_reminder_has_env_name_and_tenant_id_only():
    out = nb.reminder("abc-123")
    assert "TENANT_API_KEYS" in out and "abc-123" in out and "make gen-docs" in out
    assert "rd_live_" not in out


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(settings, "mail_transport", settings.mail_transport)  # main() flips it; restore after
    calls = {"local": 0, "runs": []}
    scs = [sc("e1", "escalation"), sc("i1", "injection"), sc("f1", "faq")]
    monkeypatch.setattr(nb, "load_pack", lambda s: None)
    monkeypatch.setattr(nb, "ensure_tenant", lambda s: "tid")
    monkeypatch.setattr(nb, "ensure_slots", lambda t: None)
    monkeypatch.setattr(nb, "sync_faq", lambda t: None)
    monkeypatch.setattr(nb, "load_scenarios", lambda s: scs)
    monkeypatch.setattr(nb, "assert_local_only", lambda c, t: calls.__setitem__("local", calls["local"] + 1))
    monkeypatch.setattr(nb, "cross_tenant_check", lambda t: [])
    monkeypatch.setattr(nb.runner, "write_report", lambda *a, **k: pytest.fail("write_report must not be called"))
    return calls


def fake_suite(fail_ids=()):
    def run(scenarios, t):
        return [(s, None, ["boom"] if s["id"] in fail_ids else []) for s in scenarios], ["cid"]
    return run


def test_main_pass(monkeypatch, fakes, capsys):
    monkeypatch.setattr(nb, "run_suite", fake_suite())
    assert nb.main("some-pack") == 0
    assert fakes["local"] >= 1 and "TENANT_API_KEYS" in capsys.readouterr().out


def test_main_fail_lists_id_and_reruns_once(monkeypatch, fakes, capsys):
    seen = []
    base = fake_suite({"i1"})

    def run(scenarios, t):
        seen.append([s["id"] for s in scenarios])
        return base(scenarios, t)
    monkeypatch.setattr(nb, "run_suite", run)
    assert nb.main("some-pack") == 1
    assert seen == [["e1", "i1"], ["i1"]]  # only the failing id is rerun, once
    assert "i1" in capsys.readouterr().out


def test_main_rerun_can_rescue_a_flake(monkeypatch, fakes):
    n = {"c": 0}

    def run(scenarios, t):
        n["c"] += 1
        return fake_suite({"i1"} if n["c"] == 1 else ())(scenarios, t)
    monkeypatch.setattr(nb, "run_suite", run)
    assert nb.main("some-pack") == 0


def test_main_pack_error(monkeypatch, fakes, capsys):
    def boom(s):
        raise PackError("bad pack text")
    monkeypatch.setattr(nb, "load_pack", boom)
    assert nb.main("some-pack") == 1
    assert "bad pack text" in capsys.readouterr().out


def test_main_rejects_unsafe_slug(fakes, capsys):
    assert nb.main("../etc") == 2


def test_main_no_escalation_fails(monkeypatch, fakes, capsys):
    monkeypatch.setattr(nb, "load_scenarios", lambda s: [sc("i1", "injection")])
    assert nb.main("some-pack") == 1
    assert "pack has no escalation scenarios" in capsys.readouterr().out


def test_main_cross_tenant_failure(monkeypatch, fakes, capsys):
    monkeypatch.setattr(nb, "run_suite", fake_suite())
    monkeypatch.setattr(nb, "cross_tenant_check", lambda t: ["leak!"])
    assert nb.main("some-pack") == 1
    assert "leak!" in capsys.readouterr().out


@pytest.fixture
def pair(monkeypatch):
    monkeypatch.setattr(llm, "embed", _hash_vec)
    n = uuid.uuid4().hex[:8]
    ids = (_mk_tenant(str(uuid.uuid4()), f"test-roofing-{n}", "summit-roofing"),
           _mk_tenant(str(uuid.uuid4()), f"test-dental-{n}", "bright-smile-dental"))
    for t in ids:
        faq.seed_faq(t, reload=True)
    return ids


def test_cross_tenant_check_passes(pair):
    assert nb.cross_tenant_check(pair[0]) == []
    assert nb.cross_tenant_check(pair[1]) == []


def test_cross_tenant_check_catches_foreign_chunk(pair, monkeypatch):
    real = tools.lookup_faq
    foreign = sorted(_texts(pair[1]))[0]
    monkeypatch.setattr(tools, "lookup_faq", lambda q, k=3, *, tenant_id: {"chunks": real(q, k, tenant_id=tenant_id)["chunks"] + [foreign]})
    assert nb.cross_tenant_check(pair[0])


def test_cross_tenant_check_not_vacuous(pair, monkeypatch):
    monkeypatch.setattr(tools, "lookup_faq", lambda q, k=3, *, tenant_id: {"chunks": []})
    assert nb.cross_tenant_check(pair[0])
