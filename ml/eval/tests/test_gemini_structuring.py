"""QA tests for Gemini structuring (ml/ocr/receipt_pipeline.py) and its use by /ocr.
urlopen is always monkeypatched: the real Gemini API is never called."""
import io
import json
import math
import os
import sys

import pytest
from PIL import Image

from conftest import REPO_ROOT

MLDIR = os.path.join(REPO_ROOT, "ml")
if MLDIR not in sys.path:
    sys.path.insert(0, MLDIR)
from ocr import receipt_pipeline as rp  # noqa: E402


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def gemini_body(text):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()


@pytest.fixture
def calls(monkeypatch):
    """Patch urlopen; set calls.reply (bytes) or calls.exc. Records requests."""
    import urllib.request

    class C:
        reqs = []
        reply = gemini_body('{"lines":[],"total":null}')
        exc = None
    c = C()
    c.reqs = []

    def fake(req, timeout=None):
        c.reqs.append(req)
        if c.exc:
            raise c.exc
        return FakeResp(c.reply)
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    return c


# ---------------- _to_num
@pytest.mark.parametrize("v,exp", [
    (3, 3.0), (3.48, 3.48), ("3.48", 3.48), ("$3.48", 3.48), ("1,29", 1.29), (" $ 2.00 ", 2.0),
    ("3.48 USD", 3.48), ("0", 0.0),
])
def test_to_num_ok(v, exp):
    r = rp._to_num(v)
    assert isinstance(r, float) and r == pytest.approx(exp)


@pytest.mark.parametrize("v", [True, False, None, "abc", "", "N/A", [], {}, [1]])
def test_to_num_none(v):
    assert rp._to_num(v) is None


def test_to_num_thousands_separator():
    assert rp._to_num("1,299.50") == pytest.approx(1299.50)


def test_to_num_nan_inf_are_not_usable():
    # NaN/inf would make jsonify emit invalid JSON
    for v in (float("nan"), float("inf"), "nan", "inf"):
        r = rp._to_num(v)
        assert r is None or math.isfinite(r)


# ---------------- clean_structured
def test_clean_structured_strings_to_floats():
    d = rp.clean_structured({"lines": [{"name": " Milk ", "quantity": "2", "price": "$3.48"},
                                       {"name": "Eggs", "quantity": None, "price": "1,29"}],
                             "total": "4.77"})
    assert d == {"lines": [{"name": "Milk", "quantity": 2.0, "price": 3.48},
                           {"name": "Eggs", "quantity": None, "price": 1.29}], "total": 4.77}
    for l in d["lines"]:
        assert all(l[k] is None or type(l[k]) is float for k in ("quantity", "price"))


def test_clean_structured_drops_bad_lines_and_quantities():
    d = rp.clean_structured({"lines": [
        {"name": "", "price": 1}, {"name": "   ", "price": 1}, {"price": 1}, {"name": None},
        "Milk", None, 5, ["Milk"],
        {"name": "A", "quantity": 0, "price": True}, {"name": "B", "quantity": -2, "price": "x"},
        {"name": "C", "quantity": False}], "total": True})
    assert [l["name"] for l in d["lines"]] == ["A", "B", "C"]
    assert all(l["quantity"] is None and l["price"] is None for l in d["lines"])
    assert d["total"] is None


def test_clean_structured_numeric_name():
    assert rp.clean_structured({"lines": [{"name": 7}]})["lines"][0]["name"] == "7"


@pytest.mark.parametrize("bad", [None, [], "x", 3, {"lines": None}, {"lines": "a"}, {"lines": {}}, {}, {"total": 1}])
def test_clean_structured_bad_shape(bad):
    assert rp.clean_structured(bad) is None


def test_clean_structured_empty_lines_ok():
    assert rp.clean_structured({"lines": []}) == {"lines": [], "total": None}


# ---------------- gemini_structure: key / model / failure
def test_no_key_returns_none_without_network(calls, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert rp.gemini_structure("x") is None
    assert calls.reqs == []


def test_model_default_alias(calls):
    rp.gemini_structure("x")
    url = calls.reqs[0].full_url
    assert "/models/gemini-3.8-flash:generateContent" in url
    assert "gemini-2.5-flash" not in url


def test_model_env(calls, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-9-test")
    rp.gemini_structure("x")
    assert "/models/gemini-9-test:generateContent" in calls.reqs[0].full_url


def test_model_empty_env_falls_back(calls, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "")
    rp.gemini_structure("x")
    assert "/models/gemini-3.8-flash:" in calls.reqs[0].full_url


def test_model_argument_beats_env(calls, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "from-env")
    rp.gemini_structure("x", model="from-arg")
    assert "/models/from-arg:" in calls.reqs[0].full_url


def test_key_in_header_not_url(calls):
    rp.gemini_structure("x", api_key="SECRET")
    r = calls.reqs[0]
    assert "SECRET" not in r.full_url
    assert {k.lower(): v for k, v in r.header_items()}["x-goog-api-key"] == "SECRET"


def test_strings_parsed_through_gemini_structure(calls):
    calls.reply = gemini_body(json.dumps({"lines": [{"name": "Milk", "quantity": "1", "price": "$3.48"}],
                                          "total": "3.48"}))
    assert rp.gemini_structure("x") == {"lines": [{"name": "Milk", "quantity": 1.0, "price": 3.48}], "total": 3.48}


@pytest.mark.parametrize("reply", [
    b"not json", b"{}", gemini_body("not json"), gemini_body("[1,2]"), gemini_body('{"lines":"x"}'),
    json.dumps({"candidates": []}).encode(), json.dumps({"error": {"code": 429}}).encode(),
    json.dumps({"candidates": [{"finishReason": "SAFETY"}]}).encode(),
])
def test_garbage_replies_return_none(calls, reply):
    calls.reply = reply
    assert rp.gemini_structure("x") is None


@pytest.mark.parametrize("exc", [OSError("down"), TimeoutError(), ValueError("v")])
def test_network_errors_return_none(calls, exc):
    calls.exc = exc
    assert rp.gemini_structure("x") is None


def test_http_error_returns_none(calls):
    import urllib.error
    calls.exc = urllib.error.HTTPError("u", 404, "model not found", {}, None)
    assert rp.gemini_structure("x") is None


# ---------------- /ocr through the service
class FakeOcr:
    def __init__(self, text):
        self.text = text

    def image_to_text(self, image):
        return self.text


RAW = "MILK 2% 3.48\nEGGS 12CT 4.29\nTOTAL 7.77\n"


def png():
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 30, 30)).save(b, "PNG")
    return b.getvalue()


def post_ocr(gemini=True, text=RAW):
    os.environ.setdefault("DETECTOR_BACKEND", "fake")
    from serve.app import create_app
    from serve.app import detector_from_env
    app = create_app(detector=detector_from_env(), ocr=FakeOcr(text), structure_with_gemini=gemini)
    return app.test_client().post("/ocr", data={"image": (io.BytesIO(png()), "r.png")},
                                  content_type="multipart/form-data")


def test_ocr_numeric_when_gemini_answers_strings(calls):
    calls.reply = gemini_body(json.dumps({"lines": [
        {"name": "MILK 2%", "quantity": "1", "price": "$3.48"},
        {"name": "EGGS 12CT", "quantity": None, "price": "4,29"}], "total": "$7.77"}))
    r = post_ocr()
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert j["total"] == 7.77 and isinstance(j["total"], float)
    assert [l["price"] for l in j["lines"]] == [3.48, 4.29]
    assert all(isinstance(l["price"], float) for l in j["lines"])
    assert j["lines"][0]["quantity"] == 1.0
    assert j["raw_text"] == RAW
    assert len(calls.reqs) == 1


@pytest.mark.parametrize("reply", [b"junk", gemini_body("nope"), gemini_body('{"lines":[]}'),
                                   gemini_body('{"lines":[{"name":""}]}'), gemini_body('{"lines":7}')])
def test_ocr_falls_back_to_deterministic_parser(calls, reply):
    calls.reply = reply
    j = post_ocr().get_json()
    base = rp.parse_receipt_text(RAW)
    assert j["lines"] == [{"name": l["name"], "quantity": l.get("quantity"), "price": l.get("price")}
                          for l in base["lines"]]
    assert j["total"] == base["total"]


def test_ocr_fallback_on_network_error(calls):
    calls.exc = OSError("x")
    j = post_ocr().get_json()
    assert j["total"] == rp.parse_receipt_text(RAW)["total"]


def test_ocr_gemini_disabled_makes_no_request(calls):
    post_ocr(gemini=False)
    assert calls.reqs == []


def test_ocr_request_uses_env_model_and_default(calls, monkeypatch):
    post_ocr()
    assert "/models/gemini-3.8-flash:" in calls.reqs[-1].full_url
    monkeypatch.setenv("GEMINI_MODEL", "gemini-x")
    post_ocr()
    assert "/models/gemini-x:" in calls.reqs[-1].full_url


def test_ocr_gemini_null_total_keeps_parser_total(calls):
    """Gemini says total null but the deterministic parser found one: do not discard it."""
    calls.reply = gemini_body(json.dumps({"lines": [{"name": "MILK", "quantity": 1, "price": 3.48}],
                                          "total": None}))
    j = post_ocr().get_json()
    assert j["total"] == rp.parse_receipt_text(RAW)["total"] == 7.77


def test_ocr_response_is_valid_json_for_nan(calls):
    calls.reply = gemini_body('{"lines":[{"name":"A","price":"nan"}],"total":"inf"}')
    r = post_ocr()
    json.loads(r.get_data(as_text=True), parse_constant=lambda c: pytest.fail("non-JSON constant " + c))


def test_to_num_comma_decimal_and_receipt_function_total(calls):
    assert rp._to_num("1,29") == pytest.approx(1.29)
    assert rp._to_num("-1,299.50") == pytest.approx(-1299.5)
