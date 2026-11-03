from types import SimpleNamespace as NS
from typing import get_args

from .pack import InArea, InList, MaxNumber, Rule, YesNo
from . import qualify

RULES = (InList(id="service_type", field="service_type", rule="in_list", values=("repair",)),
         YesNo(id="is_owner", field="is_owner", rule="yes_no"),
         InArea(id="address", field="address", rule="in_area", cities=("denver",)),
         MaxNumber(id="timeline_months", field="timeline_months", rule="max_number", max=6))
ASK = {r.id: f"{r.id}?" for r in RULES} | {"name": "n?", "phone or email": "p?"}


def mk(rules=RULES, ask=ASK):
    return NS(qualification=NS(rules=rules), messages=NS(ask=ask, anything_else="else"))


GOOD = {"service_type": "repair", "is_owner": True, "address": "1 Oak St, Denver", "timeline_months": 3,
        "name": "Sam", "phone": "1"}


def test_rule_union_matches_checks():
    assert set(get_args(get_args(Rule)[0])) == set(qualify.CHECKS)


def test_in_list_three_valued():
    r = RULES[0]
    assert (qualify._in_list(r, "repair"), qualify._in_list(r, "other"), qualify._in_list(r, None)) == (True, False, None)
    assert qualify._in_list(r, "") is False


def test_yes_no_identity():
    r = RULES[1]
    assert (qualify._yes_no(r, True), qualify._yes_no(r, False), qualify._yes_no(r, None)) == (True, False, None)
    assert qualify._yes_no(r, 1) is None and qualify._yes_no(r, 0) is None and qualify._yes_no(r, "yes") is None


def test_max_number_three_valued():
    r = RULES[3]
    assert (qualify._max_number(r, 6), qualify._max_number(r, 7), qualify._max_number(r, None)) == (True, False, None)


def test_in_area_three_valued():
    r = RULES[2]
    assert (qualify._in_area(r, "1 Oak St, Denver"), qualify._in_area(r, "1 Oak St, Austin"), qualify._in_area(r, None)) == (True, False, None)


def test_qualify_verdicts():
    p = mk()
    assert qualify.qualify(p, GOOD) == "qualified"
    assert qualify.qualify(p, GOOD | {"timeline_months": 7}) == "disqualified"
    assert qualify.qualify(p, GOOD | {"timeline_months": None}) == "incomplete"


def test_out_of_area_with_unknowns_is_disqualified():
    assert qualify.qualify(mk(), {"address": "1 Oak St, Austin"}) == "disqualified"


def test_missing_order_and_values():
    p = mk()
    assert qualify.missing_fields(p, {}) == ["service_type", "is_owner", "address", "timeline_months", "name", "phone or email"]
    assert qualify.missing_fields(p, GOOD | {"service_type": ""}) == ["service_type"]
    assert qualify.missing_fields(p, GOOD | {"is_owner": False, "timeline_months": 0}) == []


def test_not_required_rule_skipped():
    loose = (RULES[0].model_copy(update={"required": False}),) + RULES[1:]
    p = mk(loose)
    lead = GOOD | {"service_type": "plumbing"}
    assert qualify.qualify(p, lead) == "qualified"
    assert qualify.missing_fields(p, GOOD | {"service_type": None}) == []


def test_next_question():
    assert qualify.next_question(mk(), {}) == "service_type?"
    assert qualify.next_question(mk(), GOOD) == "else"


# --- edit-without-code-change: only YAML data differs between loads ---
import copy

from . import policy
from .pack import load_pack
from .test_pack import MIN_PACK, SLUG, biz, write_pack  # noqa: F401  (biz is a fixture)

LEAD = {"service_type": "repair", "is_owner": True, "address": "1 Oak St, Denver", "timeline_months": 8}


def _load(biz, edit):
    data = copy.deepcopy(MIN_PACK)
    edit(data)
    write_pack(biz, data)
    return load_pack(SLUG)


def _rule(data, rid):
    return next(r for r in data["qualification"]["rules"] if r["id"] == rid)


def test_edit_rule_changes_verdict(biz):
    assert qualify.qualify(_load(biz, lambda d: None), LEAD) == "disqualified"
    p = _load(biz, lambda d: _rule(d, "timeline_months").update(max=12))
    assert qualify.qualify(p, LEAD) == "qualified"


def test_edit_cities_changes_verdict(biz):
    lead = LEAD | {"timeline_months": 3, "address": "5 Main St, Austin"}
    assert qualify.qualify(_load(biz, lambda d: None), lead) == "disqualified"
    p = _load(biz, lambda d: _rule(d, "address").update(cities=["denver", "austin"]))
    assert qualify.qualify(p, lead) == "qualified"


def _drop_timeline(d):
    d["qualification"]["rules"] = [r for r in d["qualification"]["rules"] if r["id"] != "timeline_months"]
    del d["messages"]["ask"]["timeline_months"]


def test_remove_rule(biz):
    lead = LEAD | {"timeline_months": None}
    assert "timeline_months" in qualify.missing_fields(_load(biz, lambda d: None), lead)
    p = _load(biz, _drop_timeline)
    assert "timeline_months" not in qualify.missing_fields(p, lead)
    assert qualify.qualify(p, lead) == "qualified"


def test_edit_question_and_order_change_next_question(biz):
    assert qualify.next_question(_load(biz, lambda d: None), {}) == "s?"
    p = _load(biz, lambda d: d["messages"]["ask"].update(service_type="What service?"))
    assert qualify.next_question(p, {}) == "What service?"
    p = _load(biz, lambda d: d["qualification"]["rules"].reverse())
    assert qualify.next_question(p, {}) == "t?"


def test_edit_disqualify_text(biz):
    p = _load(biz, lambda d: d["messages"].update(disqualify="Sorry, outside our area."))
    assert qualify.qualify(p, LEAD) == "disqualified" and p.messages.disqualify == "Sorry, outside our area."


def test_edit_synonyms_changes_grounding(biz):
    assert policy.is_grounded(_load(biz, lambda d: None), "service_type", "repair", "please fix it")
    p = _load(biz, lambda d: d["qualification"]["service_synonyms"].update(repair="mend"))
    assert not policy.is_grounded(p, "service_type", "repair", "please fix it")
    assert policy.is_grounded(p, "service_type", "repair", "please mend it")


def test_edit_non_business_pattern_changes_grounding(biz):
    assert policy.is_grounded(_load(biz, lambda d: None), "service_type", "other", "clean my gutter")
    p = _load(biz, lambda d: d["qualification"].update(non_business_pattern="paint"))
    assert not policy.is_grounded(p, "service_type", "other", "clean my gutter")
    assert policy.is_grounded(p, "service_type", "other", "please paint it")
