"""Rule-based (Gemini-free) narrative: quality assessment, explanation, insights, next action."""
from __future__ import annotations

from .confidence import ConfidenceResult
from .lead_validator import NormalizedLead
from .scoring_engine import ScoreResult


def _who(n: NormalizedLead) -> str:
    if n.name and n.company_name:
        return f"{n.name} ({n.company_name})"
    return n.name or n.company_name or "This lead"


def scoring_explanation(result: ScoreResult) -> str:
    lines = ["How the score was calculated (deterministic rules; no AI involved):"]
    for p in result.parameters:
        lines.append(f"• {p.label}: {p.score:g} / {p.max_score:g} — {p.explanation}")
    lines.append(result.calculation)
    return "\n".join(lines)


def quality_assessment(n: NormalizedLead, result: ScoreResult, conf: ConfidenceResult) -> str:
    potential = {"HOT": "high", "WARM": "moderate", "COLD": "low"}[result.classification]
    text = (f"{_who(n)} is a {result.classification} lead with a score of "
            f"{result.final_score:g}/100, indicating {potential} business potential.")
    if result.positives:
        text += f" Strengths: {'; '.join(result.positives[:3]).rstrip('.')}."
    if result.negatives:
        text += f" Weaknesses: {'; '.join(result.negatives[:3]).rstrip('.')}."
    text += (f" Data confidence is {conf.level} — this reflects how complete and reliable the "
             "submitted information is, not the likelihood of conversion.")
    return text


def natural_explanation(result: ScoreResult) -> str:
    ranked = sorted(result.parameters, key=lambda p: p.ratio, reverse=True)
    best, worst = ranked[0], ranked[-1]
    return (f"The lead earned {result.final_score:g} out of 100 points. The strongest area was "
            f"{best.label} ({best.score:g}/{best.max_score:g}) and the weakest was "
            f"{worst.label} ({worst.score:g}/{worst.max_score:g}). The classification "
            f"{result.classification} follows directly from the configured thresholds.")


def business_insights(n: NormalizedLead, result: ScoreResult, conf: ConfidenceResult) -> list:
    insights = []
    for p in sorted(result.parameters, key=lambda p: p.ratio, reverse=True)[:2]:
        insights.append(f"{p.label} is a strength ({p.score:g}/{p.max_score:g}).")
    for p in sorted(result.parameters, key=lambda p: p.ratio)[:2]:
        if p.ratio < 0.7:
            insights.append(f"Improving {p.label.lower()} would raise the score "
                            f"({p.score:g}/{p.max_score:g} today).")
    if conf.level != "HIGH":
        insights.append("Confirm the missing or invalid details before investing heavy sales effort.")
    return insights


def next_action(n: NormalizedLead, result: ScoreResult, conf: ConfidenceResult) -> str:
    who = n.name or "the prospect"
    contact_ok = n.is_valid("email") or n.is_valid("phone")
    authority = next((p for p in result.parameters if p.key == "job_title"), None)
    is_decision_maker = bool(authority and authority.ratio >= 0.85)
    if not contact_ok:
        return ("Request valid contact details (email or phone) before any outreach; the lead "
                "cannot currently be reached.")
    if result.classification == "HOT":
        if not is_decision_maker:
            return (f"Contact the decision-maker at {n.company_name or 'the company'} via {who} "
                    "and schedule a product demonstration this week.")
        return f"Schedule a product demonstration with {who} within 48 hours and prepare a tailored proposal."
    if result.classification == "WARM":
        if conf.level == "LOW" or any(
                n.status.get(f) != "valid" for f in ("company_name", "website", "company_size")):
            return (f"Follow up with {who} and request the missing company information, "
                    "then re-assess the lead.")
        if not is_decision_maker:
            return f"Follow up with {who} to identify and engage the decision-maker, then send a product overview."
        return f"Send {who} a product proposal and follow up within a few days."
    return (f"Add {who} to a low-touch nurture sequence (newsletter or periodic follow-up) "
            "and re-assess if new information arrives.")
