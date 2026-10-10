"""Inference service. Contract (fixed; backend codes against it):

  POST /detect  multipart image, form mode=fridge|single
     -> {"candidates":[{name,category,confidence,freshness(fresh|semi_fresh|spoiled),bbox|null}], "model": str}
  POST /ocr     multipart image
     -> {"lines":[{name,quantity,price}], "total": float|null, "raw_text": str}
  GET  /health  -> {"status":"ok", ...}
  Errors: {"error":{"code","message"}}
"""
from __future__ import annotations
import io
import logging
import os

from flask import Flask, jsonify, request
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

from ocr.receipt_pipeline import gemini_structure, parse_receipt_text
from .backends import detector_from_env, ocr_from_env
from .categories import CATEGORIES, FRESHNESS

log = logging.getLogger("fwr.serve")
MAX_FRIDGE_CANDIDATES = 50
Image.MAX_IMAGE_PIXELS = 60_000_000


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _load_image() -> Image.Image:
    f = request.files.get("image")
    if f is None or not f.filename and not f.content_length:
        raise ApiError(400, "missing_image", "multipart field 'image' is required")
    data = f.read()
    if not data:
        raise ApiError(400, "invalid_image", "image is empty")
    try:
        Image.open(io.BytesIO(data)).verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ApiError(400, "invalid_image", "file is not a valid image")
    return img.convert("RGB")


def _clean_candidate(d: dict) -> dict:
    cat = d.get("category")
    bbox = d.get("bbox")
    return {"name": str(d["name"]),
            "category": cat if cat in CATEGORIES else "other",
            "confidence": round(float(d.get("confidence", 0.0)), 4),
            "freshness": d.get("freshness") if d.get("freshness") in FRESHNESS else "fresh",
            "bbox": [round(float(v), 1) for v in bbox] if bbox else None}


def create_app(detector=None, ocr=None, structure_with_gemini: bool | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "12")) * 1024 * 1024
    det = detector if detector is not None else detector_from_env()
    eng = ocr if ocr is not None else ocr_from_env()
    use_gemini = (structure_with_gemini if structure_with_gemini is not None
                  else bool(os.environ.get("GEMINI_API_KEY")))

    @app.errorhandler(ApiError)
    def _api(e):
        return jsonify(error={"code": e.code, "message": e.message}), e.status

    @app.errorhandler(HTTPException)
    def _http(e):
        return jsonify(error={"code": (e.name or "error").lower().replace(" ", "_"),
                              "message": e.description}), e.code

    @app.errorhandler(Exception)
    def _any(e):
        log.exception("unhandled")
        return jsonify(error={"code": "inference_failed", "message": "internal error"}), 500

    @app.get("/health")
    def health():
        return jsonify(status="ok", detector=type(det).__name__, ocr=type(eng).__name__)

    @app.post("/detect")
    def detect():
        mode = request.form.get("mode", "fridge")
        if mode not in ("fridge", "single"):
            raise ApiError(400, "invalid_mode", "mode must be 'fridge' or 'single'")
        img = _load_image()
        dets = sorted(det.predict(img), key=lambda d: -float(d.get("confidence", 0)))
        if mode == "single":
            dets = dets[:1]
        else:
            dets = dets[:MAX_FRIDGE_CANDIDATES]
        return jsonify(candidates=[_clean_candidate(d) for d in dets], model=getattr(det, "model_id", "unknown"))

    @app.post("/ocr")
    def ocr_route():
        img = _load_image()
        raw = eng.image_to_text(img)
        parsed = parse_receipt_text(raw)
        if use_gemini:
            g = gemini_structure(raw)
            if g and g.get("lines"):
                parsed = {"lines": g["lines"], "total": g.get("total", parsed["total"])}
        lines = [{"name": str(l.get("name", "")), "quantity": l.get("quantity"), "price": l.get("price")}
                 for l in parsed["lines"]]
        return jsonify(lines=lines, total=parsed["total"], raw_text=raw)

    return app


def main():  # pragma: no cover - `python -m serve.app` for dev; use gunicorn in prod
    app = create_app()
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
