"""Gate: shared code must stay business-neutral (OPS-06).

Scans explicit shared roots for the roofing-business words (case-insensitive;
the product name and the America/<city> timezone token are stripped first).
Every remaining hit file must be in ALLOW with its exact hit count and a
reason; a changed count (including zero) fails, so entries cannot rot.

Excluded, by design: pack and client data, test code and fixtures, eval
scenario data (cases.yaml), docs and planning, baselines and reports,
dashboard data snapshots, sample prospects, build output, and this script and
its test (they define the pattern).

Run: make check-shared (g-stack api container). Stdlib only.
"""
import re
import sys
from pathlib import Path

# Built from fragments so this file does not contain the banned words.
PATTERN = re.compile("ro" + "of(?!desk)|sum" + "mit|den" + "ver", re.IGNORECASE)
TZ_TOKEN = "America/Den" + "ver"

ROOTS = (
    "api/app", "n8n/workflows", "prompts", "scripts",
    "evals/runner.py", "evals/outreach_runner.py", "evals/modules",
    "dashboard/app", "dashboard/components", "dashboard/lib",
)
EXCLUDE_DIRS = {"node_modules", ".next", "__pycache__", "tests_data"}
EXCLUDE_NAMES = {
    "conftest.py", "cases.yaml",  # eval scenario data
    "sample_prospects.json",  # outbound sample data
    "check_shared.py", "test_shared_gate.py",  # define the pattern
}
TEXT_SUFFIXES = {".py", ".json", ".md", ".yaml", ".yml", ".ts", ".tsx", ".js", ".mjs", ".sh", ".txt", ".css", ".tpl"}

ALLOW = {
    "api/app/config.py": (4, "legacy default tenant/profile; changing the default is a behaviour change"),
    "api/app/replies.py": (1, "RoofDesk-own outbound demo reply text"),
    "api/app/outreach.py": (2, "RoofDesk-own outbound module, docstring example company"),
    "api/app/prospects.py": (1, "outbound target list is RoofDesk's own market, not a tenant"),
    "prompts/agent.v1.md": (4, "frozen legacy prompt, byte-identical for baselines"),
    "prompts/system.v1.md": (4, "frozen legacy prompt, byte-identical for baselines"),
    "prompts/agent.v2.md": (2, "frozen prompt few-shot example, byte-identical render"),
    "n8n/workflows/outreach-flow.json": (16, "untenanted RoofDesk-own outreach workflow, structure pinned by tests"),
    "evals/runner.py": (19, "frozen regression-gate naming and default pack"),
    "scripts/seed_demo.py": (12, "seeder for the live roofing demo"),
    "dashboard/app/page.tsx": (2, "demo page showing the roofing snapshot"),
}


def _skipped(rel: Path) -> bool:
    return (
        any(p in EXCLUDE_DIRS for p in rel.parts)
        or rel.name in EXCLUDE_NAMES
        or rel.name.startswith("test_")
        or rel.suffix not in TEXT_SUFFIXES
    )


def find_hits(root: Path, roots=ROOTS) -> dict[str, int]:
    """Return {relative posix path: hit count} for non-excluded files under roots."""
    root = Path(root)
    hits: dict[str, int] = {}
    for r in roots:
        base = root / r
        if not base.exists():
            raise FileNotFoundError(f"scan root missing: {base} (gate would pass silently)")
        files = [base] if base.is_file() else sorted(base.rglob("*"))
        for f in files:
            rel = f.relative_to(root)
            if not f.is_file() or _skipped(rel):
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue  # binary
            n = len(PATTERN.findall(text.replace(TZ_TOKEN, "")))
            if n:
                hits[rel.as_posix()] = n
    return hits


def check(hits: dict[str, int], allow=ALLOW) -> list[str]:
    """Return human-readable problems; empty list means the gate passes."""
    problems = []
    for path, n in sorted(hits.items()):
        if path not in allow:
            problems.append(f"offender: {path} has {n} hit(s), not in ALLOW")
    for path, (expected, _reason) in sorted(allow.items()):
        actual = hits.get(path, 0)
        if actual != expected:
            problems.append(f"count mismatch: {path} expected {expected}, found {actual} (stale or grown ALLOW entry)")
    return problems


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    problems = check(find_hits(root))
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    print(f"check-shared OK: {len(ALLOW)} allowlisted files, no other hits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
