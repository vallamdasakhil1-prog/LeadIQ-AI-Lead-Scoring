# Testing

```bash
cd backend && source .venv/bin/activate && pytest -v        # 260 tests, ~7 s
```
Tests use an in-memory SQLite database and fake Gemini clients; **no network access or API key is required** (they also pass with a dummy `GEMINI_API_KEY` set).
`pytest` counts each parametrised case, so 260 tests come from the files below.

| File | Tests | Covers |
|---|---:|---|
| `test_scoring_and_api.py` | 35 | The 15 assignment scenarios, API flow, analytics, history, Gemini error mapping |
| `test_negative_intent.py` | 51 | Negation-aware purchase intent |
| `test_prompt_injection.py` | 73 | Untrusted lead data, prompt construction, Gemini response validation |
| `test_contact_validation.py` | 55 | Format-only checks, reserved domains, missing/invalid contacts |
| `test_determinism_and_gemini_isolation.py` | 46 | Identical inputs ⇒ identical scores; Gemini cannot influence numbers |

## The 15 assignment scenarios (`test_scoring_and_api.py`)
| # | Scenario | Test(s) |
|---|---|---|
| 1 | Founder with strong requirement | `test_founder_strong_requirement_is_hot` |
| 2 | Manager with relevant requirement | `test_manager_relevant_requirement_is_warm_or_better` |
| 3 | Student, no purchase requirement | `test_student_without_purchase_requirement_is_cold` |
| 4 | Missing email | `test_missing_email_loses_points_and_flagged` |
| 5 | Invalid phone | `test_invalid_phone_handled` |
| 6 | Missing website | `test_missing_website` |
| 7 | Missing company size | `test_missing_company_size_gets_zero` |
| 8 | Incomplete lead | `test_incomplete_lead_not_rejected_and_no_full_marks` |
| 9 | Identical submissions | `test_identical_submissions_same_score` |
| 10 | Invalid lead information | `test_unusable_lead_rejected_with_details` |
| 11 | Gemini unavailable | `test_gemini_unavailable_falls_back`, `test_missing_api_key_falls_back`, `test_gemini_service_error_mapping` |
| 12 | Invalid Gemini response | `test_invalid_gemini_response_falls_back` |
| 13 | Score boundaries | `test_score_bounds`, `test_invalid_config_rejected` |
| 14 | Classification boundaries | `test_classification_boundaries`, `test_thresholds_configurable_without_engine_change` |
| 15 | Identical input consistency | `test_repeated_scoring_is_identical`, `test_normalisation_variants_score_identically` |

## Negative buying intent (`test_negative_intent.py`)
16 negative phrasings ("not looking for", "don't need", "not interested in buying", "no purchase requirement", "not planning to purchase", typographic
apostrophes, upper case…) must score ≤ 3/25 and carry a "rules out a purchase" factor; each must score below its positive equivalent. Positive requirements keep
hand-derived scores (19, 20, 24, 25). Negation scope: clause boundaries, "not only", "I am not a student", mixed signals, negated timeline only removes the timeline credit,
solution keywords never negated, other parameters unaffected, next action avoids recommending a demo, confidence contradiction with a referral source.

## Prompt injection (`test_prompt_injection.py`)
14 attack strings are detected (override/ignore-previous, reveal prompt/key, role change, score and classification manipulation, forged tags, forged JSON, code fences) while 7 ordinary
requirements are not flagged. Injected text in 7 different fields never appears in the payload sent to Gemini (including engine explanations that quote it). The prompt keeps the system instruction separate,
wraps the data in a single escaped block, and marks contacts "format checked only". Responses are rejected for: invalid JSON, wrong types, extra keys such as `score`, over-length items, a different stated score or label,
"recalculated/override", links/HTML, and verification claims — and each rejection falls back to rule-based text with the engine's score intact.

## Contact validation (`test_contact_validation.py`)
Format-only labelling; no generated text claims anything was verified; reserved domains (`example.com/net/org`, subdomains, `.test`, `.example`, `.invalid`, `.localhost`) are accepted and flagged while look-alikes
(`examples.com`, `myexample.com`) are not; the sample lead still scores exactly 20 + 19 + 15 + 10 + 9 + 10 + 10 = 93 with confidence HIGH; 10 malformed emails, 9 malformed phones, 6 malformed websites; missing/invalid contacts cost points and confidence.

## Determinism and Gemini isolation (`test_determinism_and_gemini_isolation.py`)
50 repeated runs per lead are identical; field order/whitespace/case/formatting variants score identically; results are identical across **separate processes with different `PYTHONHASHSEED`**;
identical submissions give identical assessments. The scoring modules import nothing from Gemini or HTTP libraries; for 5 leads × 6 Gemini behaviours (ok, error, rate-limited, invalid, lying, tampering with its payload) the score, classification, breakdown and factors are identical; the score is identical with and without Gemini.

## Test quality check
The suite was mutation-checked: disabling negation, the Gemini output cross-checks, the payload scrubbing, or reserved-domain handling each makes 3–36 tests fail.

**Not covered by automated tests:** a live call to the real Gemini API (needs a key and network) and browser/UI interaction tests. The frontend is verified by `npm run lint` and `npm run build`; the HTTP flow was exercised end to end against the running servers.
