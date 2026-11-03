# Scoring methodology

The score is produced by `backend/app/services/scoring_engine.py`, a pure function with no
database, network or LLM dependency. **Identical normalised input + identical configuration ⇒ identical
output.** Every rule, weight, keyword list and threshold lives in `backend/app/config.py`
(`ScoringConfig`) and can be overridden with environment variables or a JSON file
(`SCORING_CONFIG_PATH`) without touching the engine.

## Pipeline
1. **Normalise & validate** (`lead_validator.py`): trims/collapses whitespace, lower-cases emails, strips scheme/`www`/path from
   websites, converts phones to E.164 (10-digit numbers are assumed Indian, +91), parses company size ranges
   (`50–100 Employees`, `1000+`). Each field becomes `valid`, `missing` or `invalid`. Invalid values are *reported*, never repaired.
2. **Score** each of 7 parameters: `score = round(weight × ratio, 2)` where `ratio ∈ [0,1]` comes from the rule table below.
3. **Sum**: `Final = Σ parameter scores`, clamped to 0–100.
4. **Classify** with configurable thresholds: HOT ≥ 75, WARM ≥ 50, COLD < 50.

## Parameters and rules (default weights; total 100)

| Parameter | Weight | Rule (share of the weight earned) |
|---|---:|---|
| Industry relevance | 20 | Tier-1 target industry (IT services, software, SaaS, fintech, e-commerce, marketing, real estate, consulting…) 100%; tier-2 (finance, healthcare, education, manufacturing, retail, logistics, telecom…) 70%; any other industry 35%; missing/invalid 0% |
| Purchase intent | 25 | Named solution (CRM, ERP, software…) 32% + explicit buying signal ("looking for", "need", "require"…) 36% + timeline/budget cue ("urgent", "this month", "budget") 20% + detail (≥6 words 12%, 3–5 words 8%, 1–2 words 3%). Negative wording ("student", "college project", "not interested", "just looking"…) caps the parameter at 12%. Missing/invalid 0% |
| Job title / authority | 15 | Founder/Owner/C-level/MD 100%; Director/VP/Head 87%; Manager 67%; Senior/Lead 47%; individual contributor 27%; other title 20%; assistant/junior capped at 27%; student/intern 7%; missing/invalid 0%. Highest matching tier wins, then the junior/student caps apply |
| Company size | 10 | Midpoint of the stated range: ≤10 → 40%; 11–50 → 70%; 51–500 → 100%; 501–1000 → 80%; >1000 → 70%; missing/invalid 0% |
| Lead source | 10 | Referral/demo request 100%; website/inbound 90%; partner 80%; event/webinar/LinkedIn 70%; email campaign/ads 60%; social 50%; cold/outbound/purchased list 30%; other known source 40%; missing/invalid 0% |
| Contact information | 10 | Valid email 40% (+10% if business domain; disposable domains earn half and no bonus) + valid phone 40% + valid name 10%. Invalid/missing items earn 0 |
| Company completeness | 10 | Company name 30% + website 30% + location 20% + company size 20%, each only if present **and** valid |

Every `ParameterResult` stores: maximum weight, evaluation criteria, the rule text that applies, the actual score and a
plain-language explanation. These are persisted per assessment in `score_breakdowns` and shown in the UI.

## Missing and invalid data
* Missing data never earns full marks (each rule awards 0 for a missing field).
* Invalid data (e.g. `12345` as a phone, `lots` as company size) earns 0 for that component and is listed as a negative factor.
* A lead is rejected (HTTP 422) only when it has **neither** a valid name **nor** a valid company name.

## Worked example — Rahul Sharma (sample lead)
Industry 20 + Intent 19 (solution 8 + buying signal 9 + 4-word detail 2) + Title 15 + Size 10 + Source 9 + Contact 10 + Completeness 10 = **93 → HOT**.
The only negative factor is the missing purchase timeline.

## Why these weights
Purchase intent (25) is the strongest signal that a lead will buy now, so it is weighted highest. Industry fit (20) determines whether
the product solves the lead's problem at all. Authority (15) shows whether this person can sign the deal. Size, source, contact quality
and company completeness (10 each) are supporting signals: useful for prioritisation, but individually unable to make a lead hot.

## Confidence (separate from the score)
`services/confidence.py` never reads the score. It measures **trust in the data**, not conversion probability:

| Component | Max | Based on |
|---|---:|---|
| Data completeness | 40 | share of the 11 fields supplied |
| Contact validity | 25 | valid email 12, valid phone 10, valid name 3 |
| Information reliability | 20 | −4 per invalid field (max −12), free-mail −2, disposable email −6, placeholder text −5 |
| Consistency | 15 | −7 student title with an enterprise purchase claim; −7 high-intent source with "no requirement" wording; −4 email domain ≠ website |

HIGH ≥ 75, MEDIUM ≥ 50, LOW < 50. A complete, valid but poor-fit lead can therefore be *COLD with HIGH confidence*,
and a promising lead with sparse data can be *WARM with LOW confidence*.
