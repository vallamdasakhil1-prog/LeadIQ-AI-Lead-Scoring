"""Orchestrates lead creation and assessment.

Order of operations (the engine is always the source of truth):
  normalise -> deterministic score -> confidence -> rule-based narrative ->
  optional Gemini narrative -> persist.
The score and classification are taken from the scoring engine only; the Gemini
response object has no way to influence them.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..config import ScoringConfig, get_scoring_config
from ..models import Assessment, AssessmentHistory, Lead, ScoreBreakdown
from . import narrative
from .confidence import calculate_confidence
from .gemini_service import GeminiError, GeminiService
from .lead_validator import (FIELD_ORDER, NormalizedLead, ValidationReport, clean_text,
                             validate_and_normalize)
from .prompt_safety import scrub
from .scoring_engine import score_lead

log = logging.getLogger("leadiq.assessment")


class UnusableLeadError(Exception):
    def __init__(self, report: ValidationReport):
        super().__init__("Lead is not usable")
        self.report = report


def lead_raw(lead: Lead) -> dict:
    return {f: getattr(lead, f) for f in FIELD_ORDER}


def create_lead(db: Session, payload: dict) -> tuple:
    normalized, report = validate_and_normalize(payload)
    if not report.usable:
        raise UnusableLeadError(report)
    lead = Lead(**{f: clean_text(payload.get(f)) for f in FIELD_ORDER},
                normalized_data=normalized.to_dict(), validation_report=report.to_dict())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead, report


def _gemini_payload(n: NormalizedLead, result, conf) -> tuple:
    """Build the (sanitised) document sent to Gemini.  Returns (payload, redaction_flags).

    Lead-supplied values live under ``untrusted_lead_data``.  Engine strings may quote lead text
    (e.g. an industry name), so the whole payload is scrubbed, not just the lead block.
    """
    payload = {
        "untrusted_lead_data": {k: v for k, v in n.to_dict().items() if k != "company_size_value"},
        "engine_results": {
            "score": result.final_score,
            "classification": result.classification,
            "classification_safeguard": result.safeguard,
            "score_breakdown": [
                {"parameter": p.label, "score": p.score, "max_score": p.max_score,
                 "explanation": p.explanation} for p in result.parameters],
            "positive_factors": result.positives,
            "negative_factors": result.negatives,
            "confidence": {"level": conf.level, "score": conf.score, "notes": conf.notes,
                           "meaning": "confidence in data quality, NOT probability of conversion"},
        },
        "contact_checks": {
            "email": "format checked only; mailbox NOT verified",
            "phone": "format checked only; number NOT verified",
            "website": "format checked only; site NOT fetched or verified",
            "reserved_example_domain_used": bool(n.email_is_reserved or n.website_is_reserved),
        },
    }
    return scrub(payload)


def assess_lead(db: Session, lead: Lead, gemini: Optional[GeminiService] = None,
                config: Optional[ScoringConfig] = None) -> Assessment:
    config = config or get_scoring_config()
    normalized, _ = validate_and_normalize(lead_raw(lead))
    result = score_lead(normalized, config)
    conf = calculate_confidence(normalized, config)

    quality = narrative.quality_assessment(normalized, result, conf)
    ai_text = narrative.natural_explanation(result)
    insights = narrative.business_insights(normalized, result, conf)
    action = narrative.next_action(normalized, result, conf)
    source, model_name, error = "rule_based", None, None

    if gemini is not None:
        try:
            payload, _ = _gemini_payload(normalized, result, conf)
            analysis = gemini.analyze(payload, result.final_score, result.classification)
            quality, ai_text = analysis.quality_assessment, analysis.scoring_explanation
            insights, action = analysis.business_insights, analysis.recommended_next_action
            source, model_name = "gemini", gemini.model
        except GeminiError as exc:
            error = f"{exc.kind}: {exc}"
            log.warning("Gemini unavailable, using rule-based fallback (%s)", error)
        except Exception as exc:  # never let the AI layer break scoring
            error = f"unexpected: {type(exc).__name__}"
            log.exception("Unexpected Gemini failure")

    assessment = Assessment(
        lead_id=lead.id,
        score=result.final_score,
        classification=result.classification,
        confidence_level=conf.level,
        confidence_score=conf.score,
        confidence_details={"components": conf.components, "notes": conf.notes,
                            "contradictions": conf.contradictions,
                            "prompt_injection_flags": conf.injection_flags,
                            "disclaimer": ("Confidence reflects data quality, not conversion "
                                           "probability. Email, phone and website were format-checked "
                                           "only; none were verified.")},
        positive_factors=result.positives,
        negative_factors=result.negatives,
        scoring_explanation=narrative.scoring_explanation(result),
        quality_assessment=quality,
        ai_explanation=ai_text,
        business_insights=insights,
        recommended_next_action=action,
        explanation_source=source,
        gemini_model=model_name,
        gemini_error=error,
        config_snapshot={"weights": config.weights, "hot_threshold": config.hot_threshold,
                         "warm_threshold": config.warm_threshold,
                         "negative_intent_max_classification": config.negative_intent_max_classification,
                         "score_band": result.threshold_classification,
                         "classification_safeguard": result.safeguard},
    )
    assessment.breakdown = [
        ScoreBreakdown(parameter=p.key, label=p.label, max_score=p.max_score, score=p.score,
                       criteria=p.criteria, rule_applied=p.rule_applied, explanation=p.explanation)
        for p in result.parameters]
    db.add(assessment)
    db.flush()
    db.add(AssessmentHistory(lead_id=lead.id, assessment_id=assessment.id, score=assessment.score,
                             classification=assessment.classification,
                             confidence_level=assessment.confidence_level,
                             explanation_source=source))
    lead.normalized_data = normalized.to_dict()
    db.commit()
    db.refresh(assessment)
    return assessment
