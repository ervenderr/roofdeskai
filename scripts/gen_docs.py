"""Deterministic docs: python -m scripts.gen_docs (make gen-docs).
Renders one SOP per workflow and one runbook per pack into docs/generated/, plus the README generated blocks.
Pure render_all() returns {relative path: content}; main() writes. No timestamps, shas, absolute paths or env values.
Never run gen-docs with the e2e overlay (it must see the branch mounts only)."""
import json
import re
import sys
from pathlib import Path
from string import Template

import yaml

from app.pack import load_pack
from evals.runner import default_baseline_path

ROOT = Path(__file__).resolve().parents[1]
TPL = Path(__file__).resolve().parent / "doc_templates"
API_MARKERS = ("$env.API_URL", "api:8000", "localhost:8000")
TRIGGERS = {"webhook": "webhook", "scheduleTrigger": "schedule", "manualTrigger": "manual",
            "executeWorkflowTrigger": "called by another workflow", "errorTrigger": "error trigger"}
KEYS = {"x-api-key": "tenant key", "x-admin-key": "admin key"}
MODULES = ("brief", "capacity", "intake", "quote", "reviews")


def fill(template: str, **kw: str) -> str:
    return Template(template).substitute(**kw)  # substitute, not safe_substitute: a missing key raises


def _tpl(name: str) -> str:
    return (TPL / name).read_text(encoding="utf-8")


def _end(text: str) -> str:
    return text.rstrip("\n") + "\n"


def _workflows(wf_dir: Path) -> list[dict]:
    out = []
    for f in sorted(wf_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        triggers, keys = [], set()
        for n in data["nodes"]:
            kind = n["type"].split(".")[-1]
            if kind in TRIGGERS:
                path = n["parameters"].get("path")
                triggers.append(TRIGGERS[kind] + (f" (path {path})" if path else ""))
            if kind == "httpRequest":
                p = n["parameters"]
                if not any(m in str(p.get("url", "")) for m in API_MARKERS) or not p.get("sendHeaders"):
                    continue
                for h in p.get("headerParameters", {}).get("parameters", []):
                    if h["name"].lower() in KEYS:
                        keys.add(KEYS[h["name"].lower()])
        out.append({"file": f.name, "stem": f.stem, "name": data["name"], "nodes": len(data["nodes"]),
                    "triggers": triggers, "keys": sorted(keys)})
    return out


def _hours(p) -> str:
    c = p.calendar
    days = "weekdays only" if c.weekdays_only else "every day"
    return f"{', '.join(f'{h}:00' for h in c.slot_hours)} local, {c.slot_minutes}-minute slots, {days}, {c.days_ahead} days ahead"


def _pack_vars(p) -> dict[str, str]:
    return {"business": p.meta.business, "kind": p.meta.kind, "offer": p.meta.offer, "timezone": p.meta.timezone,
            "hours": _hours(p), "escalation": ", ".join(p.escalation.always_human) or "none listed",
            "subject": p.messages.owner_alert_subject, "slug": p.slug}


def _sop(p, wf: dict) -> str:
    keys = ", ".join(wf["keys"]) or "none (no API calls)"
    triggers = "\n".join(f"  - {t}" for t in wf["triggers"]) or "  - none"
    return _end(fill(_tpl("sop.md.tpl"), workflow=wf["stem"], workflow_name=wf["name"], file=wf["file"],
                     nodes=str(wf["nodes"]), triggers=triggers, keys=keys, **_pack_vars(p)))


def _runbook(p, wfs: list[dict]) -> str:
    listing = "\n".join(f"- {w['name']}: sop-{w['stem']}.md" for w in wfs)
    blob = " ".join([p.messages.model_dump_json(), p.escalation.safety, *(e.text for e in p.faq)])
    notes = ""
    if re.search(r"\b144\b", blob):  # Swiss emergency number text
        notes = ("\n## Needs review\n\n- This pack contains the Swiss emergency number (144) in its text. "
                 "Confirm it with the owner before real use; this is not a legal conclusion.\n")
    return _end(fill(_tpl("runbook.md.tpl"), workflows=listing, notes=notes, **_pack_vars(p)))


def _slugs(businesses_dir: Path) -> list[str]:
    return sorted(d.name for d in businesses_dir.iterdir() if (d / "pack.yaml").exists())


def render_all(businesses_dir: Path | None = None, workflows_dir: Path | None = None) -> dict[str, str]:
    biz, wf_dir = businesses_dir or ROOT / "businesses", workflows_dir or ROOT / "n8n" / "workflows"
    wfs = _workflows(wf_dir)
    out: dict[str, str] = {}
    for slug in _slugs(biz):
        p = load_pack(slug, biz)
        base = f"docs/generated/{slug}"
        out[f"{base}/runbook.md"] = _runbook(p, wfs)
        for wf in wfs:
            out[f"{base}/sop-{wf['stem']}.md"] = _sop(p, wf)
    return dict(sorted(out.items()))


def scorecard_block(businesses_dir: Path | None = None) -> str:
    """Per-pack rows from each pack's committed baseline (default_baseline_path); nothing else in evals is read."""
    rows = ["| Pack | Passed | By category |", "|---|---|---|"]
    for slug in _slugs(businesses_dir or ROOT / "businesses"):
        data = json.loads(default_baseline_path(slug).read_text(encoding="utf-8"))  # missing baseline raises
        cats: dict[str, list[int]] = {}
        for s in data["scenarios"].values():
            c = cats.setdefault(s["category"], [0, 0])
            c[0] += bool(s["passed"])
            c[1] += 1
        by_cat = ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(cats.items()))
        m = data["meta"]
        rows.append(f"| {slug} | {m['passed']}/{m['total']} | {by_cat} |")
    counts = ", ".join(
        f"{m} {len(yaml.safe_load((ROOT / 'evals' / 'modules' / m / 'cases.yaml').read_text(encoding='utf-8')))} cases"
        for m in MODULES)
    return "\n".join(rows) + f"\n\nModule eval sets (case counts, not run results): {counts}."


def catalog_block(workflows_dir: Path | None = None) -> str:
    rows = ["| Workflow | Name | Triggers | Tenant-aware | Nodes |", "|---|---|---|---|---|"]
    for w in _workflows(workflows_dir or ROOT / "n8n" / "workflows"):
        aware = "yes" if "tenant key" in w["keys"] else "no"
        rows.append(f"| {w['stem']} | {w['name']} | {', '.join(w['triggers']) or 'none'} | {aware} | {w['nodes']} |")
    return "\n".join(rows)


def _replace(text: str, name: str, body: str) -> str:
    begin, end = f"<!-- BEGIN GENERATED: {name} -->", f"<!-- END GENERATED: {name} -->"
    if text.count(begin) != 1 or text.count(end) != 1 or text.index(begin) > text.index(end):
        raise ValueError(f"README marker for {name!r} missing or duplicated")
    i, j = text.index(begin) + len(begin), text.index(end)
    return text[:i] + "\n" + body + "\n" + text[j:]


def render_readme(text: str) -> str:
    return _replace(_replace(text, "scorecard", scorecard_block()), "catalog", catalog_block())


def write_docs(docs: dict[str, str], root: Path = ROOT) -> None:
    for pack_dir in sorted({Path(k).parent for k in docs}):
        d = root / pack_dir
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f"{pack_dir.as_posix()}/{f.name}" not in docs:
                    f.unlink()  # stale generated file
    for rel, body in docs.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def main() -> int:
    write_docs(render_all())
    readme = ROOT / "README.md"
    readme.write_text(render_readme(readme.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
