"""Copywriter eval: does the model write safe, decent first-contact emails? First-try results, no retries.

    docker compose exec api python -m evals.outreach_runner [--prompt outreach-copy.v1]
"""
import argparse
import json
import re
from pathlib import Path

from app import llm, outreach, prospects
from app.config import settings

HERE = Path(__file__).parent
SAMPLE = next(p for p in (HERE.parent / "scripts" / "sample_prospects.json", Path("/srv/scripts/sample_prospects.json")) if p.exists())


def style_issues(d: outreach.Draft) -> list[str]:
    body, issues = d.body, []
    if "\n\n" not in body:
        issues.append("no paragraph breaks")
    if settings.sender_name.lower() in body.lower() or re.search(r"\bwe'?re (the )?\w+ team\b", body, re.I):
        issues.append("introduces the sender (the signature does that)")
    if re.search(r"your website|have a website", body, re.I):
        issues.append("mentions their website")
    if re.search(r"suggests you|you (clearly |really )?value|i imagine|i'm sure|you must", body, re.I):
        issues.append("speculates about the business")
    if not body.strip().endswith("?"):
        issues.append("does not end with a question")
    if not 40 <= len(body.split()) <= 120:
        issues.append(f"{len(body.split())} words")
    return issues


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=outreach.COPY_PROMPT)
    args = ap.parse_args()
    version, tpl = llm.load_prompt(args.prompt)
    rows = {}
    for r in json.loads(SAMPLE.read_text()):
        if r.get("title"):
            rows.setdefault(r["place_id"], r)  # keep the first of any duplicate rows
    rows = list(rows.values())
    results = []
    for row in rows:
        p = prospects.normalize(row)
        p = {**p, "id": 0, "pain_mentions": prospects.pain_mentions(p["review_texts"])}
        facts = outreach.facts_for(p)
        system = (tpl.replace("<<sender>>", settings.sender_name).replace("<<offer>>", settings.offer_summary)
                  .replace("<<facts>>", json.dumps(facts)))
        out = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": "Write the email."}])
        try:
            d = outreach.Draft(subject=outreach.subject_for(facts), body=outreach.parse_body(out["content"]))
            safety, style = outreach.check_draft(d, facts), style_issues(d)
        except ValueError as e:
            d, safety, style = None, [f"unparseable: {str(e).splitlines()[0][:80]}"], []
        results.append((p["name"], safety, style))
        print(f"{'PASS' if not safety and not style else 'FAIL'} {p['name']:<30} {'; '.join(safety + style)}", flush=True)

    n = len(results)
    safe = sum(1 for _, s, _ in results if not s)
    clean = sum(1 for _, s, t in results if not s and not t)
    report = [f"# Outreach copy eval ({version})", "", f"- Prompt `{version}`, model `{settings.local_llm_model}`, {n} prospects, first try, no retries",
              f"- Safety checks passed (no invented claims, numbers, links): **{safe}/{n}**",
              f"- Safety and style passed: **{clean}/{n}**", "", "## Failures", "",
              *[f"- {name}: {'; '.join(s + t)}" for name, s, t in results if s or t]]
    (HERE / "reports" / f"outreach-{version}.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
