"""Independent CPU endpoint QA. OCR-1/2 fixes landed before this test run.

Only fake engines are used; no model libraries, database or external API calls.
"""
import io
from pathlib import Path

import pytest
from PIL import Image


TEXT = "MILK 3.00\nBREAD 2.00\nTOTAL 5.00\n"


class RecordingOCR:
    def __init__(self, text=TEXT, error=None):
        self.text = text
        self.error = error
        self.images = []

    def image_to_text(self, image):
        self.images.append(image.copy())
        if self.error:
            raise self.error
        return self.text


class RecordingDetector:
    model_id = "qa-detector"

    def __init__(self):
        self.images = []

    def predict(self, image):
        self.images.append(image.copy())
        return []


@pytest.fixture
def app_factory(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]))
    monkeypatch.setenv("MAX_UPLOAD_MB", "12")
    monkeypatch.setenv("OCR_BACKEND", "off")
    from serve.app import create_app
    return create_app


def upload(client, payload=None, path="/ocr"):
    data = {} if payload is None else {"image": (io.BytesIO(payload), "receipt.jpg")}
    return client.post(path, data=data, content_type="multipart/form-data")


def picture(oriented=False):
    image = Image.new("RGB", (400, 200), "blue")
    image.paste("red", (0, 0, 200, 200))
    data = io.BytesIO()
    exif = Image.Exif()
    if oriented:
        exif[274] = 6  # Stored landscape pixels; display rotated 90 degrees clockwise.
    image.save(data, "JPEG", exif=exif, quality=95)
    return data.getvalue()


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.get_json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_ocr_1_exif_rotation_is_applied_only_to_ocr(app_factory):
    ocr, detector = RecordingOCR(), RecordingDetector()
    client = app_factory(detector, ocr, structure_with_gemini=False).test_client()
    payload = picture(oriented=True)
    assert upload(client, payload).status_code == 200
    received = ocr.images[0]
    assert received.size == (200, 400)
    assert received.getexif().get(274, 1) == 1
    red, green, blue = received.getpixel((100, 50))
    assert red > 200 and green < 30 and blue < 30
    assert upload(client, payload, path="/detect").status_code == 200
    assert detector.images[0].size == (400, 200), "Detector must retain its original pixel frame"


def test_ocr_2_empty_and_whitespace_text_are_422(app_factory):
    for text in ("", " \t\r\n "):
        client = app_factory(RecordingDetector(), RecordingOCR(text),
                             structure_with_gemini=False).test_client()
        assert_error(upload(client, picture()), 422, "ocr_no_text")


def test_off_backend_is_503(app_factory):
    client = app_factory(detector=RecordingDetector(), structure_with_gemini=False).test_client()
    assert_error(upload(client, picture()), 503, "ocr_not_configured")


def test_engine_failure_is_500_without_internal_exception_text(app_factory):
    client = app_factory(RecordingDetector(), RecordingOCR(error=RuntimeError("internal-test-detail")),
                         structure_with_gemini=False).test_client()
    response = upload(client, picture())
    assert_error(response, 500, "inference_failed")
    assert "internal-test-detail" not in response.get_data(as_text=True)


def test_oversize_upload_is_413_before_engine_call(app_factory, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    ocr = RecordingOCR()
    client = app_factory(RecordingDetector(), ocr, structure_with_gemini=False).test_client()
    assert_error(upload(client, b"x" * (1024 * 1024 + 1)), 413, "request_entity_too_large")
    assert not ocr.images


@pytest.mark.parametrize("payload,code", [(None, "missing_image"),
                                         (b"not an image", "invalid_image"),
                                         (b"", "invalid_image")])
def test_bad_upload_is_400_before_engine_call(app_factory, payload, code):
    ocr = RecordingOCR()
    client = app_factory(RecordingDetector(), ocr, structure_with_gemini=False).test_client()
    assert_error(upload(client, payload), 400, code)
    assert not ocr.images


def test_success_has_exact_receipt_contract(app_factory):
    client = app_factory(RecordingDetector(), RecordingOCR(), structure_with_gemini=False).test_client()
    response = upload(client, picture())
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"lines", "total", "raw_text"}
    assert body["raw_text"] == TEXT
    assert body["total"] == 5.0
    assert body["lines"] == [
        {"name": "MILK", "quantity": 1.0, "price": 3.0},
        {"name": "BREAD", "quantity": 1.0, "price": 2.0},
    ]
