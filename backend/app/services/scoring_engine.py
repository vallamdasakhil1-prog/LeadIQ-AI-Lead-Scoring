"""Deterministic, explainable lead scoring engine.

This module is intentionally free of any LLM / network / database imports.  Given
the same ``NormalizedLead`` and ``ScoringConfig`` it always returns the same
result.  Every parameter yields a ``ParameterResult`` containing its maximum
weight, evaluation criteria, the rule that fired, the actual score and an
explanation; the final score is the plain sum of those scores.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..config import PARAMETER_LABELS, PARAMETERS, ScoringConfig
from .lead_validator import NormalizedLead


@dataclass
class ParameterResult:
    key: str
    label: str
    max_score: float
    score: float
    criteria: str
    rule_applied: str
    explanation: str
    positives: list = field(default_factory=list)
    negatives: list = field(default_factory=list)

    @property
    def ratio(self) -> float:
        return self.score / self.max_score if self.max_score else 0.0


@dataclass
class ScoreResult:
    final_score: float
    classification: str
    parameters: list
    positives: list
    negatives: list
    calculation: str  # human readable "Final Score = a + b + ... = X"
    thresholds: dict


def _points(weight: float, ratio: float) -> float:
    return round(weight * max(0.0, min(1.0, ratio)), 2)


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _matches(text: str, phrases) -> list:
    return [p for p in phrases if _has(text, p)]


def _pct(x: float) -> str:
    return f"{round(x * 100):d}%"


def classify(score: float, cfg: ScoringConfig) -> str:
    if score >= cfg.hot_threshold:
        return "HOT"
    if score >= cfg.warm_threshold:
        return "WARM"
    return "COLD"


# --------------------------------------------------------------------------- rules
def _industry(n: NormalizedLead, cfg: ScoringConfig, w: float) -> ParameterResult:
    m = cfg.industry_multipliers
    criteria = "How closely the lead's industry matches the product's target segments."
    rule = (f"Tier-1 target industry = {_pct(m['tier1'])} of weight; tier-2 = {_pct(m['tier2'])}; "
            f"other industry = {_pct(m['other'])}; missing or invalid = 0.")
    pos, neg = [], []
    status = n.status.get("industry")
    if status == "missing":
        ratio, expl = 0.0, "No industry was provided, so no points were awarded."
        neg.append("Industry not provided")
    elif status == "invalid":
        ratio, expl = 0.0, "The industry value is invalid, so no points were awarded."
        neg.append("Industry value is invalid")
    else:
        text = n.industry.lower()
        if _matches(text, cfg.industry_tier1):
            ratio = m["tier1"]
            expl = f"'{n.industry}' is a tier-1 target industry."
            pos.append(f"Relevant industry ({n.industry})")
        elif _matches(text, cfg.industry_tier2):
            ratio = m["tier2"]
            expl = f"'{n.industry}' is a tier-2 industry with moderate fit."
            pos.append(f"Industry is a reasonable fit ({n.industry})")
        else:
            ratio = m["other"]
            expl = f"'{n.industry}' is outside the defined target industries."
            neg.append(f"Industry ({n.industry}) is outside the main target segments")
    return _build("industry_relevance", w, ratio, criteria, rule, expl, pos, neg)


def _intent(n: NormalizedLead, cfg: ScoringConfig, w: float) -> ParameterResult:
    c = cfg.intent_components
    criteria = ("Strength of the stated requirement: a named solution, an explicit buying "
                "signal, a timeline/budget and enough detail to act on.")
    rule = (f"Solution mentioned = {_pct(c['solution'])} of weight; buying signal = "
            f"{_pct(c['buying_signal'])}; timeline/budget = {_pct(c['timeline_or_budget'])}; "
            f"level of detail = up to {_pct(c['detail'])}. Negative-intent wording caps the "
            f"parameter at {_pct(cfg.intent_negative_cap)}. Missing or invalid = 0.")
    pos, neg = [], []
    status = n.status.get("requirement")
    if status == "missing":
        return _build("purchase_intent", w, 0.0, criteria, rule,
                      "No requirement was provided, so purchase intent cannot be established.",
                      pos, ["Requirement not provided (no evidence of purchase intent)"])
    if status == "invalid":
        return _build("purchase_intent", w, 0.0, criteria, rule,
                      "The requirement text is invalid, so no points were awarded.",
                      pos, ["Requirement text is invalid"])
    text = n.requirement.lower()
    solution = _matches(text, cfg.intent_solution_keywords)
    buying = _matches(text, cfg.intent_buying_keywords)
    timeline = _matches(text, cfg.intent_timeline_keywords)
    negative = _matches(text, cfg.intent_negative_keywords)
    words = len(re.findall(r"[A-Za-z0-9]+", n.requirement))
    detail_share = c["detail"] if words >= 6 else (c["detail"] * 2 / 3 if words >= 3
                                                   else c["detail"] / 4)
    parts = []
    ratio = 0.0
    if solution:
        ratio += c["solution"]
        parts.append(f"solution named ({', '.join(solution[:3])})")
        pos.append(f"Specific solution requested ({', '.join(solution[:3])})")
    else:
        neg.append("No specific product or solution mentioned in the requirement")
    if buying:
        ratio += c["buying_signal"]
        parts.append(f"buying signal ('{buying[0]}')")
        pos.append("Clear buying signal in the requirement")
    else:
        neg.append("No explicit buying signal in the requirement")
    if timeline:
        ratio += c["timeline_or_budget"]
        parts.append(f"timeline/budget cue ('{timeline[0]}')")
        pos.append("Timeline or budget indicated")
    else:
        neg.append("Unclear purchase timeline or budget")
    ratio += detail_share
    parts.append(f"{words} word(s) of detail")
    capped = False
    if negative:
        capped = True
        ratio = min(ratio, cfg.intent_negative_cap)
        neg.append(f"Requirement suggests no real purchase intent ('{negative[0]}')")
        pos = []
    expl = "Detected: " + "; ".join(parts) + "."
    if capped:
        expl += f" Capped at {_pct(cfg.intent_negative_cap)} because of negative-intent wording."
    return _build("purchase_intent", w, ratio, criteria, rule, expl, pos, neg)


def _title(n: NormalizedLead, cfg: ScoringConfig, w: float) -> ParameterResult:
    criteria = "Seniority of the contact as a proxy for budget and decision-making authority."
    tiers = "; ".join(f"{name} = {_pct(mult)}" for name, _, mult in cfg.title_rules)
    rule = (f"{tiers}; junior/assistant roles = {_pct(cfg.title_junior_multiplier)}; "
            f"student/intern = {_pct(cfg.title_student_multiplier)}; other titles = "
            f"{_pct(cfg.title_default_multiplier)}; missing or invalid = 0.")
    pos, neg = [], []
    status = n.status.get("job_title")
    if status == "missing":
        return _build("job_title", w, 0.0, criteria, rule,
                      "No job title was provided, so authority cannot be assessed.",
                      pos, ["Job title not provided (decision-making authority unknown)"])
    if status == "invalid":
        return _build("job_title", w, 0.0, criteria, rule,
                      "The job title is invalid, so no points were awarded.",
                      pos, ["Job title is invalid"])
    text = n.job_title.lower()
    matched = [(name, mult) for name, pattern, mult in cfg.title_rules
               if re.search(pattern, text)]
    if re.search(cfg.title_student_regex, text):
        ratio, tier = cfg.title_student_multiplier, "Student / intern"
        neg.append(f"'{n.job_title}' has no purchasing authority")
    else:
        if matched:
            tier, ratio = max(matched, key=lambda t: t[1])
        else:
            tier, ratio = "Other title", cfg.title_default_multiplier
        if re.search(cfg.title_junior_regex, text) and ratio > cfg.title_junior_multiplier:
            tier, ratio = "Junior / assistant", cfg.title_junior_multiplier
        if ratio >= 0.85:
            pos.append(f"{n.job_title} has decision-making authority")
        elif ratio >= 0.6:
            pos.append(f"{n.job_title} has meaningful influence on purchase decisions")
        else:
            neg.append(f"'{n.job_title}' is unlikely to be the final decision-maker")
    expl = f"'{n.job_title}' matched the '{tier}' tier ({_pct(ratio)} of weight)."
    return _build("job_title", w, ratio, criteria, rule, expl, pos, neg)


def _size(n: NormalizedLead, cfg: ScoringConfig, w: float) -> ParameterResult:
    criteria = "Whether the company is large enough to buy and small enough to close quickly."
    bands = "; ".join(
        f"{int(lo)}–{int(hi) - 1 if hi else '∞'} employees = {_pct(mult)}"
        for lo, hi, mult in cfg.size_bands)
    rule = f"Based on the midpoint of the stated range: {bands}; missing or invalid = 0."
    pos, neg = [], []
    status = n.status.get("company_size")
    if status == "missing":
        return _build("company_size", w, 0.0, criteria, rule,
                      "Company size was not provided.", pos, ["Company size not provided"])
    if status == "invalid":
        return _build("company_size", w, cfg.size_unparseable_multiplier, criteria, rule,
                      "Company size could not be interpreted.", pos, ["Company size is invalid"])
    value = n.company_size_value
    ratio = cfg.size_unparseable_multiplier
    for lo, hi, mult in cfg.size_bands:
        if value >= lo and (hi is None or value < hi):
            ratio = mult
            break
    expl = f"Stated size '{n.company_size}' (midpoint {value:g}) falls in a band worth {_pct(ratio)}."
    if ratio >= 0.9:
        pos.append(f"Company size ({n.company_size} employees) is in the ideal range")
    elif ratio >= 0.7:
        pos.append(f"Company size ({n.company_size} employees) is acceptable")
    else:
        neg.append(f"Company size ({n.company_size} employees) is a weak fit")
    return _build("company_size", w, ratio, criteria, rule, expl, pos, neg)


def _source(n: NormalizedLead, cfg: ScoringConfig, w: float) -> ParameterResult:
    criteria = "Typical conversion quality of the channel that produced the lead."
    rule = ("Referral/demo = 100% of weight; inbound website = 90%; partner = 80%; events, "
            "webinars, LinkedIn = 70%; campaigns = 60%; social = 50%; cold/purchased lists = 30%; "
            "other known source = 40%; missing or invalid = 0.")
    pos, neg = [], []
    status = n.status.get("lead_source")
    if status == "missing":
        return _build("lead_source", w, 0.0, criteria, rule, "Lead source was not provided.",
                      pos, ["Lead source not provided"])
    if status == "invalid":
        return _build("lead_source", w, 0.0, criteria, rule, "Lead source is invalid.",
                      pos, ["Lead source is invalid"])
    text = n.lead_source.lower()
    ratio, hit = cfg.source_default_multiplier, None
    for keyword, mult in cfg.source_rules:
        if _has(text, keyword):
            ratio, hit = mult, keyword
            break
    expl = (f"Source '{n.lead_source}' matched '{hit}' ({_pct(ratio)} of weight)." if hit
            else f"Source '{n.lead_source}' is not a recognised channel ({_pct(ratio)} of weight).")
    if ratio >= 0.8:
        pos.append(f"High-quality lead source ({n.lead_source})")
    elif ratio < 0.5:
        neg.append(f"Low-converting lead source ({n.lead_source})")
    return _build("lead_source", w, ratio, criteria, rule, expl, pos, neg)


def _contact(n: NormalizedLead, cfg: ScoringConfig, w: float) -> ParameterResult:
    c = cfg.contact_components
    criteria = "Whether the lead can actually be reached: valid email, valid phone and a named contact."
    rule = (f"Valid email = {_pct(c['email'])} of weight (disposable address = half); business "
            f"email domain = +{_pct(c['business_domain'])}; valid phone = {_pct(c['phone'])}; "
            f"valid name = {_pct(c['name'])}. Missing or invalid items earn 0.")
    pos, neg, parts, ratio = [], [], [], 0.0
    if n.is_valid("email"):
        if n.email_is_disposable:
            ratio += c["email"] / 2
            parts.append("disposable email (half credit)")
            neg.append("Email uses a disposable domain")
        else:
            ratio += c["email"]
            parts.append("valid email")
            pos.append("Valid email address provided")
            if n.email_is_free:
                parts.append("free-mail domain (no business bonus)")
                neg.append("Email uses a free-mail domain rather than a company domain")
            else:
                ratio += c["business_domain"]
                parts.append("business email domain")
    elif n.status.get("email") == "invalid":
        parts.append("invalid email")
        neg.append("Invalid email address")
    else:
        parts.append("no email")
        neg.append("Missing email address")
    if n.is_valid("phone"):
        ratio += c["phone"]
        parts.append("valid phone")
        pos.append("Valid phone number provided")
    elif n.status.get("phone") == "invalid":
        parts.append("invalid phone")
        neg.append("Invalid phone number")
    else:
        parts.append("no phone")
        neg.append("Missing phone number")
    if n.is_valid("name"):
        ratio += c["name"]
        parts.append("named contact")
    else:
        parts.append("no valid name")
        neg.append("No valid contact name")
    return _build("contact_information", w, ratio, criteria, rule,
                  "Found: " + ", ".join(parts) + ".", pos, neg)


def _completeness(n: NormalizedLead, cfg: ScoringConfig, w: float) -> ParameterResult:
    c = cfg.completeness_components
    criteria = "How much verifiable company information (name, website, location, size) is available."
    rule = (f"Company name = {_pct(c['company_name'])} of weight; website = {_pct(c['website'])}; "
            f"location = {_pct(c['location'])}; company size = {_pct(c['size'])}. "
            "Each earns credit only when present and valid.")
    checks = [("company_name", "company_name", "Company name"),
              ("website", "website", "Company website"),
              ("location", "company_location", "Company location"),
              ("size", "company_size", "Company size")]
    ratio, have, lack, pos, neg = 0.0, [], [], [], []
    for comp_key, field_name, label in checks:
        if n.is_valid(field_name):
            ratio += c[comp_key]
            have.append(label.lower())
        else:
            state = n.status.get(field_name)
            lack.append(label.lower())
            neg.append(f"{label} is invalid" if state == "invalid"
                       else f"Missing {label.lower()}")
    if not lack:
        pos.append("Company information is complete")
    expl = (f"Present: {', '.join(have) or 'none'}. "
            f"Absent or invalid: {', '.join(lack) or 'none'}.")
    return _build("company_completeness", w, ratio, criteria, rule, expl, pos, neg)


def _build(key, weight, ratio, criteria, rule, explanation, pos, neg) -> ParameterResult:
    return ParameterResult(
        key=key, label=PARAMETER_LABELS[key], max_score=float(weight),
        score=_points(weight, ratio), criteria=criteria, rule_applied=rule,
        explanation=explanation, positives=pos, negatives=neg,
    )


_RULES = {
    "industry_relevance": _industry,
    "purchase_intent": _intent,
    "job_title": _title,
    "company_size": _size,
    "lead_source": _source,
    "contact_information": _contact,
    "company_completeness": _completeness,
}


def score_lead(normalized: NormalizedLead, cfg: Optional[ScoringConfig] = None) -> ScoreResult:
    """Score a normalised lead.  Pure function: same input + config => same output."""
    if cfg is None:
        from ..config import get_scoring_config
        cfg = get_scoring_config()
    params = [_RULES[key](normalized, cfg, cfg.weights[key]) for key in PARAMETERS]
    total = round(sum(p.score for p in params), 2)
    final = max(0.0, min(100.0, total))
    classification = classify(final, cfg)
    calc = ("Final Score = " + " + ".join(f"{p.score:g}" for p in params)
            + f" = {final:g} / 100 → {classification} "
            f"(HOT ≥ {cfg.hot_threshold:g}, WARM ≥ {cfg.warm_threshold:g}, COLD below)")
    positives = [x for p in params for x in p.positives]
    negatives = [x for p in params for x in p.negatives]
    return ScoreResult(
        final_score=final, classification=classification, parameters=params,
        positives=positives, negatives=negatives, calculation=calc,
        thresholds={"hot": cfg.hot_threshold, "warm": cfg.warm_threshold},
    )
