"""Identical inputs => identical scores; Gemini can never influence the numbers."""
import inspect
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import ScoringConfig
from app.services import scoring_engine
from app.services.lead_validator import validate_and_normalize
from app.services.scoring_engine import score_lead
from tests.conftest import SAMPLE, FakeGemini, submit_and_assess

CFG = ScoringConfig().validate()
BACKEND = Path(__file__).resolve().parent.parent

LEADS = [
    SAMPLE,
    {**SAMPLE, "requirement": "We don't need a CRM", "job_title": "Student"},
    {"name": "Asha", "requirement": "Need CRM", "email": "bad"},
    {**SAMPLE, "industry": "Agriculture", "company_size": "1-10", "lead_source": "Cold call"},
    {"company_name": "Nova", "website": "x y", "phone": "123", "requirement": "Looking for fleet software"},
]


def fingerprint(lead):
    n, _ = validate_and_normalize(lead)
    r = score_lead(n, CFG)
    return json.dumps([r.final_score, r.classification, [(p.key, p.score, p.explanation) for p in r.parameters],
                       r.positives, r.negatives, r.calculation])


@pytest.mark.parametrize("lead", LEADS)
def test_repeated_runs_are_identical(lead):
    assert len({fingerprint(lead) for _ in range(50)}) == 1


def test_field_order_whitespace_case_and_formatting_do_not_matter():
    shuffled = dict(random.Random(7).sample(sorted(SAMPLE.items()), len(SAMPLE)))
    variant = {k: f"  {v.upper()}  " if k in ("industry", "job_title", "lead_source") else v
               for k, v in shuffled.items()}
    variant["email"], variant["phone"], variant["website"] = " RAHUL@Example.COM ", "98765 43210", "HTTP://WWW.ABCTECHNOLOGIES.COM/"
    variant["company_size"] = "50 to 100 employees"
    a, b = score_lead(validate_and_normalize(SAMPLE)[0], CFG), score_lead(validate_and_normalize(variant)[0], CFG)
    assert a.final_score == b.final_score == 93.0
    assert [p.score for p in a.parameters] == [p.score for p in b.parameters]


def test_identical_across_processes_and_hash_seeds():
    code = ("import json,sys; sys.path.insert(0,'.');"
            "from tests.test_determinism_and_gemini_isolation import fingerprint, LEADS;"
            "print(json.dumps([fingerprint(l) for l in LEADS]))")
    outs = []
    for seed in ("1", "2", "random"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "GEMINI_API_KEY": ""}
        outs.append(subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True,
                                   text=True, check=True).stdout)
    assert outs[0] == outs[1] == outs[2]


def test_identical_submissions_get_identical_assessments(client):
    results = [submit_and_assess(client, SAMPLE)[1] for _ in range(3)]
    keys = ("score", "classification", "confidence_level", "confidence_score", "positive_factors",
            "negative_factors", "scoring_explanation")
    assert all({k: r[k] for k in keys} == {k: results[0][k] for k in keys} for r in results)
    assert all([b["score"] for b in r["breakdown"]] == [20, 19, 15, 10, 9, 10, 10] for r in results)


# --- Gemini cannot influence the score ------------------------------------------------------
def _imports(module):
    import ast
    names = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(("." * node.level) + (node.module or ""))
            names |= {a.name for a in node.names}
    return names


@pytest.mark.parametrize("module", ["scoring_engine", "intent", "confidence", "lead_validator", "narrative"])
def test_deterministic_modules_do_not_import_gemini_or_network_libraries(module):
    mod = __import__(f"app.services.{module}", fromlist=["x"])
    forbidden = ("gemini", "genai", "google", "httpx", "requests", "urllib", "socket", "random")
    bad = [n for n in _imports(mod) if any(f in n.lower() for f in forbidden)]
    assert bad == [], bad


@pytest.mark.parametrize("lead", LEADS)
@pytest.mark.parametrize("mode", ["ok", "error", "rate_limited", "invalid", "lying", "mutate"])
def test_score_is_identical_whatever_gemini_does(client, gemini, lead, mode):
    gemini.mode = mode
    n, _ = validate_and_normalize(lead)
    expected = score_lead(n, CFG)
    _, a = submit_and_assess(client, lead)
    assert a["score"] == expected.final_score and a["classification"] == expected.classification
    assert [b["score"] for b in a["breakdown"]] == [p.score for p in expected.parameters]
    assert a["positive_factors"] == expected.positives and a["negative_factors"] == expected.negatives
    assert gemini.calls == 1


def test_score_is_identical_with_and_without_gemini(client, gemini):
    from app.main import app
    from app.services.gemini_service import GeminiService, get_gemini_service
    _, with_ai = submit_and_assess(client, SAMPLE)
    app.dependency_overrides[get_gemini_service] = lambda: GeminiService(api_key="")
    _, without = submit_and_assess(client, SAMPLE)
    assert with_ai["explanation_source"] == "gemini" and without["explanation_source"] == "rule_based"
    assert with_ai["score"] == without["score"] and with_ai["classification"] == without["classification"]


def test_gemini_receives_a_copy_and_cannot_edit_the_persisted_result(client, gemini):
    gemini.mode = "mutate"            # FakeGemini scribbles over the payload it receives
    _, a = submit_and_assess(client, SAMPLE)
    assert gemini.seen["engine_results"]["score"] == 0            # the fake really did tamper with its copy
    assert a["score"] == 93.0 and a["classification"] == "HOT"
    stored = client.get(f"/api/leads/{a['lead_id']}/assessment").json()
    assert stored["score"] == 93.0 and stored["breakdown"][1]["score"] == 19.0
    assert stored["config_snapshot"]["hot_threshold"] == 75


def test_gemini_text_is_stored_separately_from_numbers(client):
    _, a = submit_and_assess(client, SAMPLE)
    assert a["explanation_source"] == "gemini"
    assert a["scoring_explanation"].endswith("→ HOT (HOT ≥ 75, WARM ≥ 50, COLD below)")   # deterministic text
    assert "Final Score = 20 + 19 + 15 + 10 + 9 + 10 + 10 = 93" in a["scoring_explanation"]
