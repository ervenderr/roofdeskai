"""Strict loader and pure runners for the per-module eval sets. No LLM, no DB, no network."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import app
from app.engine import brief as brief_mod
from app.engine import capacity as cap_mod
from app.engine import connectors, intake, quote, quote_text, reviews
from app.config import settings
from app.pack import Pack, load_pack

HERE = Path(__file__).parent
PACKS = Path(app.__file__).parent / "tests_data" / "packs"
MODULES = ("quote", "capacity", "brief", "reviews", "intake")
DEFAULT_PACK = "demo-venue"

# module -> kind -> (required keys, optional keys). Unknown keys fail the load, like runner.load_scenarios.
SHAPES = {
    "quote": {"build": ({"id", "input", "expect"}, {"pack", "kind"}),
              "text_check": ({"id", "kind", "input", "text", "expect"}, {"pack", "codes"})},
    "capacity": {"flags": ({"id", "bookings", "range", "expect"}, {"kind", "pack", "tz", "overrides"}),
                 "sequence": ({"id", "kind", "range", "runs", "expect"}, {"pack", "tz"})},
    "brief": {"build": ({"id", "results", "local_date", "expect"}, {"kind", "pack"}),
              "mock": ({"id", "kind", "local_date", "expect"}, {"pack"}),
              "due": ({"id", "kind", "now_utc", "tz", "send_hour", "already_ran", "expect"}, set())},
    "reviews": {"check": ({"id", "review_text", "rating", "draft", "expect"}, {"kind", "pack", "health_privacy", "codes"})},
    "intake": {"events": ({"id", "events", "expect"}, {"kind", "pack"})},
}
EXPECT_KEYS = {
    ("quote", "build"): {"total", "lines", "needs_human"},
    ("capacity", "flags"): {"flags"}, ("capacity", "sequence"): {"runs"},
    ("brief", "build"): {"text_contains", "text_excludes", "disagreements"},
    ("brief", "mock"): {"text_contains", "disagreements_contain"},
    ("brief", "due"): {"due"},
    ("intake", "events"): {"people", "errors"},
}


@dataclass(frozen=True)
class CaseResult:
    module: str
    id: str
    ok: bool
    detail: str = ""


def _bad(module: str, case: dict, why: str):
    raise ValueError(f"evals/modules/{module}/cases.yaml: case {case.get('id')!r}: {why}")


def load_cases(module: str) -> list[dict]:
    cases = yaml.safe_load((HERE / module / "cases.yaml").read_text()) or []
    seen = set()
    for c in cases:
        if not isinstance(c, dict) or not c.get("id") or c["id"] in seen:
            _bad(module, c if isinstance(c, dict) else {}, "missing or duplicate id")
        seen.add(c["id"])
        kind = c.get("kind", next(iter(SHAPES[module])))
        if kind not in SHAPES[module]:
            _bad(module, c, f"unknown kind {kind!r}")
        req, opt = SHAPES[module][kind]
        if miss := req - set(c):
            _bad(module, c, f"missing keys {sorted(miss)}")
        if extra := set(c) - req - opt:
            _bad(module, c, f"unknown keys {sorted(extra)}")
        exp = c["expect"]
        if isinstance(exp, dict) and (e := set(exp) - EXPECT_KEYS.get((module, kind), set(exp))):
            _bad(module, c, f"unknown expect keys {sorted(e)}")
    return cases


def _pack(c: dict) -> Pack:
    slug = c.get("pack", DEFAULT_PACK)
    # fixtures first (demo-venue), then the real packs
    return load_pack(slug, base=PACKS if (PACKS / slug).is_dir() else settings.businesses_dir)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _quote(c: dict):
    pack = _pack(c)
    i = c["input"]
    req = quote.QuoteRequest(i.get("service_id"), i.get("qty"), tuple(i.get("add_on_ids", ())), i.get("customer_type"))
    return pack, req, quote.build_quote(pack, req)


def _run_quote(c: dict) -> list[str]:
    pack, req, res = _quote(c)
    errs = []
    if c.get("kind") == "text_check":
        if isinstance(res, quote.NeedsHuman):
            return [f"input is not quotable: {res}"]
        svc = next(s for s in pack.services.services if s.id == req.service_id)
        codes = quote_text.check_quote_text(c["text"], res, quote.rule_percents(svc))
        if (c["expect"] == "ok") != (not codes):
            errs.append(f"expected {c['expect']}, got codes {codes}")
        if "codes" in c and sorted(codes) != sorted(c["codes"]):
            errs.append(f"codes {sorted(codes)} != {sorted(c['codes'])}")
        return errs
    exp = c["expect"]
    if "needs_human" in exp:
        want = (exp["needs_human"]["reason"], tuple(exp["needs_human"]["missing"]))
        got = (res.reason, res.missing) if isinstance(res, quote.NeedsHuman) else res
        return [] if got == want else [f"needs_human {got} != {want}"]
    if isinstance(res, quote.NeedsHuman):
        return [f"unexpected needs_human {res}"]
    if quote.fmt(res.total) != exp["total"]:
        errs.append(f"total {quote.fmt(res.total)} != {exp['total']}")
    got = [{"ref": ln.ref, "amount": quote.fmt(ln.amount)} for ln in res.lines]
    if got != exp["lines"]:
        errs.append(f"lines {got} != {exp['lines']}")
    if sum((ln.amount for ln in res.lines), Decimal(0)) != res.total:
        errs.append("total != sum(lines)")
    return errs


def _bookings(rows) -> list[cap_mod.Booking]:
    return [cap_mod.Booking(start=b["start"], covers=b["covers"]) for b in rows]


def _flags(c: dict, bookings, overrides=()):
    pack = _pack(c)
    tz = ZoneInfo(c.get("tz", pack.meta.timezone))
    first, last = (date.fromisoformat(d) for d in c["range"])
    return cap_mod.check_capacity(pack.capacity, tz, _bookings(bookings), first, last,
                                  [cap_mod.Override(**o) for o in overrides]), first, last


def _run_capacity(c: dict) -> list[str]:
    if c.get("kind") != "sequence":
        flags, _, _ = _flags(c, c["bookings"], c.get("overrides", ()))
        got = sorted(f"{f.flag_key}" for f in flags)
        want = sorted(f"{f['kind']}:{f['shift_id']}:{f['date']}" for f in c["expect"]["flags"])
        return [] if got == want else [f"flags {got} != {want}"]
    state: dict[str, tuple[str, bool]] = {}
    errs = []
    for n, (run, want) in enumerate(zip(c["runs"], c["expect"]["runs"]), 1):
        flags, first, last = _flags(c, run["bookings"], run.get("overrides", ()))
        out = cap_mod.classify(state, flags, first, last)
        hashes = {f.flag_key: f.input_hash for f in flags}
        for k in out["new"] + out["reflagged"]:
            state[k] = (hashes[k], False)
        for k in out["resolved"]:
            state[k] = (state[k][0], True)
        for status in ("new", "unchanged", "reflagged", "resolved"):
            if sorted(out[status]) != sorted(want.get(status, [])):
                errs.append(f"run {n} {status}: {sorted(out[status])} != {sorted(want.get(status, []))}")
    return errs


def _result(r: dict) -> connectors.ConnectorResult:
    return connectors.ConnectorResult(r["name"], r.get("source", "mock"), r.get("ok", True),
                                      {k: Decimal(str(v)) for k, v in r.get("metrics", {}).items()}, r.get("error"))


def _run_brief(c: dict) -> list[str]:
    kind, exp = c.get("kind", "build"), c["expect"]
    if kind == "due":
        got = brief_mod.is_due(_dt(c["now_utc"]), c["tz"], c["send_hour"], c["already_ran"])
        return [] if got == exp["due"] else [f"due {got} != {exp['due']}"]
    pack, day = _pack(c), date.fromisoformat(c["local_date"])
    if kind == "mock":
        t = connectors.TenantRef(pack.meta.slug, "00000000-0000-0000-0000-000000000000", pack.meta.timezone)
        results = connectors.fetch_all(pack.connectors.sources, t, day)
        b = brief_mod.build_brief(pack, results, day)
        errs = [f"missing {s!r}" for s in exp.get("text_contains", []) if s not in b.text]
        errs += [f"no disagreement containing {s!r}" for s in exp.get("disagreements_contain", [])
                 if not any(s in d for d in b.disagreements)]
        return errs
    b = brief_mod.build_brief(pack, [_result(r) for r in c["results"]], day)
    errs = [f"missing {s!r}" for s in exp.get("text_contains", []) if s not in b.text]
    errs += [f"unexpected {s!r}" for s in exp.get("text_excludes", []) if s in b.text]
    if "disagreements" in exp and list(b.disagreements) != exp["disagreements"]:
        errs.append(f"disagreements {list(b.disagreements)} != {exp['disagreements']}")
    return errs


def _run_reviews(c: dict) -> list[str]:
    pack = _pack(c)
    if "health_privacy" in c:
        r = pack.meta.reviews.model_copy(update={"health_privacy": c["health_privacy"]})
        pack = pack.model_copy(update={"meta": pack.meta.model_copy(update={"reviews": r})})
    # rating is a case field only: check_reply has no rating parameter, so identical results across 1..5 are structural.
    codes = reviews.check_reply(c["draft"], pack, c["review_text"])
    errs = []
    if (c["expect"] == "pass") != (not codes):
        errs.append(f"expected {c['expect']}, got codes {codes}")
    if "codes" in c and sorted(codes) != sorted(c["codes"]):
        errs.append(f"codes {sorted(codes)} != {sorted(c['codes'])}")
    return errs


def _run_intake(c: dict) -> list[str]:
    pack, now = _pack(c), datetime(2026, 7, 1, tzinfo=timezone.utc)
    people: dict[str, dict] = {}
    errors = []
    for e in c["events"]:
        res = intake.normalise_event(getattr(pack.meta.intake, e["event"]), e["event"], e["payload"], now)
        if isinstance(res, list):
            errors += [{"event": f.event, "field": f.field, "msg": f.msg} for f in res]
            continue
        people[res.person_key] = intake.apply_event(people.get(res.person_key), res)
    exp, errs = c["expect"], []
    if "people" in exp:
        want = {p["person_key"]: p for p in exp["people"]}
        if set(want) != set(people):
            errs.append(f"person keys {sorted(people)} != {sorted(want)}")
        for k, w in want.items():
            have = people.get(k, {})
            for f, v in w.items():
                got = have.get(f)
                got = got.astimezone(timezone.utc).isoformat() if isinstance(got, datetime) else got
                if got != v:
                    errs.append(f"{k}.{f}: {got!r} != {v!r}")
    if "errors" in exp and errors != exp["errors"]:
        errs.append(f"errors {errors} != {exp['errors']}")
    return errs


RUNNERS = {"quote": _run_quote, "capacity": _run_capacity, "brief": _run_brief, "reviews": _run_reviews, "intake": _run_intake}


def run_case(module: str, case: dict) -> CaseResult:
    try:
        errs = RUNNERS[module](case)
    except Exception as e:  # a crashing case is a failing case, with its error shown
        errs = [f"{type(e).__name__}: {e}"]
    return CaseResult(module, case["id"], not errs, "; ".join(errs))


def run(module: str) -> list[CaseResult]:
    return [run_case(module, c) for c in load_cases(module)]
