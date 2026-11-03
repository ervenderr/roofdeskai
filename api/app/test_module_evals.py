"""Deterministic per-module eval sets (EVAL-05): no LLM, no DB. A failing case is named by its id."""
import pytest

from evals.modules.loader import MODULES, load_cases, run_case, run

CASES = [(m, c["id"]) for m in MODULES for c in load_cases(m)]


@pytest.mark.parametrize("module,case_id", CASES, ids=[f"{m}:{i}" for m, i in CASES])
def test_case(module, case_id):
    case = next(c for c in load_cases(module) if c["id"] == case_id)
    r = run_case(module, case)
    assert r.ok, r.detail


@pytest.mark.parametrize("module", MODULES)
def test_module_has_no_failures(module):
    results = run(module)
    assert results, f"{module}: empty case set"
    assert [r.id for r in results if not r.ok] == []
