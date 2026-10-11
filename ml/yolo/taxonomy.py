"""Single source of truth for detector class names and backend categories.

Pure stdlib. Imported by prepare_dataset.py, infer.py, export_predictions.py AND ml/serve.
Backend categories (fixed by docs/API.md / backend): produce_leafy, produce_hardy, dairy, meat,
seafood, bakery, eggs, leftovers, pantry_dry, frozen, other.
"""
from __future__ import annotations
import re

CATEGORIES = ("produce_leafy", "produce_hardy", "dairy", "meat", "seafood", "bakery",
              "eggs", "leftovers", "pantry_dry", "frozen", "other")

# canonical detector class name -> backend category. ORDER = class id order in data.yaml. Append only.
CLASS_CATEGORY: dict[str, str] = {
    # leafy / soft produce (short shelf life)
    "lettuce": "produce_leafy", "spinach": "produce_leafy", "kale": "produce_leafy",
    "cabbage": "produce_leafy", "broccoli": "produce_leafy", "cauliflower": "produce_leafy",
    "herbs": "produce_leafy", "strawberry": "produce_leafy", "grapes": "produce_leafy",
    "tomato": "produce_leafy", "cucumber": "produce_leafy", "bell_pepper": "produce_leafy",
    "zucchini": "produce_leafy", "mushroom": "produce_leafy", "banana": "produce_leafy",
    "mango": "produce_leafy", "peach": "produce_leafy", "avocado": "produce_leafy",
    # hardy produce (longer shelf life)
    "apple": "produce_hardy", "orange": "produce_hardy", "lemon": "produce_hardy",
    "lime": "produce_hardy", "carrot": "produce_hardy", "potato": "produce_hardy",
    "sweet_potato": "produce_hardy", "onion": "produce_hardy", "garlic": "produce_hardy",
    "pear": "produce_hardy", "pomegranate": "produce_hardy", "eggplant": "produce_hardy",
    "beetroot": "produce_hardy", "ginger": "produce_hardy",
    # non-produce
    "milk": "dairy", "cheese": "dairy", "yogurt": "dairy", "butter": "dairy", "cream": "dairy",
    "egg": "eggs",
    "chicken": "meat", "beef": "meat", "pork": "meat", "sausage": "meat", "bacon": "meat",
    "ham": "meat",
    "fish": "seafood", "shrimp": "seafood",
    "bread": "bakery", "tortilla": "bakery",
    "leftovers": "leftovers",
    "pasta": "pantry_dry", "rice": "pantry_dry", "canned_food": "pantry_dry",
    "juice": "other", "soda": "other", "sauce": "other", "bottle": "other",
    "frozen_food": "frozen",
    # appended 2026-10-10 for AgriFreshNET (soft, short-life produce -> produce_leafy, 5 d in expiry.py)
    "papaya": "produce_leafy", "pineapple": "produce_leafy", "bitter_melon": "produce_leafy",
}
FOOD_GROUPS = ("protein", "veggies", "fruit", "dairy", "grains", "pantry", "leftovers", "frozen", "other")

# detector class -> user-facing food group (separate from the spoilage category above).
CLASS_FOOD_GROUP: dict[str, str] = {
    "lettuce": "veggies", "spinach": "veggies", "kale": "veggies", "cabbage": "veggies",
    "broccoli": "veggies", "cauliflower": "veggies", "herbs": "veggies", "strawberry": "fruit",
    "grapes": "fruit", "tomato": "veggies", "cucumber": "veggies", "bell_pepper": "veggies",
    "zucchini": "veggies", "mushroom": "veggies", "banana": "fruit", "mango": "fruit",
    "peach": "fruit", "avocado": "fruit",
    "apple": "fruit", "orange": "fruit", "lemon": "fruit", "lime": "fruit", "carrot": "veggies",
    "potato": "veggies", "sweet_potato": "veggies", "onion": "veggies", "garlic": "veggies",
    "pear": "fruit", "pomegranate": "fruit", "eggplant": "veggies", "beetroot": "veggies",
    "ginger": "veggies",
    "milk": "dairy", "cheese": "dairy", "yogurt": "dairy", "butter": "dairy", "cream": "dairy",
    "egg": "protein",
    "chicken": "protein", "beef": "protein", "pork": "protein", "sausage": "protein",
    "bacon": "protein", "ham": "protein",
    "fish": "protein", "shrimp": "protein",
    "bread": "grains", "tortilla": "grains",
    "leftovers": "leftovers",
    "pasta": "grains", "rice": "grains", "canned_food": "pantry",
    "juice": "other", "soda": "other", "sauce": "pantry", "bottle": "other",
    "frozen_food": "frozen",
    "papaya": "fruit", "pineapple": "fruit", "bitter_melon": "veggies",
}
assert set(CLASS_FOOD_GROUP) == set(CLASS_CATEGORY), "CLASS_FOOD_GROUP must cover every class"
assert set(CLASS_FOOD_GROUP.values()) <= set(FOOD_GROUPS)

CLASS_NAMES: list[str] = list(CLASS_CATEGORY)
CLASS_ID: dict[str, int] = {n: i for i, n in enumerate(CLASS_NAMES)}

# source-dataset spellings -> canonical name (applied after normalize()).
ALIASES: dict[str, str] = {
    "apples": "apple", "bananas": "banana", "oranges": "orange", "tomatoes": "tomato",
    "potatoes": "potato", "cucumbers": "cucumber", "carrots": "carrot", "onions": "onion",
    "capsicum": "bell_pepper", "pepper": "bell_pepper", "bellpepper": "bell_pepper",
    "peppers": "bell_pepper", "bell_peppers": "bell_pepper", "strawberries": "strawberry",
    "grape": "grapes", "lemons": "lemon", "limes": "lime", "mangoes": "mango", "mangos": "mango",
    "eggs": "egg", "milk_carton": "milk", "milk_bottle": "milk", "yoghurt": "yogurt",
    "yogurt_cup": "yogurt", "cheddar": "cheese", "sausages": "sausage", "chicken_breast": "chicken",
    "steak": "beef", "ground_beef": "beef", "salmon": "fish", "loaf": "bread", "bread_loaf": "bread",
    "lettuces": "lettuce", "cabbages": "cabbage", "mushrooms": "mushroom", "zucchinis": "zucchini",
    "courgette": "zucchini", "aubergine": "eggplant", "brinjal": "eggplant", "beet": "beetroot",
    "can": "canned_food", "cans": "canned_food", "tin": "canned_food", "juice_box": "juice",
    "juice_carton": "juice", "soft_drink": "soda", "coke": "soda", "sauce_bottle": "sauce",
    "ketchup": "sauce", "mayonnaise": "sauce", "container": "leftovers", "tupperware": "leftovers",
    "pomegranates": "pomegranate", "peaches": "peach", "pears": "pear", "avocados": "avocado",
    "sweetpotato": "sweet_potato", "bittergourd": "bitter_melon", "bitter_gourd": "bitter_melon",
    "bittermelon": "bitter_melon", "karela": "bitter_melon", "papayas": "papaya", "pineapples": "pineapple",
    "eggplants": "eggplant", "okra": "other",
}
# Freshness classes (output values). Sidecar codes are FRESHNESS_CODE (0/1 kept for old data).
FRESHNESS = ("fresh", "semi_fresh", "spoiled")
FRESHNESS_CODE = {"fresh": 0, "spoiled": 1, "semi_fresh": 2}  # freshness/<split>/*.txt sidecar values
SEMI_WORDS = ("semi_fresh", "semifresh", "semi", "half_fresh", "halffresh", "medium_fresh")
SPOILED_WORDS = ("rotten", "rotting", "spoiled", "spoilt", "stale", "bad", "defective", "decayed",
                 "mouldy", "moldy", "mold", "mould", "damaged", "overripe", "unhealthy")
FRESH_WORDS = ("fresh", "good", "healthy", "ripe", "unripe")

_DAY_RANGE = re.compile(r"\(\s*\d+\s*-\s*\d+\s*\)\s*$")


def normalize(s: str) -> str:
    """'Semi fresh Pineapple (15-25)' -> 'semi_fresh_pineapple' (trailing day ranges dropped)."""
    s = _DAY_RANGE.sub("", s.strip())
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def split_freshness(raw: str) -> tuple[str, str | None]:
    """'rotten_apple' / 'freshapples' / 'Apple__Rotten' -> ('apple', 'spoiled');
    'Semi fresh banana(4-7)' / 'Semi_Fresh eggplant' -> ('banana'|'eggplant', 'semi_fresh'); no marker -> (name, None).
    Semi words are checked first, else 'semi fresh X' would read as fresh 'semi_X'."""
    n = normalize(raw)
    freshness = None
    for w in SEMI_WORDS + SPOILED_WORDS + FRESH_WORDS:
        label = "semi_fresh" if w in SEMI_WORDS else "spoiled" if w in SPOILED_WORDS else "fresh"
        if w == "semi":  # bare 'semi' only counts when followed by a fresh word ('semi_ripe')
            m = re.search(r"(^|_)semi_?(?:fresh|ripe)(_|$)", n)
            if m:
                freshness, n = label, (n[:m.start()] + "_" + n[m.end():]).strip("_")
                break
            continue
        pat = re.compile(rf"(^|_){w}(_|$)")
        if pat.search(n):
            freshness = label
            n = pat.sub("_", n).strip("_")
            break
        # glued forms: rottenapples, freshbanana
        if n.startswith(w) and len(n) > len(w):
            freshness = label
            n = n[len(w):].strip("_")
            break
    return n, freshness


def canonical_name(raw: str) -> str | None:
    """Map a source label to a canonical class, or None if we do not model it."""
    n = normalize(raw)
    if n in CLASS_CATEGORY:
        return n
    n = ALIASES.get(n, n)
    return n if n in CLASS_CATEGORY else None


def category_for(name: str) -> str:
    return CLASS_CATEGORY.get(normalize(name), "other")


def food_group_for(name: str) -> str:
    return CLASS_FOOD_GROUP.get(normalize(name), "other")
