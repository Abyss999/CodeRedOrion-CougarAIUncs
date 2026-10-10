"""Normalise raw candidates (ML / Gemini / OFF) and attach a predicted expiry."""
from ..models import CATEGORIES
from . import expiry

_DEFAULT_STORAGE = {"frozen": "freezer", "pantry_dry": "pantry"}


def _num(v, default=None):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def normalize(raw: dict) -> dict | None:
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    category = raw.get("category") if raw.get("category") in CATEGORIES else "other"
    storage = raw.get("storage")
    if storage not in ("fridge", "pantry", "freezer"):
        storage = _DEFAULT_STORAGE.get(category, "fridge")
    exp, src = expiry.predict(category, storage)
    out = {
        "name": name, "category": category, "storage": storage,
        "quantity": _num(raw.get("quantity"), 1.0), "unit": str(raw.get("unit") or "piece"),
        "est_price": _num(raw.get("est_price") if "est_price" in raw else raw.get("price")),
        "predicted_expiry": exp.isoformat(), "expiry_source": src,
    }
    for k in ("confidence", "freshness", "bbox", "barcode", "brand"):
        if k in raw:
            out[k] = raw[k]
    return out


def normalize_all(raws) -> list[dict]:
    return [c for c in (normalize(r) for r in raws if isinstance(r, dict)) if c]
