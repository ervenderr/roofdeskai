"""python -m evals.modules [--module quote|capacity|brief|reviews|intake]: exits 1 if any case fails."""
import argparse
import sys

from .loader import MODULES, run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", choices=MODULES)
    arg = ap.parse_args().module
    mods = [arg] if arg else MODULES
    failed = 0
    for m in mods:
        res = run(m)
        bad = [r for r in res if not r.ok]
        failed += len(bad) + (not res)
        print(f"{m}: {len(res) - len(bad)}/{len(res)} passed")
        for r in bad:
            print(f"  FAIL {m}:{r.id}: {r.detail}")
        if not res:
            print("  FAIL empty case set")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
