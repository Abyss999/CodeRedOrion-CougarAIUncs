"""CATEGORY_GUIDE wiring, receipt schema, and the transient-error retry in gemini._generate."""
import json
import logging
import re
from types import SimpleNamespace

import pytest

from app.models import CATEGORIES, FOOD_GROUPS
from app.services import gemini

LOGGER = "app.gemini.usage"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def usage_records():
    lg = logging.getLogger(LOGGER)
    h = _Capture()
    lg.addHandler(h)
    yield h.records
    lg.removeHandler(h)


@pytest.fixture
def gem(app, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "AIzaSy-FAKE")
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    sleeps = []
    monkeypatch.setattr(gemini.time, "sleep", lambda s: sleeps.append(s))
    with app.app_context():
        yield sleeps


class Err(Exception):
    def __init__(self, msg="boom", code=None):
        super().__init__(msg)
        if code is not None:
            self.code = code


def install(monkeypatch, outcomes, capture=None):
    """outcomes: list of exceptions or response texts, consumed one per generate_content call."""
    import google.genai as genai
    calls = []

    class Models:
        def generate_content(self, **kw):
            calls.append(kw)
            o = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
            if isinstance(o, Exception):
                raise o
            return SimpleNamespace(text=o, usage_metadata=SimpleNamespace(
                prompt_token_count=1, candidates_token_count=2, total_token_count=3))

    class Client:
        def __init__(self, **kw):
            self.models = Models()
    monkeypatch.setattr(genai, "Client", Client)
    return calls


def status(recs):
    return [dict(re.findall(r"(\w+)=(\S+)", r.getMessage()))["status"] for r in recs]


@pytest.mark.parametrize("exc", [Err(code=503), Err(code=429), Err(code=504),
                                 Err("503 UNAVAILABLE. high demand"), Err("RESOURCE_EXHAUSTED quota"),
                                 Err("DEADLINE_EXCEEDED")])
def test_transient_retried_once_then_ok(gem, monkeypatch, usage_records, exc):
    calls = install(monkeypatch, [exc, '[{"name": "Milk"}]'])
    assert gemini.parse_text("milk") == [{"name": "Milk"}]
    assert len(calls) == 2 and gem == list(gemini.RETRY_DELAYS_S)
    assert status(usage_records) == ["ok"]


@pytest.mark.parametrize("exc", [Err(code=503), Err("UNAVAILABLE")])
def test_two_transient_failures_upstream_error(gem, monkeypatch, usage_records, exc):
    calls = install(monkeypatch, [exc, exc])
    with pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert len(calls) == 2
    assert status(usage_records) == ["error"]


@pytest.mark.parametrize("exc", [Err(code=400), Err("INVALID_ARGUMENT bad"), Err(code=500), ValueError("x")])
def test_non_transient_not_retried(gem, monkeypatch, usage_records, exc):
    calls = install(monkeypatch, [exc, '[]'])
    with pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert len(calls) == 1 and gem == []
    assert status(usage_records) == ["error"]


def test_success_first_try_no_sleep(gem, monkeypatch, usage_records):
    calls = install(monkeypatch, ['[]'])
    assert gemini.parse_text("x") == []
    assert len(calls) == 1 and gem == [] and status(usage_records) == ["ok"]


def test_retry_then_bad_json_is_error_single_line(gem, monkeypatch, usage_records):
    install(monkeypatch, [Err(code=503), "not json"])
    with pytest.raises(gemini.UpstreamError):
        gemini.parse_text("x")
    assert status(usage_records) == ["error"]


def test_retry_delays_is_single_short_wait():
    assert len(gemini.RETRY_DELAYS_S) == 1 and 0 < gemini.RETRY_DELAYS_S[0] <= 5


def test_is_transient_unit():
    assert gemini._is_transient(Err(code=503)) and gemini._is_transient(Err("x UNAVAILABLE"))
    assert not gemini._is_transient(Err("nope")) and not gemini._is_transient(Err(code=404))


# ---------- CATEGORY_GUIDE / schema ----------------------------------------------------------
def test_guide_content():
    g = gemini.CATEGORY_GUIDE
    for w in ("produce_leafy", "produce_hardy", "bananas", "apples", "SHORT", "LONG"):
        assert w in g
    for c in CATEGORIES:
        assert c in g


def test_guide_in_all_three_prompts(gem, monkeypatch):
    calls = install(monkeypatch, ['[]', '[]', '[{"display_name":"a"}]'])
    gemini.parse_text("x")
    gemini.detect_from_image(b"\xff\xd8", "image/jpeg", "fridge")
    gemini.categorize_receipt_lines(["A"])
    assert len(calls) == 3
    for kw in calls:
        assert kw["config"].system_instruction.startswith(gemini.CATEGORY_GUIDE)


def test_receipt_schema_enums_and_passed(gem, monkeypatch):
    calls = install(monkeypatch, ['[{"display_name":"a","category":"dairy","food_group":"dairy","storage":"fridge"}]'])
    gemini.categorize_receipt_lines(["A"])
    props = gemini._RECEIPT_SCHEMA["items"]["properties"]
    assert props["category"]["enum"] == list(CATEGORIES)
    assert props["food_group"]["enum"] == list(FOOD_GROUPS)
    assert props["storage"]["enum"] == ["fridge", "pantry", "freezer"]
    assert calls[0]["config"].response_schema is not None
    assert json.loads(calls[0]["contents"]) == ["A"]


def test_categorize_pads_truncates_and_cleans(gem, monkeypatch):
    install(monkeypatch, ['[{"display_name":"a"}, 5]'])
    out = gemini.categorize_receipt_lines(["A", "B", "C"])
    assert out == [{"display_name": "a"}, {}, {}]
    install(monkeypatch, ['{"items":[{"display_name":"a"},{"display_name":"b"}]}'])
    assert gemini.categorize_receipt_lines(["A"]) == [{"display_name": "a"}]
