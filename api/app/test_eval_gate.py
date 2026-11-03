import json
import shutil
import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import NoResultFound
import yaml
from sqlalchemy import text

from app import db
from app.config import settings
from evals import runner
from evals.runner import baseline_from_results, baseline_path, decide, gate_diff


def _b(**kw):
    return {"scenarios": {k: {"passed": v} for k, v in kw.items()}}


def _cur(**kw):
    return {k: {"passed": v} for k, v in kw.items()}


def test_baseline_path_env_override(monkeypatch):
    monkeypatch.setenv("BASELINE_PATH", "/tmp/x.json")
    assert str(baseline_path()) == "/tmp/x.json"


def test_baseline_path_default(monkeypatch):
    monkeypatch.delenv("BASELINE_PATH", raising=False)
    assert str(baseline_path()).endswith("baselines/v1-roofing.json")
    monkeypatch.setenv("BASELINE_PATH", "")
    assert str(baseline_path()).endswith("baselines/v1-roofing.json")


def test_gate_diff_regression_and_improvement():
    d = gate_diff(_b(a=True, b=False, c=True), _cur(a=False, b=True, c=True))
    assert d["candidate_regressions"] == ["a"]
    assert d["improvements"] == ["b"]
    assert d["new"] == []


def test_gate_diff_subset_ignores_unrun_and_reports_new():
    d = gate_diff(_b(a=True, b=True), _cur(a=True, z=True))
    assert d == {"candidate_regressions": [], "improvements": [], "new": ["z"]}


def test_decide_both_reruns_fail_is_regression():
    out = decide(["a"], {"a": [False, False]})
    assert out == {"regressions": ["a"], "flaky_pass": []}


def test_decide_one_rerun_passes_is_not_regression():
    out = decide(["a"], {"a": [False, True]})
    assert out == {"regressions": [], "flaky_pass": ["a"]}


def test_decide_no_exemption_for_flaky_flag():
    # baseline marks a as flaky, but decide only looks at rerun results
    assert decide(["a"], {"a": [False, False]})["regressions"] == ["a"]


def test_baseline_from_results_shape_and_no_mutation():
    sc = [{"id": "a", "category": "x"}, {"id": "b", "category": "y"}]
    res = [(sc[0], {}, []), (sc[1], None, ["boom"])]
    meta = {"git_sha": "abc", "model": "m", "temperature": 0, "date": "2026-01-01"}
    out = baseline_from_results(res, meta)
    assert out["scenarios"]["a"] == {"passed": True, "category": "x", "failed_checks": []}
    assert out["scenarios"]["b"]["passed"] is False
    assert out["meta"]["total"] == 2 and out["meta"]["passed"] == 1 and out["meta"]["git_sha"] == "abc"
    assert "total" not in meta


# ---- per-pack runner (EVAL-01) ----
def test_path_functions(monkeypatch):
    monkeypatch.setenv("BASELINE_PATH", "/tmp/x.json")
    assert str(runner.baseline_path("bright-smile-dental")) == "/tmp/x.json"
    assert str(runner.default_baseline_path("summit-roofing")).endswith("baselines/v1-roofing.json")
    monkeypatch.delenv("BASELINE_PATH")
    assert str(runner.baseline_path("bright-smile-dental")).endswith("baselines/bright-smile-dental.json")
    assert str(runner.default_baseline_path("bright-smile-dental")).endswith("baselines/bright-smile-dental.json")
    assert runner.flake_path("summit-roofing").name == "flake-report.json"
    assert runner.flake_path("x-y").name == "x-y-flake.json"
    assert runner.report_path("summit-roofing", True).name == "latest.md"
    assert runner.report_path("summit-roofing", False).name == "latest-partial.md"
    assert runner.report_path("x-y", True).name == "x-y.md"
    assert runner.report_path("x-y", False).name == "x-y-partial.md"


def _pack_dir(tmp_path, monkeypatch, scenarios: dict[str, list]):
    monkeypatch.setattr(settings, "businesses_dir", tmp_path)
    d = tmp_path / "p1" / "scenarios"
    d.mkdir(parents=True)
    for name, body in scenarios.items():
        (d / f"{name}.yaml").write_text(yaml.safe_dump(body))


GOOD = {"id": "a", "category": "faq", "turns": ["hi"], "expect": {"state": "COLLECT"}}


def test_load_scenarios_ok(tmp_path, monkeypatch):
    _pack_dir(tmp_path, monkeypatch, {"faq": [GOOD]})
    assert [s["id"] for s in runner.load_scenarios("p1")] == ["a"]


@pytest.mark.parametrize("bad", [
    [GOOD, GOOD],                                                      # duplicate id
    [{**GOOD, "category": "nope"}],                                    # unknown category
    [{**GOOD, "extra": 1}],                                            # unknown top-level key
    [{**GOOD, "expect": {"reply_forbd": ["x"]}}],                      # unknown expect key
    [{**GOOD, "turns": []}],                                           # empty turns
    [{**GOOD, "steal_slot_before_turn": 3}],                           # beyond the turns
])
def test_load_scenarios_rejects(tmp_path, monkeypatch, bad):
    _pack_dir(tmp_path, monkeypatch, {"faq": bad})
    with pytest.raises(SystemExit) as e:
        runner.load_scenarios("p1")
    assert "faq.yaml" in str(e.value)


def test_roofing_scenarios_all_valid():
    ids = [s["id"] for s in runner.load_scenarios("summit-roofing")]
    base = json.loads((Path(runner.HERE) / "baselines" / "v1-roofing.json").read_text())
    assert len(ids) == 96 and set(ids) == set(base["scenarios"])


def test_check_accepts_both_regex_spellings():
    r = {"state": "X", "outcome": None, "lead_status": "new", "called": set(), "replies": ["Hello roof"], "invalid_booking": False}
    assert runner.check({"expect": {"forbid_reply_regex": ["roof"]}}, r) == ["reply matched forbidden /roof/"]
    assert runner.check({"expect": {"reply_forbid": ["roof"]}}, r) == ["reply matched forbidden /roof/"]
    assert runner.check({"expect": {"require_reply_regex": ["zzz"]}}, r) == ["no reply matched required /zzz/"]
    assert runner.check({"expect": {"reply_require": ["zzz"]}}, r) == ["no reply matched required /zzz/"]


def _fake_main(monkeypatch, tmp_path, argv, calls):
    monkeypatch.setattr(runner, "HERE", tmp_path)
    monkeypatch.setenv("GIT_SHA", "test")  # the container has no git binary
    (tmp_path / "baselines").mkdir(exist_ok=True)
    (tmp_path / "reports").mkdir(exist_ok=True)
    sc = [{"id": "a", "category": "faq", "turns": ["hi"]}]
    monkeypatch.setattr(runner, "load_pack", lambda s: calls.append("load_pack"))
    monkeypatch.setattr(runner, "ensure_tenant", lambda s: calls.append("ensure_tenant") or "t1")
    monkeypatch.setattr(runner, "ensure_slots", lambda t: None)
    monkeypatch.setattr(runner, "sync_faq", lambda t: None)
    monkeypatch.setattr(runner, "load_scenarios", lambda s: sc)
    monkeypatch.setattr(runner, "run_suite", lambda scs, t: calls.append("run_suite") or ([(scs[0], None, [])], [1]))
    monkeypatch.setattr(runner, "assert_local_only", lambda cids, t: calls.append("local_only"))
    monkeypatch.setattr(runner, "write_report", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["runner", *argv])


def test_roofing_write_baseline_refused_without_force(tmp_path, monkeypatch):
    calls = []
    _fake_main(monkeypatch, tmp_path, ["--pack", "summit-roofing", "--write-baseline"], calls)
    (tmp_path / "baselines" / "v1-roofing.json").write_text("{}")
    with pytest.raises(SystemExit) as e:
        runner.main()
    assert "force-baseline" in str(e.value) and "run_suite" not in calls
    assert (tmp_path / "baselines" / "v1-roofing.json").read_text() == "{}"


def test_roofing_write_baseline_with_force_and_other_pack(tmp_path, monkeypatch):
    calls = []
    _fake_main(monkeypatch, tmp_path, ["--pack", "summit-roofing", "--write-baseline", "--force-baseline"], calls)
    (tmp_path / "baselines" / "v1-roofing.json").write_text("{}")
    runner.main()
    assert "run_suite" in calls and json.loads((tmp_path / "baselines" / "v1-roofing.json").read_text())["meta"]["total"] == 1
    calls.clear()
    _fake_main(monkeypatch, tmp_path, ["--pack", "other", "--write-baseline"], calls)
    runner.main()
    assert (tmp_path / "baselines" / "other.json").exists()


def test_write_baseline_ignores_env_override(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("BASELINE_PATH", str(tmp_path / "evil.json"))
    _fake_main(monkeypatch, tmp_path, ["--pack", "other", "--write-baseline"], calls)
    runner.main()
    assert not (tmp_path / "evil.json").exists() and (tmp_path / "baselines" / "other.json").exists()


@pytest.mark.parametrize("mode", [[], ["--gate"], ["--flake"], ["--write-baseline"]])
def test_assert_local_only_in_every_mode_and_pack_files_are_isolated(tmp_path, monkeypatch, mode):
    monkeypatch.delenv("BASELINE_PATH", raising=False)
    calls = []
    _fake_main(monkeypatch, tmp_path, ["--pack", "other", *mode], calls)
    if mode == ["--gate"]:
        (tmp_path / "baselines" / "other.json").write_text(json.dumps({"scenarios": {"a": {"passed": True}}}))
    runner.main()
    assert "local_only" in calls
    assert not [f for f in tmp_path.rglob("*") if f.is_file() and ("roofing" in f.name or "latest" in f.name or f.name.startswith("flake-report"))]


T1, T2 = "00000000-0000-0000-0000-0000000000e1", "00000000-0000-0000-0000-0000000000e2"


@pytest.fixture
def two_tenants():
    with db.system() as c:
        for t, s in ((T1, "test-ev1"), (T2, "test-ev2")):
            c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:t,:s,'E','UTC','summit-roofing') "
                           "ON CONFLICT (id) DO NOTHING"), {"t": t, "s": s})
            c.execute(text("DELETE FROM slots WHERE tenant_id=:t"), {"t": t})
            c.execute(text("INSERT INTO slots (tenant_id, start_time, end_time) VALUES (:t, now()+interval '1 day', now()+interval '1 day 1 hour'),"
                           "(:t, now()+interval '2 day', now()+interval '2 day 1 hour')"), {"t": t})
    return T1, T2


def _booked(t):
    with db.system() as c:
        return c.execute(text("SELECT count(*) FROM slots WHERE tenant_id=:t AND is_booked"), {"t": t}).scalar()


def test_reset_and_steal_touch_only_their_tenant(two_tenants):
    a, b = two_tenants
    runner.reset_db("no_slots", a)
    assert (_booked(a), _booked(b)) == (2, 0)
    runner.reset_db(None, a)
    runner.steal_first_slot(a)
    assert (_booked(a), _booked(b)) == (1, 0)


def test_run_scenario_passes_tenant_to_handle_turn(two_tenants, monkeypatch):
    a, _ = two_tenants
    seen = []

    def fake(turn, cid, channel, tenant_id):
        seen.append(tenant_id)
        with db.tx(tenant_id) as c:
            lead = c.execute(text("INSERT INTO leads (tenant_id) VALUES (:t) RETURNING id"), {"t": tenant_id}).scalar()
            return c.execute(text("INSERT INTO conversations (tenant_id, lead_id) VALUES (:t,:l) RETURNING id"),
                             {"t": tenant_id, "l": lead}).scalar(), "ok"
    monkeypatch.setattr(runner, "handle_turn", fake)
    r = runner.run_scenario({"id": "x", "turns": ["a", "b"]}, a)
    assert seen == [a, a] and r["state"] == "GREETING"


def test_run_scenario_detects_wrong_tenant_conversation(two_tenants, monkeypatch):
    a, b = two_tenants

    def fake(turn, cid, channel, tenant_id):  # a buggy agent answering under the other tenant
        with db.tx(b) as c:
            lead = c.execute(text("INSERT INTO leads (tenant_id) VALUES (:t) RETURNING id"), {"t": b}).scalar()
            return c.execute(text("INSERT INTO conversations (tenant_id, lead_id) VALUES (:t,:l) RETURNING id"),
                             {"t": b, "l": lead}).scalar(), "ok"
    monkeypatch.setattr(runner, "handle_turn", fake)
    with pytest.raises((AssertionError, NoResultFound)):  # RLS hides the other tenant's row before the guard runs
        runner.run_scenario({"id": "x", "turns": ["a"]}, a)
