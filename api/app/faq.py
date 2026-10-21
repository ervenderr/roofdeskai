import logging

from sqlalchemy import text

from . import llm
from .db import engine

log = logging.getLogger("leadpilot.faq")

# Synthetic knowledge base for the fictional Summit Roofing.
FAQ = [
    ("inspection", "The roof inspection is free and takes about 45 to 60 minutes."),
    ("inspection", "An inspection covers shingles, flashing, gutters and attic ventilation, and ends with a photo report."),
    ("inspection", "After the inspection you get a written estimate at no cost and with no obligation."),
    ("warranty", "Roof replacements carry a 10-year workmanship warranty. Roof repairs carry a 1-year workmanship warranty. Manufacturer shingle warranties are separate."),
    ("area", "Summit Roofing serves Denver, Aurora, Lakewood, Arvada, Centennial and Littleton."),
    ("eligibility", "Inspections are booked for property owners only. Renters need the owner to contact us."),
    ("process", "Our process: free inspection, written estimate, scheduling, installation, then a final walkthrough."),
    ("timeline", "A typical roof replacement takes 1 to 3 days depending on roof size."),
    ("pricing", "Pricing depends on roof size, materials and condition. Exact pricing is only given in the written estimate after an inspection; we do not quote prices in chat."),
    ("hours", "Inspections are available Monday to Friday between 8am and 5pm."),
    ("insurance", "We provide a photo report that you can submit to your insurer. We do not file insurance claims for customers."),
    ("materials", "We install asphalt shingle, metal and tile roofs."),
]


def seed_faq() -> None:
    """Embed and insert the FAQ if the table is empty. Embedding failures are logged, not fatal."""
    with engine.begin() as c:
        if c.execute(text("SELECT 1 FROM faq_chunks LIMIT 1")).first():
            return
        try:
            for source, chunk in FAQ:
                c.execute(
                    text("INSERT INTO faq_chunks (source, text, embedding) VALUES (:s, :t, CAST(:e AS vector))"),
                    {"s": source, "t": chunk, "e": vector_literal(llm.embed(chunk))},
                )
        except Exception:
            log.exception("FAQ seeding failed; lookup_faq will return nothing")
            raise


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(str(x) for x in v) + "]"
