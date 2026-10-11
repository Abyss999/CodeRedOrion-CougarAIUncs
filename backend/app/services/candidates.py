"""Normalise raw candidates (ML / Gemini / OFF) and attach a predicted expiry."""
import logging

from ..models import CATEGORIES
from . import expiry, food_group

log = logging.getLogger(__name__)

FRESHNESS = ("fresh", "semi_fresh", "spoiled")
# Variant map, applied after lower-casing and collapsing space/hyphen/underscore runs to a single
# space. Mirrors SEMI_WORDS / SPOILED_WORDS in ml/yolo/taxonomy.py (keep in sync) so the same word
# never means different things in the two layers; "ripe" is deliberately NOT here (taxonomy: fresh).
# Anything not listed (or not one of FRESHNESS) falls back to "fresh" + WARNING.
_SEMI = ("semi fresh", "semifresh", "semi", "half fresh", "halffresh", "medium fresh", "use soon")
_SPOILED = ("rotten", "rotting", "spoilt", "stale", "bad", "defective", "decayed", "mouldy", "moldy",
            "mold", "mould", "damaged", "overripe", "unhealthy")
_FRESHNESS_ALIASES = {**{w: "semi_fresh" for w in _SEMI}, **{w: "spoiled" for w in _SPOILED}}

_DEFAULT_STORAGE = {"frozen": "freezer", "pantry_dry": "pantry"}


def _num(v, default=None):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def normalize_freshness(value, source: str = "unknown") -> str:
    """Map a raw freshness label to fresh|semi_fresh|spoiled.

    Unknown/missing values become "fresh" and log a WARNING with the (truncated) raw value and
    source; no user data is logged.
    """
    if isinstance(value, str):
        key = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
        if key in ("fresh", "semi fresh", "spoiled"):
            return key.replace(" ", "_")
        if key in _FRESHNESS_ALIASES:
            return _FRESHNESS_ALIASES[key]
    log.warning("freshness_fallback raw=%r source=%s -> fresh", str(value)[:40], source)
    return "fresh"


def normalize(raw: dict, source: str | None = None) -> dict | None:
    """`source` ("yolo"/"gemini"/...) marks a path that must carry freshness: it is always set.
    Without it, freshness is normalised only if the raw candidate included one."""
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    category = raw.get("category") if raw.get("category") in CATEGORIES else "other"
    storage = raw.get("storage")
    if storage not in ("fridge", "pantry", "freezer"):
        storage = _DEFAULT_STORAGE.get(category, "fridge")
    fg = food_group.resolve(raw.get("food_group"), category, name)
    exp, src = expiry.predict(category, storage)
    out = {
        "name": name, "category": category, "food_group": fg, "storage": storage,
        "quantity": _num(raw.get("quantity"), 1.0), "unit": str(raw.get("unit") or "piece"),
        "est_price": _num(raw.get("est_price") if "est_price" in raw else raw.get("price")),
        "predicted_expiry": exp.isoformat(), "expiry_source": src,
    }
    for k in ("confidence", "bbox", "barcode", "brand"):
        if k in raw:
            out[k] = raw[k]
    if source is not None or "freshness" in raw:
        out["freshness"] = normalize_freshness(raw.get("freshness"), source or "other")
    return out


def normalize_all(raws, source: str | None = None) -> list[dict]:
    return [c for c in (normalize(r, source) for r in raws if isinstance(r, dict)) if c]
