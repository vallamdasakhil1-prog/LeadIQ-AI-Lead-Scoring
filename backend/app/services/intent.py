"""Negation-aware purchase-intent analysis (pure and deterministic; no LLM).

A buying phrase counts as a positive signal only if it is *not negated*.  A phrase is
negated when a negation cue ("not", "no", "don't", "never", "without", ...) appears within
``intent_negation_window`` tokens before it **in the same clause**.  Clauses are split on
punctuation and on contrast words ("but", "however", ...), so "Not looking for ERP, but need
a CRM" keeps "need" affirmed.

Policy (documented in docs/SCORING_METHODOLOGY.md):
* Solution keywords (crm, erp, ...) are never negated: naming a product is neutral.
* Negated buying phrases ("not looking for", "don't need", "no purchase") are NOT counted as
  buying signals.  If a negated buying phrase exists and no affirmed buying phrase does, the
  requirement has *negative intent* and the parameter is capped.
* Explicit non-purchase indicators ("student", "college project", "just browsing") also cap it,
  unless they are themselves negated ("I am not a student").
* Negated timeline/budget cues ("no budget") only remove the timeline credit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import ScoringConfig

_CLAUSE_SPLIT = re.compile(
    r"[.;:!?\n()\[\]]+|,|\b(?:but|however|although|though|yet|except|whereas)\b"
)
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)*")
_NEGATION_WORDS = {"not", "no", "never", "without", "neither", "nor", "cannot", "none", "nothing"}
_NOT_A_NEGATION_BEFORE = {"only", "just", "doubt"}  # "not only ...", "not just ...", "no doubt"


def _normalise(text: str) -> str:
    return text.lower().replace("’", "'").replace("‘", "'").replace("`", "'")


def _tokens(text: str) -> list:
    return _TOKEN.findall(_normalise(text))


def _is_cue(tokens: list, i: int) -> bool:
    t = tokens[i]
    if t in _NEGATION_WORDS or t.endswith("n't"):
        if t in ("not", "no") and i + 1 < len(tokens) and tokens[i + 1] in _NOT_A_NEGATION_BEFORE:
            return False
        return True
    return False


def _occurrences(tokens: list, phrase: str) -> list:
    p = _tokens(phrase)
    if not p:
        return []
    return [i for i in range(len(tokens) - len(p) + 1) if tokens[i:i + len(p)] == p]


def _negation_cue(tokens: list, start: int, window: int):
    """Index of the nearest negation cue within ``window`` tokens before ``start`` (or None)."""
    for j in range(start - 1, max(-1, start - window - 1), -1):
        if _is_cue(tokens, j):
            return j
    return None


@dataclass
class IntentAnalysis:
    solution: list = field(default_factory=list)          # named products (never negated)
    buying: list = field(default_factory=list)            # affirmed buying phrases
    timeline: list = field(default_factory=list)          # affirmed timeline/budget cues
    negated: list = field(default_factory=list)           # evidence such as "do not need"
    timeline_negated: list = field(default_factory=list)  # e.g. "no budget"
    negative: list = field(default_factory=list)          # student / college project / just browsing
    words: int = 0

    @property
    def negative_intent(self) -> bool:
        return bool(self.negative) or (bool(self.negated) and not self.buying)

    @property
    def mixed_signals(self) -> bool:
        return bool(self.negated) and bool(self.buying) and not self.negative


def analyse_intent(text: str, cfg: ScoringConfig) -> IntentAnalysis:
    a = IntentAnalysis(words=len(re.findall(r"[A-Za-z0-9]+", text)))
    window = cfg.intent_negation_window

    def add(bucket: list, value: str) -> None:
        if value not in bucket:
            bucket.append(value)

    for clause in _CLAUSE_SPLIT.split(_normalise(text)):
        tokens = _tokens(clause)
        if not tokens:
            continue
        for phrase in cfg.intent_solution_keywords:
            if _occurrences(tokens, phrase):
                add(a.solution, phrase)
        for phrase in cfg.intent_buying_keywords:
            for i in _occurrences(tokens, phrase):
                cue = _negation_cue(tokens, i, window)
                if cue is None:
                    add(a.buying, phrase)
                else:
                    add(a.negated, " ".join(tokens[cue:i + len(_tokens(phrase))]))
        for phrase in cfg.intent_negation_targets:  # nouns/verbs such as "requirement", "purchase"
            for i in _occurrences(tokens, phrase):
                cue = _negation_cue(tokens, i, window)
                if cue is not None:
                    add(a.negated, " ".join(tokens[cue:i + len(_tokens(phrase))]))
        for phrase in cfg.intent_timeline_keywords:
            for i in _occurrences(tokens, phrase):
                cue = _negation_cue(tokens, i, window)
                if cue is None:
                    add(a.timeline, phrase)
                else:
                    add(a.timeline_negated, " ".join(tokens[cue:i + len(_tokens(phrase))]))
        for phrase in cfg.intent_negative_keywords:
            for i in _occurrences(tokens, phrase):
                if _negation_cue(tokens, i, window) is None:
                    add(a.negative, phrase)
    return a
