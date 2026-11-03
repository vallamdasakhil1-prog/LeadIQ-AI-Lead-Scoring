"""The 15 required scenarios (numbers in comments match the assignment list)."""
import pytest

from app.config import ScoringConfig
from app.services.assessment_service import assess_lead
from app.services.confidence import calculate_confidence
from app.services.gemini_service import GeminiAnalysis, GeminiError, GeminiService
from app.services.lead_validator import validate_and_normalize
from app.services.scoring_engine import classify, score_lead
from tests.conftest import SAMPLE, FakeGemini, submit_and_assess

CFG = ScoringConfig().validate()


def score(payload, cfg=CFG):
    n, _ = validate_and_normalize(payload)
    return score_lead(n, cfg)


def params(result):
    return {p.key: p for p in result.parameters}


# 1. Founder with a strong purchase requirement
def test_founder_strong_requirement_is_hot():
    r = score(SAMPLE)
    assert r.classification == "HOT" and r.final_score >= 75
    assert params(r)["job_title"].score == 15
    assert params(r)["purchase_intent"].score >= 18
    assert any("decision-making authority" in p for p in r.positives)


# 2. Manager with a relevant requirement
def test_manager_relevant_requirement_is_warm_or_better():
    p = dict(SAMPLE, job_title="Sales Manager", industry="Manufacturing", lead_source="LinkedIn")
    r = score(p)
    assert r.classification in ("WARM", "HOT")
    assert params(r)["job_title"].score == pytest.approx(10.05)
    assert params(r)["job_title"].score < params(score(SAMPLE))["job_title"].score


# 3. Student with no purchase requirement
def test_student_without_purchase_requirement_is_cold():
    p = dict(name="Rohit", job_title="Student", requirement="Just looking for a college project",
             lead_source="Cold Call", email="r@gmail.com")
    r = score(p)
    assert r.classification == "COLD"
    assert params(r)["job_title"].score <= 1.1
    assert params(r)["purchase_intent"].score <= 3
    assert any("no real purchase intent" in n for n in r.negatives)


# 4. Missing email
def test_missing_email_loses_points_and_flagged():
    full = score(SAMPLE)
    r = score(dict(SAMPLE, email=None))
    assert params(r)["contact_information"].score == 5.0  # phone 4 + name 1
    assert r.final_score < full.final_score
    assert "Missing email address" in r.negatives


# 5. Invalid phone number
def test_invalid_phone_handled():
    n, rep = validate_and_normalize(dict(SAMPLE, phone="12345"))
    assert "phone" in rep.invalid and rep.usable
    r = score_lead(n, CFG)
    assert "Invalid phone number" in r.negatives
    assert params(r)["contact_information"].score == 6.0  # email 4 + bonus 1 + name 1


# 6. Missing website
def test_missing_website():
    r = score(dict(SAMPLE, website=None))
    assert params(r)["company_completeness"].score == 7.0
    assert "Missing company website" in r.negatives


# 7. Missing company size
def test_missing_company_size_gets_zero():
    r = score(dict(SAMPLE, company_size=None))
    assert params(r)["company_size"].score == 0
    assert params(r)["company_completeness"].score == 8.0


# 8. Incomplete lead information
def test_incomplete_lead_not_rejected_and_no_full_marks():
    p = dict(name="Asha", requirement="Need CRM")
    n, rep = validate_and_normalize(p)
    assert rep.usable and len(rep.missing) == 9
    r = score_lead(n, CFG)
    assert 0 <= r.final_score < 50
    for res in r.parameters:
        assert res.score < res.max_score
    conf = calculate_confidence(n, CFG)
    assert conf.level == "LOW"


# 9. Identical lead submissions (API level)
def test_identical_submissions_same_score(client):
    _, a1 = submit_and_assess(client, SAMPLE)
    _, a2 = submit_and_assess(client, SAMPLE)
    assert a1["score"] == a2["score"] and a1["classification"] == a2["classification"]
    assert [b["score"] for b in a1["breakdown"]] == [b["score"] for b in a2["breakdown"]]


# 10. Invalid lead information
def test_unusable_lead_rejected_with_details(client):
    r = client.post("/api/leads", json={"email": "bad", "phone": "x"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["validation"]["usable"] is False and "email" in detail["validation"]["invalid"]
    r2 = client.post("/api/leads", json={"name": "Rahul", "email": "bad", "website": "no way"})
    assert r2.status_code == 201
    assert set(r2.json()["validation"]["invalid"]) == {"email", "website"}


# 11. Gemini API unavailable
@pytest.mark.parametrize("mode", ["error", "rate_limited"])
def test_gemini_unavailable_falls_back(client, gemini, mode):
    gemini.mode = mode
    _, a = submit_and_assess(client, SAMPLE)
    assert a["explanation_source"] == "rule_based" and a["gemini_error"]
    assert a["score"] == score(SAMPLE).final_score
    assert a["quality_assessment"] and a["recommended_next_action"] and a["scoring_explanation"]
    assert len(a["breakdown"]) == 7


def test_missing_api_key_falls_back(client):
    from app.main import app
    from app.services.gemini_service import get_gemini_service
    app.dependency_overrides[get_gemini_service] = lambda: GeminiService(api_key="")
    _, a = submit_and_assess(client, SAMPLE)
    assert a["explanation_source"] == "rule_based" and "missing_api_key" in a["gemini_error"]


# 12. Invalid Gemini response
@pytest.mark.parametrize("text", ["not json at all", '{"quality_assessment": "x"}', "[]"])
def test_invalid_gemini_response_falls_back(client, gemini, text):
    gemini.mode, gemini.text = "invalid", text
    _, a = submit_and_assess(client, SAMPLE)
    assert a["explanation_source"] == "rule_based" and "invalid_response" in a["gemini_error"]


# 13. Score boundary conditions
def test_score_bounds():
    worst = score({"name": "Zed"})
    best = score(dict(SAMPLE, requirement="Urgently need to buy a CRM platform, budget approved this month, "
                      "please send pricing and a demo", lead_source="Referral"))
    assert 0 <= worst.final_score <= best.final_score <= 100
    assert worst.final_score == pytest.approx(1.0)  # only the valid name earns points
    assert sum(p.max_score for p in best.parameters) == 100


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        ScoringConfig(weights={**CFG.weights, "purchase_intent": 30}).validate()


# 14. Classification boundary conditions
@pytest.mark.parametrize("value,expected", [
    (100, "HOT"), (75, "HOT"), (74.99, "WARM"), (50, "WARM"), (49.99, "COLD"), (0, "COLD")])
def test_classification_boundaries(value, expected):
    assert classify(value, CFG) == expected


def test_thresholds_configurable_without_engine_change():
    strict = ScoringConfig(hot_threshold=95, warm_threshold=80).validate()
    assert score(SAMPLE, strict).final_score == score(SAMPLE).final_score
    assert score(SAMPLE, strict).classification == "WARM"


# 15. Identical input consistency
def test_repeated_scoring_is_identical():
    results = [score(SAMPLE) for _ in range(25)]
    assert len({(r.final_score, r.classification, tuple(p.score for p in r.parameters))
                for r in results}) == 1


def test_normalisation_variants_score_identically():
    variant = dict(SAMPLE, name="  rahul   sharma ", website="HTTPS://WWW.ABCTECHNOLOGIES.COM/home",
                   phone="9876543210", email=" RAHUL@EXAMPLE.COM ", company_size="50 - 100")
    assert score(variant).final_score == score(SAMPLE).final_score


# ---- Gemini cannot modify the score --------------------------------------------------
def test_gemini_cannot_modify_score(client, gemini):
    gemini.mode = "lying"
    _, a = submit_and_assess(client, SAMPLE)
    assert a["score"] == score(SAMPLE).final_score
    assert a["explanation_source"] == "rule_based" and "contradicting" in a["gemini_error"]


def test_gemini_success_keeps_engine_score(client, gemini):
    lead_id, a = submit_and_assess(client, SAMPLE)
    assert a["explanation_source"] == "gemini" and a["gemini_model"] == "fake-model"
    assert a["score"] == score(SAMPLE).final_score and a["classification"] == "HOT"
    assert "AI" in a["quality_assessment"]
    assert client.get(f"/api/leads/{lead_id}/assessment").json()["score"] == a["score"]


def test_gemini_schema_has_no_score_fields():
    assert not {"score", "classification", "final_score"} & set(GeminiAnalysis.model_fields)


def test_confidence_independent_of_score():
    poor_but_complete = dict(SAMPLE, job_title="Student", industry="Agriculture",
                             requirement="Not interested", lead_source="Cold Call")
    n1, _ = validate_and_normalize(SAMPLE)
    n2, _ = validate_and_normalize(poor_but_complete)
    assert score(poor_but_complete).final_score < 50 < score(SAMPLE).final_score
    assert calculate_confidence(n2, CFG).level == "HIGH"  # complete & valid data despite a COLD score


# ---- API / persistence -----------------------------------------------------------------
def test_api_flow_and_analytics(client):
    assert client.get("/api/analytics/overview").json()["total_leads"] == 0
    submit_and_assess(client, SAMPLE)
    submit_and_assess(client, dict(name="Stu", job_title="Student", requirement="college project"))
    client.post("/api/leads", json={"name": "Unassessed Person"})
    ov = client.get("/api/analytics/overview").json()
    assert ov["total_leads"] == 3 and ov["assessed_leads"] == 2 and ov["unassessed_leads"] == 1
    assert ov["hot_leads"] == 1 and ov["cold_leads"] == 1
    assert ov["average_score"] == pytest.approx((score(SAMPLE).final_score + ov["category_statistics"][2]["average_score"]) / 2, abs=0.01)
    assert sum(b["count"] for b in ov["score_distribution"]) == 2
    hot = client.get("/api/leads", params={"classification": "HOT"}).json()
    assert hot["total"] == 1 and hot["items"][0]["company_name"] == "ABC Technologies"
    assert client.get("/api/leads", params={"search": "abc"}).json()["total"] == 1
    assert client.get("/api/leads", params={"classification": "UNASSESSED"}).json()["total"] == 1
    assert client.get("/api/leads", params={"classification": "bogus"}).status_code == 422


def test_reassessment_preserves_history_and_breakdown(client):
    lead_id, first = submit_and_assess(client, SAMPLE)
    client.post(f"/api/leads/{lead_id}/assess")
    hist = client.get(f"/api/leads/{lead_id}/history").json()
    assert len(hist) == 2
    assert len(client.get(f"/api/leads/{lead_id}/assessment").json()["breakdown"]) == 7


def test_not_found_and_health(client):
    assert client.get("/api/leads/999").status_code == 404
    assert client.post("/api/leads/999/assess").status_code == 404
    assert client.get("/api/leads/1/assessment").status_code == 404
    assert client.get("/api/health").json()["status"] == "ok"


def test_gemini_service_error_mapping():
    import httpx
    from google.genai import errors

    class Boom:
        def __init__(self, exc): self.exc = exc
        class models: pass

    def svc_with(exc):
        s = GeminiService(api_key="k", retries=0, client=object())
        s._generate_text = lambda prompt: (_ for _ in ()).throw(exc)
        return s

    payload = {"x": 1}
    for exc, kind in [(errors.APIError(429, {}), "rate_limited"),
                      (errors.APIError(504, {}), "timeout"),
                      (httpx.ReadTimeout("t"), "timeout"),
                      (httpx.ConnectError("c"), "network"),
                      (errors.APIError(500, {}), "api_error")]:
        with pytest.raises(GeminiError) as ei:
            svc_with(exc).analyze(payload, 90, "HOT")
        assert ei.value.kind == kind
