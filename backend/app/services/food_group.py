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


# --- name-only derivation (receipt lines have no category) -------------------------------------
# Receipt abbreviation -> canonical word (tokens are matched whole, lowercase, [a-z]+ only).
ABBREVIATIONS = {
    "chkn": "chicken", "chk": "chicken", "chix": "chicken", "ckn": "chicken",
    "bf": "beef", "grnd": "ground", "brd": "bread", "ygrt": "yogurt", "yogrt": "yogurt",
    "yog": "yogurt", "mozz": "mozzarella", "chs": "cheese", "chz": "cheese", "btr": "butter",
    "bcn": "bacon", "shrmp": "shrimp", "trky": "turkey", "tky": "turkey", "sausg": "sausage",
    "sasg": "sausage", "froz": "frozen", "frzn": "frozen", "frz": "frozen", "spag": "spaghetti",
    "oatml": "oatmeal", "crm": "cream",
    "strwb": "strawberry", "bnna": "banana", "avo": "avocado", "lettuc": "lettuce", "brocc": "broccoli", "spnch": "spinach", "crrt": "carrot",
    # receipt abbreviations also used by the pipeline (moved from pipeline/category_cleanup/abbreviations.json)
    "mlk": "milk", "skm": "skim", "whl": "whole", "grk": "greek", "brst": "breast", "stk": "steak",
    "prk": "pork", "saus": "sausage", "ched": "cheddar", "parm": "parmesan", "bttr": "butter",
    "bred": "bread", "tort": "tortilla", "tom": "tomato", "tmto": "tomato", "onin": "onion",
    "ltc": "lettuce", "lett": "lettuce", "broc": "broccoli", "caul": "cauliflower", "crt": "carrot",
    "crts": "carrots", "cuc": "cucumber", "cuke": "cucumber", "strawb": "strawberry",
    "grps": "grapes", "grp": "grapes", "avoc": "avocado", "appl": "apple", "aple": "apple",
    "orng": "orange", "lmn": "lemon", "lme": "lime", "mshrm": "mushroom", "mush": "mushroom",
    "shrms": "mushrooms", "pepr": "pepper", "zuc": "zucchini", "zucc": "zucchini",
    "papya": "papaya", "pnapl": "pineapple", "pinapl": "pineapple", "jce": "juice", "oj": "juice",
    "rce": "rice", "slmn": "salmon",
}

# Checked in this order; the first group with a matching token wins. Fruit sits after the
# dairy/protein/grains words so "strawberry yogurt" is dairy, but before veggies.
_FROZEN = frozenset({"frozen", "popsicle", "popsicles", "icecream", "gelato", "sorbet"})
# Words that make a line pantry even if a fruit/dairy word is present (juice, sauces, spreads).
_PANTRY_FIRST = frozenset("""
juice juices sauce sauces applesauce broth stock soup soups jam jelly jelly preserves syrup salsa
ketchup mustard mayo mayonnaise dressing vinaigrette seasoning spice spices hummus
""".split())
DAIRY_WORDS = frozenset("""
milk cheese cheeses yogurt yoghurt butter cream creamer kefir cheddar mozzarella parmesan gouda
swiss provolone feta brie ricotta mascarpone halfandhalf curd custard
""".split())
PROTEIN_WORDS = frozenset("""
chicken beef pork turkey ham bacon sausage sausages hotdog hotdogs egg eggs fish salmon tuna shrimp
tofu tempeh steak ribeye sirloin brisket lamb veal duck chorizo pepperoni salami jerky meatball
meatballs patty patties cod tilapia crab lobster scallop scallops sardines anchovies prawns wings
thighs drumstick lunchmeat brat bratwurst
""".split())
GRAINS_WORDS = frozenset("""
bread bagel bagels bun buns roll rolls baguette brioche pita naan tortilla rice pasta spaghetti penne
macaroni noodle noodles ramen couscous quinoa cereal cheerios granola oats oatmeal flour cracker
crackers pretzel pretzels waffle waffles pancake muffin muffins croissant cornbread barley
fettuccine linguine ravioli lasagna
""".split())
# Common vegetables. Receipts carry no category, so this is the only way to reach "veggies".
VEG_WORDS = frozenset("""
carrot carrots broccoli cauliflower spinach kale lettuce romaine cabbage celery onion onions scallion
scallions leek garlic ginger potato potatoes yam yams tomato tomatoes cucumber cucumbers zucchini squash
pepper peppers jalapeno jalapenos mushroom mushrooms corn peas asparagus beet beets radish radishes
turnip eggplant cilantro parsley basil mint dill arugula chard bok choy salad greens celery pumpkin
artichoke brussels sprouts sprout cress okra fennel
""".split())
PANTRY_WORDS = frozenset("""
beans bean lentils lentil chickpeas oil sugar salt honey peanut almonds almond nuts walnuts pecans
cashews seeds chia coffee tea cocoa vinegar pickles pickle olives chips snacks cookies cookie candy
chocolate bars cake mix vanilla baking soda
""".split())

_GROUP_ORDER = (("frozen", _FROZEN), ("pantry", _PANTRY_FIRST), ("dairy", DAIRY_WORDS),
                ("protein", PROTEIN_WORDS), ("grains", GRAINS_WORDS), ("fruit", FRUIT_WORDS),
                ("veggies", VEG_WORDS), ("pantry", PANTRY_WORDS))
# Two-word phrases whose meaning differs from either word alone.
_PHRASES = (("ice cream", "frozen"), ("peanut butter", "pantry"), ("almond butter", "pantry"),
            ("cashew butter", "pantry"), ("apple butter", "pantry"), ("cream cheese", "dairy"),
            ("sour cream", "dairy"), ("cottage cheese", "dairy"), ("pot pie", "frozen"))


def _tokens(name: str) -> list[str]:
    out = []
    for t in _WORD.findall((name or "").lower()):
        t = ABBREVIATIONS.get(t, t)
        out.append(t)
    return out


def derive_from_name(name: str) -> str:
    """Deterministic keyword match on whole tokens, for sources with no category (receipt lines).
    Falls back to "other"."""
    toks = _tokens(name)
    if not toks:
        return "other"
    joined = " " + " ".join(toks) + " "
    for phrase, group in _PHRASES:
        if f" {phrase} " in joined:
            return group
    # also try a naive singular ("pears" is already listed, but "tortillas" -> "tortilla")
    cand = set(toks) | {t[:-1] for t in toks if len(t) > 3 and t.endswith("s")}
    for group, words in _GROUP_ORDER:
        if cand & words:
            return group
    return "other"


def valid(value) -> bool:
    return isinstance(value, str) and value in FOOD_GROUPS


def resolve(value, category: str, name: str) -> str:
    """Use `value` if it is a valid food group, else derive from category + name."""
    return value if valid(value) else derive(category, name)
