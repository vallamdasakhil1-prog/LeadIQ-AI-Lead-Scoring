"""Negation-aware purchase-intent detection."""
import pytest

from app.config import ScoringConfig
from app.services import narrative
from app.services.confidence import calculate_confidence
from app.services.intent import analyse_intent
from app.services.lead_validator import validate_and_normalize
from app.services.scoring_engine import score_lead
from tests.conftest import SAMPLE, submit_and_assess

CFG = ScoringConfig().validate()
INTENT_CAP = CFG.weights["purchase_intent"] * CFG.intent_negative_cap  # 3.0


def run(requirement, **overrides):
    lead = {**SAMPLE, "requirement": requirement, **overrides}
    n, _ = validate_and_normalize(lead)
    return n, score_lead(n, CFG)


def intent(result):
    return next(p for p in result.parameters if p.key == "purchase_intent")


NEGATIVE = [
    "Not looking for CRM software",
    "We are not looking for a CRM right now",
    "We don't need a CRM",
    "We do not need any software",
    "Not interested in buying software",
    "We are not interested in purchasing a CRM",
    "No purchase requirement",
    "No requirement at the moment",
    "Not planning to purchase a CRM",
    "We are not planning to buy any software this year",
    "Do not really need a CRM at the moment",
    "Never going to buy a CRM, just checking",
    "Not looking to buy anything",
    "Has no need for CRM software",
    "NOT LOOKING FOR CRM",                       # case-insensitive
    "We don’t need a CRM",                       # typographic apostrophe
]


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative_requirements_cannot_score_high(text):
    _, r = run(text)
    p = intent(r)
    assert p.score <= INTENT_CAP, (text, p.score, p.explanation)
    assert "negative_intent" in p.flags and r.negative_intent
    assert not any("Clear buying signal" in x for x in r.positives)
    assert any("rules out a purchase" in x or "no real purchase intent" in x for x in r.negatives)


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative_is_always_below_the_positive_equivalent(text):
    assert intent(run(text)[1]).score < intent(run("Looking for CRM software")[1]).score


# Hand-derived from the rules (weight 25): solution 8 + buying signal 9 + timeline 5 + detail
# (>=6 words 3, 3-5 words 2, 1-2 words 0.75).
POSITIVE = [
    ("Looking for CRM software", 19.0),                    # 8 + 9 + 0 + 2   (4 words)
    ("Need a CRM for our sales team", 20.0),               # 8 + 9 + 0 + 3   (7 words)
    ("We want to buy a CRM platform", 20.0),               # 8 + 9 + 0 + 3   (7 words)
    ("Urgently need to buy a CRM platform, budget approved this month", 25.0),  # 8 + 9 + 5 + 3
    ("Require ERP software; budget approved", 24.0),       # 8 + 9 + 5 + 2   (5 words)
]


@pytest.mark.parametrize("text,expected", POSITIVE)
def test_positive_requirements_keep_their_scores(text, expected):
    _, r = run(text)
    assert intent(r).score == expected
    assert not r.negative_intent and "negative_intent" not in intent(r).flags


def test_sample_lead_intent_unchanged_by_negation_logic():
    _, r = run(SAMPLE["requirement"])
    assert intent(r).score == 19.0 and r.final_score == 92.0


@pytest.mark.parametrize("text", [
    "Not looking for ERP, but need a CRM urgently",     # contrast word starts a new clause
    "Not looking for ERP; need a CRM",                  # punctuation starts a new clause
    "We are not only looking for CRM but also ERP",     # 'not only' is not a negation
    "I am not a student, need CRM software",            # negated student keyword
    "No budget yet, but we need a CRM",
])
def test_negation_is_scoped_to_its_clause(text):
    _, r = run(text)
    assert intent(r).score > INTENT_CAP, intent(r).explanation
    assert not r.negative_intent


def test_mixed_signals_are_reported_but_not_capped():
    _, r = run("Not looking for ERP, but need a CRM urgently")
    assert any("negated buying phrase" in x for x in r.negatives)


def test_negated_timeline_removes_only_the_timeline_credit():
    _, with_budget = run("Looking for CRM, budget approved")   # 5 words each, so equal detail points
    _, no_budget = run("Looking for CRM, no budget")
    assert not no_budget.negative_intent
    assert intent(no_budget).score == intent(with_budget).score - 5.0


def test_solution_keywords_are_never_negated():
    a = analyse_intent("We don't need a CRM", CFG)
    assert a.solution == ["crm"] and a.buying == [] and a.negated == ["don't need"]


def test_student_wording_still_caps_even_with_buying_words():
    _, r = run("Just looking for a college project on CRM")
    assert intent(r).score <= INTENT_CAP and r.negative_intent


def test_negative_intent_does_not_change_other_parameters():
    _, pos = run("Looking for CRM software")
    _, neg = run("Not looking for CRM software")
    for a, b in zip(pos.parameters, neg.parameters):
        if a.key != "purchase_intent":
            assert a.score == b.score


def test_strong_profile_with_negative_intent_gets_no_demo_recommendation():
    n, r = run("We are not interested in buying a CRM")
    conf = calculate_confidence(n, CFG)
    action = narrative.next_action(n, r, conf)
    assert r.classification in ("HOT", "WARM")          # the profile alone still scores well
    assert "demonstration" not in action.lower() and "no purchase intent" in action


def test_negative_intent_with_referral_source_is_a_confidence_contradiction():
    n, _ = validate_and_normalize({**SAMPLE, "requirement": "Not interested", "lead_source": "Referral"})
    assert any("conflicts" in c for c in calculate_confidence(n, CFG).contradictions)


def test_negative_requirement_end_to_end(client):
    _, a = submit_and_assess(client, {**SAMPLE, "requirement": "We don't need a CRM"})
    row = next(b for b in a["breakdown"] if b["parameter"] == "purchase_intent")
    assert row["score"] <= INTENT_CAP
    assert any("rules out a purchase" in x for x in a["negative_factors"])
