"""Format validation is not verification; reserved example domains; missing / invalid contacts."""
import re

import pytest

from app.config import ScoringConfig
from app.services.confidence import calculate_confidence
from app.services.lead_validator import is_reserved_domain, validate_and_normalize
from app.services.scoring_engine import score_lead
from tests.conftest import SAMPLE, submit_and_assess

CFG = ScoringConfig().validate()


def field(report, name):
    return next(f for f in report.fields if f["field"] == name)


def contact_score(lead):
    n, _ = validate_and_normalize(lead)
    return next(p for p in score_lead(n, CFG).parameters if p.key == "contact_information").score


# --- format validation is never presented as verification ---------------------------------
def test_valid_contact_fields_are_labelled_format_only():
    _, rep = validate_and_normalize({**SAMPLE, "email": "rahul@acme.in", "website": "acme.in"})
    for name in ("email", "phone", "website"):
        f = field(rep, name)
        assert f["status"] == "valid" and f["check"] == "format_only"
        assert "not verified" in f["message"].lower() or "not checked" in f["message"].lower()
    assert field(rep, "name")["check"] is None


def unqualified_verified_claims(text):
    """Sentences that say 'verified' without negating it."""
    return [s for s in re.split(r"(?<=[.!?])\s+", text)
            if re.search(r"\bverif", s, re.I) and not re.search(r"\b(not|none|never|no)\b", s, re.I)]


def test_no_output_claims_anything_was_verified(client):
    _, a = submit_and_assess(client, SAMPLE)
    texts = [a["quality_assessment"], a["ai_explanation"], a["scoring_explanation"],
             a["confidence_details"]["disclaimer"], *a["positive_factors"], *a["negative_factors"],
             *a["confidence_details"]["notes"], *[b["explanation"] + " " + b["criteria"] + " " + b["rule_applied"]
                                                  for b in a["breakdown"]]]
    # rule-based text only (the default fake Gemini text has no claims either)
    for t in texts:
        assert unqualified_verified_claims(t) == [], t
    assert any("not verified" in t for t in a["positive_factors"])


def test_api_exposes_format_only_checks_and_warnings(client):
    r = client.post("/api/leads", json=SAMPLE).json()
    email = next(f for f in r["validation"]["fields"] if f["field"] == "email")
    assert email["check"] == "format_only" and "reserved example domain" in email["warning"]
    assert any("example.com" in w for w in r["validation"]["warnings"])


# --- reserved example domains -------------------------------------------------------------
@pytest.mark.parametrize("domain", ["example.com", "example.org", "EXAMPLE.NET", "mail.example.com",
                                    "foo.test", "bar.example", "x.invalid", "my.localhost"])
def test_reserved_domains_detected(domain):
    assert is_reserved_domain(domain)


@pytest.mark.parametrize("domain", ["examples.com", "myexample.com", "example.co.in", "acme.com",
                                    "example-corp.com", "testing.com", "contest.io"])
def test_lookalike_domains_are_not_reserved(domain):
    assert not is_reserved_domain(domain)


def test_reserved_email_is_accepted_but_flagged_and_does_not_break_the_sample():
    n, rep = validate_and_normalize(SAMPLE)
    assert rep.usable and n.is_valid("email") and n.email_is_reserved
    assert field(rep, "email")["warning"]
    r = score_lead(n, CFG)
    assert [p.score for p in r.parameters] == [20, 19, 15, 10, 9, 10, 10]
    assert r.final_score == 93.0 and r.classification == "HOT"
    conf = calculate_confidence(n, CFG)
    assert conf.level == "HIGH" and any("reserved example domain" in x for x in conf.notes)
    assert not conf.contradictions     # example.com vs the company site is expected demo data


def test_reserved_website_is_flagged():
    _, rep = validate_and_normalize({**SAMPLE, "website": "https://www.example.com/home"})
    f = field(rep, "website")
    assert f["status"] == "valid" and f["normalized"] == "example.com" and f["warning"]


def test_real_domain_has_no_reserved_warning_but_still_isnt_verified():
    _, rep = validate_and_normalize({**SAMPLE, "email": "rahul@abctechnologies.com"})
    f = field(rep, "email")
    assert f["warning"] is None and "not verified" in f["message"].lower()


# --- missing and invalid contact details --------------------------------------------------
def test_missing_contacts_are_reported_and_cost_points():
    n, rep = validate_and_normalize({**SAMPLE, "email": None, "phone": ""})
    assert {"email", "phone"} <= set(rep.missing) and rep.usable
    assert field(rep, "email")["status"] == "missing"
    assert contact_score({**SAMPLE, "email": None, "phone": None}) == 1.0     # only the name
    r = score_lead(n, CFG)
    assert "Missing email address" in r.negatives and "Missing phone number" in r.negatives
    assert calculate_confidence(n, CFG).components["contact_validity"]["score"] == 3


@pytest.mark.parametrize("email", ["rahul@@x.com", "rahul@example", "rahul example.com", "a..b@x.com",
                                   "@x.com", "rahul@", "rahul@x", "rahul@.com", "r" * 70 + "@x.com", "rahul@x..com"])
def test_malformed_emails_are_invalid(email):
    n, rep = validate_and_normalize({**SAMPLE, "email": email})
    assert field(rep, "email")["status"] == "invalid" and "email" in rep.invalid and n.email is None
    assert contact_score({**SAMPLE, "email": email}) == 5.0          # phone 4 + name 1
    assert "Invalid email address" in score_lead(n, CFG).negatives


@pytest.mark.parametrize("phone", ["12345", "abcdefghij", "0000000000", "+91 1234567890", "+1", "98765 4321",
                                   "+0 9876543210", "1111111111", "+91 98765 4321 99"])
def test_malformed_phones_are_invalid(phone):
    n, rep = validate_and_normalize({**SAMPLE, "phone": phone})
    assert field(rep, "phone")["status"] == "invalid" and n.phone is None
    assert contact_score({**SAMPLE, "phone": phone}) == 6.0          # email 4 + business domain 1 + name 1


@pytest.mark.parametrize("raw,normalized", [("+91 9876543210", "+919876543210"), ("9876543210", "+919876543210"),
                                            ("09876543210", "+919876543210"), ("+1 415 555 2671", "+14155552671"),
                                            ("(+44) 20 7946 0958", "+442079460958")])
def test_phone_normalisation(raw, normalized):
    n, _ = validate_and_normalize({**SAMPLE, "phone": raw})
    assert n.phone == normalized


@pytest.mark.parametrize("website", ["not a website", "http://", "abc", "ab_c.com", "-bad.com", "a.b"])
def test_malformed_websites_are_invalid(website):
    n, rep = validate_and_normalize({**SAMPLE, "website": website})
    assert field(rep, "website")["status"] == "invalid" and n.website is None


def test_free_and_disposable_emails_get_less_credit_and_confidence():
    assert contact_score({**SAMPLE, "email": "rahul@gmail.com"}) == 9.0
    assert contact_score({**SAMPLE, "email": "rahul@mailinator.com"}) == 7.0
    n, _ = validate_and_normalize({**SAMPLE, "email": "rahul@mailinator.com"})
    assert any("disposable" in x for x in calculate_confidence(n, CFG).notes)


def test_all_contacts_bad_still_scores_and_confidence_drops():
    bad = {**SAMPLE, "email": "nope", "phone": "123", "website": "x y"}
    n, rep = validate_and_normalize(bad)
    assert rep.usable and set(rep.invalid) == {"email", "phone", "website"}
    good_conf, bad_conf = (calculate_confidence(validate_and_normalize(l)[0], CFG) for l in (SAMPLE, bad))
    assert bad_conf.score < good_conf.score and bad_conf.level in ("MEDIUM", "LOW", "HIGH")
    assert score_lead(n, CFG).final_score < 93


def test_api_accepts_unverifiable_contacts_but_lists_them(client):
    r = client.post("/api/leads", json={"name": "Asha", "email": "bad@@", "phone": "1", "website": "no way"})
    assert r.status_code == 201
    v = r.json()["validation"]
    assert set(v["invalid"]) == {"email", "phone", "website"}
    assert all(any(m.startswith(lbl) for m in v["messages"]) for lbl in ("Email", "Phone", "Website"))
    lead_id = r.json()["lead"]["id"]
    a = client.post(f"/api/leads/{lead_id}/assess").json()
    assert {"Invalid email address", "Invalid phone number"} <= set(a["negative_factors"])
