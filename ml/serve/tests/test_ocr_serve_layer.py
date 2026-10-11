"""Serve-layer behaviour of /ocr that is independent of the OCR engine: EXIF upright, blank text -> 422, warmup flag."""
import importlib
import io
import logging
import sys

import pytest
from PIL import Image

from serve.app import create_app
from serve.backends import FakeOCR


class RecordingOCR:
    """Records every image it is given; returns fixed text."""
    def __init__(self, text=FakeOCR.TEXT):
        self.text, self.seen = text, []

    def image_to_text(self, image) -> str:
        self.seen.append(image)
        return self.text


class RecordingDetector:
    model_id = "recording-detector"

    def __init__(self):
        self.seen = []

    def predict(self, image) -> list[dict]:
        self.seen.append(image)
        return []


def jpeg(size=(200, 100), orientation=None):
    img = Image.new("RGB", size, (30, 120, 200))
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    b = io.BytesIO()
    img.save(b, "JPEG", exif=exif.tobytes())
    b.seek(0)
    return b


def post(c, url, img):
    return c.post(url, data={"image": (img, "x.jpg")}, content_type="multipart/form-data")


def make(ocr=None, det=None):
    ocr = ocr if ocr is not None else RecordingOCR()
    det = det if det is not None else RecordingDetector()
    return create_app(det, ocr, structure_with_gemini=False).test_client(), det, ocr


def test_ocr_applies_exif_orientation():
    c, _, ocr = make()
    r = post(c, "/ocr", jpeg((200, 100), orientation=6))   # stored landscape, displays portrait
    assert r.status_code == 200
    assert len(ocr.seen) == 1
    assert ocr.seen[0].size == (100, 200) and ocr.seen[0].mode == "RGB"


def test_ocr_without_exif_orientation_is_unchanged():
    c, _, ocr = make()
    assert post(c, "/ocr", jpeg((200, 100))).status_code == 200
    assert post(c, "/ocr", jpeg((200, 100), orientation=1)).status_code == 200
    assert [i.size for i in ocr.seen] == [(200, 100), (200, 100)]


def test_detect_does_not_apply_exif_orientation():
    c, det, _ = make()
    r = post(c, "/detect", jpeg((200, 100), orientation=6))
    assert r.status_code == 200
    assert len(det.seen) == 1
    assert det.seen[0].size == (200, 100) and det.seen[0].mode == "RGB"   # stored frame, as before


def test_ocr_bad_exif_transpose_falls_back_to_stored_orientation(monkeypatch):
    import serve.app as app_mod

    def boom(img, *a, **k):
        raise ValueError("bad exif")
    monkeypatch.setattr(app_mod.ImageOps, "exif_transpose", boom)
    c, _, ocr = make()
    assert post(c, "/ocr", jpeg((200, 100), orientation=6)).status_code == 200
    assert ocr.seen[0].size == (200, 100)


@pytest.mark.parametrize("text", ["", " ", "\n", "  \n\t \r\n  "])
def test_blank_ocr_text_is_422_ocr_no_text(text):
    c, _, _ = make(RecordingOCR(text))
    r = post(c, "/ocr", jpeg())
    assert r.status_code == 422
    assert r.json == {"error": {"code": "ocr_no_text",
                                "message": "No text could be read from the receipt photo. "
                                           "Retake the photo flat, well lit and in focus."}}
    assert "lines" not in r.json


def test_normal_ocr_text_is_200_with_contract_keys():
    c, _, _ = make()
    r = post(c, "/ocr", jpeg())
    assert r.status_code == 200
    assert set(r.json) == {"lines", "total", "raw_text"}
    assert r.json["total"] == 4.21 and r.json["lines"]


def test_other_ocr_errors_unchanged(monkeypatch):
    monkeypatch.setenv("OCR_BACKEND", "off")
    c = create_app(RecordingDetector(), structure_with_gemini=False).test_client()
    r = post(c, "/ocr", jpeg())
    assert r.status_code == 503 and r.json["error"]["code"] == "ocr_not_configured"

    class Boom:
        def image_to_text(self, image):
            raise RuntimeError("model blew up")
    r = post(make(Boom())[0], "/ocr", jpeg())
    assert r.status_code == 500 and r.json["error"]["code"] == "inference_failed"

    c, _, _ = make()
    r = c.post("/ocr", data={}, content_type="multipart/form-data")
    assert r.status_code == 400 and r.json["error"]["code"] == "missing_image"
    r = post(c, "/ocr", io.BytesIO(b"not an image"))
    assert r.status_code == 400 and r.json["error"]["code"] == "invalid_image"


# --- wsgi warmup ---------------------------------------------------------------------------------------

class WarmableOCR(RecordingOCR):
    def __init__(self, fail=False):
        super().__init__()
        self.warmups, self.fail = 0, fail

    def warmup(self):
        self.warmups += 1
        if self.fail:
            raise RuntimeError("model download failed")


@pytest.fixture
def load_wsgi(monkeypatch):
    """Import serve.wsgi fresh with a fake OCR engine and OCR_WARMUP set (None = unset); restore afterwards."""
    import serve
    had_mod = "serve.wsgi" in sys.modules
    saved_mod = sys.modules.get("serve.wsgi")
    saved_attr = getattr(serve, "wsgi", None)

    def _load(engine, warmup):
        for k in ("YOLO_WEIGHTS", "DETECTOR_BACKEND"):
            monkeypatch.delenv(k, raising=False)
        if warmup is None:
            monkeypatch.delenv("OCR_WARMUP", raising=False)
        else:
            monkeypatch.setenv("OCR_WARMUP", warmup)
        monkeypatch.setattr("serve.backends.ocr_from_env", lambda: engine)
        sys.modules.pop("serve.wsgi", None)
        return importlib.import_module("serve.wsgi")

    yield _load
    if had_mod:
        sys.modules["serve.wsgi"] = saved_mod
    else:
        sys.modules.pop("serve.wsgi", None)
    if saved_attr is not None:
        serve.wsgi = saved_attr
    elif hasattr(serve, "wsgi"):
        delattr(serve, "wsgi")


def test_warmup_flag_calls_warmup_once(load_wsgi, caplog):
    eng = WarmableOCR()
    with caplog.at_level(logging.INFO, logger="fwr.serve"):
        mod = load_wsgi(eng, "1")
    assert eng.warmups == 1
    assert "ocr warmup ok" in caplog.text
    assert mod.app.test_client().get("/health").status_code == 200


def test_failed_warmup_does_not_break_service(load_wsgi, caplog):
    eng = WarmableOCR(fail=True)
    with caplog.at_level(logging.WARNING, logger="fwr.serve"):
        mod = load_wsgi(eng, "1")
    assert eng.warmups == 1
    assert "ocr warmup failed" in caplog.text
    c = mod.app.test_client()
    assert c.get("/health").status_code == 200
    assert post(c, "/detect", jpeg()).status_code == 200
    assert post(c, "/ocr", jpeg()).status_code == 200     # first /ocr call retries the lazy load


@pytest.mark.parametrize("flag", [None, "", "0", "true", "yes", "2"])
def test_warmup_not_called_unless_flag_is_exactly_1(load_wsgi, flag):
    eng = WarmableOCR()
    mod = load_wsgi(eng, flag)
    assert eng.warmups == 0
    assert mod.app.test_client().get("/health").status_code == 200


def test_warmup_flag_with_engine_lacking_warmup_is_ok(load_wsgi):
    mod = load_wsgi(FakeOCR(), "1")
    assert mod.app.test_client().get("/health").status_code == 200


def test_warmup_flag_with_ocr_off_is_ok(load_wsgi, monkeypatch):
    monkeypatch.setenv("OCR_BACKEND", "off")   # create_app re-reads env when handed no engine
    mod = load_wsgi(None, "1")
    c = mod.app.test_client()
    assert c.get("/health").json["ocr"] == "off"
    assert post(c, "/ocr", jpeg()).status_code == 503
