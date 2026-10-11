"""Gemini / ML / Open Food Facts are stubbed: tests never touch the network."""
import io

import pytest
import requests as real_requests

from app.services import gemini, ml, barcode


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call attempted in test")
    monkeypatch.setattr(real_requests, "get", boom)
    monkeypatch.setattr(real_requests, "post", boom)


def img(name="a.jpg"):
    return {"image": (io.BytesIO(b"\xff\xd8fakejpeg"), name, "image/jpeg")}


def err_code(r):
    e = r.get_json()["error"]
    assert e["message"]
    return e["code"]


# ---------- no-key behaviour -----------------------------------------------------------------
def test_parse_text_no_key_502(client, user):
    r = client.post("/items/parse-text", json={"text": "2 apples"}, headers=user["headers"])
    assert r.status_code == 502 and err_code(r) == "upstream_unavailable"


def test_from_photo_no_key_no_ml_502(client, user):
    r = client.post("/items/from-photo", data={"mode": "fridge", **img()}, headers=user["headers"],
                    content_type="multipart/form-data")
    assert r.status_code == 502 and err_code(r) == "upstream_unavailable"


def test_recipes_no_key_502(client, user, make_item):
    make_item(user)
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 502 and err_code(r) == "upstream_unavailable"


def test_receipt_no_ml_502(client, user):
    r = client.post("/items/from-receipt", data=img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 502 and err_code(r) == "upstream_unavailable"


def test_create_items_without_gemini_uses_default(client, user, make_item):
    assert make_item(user)["expiry_source"] == "default"


# ---------- parse-text -----------------------------------------------------------------------
def test_parse_text_success(client, user, monkeypatch):
    monkeypatch.setattr(gemini, "parse_text", lambda t: [
        {"name": "Apples", "category": "produce_hardy", "quantity": 2, "unit": "piece", "est_price": 1.5},
        {"name": "Milk", "category": "dairy", "storage": "fridge", "quantity": 1, "unit": "l"},
        {"name": "", "category": "dairy"}, "junk"])
    r = client.post("/items/parse-text", json={"text": "2 apples and milk"}, headers=user["headers"])
    assert r.status_code == 200
    c = r.get_json()["candidates"]
    assert [x["name"] for x in c] == ["Apples", "Milk"]
    assert all(x["predicted_expiry"] and x["expiry_source"] == "default" and x["storage"] for x in c)
    # not saved
    assert client.get("/items", headers=user["headers"]).get_json()["items"] == []


def test_parse_text_bad_input(client, user):
    for body in [{}, {"text": ""}, {"text": "x" * 5000}]:
        assert client.post("/items/parse-text", json=body, headers=user["headers"]).status_code == 400
    assert client.post("/items/parse-text", json={"text": "x"}).status_code == 401


def test_parse_text_upstream_error(client, user, monkeypatch):
    def fail(t):
        raise gemini.UpstreamError("down")
    monkeypatch.setattr(gemini, "parse_text", fail)
    r = client.post("/items/parse-text", json={"text": "x"}, headers=user["headers"])
    assert r.status_code == 502 and err_code(r) == "upstream_unavailable"


# ---------- from-photo -----------------------------------------------------------------------
YOLO = [{"name": "Banana", "category": "produce_hardy", "confidence": 0.9, "freshness": "fresh", "bbox": [1, 2, 3, 4]}]


def test_from_photo_uses_ml_when_configured(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "detect", lambda *a, **k: YOLO)
    monkeypatch.setattr(gemini, "detect_from_image", lambda *a, **k: pytest.fail("gemini must not be used"))
    r = client.post("/items/from-photo", data={"mode": "single", **img()}, headers=user["headers"],
                    content_type="multipart/form-data")
    assert r.status_code == 200
    b = r.get_json()
    assert b["source"] == "yolo"
    c = b["candidates"][0]
    assert c["name"] == "Banana" and c["freshness"] == "fresh" and c["confidence"] == 0.9 and c["bbox"] == [1, 2, 3, 4]


def test_from_photo_gemini_fallback_when_no_ml(client, user, monkeypatch):
    monkeypatch.setattr(gemini, "detect_from_image", lambda *a, **k: [dict(YOLO[0], freshness="spoiled")])
    r = client.post("/items/from-photo", data=img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["source"] == "gemini"
    assert r.get_json()["candidates"][0]["freshness"] == "spoiled"


def test_from_photo_falls_back_when_ml_down(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    def down(*a, **k):
        raise ml.MLUnavailable("x")
    monkeypatch.setattr(ml, "detect", down)
    monkeypatch.setattr(gemini, "detect_from_image", lambda *a, **k: YOLO)
    r = client.post("/items/from-photo", data=img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["source"] == "gemini"


def test_from_photo_ml_http_via_requests(app, client, user, monkeypatch):
    """Exercise app.services.ml itself with a stubbed requests.post."""
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid/")
    class R:
        def raise_for_status(self): pass
        def json(self): return {"candidates": YOLO}
    seen = {}
    def post(url, **kw):
        seen["url"] = url
        return R()
    monkeypatch.setattr(real_requests, "post", post)
    r = client.post("/items/from-photo", data=img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["source"] == "yolo"
    assert seen["url"] == "http://ml.invalid/detect"


def test_from_photo_bad_input(client, user):
    h = user["headers"]
    assert client.post("/items/from-photo", data={"mode": "bogus", **img()}, headers=h, content_type="multipart/form-data").status_code == 400
    assert client.post("/items/from-photo", data={"mode": "fridge"}, headers=h, content_type="multipart/form-data").status_code == 400
    assert client.post("/items/from-photo", data=img()).status_code == 401


# ---------- receipt --------------------------------------------------------------------------
def test_receipt_success(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "ocr", lambda *a, **k: {"lines": [
        {"name": "Milk", "quantity": 2, "price": 3.5}, {"name": " "}, {"name": "Eggs", "price": 4}], "total": 11.0})
    r = client.post("/items/from-receipt", data=img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200
    b = r.get_json()
    assert b["total"] == 11.0
    assert [{k: c[k] for k in ("name", "quantity", "price")} for c in b["candidates"]] == [
        {"name": "Milk", "quantity": 2.0, "price": 3.5}, {"name": "Eggs", "quantity": 1.0, "price": 4.0}]
    assert all(c["food_group"] for c in b["candidates"])  # added in 0003


def test_receipt_missing_image(client, user):
    assert client.post("/items/from-receipt", data={}, headers=user["headers"], content_type="multipart/form-data").status_code == 400


# ---------- barcode --------------------------------------------------------------------------
class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body
    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.HTTPError("x")
    def json(self): return self._b


def test_barcode_success(client, user, monkeypatch):
    monkeypatch.setattr(real_requests, "get", lambda *a, **k: Resp(200, {"status": 1, "product": {
        "product_name": "Whole Milk", "brands": "Acme", "categories_tags": ["en:dairies", "en:milks"], "quantity": "1 l"}}))
    r = client.get("/items/barcode/5000112637922", headers=user["headers"])
    assert r.status_code == 200
    c = r.get_json()["candidate"]
    assert c["name"] == "Whole Milk" and c["category"] == "dairy" and c["predicted_expiry"]


def test_barcode_not_found_and_upstream(client, user, monkeypatch):
    monkeypatch.setattr(real_requests, "get", lambda *a, **k: Resp(200, {"status": 0}))
    assert client.get("/items/barcode/5000112637922", headers=user["headers"]).status_code == 404
    monkeypatch.setattr(real_requests, "get", lambda *a, **k: Resp(404, {}))
    assert client.get("/items/barcode/5000112637922", headers=user["headers"]).status_code == 404
    def down(*a, **k):
        raise real_requests.ConnectionError("down")
    monkeypatch.setattr(real_requests, "get", down)
    r = client.get("/items/barcode/5000112637922", headers=user["headers"])
    assert r.status_code == 502 and err_code(r) == "upstream_unavailable"


def test_barcode_bad_code(client, user):
    assert client.get("/items/barcode/abc", headers=user["headers"]).status_code == 400
    assert client.get("/items/barcode/12", headers=user["headers"]).status_code == 400


# ---------- recipes --------------------------------------------------------------------------
def test_recipes_success_and_ordering(client, user, make_item, monkeypatch):
    from conftest import iso_in
    make_item(user, name="Late", predicted_expiry=iso_in(9))
    soon = make_item(user, name="Soon", predicted_expiry=iso_in(1))
    seen = {}
    def fake(items, n, dietary):
        seen.update(items=items, n=n, dietary=dietary)
        return [{"title": "Soup", "minutes": 20, "uses_items": ["Soon"], "missing_items": [], "steps": ["Boil"]}]
    monkeypatch.setattr(gemini, "suggest_recipes", fake)
    r = client.post("/recipes/suggest", json={"max_results": 1, "dietary": ["vegan"]}, headers=user["headers"])
    assert r.status_code == 200
    assert r.get_json()["recipes"][0]["title"] == "Soup"
    # backend PR 2: uses_items are mapped back to the caller's items
    assert r.get_json()["recipes"][0]["uses_items"] == [
        {"item_id": soon["id"], "name": "Soon", "predicted_expiry": iso_in(1)}]
    assert [i["name"] for i in seen["items"]] == ["Soon", "Late"]
    assert seen["n"] == 1 and seen["dietary"] == ["vegan"]


def test_recipes_no_items_and_bad_input(client, user):
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 200 and r.get_json()["recipes"] == []
    for body in [{"max_results": 0}, {"max_results": "x"}, {"dietary": "vegan"}, {"dietary": [1]}]:
        assert client.post("/recipes/suggest", json=body, headers=user["headers"]).status_code == 400


def test_recipes_upstream_error(client, user, make_item, monkeypatch):
    make_item(user)
    def fail(*a):
        raise gemini.UpstreamError("x")
    monkeypatch.setattr(gemini, "suggest_recipes", fail)
    assert client.post("/recipes/suggest", json={}, headers=user["headers"]).status_code == 502


# ---------- gemini shelf life on create ------------------------------------------------------
def test_create_uses_gemini_shelf_life(app, client, user, monkeypatch):
    from datetime import date, timedelta
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(gemini, "estimate_shelf_life", lambda items: [11])
    r = client.post("/items", json={"items": [{"name": "Tofu", "category": "other", "storage": "fridge",
                    "quantity": 1, "unit": "pack", "source": "manual"}]}, headers=user["headers"])
    it = r.get_json()["items"][0]
    assert it["expiry_source"] == "gemini"
    assert it["predicted_expiry"] == (date.today() + timedelta(days=11)).isoformat()


def test_create_gemini_failure_falls_back(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "k")
    def fail(items):
        raise gemini.UpstreamError("x")
    monkeypatch.setattr(gemini, "estimate_shelf_life", fail)
    r = client.post("/items", json={"items": [{"name": "Tofu", "category": "other", "storage": "fridge",
                    "quantity": 1, "unit": "pack", "source": "manual"}]}, headers=user["headers"])
    assert r.status_code == 201 and r.get_json()["items"][0]["expiry_source"] == "default"


# ---------- contract additions: 413, ML error fallback, codes -----------------------------------
def test_upload_over_10mb_413(client, user):
    big = {"image": (io.BytesIO(b"\0" * (10 * 1024 * 1024 + 1024)), "big.jpg", "image/jpeg")}
    r = client.post("/items/from-photo", data=big, headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 413 and err_code(r) == "payload_too_large"
    big = {"image": (io.BytesIO(b"\0" * (10 * 1024 * 1024 + 1024)), "big.jpg", "image/jpeg")}
    r = client.post("/items/from-receipt", data=big, headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 413 and err_code(r) == "payload_too_large"


def test_from_photo_ml_http_error_falls_back_to_gemini(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    class Bad:
        def raise_for_status(self): raise real_requests.HTTPError("500")
        def json(self): return {}
    monkeypatch.setattr(real_requests, "post", lambda *a, **k: Bad())
    monkeypatch.setattr(gemini, "detect_from_image", lambda *a, **k: YOLO)
    r = client.post("/items/from-photo", data=img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["source"] == "gemini"


def test_from_photo_ml_error_and_gemini_down_502(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    def conn(*a, **k):
        raise real_requests.ConnectionError("x")
    monkeypatch.setattr(real_requests, "post", conn)
    r = client.post("/items/from-photo", data=img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 502 and err_code(r) == "upstream_unavailable"


def test_barcode_400_code_shape(client, user):
    for c in ("abc", "12", "1" * 15):
        r = client.get(f"/items/barcode/{c}", headers=user["headers"])
        assert r.status_code == 400 and err_code(r) == "validation_error"


def test_recipes_empty_when_only_removed_items(client, user, make_item):
    it = make_item(user)
    client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 200 and r.get_json() == {"recipes": []}
