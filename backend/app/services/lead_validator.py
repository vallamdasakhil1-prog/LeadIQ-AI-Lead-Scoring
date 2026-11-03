"""Validation and normalisation of raw lead input.

Every field is classified as ``valid``, ``missing`` or ``invalid``.  Invalid
values are never silently repaired: they are reported and treated as unusable
by the scoring engine.  A lead is rejected outright only when it has neither a
usable contact name nor a usable company name.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

FIELD_ORDER = [
    "name", "company_name", "website", "job_title", "industry", "company_location",
    "company_size", "lead_source", "requirement", "email", "phone",
]
FIELD_LABELS = {
    "name": "Name", "company_name": "Company Name", "website": "Website",
    "job_title": "Job Title", "industry": "Industry",
    "company_location": "Company Location", "company_size": "Company Size",
    "lead_source": "Lead Source", "requirement": "Requirement",
    "email": "Email", "phone": "Phone",
}

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.in", "outlook.com", "hotmail.com", "live.com",
    "aol.com", "icloud.com", "proton.me", "protonmail.com", "rediffmail.com", "gmx.com",
    "zoho.com", "ymail.com", "mail.com",
}
DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com", "10minutemail.com", "guerrillamail.com", "tempmail.com",
    "trashmail.com", "yopmail.com", "throwawaymail.com", "sharklasers.com",
}
PLACEHOLDER_VALUES = {
    "test", "testing", "asdf", "asdfgh", "qwerty", "xxx", "xyz", "abc", "na", "n/a",
    "none", "null", "unknown", "dummy", "sample", "fake", "foo", "bar",
}

_EMAIL_RE = re.compile(
    r"^[a-z0-9._%+\-]+@[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?)*\.[a-z]{2,}$"
)
_DOMAIN_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?)+$"
)


@dataclass
class FieldReport:
    field: str
    label: str
    status: str  # valid | missing | invalid
    message: str
    raw: Optional[str] = None
    normalized: Optional[str] = None


@dataclass
class ValidationReport:
    usable: bool
    fields: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    invalid: list = field(default_factory=list)
    messages: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NormalizedLead:
    name: Optional[str] = None
    company_name: Optional[str] = None
    website: Optional[str] = None  # bare host, e.g. abctechnologies.com
    job_title: Optional[str] = None
    industry: Optional[str] = None
    company_location: Optional[str] = None
    company_size: Optional[str] = None  # canonical text, e.g. "50-100"
    company_size_value: Optional[float] = None  # midpoint used for scoring
    lead_source: Optional[str] = None
    requirement: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None  # E.164
    status: dict = field(default_factory=dict)

    @property
    def email_domain(self) -> Optional[str]:
        return self.email.split("@", 1)[1] if self.email else None

    @property
    def email_is_free(self) -> bool:
        return self.email_domain in FREE_EMAIL_DOMAINS

    @property
    def email_is_disposable(self) -> bool:
        return self.email_domain in DISPOSABLE_EMAIL_DOMAINS

    def is_valid(self, name: str) -> bool:
        return self.status.get(name) == "valid"

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("status", None)
        return data


# --------------------------------------------------------------------------- helpers
def clean_text(value) -> Optional[str]:
    if value is None:
        return None
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _has_letter(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def normalize_website(raw: str) -> Optional[str]:
    s = raw.strip().lower()
    if " " in s:
        return None
    s = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = re.split(r"[/?#]", s, maxsplit=1)[0]
    s = s.split("@")[-1].split(":")[0].rstrip(".")
    if len(s) > 253 or not _DOMAIN_RE.match(s) or not re.search(r"\.[a-z]{2,}$", s):
        return None
    return s


def normalize_email(raw: str) -> Optional[str]:
    s = raw.strip().lower()
    if len(s) > 254 or ".." in s or not _EMAIL_RE.match(s):
        return None
    if len(s.split("@", 1)[0]) > 64:
        return None
    return s


def normalize_phone(raw: str) -> Optional[str]:
    """Return an E.164 number or None.  10-digit national numbers are assumed Indian (+91)."""
    s = re.sub(r"[\s().\-]", "", raw)
    if not re.fullmatch(r"\+?\d+", s):
        return None
    if s.startswith("+"):
        digits = s[1:]
    elif s.startswith("00"):
        digits = s[2:]
    elif len(s) == 10:
        digits = "91" + s
    elif len(s) == 11 and s.startswith("0"):
        digits = "91" + s[1:]
    elif len(s) == 12 and s.startswith("91"):
        digits = s
    else:
        return None
    if not 8 <= len(digits) <= 15 or digits[0] == "0":
        return None
    if digits.startswith("91"):
        national = digits[2:]
        if len(national) != 10 or national[0] not in "6789":
            return None
    if len(set(digits)) <= 2:  # 0000000000, 1111111111 ...
        return None
    return "+" + digits


def parse_company_size(raw: str) -> Optional[tuple]:
    """Return (canonical text, midpoint) or None.  Understands 50-100, 50–100 employees, 1000+, 250."""
    s = raw.lower().replace(",", "")
    s = re.sub(r"\b(employees?|emps?|staff|people|members)\b", "", s).strip()
    m = re.fullmatch(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo < 1 or hi < lo or hi > 10_000_000:
            return None
        return f"{lo}-{hi}", (lo + hi) / 2
    m = re.fullmatch(r"(?:over|more than|above|>)?\s*(\d+)\s*\+?", s)
    if m:
        n = int(m.group(1))
        if n < 1 or n > 10_000_000:
            return None
        plus = "+" in s or re.match(r"(over|more than|above|>)", s) is not None
        return (f"{n}+" if plus else str(n)), float(n)
    return None


def _simple_text(raw, min_len=2, max_len=200):
    text = clean_text(raw)
    if text is None:
        return None, "missing"
    if len(text) < min_len or len(text) > max_len or not _has_letter(text):
        return text, "invalid"
    return text, "valid"


# --------------------------------------------------------------------------- main API
def validate_and_normalize(raw: dict) -> tuple:
    """Return (NormalizedLead, ValidationReport) for a dict of raw lead fields."""
    n = NormalizedLead()
    reports: list = []

    def add(name, status, message, raw_value, normalized=None):
        n.status[name] = status
        reports.append(FieldReport(
            name, FIELD_LABELS[name], status, message, clean_text(raw_value), normalized
        ))

    # Name
    text, st = _simple_text(raw.get("name"), 2, 120)
    if st == "valid":
        if text.islower() or text.isupper():
            text = text.title()
        n.name = text
        add("name", st, "OK", raw.get("name"), text)
    else:
        add("name", st, "Name not provided." if st == "missing"
            else "Name must be 2–120 characters and contain letters.", raw.get("name"))

    # Company name
    text = clean_text(raw.get("company_name"))
    if text is None:
        add("company_name", "missing", "Company name not provided.", None)
    elif len(text) < 2 or len(text) > 150 or not any(ch.isalnum() for ch in text):
        add("company_name", "invalid", "Company name must be 2–150 characters.", text)
    else:
        n.company_name = text
        add("company_name", "valid", "OK", text, text)

    # Website
    text = clean_text(raw.get("website"))
    if text is None:
        add("website", "missing", "Website not provided.", None)
    else:
        host = normalize_website(text)
        if host:
            n.website = host
            add("website", "valid", "OK", text, host)
        else:
            add("website", "invalid", "Website is not a valid domain (e.g. example.com).", text)

    # Plain text fields
    for fname, lo, hi, label in (
        ("job_title", 2, 100, "Job title"),
        ("industry", 2, 100, "Industry"),
        ("company_location", 2, 150, "Company location"),
        ("lead_source", 2, 100, "Lead source"),
        ("requirement", 3, 2000, "Requirement"),
    ):
        text, st = _simple_text(raw.get(fname), lo, hi)
        if st == "valid":
            setattr(n, fname, text)
            add(fname, st, "OK", raw.get(fname), text)
        elif st == "missing":
            add(fname, st, f"{label} not provided.", None)
        else:
            add(fname, st, f"{label} must be {lo}–{hi} characters and contain letters.", text)

    # Company size
    text = clean_text(raw.get("company_size"))
    if text is None:
        add("company_size", "missing", "Company size not provided.", None)
    else:
        parsed = parse_company_size(text)
        if parsed:
            n.company_size, n.company_size_value = parsed
            add("company_size", "valid", "OK", text, parsed[0])
        else:
            add("company_size", "invalid",
                "Company size must be a number or range such as 50-100 or 1000+.", text)

    # Email
    text = clean_text(raw.get("email"))
    if text is None:
        add("email", "missing", "Email not provided.", None)
    else:
        email = normalize_email(text)
        if email:
            n.email = email
            add("email", "valid", "OK", text, email)
        else:
            add("email", "invalid", "Email address is not valid.", text)

    # Phone
    text = clean_text(raw.get("phone"))
    if text is None:
        add("phone", "missing", "Phone not provided.", None)
    else:
        phone = normalize_phone(text)
        if phone:
            n.phone = phone
            add("phone", "valid", "OK", text, phone)
        else:
            add("phone", "invalid",
                "Phone number is not valid (use e.g. +91 9876543210).", text)

    reports.sort(key=lambda r: FIELD_ORDER.index(r.field))
    usable = n.status["name"] == "valid" or n.status["company_name"] == "valid"
    report = ValidationReport(
        usable=usable,
        fields=[asdict(r) for r in reports],
        missing=[r.field for r in reports if r.status == "missing"],
        invalid=[r.field for r in reports if r.status == "invalid"],
        messages=[f"{r.label}: {r.message}" for r in reports if r.status != "valid"],
    )
    if not usable:
        report.messages.insert(
            0, "Lead cannot be assessed: a valid contact name or company name is required."
        )
    return n, report


def looks_like_placeholder(value: Optional[str]) -> bool:
    return bool(value) and value.strip().lower() in PLACEHOLDER_VALUES
