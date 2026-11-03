"""Schema bootstrap: baseline on an empty database (a hosted deploy), then pending numbered migrations on every start.

Operators can also run `python -m app.bootstrap`."""
import logging

from sqlalchemy import text

from .config import settings
from .db import engine

log = logging.getLogger("leadpilot.bootstrap")

MIG_LOCK = 724911  # advisory lock key: two API instances starting together must not run a migration twice


def _run(c, name: str) -> None:
    c.exec_driver_sql((settings.db_dir / name).read_text().replace("%", "%%"))  # multi-statement files; psycopg still parses % even without params


def _lock(c) -> None:
    c.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIG_LOCK})


def apply_migrations(eng=engine) -> list[str]:
    """Apply pending db/migrations/NNN_*.sql, each in its own transaction. Returns the versions applied now.

    shortcut: no checksum, edits to an applied migration are not detected; add one if migrations get edited after release."""
    mdir = settings.db_dir / "migrations"
    if not mdir.is_dir():
        raise FileNotFoundError(f"migrations directory missing: {mdir}")
    with eng.begin() as c:
        c.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
    applied = []
    for f in sorted(mdir.glob("[0-9][0-9][0-9]_*.sql")):
        with eng.begin() as c:
            _lock(c)
            if c.execute(text("SELECT 1 FROM schema_migrations WHERE version=:v"), {"v": f.stem}).first():
                continue  # re-checked under the lock
            _run(c, f"migrations/{f.name}")
            c.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": f.stem})
        applied.append(f.stem)
        log.info("applied migration %s", f.stem)
    return applied


def set_app_role_login(eng=engine, password: str | None = None) -> None:
    """Give app_rw its login password (SQL migrations cannot read env). Literal is built server-side with %L."""
    pw = password or settings.app_db_password
    if not pw:
        return
    with eng.begin() as c:
        stmt = c.execute(text("SELECT format('ALTER ROLE app_rw LOGIN PASSWORD %L', CAST(:p AS text))"), {"p": pw}).scalar()
        c.exec_driver_sql(stmt)


def bootstrap_schema(eng=engine) -> bool:
    created = False
    with eng.begin() as c:
        _lock(c)
        if not c.execute(text("SELECT to_regclass('public.leads')")).scalar():  # guards the baseline only
            for f in ("init.sql", "outreach.sql", "faq_seed.sql"):
                if (settings.db_dir / f).is_file():
                    _run(c, f)
            created = True
            log.info("empty database: schema created")
    apply_migrations(eng)
    set_app_role_login(eng)
    return created


if __name__ == "__main__":
    bootstrap_schema()
    with engine.begin() as c:
        print("migrations:", [r[0] for r in c.execute(text("SELECT version FROM schema_migrations ORDER BY 1"))])
