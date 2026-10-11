"""Inference service. Contract (fixed; backend codes against it):

  POST /detect  multipart image, form mode=fridge|single
     -> {"candidates":[{name,category,food_group,confidence,freshness(fresh|semi_fresh|spoiled),bbox|null}], "model": str}
  POST /ocr     multipart image
     -> {"lines":[{name,quantity,price}], "total": float|null, "raw_text": str}
  GET  /health  -> {"status":"ok", ...}
  Errors: {"error":{"code","message"}}
  /ocr applies EXIF orientation before OCR; /detect does not. /ocr answers 422 ocr_no_text when the engine
  reads no text (blank or whitespace-only), never an empty 200.
"""
from __future__ import annotations
import io
import logging
import os

from flask import Flask, jsonify, request
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

from ocr.receipt_pipeline import gemini_structure, parse_receipt_text
from .backends import detector_from_env, ocr_from_env
from .categories import CATEGORIES, FOOD_GROUPS, FRESHNESS, SEMI_WORDS, SPOILED_WORDS, food_group_for

log = logging.getLogger("fwr.serve")
MAX_FRIDGE_CANDIDATES = 50
Image.MAX_IMAGE_PIXELS = 60_000_000


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _load_image(upright: bool = False) -> Image.Image:
    """Decode the upload to RGB. upright=True applies the EXIF orientation first (/ocr only; /detect keeps
    the stored pixel frame, see docs/API.md and ML_BBOX_FRAME)."""
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
    if upright:  # must run on the opened image: EXIF is gone after convert()
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:  # malformed EXIF must not fail the request; OCR the stored orientation
            log.warning("exif_transpose failed; using stored orientation", exc_info=True)
    return img.convert("RGB")


def _clean_freshness(d: dict) -> str:
    """Case/space/hyphen-insensitive; taxonomy spoiled/semi words map to their class (a spoiled
    variant must never fall through to fresh). Anything else -> fresh + warning."""
    f = d.get("freshness")
    if isinstance(f, str):
        key = "_".join(f.strip().lower().replace("-", " ").replace("_", " ").split())
        if key in FRESHNESS:
            return key
        if key in SPOILED_WORDS:
            return "spoiled"
        if key in SEMI_WORDS or key == "use_soon":
            return "semi_fresh"
    log.warning("unknown freshness %r for %r; treating as fresh", f, d.get("name"))
    return "fresh"


def _clean_candidate(d: dict) -> dict:
    cat = d.get("category")
    bbox = d.get("bbox")
    return {"name": str(d["name"]),
            "category": cat if cat in CATEGORIES else "other",
            "food_group": (d.get("food_group") if d.get("food_group") in FOOD_GROUPS
                           else food_group_for(str(d["name"]))),
            "confidence": round(float(d.get("confidence", 0.0)), 4),
            "freshness": _clean_freshness(d),
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
        return jsonify(status="ok", detector=type(det).__name__, ocr=type(eng).__name__ if eng is not None else "off")

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
        if eng is None:
            raise ApiError(503, "ocr_not_configured", "receipt OCR is off on this service (OCR_BACKEND=off)")
        img = _load_image(upright=True)
        raw = eng.image_to_text(img)
        if not (raw or "").strip():
            log.warning("ocr engine returned no text")
            raise ApiError(422, "ocr_no_text", "No text could be read from the receipt photo. "
                                               "Retake the photo flat, well lit and in focus.")
        parsed = parse_receipt_text(raw)
        if use_gemini:
            g = gemini_structure(raw)
            if g and g.get("lines"):
                parsed = {"lines": g["lines"], "total": g["total"] if g.get("total") is not None else parsed["total"]}
        lines = [{"name": str(l.get("name", "")), "quantity": l.get("quantity"), "price": l.get("price")}
                 for l in parsed["lines"]]
        return jsonify(lines=lines, total=parsed["total"], raw_text=raw)

    return app


def main():  # pragma: no cover - `python -m serve.app` for dev; use gunicorn in prod
    app = create_app()
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
