"""POST /items/from-receipt: full candidates, Gemini enrichment, heuristic fallback, number parsing.
Gemini and the ML service are stubbed; no network."""
import io

import pytest

from app.models import CATEGORIES, FOOD_GROUPS
from app.services import candidates, gemini, ml

FULL = {"name", "category", "food_group", "storage", "quantity", "unit", "est_price",
        "predicted_expiry", "expiry_source", "price", "receipt_text"}


def img():
    return {"image": (io.BytesIO(b"\xff\xd8fakejpeg"), "r.jpg", "image/jpeg")}


@pytest.fixture
def post(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")

    def go(lines, total=None, gem=None, configured=False):
        monkeypatch.setattr(ml, "ocr", lambda *a, **k: {"lines": lines, "total": total})
        monkeypatch.setattr(gemini, "is_configured", lambda: configured)
        calls = []

        def fake(names):
            calls.append(names)
            if isinstance(gem, Exception):
                raise gem
            return gem(names) if callable(gem) else gem

        monkeypatch.setattr(gemini, "categorize_receipt_lines", fake)
        r = client.post("/items/from-receipt", data=img(), headers=user["headers"],
                        content_type="multipart/form-data")
        r.calls = calls
        return r
    return go


def L(name, q=1, p=1.0):
    return {"name": name, "quantity": q, "price": p}


def test_full_candidate_shape_and_post_back(client, user, post):
    r = post([L("GV WHL MILK GAL", 1, 3.48)], total=3.48)
    assert r.status_code == 200
    b = r.get_json()
    assert set(b) == {"candidates", "total", "categorized_by", "source"} and b["total"] == 3.48
    c = b["candidates"][0]
    assert FULL <= set(c)
    assert c["price"] == c["est_price"] == 3.48 and c["receipt_text"] == "GV WHL MILK GAL"
    assert c["category"] in CATEGORIES and c["food_group"] in FOOD_GROUPS
    r2 = client.post("/items", json={"items": [{k: c[k] for k in (
        "name", "category", "food_group", "storage", "quantity", "unit", "est_price",
        "predicted_expiry", "expiry_source")}]}, headers=user["headers"])
    assert r2.status_code == 201, r2.get_json()
    r3 = client.post("/items", json={"items": [c]}, headers=user["headers"])  # whole candidate as-is
    assert r3.status_code == 201, r3.get_json()


def test_gemini_enrichment(post):
    gem = [{"display_name": "Whole milk", "category": "dairy", "food_group": "dairy", "storage": "fridge"},
           {"display_name": "Frozen peas", "category": "frozen", "food_group": "veggies", "storage": "freezer"}]
    r = post([L("GV WHL MILK GAL"), L("FROZ PEAS")], gem=gem, configured=True)
    b = r.get_json()
    assert b["categorized_by"] == "gemini"
    assert r.calls == [["GV WHL MILK GAL", "FROZ PEAS"]]
    assert [c["name"] for c in b["candidates"]] == ["Whole milk", "Frozen peas"]
    assert b["candidates"][1]["storage"] == "freezer" and b["candidates"][1]["food_group"] == "veggies"
    assert b["candidates"][0]["receipt_text"] == "GV WHL MILK GAL"


def test_gemini_invalid_enums_fall_back(post):
    gem = [{"display_name": "Chicken", "category": "bogus", "food_group": "nope", "storage": "attic"}]
    c = post([L("CHKN BRST")], gem=gem, configured=True).get_json()["candidates"][0]
    assert c["category"] == "meat" and c["food_group"] == "protein" and c["storage"] == "fridge"
    assert c["name"] == "Chicken"


def test_gemini_fewer_entries_than_lines(post):
    gem = [{"display_name": "Whole milk", "category": "dairy", "food_group": "dairy", "storage": "fridge"}]
    b = post([L("MILK"), L("LARGE EGGS"), L("BANANAS")], gem=gem, configured=True).get_json()
    assert len(b["candidates"]) == 3
    assert [c["category"] for c in b["candidates"]] == ["dairy", "eggs", "produce_leafy"]
    assert b["categorized_by"] == "gemini"


def test_gemini_upstream_error_falls_back(post):
    r = post([L("CHKN BRST")], gem=gemini.UpstreamError("x"), configured=True)
    assert r.status_code == 200
    b = r.get_json()
    assert b["categorized_by"] == "heuristic" and b["candidates"][0]["name"] == "CHKN BRST"
    assert b["candidates"][0]["category"] == "meat"


def test_not_configured_no_gemini_call(post):
    r = post([L("CHKN BRST")], gem=AssertionError("must not call"), configured=False)
    assert r.status_code == 200 and r.calls == [] and r.get_json()["categorized_by"] == "heuristic"


def test_no_lines_no_gemini_call(post):
    r = post([{"name": " "}, "junk", None], gem=AssertionError("no"), configured=True)
    assert r.status_code == 200 and r.calls == []
    assert r.get_json()["candidates"] == []


@pytest.mark.parametrize("name,cat", [
    ("GV WHL MILK GAL", "dairy"), ("CHKN BRST", "meat"), ("SALMON FILLET", "seafood"),
    ("LARGE EGGS", "eggs"), ("BANANAS", "produce_leafy"), ("FROZ PEAS", "frozen"),
    ("WHITE BREAD", "bakery"), ("XQZT 99", "other"),
])
def test_heuristic_categories(post, name, cat):
    c = post([L(name)]).get_json()["candidates"][0]
    assert c["category"] == cat and c["name"] == name


def test_category_from_name_always_valid():
    for n in ["", "???", "RICE", "TUNA CAN", "SHRIMP", "APPLES", "PASTA SAUCE", "LEFTOVER SOUP", "123"]:
        assert candidates.category_from_name(n) in CATEGORIES


@pytest.mark.parametrize("raw,exp", [("$3.48", 3.48), ("1,29", 1.29), ("abc", None), ("", None),
                                     (None, None), (2, 2.0), ("-1.50", -1.5), ("$", None), ([], None),
                                     ("1,299.50", 1299.5), ("$1,299.50", 1299.5), ("1,29", 1.29),
                                     (float("nan"), None), (float("inf"), None), (float("-inf"), None),
                                     ("nan", None), ("inf", None)])
def test_money(raw, exp):
    assert candidates._money(raw) == exp


@pytest.mark.parametrize("raw,exp", [(None, 1.0), (0, 1.0), (-2, 1.0), ("0", 1.0), ("abc", 1.0),
                                     ("2", 2.0), ("1,5", 1.5), (3, 3.0), (True, 1.0),
                                     (float("nan"), 1.0), (float("inf"), 1.0)])
def test_qty(raw, exp):
    assert candidates._qty(raw) == exp


def test_numbers_through_endpoint(post):
    b = post([{"name": "A", "quantity": "2", "price": "$3.48"}, {"name": "B", "quantity": 0, "price": "1,29"},
              {"name": "C", "quantity": -1, "price": "garbage"}, {"name": "D"}], total="$12,50").get_json()
    cs = b["candidates"]
    assert [c["price"] for c in cs] == [3.48, 1.29, None, None]
    assert [c["quantity"] for c in cs] == [2.0, 1.0, 1.0, 1.0]
    assert cs[2]["est_price"] is None and b["total"] == 12.5


@pytest.mark.parametrize("total,exp", [("junk", None), (None, None), ("$7.00", 7.0), (5, 5.0), ({}, None), ([], None)])
def test_total_variants(post, total, exp):
    r = post([L("MILK")], total=total)
    assert r.status_code == 200 and r.get_json()["total"] == exp


def test_odd_payloads_no_500(post):
    lines = ["str", 5, None, [], {"name": None}, {"name": ""}, {"name": 123}, {"name": "MILK", "quantity": {}, "price": []},
             {"quantity": 1}, {"name": "  EGGS  "}]
    r = post(lines)
    assert r.status_code == 200
    names = [c["name"] for c in r.get_json()["candidates"]]
    assert names == ["123", "MILK", "EGGS"]


def test_ml_failure_502(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")

    def down(*a, **k):
        raise ml.MLUnavailable("x")
    monkeypatch.setattr(ml, "ocr", down)
    r = client.post("/items/from-receipt", data=img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 502


def test_display_name_truncated_and_blank_ignored(post):
    gem = [{"display_name": "x" * 500, "category": "dairy"}, {"display_name": "   ", "category": "dairy"}]
    cs = post([L("A"), L("B")], gem=gem, configured=True).get_json()["candidates"]
    assert len(cs[0]["name"]) == 120 and cs[1]["name"] == "B"


def test_gemini_non_dict_entries(post):
    cs = post([L("MILK")], gem=["junk"], configured=True).get_json()["candidates"]
    assert cs[0]["category"] == "dairy"


def test_nan_inf_through_endpoint_valid_json(post):
    import json
    r = post([{"name": "A", "quantity": float("nan"), "price": float("inf")},
              {"name": "B", "quantity": float("-inf"), "price": float("nan")}], total=float("nan"))
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "NaN" not in body and "Infinity" not in body
    b = json.loads(body, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    assert b["total"] is None
    assert [(c["price"], c["est_price"], c["quantity"]) for c in b["candidates"]] == [(None, None, 1.0)] * 2


def test_thousands_total_through_endpoint(post):
    assert post([L("MILK")], total="1,299.50").get_json()["total"] == 1299.5
