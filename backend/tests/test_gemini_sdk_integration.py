"""The real ``google-genai`` SDK against a local stand-in HTTP server.

No network and no API key are needed: the SDK is pointed at 127.0.0.1.  This verifies what *our*
code sends (model, JSON mime type, schema, no deprecated sampling parameters) and how it parses
and validates a structured response.  It does NOT prove that Google's live API accepts the schema
-- that needs a real key (see README "Gemini integration status").
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from app.services.gemini_service import (DEFAULT_MODEL, GeminiAnalysis, GeminiError, GeminiService,
                                         SYSTEM_INSTRUCTION)

ROOT = Path(__file__).resolve().parents[2]
GOOD = {"quality_assessment": "A strong HOT lead with a score of 92/100.",
        "scoring_explanation": "The score comes from the deterministic engine.",
        "business_insights": ["Good industry fit"], "recommended_next_action": "Book a demo this week."}
PAYLOAD = {"untrusted_lead_data": {"name": "Rahul"}, "engine_results": {"score": 92.0, "classification": "HOT"}}


class _Server:
    def __init__(self):
        self.status, self.body, self.requests = 200, GOOD, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append({"path": self.path, "body": json.loads(raw)})
                if outer.status != 200:
                    payload = {"error": {"code": outer.status, "message": "x", "status": "ERR"}}
                else:
                    text = outer.body if isinstance(outer.body, str) else json.dumps(outer.body)
                    payload = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]},
                                               "finishReason": "STOP"}]}
                data = json.dumps(payload).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_port}"


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    s = _Server()
    yield s
    s.httpd.shutdown()


def service(server, **kw):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key="test-key", http_options=types.HttpOptions(base_url=server.url))
    return GeminiService(api_key="test-key", client=client, retry_delay=0, **kw)


def test_default_model_is_gemini_3_8_flash(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert DEFAULT_MODEL == "gemini-3.8-flash"
    assert GeminiService(api_key="k").model == "gemini-3.8-flash"
    monkeypatch.setenv("GEMINI_MODEL", "some-other-model")
    assert GeminiService(api_key="k").model == "some-other-model"


def test_structured_json_round_trip_through_the_real_sdk(server):
    result = service(server).analyze(PAYLOAD, 92.0, "HOT")
    assert isinstance(result, GeminiAnalysis) and result.business_insights == ["Good industry fit"]
    req = server.requests[0]
    assert req["path"].endswith("/models/gemini-3.8-flash:generateContent")
    cfg = req["body"]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    schema = cfg.get("responseSchema") or cfg.get("responseJsonSchema")
    assert set(schema["properties"]) == {"quality_assessment", "scoring_explanation", "business_insights",
                                         "recommended_next_action"}
    assert not {"score", "classification"} & set(schema["properties"])
    assert req["body"]["systemInstruction"]["parts"][0]["text"] == SYSTEM_INSTRUCTION
    assert "untrusted_lead_data" in req["body"]["contents"][0]["parts"][0]["text"]


def test_no_deprecated_sampling_parameters_are_sent(server):
    service(server).analyze(PAYLOAD, 92.0, "HOT")
    cfg = server.requests[0]["body"]["generationConfig"]
    assert not {"temperature", "topP", "topK", "top_p", "top_k"} & set(cfg)
    assert "temperature=" not in (ROOT / "backend/app/services/gemini_service.py").read_text()


def test_configured_model_is_used_in_the_request(server):
    service(server, model="gemini-3.8-flash-custom").analyze(PAYLOAD, 92.0, "HOT")
    assert "gemini-3.8-flash-custom:generateContent" in server.requests[0]["path"]


@pytest.mark.parametrize("body", [
    "this is not json",
    json.dumps({**GOOD, "score": 99}),                                   # smuggled key
    json.dumps({"quality_assessment": "only one field present here"}),   # missing fields
    json.dumps({**GOOD, "business_insights": "not a list"}),             # wrong type
    json.dumps({**GOOD, "quality_assessment": "Final score: 12/100 in my view."}),   # contradicts engine
    json.dumps({**GOOD, "scoring_explanation": "I recalculated the score for you."}),
    json.dumps({**GOOD, "quality_assessment": "This is a COLD lead overall."}),
    json.dumps({**GOOD, "quality_assessment": "The email is verified and deliverable, see https://x.io"}),
])
def test_invalid_or_contradictory_responses_are_rejected(server, body):
    server.body = body
    with pytest.raises(GeminiError) as e:
        service(server).analyze(PAYLOAD, 92.0, "HOT")
    assert e.value.kind == "invalid_response"


@pytest.mark.parametrize("status,kind", [(429, "rate_limited"), (404, "api_error"), (403, "api_error"),
                                         (500, "api_error"), (504, "timeout")])
def test_http_errors_map_to_fallback_error_kinds(server, status, kind):
    server.status = status
    with pytest.raises(GeminiError) as e:
        service(server, retries=0).analyze(PAYLOAD, 92.0, "HOT")
    assert e.value.kind == kind


def test_transient_errors_are_retried_once(server):
    server.status = 503
    with pytest.raises(GeminiError):
        service(server, retries=1).analyze(PAYLOAD, 92.0, "HOT")
    assert len(server.requests) == 2


def test_unconfigured_service_never_calls_out():
    for key in ("", "your_gemini_api_key"):
        with pytest.raises(GeminiError) as e:
            GeminiService(api_key=key).analyze(PAYLOAD, 92.0, "HOT")
        assert e.value.kind == "missing_api_key"


# ----------------------------------------------------------------------------- documentation sync
def test_env_example_and_readme_document_the_default_model():
    for rel in (".env.example", "README.md"):
        text = (ROOT / rel).read_text()
        assert "gemini-3.8-flash" in text, rel
        assert "gemini-3.5-flash" not in text, rel
