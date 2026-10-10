"""Open Food Facts barcode lookup."""
import requests

OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
TIMEOUT = 8

# substring of an OFF category tag -> app category (first match wins)
_CATEGORY_HINTS = [
    ("frozen", "frozen"), ("seafood", "seafood"), ("fish", "seafood"), ("meat", "meat"),
    ("poultry", "meat"), ("sausage", "meat"), ("egg", "eggs"), ("dairies", "dairy"),
    ("milk", "dairy"), ("cheese", "dairy"), ("yogurt", "dairy"), ("bread", "bakery"),
    ("bakery", "bakery"), ("salad", "produce_leafy"), ("lettuce", "produce_leafy"),
    ("spinach", "produce_leafy"), ("vegetable", "produce_hardy"), ("fruit", "produce_hardy"),
    ("pasta", "pantry_dry"), ("rice", "pantry_dry"), ("cereal", "pantry_dry"),
    ("canned", "pantry_dry"), ("snack", "pantry_dry"), ("flour", "pantry_dry"),
]


class BarcodeUpstreamError(Exception):
    pass


def category_from_tags(tags) -> str:
    joined = " ".join(tags or []).lower()
    for needle, cat in _CATEGORY_HINTS:
        if needle in joined:
            return cat
    return "other"


def lookup(code: str) -> dict | None:
    """Return a candidate dict or None if the product is unknown."""
    try:
        r = requests.get(OFF_URL.format(code=code), timeout=TIMEOUT,
                         headers={"User-Agent": "FoodWasteReducer/0.1 (hackathon)"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        body = r.json()
    except (requests.RequestException, ValueError) as e:
        raise BarcodeUpstreamError(type(e).__name__) from e
    if body.get("status") != 1 or not body.get("product"):
        return None
    p = body["product"]
    name = p.get("product_name") or p.get("generic_name") or p.get("brands")
    if not name:
        return None
    return {
        "name": name.strip(),
        "category": category_from_tags(p.get("categories_tags")),
        "brand": p.get("brands") or None,
        "barcode": code,
        "quantity_text": p.get("quantity") or None,
    }
