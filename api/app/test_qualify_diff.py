"""Dual-run: old hardcoded policy functions (oracle) vs data-driven qualify over a large grid."""
import hashlib
import itertools
import random
import string
import time

from . import policy, qualify

CURATED = [None, "", "   ", "Denver", "123 Main St", "123 Main St, Denver", "123 main st, DENVER",
           "123 Main St, Denver CO", "123 Main St, Denver, CO", "123 Main St, Denver, CO 80202",
           "123 Main St, Denver CO 80202-1234", "123 Main St Denver CO 80202", "1 Oak St Denver",
           "12 Denver Ave", "12 Denver Ave, Boulder", "12 Aurora Ave, Austin TX", "123 Main St, Apt 4",
           "123 Main St, Apt 4, Denver", "123 Main St, Unit 5, Aurora CO", "123 Main St, Suite 100",
           "123 Main St, Ste 2", "123 Main St, Floor 3, Austin", "14 Congress Ave, Austin",
           "14 Congress Ave, Austin, TX 78701", "9 Elm St, Boulder CO 80302", "somewhere in Denver",
           "Denver, 12 Oak", "12 Oak St,", "12 Oak St, ,Denver", "12 Oak St , Denver", "12 Oak St,Denver",
           "12 Oak St, CO 80202", "12 Oak St, CO", "12 Oak St, 80202", "12 Oak St, St. Louis",
           "12 Oak St, Fort Collins CO", "12 Oak St, Littleton, Colorado", "12 O'Brien Ln, Arvada",
           "12 Oak St, Lakewood Colorado 80226", "12 Oak St, Centennial.", "12 Oak St, Denver-Aurora",
           "12 Oak St, ño Denver", "12 Oak St, Lo", "12 Oak St, LA", "12 Oak St, Ft. Worth TX",
           "Apt 4, Denver", "12 Oak St, Highlands Ranch CO 80126", "12 Oak St; Denver",
           "12 Oak St, Denver 80202, CO", "12 Oak St, West Denver", "12 Oak St, Denverton",
           "5 Main St, Austin"]
EDGE_ADDRS = [None, "123 Main St", "123 Main St, Denver", "14 Congress Ave, Austin", "12 Oak St, Apt 4"]
CONTACTS = [(None, None), ("303-555-0100", None), (None, "a@b.co"), ("", "")]
NAMES = [None, "", "Sam"]
MAIN = (["repair", "replacement", "inspection", "other", None], [True, False, None],
        [None, 0, 1, 5, 6, 7, 24], CURATED)
EDGE = (["repair", "replacement", "inspection", "other", None, "", "plumbing", "Repair"],
        [True, False, None, 0, 1], [None, 0, 1, 5, 6, 7, 24, -1], EDGE_ADDRS)

def iter_leads():
    for tier in (MAIN, EDGE):
        for s, o, t, a, n, (p, e) in itertools.product(*tier, NAMES, CONTACTS):
            yield {"service_type": s, "is_owner": o, "timeline_months": t, "address": a, "name": n,
                   "phone": p, "email": e}


def _fuzz():
    rng = random.Random(20261103)
    pick = lambda xs: xs[rng.randrange(len(xs))]
    cities = ["denver", "aurora", "lakewood", "arvada", "littleton", "centennial", "austin", "boulder",
              "fort collins", "ño", "lo", "highlands ranch"]
    out = []
    for _ in range(5000):
        s = pick(["", "12", "4B", "1600"]) + " " + pick(["Oak St", "Main Street", "Denver Ave", "O'Brien Ln", "St. Paul Rd"])
        s += pick([", ", ",", " , ", ", , ", " ", "; "]) + pick(cities) + " " + pick(["", "CO", "TX", "Colorado", "co"])
        s += " " + pick(["", "80202", "80202-1234", "8020"]) + pick(["", ", Apt 4", ", Unit 5", ", Suite 100", ", ste 2"])
        out.append(pick([s, s.lower(), s.upper(), s.title()]))
    alphabet = string.ascii_letters + string.digits + ", .'-;"
    for _ in range(5000):
        out.append("".join(alphabet[rng.randrange(len(alphabet))] for _ in range(rng.randrange(31))))
    return out


def address_corpus():
    return CURATED + _fuzz()


def _digest(rows):
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def grid_digest(verdict_fn, missing_fn, question_fn):
    return _digest(f"{i}|{verdict_fn(l)}|{missing_fn(l)}|{question_fn(l)}" for i, l in enumerate(iter_leads()))


def addr_digest(status_fn):
    return _digest(f"{i}|{status_fn(a)}" for i, a in enumerate(address_corpus()))


GRID_COUNT = sum(1 for _ in iter_leads())  # pinned below so the grid cannot shrink
ADDR_COUNT = len(address_corpus())


def test_grid_not_shrunk():
    assert GRID_COUNT == 84_720 and ADDR_COUNT == 10_052


def test_zero_diff_grid(roofing_pack):
    t0, diffs, n = time.time(), [], 0
    for lead in iter_leads():
        n += 1
        for name, old, new in (("qualification", policy.qualification, qualify.qualify),
                               ("missing_fields", policy.missing_fields, qualify.missing_fields),
                               ("next_question", policy.next_question, qualify.next_question)):
            o, w = old(roofing_pack, lead), new(roofing_pack, lead)
            if o != w:
                diffs.append((lead, name, o, w))
    print(f"grid leads={n} runtime={time.time() - t0:.1f}s")
    assert n == GRID_COUNT
    assert not diffs, diffs[:10]


def test_address_zero_diff(roofing_pack):
    cities = roofing_pack.qualification.service_area
    corpus = address_corpus()
    assert len(corpus) == ADDR_COUNT
    diffs = [(a, policy.address_status(roofing_pack, a), qualify.address_status(cities, a))
             for a in corpus if policy.address_status(roofing_pack, a) != qualify.address_status(cities, a)]
    assert not diffs, diffs[:10]


def test_frozen_digest_old(roofing_pack):  # temporary: removed with the old path
    from .tests_data import frozen_qualify as Q
    p = roofing_pack
    assert grid_digest(lambda l: policy.qualification(p, l), lambda l: policy.missing_fields(p, l),
                       lambda l: policy.next_question(p, l)) == Q.GRID_SHA256
    assert addr_digest(lambda a: policy.address_status(p, a)) == Q.ADDR_SHA256


def test_frozen_digest_new(roofing_pack):
    from .tests_data import frozen_qualify as Q
    p = roofing_pack
    assert (GRID_COUNT, ADDR_COUNT) == (Q.GRID_COUNT, Q.ADDR_COUNT)
    assert grid_digest(lambda l: qualify.qualify(p, l), lambda l: qualify.missing_fields(p, l),
                       lambda l: qualify.next_question(p, l)) == Q.GRID_SHA256
    cities = next(r.cities for r in p.qualification.rules if r.rule == "in_area")
    assert addr_digest(lambda a: qualify.address_status(cities, a)) == Q.ADDR_SHA256


def test_rule_params_frozen(roofing_pack):
    from .tests_data import frozen_old as F
    rules = roofing_pack.qualification.rules
    assert set(next(r.cities for r in rules if r.rule == "in_area")) == set(F.FROZEN_SERVICE_AREA)
    assert set(next(r.values for r in rules if r.rule == "in_list" and r.field == "service_type")) == set(
        F.FROZEN_QUALIFYING_SERVICES)
    assert next(r.max for r in rules if r.rule == "max_number") == F.FROZEN_MAX_TIMELINE_MONTHS
