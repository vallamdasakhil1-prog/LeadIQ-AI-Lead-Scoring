from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class LeadCreate(BaseModel):
    """All 11 input fields; every one is optional so incomplete leads are accepted."""

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    company_name: Optional[str] = None
    website: Optional[str] = None
    job_title: Optional[str] = None
    industry: Optional[str] = None
    company_location: Optional[str] = None
    company_size: Optional[str] = None
    lead_source: Optional[str] = None
    requirement: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def _coerce(cls, v: Any):
        if v is None or isinstance(v, str):
            return v
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
        raise ValueError("must be a string")

    @field_validator("*")
    @classmethod
    def _limit(cls, v):
        if v is not None and len(v) > 2000:
            raise ValueError("value too long (max 2000 characters)")
        return v


class FieldReportOut(BaseModel):
    field: str
    label: str
    status: str
    message: str
    raw: Optional[str] = None
    normalized: Optional[str] = None
    check: Optional[str] = None
    warning: Optional[str] = None


class ValidationReportOut(BaseModel):
    usable: bool
    fields: list[FieldReportOut]
    missing: list[str]
    invalid: list[str]
    messages: list[str]
    warnings: list[str] = []


class ScoreBreakdownOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    parameter: str
    label: str
    max_score: float
    score: float
    criteria: str
    rule_applied: str
    explanation: str


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lead_id: int
    score: float
    classification: str
    confidence_level: str
    confidence_score: float
    confidence_details: dict
    positive_factors: list[str]
    negative_factors: list[str]
    scoring_explanation: str
    quality_assessment: str
    ai_explanation: str
    business_insights: list[str]
    recommended_next_action: str
    explanation_source: str
    gemini_model: Optional[str] = None
    gemini_error: Optional[str] = None
    config_snapshot: dict
    assessed_at: datetime
    breakdown: list[ScoreBreakdownOut]


class AssessmentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    score: float
    classification: str
    confidence_level: str
    assessed_at: datetime


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: Optional[str] = None
    company_name: Optional[str] = None
    website: Optional[str] = None
    job_title: Optional[str] = None
    industry: Optional[str] = None
    company_location: Optional[str] = None
    company_size: Optional[str] = None
    lead_source: Optional[str] = None
    requirement: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    validation_report: Optional[dict] = None
    created_at: datetime
    latest_assessment: Optional[AssessmentSummary] = None


class LeadCreated(BaseModel):
    lead: LeadOut
    validation: ValidationReportOut


class LeadListResponse(BaseModel):
    items: list[LeadOut]
    total: int
    limit: int
    offset: int


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assessment_id: int
    score: float
    classification: str
    confidence_level: str
    explanation_source: str
    created_at: datetime
