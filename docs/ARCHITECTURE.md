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

## Gemini: responsibilities and limits
**Gemini writes text only:** the lead quality assessment, a natural-language explanation, business insights and a recommended next action.
It does **not** calculate, adjust or rank anything. If it is unavailable or its answer is rejected, rule-based text (`narrative.py`) is used and the
score, classification, breakdown, factors, confidence and a deterministic calculation text are unaffected.

## How the score is protected from Gemini
* Scoring runs **before** Gemini is called; `scoring_engine`, `intent`, `confidence`, `lead_validator` and `narrative` import nothing from Gemini or any HTTP library (tested).
* The persisted `score`/`classification` come from the engine result object. Gemini receives a *copy* of the data (a test mutates it and the stored result is unchanged).
* `GeminiAnalysis` has four text fields and `extra="forbid"`: a response containing `score`, `classification` or any other key fails validation.
* The same schema is sent to Gemini as `response_schema` with `response_mime_type="application/json"`.

## Treating lead data as untrusted (prompt-injection defence)
1. **Separation:** rules go in the SDK's `system_instruction`; the lead is sent in the user turn as JSON inside `<lead_analysis_data>` tags under `untrusted_lead_data`, next to the engine's results. The system prompt says everything inside is data, never instructions.
2. **Escaping:** the JSON is ASCII-escaped and `<`/`>` become `\u003c`/`\u003e`, so lead text cannot forge or close the tags.
3. **Scrubbing (`prompt_safety.py`):** every string in the payload — including engine explanations that quote lead text — has control/zero-width characters removed and length capped; strings that look like instructions ("ignore previous instructions", "set the score to 100", role changes, fake system tags, forged JSON keys, requests to reveal the prompt/keys) are replaced with a placeholder and recorded. Lead fields containing such text also lower the *confidence* (reliability −5) and are listed in the assessment's `confidence_details.prompt_injection_flags`; they never change the score.
4. **Output validation:** strict schema (above), length limits, and cross-checks against the engine — any stated overall score or HOT/WARM/COLD label that differs from the engine's, talk of "recalculating/overriding", links or HTML, or claims that contact details are verified, causes the response to be rejected.
5. **Fallback:** any rejection or failure keeps the rule-based text; `explanation_source` records `gemini` or `rule_based` and `gemini_error` the reason.

Detection is a best-effort layer; the guarantees are 1–2 and 4–5 plus the architectural fact that the number does not depend on Gemini at all.
Residual risks: a clever injection that evades the patterns could still influence Gemini's *wording* (not numbers), within the schema and cross-checks; keyword-stuffing a requirement can raise the deterministic intent score.

## Failure handling (all fall back to rule-based text)
missing/placeholder key · 429 rate limit (one retry) · timeout · network error · 404 model-not-found · other API errors · malformed or schema-invalid JSON · contradictory or unsafe content.

## Data model
* `leads` – raw fields as submitted, normalised JSON, validation report.
* `assessments` – score, classification, confidence (+ components), factors, explanations, next action, config snapshot (weights/thresholds used).
* `score_breakdowns` – one row per parameter per assessment (max, score, criteria, rule, explanation).
* `assessment_history` – append-only log of every assessment run.

Analytics (`GET /api/analytics/overview`) is computed in SQL/Python from the latest assessment of each lead; nothing is hard-coded.
