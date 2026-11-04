"""Tests for the shared-code word gate (scripts/check_shared.py).

Banned words are built from fragments so this file stays out of the scan.
"""
from pathlib import Path

import pytest

from scripts import check_shared as cs

W_SUM = "Sum" + "mit"
W_ROOF = "ro" + "ofing"
W_DEN = "Den" + "ver"


def _tree(tmp_path, roots=("api/app", "prompts")):
    for r in roots:
        (tmp_path / r).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_planted_hit_counted(tmp_path):
    root = _tree(tmp_path)
    (root / "api/app/x.py").write_text(f"# {W_SUM} here\n", encoding="utf-8")
    assert cs.find_hits(root, roots=("api/app", "prompts")) == {"api/app/x.py": 1}


def test_product_name_and_tz_not_hits(tmp_path):
    root = _tree(tmp_path)
    (root / "api/app/x.py").write_text("RoofDesk tz=America/" + W_DEN + "\n", encoding="utf-8")
    assert cs.find_hits(root, roots=("api/app", "prompts")) == {}


def test_roofing_and_city_are_hits(tmp_path):
    root = _tree(tmp_path)
    (root / "api/app/x.py").write_text(f"{W_ROOF} and {W_DEN.lower()}\n", encoding="utf-8")
    assert cs.find_hits(root, roots=("api/app", "prompts"))["api/app/x.py"] == 2


def test_excluded_paths_skipped(tmp_path):
    root = _tree(tmp_path)
    for name in ("test_a.py", "conftest.py"):
        (root / "api/app" / name).write_text(W_SUM, encoding="utf-8")
    (root / "api/app/tests_data").mkdir()
    (root / "api/app/tests_data/d.txt").write_text(W_SUM, encoding="utf-8")
    (root / "api/app/__pycache__").mkdir()
    (root / "api/app/__pycache__/m.py").write_text(W_SUM, encoding="utf-8")
    (root / "api/app/blob.bin").write_bytes(b"\x00\xff" + W_SUM.encode())
    assert cs.find_hits(root, roots=("api/app", "prompts")) == {}


def test_eval_cases_yaml_excluded(tmp_path):
    root = _tree(tmp_path, roots=("evals/modules",))
    (root / "evals/modules/capacity").mkdir()
    (root / "evals/modules/capacity/cases.yaml").write_text(W_SUM, encoding="utf-8")
    (root / "evals/modules/capacity/loader.py").write_text(W_SUM, encoding="utf-8")
    assert cs.find_hits(root, roots=("evals/modules",)) == {"evals/modules/capacity/loader.py": 1}


def test_missing_root_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        cs.find_hits(tmp_path, roots=("api/app",))


def test_allow_pins_count():
    allow = {"a.py": (2, "why")}
    assert cs.check({"a.py": 2}, allow) == []
    assert cs.check({"a.py": 1}, allow)  # shrank
    assert cs.check({"a.py": 3}, allow)  # grew
    assert cs.check({}, allow)  # stale
    assert cs.check({"b.py": 1}, allow)  # unlisted offender


def test_real_repo_clean():
    root = Path(cs.__file__).resolve().parent.parent
    problems = cs.check(cs.find_hits(root), cs.ALLOW)
    assert problems == []
