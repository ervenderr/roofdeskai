"""Run scenarios through the real agent and score them with deterministic checks.

    docker compose exec -e GIT_SHA=$(git rev-parse --short HEAD) api python -m evals.runner [--ids a,b] [--category x]
"""
import argparse
import json
import os
import re
import statistics
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import text

from app import policy
from app.agent import PROMPT, handle_turn
from app.config import settings
from app.db import engine
from app.llm import load_prompt

HERE = Path(__file__).parent


def load_scenarios() -> list[dict]:
    return [s for f in sorted((HERE / "scenarios").glob("*.yaml")) for s in yaml.safe_load(f.read_text())]


def reset_db(setup: str | None) -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM appointments"))
        c.execute(text("UPDATE slots SET is_booked=:b"), {"b": setup == "no_slots"})


def steal_first_slot() -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE slots SET is_booked=true WHERE id=(SELECT id FROM slots WHERE NOT is_booked "
                       "AND start_time > now() ORDER BY start_time LIMIT 1)"))


def run_scenario(sc: dict) -> dict:
    reset_db(sc.get("setup"))
    cid, replies, times = None, [], []
    for i, turn in enumerate(sc["turns"], 1):
        if sc.get("steal_slot_before_turn") == i:
            steal_first_slot()
        start = time.perf_counter()
        cid, reply = handle_turn(turn, cid, channel="eval")
        times.append(time.perf_counter() - start)
        replies.append(reply)
    with engine.connect() as c:
        convo = c.execute(text("SELECT c.state, c.outcome, l.status AS lead_status, l.id AS lead_id FROM conversations c "
                               "JOIN leads l ON l.id=c.lead_id WHERE c.id=:i"), {"i": cid}).mappings().one()
        called = {r[0] for r in c.execute(text("SELECT tool_name FROM tool_calls WHERE conversation_id=:i AND ok"),
                                          {"i": cid})}
        lead = dict(c.execute(text("SELECT * FROM leads WHERE id=:i"), {"i": convo["lead_id"]}).mappings().one())
        booked = c.execute(text("SELECT count(*) FROM appointments WHERE lead_id=:i"), {"i": convo["lead_id"]}).scalar()
    invalid_booking = bool(booked) and policy.qualification(lead) != "qualified"
    return {"cid": cid, "replies": replies, "times": times, "called": called, "invalid_booking": invalid_booking, **convo}


def check(sc: dict, r: dict) -> list[str]:
    exp, fails = sc.get("expect", {}), []
    if "state" in exp and r["state"] != exp["state"]:
        fails.append(f"state {r['state']} != {exp['state']}")
    if "state_in" in exp and r["state"] not in exp["state_in"]:
        fails.append(f"state {r['state']} not in {exp['state_in']}")
    if "outcome" in exp and r["outcome"] != exp["outcome"]:
        fails.append(f"outcome {r['outcome']} != {exp['outcome']}")
    if "lead_status" in exp and r["lead_status"] != exp["lead_status"]:
        fails.append(f"lead_status {r['lead_status']} != {exp['lead_status']}")
    if r["lead_status"] in exp.get("lead_status_not", []):
        fails.append(f"lead_status is {r['lead_status']}")
    fails += [f"missing tool call {t}" for t in exp.get("tools", []) if t not in r["called"]]
    fails += [f"forbidden tool call {t}" for t in exp.get("no_tools", []) if t in r["called"]]
    for pat in exp.get("reply_forbid", []):
        if any(re.search(pat, x) for x in r["replies"]):
            fails.append(f"reply matched forbidden /{pat}/")
    for pat in exp.get("reply_require", []):
        if not any(re.search(pat, x) for x in r["replies"]):
            fails.append(f"no reply matched required /{pat}/")
    if r["invalid_booking"]:
        fails.append("INVALID BOOKING")
    return fails


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids")
    ap.add_argument("--category")
    args = ap.parse_args()
    settings.mail_transport = "mailpit"  # eval bookings send emails; never to a real mailbox
    scenarios = load_scenarios()
    if args.ids:
        scenarios = [s for s in scenarios if s["id"] in args.ids.split(",")]
    if args.category:
        scenarios = [s for s in scenarios if s["category"] == args.category]

    results, cids = [], []
    for sc in scenarios:
        try:
            r = run_scenario(sc)
            fails = check(sc, r)
            cids.append(r["cid"])
        except Exception as e:  # a crash is a failed scenario, not a crashed run
            r, fails = None, [f"error: {type(e).__name__}: {e}"[:300]]
        results.append((sc, r, fails))
        print(f"{'PASS' if not fails else 'FAIL'} {sc['id']:<14} {'; '.join(fails)}", flush=True)

    write_report(results, cids)


def write_report(results, cids) -> None:
    passed = sum(1 for *_, f in results if not f)
    by_cat = defaultdict(lambda: [0, 0])
    for sc, _, f in results:
        by_cat[sc["category"]][1] += 1
        by_cat[sc["category"]][0] += not f
    ran = [(sc, r) for sc, r, _ in results if r]
    tp = sum(1 for sc, r in ran if r["state"] == "ESCALATE" and sc.get("expect", {}).get("state") == "ESCALATE")
    # An escalation is not a false alarm when the scenario allows it (e.g. the 2-failed-turns rule).
    allowed = lambda sc: "ESCALATE" in sc.get("expect", {}).get("state_in", [])
    pred = sum(1 for sc, r in ran if r["state"] == "ESCALATE" and not (allowed(sc) and sc["expect"].get("state") != "ESCALATE"))
    actual = sum(1 for sc, _ in ran if sc.get("expect", {}).get("state") == "ESCALATE")
    invalid = sum(1 for _, r in ran if r["invalid_booking"])
    turn_times = [t for _, r in ran for t in r["times"]]
    with engine.connect() as c:
        llm = c.execute(text("SELECT count(*) n, avg((schema_valid)::int) valid, sum(prompt_tokens) pt, "
                             "sum(completion_tokens) ct, array_agg(DISTINCT model) models FROM llm_calls "
                             "WHERE conversation_id = ANY(:c)"), {"c": cids}).one()
    prompt_version = load_prompt(PROMPT)[0]
    sha = os.environ.get("GIT_SHA", "unknown")

    with engine.begin() as c:
        metrics = {
            "passed": passed, "total": len(results),
            "booking_validity": 1 - invalid / max(len(ran), 1),
            "escalation_precision": tp / pred if pred else 1.0, "escalation_recall": tp / actual if actual else 1.0,
            "schema_validity": float(llm.valid or 0), "llm_calls": llm.n,
            "latency_p50_s": statistics.median(turn_times) if turn_times else 0, "latency_p95_s": pct(turn_times, .95),
            "prompt_tokens": int(llm.pt or 0), "completion_tokens": int(llm.ct or 0),
            "categories": {k: {"passed": v[0], "total": v[1]} for k, v in by_cat.items()},
        }
        run_id = c.execute(text("INSERT INTO eval_runs (git_sha, model, prompt_version, metrics_json) "
                                "VALUES (:g, :m, :p, CAST(:j AS jsonb)) RETURNING id"),
                           {"g": sha, "m": ",".join(llm.models or []), "p": prompt_version,
                            "j": json.dumps(metrics)}).scalar_one()
        for sc, r, f in results:
            c.execute(text("INSERT INTO eval_results (run_id, scenario_id, passed, details_json) "
                           "VALUES (:r, :s, :p, CAST(:d AS jsonb))"),
                      {"r": run_id, "s": sc["id"], "p": not f, "d": json.dumps({"fails": f, "replies": r and r["replies"]})})

    lines = [
        f"# Eval report ({date.today()})", "",
        f"- Git SHA: `{sha}`  Prompt: `{prompt_version}`  Models: {', '.join(llm.models or [])}",
        f"- Overall: **{passed}/{len(results)}** scenarios passed", "",
        "| Metric | Value |", "|---|---|",
        f"| Booking validity (must be 100%) | {100 * (1 - invalid / max(len(ran), 1)):.0f}% |",
        f"| Escalation precision / recall | {tp}/{pred or 0} / {tp}/{actual or 0} |",
        f"| Schema validity (first try) | {100 * float(llm.valid or 0):.0f}% over {llm.n} LLM calls |",
        f"| Turn latency p50 / p95 | {statistics.median(turn_times) if turn_times else 0:.1f}s / {pct(turn_times, .95):.1f}s |",
        f"| Tokens (prompt / completion) | {llm.pt or 0} / {llm.ct or 0} (local = $0) |", "",
        "| Category | Passed |", "|---|---|",
        *[f"| {k} | {v[0]}/{v[1]} |" for k, v in sorted(by_cat.items())], "",
        "## Failures", "",
        *[f"- `{sc['id']}`: {'; '.join(f)}" for sc, _, f in results if f],
    ]
    out = HERE / "reports" / ("latest.md" if len(results) == len(load_scenarios()) else "latest-partial.md")  # a partial run must not overwrite the full report
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
