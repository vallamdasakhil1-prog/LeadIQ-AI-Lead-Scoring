"""Google Gemini integration (official ``google-genai`` SDK).

Gemini only *explains*: it never receives a way to set the score, the response
schema has no score field, and responses that contradict the engine's score or
classification are rejected.  Any failure raises ``GeminiError`` so the caller
can fall back to the rule-based narrative.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger("leadiq.gemini")

DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = (
    "You are a sales-analytics assistant for a lead scoring product. A deterministic scoring "
    "engine has ALREADY calculated the score, classification, breakdown, factors and data "
    "confidence. Treat them as final facts.\n"
    "Rules you must follow:\n"
    "1. Do NOT calculate, change, re-weight or dispute the score or classification.\n"
    "2. Do NOT invent lead information. Fields that are null were not provided; say so rather "
    "than guessing.\n"
    "3. Confidence describes data quality, NOT the probability of conversion; keep them distinct.\n"
    "4. Write concise, practical, professional prose for a sales team.\n"
    "Return ONLY JSON matching the provided schema."
)


class GeminiAnalysis(BaseModel):
    """Structured output requested from Gemini.  Intentionally has no score fields."""

    quality_assessment: str = Field(min_length=10, max_length=1500)
    scoring_explanation: str = Field(min_length=10, max_length=2500)
    business_insights: list[str] = Field(min_length=1, max_length=6)
    recommended_next_action: str = Field(min_length=5, max_length=600)

    @field_validator("business_insights")
    @classmethod
    def _non_empty_items(cls, v):
        v = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        if not v:
            raise ValueError("business_insights must contain at least one non-empty item")
        return v


class GeminiError(Exception):
    """kind: missing_api_key | rate_limited | timeout | network | api_error | invalid_response"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _guard_against_overrides(analysis: GeminiAnalysis, score: float, classification: str) -> None:
    """Reject narrative text that states a different score or classification."""
    text = " ".join([analysis.quality_assessment, analysis.scoring_explanation,
                     analysis.recommended_next_action, *analysis.business_insights])
    for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*(?:/|out of)\s*100", text, flags=re.I):
        if abs(float(m.group(1)) - score) > 0.51:
            raise GeminiError("invalid_response",
                              f"Response states score {m.group(1)}/100, contradicting the engine ({score:g}).")
    for m in re.finditer(r"\b(hot|warm|cold)\s+(?:lead|prospect)\b", text, flags=re.I):
        if m.group(1).upper() != classification:
            raise GeminiError("invalid_response",
                              f"Response labels the lead {m.group(1).upper()}, contradicting {classification}.")


class GeminiService:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 timeout_seconds: Optional[float] = None, retries: Optional[int] = None,
                 retry_delay: float = 1.0, client=None):
        self._api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
        self.timeout_seconds = timeout_seconds or float(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))
        self.retries = retries if retries is not None else int(os.getenv("GEMINI_MAX_RETRIES", "1"))
        self.retry_delay = retry_delay
        self._client = client  # injectable for tests

    @property
    def is_configured(self) -> bool:
        placeholder = self._api_key.strip().lower() in ("", "your_gemini_api_key")
        return self._client is not None or not placeholder

    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
            )
        return self._client

    def _generate_text(self, prompt: str) -> str:
        from google.genai import types

        response = self._get_client().models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=GeminiAnalysis,
                temperature=0.2,
            ),
        )
        return response.text or ""

    def analyze(self, payload: dict, score: float, classification: str) -> GeminiAnalysis:
        if not self.is_configured:
            raise GeminiError("missing_api_key", "GEMINI_API_KEY is not configured.")
        prompt = ("Analyse this lead. All numbers below were produced by the deterministic engine.\n"
                  + json.dumps(payload, indent=2, default=str))
        attempt = 0
        while True:
            try:
                text = self._generate_text(prompt)
                break
            except GeminiError:
                raise
            except Exception as exc:  # map SDK / transport errors
                err = self._map_error(exc)
                if err.kind in ("rate_limited", "network", "api_error") and attempt < self.retries \
                        and getattr(exc, "code", 500) in (429, 500, 502, 503, 504):
                    attempt += 1
                    time.sleep(self.retry_delay * attempt)
                    continue
                raise err from exc
        return self._parse(text, score, classification)

    @staticmethod
    def _parse(text: str, score: float, classification: str) -> GeminiAnalysis:
        cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
        try:
            analysis = GeminiAnalysis.model_validate_json(cleaned)
        except (ValidationError, ValueError) as exc:
            raise GeminiError("invalid_response", f"Gemini returned an invalid response: {exc}") from exc
        _guard_against_overrides(analysis, score, classification)
        return analysis

    @staticmethod
    def _map_error(exc: Exception) -> GeminiError:
        import httpx

        try:
            from google.genai import errors as genai_errors
        except Exception:  # pragma: no cover
            genai_errors = None
        code = getattr(exc, "code", None)
        if genai_errors and isinstance(exc, genai_errors.APIError):
            if code == 429:
                return GeminiError("rate_limited", "Gemini rate limit reached.")
            if code in (408, 504):
                return GeminiError("timeout", "Gemini request timed out.")
            if code in (401, 403):
                return GeminiError("api_error", "Gemini rejected the API key or permissions.")
            return GeminiError("api_error", f"Gemini API error ({code}).")
        if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            return GeminiError("timeout", "Gemini request timed out.")
        if isinstance(exc, (httpx.HTTPError, ConnectionError, OSError)):
            return GeminiError("network", "Could not reach the Gemini API.")
        return GeminiError("api_error", f"Unexpected Gemini failure: {type(exc).__name__}")


def get_gemini_service() -> GeminiService:
    """FastAPI dependency (overridden in tests)."""
    return GeminiService()
