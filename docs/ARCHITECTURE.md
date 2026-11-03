# Architecture

```
Browser (Next.js, TypeScript, Tailwind, Recharts)
   │  fetch JSON (no secrets in the browser)
   ▼
FastAPI  ── routes/ (leads, analytics, health)
   │
   ├─ services/lead_validator.py     normalise + validate (valid | missing | invalid)
   ├─ services/scoring_engine.py     DETERMINISTIC weighted rules  ← source of truth
   ├─ services/confidence.py         data-quality confidence (independent of score)
   ├─ services/narrative.py          rule-based fallback text / next action
   ├─ services/gemini_service.py     Gemini (google-genai) – explanations only
   └─ services/assessment_service.py orchestration + persistence
   ▼
SQLite via SQLAlchemy: leads, assessments, score_breakdowns, assessment_history
```

## Request flow (`POST /api/leads/{id}/assess`)
1. Load the lead and re-normalise its stored raw fields.
2. `score_lead()` → score, classification, 7 parameter results, positive/negative factors.
3. `calculate_confidence()` → HIGH/MEDIUM/LOW.
4. Build the rule-based narrative (always available).
5. Call Gemini with the lead, score, classification, breakdown, factors and confidence. On success its quality assessment,
   explanation, insights and next action replace the fallback text. On **any** failure the fallback is kept and the reason is stored.
6. Persist `Assessment` + 7 `ScoreBreakdown` rows + an `AssessmentHistory` row. Return the assessment.

## How Gemini is prevented from affecting the score
* Scoring happens **before** Gemini is called and imports nothing from it.
* The persisted `score`/`classification` are read from the engine result; the Gemini response object has no such fields
  (`GeminiAnalysis` = quality_assessment, scoring_explanation, business_insights, recommended_next_action).
* The response is requested as JSON with a response schema and validated with Pydantic.
* A guard rejects responses that state a different `N/100` score or a different HOT/WARM/COLD label.
* The system prompt forbids recalculating scores or inventing missing fields; null fields are sent as null.
* The API key is read from the backend environment only; the frontend only knows `NEXT_PUBLIC_API_URL`.

## Failure handling (all fall back to rule-based text)
missing/placeholder key · 429 rate limit (one retry) · timeout · network error · other API errors · malformed or schema-invalid JSON ·
contradictory content. `assessments.explanation_source` is `gemini` or `rule_based`; `gemini_error` records the reason.

## Data model
* `leads` – raw fields as submitted, normalised JSON, validation report.
* `assessments` – score, classification, confidence (+ components), factors, explanations, next action, config snapshot (weights/thresholds used).
* `score_breakdowns` – one row per parameter per assessment (max, score, criteria, rule, explanation).
* `assessment_history` – append-only log of every assessment run.

Analytics (`GET /api/analytics/overview`) is computed in SQL/Python from the latest assessment of each lead; nothing is hard-coded.
