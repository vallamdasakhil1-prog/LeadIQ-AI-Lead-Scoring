# LeadIQ – AI-Based Lead Scoring System

Built for the Leadonspot AI/ML Intern technical assessment. Leads are scored by a **deterministic, weighted rule engine**;
**Google Gemini only writes the explanation, insights and next action** and can never change the score or classification.

## Problem statement
Sales teams waste time on leads that will never buy. LeadIQ ranks every lead 0–100, classifies it HOT / WARM / COLD, explains
exactly why, states how much to trust the data, and recommends the next sales action.

## Key features
* 11-field lead form; missing/invalid fields are flagged, normalised, and never block an otherwise usable lead
* Transparent 7-parameter scoring (weights sum to 100), configurable thresholds, full per-rule breakdown
* All seven outputs per lead: score, classification, quality assessment, positive factors, negative factors, scoring explanation, confidence, next action
* Confidence (HIGH/MEDIUM/LOW) computed independently of the score — it measures data quality, not conversion probability
* Gemini analysis with structured JSON + Pydantic validation, and a full rule-based fallback when Gemini is unavailable
* Dashboard, lead management (search/filter), assessment page, analytics — all from real database records; light & dark themes
* SQLite persistence incl. score breakdown and assessment history; Swagger docs at `/docs`

## Technology stack
Next.js 16 · TypeScript · Tailwind CSS 4 · shadcn/ui-style components (Radix + cva) · Recharts · Lucide  |
Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy · SQLite · `google-genai` · Pytest

## Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). In short: `routes → assessment_service → (lead_validator → scoring_engine → confidence → narrative) → optional gemini_service → SQLite`.

## Scoring methodology
See [docs/SCORING_METHODOLOGY.md](docs/SCORING_METHODOLOGY.md).

| Parameter | Weight |
|---|---:|
| Industry relevance | 20 |
| Purchase intent | 25 |
| Job title / authority | 15 |
| Company size | 10 |
| Lead source | 10 |
| Contact information | 10 |
| Company information completeness | 10 |

HOT 75–100 · WARM 50–74 · COLD 0–49 (override with `HOT_THRESHOLD` / `WARM_THRESHOLD`). Weights/keywords can be overridden via `SCORING_CONFIG_PATH`.
Weights reflect buying signal strength: intent and fit matter most; the remaining factors support prioritisation.

## Gemini integration
`backend/app/services/gemini_service.py` uses the official `google-genai` SDK with `response_mime_type="application/json"` and a Pydantic response schema.
Gemini receives the lead, score, classification, breakdown, factors and confidence and returns: quality assessment, natural-language explanation, business insights and next action.
Safeguards: scoring runs first; the response has no score fields; contradicting scores/labels are rejected; timeouts, rate limits (one retry), network/API errors, missing key and invalid JSON all fall back to rule-based text. The key lives only in the backend environment.

## Confidence calculation
Completeness (40) + contact validity (25) + reliability (20) + consistency (15) → HIGH ≥ 75, MEDIUM ≥ 50, LOW < 50. See the methodology doc.

## Installation & setup
Requirements: Python 3.12+, Node 20+.

```bash
git clone <your-repo-url> leadiq && cd leadiq
cp .env.example backend/.env          # then edit: GEMINI_API_KEY and GEMINI_MODEL
```

### Run the backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed            # optional: load sample leads, scored by the real engine (add --no-ai to skip Gemini)
uvicorn app.main:app --reload --port 8000     # Swagger UI: http://localhost:8000/docs
```

### Run the frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                           # http://localhost:3000
```

### Run the tests
```bash
cd backend && source .venv/bin/activate && pytest -v      # 35 tests, no network or API key needed
```
See [docs/TESTING.md](docs/TESTING.md).

## Sample input / output
Input: Rahul Sharma · ABC Technologies · www.abctechnologies.com · Founder · IT Services · Bangalore · 50–100 Employees · Website · "Looking for CRM software" · rahul@example.com · +91 9876543210

Output (rule-based fields shown; with a key, the quality assessment / insights / next action are written by Gemini):
```
Score 93 / 100 → HOT          Confidence: HIGH (96/100, data quality – not conversion probability)
Industry 20/20 · Intent 19/25 · Title 15/15 · Size 10/10 · Source 9/10 · Contact 10/10 · Completeness 10/10
Final Score = 20 + 19 + 15 + 10 + 9 + 10 + 10 = 93
+ Relevant industry; specific solution requested (CRM); clear buying signal; Founder has decision-making authority; valid contact details
− Unclear purchase timeline or budget
Next action: Schedule a product demonstration with Rahul Sharma within 48 hours and prepare a tailored proposal.
```

## Screenshots
Not included yet — run the app locally and add captures of the Dashboard, Add Lead, Assessment, Leads and Analytics pages to `docs/screenshots/`.

## Limitations and future improvements
* Purchase intent uses keyword rules; a trained model or embeddings could capture nuance (but must stay explainable).
* Rule tables are tuned for a CRM/software seller; make per-tenant configs editable in the UI.
* 10-digit phone numbers are assumed Indian; add per-lead country handling.
* No authentication/multi-tenancy; SQLite is for local use (switch `DATABASE_URL` for Postgres).
* The Gemini path is covered by mocked tests; verify it with your own key before the demo. The default model name (`gemini-2.5-flash`) is only a default — set `GEMINI_MODEL` to a model your key supports.
* UI components follow shadcn/ui conventions but were written by hand (the shadcn CLI registry was unreachable in the build environment).
* Future: CSV import, webhook/CRM export, score-weight tuning from won/lost outcomes, Docker Compose.
