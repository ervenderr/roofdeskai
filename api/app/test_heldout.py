import json
import sys

import pytest
import yaml

from app.config import settings
from evals import runner

SC = {"id": "x-1", "category": "faq", "turns": ["hi"], "expect": {}}


def _write(root, name, items):
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(yaml.safe_dump(items))


# ---- loader root ----

def test_load_scenarios_custom_root(tmp_path):
    _write(tmp_path, "a.yaml", [SC])
    assert [s["id"] for s in runner.load_scenarios("any", tmp_path)] == ["x-1"]


@pytest.mark.parametrize("bad", [
    [SC, SC],
    [{**SC, "category": "nope"}],
    [{**SC, "bogus": 1}],
])
def test_load_scenarios_custom_root_still_validates(tmp_path, bad):
    _write(tmp_path, "a.yaml", bad)
    with pytest.raises(SystemExit):
        runner.load_scenarios("any", tmp_path)


# ---- parsing ----

@pytest.mark.parametrize("flag", [["--write-baseline"], ["--gate"], ["--flake"], ["--ids", "a"], ["--category", "faq"]])
def test_heldout_rejects_other_modes(monkeypatch, flag):
    monkeypatch.setattr(sys, "argv", ["runner", "--heldout", *flag])
    with pytest.raises(SystemExit) as e:
        runner.main()
    assert e.value.code == 2


# ---- run-once guard ----

@pytest.fixture
def ho(tmp_path, monkeypatch):
    held, rep = tmp_path / "heldout", tmp_path / "reports"
    rep.mkdir()
    _write(held / "pk", "a.yaml", [SC, {**SC, "id": "x-2"}])
    monkeypatch.setattr(runner, "HELDOUT", held)
    monkeypatch.setattr(runner, "REPORTS", rep)
    monkeypatch.setattr(runner, "assert_local_only", lambda cids, t: None)
    monkeypatch.setattr(runner, "report_path", lambda *a, **k: pytest.fail("heldout must not use report_path"))
    monkeypatch.setattr(runner, "write_report", lambda results, cids, slug, t, out=None, header=(): out.write_text("\n".join(header)))
    monkeypatch.setenv("GIT_SHA", "run123")
    monkeypatch.setenv("HELDOUT_SHA", "fix456")
    monkeypatch.setenv("HELDOUT_PRECHECK", "pre ok")
    return held, rep


def _suite(results):
    return lambda scenarios, t: (results, [1])


def _ok_results():
    r = {"state": "DONE"}
    return [({**SC}, r, []), ({**SC, "id": "x-2"}, r, ["state a != b"])]


def test_first_run_writes_record_and_report(ho, monkeypatch):
    held, rep = ho
    monkeypatch.setattr(runner, "run_suite", _suite(_ok_results()))
    runner.run_heldout("pk", "t", None)
    rec = json.loads((held / "results" / "pk.json").read_text())
    assert (rec["scenarios_sha"], rec["run_sha"], rec["precheck"]) == ("fix456", "run123", "pre ok")
    assert (rec["passed"], rec["total"], rec["reruns"], rec["local_only"]) == (1, 2, [], True)
    assert rec["scenarios"]["x-2"] == {"passed": False, "failed_checks": ["state a != b"]}
    assert len(rec["scenarios_sha256"]) == 64 and rec["model"] and rec["date"]
    report = (rep / "heldout-pk.md").read_text()
    assert "fix456" in report and "run123" in report and "held out from tuning" in report
    assert sorted(p.name for p in rep.iterdir()) == ["heldout-pk.md"]


def test_second_run_refused_then_forced(ho, monkeypatch):
    held, rep = ho
    monkeypatch.setattr(runner, "run_suite", _suite(_ok_results()))
    runner.run_heldout("pk", "t", None)
    before = (held / "results" / "pk.json").read_text()
    with pytest.raises(SystemExit):
        runner.run_heldout("pk", "t", None)
    assert (held / "results" / "pk.json").read_text() == before
    assert not (held / "results" / "pk.prev.json").exists()
    runner.run_heldout("pk", "t", "ollama timed out")
    assert (held / "results" / "pk.prev.json").read_text() == before
    rec = json.loads((held / "results" / "pk.json").read_text())
    assert [x["reason"] for x in rec["reruns"]] == ["ollama timed out"]


def test_local_only_abort_writes_nothing(ho, monkeypatch):
    held, rep = ho
    monkeypatch.setattr(runner, "run_suite", _suite(_ok_results()))
    monkeypatch.setattr(runner, "assert_local_only", lambda cids, t: sys.exit("ABORT"))
    with pytest.raises(SystemExit):
        runner.run_heldout("pk", "t", None)
    assert not (held / "results").exists() and list(rep.iterdir()) == []


@pytest.mark.parametrize("bad", [
    [({**SC}, None, ["error: x"])],
    [({**SC}, {"state": "DONE"}, ["error: TimeoutError: x"])],
])
def test_infra_fault_aborts_without_record(ho, monkeypatch, bad):
    held, rep = ho
    monkeypatch.setattr(runner, "run_suite", _suite(bad))
    with pytest.raises(SystemExit):
        runner.run_heldout("pk", "t", None)
    assert not (held / "results").exists() and list(rep.iterdir()) == []


# ---- scenario set (RED until scenarios exist) ----

def _ids(slug):
    return [s["id"] for s in runner.load_scenarios(slug, runner.HERE / "heldout" / slug)]


@pytest.mark.parametrize("slug,n,prefix", [("summit-roofing", 12, "ho-r-"), ("bright-smile-dental", 8, "ho-d-")])
def test_heldout_set_counts_and_prefix(slug, n, prefix):
    ids = _ids(slug)
    assert len(ids) == n and all(i.startswith(prefix) for i in ids)


def test_heldout_set_disjoint_from_dev():
    dev = {s["id"] for d in settings.businesses_dir.iterdir() if (d / "scenarios").is_dir()
           for s in runner.load_scenarios(d.name)}
    held = set(_ids("summit-roofing")) | set(_ids("bright-smile-dental"))
    assert dev and not (dev & held)
