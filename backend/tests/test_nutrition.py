"""services/nutrition.clean_nutrition: shape, bounds and plausibility of the per-100 g nutrition object."""
import math

import pytest

from app.services.nutrition import clean_nutrition

APPLE = {"basis": "per_100g", "kcal": 52, "protein_g": 0.3, "carbs_g": 13.8, "fat_g": 0.2}
CORE = ("kcal", "protein_g", "carbs_g", "fat_g")


def good(**over):
    d = dict(APPLE)
    d.update(over)
    return d


def test_minimal_valid_is_normalised():
    out = clean_nutrition(APPLE)
    assert out == {"basis": "per_100g", "kcal": 52, "protein_g": 0.3, "carbs_g": 13.8, "fat_g": 0.2,
                   "estimated": True}
    assert isinstance(out["kcal"], int)


def test_basis_may_be_omitted():
    out = clean_nutrition({k: v for k, v in APPLE.items() if k != "basis"})
    assert out is not None and out["basis"] == "per_100g"


@pytest.mark.parametrize("basis", ["per_serving", "per_item", "", None, 100, "PER_100G"])
def test_other_basis_rejected(basis):
    assert clean_nutrition(good(basis=basis)) is None


def test_optional_keys_kept_and_rounded():
    out = clean_nutrition(good(fiber_g=2.44, sugar_g=10.0, sodium_mg=1))
    assert out["fiber_g"] == 2.4 and out["sugar_g"] == 10.0 and out["sodium_mg"] == 1.0
    assert all(isinstance(out[k], float) for k in ("protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg"))


def test_optional_null_is_left_out():
    out = clean_nutrition(good(fiber_g=None, sugar_g=None, sodium_mg=None))
    assert out is not None and not ({"fiber_g", "sugar_g", "sodium_mg"} & set(out))


@pytest.mark.parametrize("key,bad", [("fiber_g", "x"), ("fiber_g", -1), ("fiber_g", 100.5), ("sugar_g", True),
                                     ("sodium_mg", 40_001), ("sodium_mg", float("inf")), ("sodium_mg", [1])])
def test_invalid_optional_key_rejects_the_whole_object(key, bad):
    assert clean_nutrition(good(**{key: bad})) is None


def test_estimated_is_forced_true_and_unknown_keys_dropped():
    out = clean_nutrition(good(estimated=False, brand="Acme", source="gemini"))
    assert out["estimated"] is True
    assert "brand" not in out and "source" not in out


@pytest.mark.parametrize("raw", [None, [], "x", 5, True, 1.5, [APPLE]])
def test_non_object_is_none(raw):
    assert clean_nutrition(raw) is None


@pytest.mark.parametrize("key", CORE)
def test_missing_core_key_is_none(key):
    assert clean_nutrition({k: v for k, v in APPLE.items() if k != key}) is None


@pytest.mark.parametrize("key", CORE)
@pytest.mark.parametrize("bad", ["52", True, False, None, [], {}, math.nan, math.inf, -math.inf, -0.1])
def test_core_values_must_be_finite_non_negative_numbers(key, bad):
    assert clean_nutrition(good(**{key: bad})) is None


@pytest.mark.parametrize("over", [{"kcal": 901}, {"protein_g": 100.1}, {"carbs_g": 101}, {"fat_g": 100.1}])
def test_out_of_bounds_is_none(over):
    assert clean_nutrition(good(**over)) is None


def test_upper_bounds_are_inclusive_when_plausible():
    assert clean_nutrition({"kcal": 900, "protein_g": 0, "carbs_g": 0, "fat_g": 100}) is not None  # pure fat
    assert clean_nutrition({"kcal": 400, "protein_g": 0, "carbs_g": 100, "fat_g": 0}) is not None  # sugar


def test_water_and_other_zero_foods_are_valid():
    out = clean_nutrition({"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0})
    assert out is not None and out["kcal"] == 0


def test_macro_mass_cannot_exceed_105_g():
    over = {"kcal": 590, "protein_g": 40, "carbs_g": 40, "fat_g": 30}  # 110 g of macros in 100 g of food
    assert clean_nutrition(over) is None
    edge = {"kcal": 595, "protein_g": 35, "carbs_g": 35, "fat_g": 35}  # exactly 105 g
    assert clean_nutrition(edge) is not None


@pytest.mark.parametrize("kcal,ok", [(170, True), (120, True), (220, True), (100, False), (240, False), (500, False)])
def test_kcal_must_sit_near_the_atwater_estimate(kcal, ok):
    # 10 g each of protein, carbs and fat: 4*10 + 4*10 + 9*10 = 170 kcal; tolerance max(40 %, 30) = 68
    assert (clean_nutrition({"kcal": kcal, "protein_g": 10, "carbs_g": 10, "fat_g": 10}) is not None) is ok


def test_low_kcal_foods_get_the_absolute_slack():
    lettuce = {"kcal": 15, "protein_g": 1.4, "carbs_g": 2.9, "fat_g": 0.2}  # Atwater 19; fibre makes real kcal lower
    assert clean_nutrition(lettuce) is not None
    assert clean_nutrition({"kcal": 60, "protein_g": 0, "carbs_g": 0, "fat_g": 0}) is None  # 60 > 30 from 0


def test_ints_become_floats_and_kcal_is_rounded_to_int():
    out = clean_nutrition({"kcal": 51.6, "protein_g": 1, "carbs_g": 12, "fat_g": 0})
    assert out["kcal"] == 52 and isinstance(out["kcal"], int)
    assert out["protein_g"] == 1.0 and isinstance(out["protein_g"], float)


def test_cleaning_is_idempotent_so_an_echoed_candidate_round_trips():
    once = clean_nutrition(good(fiber_g=2.4, sugar_g=10.4, sodium_mg=1))
    assert clean_nutrition(once) == once


def test_input_is_not_mutated():
    raw = good(estimated=False)
    before = dict(raw)
    clean_nutrition(raw)
    assert raw == before
