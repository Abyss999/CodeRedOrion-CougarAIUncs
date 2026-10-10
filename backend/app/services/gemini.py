"""Single seam for every Gemini call. Tests monkeypatch the module-level functions
(`parse_text`, `suggest_recipes`, `detect_from_image`, `estimate_shelf_life`).
All raise UpstreamError when the key is missing or the call fails."""
import json

from flask import current_app

from ..models import CATEGORIES


class UpstreamError(Exception):
    pass


def is_configured() -> bool:
    return bool(current_app.config.get("GEMINI_API_KEY"))


def _generate(contents, schema_hint: str):
    key = current_app.config.get("GEMINI_API_KEY")
    model = current_app.config.get("GEMINI_MODEL")
    if not key or not model:
        raise UpstreamError("Gemini is not configured (GEMINI_API_KEY / GEMINI_MODEL).")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", system_instruction=schema_hint),
        )
        return json.loads(resp.text)
    except UpstreamError:
        raise
    except Exception as e:  # SDK/network/JSON errors all mean "upstream failed"
        raise UpstreamError(f"Gemini request failed: {type(e).__name__}") from e


_ITEM_SCHEMA = (
    "Return JSON: a list of objects {name:str, category:one of %s, storage:fridge|pantry|freezer, "
    "quantity:number, unit:str, est_price:number|null}." % ", ".join(CATEGORIES)
)


def parse_text(text: str) -> list[dict]:
    data = _generate(f"Extract the grocery/food items from this text:\n{text}", _ITEM_SCHEMA)
    return data if isinstance(data, list) else data.get("items", [])


def detect_from_image(image: bytes, mime: str, mode: str) -> list[dict]:
    from google.genai import types

    hint = ("Identify the food items in the photo and whether each looks fresh, semi-fresh (use soon) or spoiled. "
            "Return JSON: a list of {name:str, category:one of %s, confidence:number 0-1, "
            "freshness:fresh|semi_fresh|spoiled}." % ", ".join(CATEGORIES))
    part = types.Part.from_bytes(data=image, mime_type=mime)
    prompt = "Single item close-up." if mode == "single" else "Fridge/pantry shelf photo."
    data = _generate([part, prompt], hint)
    return data if isinstance(data, list) else data.get("candidates", [])


def suggest_recipes(items: list[dict], max_results: int, dietary: list[str]) -> list[dict]:
    hint = ("Suggest recipes that use up the soonest-expiring items first. Return JSON: a list of "
            "{title:str, minutes:int, uses_items:[str], missing_items:[str], steps:[str]}.")
    prompt = json.dumps({"items_soonest_expiring_first": items, "max_results": max_results,
                         "dietary": dietary})
    data = _generate(prompt, hint)
    data = data if isinstance(data, list) else data.get("recipes", [])
    return data[:max_results]


def estimate_shelf_life(items: list[dict]) -> list[int | None]:
    """Days until expiry for each {name, category, storage}; None where unknown."""
    hint = "Return JSON: a list of integers (days of shelf life), one per input item, in order."
    data = _generate(json.dumps(items), hint)
    return [d if isinstance(d, int) and 0 <= d <= 3650 else None for d in data][: len(items)]
