"""Treat lead data as untrusted before it reaches an LLM.

Lead fields are typed by strangers.  Before anything is sent to Gemini we
  1. strip control characters and cap the length of every string,
  2. detect instruction-like text (prompt-injection attempts), and
  3. replace any string that looks like an instruction with a neutral placeholder.
Detection is a best-effort *defence in depth*: the real guarantees are that the deterministic
score never depends on Gemini and that Gemini's output is schema-validated and cross-checked.
"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[withheld: instruction-like text removed]"
DEFAULT_MAX_LEN = 400
MAX_LEN_BY_KEY = {"requirement": 800}

_FLAGS = re.I | re.S
INJECTION_PATTERNS = {
    "override_instructions": re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass|skip)\b[^.\n]{0,50}"
        r"\b(?:instructions?|prompts?|guidelines?|directives?|system message|rules above)\b", _FLAGS),
    "ignore_previous": re.compile(
        r"\b(?:ignore|disregard|forget)\b\s+(?:all\s+|any\s+|the\s+)?"
        r"(?:previous|prior|above|earlier|preceding)\b", _FLAGS),
    "reveal_secrets": re.compile(
        r"\b(?:reveal|print|repeat|leak|disclose|expose|show)\b[^.\n]{0,30}"
        r"\b(?:system prompt|your prompt|your instructions|api[ _-]?key|hidden instructions|secrets?)\b", _FLAGS),
    "role_change": re.compile(
        r"\b(?:you are now|pretend (?:to be|you)|new instructions?|from now on|your new (?:role|task)"
        r"|developer mode|jailbreak)\b|\bact as (?:an? |the )?(?:ai|assistant|system|admin|developer|model|llm|dan)\b",
        _FLAGS),
    "score_manipulation": re.compile(
        r"\b(?:set|change|make|assign|give|rate|mark|output|return|increase|raise)\b[^.\n]{0,40}"
        r"\b(?:score|classification|rating)\b[^.\n]{0,30}\b(?:to|as|of|at)\b[^.\n]{0,15}"
        r"(?:\b\d{2,3}\b|\bhot\b|\bwarm\b|\bcold\b|\bmax(?:imum)?\b|\bhighest\b|\bperfect\b)", _FLAGS),
    "classification_manipulation": re.compile(
        r"\b(?:classify|label|mark|categori[sz]e|rate)\s+(?:this|the|my|that|our)\s+"
        r"(?:lead|prospect|contact|company|enquiry|inquiry)\b[^.\n]{0,20}\b(?:as|to)\b\s+(?:a\s+)?"
        r"(?:hot|warm|cold)\b"
        r"|\b(?:classify|categori[sz]e|label)\s+(?:it\s+|this\s+|me\s+)?(?:as|to)\s+(?:a\s+)?"
        r"(?:hot|warm|cold)\b", _FLAGS),
    "markup_injection": re.compile(
        r"</?\s*(?:system|assistant|user|instructions?|prompt|lead_analysis_data|untrusted\w*|engine_results)\b[^>]*>"
        r"|\[/?(?:inst|system)\]|<\|[a-z_]+\|>|```", _FLAGS),
    "json_forgery": re.compile(
        r"[\"']\s*(?:score|final_score|classification|quality_assessment|recommended_next_action)"
        r"\s*[\"']\s*:", _FLAGS),
}


def find_injection(text: str) -> list:
    """Names of the injection patterns found in ``text`` (empty list = nothing suspicious)."""
    if not text:
        return []
    return [name for name, rx in INJECTION_PATTERNS.items() if rx.search(text)]


def sanitize_text(text: str, max_len: int = DEFAULT_MAX_LEN) -> str:
    text = re.sub(r"[\x00-\x1f\x7f\u200b-\u200f\u2028-\u202e\u2060\ufeff]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def scrub(value: Any, key: str = "", path: str = "", flags: list | None = None):
    """Recursively sanitise a JSON-like structure.  Returns (clean_value, flags)."""
    flags = [] if flags is None else flags
    if isinstance(value, str):
        hits = find_injection(value)  # check the raw text first, before truncation could hide it
        if hits:
            flags.append({"path": path or key, "patterns": hits})
            return REDACTED, flags
        return sanitize_text(value, MAX_LEN_BY_KEY.get(key, DEFAULT_MAX_LEN)), flags
    if isinstance(value, dict):
        return {k: scrub(v, k, f"{path}.{k}" if path else k, flags)[0] for k, v in value.items()}, flags
    if isinstance(value, (list, tuple)):
        return [scrub(v, key, f"{path}[{i}]", flags)[0] for i, v in enumerate(value)], flags
    return value, flags
