"""Confidence in the *data* behind an assessment (format checks only: nothing is verified).

Deliberately independent of the lead score: it looks only at how complete,
valid, reliable and self-consistent the submitted information is.  It says
nothing about the probability that the lead will convert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import ScoringConfig
from .intent import analyse_intent
from .lead_validator import FIELD_ORDER, NormalizedLead, looks_like_placeholder
from .prompt_safety import find_injection

W_COMPLETENESS, W_CONTACT, W_RELIABILITY, W_CONSISTENCY = 40.0, 25.0, 20.0, 15.0


@dataclass
class ConfidenceResult:
    level: str
    score: float
    components: dict
    notes: list = field(default_factory=list)
    contradictions: list = field(default_factory=list)
    injection_flags: list = field(default_factory=list)  # fields containing instruction-like text


def calculate_confidence(n: NormalizedLead, cfg: ScoringConfig) -> ConfidenceResult:
    notes: list = []

    # 1. Data completeness (40): share of the 11 fields that are present
    present = sum(1 for f in FIELD_ORDER if n.status.get(f) in ("valid", "invalid"))
    completeness = round(W_COMPLETENESS * present / len(FIELD_ORDER), 2)
    if present < len(FIELD_ORDER):
        notes.append(f"{len(FIELD_ORDER) - present} of {len(FIELD_ORDER)} fields were not provided.")

    # 2. Contact validity (25)
    contact = 0.0
    contact += 12 if n.is_valid("email") else 0
    contact += 10 if n.is_valid("phone") else 0
    contact += 3 if n.is_valid("name") else 0
    if not n.is_valid("email"):
        notes.append("No valid email address.")
    if not n.is_valid("phone"):
        notes.append("No valid phone number.")

    # 3. Information reliability (20)
    reliability = W_RELIABILITY
    invalid = [f for f in FIELD_ORDER if n.status.get(f) == "invalid"]
    if invalid:
        reliability -= min(12, 4 * len(invalid))
        notes.append(f"{len(invalid)} field(s) contained invalid values.")
    if n.email and n.company_name and n.email_is_free:
        reliability -= 2
    if n.email and n.email_is_disposable:
        reliability -= 6
        notes.append("Email uses a disposable domain.")
    if any(looks_like_placeholder(v) for v in (n.name, n.company_name)):
        reliability -= 5
        notes.append("Name or company looks like placeholder text.")
    if n.email_is_reserved or n.website_is_reserved:
        reliability -= 3
        notes.append("Email or website uses a reserved example domain (demonstration data, not a real "
                     "mailbox or site).")
    injection_flags = []
    for fname in FIELD_ORDER:
        hits = find_injection(getattr(n, fname) or "")
        if hits:
            injection_flags.append({"field": fname, "patterns": hits})
    if injection_flags:
        reliability -= 5
        notes.append("Instruction-like text was found in: "
                     + ", ".join(f["field"] for f in injection_flags)
                     + ". It was withheld from the AI analysis and had no effect on the score.")
    reliability = max(0.0, reliability)

    # 4. Consistency (15): contradictions reduce confidence
    contradictions: list = []
    penalty = 0.0
    req = (n.requirement or "").lower()
    title = (n.job_title or "").lower()
    if re.search(cfg.title_student_regex, title) and re.search(r"\b(buy|purchase|implement|budget|enterprise)\b", req):
        contradictions.append("Student/intern contact claims an enterprise purchase requirement.")
        penalty += 7
    if n.requirement and analyse_intent(n.requirement, cfg).negative_intent and n.lead_source and re.search(
            r"referral|demo", n.lead_source.lower()):
        contradictions.append("High-intent lead source conflicts with a requirement that expresses no purchase intent.")
        penalty += 7
    if n.email_domain and n.website and not n.email_is_free and not n.email_is_disposable \
            and not n.email_is_reserved and not n.website_is_reserved \
            and n.email_domain != n.website and not n.email_domain.endswith("." + n.website) \
            and not n.website.endswith("." + n.email_domain):
        contradictions.append(
            f"Email domain ({n.email_domain}) differs from the company website ({n.website}).")
        penalty += 4
    consistency = max(0.0, W_CONSISTENCY - penalty)
    notes.extend(contradictions)

    total = round(completeness + contact + reliability + consistency, 2)
    level = "HIGH" if total >= 75 else "MEDIUM" if total >= 50 else "LOW"
    return ConfidenceResult(
        level=level, score=total,
        components={
            "data_completeness": {"score": completeness, "max": W_COMPLETENESS},
            "contact_validity": {"score": contact, "max": W_CONTACT},
            "information_reliability": {"score": reliability, "max": W_RELIABILITY},
            "consistency": {"score": consistency, "max": W_CONSISTENCY},
        },
        notes=notes, contradictions=contradictions, injection_flags=injection_flags,
    )
