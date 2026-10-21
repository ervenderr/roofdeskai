"""First start on an empty database (a hosted deploy): create the schema and load the FAQ rows. A no-op everywhere else."""
import logging
from pathlib import Path

from sqlalchemy import text

from .config import settings
from .db import engine

log = logging.getLogger("leadpilot.bootstrap")


def _run(c, name: str) -> None:
    c.exec_driver_sql((settings.db_dir / name).read_text())  # multi-statement files, no bind params


def bootstrap_schema() -> bool:
    with engine.begin() as c:
        if c.execute(text("SELECT to_regclass('public.leads')")).scalar():
            return False
        for f in ("init.sql", "outreach.sql", "faq_seed.sql"):
            if (settings.db_dir / f).is_file():
                _run(c, f)
    log.info("empty database: schema created")
    return True
