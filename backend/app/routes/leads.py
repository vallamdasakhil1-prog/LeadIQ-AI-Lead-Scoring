from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assessment, AssessmentHistory, Lead
from ..schemas import (AssessmentOut, AssessmentSummary, HistoryItem, LeadCreate, LeadCreated, LeadListResponse,
                       LeadOut)
from ..services.assessment_service import UnusableLeadError, assess_lead, create_lead
from ..services.gemini_service import GeminiService, get_gemini_service

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _lead_or_404(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    return lead


def _latest(db: Session, lead_id: int) -> Optional[Assessment]:
    return db.scalars(select(Assessment).where(Assessment.lead_id == lead_id)
                      .order_by(Assessment.id.desc()).limit(1)).first()


def _lead_out(lead: Lead, latest: Optional[Assessment]) -> LeadOut:
    out = LeadOut.model_validate(lead)
    out.latest_assessment = AssessmentSummary.model_validate(latest) if latest else None
    return out


@router.post("", response_model=LeadCreated, status_code=201)
def submit_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    try:
        lead, report = create_lead(db, payload.model_dump())
    except UnusableLeadError as exc:
        raise HTTPException(status_code=422, detail={
            "message": "Lead cannot be processed.", "validation": exc.report.to_dict()})
    return {"lead": _lead_out(lead, None), "validation": report.to_dict()}


@router.get("", response_model=LeadListResponse)
def list_leads(search: Optional[str] = None,
               classification: Optional[str] = Query(None, description="HOT, WARM, COLD or UNASSESSED"),
               limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db)):
    latest_ids = select(func.max(Assessment.id)).group_by(Assessment.lead_id)
    stmt = (select(Lead, Assessment).outerjoin(
        Assessment, and_(Assessment.lead_id == Lead.id, Assessment.id.in_(latest_ids))))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(*(getattr(Lead, f).ilike(like) for f in (
            "name", "company_name", "email", "industry", "requirement", "job_title"))))
    if classification:
        c = classification.upper()
        if c == "UNASSESSED":
            stmt = stmt.where(Assessment.id.is_(None))
        elif c in ("HOT", "WARM", "COLD"):
            stmt = stmt.where(Assessment.classification == c)
        else:
            raise HTTPException(status_code=422, detail="classification must be HOT, WARM, COLD or UNASSESSED")
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Lead.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [_lead_out(l, a) for l, a in rows], "total": total or 0,
            "limit": limit, "offset": offset}


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = _lead_or_404(db, lead_id)
    return _lead_out(lead, _latest(db, lead_id))


@router.post("/{lead_id}/assess", response_model=AssessmentOut, status_code=201)
def run_assessment(lead_id: int, db: Session = Depends(get_db),
                   gemini: GeminiService = Depends(get_gemini_service)):
    lead = _lead_or_404(db, lead_id)
    return assess_lead(db, lead, gemini)


@router.get("/{lead_id}/assessment", response_model=AssessmentOut)
def get_assessment(lead_id: int, db: Session = Depends(get_db)):
    _lead_or_404(db, lead_id)
    latest = _latest(db, lead_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="This lead has not been assessed yet")
    return latest


@router.get("/{lead_id}/history", response_model=list[HistoryItem])
def assessment_history(lead_id: int, db: Session = Depends(get_db)):
    _lead_or_404(db, lead_id)
    return db.scalars(select(AssessmentHistory).where(AssessmentHistory.lead_id == lead_id)
                      .order_by(AssessmentHistory.id.desc())).all()
