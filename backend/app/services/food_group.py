"""User-facing food grouping (separate from the spoilage `category`).

`derive(category, name)` is the single heuristic: used at runtime (create / candidates) and
mirrored by migration 0003's backfill (the migration inlines a copy so it never breaks if this
module changes)."""
import re

FOOD_GROUPS = ("protein", "veggies", "fruit", "dairy", "grains", "pantry", "leftovers", "frozen", "other")

_FROM_CATEGORY = {
    "meat": "protein", "seafood": "protein", "eggs": "protein", "bakery": "grains",
    "pantry_dry": "pantry", "dairy": "dairy", "leftovers": "leftovers", "frozen": "frozen",
    "other": "other",
}

FRUIT_WORDS = frozenset("""
apple apples apricot apricots avocado avocados banana bananas berry berries blackberry blackberries
blueberry blueberries cantaloupe cherry cherries clementine clementines coconut cranberry cranberries
currant date dates fig figs grape grapes grapefruit guava honeydew kiwi kiwis lemon lemons lime limes
lychee mandarin mandarins mango mangos mangoes melon melons nectarine nectarines orange oranges papaya
passionfruit peach peaches pear pears persimmon pineapple pineapples plum plums pomegranate
pomegranates raspberry raspberries strawberry strawberries tangerine tangerines watermelon
""".split())

_WORD = re.compile(r"[a-z]+")


def is_fruit_name(name: str) -> bool:
    return any(w in FRUIT_WORDS for w in _WORD.findall((name or "").lower()))


def derive(category: str, name: str = "") -> str:
    if category in ("produce_leafy", "produce_hardy"):
        return "fruit" if is_fruit_name(name) else "veggies"
    return _FROM_CATEGORY.get(category, "other")


def derive_from_name(name: str) -> str:
    """For sources with no category (receipt lines)."""
    return "fruit" if is_fruit_name(name) else "other"


def valid(value) -> bool:
    return isinstance(value, str) and value in FOOD_GROUPS


def resolve(value, category: str, name: str) -> str:
    """Use `value` if it is a valid food group, else derive from category + name."""
    return value if valid(value) else derive(category, name)
