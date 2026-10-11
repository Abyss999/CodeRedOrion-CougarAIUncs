"""Gemini usage line carries the upstream HTTP status: `status=error code=429`, `code=null`, `code=200` on success."""
import logging
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.services import gemini, ml  # noqa: F401  (ml: keep import order stable with sibling tests)

LOGGER = "app.gemini.usage"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


@pytest.fixture
def lines():
    lg = logging.getLogger(LOGGER)
    h = _Capture()
    lg.addHandler(h)
    yield h.messages
    lg.removeHandler(h)


@pytest.fixture
def gem(app, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "fake-key-for-tests")
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setattr(gemini, "RETRY_DELAYS_S", ())  # no sleeping on transient errors
    with app.app_context():
        yield


def _resp(message, status):
    """Stand-in for the SDK's replay response (the error classes read `body_segments[0]['error']`)."""
    return SimpleNamespace(body_segments=[{"error": {"message": message, "status": status}}])


def _client(monkeypatch, *, raises=None, text='[{"name": "Milk"}]'):
    import google.genai as genai

    class Models:
        def generate_content(self, **kw):
            if raises:
                raise raises
            return SimpleNamespace(text=text, usage_metadata=None)

    class Client:
        def __init__(self, api_key=None, **kw):
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)


def test_client_error_429_logs_code(gem, monkeypatch, lines):
    _client(monkeypatch, raises=errors.ClientError(429, _resp("quota", "RESOURCE_EXHAUSTED")))
    with pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert len(lines) == 1 and lines[0].endswith("status=error code=429"), lines


def test_server_error_503_logs_code(gem, monkeypatch, lines):
    _client(monkeypatch, raises=errors.ServerError(503, _resp("busy", "UNAVAILABLE")))
    with pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert len(lines) == 1 and lines[0].endswith("status=error code=503"), lines


def test_plain_exception_logs_code_null(gem, monkeypatch, lines):
    _client(monkeypatch, raises=TimeoutError("read timed out"))
    with pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert len(lines) == 1 and lines[0].endswith("status=error code=null"), lines


def test_bad_json_logs_code_null(gem, monkeypatch, lines):
    _client(monkeypatch, text="not json")
    with pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert len(lines) == 1 and lines[0].endswith("status=error code=null"), lines


def test_success_logs_code_200(gem, monkeypatch, lines):
    _client(monkeypatch)
    assert gemini.parse_text("milk") == [{"name": "Milk"}]
    assert len(lines) == 1 and lines[0].endswith("status=ok code=200"), lines


def test_cost_script_still_parses_code_field():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "gemini_cost.py"
    spec = importlib.util.spec_from_file_location("gemini_cost", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = list(mod.parse([
        "x gemini_usage model=m purpose=p input_tokens=1 output_tokens=2 total_tokens=3 latency_ms=9 status=error code=429",
        "x gemini_usage model=m purpose=p input_tokens=null output_tokens=null total_tokens=null latency_ms=9 status=error code=null",
    ]))
    assert [r["status"] for r in rows] == ["error", "error"] and rows[0]["code"] == "429"
