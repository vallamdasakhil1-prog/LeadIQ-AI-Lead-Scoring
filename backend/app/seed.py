"""Insert demonstration leads and score them with the real engine.

    python -m app.seed            # uses Gemini if GEMINI_API_KEY is set
    python -m app.seed --no-ai    # deterministic rule-based narrative only
"""
from __future__ import annotations

import sys

from .database import SessionLocal, init_db
from .sample_data import RAHUL_SHARMA, SYNTHETIC_LEADS
from .services.assessment_service import assess_lead, create_lead
from .services.gemini_service import GeminiService


def main() -> None:
    init_db()
    gemini = None if "--no-ai" in sys.argv else GeminiService()
    if gemini is not None and not gemini.is_configured:
        gemini = None
    with SessionLocal() as db:
        for payload in [RAHUL_SHARMA, *SYNTHETIC_LEADS]:
            lead, _ = create_lead(db, payload)
            a = assess_lead(db, lead, gemini)
            label = lead.name or lead.company_name
            print(f"{label:<22} {a.score:>6.2f}  {a.classification:<5} confidence={a.confidence_level:<6} ({a.explanation_source})")


if __name__ == "__main__":
    main()
