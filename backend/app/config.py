"""Runtime settings and the (fully configurable) scoring configuration.

The scoring engine receives a ``ScoringConfig`` object; weights, thresholds,
keyword lists and band tables all live here so they can be changed without
touching ``scoring_engine.py``.  Overrides can come from environment variables
(``HOT_THRESHOLD``, ``WARM_THRESHOLD``) or from a JSON file pointed to by
``SCORING_CONFIG_PATH``.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

PARAMETERS = (
    "industry_relevance",
    "purchase_intent",
    "job_title",
    "company_size",
    "lead_source",
    "contact_information",
    "company_completeness",
)

PARAMETER_LABELS = {
    "industry_relevance": "Industry Relevance",
    "purchase_intent": "Purchase Intent",
    "job_title": "Job Title / Decision-Making Authority",
    "company_size": "Company Size",
    "lead_source": "Lead Source",
    "contact_information": "Contact Information",
    "company_completeness": "Company Information Completeness",
}

DEFAULT_WEIGHTS = {
    "industry_relevance": 20,
    "purchase_intent": 25,
    "job_title": 15,
    "company_size": 10,
    "lead_source": 10,
    "contact_information": 10,
    "company_completeness": 10,
}


def database_url() -> str:
    return os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'leadiq.db'}")


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass
class ScoringConfig:
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    hot_threshold: float = 75.0
    warm_threshold: float = 50.0

    # --- Industry relevance ---------------------------------------------
    industry_tier1: list = field(default_factory=lambda: [
        "it services", "information technology", "software", "saas", "technology",
        "tech", "fintech", "e-commerce", "ecommerce", "digital", "marketing",
        "advertising", "real estate", "consulting", "startup", "internet",
    ])
    industry_tier2: list = field(default_factory=lambda: [
        "finance", "banking", "bfsi", "insurance", "healthcare", "hospital", "pharma",
        "education", "edtech", "manufacturing", "retail", "logistics", "hospitality",
        "automotive", "construction", "media", "travel", "telecom", "consumer",
    ])
    industry_multipliers: dict = field(
        default_factory=lambda: {"tier1": 1.0, "tier2": 0.7, "other": 0.35}
    )

    # --- Purchase intent --------------------------------------------------
    intent_components: dict = field(default_factory=lambda: {
        "solution": 0.32, "buying_signal": 0.36, "timeline_or_budget": 0.20, "detail": 0.12,
    })
    intent_solution_keywords: list = field(default_factory=lambda: [
        "crm", "erp", "software", "saas", "platform", "automation", "lead management",
        "app", "tool", "system", "solution", "website", "cloud", "analytics", "chatbot",
        "hrms", "billing", "inventory", "ai", "dashboard", "integration",
    ])
    intent_buying_keywords: list = field(default_factory=lambda: [
        "looking for", "looking to", "need", "needs", "want to buy", "want to purchase",
        "require", "requires", "required", "interested in buying", "planning to",
        "wish to", "searching for", "evaluate", "evaluating", "implement", "purchase",
        "buy", "buying", "purchasing", "upgrade", "replace", "migrate", "quote", "pricing",
        "demo", "proposal",
    ])
    # Words that, when negated ("no purchase requirement", "not interested"), signal no intent.
    intent_negation_targets: list = field(default_factory=lambda: [
        "requirement", "requirements", "purchase", "purchasing", "buying", "interested",
        "interest", "planning", "plans", "intent", "intention", "looking",
    ])
    intent_negation_window: int = 4  # how many tokens before a phrase a negation cue may appear
    intent_timeline_keywords: list = field(default_factory=lambda: [
        "urgent", "urgently", "immediately", "asap", "this month", "this week",
        "next month", "next week", "this quarter", "within", "budget", "approved",
        "deadline", "right away", "by q1", "by q2", "by q3", "by q4",
    ])
    intent_negative_keywords: list = field(default_factory=lambda: [
        "student", "learning", "assignment", "academic", "research paper", "college project",
        "school project", "curious", "just browsing", "just looking", "exploring only",
        "thesis", "for fun",
    ])
    intent_negative_cap: float = 0.12  # max share of the weight when negative intent is detected

    # --- Job title / authority -------------------------------------------
    # [name, regex, multiplier]; the highest matching multiplier wins, then the
    # student / junior modifiers cap it.
    title_rules: list = field(default_factory=lambda: [
        ["Owner / C-level / Founder",
         r"\b(founder|co-?founder|owner|ceo|cto|cfo|coo|cmo|cio|chief|chairman|proprietor|managing director|managing partner|partner|md)\b|(?<!vice )\bpresident\b", 1.0],
        ["Director / VP / Head", r"\b(vice president|vp|svp|director|head)\b", 0.87],
        ["Manager", r"\b(manager|gm)\b", 0.67],
        ["Senior / Lead", r"\b(senior|sr|lead|principal|supervisor)\b", 0.47],
        ["Individual contributor",
         r"\b(executive|analyst|engineer|developer|consultant|specialist|coordinator|officer|representative|administrator|designer|accountant)\b", 0.27],
    ])
    title_student_regex: str = r"\b(student|intern|trainee|fresher|apprentice|learner)\b"
    title_student_multiplier: float = 0.07
    title_junior_regex: str = r"\b(assistant|junior|jr|associate)\b"
    title_junior_multiplier: float = 0.27
    title_default_multiplier: float = 0.2

    # --- Company size: [min_inclusive, max_exclusive|None, multiplier] on the
    # midpoint of the stated employee range ---------------------------------
    size_bands: list = field(default_factory=lambda: [
        [0, 11, 0.4], [11, 51, 0.7], [51, 501, 1.0], [501, 1001, 0.8], [1001, None, 0.7],
    ])
    size_unparseable_multiplier: float = 0.0

    # --- Lead source: [keyword, multiplier], first match wins ---------------
    source_rules: list = field(default_factory=lambda: [
        ["referral", 1.0], ["demo", 1.0], ["website", 0.9], ["inbound", 0.9],
        ["contact form", 0.9], ["organic", 0.9], ["partner", 0.8], ["webinar", 0.7],
        ["event", 0.7], ["trade show", 0.7], ["conference", 0.7], ["linkedin", 0.7],
        ["email campaign", 0.6], ["newsletter", 0.6], ["ads", 0.6], ["advertisement", 0.6],
        ["social", 0.5], ["facebook", 0.5], ["instagram", 0.5], ["twitter", 0.5],
        ["cold", 0.3], ["outbound", 0.3], ["purchased", 0.3], ["scraped", 0.3], ["list", 0.3],
    ])
    source_default_multiplier: float = 0.4

    # --- Share of the weight earned by each sub-check -----------------------
    contact_components: dict = field(default_factory=lambda: {
        "email": 0.4, "business_domain": 0.1, "phone": 0.4, "name": 0.1,
    })
    completeness_components: dict = field(default_factory=lambda: {
        "company_name": 0.3, "website": 0.3, "location": 0.2, "size": 0.2,
    })

    def validate(self) -> "ScoringConfig":
        if set(self.weights) != set(PARAMETERS):
            raise ValueError(f"weights must define exactly: {', '.join(PARAMETERS)}")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("weights must be non-negative")
        if abs(sum(self.weights.values()) - 100) > 1e-9:
            raise ValueError("weights must sum to 100")
        if not (0 < self.warm_threshold < self.hot_threshold <= 100):
            raise ValueError("thresholds must satisfy 0 < warm < hot <= 100")
        for name in ("intent_components", "contact_components", "completeness_components"):
            if abs(sum(getattr(self, name).values()) - 1.0) > 1e-9:
                raise ValueError(f"{name} must sum to 1.0")
        return self

    def to_dict(self) -> dict:
        return asdict(self)


def _load() -> ScoringConfig:
    cfg = ScoringConfig()
    path = os.getenv("SCORING_CONFIG_PATH")
    if path:
        data = json.loads(Path(path).read_text())
        for key, value in data.items():
            if not hasattr(cfg, key):
                raise ValueError(f"Unknown scoring config key: {key}")
            setattr(cfg, key, value)
    if os.getenv("HOT_THRESHOLD"):
        cfg.hot_threshold = float(os.environ["HOT_THRESHOLD"])
    if os.getenv("WARM_THRESHOLD"):
        cfg.warm_threshold = float(os.environ["WARM_THRESHOLD"])
    return cfg.validate()


@lru_cache(maxsize=1)
def get_scoring_config() -> ScoringConfig:
    return _load()
