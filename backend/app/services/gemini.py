"""Single seam for every Gemini call. Tests monkeypatch the module-level functions
(`parse_text`, `suggest_recipes`, `detect_from_image`, `estimate_shelf_life`).
All raise UpstreamError when the key is missing or the call fails."""
import json
import logging
import time

from flask import current_app

from ..models import CATEGORIES, FOOD_GROUPS


usage_log = logging.getLogger("app.gemini.usage")
if not usage_log.handlers:  # gunicorn's root logger drops INFO; give this logger its own handler
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    usage_log.addHandler(_h)
    usage_log.setLevel(logging.INFO)
    usage_log.propagate = False


def _tok(usage, attr):
    v = getattr(usage, attr, None) if usage is not None else None
    return v if isinstance(v, int) else None


def _log_usage(model, purpose, started, status, resp=None):
    """One INFO line per Gemini call: key=value, no prompt/response text, no user data, no key."""
    try:
        usage = getattr(resp, "usage_metadata", None)
        tin, tout, ttl = (_tok(usage, "prompt_token_count"), _tok(usage, "candidates_token_count"),
                          _tok(usage, "total_token_count"))
        think = _tok(usage, "thoughts_token_count")  # billed as output but reported separately
        if think and tout is not None:
            tout += think
        f = lambda v: "null" if v is None else v  # noqa: E731
        usage_log.info("gemini_usage model=%s purpose=%s input_tokens=%s output_tokens=%s "
                       "total_tokens=%s latency_ms=%d status=%s", model, purpose, f(tin), f(tout),
                       f(ttl), int((time.monotonic() - started) * 1000), status)
    except Exception:  # logging must never break a request
        pass


class UpstreamError(Exception):
    pass


# Gemini answers 503 UNAVAILABLE ("model is experiencing high demand") or 429 RESOURCE_EXHAUSTED in
# bursts. One short wait and retry rescues most of them; anything else fails fast.
RETRY_DELAYS_S = (1.5,)
_TRANSIENT = ("UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED")


def _is_transient(e: Exception) -> bool:
    code = getattr(e, "code", None)
    return code in (429, 503, 504) or any(t in str(e)[:300] for t in _TRANSIENT)


def is_configured() -> bool:
    return bool(current_app.config.get("GEMINI_API_KEY"))


def _as_list(data, list_key):
    """The usable list in a parsed response: a top-level list, or `data[list_key]` (a missing key
    means "nothing found" -> []). Any other shape raises, so `_generate` reports it as an upstream
    error (BE-13) instead of a caller crashing with a 500."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and list_key is not None:
        inner = data.get(list_key, [])
        if isinstance(inner, list):
            return inner
        raise ValueError(f"Gemini '{list_key}' is {type(inner).__name__}, not a list")
    raise ValueError(f"Gemini returned {type(data).__name__}, not a JSON list/object")


def _unwrap(data, list_key):
    """Callers re-apply `_as_list` (a no-op on `_generate`'s list) so a stubbed `_generate` returning a
    wrapped object or a bad shape still behaves: unusable -> UpstreamError, never a 500."""
    try:
        return _as_list(data, list_key)
    except ValueError as e:
        raise UpstreamError(f"Gemini returned an unusable response: {e}") from e


def _generate(contents, schema_hint: str, response_schema=None, purpose: str = "generate",
              list_key: str | None = None):
    """Parsed JSON as a list (see `_as_list`). A scalar (null, string, number, bool) or an unusable
    shape is an UpstreamError, logged as exactly one `status=error` usage line."""
    key = current_app.config.get("GEMINI_API_KEY")
    model = current_app.config.get("GEMINI_MODEL")
    if not key or not model:
        raise UpstreamError("Gemini is not configured (GEMINI_API_KEY / GEMINI_MODEL).")
    started, resp = time.monotonic(), None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json", system_instruction=schema_hint,
            **({"response_schema": response_schema} if response_schema else {}))
        for delay in (*RETRY_DELAYS_S, None):
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
                break
            except Exception as e:  # retried only if transient; the usage line is still one per call
                if delay is None or not _is_transient(e):
                    raise
                time.sleep(delay)
        data = _as_list(json.loads(resp.text), list_key)
    except Exception as e:  # SDK/network/JSON errors all mean "upstream failed"
        _log_usage(model, purpose, started, "error", resp)
        raise UpstreamError(f"Gemini request failed: {type(e).__name__}") from e
    _log_usage(model, purpose, started, "ok", resp)
    return data


# Same buckets as ml/yolo/taxonomy.CLASS_CATEGORY, so Gemini and the YOLO path agree on shelf life.
CATEGORY_GUIDE = (
    "Categories: produce_leafy = SHORT-life produce (leafy greens, herbs, berries, grapes, tomatoes, "
    "cucumbers, peppers, zucchini, mushrooms, bananas, mangoes, peaches, avocados, papaya, pineapple); "
    "produce_hardy = LONG-life produce (apples, citrus, pears, pomegranates, carrots, potatoes, onions, "
    "garlic, ginger, beets, eggplant); dairy; meat; seafood; bakery; eggs; leftovers (cooked or prepared "
    "food); pantry_dry (shelf-stable dry or canned); frozen; other (drinks, sauces, anything else). ")

_ITEM_SCHEMA = (
    CATEGORY_GUIDE +
    "Return JSON: a list of objects {name:str, category:one of %s, food_group:one of %s, "
    "storage:fridge|pantry|freezer, quantity:number, unit:str, est_price:number|null}. "
    "food_group is the user-facing grouping (fruit vs veggies, protein, dairy, grains, pantry...)."
    % (", ".join(CATEGORIES), ", ".join(FOOD_GROUPS))
)


def parse_text(text: str) -> list[dict]:
    return _unwrap(_generate(f"Extract the grocery/food items from this text:\n{text}", _ITEM_SCHEMA,
                             purpose="parse_text", list_key="items"), "items")


def detect_from_image(image: bytes, mime: str, mode: str) -> list[dict]:
    from google.genai import types

    hint = (CATEGORY_GUIDE +
            "Identify the food items in the photo and whether each looks fresh, semi-fresh (use soon) or spoiled. "
            "Return JSON: a list of {name:str, category:one of %s, food_group:one of %s, "
            "confidence:number 0-1, freshness:fresh|semi_fresh|spoiled}." % (", ".join(CATEGORIES), ", ".join(FOOD_GROUPS)))
    part = types.Part.from_bytes(data=image, mime_type=mime)
    prompt = "Single item close-up." if mode == "single" else "Fridge/pantry shelf photo."
    return _unwrap(_generate([part, prompt], hint, purpose="detect", list_key="candidates"), "candidates")


_RECEIPT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "display_name": {"type": "string"},
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "food_group": {"type": "string", "enum": list(FOOD_GROUPS)},
            "storage": {"type": "string", "enum": ["fridge", "pantry", "freezer"]},
        },
        "required": ["display_name", "category", "food_group", "storage"],
    },
}


def categorize_receipt_lines(names: list[str]) -> list[dict]:
    """One call per receipt: abbreviated receipt names -> [{display_name, category, food_group,
    storage}], same order and length as `names` (padded with {} if Gemini returns fewer)."""
    hint = (CATEGORY_GUIDE +
            "You get grocery receipt line names, often abbreviated (GV 2% MLK GAL, CHKN BRST). For each, "
            "return one object in the same order: display_name (plain readable product name without brand "
            "codes, sizes or prices, e.g. '2% milk'), category, food_group, storage (where it is kept at home).")
    data = _unwrap(_generate(json.dumps(names), hint, _RECEIPT_SCHEMA, purpose="receipt_categorize",
                             list_key="items"), "items")
    data = [d if isinstance(d, dict) else {} for d in data][: len(names)]
    return data + [{}] * (len(names) - len(data))


_RECIPE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "minutes": {"type": "integer"},
            "servings": {"type": "integer", "description": "How many people the recipe serves."},
            "uses_items": {"type": "array", "items": {"type": "string"}},
            "missing_items": {"type": "array", "items": {"type": "string"}},
            "steps": {"type": "array", "items": {"type": "string"}},
            "macros": {
                "type": "object",
                "description": "Estimated nutrition per serving.",
                "properties": {
                    "kcal": {"type": "integer"},
                    "protein_g": {"type": "number"},
                    "carbs_g": {"type": "number"},
                    "fat_g": {"type": "number"},
                },
                "required": ["kcal", "protein_g", "carbs_g", "fat_g"],
            },
        },
        "required": ["title", "minutes", "servings", "uses_items", "missing_items", "steps", "macros"],
    },
}


def suggest_recipes(items: list[dict], max_results: int, dietary: list[str]) -> list[dict]:
    hint = ("Suggest recipes that use up the soonest-expiring items first. Return JSON: a list of "
            "{title:str, minutes:int, servings:int, uses_items:[str] (names exactly as given in the input), "
            "missing_items:[str], steps:[str], "
            "macros:{kcal:int, protein_g:number, carbs_g:number, fat_g:number} (estimated per serving)}.")
    prompt = json.dumps({"items_soonest_expiring_first": items, "max_results": max_results,
                         "dietary": dietary})
    return _unwrap(_generate(prompt, hint, _RECIPE_SCHEMA, purpose="recipes", list_key="recipes"),
                   "recipes")[:max_results]


def estimate_shelf_life(items: list[dict]) -> list[int | None]:
    """Days until expiry for each {name, category, storage}; None where unknown."""
    hint = "Return JSON: a list of integers (days of shelf life), one per input item, in order."
    data = _unwrap(_generate(json.dumps(items), hint, purpose="shelf_life", list_key="days"), "days")
    return [d if isinstance(d, int) and 0 <= d <= 3650 else None for d in data][: len(items)]
