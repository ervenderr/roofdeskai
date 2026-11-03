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
