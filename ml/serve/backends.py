"""Injectable backends. Heavy deps (ultralytics, transformers) are imported lazily and only when
a real backend is constructed AND used - the fakes need only Pillow."""
from __future__ import annotations
import os

from .categories import category_for


class FakeDetector:
    """Deterministic stand-in. Output depends on image size only, so tests are stable."""
    model_id = "fake-detector"

    def __init__(self, detections: list[dict] | None = None):
        self._fixed = detections

    def predict(self, image) -> list[dict]:
        if self._fixed is not None:
            return [dict(d) for d in self._fixed]
        w, h = image.size
        return [
            {"name": "milk", "category": category_for("milk"), "freshness": "fresh",
             "confidence": 0.91, "bbox": [0.1 * w, 0.1 * h, 0.4 * w, 0.6 * h]},
            {"name": "apple", "category": category_for("apple"), "freshness": "spoiled",
             "confidence": 0.77, "bbox": [0.5 * w, 0.5 * h, 0.8 * w, 0.9 * h]},
        ]


class YoloDetector:
    """Two-stage YOLO (detector + optional freshness classifier). Weights from env:
    YOLO_WEIGHTS (required), FRESHNESS_WEIGHTS, YOLO_CONF, SPOILED_THRESHOLD, SEMI_FRESH_THRESHOLD, YOLO_DEVICE.
    Loaded on first predict() (or via warmup()), never at import."""

    def __init__(self, ts=None):
        self._ts = ts

    def _get(self):
        if self._ts is None:
            from yolo.infer import TwoStage
            self._ts = TwoStage.from_env()
        return self._ts

    @property
    def model_id(self) -> str:
        return self._get().model_id

    def warmup(self):
        self._get().load()

    def predict(self, image) -> list[dict]:
        return self._get().predict(image)


class FakeOCR:
    model_id = "fake-ocr"
    TEXT = "GV 2% MILK GAL 3.48 F\nBANANAS\n1.23 lb @ $0.59/lb 0.73 F\nSUBTOTAL 4.21\nTAX 0.00\nTOTAL 4.21\n"

    def __init__(self, text: str | None = None):
        self.text = text if text is not None else self.TEXT

    def image_to_text(self, image) -> str:
        return self.text


class GlmOcr:
    """GLM-OCR text recognition (lazy). Structuring (parser + optional Gemini) is done by the app."""
    model_id = "zai-org/GLM-OCR"

    def __init__(self):
        self._engine = None

    def _get(self):
        if self._engine is None:
            from ocr.receipt_pipeline import GlmOcrEngine
            self._engine = GlmOcrEngine()
        return self._engine

    def warmup(self):
        self._get().load()

    def image_to_text(self, image) -> str:
        return self._get().image_to_text(image)


def detector_from_env():
    kind = os.environ.get("DETECTOR_BACKEND") or ("yolo" if os.environ.get("YOLO_WEIGHTS") else "fake")
    return YoloDetector() if kind == "yolo" else FakeDetector()


def ocr_from_env():
    """fake (default, dev) | glm | off. off: /ocr answers 503 ocr_not_configured, so a deployment without OCR never
    returns FakeOCR's canned receipt as if it were real (the backend maps the error to its own 502)."""
    kind = os.environ.get("OCR_BACKEND", "fake")
    if kind == "off":
        return None
    return GlmOcr() if kind == "glm" else FakeOCR()
