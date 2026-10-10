"""Client for the off-box ML service (`ml/serve`): POST /detect and POST /ocr."""
import requests
from flask import current_app

TIMEOUT = 60


class MLUnavailable(Exception):
    pass


def base_url() -> str:
    return (current_app.config.get("ML_SERVICE_URL") or "").rstrip("/")


def is_configured() -> bool:
    return bool(base_url())


def _post(path: str, image: bytes, filename: str, mime: str, data: dict | None = None) -> dict:
    if not is_configured():
        raise MLUnavailable("ML_SERVICE_URL is not set.")
    try:
        r = requests.post(f"{base_url()}{path}", files={"image": (filename, image, mime)},
                          data=data or {}, timeout=TIMEOUT)
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, dict):
            raise ValueError("bad body")
        return body
    except (requests.RequestException, ValueError) as e:
        raise MLUnavailable(f"ML service request failed: {type(e).__name__}") from e


def detect(image: bytes, filename: str, mime: str, mode: str) -> list[dict]:
    body = _post("/detect", image, filename, mime, {"mode": mode})
    cands = body.get("candidates")
    if not isinstance(cands, list):
        raise MLUnavailable("ML /detect returned an unexpected shape.")
    return cands


def ocr(image: bytes, filename: str, mime: str) -> dict:
    body = _post("/ocr", image, filename, mime)
    if not isinstance(body.get("lines"), list):
        raise MLUnavailable("ML /ocr returned an unexpected shape.")
    return body
