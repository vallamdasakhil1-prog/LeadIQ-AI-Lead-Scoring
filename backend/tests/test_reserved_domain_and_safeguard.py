"""Reserved-domain contact scoring and the negative-purchase-intent classification safeguard."""
import pytest

from app.config import ScoringConfig
from app.services import narrative
from app.services.confidence import calculate_confidence
from app.services.lead_validator import validate_and_normalize
from app.services.scoring_engine import apply_negative_intent_cap, score_lead
from tests.conftest import SAMPLE, FakeGemini, submit_and_assess

CFG = ScoringConfig().validate()
NEGATIVE_REQ = "We are not interested in buying a CRM"


def run(overrides=None, cfg=CFG, **kw):
    lead = {**SAMPLE, **(overrides or {}), **kw}
    n, _ = validate_and_normalize(lead)
    return n, score_lead(n, cfg)


def param(result, key):
    return next(p for p in result.parameters if p.key == key)


# ----------------------------------------------------------------------------- reserved domains
@pytest.mark.parametrize("email", [
    "a@example.com", "a@example.net", "a@example.org", "a@mail.example.com", "a@EXAMPLE.COM",
    "a@corp.test", "a@corp.example", "a@corp.invalid", "a@corp.localhost"])
def test_reserved_email_domains_get_no_business_bonus(email):
    n, r = run(email=email)
    assert n.email_is_reserved
    assert param(r, "contact_information").score == 9.0      # email 4 + phone 4 + name 1, no +1 bonus
    assert any("reserved example domain" in x for x in param(r, "contact_information").negatives)


@pytest.mark.parametrize("email", ["a@acme.com", "a@examples.com", "a@myexample.com", "a@example.co.in",
                                   "a@testing.com", "a@finedge.io"])
def test_real_and_lookalike_domains_still_get_the_bonus(email):
    n, r = run(email=email)
    assert not n.email_is_reserved
    assert param(r, "contact_information").score == 10.0


def test_free_mail_still_gets_no_bonus_and_reserved_is_not_double_penalised():
    assert param(run(email="a@gmail.com")[1], "contact_information").score == 9.0
    assert param(run(email="a@example.com")[1], "contact_information").score == 9.0


def test_reserved_website_does_not_change_the_email_bonus():
    n, r = run(email="a@acme.com", website="example.org")
    assert n.website_is_reserved and param(r, "contact_information").score == 10.0


def test_the_bonus_decision_is_visible_in_the_explanation_and_rule():
    _, r = run()
    p = param(r, "contact_information")
    assert "no business-domain bonus" in p.explanation
    assert "never earn the business-domain bonus" in p.rule_applied


def test_sample_lead_recalculated_by_the_engine():
    n, r = run()
    assert [p.score for p in r.parameters] == [20, 19, 15, 10, 9, 9, 10]
    assert r.final_score == 92.0 and r.classification == "HOT" and r.safeguard is None
    assert r.calculation.startswith("Final Score = 20 + 19 + 15 + 10 + 9 + 9 + 10 = 92 / 100 → HOT")


def test_sample_lead_keeps_its_demonstration_data_warning_and_confidence():
    n, rep = validate_and_normalize(SAMPLE)
    email = next(f for f in rep.to_dict()["fields"] if f["field"] == "email")
    assert "reserved example domain" in email["warning"]
    assert any("example.com" in w for w in rep.to_dict()["warnings"])
    conf = calculate_confidence(n, CFG)
    assert conf.score == 97.0 and conf.level == "HIGH"
    assert any("reserved example domain" in x for x in conf.notes)


def test_sample_lead_api_flow_is_consistent(client):
    r = client.post("/api/leads", json=SAMPLE).json()
    assert any("reserved example domain" in w for w in r["validation"]["warnings"])
    a = client.post(f"/api/leads/{r['lead']['id']}/assess").json()
    assert a["score"] == 92.0 and a["classification"] == "HOT" and a["confidence_score"] == 97.0
    assert "Final Score = 20 + 19 + 15 + 10 + 9 + 9 + 10 = 92" in a["scoring_explanation"]


# ----------------------------------------------------------------------------- safeguard
def test_negative_intent_total_is_hot_by_score_but_capped_to_warm():
    _, r = run(requirement=NEGATIVE_REQ)
    assert r.final_score == 76.0                              # 20 + 3 + 15 + 10 + 9 + 9 + 10
    assert r.threshold_classification == "HOT" and r.classification == "WARM"
    assert r.safeguard["rule"] == "negative_intent_cap"
    assert r.safeguard["score_band"] == "HOT" and r.safeguard["applied_classification"] == "WARM"


def test_safeguard_never_changes_the_numeric_score_or_any_parameter():
    _, capped = run(requirement=NEGATIVE_REQ)
    _, uncapped = run({"requirement": NEGATIVE_REQ},
                      cfg=ScoringConfig(negative_intent_max_classification="HOT").validate())
    assert capped.final_score == uncapped.final_score == 76.0
    assert [p.score for p in capped.parameters] == [p.score for p in uncapped.parameters]
    assert uncapped.classification == "HOT" and uncapped.safeguard is None


def test_safeguard_is_explained_consistently_everywhere():
    n, r = run(requirement=NEGATIVE_REQ)
    conf = calculate_confidence(n, CFG)
    assert "76 / 100 → HOT by score alone" in r.calculation and "capped at WARM" in r.calculation
    assert any(x.startswith("Classification capped at WARM") for x in r.negatives)
    assert "capped at WARM" in narrative.quality_assessment(n, r, conf)
    assert "capped at WARM" in narrative.natural_explanation(r)
    assert "capped at WARM" in narrative.scoring_explanation(r)
    assert "Do not push for a demo" in narrative.next_action(n, r, conf)
    assert "follows directly from the configured thresholds" not in narrative.natural_explanation(r)


def test_cap_boundaries_around_the_hot_threshold():
    # Score 76. hot=76 -> score is exactly on the boundary (HOT band) -> capped.
    at = ScoringConfig(hot_threshold=76.0).validate()
    _, r = run(requirement=NEGATIVE_REQ, cfg=at)
    assert r.threshold_classification == "HOT" and r.classification == "WARM" and r.safeguard
    # hot=76.01 -> already WARM by score -> the safeguard does not fire and does not claim to.
    above = ScoringConfig(hot_threshold=76.01).validate()
    _, r = run(requirement=NEGATIVE_REQ, cfg=above)
    assert r.classification == "WARM" and r.safeguard is None
    assert "capped" not in r.calculation


def test_cap_never_raises_a_class():
    for band in ("COLD", "WARM"):
        assert apply_negative_intent_cap(band, True, CFG) == band
    cold_cfg = ScoringConfig(negative_intent_max_classification="COLD").validate()
    assert apply_negative_intent_cap("HOT", True, cold_cfg) == "COLD"
    assert apply_negative_intent_cap("WARM", True, cold_cfg) == "COLD"
    assert apply_negative_intent_cap("COLD", True, cold_cfg) == "COLD"


@pytest.mark.parametrize("band", ["HOT", "WARM", "COLD"])
def test_no_negative_intent_means_no_cap(band):
    assert apply_negative_intent_cap(band, False, CFG) == band


def test_configurable_cap_to_cold_and_disabled():
    _, r = run(requirement=NEGATIVE_REQ, cfg=ScoringConfig(negative_intent_max_classification="COLD").validate())
    assert r.final_score == 76.0 and r.classification == "COLD" and "capped at COLD" in r.calculation
    _, r = run(requirement=NEGATIVE_REQ, cfg=ScoringConfig(negative_intent_max_classification="HOT").validate())
    assert r.classification == "HOT"


def test_invalid_cap_value_is_rejected():
    with pytest.raises(ValueError):
        ScoringConfig(negative_intent_max_classification="LUKEWARM").validate()


def test_already_cold_negative_lead_is_unchanged():
    _, r = run(requirement="Not interested", job_title="Student", industry="Handicrafts",
               company_size="1-10", lead_source="Purchased List")
    assert r.classification == "COLD" and r.safeguard is None and r.negative_intent


# --- regression: positive and mixed-signal leads are untouched ---------------------------------
@pytest.mark.parametrize("req", [
    "Looking for CRM software",
    "Not looking for ERP, but need a CRM urgently",
    "No budget yet, but we need a CRM",
    "I am not a student, need CRM software",
])
def test_positive_and_mixed_leads_stay_hot_without_safeguard(req):
    _, r = run(requirement=req)
    assert r.classification == "HOT" and r.safeguard is None


@pytest.mark.parametrize("req", ["Not looking for CRM software", "We don't need a CRM", "No purchase requirement",
                                 "Just looking for a college project on CRM"])
def test_all_negative_phrasings_get_the_safeguard_when_the_profile_is_strong(req):
    _, r = run(requirement=req)
    assert r.negative_intent and r.threshold_classification == "HOT" and r.classification == "WARM"


def test_negative_intent_end_to_end_api_is_consistent(client, gemini):
    gemini.mode = "error"          # rule-based text, so the engine's own wording is what we assert on
    _, a = submit_and_assess(client, {**SAMPLE, "requirement": NEGATIVE_REQ})
    assert a["score"] == 76.0 and a["classification"] == "WARM"
    assert a["config_snapshot"]["score_band"] == "HOT"
    assert a["config_snapshot"]["classification_safeguard"]["applied_classification"] == "WARM"
    assert "76 / 100 → HOT by score alone" in a["scoring_explanation"].splitlines()[-1]
    assert any(x.startswith("Classification capped at WARM") for x in a["negative_factors"])
    assert "capped at WARM" in a["quality_assessment"]
    assert "Do not push for a demo" in a["recommended_next_action"]
    ov = client.get("/api/analytics/overview").json()
    assert ov["warm_leads"] == 1 and ov["hot_leads"] == 0
    assert client.get("/api/leads", params={"classification": "WARM"}).json()["total"] == 1


def test_gemini_is_told_about_the_cap_and_cannot_undo_it(client, gemini):
    _, a = submit_and_assess(client, {**SAMPLE, "requirement": NEGATIVE_REQ})
    assert a["explanation_source"] == "gemini"
    eng = gemini.seen["engine_results"]
    assert eng["classification"] == "WARM" and eng["classification_safeguard"]["score_band"] == "HOT"
    assert a["score"] == 76.0 and a["classification"] == "WARM"


def test_gemini_calling_a_capped_lead_hot_is_rejected_and_falls_back(client, gemini):
    gemini.mode, gemini.text = "invalid", (
        '{"quality_assessment":"This is a HOT lead and should get a demo right away.",'
        '"scoring_explanation":"The lead earned 76 points in total.",'
        '"business_insights":["Call them"],"recommended_next_action":"Book a demo."}')
    _, a = submit_and_assess(client, {**SAMPLE, "requirement": NEGATIVE_REQ})
    assert a["explanation_source"] == "rule_based" and "invalid_response" in a["gemini_error"]
    assert a["classification"] == "WARM" and a["score"] == 76.0


# ----------------------------------------------------------------------------- input validation
@pytest.mark.parametrize("payload,status", [
    ({}, 422), ({"email": "bad"}, 422), ({"name": " ", "company_name": ""}, 422),
    ({"name": "A" * 2001}, 422), ({"name": True}, 422), ({"name": ["x"]}, 422),
    ({"name": "Asha"}, 201), ({"company_name": "Acme Ltd"}, 201), ({"name": 12345}, 422), ({"name": 12345, "company_name": "Acme"}, 201),
])
def test_lead_input_validation(client, payload, status):
    assert client.post("/api/leads", json=payload).status_code == status


def test_missing_and_invalid_fields_cost_points_but_never_crash(client, gemini):
    gemini.mode = "error"
    _, a = submit_and_assess(client, {"name": "Asha", "email": "bad@@", "phone": "1", "company_size": "lots"})
    assert 0 <= a["score"] <= 100 and a["classification"] == "COLD"
    assert a["explanation_source"] == "rule_based"
    assert {"Invalid email address", "Invalid phone number"} <= set(a["negative_factors"])
