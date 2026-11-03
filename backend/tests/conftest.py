import os

os.environ.setdefault("GEMINI_API_KEY", "")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.gemini_service import GeminiAnalysis, GeminiError, get_gemini_service

SAMPLE = dict(
    name="Rahul Sharma", company_name="ABC Technologies", website="www.abctechnologies.com",
    job_title="Founder", industry="IT Services", company_location="Bangalore",
    company_size="50–100 Employees", lead_source="Website",
    requirement="Looking for CRM software", email="rahul@example.com", phone="+91 9876543210")


class FakeGemini:
    """Stands in for GeminiService. Behaviour is selected via ``mode``."""
    model = "fake-model"
    is_configured = True

    def __init__(self, mode="ok", text=None):
        self.mode, self.text, self.calls, self.seen = mode, text, 0, None

    def analyze(self, payload, score, classification):
        self.calls += 1
        self.seen = payload
        if self.mode == "mutate":
            payload["engine_results"]["score"] = 0
            payload["engine_results"]["classification"] = "COLD"
            payload["engine_results"]["score_breakdown"].clear()
        if self.mode == "error":
            raise GeminiError("network", "Could not reach the Gemini API.")
        if self.mode == "rate_limited":
            raise GeminiError("rate_limited", "Gemini rate limit reached.")
        if self.mode == "invalid":
            from app.services.gemini_service import GeminiService
            return GeminiService._parse(self.text or "this is not json", score, classification)
        if self.mode == "lying":  # tries to override the score
            from app.services.gemini_service import GeminiService
            return GeminiService._parse(
                '{"quality_assessment":"Great lead, really scores 12/100 in my view.",'
                '"scoring_explanation":"I recalculated the score as 12/100 overall.",'
                '"business_insights":["x insight"],"recommended_next_action":"Call them now."}',
                score, classification)
        return GeminiAnalysis(
            quality_assessment=f"AI view: {classification} lead with strong potential.",
            scoring_explanation="AI narrative explaining the deterministic breakdown.",
            business_insights=["AI insight one"], recommended_next_action="AI: book a demo.")


@pytest.fixture()
def gemini():
    return FakeGemini()


@pytest.fixture()
def client(gemini):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_gemini_service] = lambda: gemini
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def submit_and_assess(client, payload):
    r = client.post("/api/leads", json=payload)
    assert r.status_code == 201, r.text
    lead_id = r.json()["lead"]["id"]
    a = client.post(f"/api/leads/{lead_id}/assess")
    assert a.status_code == 201, a.text
    return lead_id, a.json()
