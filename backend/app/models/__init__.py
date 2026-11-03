from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Raw (trimmed) values exactly as submitted
    name: Mapped[Optional[str]] = mapped_column(String(200))
    company_name: Mapped[Optional[str]] = mapped_column(String(300))
    website: Mapped[Optional[str]] = mapped_column(String(300))
    job_title: Mapped[Optional[str]] = mapped_column(String(200))
    industry: Mapped[Optional[str]] = mapped_column(String(200))
    company_location: Mapped[Optional[str]] = mapped_column(String(200))
    company_size: Mapped[Optional[str]] = mapped_column(String(100))
    lead_source: Mapped[Optional[str]] = mapped_column(String(200))
    requirement: Mapped[Optional[str]] = mapped_column(Text)
    email: Mapped[Optional[str]] = mapped_column(String(320))
    phone: Mapped[Optional[str]] = mapped_column(String(60))
    # Result of validation / normalisation at submission time
    normalized_data: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Assessment.id"
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(10), index=True)
    confidence_level: Mapped[str] = mapped_column(String(10))
    confidence_score: Mapped[float] = mapped_column(Float)
    confidence_details: Mapped[dict] = mapped_column(JSON, default=dict)
    positive_factors: Mapped[list] = mapped_column(JSON, default=list)
    negative_factors: Mapped[list] = mapped_column(JSON, default=list)
    scoring_explanation: Mapped[str] = mapped_column(Text)  # deterministic calculation
    quality_assessment: Mapped[str] = mapped_column(Text)
    ai_explanation: Mapped[str] = mapped_column(Text)
    business_insights: Mapped[list] = mapped_column(JSON, default=list)
    recommended_next_action: Mapped[str] = mapped_column(Text)
    explanation_source: Mapped[str] = mapped_column(String(20), default="rule_based")
    gemini_model: Mapped[Optional[str]] = mapped_column(String(100))
    gemini_error: Mapped[Optional[str]] = mapped_column(Text)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="assessments")
    breakdown: Mapped[list["ScoreBreakdown"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", order_by="ScoreBreakdown.id"
    )


class ScoreBreakdown(Base):
    __tablename__ = "score_breakdowns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    parameter: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100))
    max_score: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    criteria: Mapped[str] = mapped_column(Text)
    rule_applied: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)

    assessment: Mapped[Assessment] = relationship(back_populates="breakdown")


class AssessmentHistory(Base):
    """Append-only log of every assessment run for a lead."""

    __tablename__ = "assessment_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(10))
    confidence_level: Mapped[str] = mapped_column(String(10))
    explanation_source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
