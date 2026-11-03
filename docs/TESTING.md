# Testing

```bash
cd backend && source .venv/bin/activate && pytest -v
```
Tests use an in-memory SQLite database and a fake Gemini client; **no network or API key is required**.

| # | Required scenario | Test(s) in `tests/test_scoring_and_api.py` |
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

Extra guarantees: `test_gemini_cannot_modify_score` (a response claiming 12/100 is rejected), `test_gemini_success_keeps_engine_score`,
`test_gemini_schema_has_no_score_fields`, `test_confidence_independent_of_score`, API/analytics/history/404 tests.

**Not covered by automated tests:** a live call to the real Gemini API (needs a key) and browser/UI tests; the frontend is verified
by `npm run build` and `npm run lint`.
