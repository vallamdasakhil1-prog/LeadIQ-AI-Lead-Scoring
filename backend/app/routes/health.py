from __future__ import annotations

from fastapi import APIRouter

from ..services.gemini_service import GeminiService

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    svc = GeminiService()
    return {"status": "ok", "gemini_configured": svc.is_configured, "gemini_model": svc.model}
