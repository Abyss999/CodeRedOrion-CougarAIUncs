"""PR #54 (feat/receipt-gemini-link) backend QA: POST /items/from-receipt with Gemini categorisation,
the heuristic fallback, receipt number parsing, total handling, and the transient-error retry in
services/gemini._generate. Gemini is stubbed at google.genai.Client (or at
gemini.categorize_receipt_lines); the ML service at ml.ocr. Nothing touches the network."""
import io
import json
import logging
import re
from types import SimpleNamespace

import pytest
import requests as real_requests

from app.services import candidates, gemini, ml


def _tiny_jpeg():  # a real 8x8 JPEG: uploads are now validated as images before any backend runs
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 60, 60)).save(buf, "JPEG")
    return buf.getvalue()


TINY_JPEG = _tiny_jpeg()

LOGGER = "app.gemini.usage"
FAKE_KEY = "test-gemini-key-not-real"


# ---------- fixtures / helpers ---------------------------------------------------------------
@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call attempted in test")
    monkeypatch.setattr(real_requests, "get", boom)
    monkeypatch.setattr(real_requests, "post", boom)


@pytest.fixture
def sleeps(monkeypatch):
    """Record retry back-off sleeps instead of waiting 1.5 s."""
    calls = []
    monkeypatch.setattr(gemini.time, "sleep", lambda s: calls.append(s))
    return calls


@pytest.fixture
def usage_records():
    lg = logging.getLogger(LOGGER)  # propagate=False, so attach our own handler

    class H(logging.Handler):
        def __init__(self):
            super().__init__(logging.DEBUG)
            self.records = []

        def emit(self, record):
            self.records.append(record)

    h = H()
    lg.addHandler(h)
    yield h.records
    lg.removeHandler(h)


@pytest.fixture
def gem_on(app, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")


@pytest.fixture
def ml_on(app, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")


def _kv(rec):
    return dict(re.findall(r"(\w+)=(\S+)", rec.getMessage()))


def img():
    return {"image": (io.BytesIO(TINY_JPEG), "r.jpg", "image/jpeg")}


def post_receipt(client, user, **kw):
    return client.post("/items/from-receipt", data=kw.pop("data", None) or img(), headers=user["headers"],
                       content_type="multipart/form-data", **kw)


def set_ocr(monkeypatch, lines, total=None, **extra):
    monkeypatch.setattr(ml, "ocr", lambda *a, **k: {"lines": lines, "total": total, **extra})


def api_error(code: int, status: str, message: str = "x"):
    """A real google.genai APIError built from a requests.Response, as the SDK raises it."""
    from google.genai import errors

    r = real_requests.models.Response()
    r.status_code = code
    r._content = json.dumps({"error": {"code": code, "message": message, "status": status}}).encode()
    r.headers["Content-Type"] = "application/json"
    return (errors.ClientError if code < 500 else errors.ServerError)(code, r)


class FakeGenai:
    """Stands in for google.genai.Client. `script` is consumed one entry per generate_content call:
    an Exception is raised, a str is returned as resp.text."""

    def __init__(self, monkeypatch, script):
        import google.genai as genai

        self.script = list(script)
        self.calls = []
        fake = self

        class Models:
            def generate_content(self, **kw):
                fake.calls.append(kw)
                step = fake.script.pop(0) if fake.script else AssertionError("unexpected extra call")
                if isinstance(step, BaseException):
                    raise step
                return SimpleNamespace(text=step, usage_metadata=SimpleNamespace(
                    prompt_token_count=10, candidates_token_count=5, total_token_count=15))

        class Client:
            def __init__(self, api_key=None, **k):
                self.models = Models()

        monkeypatch.setattr(genai, "Client", Client)


ENRICHED = [
    {"display_name": "2% milk", "category": "dairy", "food_group": "dairy", "storage": "fridge"},
    {"display_name": "Chicken breast", "category": "meat", "food_group": "protein", "storage": "freezer"},
    {"display_name": "Bananas", "category": "produce_leafy", "food_group": "fruit", "storage": "pantry"},
]
LINES = [{"name": "GV 2% MLK GAL", "quantity": 1, "price": 3.48},
         {"name": "CHKN BRST", "quantity": 2, "price": "$7.99"},
         {"name": "BANANAS", "quantity": None, "price": 0.73}]


# ---------- 1. Gemini categorises ------------------------------------------------------------
def test_gemini_categories_used_end_to_end(app, client, user, monkeypatch, gem_on, ml_on, usage_records):
    fake = FakeGenai(monkeypatch, [json.dumps(ENRICHED)])
    set_ocr(monkeypatch, LINES, total=12.20)
    r = post_receipt(client, user)
    assert r.status_code == 200, r.get_data(as_text=True)
    b = r.get_json()
    assert b["categorized_by"] == "gemini"
    assert len(fake.calls) == 1  # one call per receipt
    assert json.loads(fake.calls[0]["contents"]) == ["GV 2% MLK GAL", "CHKN BRST", "BANANAS"]
    got = [(c["name"], c["category"], c["food_group"], c["storage"], c["receipt_text"]) for c in b["candidates"]]
    assert got == [("2% milk", "dairy", "dairy", "fridge", "GV 2% MLK GAL"),
                   ("Chicken breast", "meat", "protein", "freezer", "CHKN BRST"),
                   ("Bananas", "produce_leafy", "fruit", "pantry", "BANANAS")]
    c = b["candidates"][1]
    assert c["price"] == c["est_price"] == 7.99 and c["quantity"] == 2.0
    assert b["candidates"][2]["quantity"] == 1.0
    for c in b["candidates"]:
        for k in ("predicted_expiry", "expiry_source", "unit"):
            assert c[k]
    assert len(usage_records) == 1 and _kv(usage_records[0])["purpose"] == "receipt_categorize"
    assert _kv(usage_records[0])["status"] == "ok"


def test_gemini_candidates_post_back_to_items(app, client, user, monkeypatch, gem_on, ml_on):
    FakeGenai(monkeypatch, [json.dumps(ENRICHED)])
    set_ocr(monkeypatch, LINES, total=12.20)
    cands = post_receipt(client, user).get_json()["candidates"]
    r = client.post("/items", json={"items": [dict(c, source="receipt") for c in cands]}, headers=user["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)


def test_gemini_stubbed_at_service_boundary(client, user, monkeypatch, ml_on):
    seen = []
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "categorize_receipt_lines", lambda names: seen.append(names) or ENRICHED[:2])
    set_ocr(monkeypatch, LINES[:2])
    b = post_receipt(client, user).get_json()
    assert seen == [["GV 2% MLK GAL", "CHKN BRST"]]
    assert b["categorized_by"] == "gemini" and [c["category"] for c in b["candidates"]] == ["dairy", "meat"]


def test_gemini_invalid_fields_fall_back_per_line(client, user, monkeypatch, gem_on, ml_on):
    bad = [{"display_name": "", "category": "dairy", "food_group": "dairy", "storage": "fridge"},
           {"display_name": "Chicken", "category": "NOT_A_CATEGORY", "food_group": "nope", "storage": "attic"}]
    monkeypatch.setattr(gemini, "categorize_receipt_lines", lambda names: bad)
    set_ocr(monkeypatch, LINES[:2])
    b = post_receipt(client, user).get_json()
    c0, c1 = b["candidates"]
    assert c0["name"] == "GV 2% MLK GAL"  # empty display_name keeps the printed name
    assert c1["category"] == candidates.category_from_name("CHKN BRST") == "meat"
    assert c1["food_group"] == "protein" and c1["storage"] in ("fridge", "pantry", "freezer")


def test_gemini_short_answer_padded(client, user, monkeypatch, gem_on, ml_on):
    FakeGenai(monkeypatch, [json.dumps(ENRICHED[:1])])
    set_ocr(monkeypatch, LINES)
    b = post_receipt(client, user).get_json()
    assert [c["name"] for c in b["candidates"]] == ["2% milk", "CHKN BRST", "BANANAS"]


def test_gemini_long_display_name_capped(client, user, monkeypatch, gem_on, ml_on):
    FakeGenai(monkeypatch, [json.dumps([dict(ENRICHED[0], display_name="M" * 500)])])
    set_ocr(monkeypatch, LINES[:1])
    assert len(post_receipt(client, user).get_json()["candidates"][0]["name"]) == 120


def test_no_gemini_call_without_lines(client, user, monkeypatch, gem_on, ml_on):
    fake = FakeGenai(monkeypatch, [])
    set_ocr(monkeypatch, [{"name": "  "}, "junk", {"price": 1}], total=0)
    b = post_receipt(client, user).get_json()
    assert b == {"candidates": [], "total": 0.0, "categorized_by": "heuristic", "source": "ocr"} and fake.calls == []


# ---------- 2. Gemini fails -> heuristic -----------------------------------------------------
@pytest.mark.parametrize("failure", [
    api_error(400, "INVALID_ARGUMENT"), api_error(403, "PERMISSION_DENIED"),
    api_error(500, "INTERNAL"), RuntimeError("socket closed"), "not json at all",
])
def test_gemini_failure_falls_back_to_heuristic(client, user, monkeypatch, gem_on, ml_on, sleeps, failure):
    FakeGenai(monkeypatch, [failure])
    set_ocr(monkeypatch, LINES, total="12.20")
    r = post_receipt(client, user)
    assert r.status_code == 200, r.get_data(as_text=True)
    b = r.get_json()
    assert b["categorized_by"] == "heuristic" and b["total"] == 12.20
    assert [(c["name"], c["category"]) for c in b["candidates"]] == [
        ("GV 2% MLK GAL", "dairy"), ("CHKN BRST", "meat"), ("BANANAS", "produce_leafy")]
    assert all(c["receipt_text"] == c["name"] for c in b["candidates"])


def test_gemini_retry_exhausted_falls_back(client, user, monkeypatch, gem_on, ml_on, sleeps, usage_records):
    fake = FakeGenai(monkeypatch, [api_error(503, "UNAVAILABLE"), api_error(503, "UNAVAILABLE")])
    set_ocr(monkeypatch, LINES)
    b = post_receipt(client, user).get_json()
    assert b["categorized_by"] == "heuristic" and len(fake.calls) == 2 and sleeps == [1.5]
    assert len(usage_records) == 1 and _kv(usage_records[0])["status"] == "error"


def test_upstream_error_at_service_boundary(client, user, monkeypatch, ml_on):
    def boom(names):
        raise gemini.UpstreamError("down")
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "categorize_receipt_lines", boom)
    set_ocr(monkeypatch, LINES)
    r = post_receipt(client, user)
    assert r.status_code == 200 and r.get_json()["categorized_by"] == "heuristic"


def test_no_key_never_calls_gemini(client, user, monkeypatch, ml_on):
    monkeypatch.setattr(gemini, "categorize_receipt_lines",
                        lambda names: pytest.fail("Gemini called without a key"))
    set_ocr(monkeypatch, LINES)
    assert post_receipt(client, user).get_json()["categorized_by"] == "heuristic"


@pytest.mark.parametrize("answer", ["[]", "{}", '{"items": []}', "[1, 2, 3]"])
def test_empty_gemini_answer_is_not_reported_as_gemini(client, user, monkeypatch, gem_on, ml_on, answer):
    """BE-12 (fixed on #54): categorize_receipt_lines pads to len(names) with {}; the route must report
    categorized_by="gemini" only when some entry actually contributed a field."""
    FakeGenai(monkeypatch, [answer])
    set_ocr(monkeypatch, LINES)
    b = post_receipt(client, user).get_json()
    assert [c["name"] for c in b["candidates"]] == ["GV 2% MLK GAL", "CHKN BRST", "BANANAS"]  # heuristic
    assert b["categorized_by"] == "heuristic"


@pytest.mark.parametrize("answer", ["null", '"a string"', "42", "true", '{"items": "nope"}', '{"items": 5}'])
def test_non_container_gemini_answer_is_not_500(client, user, monkeypatch, gem_on, ml_on, sleeps, usage_records,
                                                answer):
    """BE-13 (fixed via #57 on main, verified on #54): a scalar or unusable JSON shape is an UpstreamError in
    _generate, so the receipt falls back to the heuristic with 200 and logs one status=error line."""
    fake = FakeGenai(monkeypatch, [answer])
    set_ocr(monkeypatch, LINES, total=12.20)
    r = post_receipt(client, user)
    assert r.status_code == 200, r.get_data(as_text=True)
    b = r.get_json()
    assert b["categorized_by"] == "heuristic" and b["total"] == 12.20
    assert [(c["name"], c["category"]) for c in b["candidates"]] == [
        ("GV 2% MLK GAL", "dairy"), ("CHKN BRST", "meat"), ("BANANAS", "produce_leafy")]
    assert len(fake.calls) == 1 and sleeps == []  # not transient: no retry
    assert len(usage_records) == 1
    kv = _kv(usage_records[0])
    assert kv["status"] == "error" and kv["purpose"] == "receipt_categorize"


def test_wrapped_items_answer_still_categorises(client, user, monkeypatch, gem_on, ml_on, usage_records):
    """list_key="items" (merged from #57): {"items": [...]} is unwrapped like a bare list."""
    FakeGenai(monkeypatch, [json.dumps({"items": ENRICHED})])
    set_ocr(monkeypatch, LINES)
    b = post_receipt(client, user).get_json()
    assert b["categorized_by"] == "gemini"
    assert [(c["name"], c["category"]) for c in b["candidates"]] == [
        ("2% milk", "dairy"), ("Chicken breast", "meat"), ("Bananas", "produce_leafy")]
    assert len(usage_records) == 1 and _kv(usage_records[0])["status"] == "ok"


# ---------- 3. number parsing ----------------------------------------------------------------
@pytest.mark.parametrize("raw, want", [
    ("$3.48", 3.48), ("3.48", 3.48), (" $ 3.48 ", 3.48), ("1,29", 1.29), ("$1,299.50", 1299.50),
    ("3.48 F", 3.48), (3.48, 3.48), (3, 3.0), ("abc", None), ("", None), (None, None), ("$", None),
    ("1e400", 1.0), (1e300, 1e300), (float("inf"), None), (float("nan"), None), ("9" * 400, None),
    ([], None), ({}, None),
])
def test_money_parsing(raw, want):
    assert candidates._money(raw) == want


@pytest.mark.parametrize("price, want", [
    ("$3.48", 3.48), ("abc", None), ("1,29", 1.29), ("9" * 400, None), (1e308, 1e308),
    ([1, 2], None), ({"a": 1}, None),
])
def test_route_price_never_500(client, user, monkeypatch, ml_on, price, want):
    set_ocr(monkeypatch, [{"name": "MILK", "quantity": "2", "price": price}], total=price)
    r = post_receipt(client, user)
    assert r.status_code == 200, r.get_data(as_text=True)
    b = r.get_json()  # strict JSON: NaN/Infinity would make this invalid
    json.loads(r.get_data(as_text=True), parse_constant=lambda c: pytest.fail(f"non-JSON constant {c}"))
    c = b["candidates"][0]
    assert c["price"] == c["est_price"] == want and b["total"] == want and c["quantity"] == 2.0


@pytest.mark.parametrize("price", ["-1.00", -0.5, "$-1.00", "-$1.00"])
def test_route_negative_price_dropped_not_500(client, user, monkeypatch, ml_on, price):
    """BE-14: a negative price is a discount line; it is dropped (was returned as est_price -1.0)."""
    set_ocr(monkeypatch, [{"name": "MILK", "quantity": "2", "price": price}], total=3.0)
    r = post_receipt(client, user)
    assert r.status_code == 200 and r.get_json()["candidates"] == []


@pytest.mark.parametrize("qty, want", [("abc", 1.0), ("0", 1.0), (-3, 1.0), ("2.5", 2.5), (None, 1.0),
                                       ("1e400", 1.0), (float("inf"), 1.0), ("x3", 3.0)])
def test_route_quantity_defaults_positive(client, user, monkeypatch, ml_on, qty, want):
    set_ocr(monkeypatch, [{"name": "EGGS", "quantity": qty, "price": 2}])
    r = post_receipt(client, user)
    assert r.status_code == 200 and r.get_json()["candidates"][0]["quantity"] == want


# ---------- 4. total -------------------------------------------------------------------------
@pytest.mark.parametrize("total, want", [(4.21, 4.21), ("4.21", 4.21), ("$4.21", 4.21), ("TOTAL $4.21", 4.21),
                                         ("1,29", 1.29), (None, None), ("n/a", None), (0, 0.0)])
def test_total_parsed(client, user, monkeypatch, ml_on, total, want):
    set_ocr(monkeypatch, [{"name": "MILK", "price": 3.48}], total=total)
    assert post_receipt(client, user).get_json()["total"] == want


def test_total_missing_key(client, user, monkeypatch, ml_on):
    monkeypatch.setattr(ml, "ocr", lambda *a, **k: {"lines": [{"name": "MILK", "price": 1}]})
    r = post_receipt(client, user)
    assert r.status_code == 200 and r.get_json()["total"] is None


def test_raw_text_not_echoed(client, user, monkeypatch, ml_on):
    set_ocr(monkeypatch, [{"name": "MILK", "price": 1}], total=1, raw_text="SECRET RAW OCR")
    assert "raw_text" not in post_receipt(client, user).get_json()


@pytest.mark.parametrize("label", ["TOTAL", "SUBTOTAL", "TAX", "Sales Tax", "GRAND TOTAL", "BALANCE DUE"])
def test_total_and_tax_lines_do_not_become_items(client, user, monkeypatch, ml_on, label):
    """BE-11 (fixed on #54): ml/serve's Gemini-structuring path filters total/tax lines by prompt only,
    so the backend guards with candidates.is_receipt_total."""
    set_ocr(monkeypatch, [{"name": "MILK", "price": 3.48}, {"name": label, "price": 4.21}], total=4.21)
    names = [c["name"] for c in post_receipt(client, user).get_json()["candidates"]]
    assert names == ["MILK"]


# ---------- 5. retry + usage logging (gemini._generate) --------------------------------------
@pytest.fixture
def gem_ctx(app, gem_on):
    with app.app_context():
        yield


@pytest.mark.parametrize("first", [
    api_error(503, "UNAVAILABLE", "The model is overloaded."), api_error(429, "RESOURCE_EXHAUSTED"),
    api_error(504, "DEADLINE_EXCEEDED"), RuntimeError("503 UNAVAILABLE upstream"),
])
def test_transient_retried_once_then_succeeds(gem_ctx, monkeypatch, sleeps, usage_records, first):
    fake = FakeGenai(monkeypatch, [first, json.dumps(ENRICHED[:1])])
    assert gemini.categorize_receipt_lines(["GV 2% MLK GAL"]) == ENRICHED[:1]
    assert len(fake.calls) == 2 and sleeps == [1.5]
    assert len(usage_records) == 1  # one line per logical call, not per attempt
    kv = _kv(usage_records[0])
    assert kv["status"] == "ok" and kv["purpose"] == "receipt_categorize" and kv["total_tokens"] == "15"


@pytest.mark.parametrize("err", [api_error(503, "UNAVAILABLE"), api_error(429, "RESOURCE_EXHAUSTED")])
def test_transient_twice_fails_after_exactly_one_retry(gem_ctx, monkeypatch, sleeps, usage_records, err):
    fake = FakeGenai(monkeypatch, [err, err])
    with pytest.raises(gemini.UpstreamError) as ei:
        gemini.categorize_receipt_lines(["MILK"])
    assert len(fake.calls) == 2 and sleeps == [1.5]
    assert FAKE_KEY not in str(ei.value)
    assert len(usage_records) == 1 and _kv(usage_records[0])["status"] == "error"


@pytest.mark.parametrize("err", [
    api_error(400, "INVALID_ARGUMENT"), api_error(401, "UNAUTHENTICATED"), api_error(403, "PERMISSION_DENIED"),
    api_error(404, "NOT_FOUND"), api_error(500, "INTERNAL"), TimeoutError("read timed out"),
    ConnectionError("reset"), ValueError("bad"),
])
def test_non_transient_fails_fast(gem_ctx, monkeypatch, sleeps, usage_records, err):
    fake = FakeGenai(monkeypatch, [err, json.dumps([{}])])
    with pytest.raises(gemini.UpstreamError):
        gemini.categorize_receipt_lines(["MILK"])
    assert len(fake.calls) == 1 and sleeps == []
    assert len(usage_records) == 1 and _kv(usage_records[0])["status"] == "error"


def test_bad_json_not_retried(gem_ctx, monkeypatch, sleeps, usage_records):
    fake = FakeGenai(monkeypatch, ["{not json", "[]"])
    with pytest.raises(gemini.UpstreamError):
        gemini.categorize_receipt_lines(["MILK"])
    assert len(fake.calls) == 1 and sleeps == [] and len(usage_records) == 1


def test_retry_applies_to_every_helper(gem_ctx, monkeypatch, sleeps, usage_records):
    FakeGenai(monkeypatch, [api_error(503, "UNAVAILABLE"), '[{"name": "Milk"}]'])
    assert gemini.parse_text("milk") == [{"name": "Milk"}]
    assert sleeps == [1.5] and len(usage_records) == 1 and _kv(usage_records[0])["purpose"] == "parse_text"


def test_receipt_schema_and_config_sent(gem_ctx, monkeypatch):
    fake = FakeGenai(monkeypatch, [json.dumps(ENRICHED[:1])])
    gemini.categorize_receipt_lines(["MILK"])
    cfg = fake.calls[0]["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_schema is not None  # the enum schema survived SDK validation
    assert "produce_leafy" in cfg.system_instruction and "abbreviated" in cfg.system_instruction


def test_is_transient_classification():
    assert gemini._is_transient(SimpleNamespace(code=503))  # duck-typed .code
    assert gemini._is_transient(api_error(429, "RESOURCE_EXHAUSTED"))
    assert not gemini._is_transient(api_error(400, "INVALID_ARGUMENT"))
    assert not gemini._is_transient(TimeoutError("timed out"))


# ---------- 6. auth + validation -------------------------------------------------------------
def test_requires_auth(client, monkeypatch, ml_on):
    set_ocr(monkeypatch, LINES)
    r = client.post("/items/from-receipt", data=img(), content_type="multipart/form-data")
    assert r.status_code == 401 and set(r.get_json()["error"]) >= {"code", "message"}
    r = client.post("/items/from-receipt", data=img(), content_type="multipart/form-data",
                    headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


@pytest.mark.parametrize("kw", [
    {"data": {}, "content_type": "multipart/form-data"},
    {"data": {"image": (io.BytesIO(b""), "e.jpg", "image/jpeg")}, "content_type": "multipart/form-data"},
    {"data": {"photo": (io.BytesIO(b"\xff\xd8x"), "e.jpg", "image/jpeg")}, "content_type": "multipart/form-data"},
    {"json": {"image": "base64..."}},
    {},
])
def test_missing_or_empty_body_400(client, user, monkeypatch, ml_on, kw):
    monkeypatch.setattr(ml, "ocr", lambda *a, **k: pytest.fail("OCR called without an image"))
    r = client.post("/items/from-receipt", headers=user["headers"], **kw)
    assert r.status_code == 400, r.get_data(as_text=True)
    e = r.get_json()["error"]
    assert e["code"] == "validation_error" and e["message"]


def test_ocr_unavailable_502_shape(client, user, monkeypatch, ml_on):
    def down(*a, **k):
        raise ml.MLUnavailable("ML service request failed: ConnectionError")
    monkeypatch.setattr(ml, "ocr", down)
    r = post_receipt(client, user)
    assert r.status_code == 502 and set(r.get_json()["error"]) >= {"code", "message"}


# ---------- BE-11 regressions: food names that must survive the total/tax guard ----------------
FOOD_NOT_TOTALS = ["Cashews", "Cardamom pods", "Tortilla", "Taxi bread", "Totino pizza", "Balanced oats",
                   "Changua", "CASHEWS 8OZ", "cardamom", "TORTILLA CHIPS", "TAXI BREAD", "TOTINOS PIZZA ROLLS",
                   "BALANCED OATS", "CHANGUA"]


@pytest.mark.parametrize("name", FOOD_NOT_TOTALS)
def test_food_names_are_not_receipt_totals(name):
    assert not candidates.is_receipt_total(name)


@pytest.mark.parametrize("name", ["TOTAL", "total", "  Total ", "SUBTOTAL", "Sub Total", "SUB-TOTAL", "TAX",
                                  "Sales Tax", "GRAND TOTAL", "BALANCE DUE", "CHANGE", "CASH", "VISA TENDER",
                                  "DEBIT CARD", "CREDIT CARD", "TOTAL 4.21"])
def test_total_like_names_are_receipt_totals(name):
    assert candidates.is_receipt_total(name)


def test_total_cereal_is_kept():
    """Orchestrator ruling (tail rule): a keyword followed by a non-receipt word is food."""
    assert not candidates.is_receipt_total("Total Cereal")


@pytest.mark.parametrize("name", ["Cash & Carry Crackers", "Change Coffee Co Beans", "Discover granola"])
def test_brand_names_starting_with_keywords_are_kept(name):
    assert not candidates.is_receipt_total(name)


@pytest.mark.parametrize("name", ["TOTAL DUE", "TAX 1 8.25%", "CHANGE DUE", "CASH TENDERED", "VISA CREDIT ****1234",
                                  "BALANCE DUE", "TOTAL $4.21", "VISA x1234", "CARD XXXX1234"])
def test_tail_rule_drops_payment_lines(name):
    assert candidates.is_receipt_total(name)


def test_tail_rule_end_to_end(client, user, monkeypatch, ml_on):
    keep = ["Total Cereal", "Cash & Carry Crackers", "Change Coffee Co Beans", "Discover granola"]
    drop = ["TOTAL DUE", "TAX 1 8.25%", "CHANGE DUE", "CASH TENDERED", "VISA CREDIT ****1234", "VISA x1234",
            "CARD XXXX1234"]
    set_ocr(monkeypatch, [{"name": n, "price": 3.0} for n in keep + drop], total=12.0)
    assert [c["name"] for c in post_receipt(client, user).get_json()["candidates"]] == keep


def test_food_names_kept_end_to_end(client, user, monkeypatch, ml_on):
    set_ocr(monkeypatch, [{"name": n, "price": 2.0} for n in FOOD_NOT_TOTALS[:7]]
            + [{"name": "SUBTOTAL", "price": 14.0}, {"name": "TAX", "price": 0.5}, {"name": "TOTAL", "price": 14.5}],
            total=14.5)
    b = post_receipt(client, user).get_json()
    assert [c["name"] for c in b["candidates"]] == FOOD_NOT_TOTALS[:7] and b["total"] == 14.5


def test_totals_never_sent_to_gemini(client, user, monkeypatch, gem_on, ml_on):
    lines = [{"name": "GV 2% MLK GAL", "price": 3.48}, {"name": "SUBTOTAL", "price": 3.48},
             {"name": "Cashews", "price": 5.0}, {"name": "Sales Tax", "price": 0.29},
             {"name": "GRAND TOTAL", "price": 8.77}, {"name": "VISA TENDER", "price": 8.77},
             {"name": "CHANGE", "price": 0}]
    answer = [{"display_name": "2% milk", "category": "dairy", "food_group": "dairy", "storage": "fridge"},
              {"display_name": "Cashews", "category": "pantry_dry", "food_group": "pantry", "storage": "pantry"}]
    fake = FakeGenai(monkeypatch, [json.dumps(answer)])
    set_ocr(monkeypatch, lines, total=8.77)
    b = post_receipt(client, user).get_json()
    assert len(fake.calls) == 1
    assert json.loads(fake.calls[0]["contents"]) == ["GV 2% MLK GAL", "Cashews"]  # the stubbed request
    assert [(c["name"], c["category"]) for c in b["candidates"]] == [("2% milk", "dairy"), ("Cashews", "pantry_dry")]
    assert b["categorized_by"] == "gemini" and b["total"] == 8.77


def test_only_totals_no_gemini_call(client, user, monkeypatch, gem_on, ml_on):
    fake = FakeGenai(monkeypatch, [])
    set_ocr(monkeypatch, [{"name": "SUBTOTAL", "price": 1}, {"name": "TOTAL", "price": 1}], total=1)
    b = post_receipt(client, user).get_json()
    assert fake.calls == [] and b == {"candidates": [], "total": 1.0, "categorized_by": "heuristic", "source": "ocr"}


def test_partial_gemini_answer_counts_as_gemini(client, user, monkeypatch, gem_on, ml_on):
    """BE-12 boundary: one usable entry is enough for categorized_by="gemini"."""
    FakeGenai(monkeypatch, [json.dumps([{}, {"category": "meat"}])])
    set_ocr(monkeypatch, LINES[:2])
    assert post_receipt(client, user).get_json()["categorized_by"] == "gemini"


# ---------- BE-14: coupon / discount lines ---------------------------------------------------
def test_be14_coupon_repro_posts_back_201(client, user, monkeypatch, ml_on):
    set_ocr(monkeypatch, [{"name": "MILK", "price": 3.48}, {"name": "COUPON", "price": -0.50}], total=2.98)
    b = post_receipt(client, user).get_json()
    assert [c["name"] for c in b["candidates"]] == ["MILK"] and b["total"] == 2.98
    r = client.post("/items", json={"items": [dict(c, source="receipt") for c in b["candidates"]]},
                    headers=user["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)


@pytest.mark.parametrize("name, price", [
    ("MFR COUPON", 0.75), ("INSTANT SAVINGS", 1.00), ("COUPON $1.00 OFF", 1.00), ("DISCOUNT 10%", 0.35),
    ("SAVINGS", 2.00), ("MFR COUPON", -0.75), ("INSTANT SAVINGS 1.00 OFF", None), ("MILK", -0.5),
    ("MILK", "-1.00"), ("MILK", -0.01),
])
def test_be14_noise_dropped(name, price):
    assert candidates.is_receipt_noise(name, price)


@pytest.mark.parametrize("name, price", [
    ("Savings Bread", 2.50), ("Discount Ham", 4.99), ("Coupon Cookies", 2.00), ("Coupon Cookies 2.00", 2.00),
    ("MILK", 0), ("MILK", None), ("MILK", "abc"),
])
def test_be14_food_kept(name, price):
    assert not candidates.is_receipt_noise(name, price)


def test_be14_end_to_end(client, user, monkeypatch, ml_on):
    keep = [{"name": "Savings Bread", "price": 2.5}, {"name": "Discount Ham", "price": 4.99},
            {"name": "Coupon Cookies 2.00", "price": 2.0}]
    drop = [{"name": "MFR COUPON", "price": -0.75}, {"name": "INSTANT SAVINGS", "price": -1.0},
            {"name": "COUPON $1.00 OFF", "price": None}, {"name": "DISCOUNT 10%", "price": -0.35},
            {"name": "SAVINGS", "price": 2.0}, {"name": "EGGS", "price": "-1.00"}]
    set_ocr(monkeypatch, keep + drop, total=7.0)
    b = post_receipt(client, user).get_json()
    assert [c["name"] for c in b["candidates"]] == [k["name"] for k in keep]
    assert all(c["est_price"] is None or c["est_price"] >= 0 for c in b["candidates"])
    r = client.post("/items", json={"items": [dict(c, source="receipt") for c in b["candidates"]]},
                    headers=user["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)


def test_be14_coupons_never_sent_to_gemini(client, user, monkeypatch, gem_on, ml_on):
    lines = [{"name": "GV 2% MLK GAL", "price": 3.48}, {"name": "MFR COUPON", "price": -0.75},
             {"name": "Coupon Cookies", "price": 2.0}, {"name": "INSTANT SAVINGS", "price": -1.0},
             {"name": "COUPON $1.00 OFF", "price": 1.0}, {"name": "EGGS", "price": "-1.00"}]
    fake = FakeGenai(monkeypatch, [json.dumps(ENRICHED[:2])])
    set_ocr(monkeypatch, lines, total=4.73)
    b = post_receipt(client, user).get_json()
    assert len(fake.calls) == 1
    assert json.loads(fake.calls[0]["contents"]) == ["GV 2% MLK GAL", "Coupon Cookies"]
    assert len(b["candidates"]) == 2 and b["categorized_by"] == "gemini"
