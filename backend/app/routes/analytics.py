from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import PARAMETER_LABELS, get_scoring_config
from ..database import get_db
from ..models import Assessment, Lead

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/overview")
def overview(db: Session = Depends(get_db)):
    """All figures are computed from stored records (latest assessment per lead)."""
    total_leads = db.scalar(select(func.count(Lead.id))) or 0
    latest_ids = select(func.max(Assessment.id)).group_by(Assessment.lead_id)
    rows = db.execute(select(Assessment.classification, Assessment.score,
                             Assessment.confidence_level)
                      .where(Assessment.id.in_(latest_ids))).all()
    assessed = len(rows)
    counts = {"HOT": 0, "WARM": 0, "COLD": 0}
    scores = {"HOT": [], "WARM": [], "COLD": []}
    confidence = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    buckets = [{"range": f"{i}-{i + 9 if i < 90 else 100}", "count": 0} for i in range(0, 100, 10)]
    for cls, score, conf in rows:
        counts[cls] += 1
        scores[cls].append(score)
        confidence[conf] += 1
        buckets[min(int(score // 10), 9)]["count"] += 1
    all_scores = [s for v in scores.values() for s in v]
    stats = []
    for cls in ("HOT", "WARM", "COLD"):
        v = scores[cls]
        stats.append({
            "classification": cls, "count": counts[cls],
            "percentage": round(100 * counts[cls] / assessed, 1) if assessed else 0.0,
            "average_score": round(sum(v) / len(v), 2) if v else None,
            "min_score": min(v) if v else None, "max_score": max(v) if v else None})
    return {
        "total_leads": total_leads,
        "assessed_leads": assessed,
        "unassessed_leads": total_leads - assessed,
        "hot_leads": counts["HOT"], "warm_leads": counts["WARM"], "cold_leads": counts["COLD"],
        "average_score": round(sum(all_scores) / len(all_scores), 2) if all_scores else None,
        "classification_distribution": [{"name": k, "value": v} for k, v in counts.items()],
        "score_distribution": buckets,
        "confidence_distribution": [{"name": k, "value": v} for k, v in confidence.items()],
        "category_statistics": stats,
    }


@router.get("/config/scoring", tags=["config"])
def scoring_config():
    cfg = get_scoring_config()
    return {"weights": cfg.weights, "labels": PARAMETER_LABELS,
            "thresholds": {"hot": cfg.hot_threshold, "warm": cfg.warm_threshold}}
