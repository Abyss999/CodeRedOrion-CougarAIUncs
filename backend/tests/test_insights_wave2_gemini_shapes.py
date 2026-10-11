"""BE-13 (fixed at the root in backend PR 2): Gemini returning a valid-JSON scalar (null, string,
number, bool), or a non-list under the expected key, is an upstream error. It logs exactly one
`gemini_usage ... status=error` line, surfaces as 502 `upstream_unavailable` on the AI endpoints
(never a 500), and POST /items falls back to the default shelf-life table.

Gemini is stubbed at `google.genai.Client`, so the real `_generate` / `_as_list` / `_unwrap` run."""
import io
import json
import logging
import re
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from conftest import items_of

LOGGER = "app.gemini.usage"
SCALARS = ["null", '"oops"', '""', "42", "0", "3.5", "-1", "true", "false"]
KEYS = {"parse_text": "items", "detect": "candidates", "recipes": "recipes", "shelf_life": "days"}
NON_LISTS = ["null", '"x"', "7", "true", '{"a": 1}']


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def usage(app, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "fake-key-for-tests")
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    lg = logging.getLogger(LOGGER)
    h = _Capture()
    lg.addHandler(h)
    yield h.records
    lg.removeHandler(h)


@pytest.fixture
def reply(monkeypatch):
    """reply(text): every generate_content call returns `text`. Returns the list of calls."""
    import google.genai as genai

    calls = []

    def install(text):
        class Models:
            def generate_content(self, **kw):
                calls.append(kw)
                return SimpleNamespace(text=text, usage_metadata=SimpleNamespace(
                    prompt_token_count=10, candidates_token_count=2, total_token_count=12))

        class Client:
            def __init__(self, api_key=None, **kw):
                self.models = Models()

        monkeypatch.setattr(genai, "Client", Client)
        return calls

    return install


def kv(rec):
    return dict(re.findall(r"(\w+)=(\S+)", rec.getMessage()))


def one_error_line(records, purpose):
    assert len(records) == 1, [r.getMessage() for r in records]
    d = kv(records[0])
    assert d["status"] == "error" and d["purpose"] == purpose, d
    assert d["input_tokens"] == "10"  # usage still read from the response that came back


def assert_502(r):
    assert r.status_code == 502, r.get_data(as_text=True)
    body = r.get_json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}, body
    assert body["error"]["code"] == "upstream_unavailable" and body["error"]["message"]


# ---- callers --------------------------------------------------------------------------------------
def call_parse(client, user, make_item):
    return client.post("/items/parse-text", json={"text": "2 milk"}, headers=user["headers"])


def call_detect(client, user, make_item):
    return client.post("/items/from-photo", data={"image": (io.BytesIO(b"\xff\xd8fakejpeg"), "a.jpg")},
                       content_type="multipart/form-data", headers=user["headers"])


def call_recipes(client, user, make_item):
    make_item(user, name="Milk", predicted_expiry=(date.today() + timedelta(days=2)).isoformat())
    return client.post("/recipes/suggest", json={}, headers=user["headers"])


ENDPOINTS = [("parse_text", call_parse), ("detect", call_detect), ("recipes", call_recipes)]


@pytest.mark.parametrize("raw", SCALARS)
@pytest.mark.parametrize("purpose,call", ENDPOINTS, ids=[e[0] for e in ENDPOINTS])
def test_scalar_response_is_502_with_one_error_line(client, user, make_item, usage, reply, purpose, call, raw):
    reply(raw)
    r = call(client, user, make_item)
    assert_502(r)
    one_error_line(usage, purpose)


@pytest.mark.parametrize("inner", NON_LISTS)
@pytest.mark.parametrize("purpose,call", ENDPOINTS, ids=[e[0] for e in ENDPOINTS])
def test_non_list_under_key_is_502(client, user, make_item, usage, reply, purpose, call, inner):
    reply('{"%s": %s}' % (KEYS[purpose], inner))
    assert_502(call(client, user, make_item))
    one_error_line(usage, purpose)


@pytest.mark.parametrize("purpose,call", ENDPOINTS, ids=[e[0] for e in ENDPOINTS])
def test_invalid_json_is_502(client, user, make_item, usage, reply, purpose, call):
    reply("not json {")
    assert_502(call(client, user, make_item))
    one_error_line(usage, purpose)


# ---- shapes that are still fine -------------------------------------------------------------------
def test_wrapped_and_bare_lists_ok(client, user, make_item, usage, reply):
    reply('{"items": [{"name": "Milk", "category": "dairy"}]}')
    r = call_parse(client, user, make_item)
    assert r.status_code == 200 and [c["name"] for c in r.get_json()["candidates"]] == ["Milk"]
    reply('[{"name": "Eggs", "category": "eggs"}]')
    r = call_parse(client, user, make_item)
    assert r.status_code == 200 and [c["name"] for c in r.get_json()["candidates"]] == ["Eggs"]
    assert [kv(x)["status"] for x in usage] == ["ok", "ok"]


@pytest.mark.parametrize("purpose,call,field", [("parse_text", call_parse, "candidates"),
                                                ("detect", call_detect, "candidates"),
                                                ("recipes", call_recipes, "recipes")])
def test_object_without_the_key_means_nothing_found(client, user, make_item, usage, reply, purpose, call, field):
    """API contract (gemini._as_list): a missing key is "nothing found" -> [] and status=ok."""
    reply('{"something_else": [1, 2]}')
    r = call(client, user, make_item)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()[field] == []
    assert len(usage) == 1 and kv(usage[0])["status"] == "ok"


def test_502_recipes_not_cached(client, user, make_item, usage, reply):
    calls = reply("null")
    assert_502(call_recipes(client, user, make_item))
    reply('[{"title": "Soup", "minutes": 5, "servings": 2, "uses_items": ["Milk"], "missing_items": [], "steps": []}]')
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 200 and r.get_json()["recipes"][0]["title"] == "Soup"


# ---- POST /items: shelf-life falls back to the default table --------------------------------------
@pytest.mark.parametrize("raw", SCALARS + ['{"days": %s}' % x for x in NON_LISTS] + ["not json {"])
def test_create_falls_back_to_default_shelf_life(client, user, sql, usage, reply, raw):
    from app.services import expiry

    reply(raw)
    r = client.post("/items", json={"items": [{"name": "Milk", "category": "dairy", "storage": "fridge"},
                                              {"name": "Rice", "category": "pantry_dry", "storage": "pantry"}]},
                    headers=user["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)
    got = items_of(r)
    for it, (cat, st) in zip(got, (("dairy", "fridge"), ("pantry_dry", "pantry"))):
        want_date, want_src = expiry.predict(cat, st)
        assert it["expiry_source"] == want_src == "default"
        assert it["predicted_expiry"] == want_date.isoformat()
    one_error_line(usage, "shelf_life")
    assert sql("SELECT count(*) AS n FROM food_events WHERE event_type='add'")[0]["n"] == 2


def test_create_uses_gemini_days_when_shape_ok(client, user, usage, reply):
    for raw in ('[5, 400]', '{"days": [5, 400]}'):
        reply(raw)
        r = client.post("/items", json={"items": [{"name": "Milk"}, {"name": "Rice"}]}, headers=user["headers"])
        assert r.status_code == 201
        a, b = items_of(r)
        assert a["expiry_source"] == "gemini" and a["predicted_expiry"] == (date.today() + timedelta(days=5)).isoformat()
        assert b["expiry_source"] == "gemini"
    assert [kv(x)["status"] for x in usage] == ["ok", "ok"]


# ---- service level: each helper raises UpstreamError, never TypeError/AttributeError -------------
@pytest.mark.parametrize("raw", SCALARS + ["not json {"])
@pytest.mark.parametrize("helper", ["parse_text", "detect_from_image", "suggest_recipes", "estimate_shelf_life"])
def test_helpers_raise_upstream_error(app, usage, reply, helper, raw):
    from app.services import gemini

    reply(raw)
    args = {"parse_text": ("milk",), "detect_from_image": (b"img", "image/jpeg", "fridge"),
            "suggest_recipes": ([{"name": "Milk"}], 2, []), "estimate_shelf_life": ([{"name": "Milk"}],)}[helper]
    with app.app_context():
        with pytest.raises(gemini.UpstreamError):
            getattr(gemini, helper)(*args)
    assert len(usage) == 1 and kv(usage[0])["status"] == "error"
