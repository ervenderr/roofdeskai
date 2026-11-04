"""Age out PII: python -m scripts.retention [--days N] [--tenant ID]. Days default to RETENTION_DAYS; 0 disables."""
import argparse

from app import retention
from app.config import settings


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--tenant", default=None)
    a = ap.parse_args(argv)
    days = settings.retention_days if a.days is None else a.days
    if days <= 0:
        print("retention disabled (RETENTION_DAYS=0)")
        return
    result = {a.tenant: retention.purge_tenant(a.tenant, days)} if a.tenant else retention.purge_all(days)
    for tid, counts in result.items():
        print(tid, {k: v for k, v in counts.items() if v})


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
