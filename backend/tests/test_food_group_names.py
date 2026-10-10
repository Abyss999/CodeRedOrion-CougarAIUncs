"""BE-2: food_group.derive_from_name keyword tables + receipt abbreviations."""
import io

import pytest

from app.services import food_group, ml

GROUPS = ["protein", "veggies", "fruit", "dairy", "grains", "pantry", "leftovers", "frozen", "other"]

# (receipt-style name, expected group). Names marked (fx) come from ml/eval/fixtures/receipts.
NAMES = [
    ("GV WHL MILK GAL", "dairy"),            # fx
    ("KS ORG EGGS", "protein"),
    ("KS ORG EGGS 24CT", "protein"),         # fx
    ("GV LARGE EGG 18", "protein"),          # fx
    ("CHKN BRST", "protein"),
    ("CHKN BRST BNLS", "protein"),           # fx
    ("WHT BRD", "grains"),
    ("BREAD WHOLE WHEAT", "grains"),         # fx
    ("ORG BANANAS", "fruit"),
    ("BANANAS ORG", "fruit"),                # fx
    ("BABY SPINACH", "veggies"),
    ("SPINACH BABY", "veggies"),             # fx
    ("FRZN PEAS", "frozen"),
    ("FROZ PEAS 12OZ", "frozen"),            # fx
    ("Frozen Pizza Margherita", "frozen"),   # fx
    ("MILK 2% GAL", "dairy"),                # fx
    ("Whole Milk Gallon", "dairy"),          # fx
    ("BUTTER UNSALTED", "dairy"),            # fx
    ("GREEK YOGURT", "dairy"),               # fx
    ("SHREDDED CHEESE", "dairy"),            # fx
    ("SOUR CREAM", "dairy"),                 # fx
    ("Cottage Cheese 16oz", "dairy"),        # fx
    ("GROUND BEEF 80/20", "protein"),        # fx
    ("SALMON FILLET", "protein"),            # fx
    ("SHRIMP RAW 1LB", "protein"),           # fx
    ("Pork Chops Thick", "protein"),         # fx
    ("ROTISSERIE CHICKEN", "protein"),       # fx
    ("TOFU FIRM 14OZ", "protein"),           # fx
    ("ROMA TOMATOES", "veggies"),            # fx
    ("LETTUCE ROMAINE", "veggies"),          # fx
    ("ORG KALE BUNCH", "veggies"),           # fx
    ("BROCCOLI CROWN", "veggies"),           # fx
    ("STRAWBERRIES 2LB", "fruit"),           # fx
    ("Honeycrisp Apples", "fruit"),          # fx
    ("AVOCADO HASS", "fruit"),               # fx
    ("CANNED BLACK BEANS", "pantry"),        # fx
    ("Maple Syrup", "pantry"),               # fx
    ("PAPER TOWELS", "other"),               # fx
    ("GATORADE 28OZ", "other"),              # fx
]


@pytest.mark.parametrize("name,want", NAMES)
def test_receipt_names(name, want):
    assert food_group.derive_from_name(name) == want


def test_table_has_at_least_25_cases():
    assert len(NAMES) >= 25


@pytest.mark.parametrize("name", ["milk", "Milk", "MILK", "mIlK"])
def test_case_insensitive(name):
    assert food_group.derive_from_name(name) == "dairy"


@pytest.mark.parametrize("name", ["", "   ", None, "ZZQX WIDGET", "12345", "@@##", "XYZZY 3PK"])
def test_unknown_or_empty_defaults_to_other(name):
    assert food_group.derive_from_name(name) == "other"


@pytest.mark.parametrize("name", [
    "BUTTERNUT SQUASH",   # not butter
    "PEANUT BUTTER 16OZ",  # spread, not dairy butter
    "ALMOND BUTTER",
    "EGGPLANT",           # not eggs
    "MILKY WAY BAR",      # whole-token match only
    "JASMINE RICE 5LB",   # 'ice' substring must not mean frozen
    "PRICE ADJUSTMENT",   # 'rice' substring
    "HAMMER",             # 'ham' substring
    "CORNER STORE",       # 'corn' substring
    "PEASANT BREAD",      # 'peas' substring (grains is fine; veggies/frozen is not)
])
def test_no_substring_false_positives(name):
    got = food_group.derive_from_name(name)
    forbidden = {
        "BUTTERNUT SQUASH": {"dairy"}, "PEANUT BUTTER 16OZ": {"dairy"}, "ALMOND BUTTER": {"dairy"},
        "EGGPLANT": {"protein"}, "MILKY WAY BAR": {"dairy"}, "JASMINE RICE 5LB": {"frozen"},
        "PRICE ADJUSTMENT": {"grains", "pantry", "frozen"}, "HAMMER": {"protein"},
        "CORNER STORE": {"veggies", "grains", "pantry"}, "PEASANT BREAD": {"veggies", "frozen"},
    }[name]
    assert got not in forbidden, f"{name!r} -> {got}"


def test_pineapple_is_fruit_not_apple_confusion():
    assert food_group.derive_from_name("PINEAPPLE") == "fruit"
    assert food_group.derive_from_name("PINEAPPLE CHUNKS") == "fruit"


def test_apple_juice_and_creamer_return_valid_group():
    # Ambiguous by spec; only the contract (a valid group, never an exception) is asserted.
    for n in ("CREAMER", "COFFEE CREAMER", "ICE CREAM", "COCONUT MILK", "APPLE JUICE"):
        assert food_group.derive_from_name(n) in GROUPS


def test_return_always_valid_group_for_fixture_names():
    for n, _ in NAMES:
        assert food_group.valid(food_group.derive_from_name(n))


def _img():
    return {"image": (io.BytesIO(b"\xff\xd8\xff\xe0fake"), "r.jpg", "image/jpeg")}


def test_receipt_end_to_end_milk_eggs_not_other(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "ocr", lambda *a, **k: {"lines": [
        {"name": "GV WHL MILK GAL", "quantity": 1, "price": 3.5}, {"name": "KS ORG EGGS", "price": 4},
        {"name": "ORG BANANAS", "price": 1.2}, {"name": "ZZQX WIDGET", "price": 2}], "total": 10.7})
    r = client.post("/items/from-receipt", data=_img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200, r.get_data(as_text=True)
    got = {c["name"]: c["food_group"] for c in r.get_json()["candidates"]}
    assert got == {"GV WHL MILK GAL": "dairy", "KS ORG EGGS": "protein", "ORG BANANAS": "fruit",
                   "ZZQX WIDGET": "other"}


def test_receipt_plain_milk_and_eggs(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "ocr", lambda *a, **k: {"lines": [
        {"name": "Milk", "quantity": 2, "price": 3.5}, {"name": "Eggs", "price": 4}], "total": 11.0})
    r = client.post("/items/from-receipt", data=_img(), headers=user["headers"], content_type="multipart/form-data")
    got = {c["name"]: c["food_group"] for c in r.get_json()["candidates"]}
    assert got == {"Milk": "dairy", "Eggs": "protein"}
