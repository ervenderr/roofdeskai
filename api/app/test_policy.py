import pytest
from pydantic import ValidationError

from . import policy
from .schemas import LeadFields

GOOD = {"service_type": "repair", "is_owner": True, "address": "12 Oak St, Denver", "timeline_months": 2}


def test_qualified():
    assert policy.qualification(GOOD) == "qualified"


@pytest.mark.parametrize("change", [
    {"is_owner": False},
    {"address": "5 Main St, Austin"},
    {"timeline_months": 12},
    {"service_type": "other"},
])
def test_each_criterion_disqualifies(change):
    assert policy.qualification({**GOOD, **change}) == "disqualified"


def test_address_without_city_is_incomplete_not_disqualified():
    assert policy.qualification({**GOOD, "address": "1 Oak St"}) == "incomplete"
    assert "address" in policy.missing_fields({**GOOD, "address": "1 Oak St"})


def test_pick_slot_only_from_offered():
    assert policy.pick_slot("the second one", [10, 11, 12]) == 11
    assert policy.pick_slot("option 3", [10, 11, 12]) == 12
    assert policy.pick_slot("slot 999", [10, 11, 12]) is None
    assert policy.pick_slot("Saturday at 8am?", [10, 11]) is None


def test_incomplete_until_all_known():
    assert policy.qualification({"is_owner": True}) == "incomplete"


def test_budget_never_disqualifies():
    assert policy.qualification({**GOOD, "budget_range": "under 100"}) == "qualified"


@pytest.mark.parametrize("msg,reason", [
    ("Can I talk to a real person?", "human_request"),
    ("I'm calling my lawyer", "legal"),
    ("part of my roof collapsed", "safety"),
    ("This is ridiculous, you're useless", "angry"),
    ("I rent my place in Denver", None),
])
def test_escalation_reason(msg, reason):
    assert policy.escalation_reason(msg) == reason


def test_unsupported_claim():
    kb = ["Roof replacements carry a 10-year workmanship warranty."]
    assert policy.unsupported_claim("It costs $5,000.", kb)
    assert policy.unsupported_claim("We offer a 25-year warranty.", kb)
    assert not policy.unsupported_claim("We offer a 10-year workmanship warranty.", kb)
    assert not policy.unsupported_claim("Happy to help!", kb)


def test_update_lead_schema_rejects_unknown_and_bad_values():
    with pytest.raises(ValidationError):
        LeadFields.model_validate({"status": "booked"})
    assert LeadFields.model_validate({"email": "nope"}).email is None  # bad value = not given
    assert LeadFields.model_validate({"name": "unknown"}).name is None


def test_ungrounded_values_are_dropped():
    msg = "Hi, I have a few missing shingles after the storm and want it repaired."
    kept, dropped = policy.ground({"is_owner": False, "timeline_months": 0, "service_type": "repair"}, msg)
    assert kept == {"service_type": "repair"} and dropped == ["is_owner", "timeline_months"]
    assert policy.ground({"service_type": "other"}, "something done to my roof, not sure what")[0] == {}


def test_grounded_values_are_kept():
    kept, _ = policy.ground({"is_owner": False}, "no", asked="Do you own the property?")
    assert kept == {"is_owner": False}
    msg = "I'm Sam Reyes, phone 303-555-0142, I own 5 Elm St, Denver, within 2 months"
    fields = {"name": "Sam Reyes", "phone": "303-555-0142", "is_owner": True, "address": "5 Elm St, Denver",
              "timeline_months": 2}
    assert policy.ground(fields, msg)[0] == fields


def test_pick_slot_ignores_stray_numbers_and_negation():
    assert policy.pick_slot("I have one question about the roof warranty and pricing", [10, 11]) is None
    assert policy.pick_slot("not the first one, the second", [10, 11]) is None
    assert policy.pick_slot("the second one", [10, 11]) == 11


@pytest.mark.parametrize("addr,expected", [
    ("123 Main St, Apt 4", "incomplete"),
    ("14 Congress Ave, Austin", "out"),
    ("5 Oak Dr, Denver, CO 80202", "in"),
    ("1 Oak St Denver", "in"),
    ("12 Denver Ave, Boulder", "out"),
    ("somewhere in Denver", "incomplete"),
])
def test_address_status(addr, expected):
    assert policy.address_status(addr) == expected


def test_names_and_streets_do_not_trigger_escalation():
    assert policy.escalation_reason("My name is Sue, I live at 4 Maple Court, Denver") is None
    assert policy.escalation_reason("I will take this to court") == "legal"
    assert policy.escalation_reason("gas smell in the attic", only=("safety", "legal")) == "safety"


def test_claim_guard_uses_whole_numbers():
    assert policy.unsupported_claim("That is $6.", ["takes about 45 to 60 minutes"])
    assert policy.unsupported_claim("We give a 2-year warranty", ["10-year workmanship warranty, 1 year repairs, 12 chips"])


def test_question_detection():
    assert policy.looks_like_question("How long does the inspection take?")
    assert policy.looks_like_question("is it free")
    assert not policy.looks_like_question("Kim Lee, 303-555-0123")


def test_not_ready_needs_the_customers_own_words():
    assert not policy.not_ready_grounded("None of these work for me.")
    assert not policy.not_ready_grounded("idk")
    assert policy.not_ready_grounded("Just browsing, I'll decide later")


def test_answer_must_reuse_faq_words():
    faq = ["The roof inspection is free and takes about 45 to 60 minutes."]
    q = "How long does the inspection take?"
    assert policy.answer_supported("It takes about 45 to 60 minutes.", faq)
    assert not policy.answer_supported("Yes, we are fully licensed and insured.", faq)


def test_answer_guard_accepts_inflections_but_not_new_claims():
    faq = ["Summit Roofing serves Denver, Aurora, Lakewood.", "Roof replacements carry a 10-year workmanship warranty."]
    assert policy.answer_supported("Yes, we serve Aurora.", faq)
    assert policy.answer_supported("A replacement has a 10-year workmanship warranty.", faq)
    assert not policy.answer_supported("We are licensed and insured.", ["We provide a photo report for your insurer."])


def test_address_status_handles_state_without_a_comma_and_zip_codes():
    from .policy import address_status
    for addr in ("412 Oak Lane, Denver CO", "412 Oak Lane, Aurora CO 80012", "412 Oak Lane, Denver, CO", "120 Main St, Lakewood Colorado"):
        assert address_status(addr) == "in", addr
    for addr in ("412 Oak Lane, Austin TX", "412 Aurora Ave, Austin TX", "9 Elm St, Boulder CO 80302"):
        assert address_status(addr) == "out", addr
