"""Pure-function parity contract between photo and receipt candidate normalization."""
from datetime import date

import pytest

from app.services import candidates


@pytest.fixture(autouse=True)
def _clean():
    """Pure-function module: overrides conftest's DB-truncating autouse fixture so no database is needed."""
    yield


_COMMON = (
    "category", "food_group", "storage", "predicted_expiry", "expiry_source",
    "quantity", "unit", "est_price",
)


def _pair(photo_name, photo_category, food_group, receipt_name, *, receipt_category=None,
          receipt_group=None, receipt_storage=None, receipt_quantity=2, receipt_price="3.49"):
    photo = candidates.normalize_all([{
        "name": photo_name, "category": photo_category, "food_group": food_group,
        "storage": receipt_storage, "quantity": receipt_quantity, "unit": "piece",
        "est_price": float(receipt_price), "freshness": "fresh", "confidence": 0.91,
        "bbox": [1.0, 2.0, 3.0, 4.0],
    }], "yolo")[0]
    enriched = None
    if receipt_category is not None:
        enriched = [{"category": receipt_category, "food_group": receipt_group,
                     "storage": receipt_storage, "unit": "piece"}]
    receipt = candidates.from_receipt_lines([{
        "name": receipt_name, "quantity": receipt_quantity, "price": receipt_price,
    }], enriched)[0]
    return photo, receipt


@pytest.mark.parametrize("photo_name,category,group,receipt_name", [
    ("banana", "produce_leafy", "fruit", "ORG BANANAS"),
    ("strawberry", "produce_leafy", "fruit", "Strawberries"),
    ("spinach", "produce_leafy", "veggies", "Spinach"),
    ("broccoli", "produce_leafy", "veggies", "Broccoli"),
    ("milk", "dairy", "dairy", "GV 2% MILK GAL"),
    ("cheese", "dairy", "dairy", "Cheddar cheese"),
    ("egg", "eggs", "protein", "Eggs"),
    ("chicken", "meat", "protein", "CHKN BRST"),
    ("beef", "meat", "protein", "Ground beef"),
    ("fish", "seafood", "protein", "Salmon"),
    ("bread", "bakery", "grains", "Bread"),
    ("frozen_food", "frozen", "frozen", "Frozen peas"),
    ("canned_food", "pantry_dry", "pantry", "Almonds"),
])
def test_shared_fields_match_for_equivalent_receipt_and_photo_inputs(photo_name, category, group, receipt_name):
    photo, receipt = _pair(photo_name, category, group, receipt_name,
                           receipt_category=category, receipt_group=group,
                           receipt_storage="fridge")
    for key in _COMMON:
        assert photo[key] == receipt[key]
        assert type(photo[key]) is type(receipt[key])


def test_path_specific_fields_are_exact_and_documented():
    photo, receipt = _pair("milk", "dairy", "dairy", "GV 2% MILK GAL",
                           receipt_category="dairy", receipt_group="dairy", receipt_storage="fridge")
    assert set(photo) == {"name", *_COMMON, "freshness", "confidence", "bbox"}
    assert set(receipt) == {"name", *_COMMON, "receipt_text", "price"}
    assert photo["freshness"] == "fresh"
    assert photo["confidence"] == 0.91
    assert photo["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert receipt["receipt_text"] == "GV 2% MILK GAL"
    assert receipt["price"] == receipt["est_price"] == 3.49
    assert type(photo["quantity"]) is float
    assert type(receipt["quantity"]) is float


@pytest.mark.xfail(strict=True, reason="PARITY-1: name-only receipt category maps apples to produce_leafy; improve category_from_name in backend/app/services/candidates.py")
def test_receipt_apple_matches_yolo_hardy_category():
    photo, receipt = _pair("apple", "produce_hardy", "fruit", "Apples")
    assert photo["category"] == receipt["category"] == "produce_hardy"


@pytest.mark.xfail(strict=True, reason="PARITY-2: name-only receipt category maps carrots to produce_leafy; improve category_from_name in backend/app/services/candidates.py")
def test_receipt_carrot_matches_yolo_hardy_category():
    photo, receipt = _pair("carrot", "produce_hardy", "veggies", "Carrots")
    assert photo["category"] == receipt["category"] == "produce_hardy"


@pytest.mark.xfail(strict=True, reason="PARITY-3: receipt rice is inferred as bakery/fridge instead of pantry_dry/pantry; improve category_from_name in backend/app/services/candidates.py")
def test_receipt_rice_matches_yolo_pantry_category_and_storage():
    photo, receipt = _pair("rice", "pantry_dry", "grains", "Rice", receipt_storage="pantry")
    assert (photo["category"], photo["storage"], photo["food_group"]) == (
        receipt["category"], receipt["storage"], receipt["food_group"]
    ) == ("pantry_dry", "pantry", "grains")


def test_expiry_values_are_dates_serialized_as_iso_strings():
    photo, receipt = _pair("milk", "dairy", "dairy", "GV 2% MILK GAL",
                           receipt_category="dairy", receipt_group="dairy", receipt_storage="fridge")
    assert date.fromisoformat(photo["predicted_expiry"]).isoformat() == photo["predicted_expiry"]
    assert date.fromisoformat(receipt["predicted_expiry"]).isoformat() == receipt["predicted_expiry"]

