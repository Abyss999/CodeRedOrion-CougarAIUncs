import io
import pytest
from PIL import Image
from serve.app import create_app
from serve.backends import FakeDetector, FakeOCR, YoloDetector
from serve.categories import CATEGORIES


def png(size=(200, 100)):
    b = io.BytesIO(); Image.new("RGB", size, (200, 30, 30)).save(b, "PNG"); b.seek(0); return b


@pytest.fixture
def client():
    return create_app(FakeDetector(), FakeOCR(), structure_with_gemini=False).test_client()


def post(c, url, img=None, **form):
    data = dict(form)
    if img is not None:
        data["image"] = (img, "x.png")
    return c.post(url, data=data, content_type="multipart/form-data")


def test_health(client):
    r = client.get("/health"); assert r.status_code == 200 and r.json["status"] == "ok"


def test_detect_fridge_contract(client):
    r = post(client, "/detect", png(), mode="fridge")
    assert r.status_code == 200
    j = r.json
    assert set(j) == {"candidates", "model"} and j["model"] == "fake-detector"
    assert len(j["candidates"]) == 2
    for c in j["candidates"]:
        assert set(c) == {"name", "category", "food_group", "confidence", "freshness", "bbox"}
        assert c["category"] in CATEGORIES and c["freshness"] in ("fresh", "semi_fresh", "spoiled")
        assert len(c["bbox"]) == 4
    assert j["candidates"][0]["confidence"] >= j["candidates"][1]["confidence"]


def test_detect_single_returns_top_one_and_default_mode(client):
    assert len(post(client, "/detect", png(), mode="single").json["candidates"]) == 1
    assert len(post(client, "/detect", png()).json["candidates"]) == 2  # default fridge


def test_detect_null_bbox_and_unknown_category_normalised():
    d = FakeDetector([{"name": "mystery", "category": "weird", "confidence": 0.5, "freshness": "??", "bbox": None}])
    r = post(create_app(d, FakeOCR()).test_client(), "/detect", png(), mode="single")
    assert r.json["candidates"][0] == {"name": "mystery", "category": "other", "food_group": "other", "confidence": 0.5,
                                       "freshness": "fresh", "bbox": None}


@pytest.mark.parametrize("url", ["/detect", "/ocr"])
def test_missing_and_invalid_image(client, url):
    r = post(client, url)
    assert r.status_code == 400 and r.json["error"]["code"] == "missing_image"
    r = post(client, url, io.BytesIO(b"not an image"))
    assert r.status_code == 400 and r.json["error"]["code"] == "invalid_image"
    r = post(client, url, io.BytesIO(b""))
    assert r.status_code == 400


def test_invalid_mode(client):
    r = post(client, "/detect", png(), mode="bogus")
    assert r.status_code == 400 and r.json["error"]["code"] == "invalid_mode"


def test_ocr_contract(client):
    r = post(client, "/ocr", png())
    assert r.status_code == 200
    j = r.json
    assert set(j) == {"lines", "total", "raw_text"}
    assert j["total"] == 4.21 and "MILK" in j["raw_text"]
    assert j["lines"][0] == {"name": "GV 2% MILK GAL", "quantity": 1.0, "price": 3.48}
    assert all(set(l) == {"name", "quantity", "price"} for l in j["lines"])


def test_errors_are_json(client):
    r = client.get("/nope"); assert r.status_code == 404 and "code" in r.json["error"]
    r = client.get("/detect"); assert r.status_code == 405 and "code" in r.json["error"]


def test_backend_failure_is_500_json():
    class Boom:
        def predict(self, image): raise RuntimeError("cuda oom")
    r = post(create_app(Boom(), FakeOCR()).test_client(), "/detect", png())
    assert r.status_code == 500 and r.json["error"]["code"] == "inference_failed"


def test_yolo_detector_is_lazy_and_needs_weights(monkeypatch):
    monkeypatch.delenv("YOLO_WEIGHTS", raising=False)
    d = YoloDetector()           # construction must not import ultralytics or read env
    import sys; assert "ultralytics" not in sys.modules and "torch" not in sys.modules
    with pytest.raises(RuntimeError):
        d.predict(Image.new("RGB", (4, 4)))


def test_taxonomy_categories_valid():
    from serve.categories import CLASS_CATEGORY
    assert set(CLASS_CATEGORY.values()) <= set(CATEGORIES)


def test_detect_freshness_normalisation(caplog):
    dets = [{"name": "papaya", "confidence": 0.9, "freshness": "semi_fresh", "bbox": None},
            {"name": "apple", "confidence": 0.8, "freshness": "spoiled", "bbox": None},
            {"name": "milk", "confidence": 0.7, "freshness": "rotten", "bbox": None},
            {"name": "kale", "confidence": 0.65, "freshness": "glowing", "bbox": None},
            {"name": "egg", "confidence": 0.6, "bbox": None}]
    with caplog.at_level("WARNING", logger="fwr.serve"):
        r = post(create_app(FakeDetector(dets), FakeOCR()).test_client(), "/detect", png(), mode="fridge")
    got = {c["name"]: c["freshness"] for c in r.json["candidates"]}
    assert got == {"papaya": "semi_fresh", "apple": "spoiled", "milk": "spoiled", "kale": "fresh", "egg": "fresh"}
    assert "glowing" in caplog.text  # unknown -> fresh + warning; "rotten" is a spoiled variant (ML-27)


def test_detect_new_classes_food_group():
    dets = [{"name": "bitter_melon", "confidence": 0.9, "freshness": "fresh", "bbox": None},
            {"name": "pineapple", "confidence": 0.8, "freshness": "fresh", "bbox": None}]
    r = post(create_app(FakeDetector(dets), FakeOCR()).test_client(), "/detect", png())
    assert {c["name"]: c["food_group"] for c in r.json["candidates"]} == {"bitter_melon": "veggies", "pineapple": "fruit"}
