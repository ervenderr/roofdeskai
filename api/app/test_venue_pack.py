"""Third pack (escape-room venue): shape, deterministic escalation recall, scenario counts. No LLM, no DB."""
import re

import pytest

from . import policy
from .engine import quote
from .pack import load_pack

SLUG = "puzzle-peak"
PRICE_RE = re.compile(r"(?i)(chf|fr\.|francs?|[$€£]|\d[\d'.,]*\s*(?:chf|francs?)|\d+\s?%)")
COUNTS = {"qualified": 4, "disqualified": 3, "slots": 3, "faq": 4, "escalation": 5, "injection": 3,
          "out_of_knowledge": 4, "out_of_order": 2, "vague": 2, "voice": 3}


@pytest.fixture(scope="module")
def pack():
    return load_pack(SLUG)


@pytest.fixture(scope="module")
def scenarios():
    from evals.runner import load_scenarios
    return load_scenarios(SLUG)  # real validate path: unique ids, known categories and keys


def test_slug_is_not_the_test_owned_fixture(pack):
    assert pack.meta.slug == SLUG != "demo-venue"


def test_pack_loads_with_all_three_modules(pack):
    assert pack.services is not None and pack.capacity is not None and pack.connectors is not None
    assert pack.meta.timezone == pack.calendar.timezone == "Europe/Zurich"
    for field in (pack.meta.business, pack.meta.kind, pack.meta.offer):
        assert "{{" not in field and "<<" not in field
    assert [r.rule for r in pack.qualification.rules] == ["in_list"]
    assert set(pack.qualification.rules[0].values) == {"escape_room", "private_event"}


def test_faq_has_no_prices(pack):
    assert 8 <= len(pack.faq) <= 12
    assert not any(PRICE_RE.search(e.text) for e in pack.faq)


def test_unpriced_service_needs_human(pack):
    # vip_experience is deliberately unpriced in services.yaml: code must not guess a number
    res = quote.build_quote(pack, quote.QuoteRequest("vip_experience", 4, (), "consumer"))
    assert isinstance(res, quote.NeedsHuman)


def test_scenarios_counts_and_ids(scenarios):
    assert all(s["id"].startswith("v") for s in scenarios)
    counts = {}
    for s in scenarios:
        counts[s["category"]] = counts.get(s["category"], 0) + 1
    assert counts == COUNTS
    assert len(scenarios) == sum(COUNTS.values())


def test_scenario_recall_is_deterministic_and_total(pack, scenarios):
    emergency = [s for s in scenarios if s["expect"].get("state") == "ESCALATE"]
    assert len(emergency) >= 6
    missed = []
    for s in emergency:
        reasons = [policy.escalation_reason(t, pack=pack) for t in s["turns"]]
        if not (reasons[-1] in ("safety", "human_request") and not any(reasons[:-1])):
            missed.append(s["id"])
    assert missed == []


def test_no_other_scenario_turn_escalates(pack, scenarios):
    bad = [(s["id"], t) for s in scenarios if s["expect"].get("state") != "ESCALATE"
           for t in s["turns"] if policy.escalation_reason(t, pack=pack)]
    assert bad == []
