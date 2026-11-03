import logging
import uuid

from sqlalchemy import text

from . import llm
from .db import tx
from .pack import get_pack

log = logging.getLogger("leadpilot.faq")

def seed_faq(tenant_id: str, reload: bool = False) -> None:
    """Embed and insert the FAQ if this tenant has none (reload: replace its rows). Embedding failures are logged, not fatal."""
    t = str(uuid.UUID(str(tenant_id)))
    entries = get_pack(t).faq  # before the transaction: a tenant without a pack raises PackError
    with tx(t) as c:
        if reload:
            c.execute(text("DELETE FROM faq_chunks WHERE tenant_id = :t"), {"t": t})
        elif c.execute(text("SELECT 1 FROM faq_chunks WHERE tenant_id = :t LIMIT 1"), {"t": t}).first():
            return
        try:
            for e in entries:
                source, chunk = e.source, e.text
                c.execute(
                    text("INSERT INTO faq_chunks (tenant_id, source, text, embedding) VALUES (:tn, :s, :t, CAST(:e AS vector))"),
                    {"tn": t, "s": source, "t": chunk, "e": vector_literal(llm.embed(chunk))},
                )
        except Exception:
            log.exception("FAQ seeding failed; lookup_faq will return nothing")
            raise


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(str(x) for x in v) + "]"
