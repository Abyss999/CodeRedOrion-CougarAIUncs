"""Per-100 g nutrition of an item (`items.nutrition`, JSONB).

One validator shared by `POST /items` (a bad client value is a 400) and the Gemini enrichment path
(anything unusable becomes None, never an error). Shape, as served by the API:

    {"basis": "per_100g", "kcal": int, "protein_g": n, "carbs_g": n, "fat_g": n,
     "fiber_g"?: n, "sugar_g"?: n, "sodium_mg"?: n, "estimated": true}

The four core keys match the recipe `macros` object (which is per serving), so one UI component can
show both; only the basis differs. Values are estimates, so `estimated` is always true and is set
here, never taken from the input.
"""
import math

BASIS = "per_100g"
# Upper bound per 100 g of food (the lower bound is 0). Pure fat is 900 kcal; pure salt holds about
# 38,800 mg of sodium.
CORE_MAX = {"kcal": 900, "protein_g": 100, "carbs_g": 100, "fat_g": 100}
OPTIONAL_MAX = {"fiber_g": 100, "sugar_g": 100, "sodium_mg": 40_000}
# Plausibility: protein + carbs + fat cannot outweigh 100 g of food (5 g of slack for rounding), and
# kcal must sit near the Atwater estimate 4P + 4C + 9F. Fibre, alcohol and acids make real foods
# deviate, so the tolerance is the larger of 40 % and 30 kcal.
MACRO_MASS_MAX_G = 105
KCAL_REL_TOL = 0.40
KCAL_ABS_TOL = 30


def _number(value, hi):
    """A finite number in 0..hi, else None. Booleans and numeric strings are not numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if 0 <= value <= hi else None


def clean_nutrition(raw) -> dict | None:
    """The cleaned per-100 g nutrition object, or None when `raw` is unusable.

    All-or-nothing: a missing or invalid core key, a present-but-invalid optional key, another basis
    or an implausible combination gives None. An optional key that is null is left out. Unknown keys
    are dropped."""
    if not isinstance(raw, dict):
        return None
    if raw.get("basis", BASIS) != BASIS:
        return None
    out = {"basis": BASIS}
    for key, hi in CORE_MAX.items():
        v = _number(raw.get(key), hi)
        if v is None:
            return None
        out[key] = v
    for key, hi in OPTIONAL_MAX.items():
        if raw.get(key) is None:
            continue
        v = _number(raw[key], hi)
        if v is None:
            return None
        out[key] = v
    protein, carbs, fat = out["protein_g"], out["carbs_g"], out["fat_g"]
    if protein + carbs + fat > MACRO_MASS_MAX_G:
        return None
    atwater = 4 * protein + 4 * carbs + 9 * fat
    if abs(out["kcal"] - atwater) > max(KCAL_REL_TOL * atwater, KCAL_ABS_TOL):
        return None
    out["kcal"] = int(round(out["kcal"]))
    for key in ("protein_g", "carbs_g", "fat_g", *OPTIONAL_MAX):
        if key in out:
            out[key] = round(out[key], 1)
    out["estimated"] = True
    return out
