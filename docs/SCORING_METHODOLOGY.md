# Scoring methodology

The score is produced by `backend/app/services/scoring_engine.py`, a pure function with **no database, network or LLM
dependency** (a test asserts the module imports nothing from Gemini or any HTTP library). Given the same normalised input and the
same configuration it always returns the same result — also across processes and `PYTHONHASHSEED` values (tested).
Every rule, weight, keyword list and threshold lives in `backend/app/config.py` (`ScoringConfig`) and can be overridden with
environment variables or a JSON file (`SCORING_CONFIG_PATH`) without touching the engine.

## Pipeline
1. **Normalise & validate** (`lead_validator.py`): trim/collapse whitespace, lower-case emails, strip scheme/`www`/path from websites,
   convert phones to E.164 (10-digit numbers are assumed Indian, +91), parse company size (`50–100 Employees`, `1000+`).
   Each field becomes `valid`, `missing` or `invalid`. Invalid values are *reported*, never repaired.
2. **Score** each of the 7 parameters: `score = round(weight × ratio, 2)`, `ratio ∈ [0, 1]` from the rule tables below.
3. **Sum**: `Final = Σ parameter scores`, clamped to 0–100.
4. **Classify** (configurable): HOT ≥ 75, WARM ≥ 50, COLD < 50.
5. **Safeguard**: if the requirement expresses negative purchase intent, the classification is capped at `negative_intent_max_classification` (default WARM). The score from step 3 is never modified.

## Parameters and rules (default weights, total 100)

| Parameter | Weight | Rule (share of the weight earned) |
|---|---:|---|
| Industry relevance | 20 | Tier-1 target industry (IT services, software, SaaS, fintech, e-commerce, marketing, real estate, consulting…) 100%; tier-2 (finance, healthcare, education, manufacturing, retail, logistics, telecom…) 70%; any other industry 35%; missing/invalid 0% |
| Purchase intent | 25 | Named solution (CRM, ERP, software…) 32% + **non-negated** buying signal ("looking for", "need", "require", "buy"…) 36% + timeline/budget cue ("urgent", "this month", "budget approved") 20% + detail (≥ 6 words 12%, 3–5 words 8%, 1–2 words 3%). Negative intent caps the parameter at 12% (see below). Missing/invalid 0% |
| Job title / authority | 15 | Founder/Owner/C-level/MD 100%; Director/VP/Head 87%; Manager 67%; Senior/Lead 47%; individual contributor 27%; other title 20%; assistant/junior capped at 27%; student/intern 7%; missing/invalid 0%. Highest matching tier wins, then the junior/student caps apply |
| Company size | 10 | Midpoint of the stated range: ≤ 10 → 40%; 11–50 → 70%; 51–500 → 100%; 501–1000 → 80%; > 1000 → 70%; missing/invalid 0% |
| Lead source | 10 | Referral/demo request 100%; website/inbound 90%; partner 80%; event/webinar/LinkedIn 70%; email campaign/ads 60%; social 50%; cold/outbound/purchased list 30%; other known source 40%; missing/invalid 0% |
| Contact information | 10 | Well-formed email 40% (+10% only for a genuine business domain: free-mail, disposable and **reserved example domains earn no bonus**; disposable earns half the email credit) + well-formed phone 40% + valid name 10%. Missing/malformed items earn 0 |
| Company completeness | 10 | Company name 30% + website 30% + location 20% + size 20%, each only if present **and** well-formed |

Each `ParameterResult` stores its maximum weight, evaluation criteria, the rule text, the actual score and an explanation; these are
persisted in `score_breakdowns` and shown in the UI.

## Purchase intent: negation-aware detection (`services/intent.py`)
Plain keyword matching would read "**not** looking for a CRM" as a buying signal. The analyser therefore checks every phrase for negation:

* A phrase is **negated** when a cue (`not`, `no`, `never`, `without`, `neither`, `nor`, `cannot`, `none`, `nothing`, or any `…n't` word such
  as *don't*, *doesn't*, *isn't*) appears within **4 tokens before it, in the same clause**. The window is `intent_negation_window`.
* Clauses end at punctuation (`. , ; : ! ?` and brackets) and at contrast words (*but, however, although, though, yet, except, whereas*), so
  "Not looking for ERP, but need a CRM urgently" keeps *need* affirmed.
* "not only…", "not just…" and "no doubt" are **not** treated as negation.
* Typographic apostrophes (`don’t`) and upper-case text are handled.
* **Negated buying phrases earn no credit.** Negation targets are the buying phrases plus *requirement(s), purchase, purchasing, buying,
  interested, interest, planning, plans, intent, intention, looking* — which is how "no purchase requirement", "not interested in buying" and
  "not planning to purchase" are caught.
* **Negative intent** = (a negated buying phrase exists **and** no affirmed buying phrase does) **or** explicit non-purchase wording
  ("student", "college project", "just browsing", "curious", "thesis"…) that is not itself negated ("I am not a student" is fine).
  Negative intent caps purchase intent at 12% of its weight (3 / 25 points) and adds a negative factor ("Requirement rules out a purchase").
* **Mixed signals** ("Not looking for ERP, but need a CRM") are scored on the affirmed phrases only and carry an explanatory negative factor.
* Solution keywords are never negated (naming a product is neutral). A negated timeline cue ("no budget yet") only removes the timeline credit.

| Requirement | Intent score |
|---|---:|
| Looking for CRM software | 19 |
| Urgently need to buy a CRM platform, budget approved this month | 25 |
| Not looking for CRM software | 3 |
| We don't need a CRM | 3 |
| Not interested in buying software | 3 |
| No purchase requirement | 2 |
| Not planning to purchase a CRM | 3 |
| Not looking for ERP, but need a CRM urgently | 25 |

**Known limits:** rules are keyword based, English only, and do not resolve double negatives ("can't say we aren't interested") or sarcasm.
### Negative-intent classification safeguard
Because intent is 25% of the total, a founder at a perfect-fit company who states *no* purchase intent still sums to **76** (20 + 3 + 15 + 10 + 9 + 9 + 10), which is HOT by the thresholds. Telling a sales team that such a lead is HOT would be misleading, so:

* `classification = min(threshold band, negative_intent_max_classification)` when negative intent is detected; otherwise the band is used unchanged. It only ever lowers a class.
* The numeric score, every parameter score and the breakdown are untouched. Score and classification therefore stay separately explainable.
* Wherever the cap fires, the reason is stated the same way: the calculation line (`76 / 100 → HOT by score alone … classification capped at WARM`), a negative factor, the quality assessment, the UI note under the score dial, `config_snapshot.classification_safeguard` in the API, and the Gemini prompt (`engine_results.classification_safeguard`).
* Mixed signals ("Not looking for ERP, but need a CRM urgently") are not negative intent and are not capped. A lead already below the cap (e.g. COLD) is unchanged and no safeguard is reported.
* Configuration: JSON key `negative_intent_max_classification` = `HOT` (disabled) | `WARM` (default) | `COLD`. WARM was chosen because explicit "not interested" means *qualify before pursuing*, not *ignore*; choose COLD for a stricter policy.
* Tested at the boundary (`hot_threshold` exactly at, and just above, the score), for each cap setting, for every negative phrasing, end-to-end through the API, and against a Gemini response that tries to call the lead HOT.

## Contact validation: format checking is not verification
`email`, `phone` and `website` are checked **for format only**. The system does not contact a mail server, do a DNS/MX lookup, fetch the
website or place a call, so it never says anything is "verified". Validation reports mark those fields `check: "format_only"` with the
message "Format is valid. The mailbox was not verified." (and equivalents); the UI, the rule-based text and the Gemini prompt say the same, and a test
scans all generated text for unqualified "verified" claims. Gemini responses that claim verification are rejected.

**Reserved example domains.** `example.com`, `example.net`, `example.org` (and subdomains) and the TLDs `.test`, `.example`, `.invalid`,
`.localhost` (RFC 2606 / 6761) can never be real mailboxes or sites. They are *accepted* — otherwise the assignment's sample lead (`rahul@example.com`) would be unusable — but they are flagged as demonstration data: a validation warning, a confidence note, a 3-point reliability deduction, a "demonstration data" mention in the explanation and in the Gemini prompt. **They never earn the business-domain bonus point**, because a reserved name cannot be a real company mailbox; the contact explanation says so and a negative factor records it. No domain-mismatch contradiction is raised for them.
Look-alikes such as `examples.com` or `myexample.com` are **not** treated as reserved.

## Missing and invalid data
* Missing data never earns full marks (each rule awards 0 for a missing field).
* Invalid data (`12345` as a phone, `lots` as company size) earns 0 for that component and appears as a negative factor.
* A lead is rejected (HTTP 422) only when it has **neither** a valid name **nor** a valid company name.

## Exact calculation: Rahul Sharma (assignment sample lead)
Input: Rahul Sharma · ABC Technologies · www.abctechnologies.com · Founder · IT Services · Bangalore · 50–100 Employees · Website · "Looking for CRM software" · rahul@example.com · +91 9876543210

| Parameter | Weight | How it is computed | Score |
|---|---:|---|---:|
| Industry relevance | 20 | "IT Services" is tier-1 → 100% × 20 | **20** |
| Purchase intent | 25 | solution named (*crm*, *software*) 32% × 25 = 8; buying signal "looking for" (not negated) 36% × 25 = 9; timeline/budget none = 0; 4 words → detail 8% × 25 = 2 | **19** |
| Job title | 15 | "Founder" → Owner/C-level tier 100% × 15 | **15** |
| Company size | 10 | "50–100" → "50-100", midpoint 75 → 51–500 band 100% × 10 | **10** |
| Lead source | 10 | "Website" → inbound 90% × 10 | **9** |
| Contact information | 10 | email well-formed 4 + business-domain bonus **0** (`example.com` is a reserved example domain) + phone well-formed 4 + name 1 | **9** |
| Company completeness | 10 | name 3 + website 3 + location 2 + size 2 | **10** |

**Final Score = 20 + 19 + 15 + 10 + 9 + 9 + 10 = 92 / 100 → HOT** (≥ 75). Positive factors: relevant industry, specific solution requested, clear
buying signal, founder authority, ideal company size, high-quality source, well-formed contacts, complete company information. Negative factors: unclear purchase timeline or budget; reserved example email domain earned no business-domain credit. (Before this correction the sample was 93: the engine wrongly gave the bonus to `example.com`.)

Confidence (independent of the score): completeness 11/11 × 40 = 40; contact format validity 12 + 10 + 3 = 25; reliability 20 − 3 (reserved example domain) = 17;
consistency 15 (no contradictions) → **97 → HIGH**.
These numbers are asserted in `tests/test_contact_validation.py` and `tests/test_determinism_and_gemini_isolation.py`.

## Why these weights
Purchase intent (25) is the strongest signal that a lead will buy now. Industry fit (20) decides whether the product solves the lead's problem.
Authority (15) shows who can sign. Size, source, contact quality and completeness (10 each) support prioritisation but cannot alone make a lead hot.

## Confidence (separate from the score)
`services/confidence.py` never reads the score. It measures **trust in the data**, not conversion probability:

| Component | Max | Based on |
|---|---:|---|
| Data completeness | 40 | share of the 11 fields supplied |
| Contact format validity | 25 | well-formed email 12, phone 10, name 3 (nothing is verified) |
| Information reliability | 20 | −4 per invalid field (max −12), free-mail −2, disposable email −6, placeholder text −5, reserved example domain −3, instruction-like text in a field −5 |
| Consistency | 15 | −7 student title with an enterprise purchase claim; −7 high-intent source with no-intent wording; −4 email domain ≠ website (not applied to reserved domains) |

HIGH ≥ 75, MEDIUM ≥ 50, LOW < 50. A complete, well-formed but poor-fit lead can be *COLD with HIGH confidence*; a promising lead with sparse data can be *WARM with LOW confidence*.
