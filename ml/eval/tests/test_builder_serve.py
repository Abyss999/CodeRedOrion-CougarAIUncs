"""Contract tests for the builder's Flask inference service (ml/serve) using its fake backends.

Discovery: env ML_SERVE_APP="path/to/app.py:factory_or_app" (factory is called with no args; if that
fails, with fake=True). Otherwise looks for ml/serve/app.py exposing create_app() or app.
Skips if the service does not exist yet. Contract (from the orchestrator brief):
  POST /detect  -> {"candidates":[{name,category,confidence,freshness,bbox}], "model": str}
  POST /ocr     -> {"lines":[{name,quantity,price}], "total", "raw_text"}
  bad/missing image -> 400 {"error":{"code","message"}};  GET /health -> 200
"""
import importlib
import importlib.util
import io
import os
import sys

import pytest
from PIL import Image

from conftest import REPO_ROOT

CATEGORIES = {"produce_leafy", "produce_hardy", "dairy", "meat", "seafood", "bakery", "eggs",
              "leftovers", "pantry_dry", "frozen", "other"}


def _load(path):
    mldir = os.path.join(REPO_ROOT, "ml")
    if mldir not in sys.path:
        sys.path.insert(0, mldir)  # the service imports `ocr.*` relative to ml/
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("builder_serve_app", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_app():
    """Import as the package `serve.app` with ml/ on sys.path (the service uses `ocr.*` and relative imports)."""
    if not os.path.exists(os.path.join(REPO_ROOT, "ml", "serve", "app.py")):
        pytest.skip("ml/serve/app.py does not exist yet")
    mldir = os.path.join(REPO_ROOT, "ml")
    if mldir not in sys.path:
        sys.path.insert(0, mldir)
    for k in ("DETECTOR_BACKEND", "OCR_BACKEND"):
        os.environ[k] = "fake"  # never load real models here
    mod = importlib.import_module("serve.app")
    obj = getattr(mod, "create_app", None) or getattr(mod, "app", None)
    return obj() if callable(obj) and not hasattr(obj, "test_client") else obj


@pytest.fixture(scope="module")
def client():
    app = build_app()
    app.config["TESTING"] = True
    return app.test_client()


def png_bytes():
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 30, 30)).save(b, "PNG")
    return b.getvalue()


def post_img(client, path, data=None, field="image", filename="a.png", **form):
    payload = dict(form)
    if data is not None:
        payload[field] = (io.BytesIO(data), filename)
    return client.post(path, data=payload, content_type="multipart/form-data")


def assert_error(r):
    assert r.status_code == 400, r.get_data(as_text=True)
    j = r.get_json()
    assert set(j) == {"error"} and set(j["error"]) >= {"code", "message"}
    assert isinstance(j["error"]["code"], str) and isinstance(j["error"]["message"], str)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_detect_shape(client):
    r = post_img(client, "/detect", png_bytes())
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert set(j) == {"candidates", "model"}, set(j)
    assert isinstance(j["model"], str) and j["model"]
    assert isinstance(j["candidates"], list)
    for c in j["candidates"]:
        assert set(c) >= {"name", "category", "confidence", "freshness", "bbox"}
        assert isinstance(c["name"], str) and c["name"]
        assert c["category"] in CATEGORIES
        assert c["freshness"] in {"fresh", "spoiled"}
        assert isinstance(c["confidence"], (int, float)) and 0 <= c["confidence"] <= 1
        assert isinstance(c["bbox"], list) and len(c["bbox"]) == 4 and all(isinstance(v, (int, float)) for v in c["bbox"])
        x1, y1, x2, y2 = c["bbox"]
        assert x2 > x1 and y2 > y1


def test_detect_accepts_mode_field(client):
    for mode in ("fridge", "single"):
        assert post_img(client, "/detect", png_bytes(), mode=mode).status_code == 200


def test_detect_missing_image(client):
    assert_error(client.post("/detect", data={}, content_type="multipart/form-data"))


def test_detect_corrupt_image(client):
    assert_error(post_img(client, "/detect", b"this is not an image"))


def test_detect_empty_file(client):
    assert_error(post_img(client, "/detect", b""))


def test_ocr_shape(client):
    r = post_img(client, "/ocr", png_bytes())
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert set(j) == {"lines", "total", "raw_text"}, set(j)
    assert isinstance(j["raw_text"], str)
    assert j["total"] is None or isinstance(j["total"], (int, float))
    assert isinstance(j["lines"], list)
    for l in j["lines"]:
        assert set(l) >= {"name", "quantity", "price"}
        assert isinstance(l["name"], str) and l["name"]
        assert isinstance(l["quantity"], (int, float))
        assert l["price"] is None or isinstance(l["price"], (int, float))


def test_ocr_missing_image(client):
    assert_error(client.post("/ocr", data={}, content_type="multipart/form-data"))


def test_ocr_corrupt_image(client):
    assert_error(post_img(client, "/ocr", b"\x00\x01garbage"))


def test_wrong_field_name_is_400_not_500(client):
    assert_error(post_img(client, "/detect", png_bytes(), field="file"))


def test_invalid_mode_is_400(client):
    assert_error(post_img(client, "/detect", png_bytes(), mode="bogus"))


def test_single_mode_returns_at_most_one(client):
    j = post_img(client, "/detect", png_bytes(), mode="single").get_json()
    assert len(j["candidates"]) <= 1


def test_oversize_is_413_with_error_shape(client):
    big = b"\x00" * (13 * 1024 * 1024)  # default MAX_UPLOAD_MB is 12
    r = post_img(client, "/detect", big)
    assert r.status_code == 413
    j = r.get_json()
    assert j and "code" in j["error"] and "message" in j["error"]


def test_unknown_route_returns_json_error(client):
    r = client.get("/nope")
    assert r.status_code == 404 and r.get_json() and "error" in r.get_json()
