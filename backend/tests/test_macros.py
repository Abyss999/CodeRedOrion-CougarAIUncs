"""/recipes/suggest macros. Gemini is stubbed one level down (gemini._generate) so real sanitising code runs."""
import pytest

from app.services import gemini

GOOD = {"kcal": 450, "protein_g": 30.5, "carbs_g": 40, "fat_g": 15}


def recipe(**over):
    r = {"title": "Soup", "minutes": 20, "uses_items": ["Milk"], "missing_items": [], "steps": ["Boil"],
         "macros": dict(GOOD)}
    r.update(over)
    return r


@pytest.fixture
def stub(monkeypatch):
    def set_(recipes):
        monkeypatch.setattr(gemini, "_generate", lambda contents, hint, *a, **k: recipes)
    return set_


@pytest.fixture
def suggest(client, user, make_item):
    make_item(user)

    def go(**body):
        return client.post("/recipes/suggest", json=body, headers=user["headers"])
    return go


def test_valid_macros(stub, suggest):
    stub([recipe()])
    r = suggest()
    assert r.status_code == 200
    rec = r.get_json()["recipes"][0]
    assert rec["macros"] == {"kcal": 450, "protein_g": 30.5, "carbs_g": 40, "fat_g": 15}
    assert rec["macros_estimated"] is True
    assert rec["title"] == "Soup" and rec["steps"] == ["Boil"]


def test_valid_zero_macros_ok(stub, suggest):
    stub([recipe(macros={"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0})])
    assert suggest().get_json()["recipes"][0]["macros"] is not None


def test_missing_macros_null(stub, suggest):
    r0 = recipe(); del r0["macros"]
    stub([r0])
    r = suggest()
    assert r.status_code == 200 and r.get_json()["recipes"][0]["macros"] is None


BAD = [
    None, "450 kcal", 450, [], [450, 30, 40, 15], {},
    {"kcal": 450},  # missing keys
    {"kcal": 450, "protein_g": 30, "carbs_g": 40},  # missing fat
    {"kcal": "450", "protein_g": 30, "carbs_g": 40, "fat_g": 15},  # strings
    {"kcal": 450, "protein_g": "lots", "carbs_g": 40, "fat_g": 15},
    {"kcal": None, "protein_g": 30, "carbs_g": 40, "fat_g": 15},
    {"kcal": True, "protein_g": 30, "carbs_g": 40, "fat_g": 15},  # bool is not a number
    {"kcal": [450], "protein_g": 30, "carbs_g": 40, "fat_g": 15},
    {"kcal": -1, "protein_g": 30, "carbs_g": 40, "fat_g": 15},  # negative
    {"kcal": 450, "protein_g": -5, "carbs_g": 40, "fat_g": 15},
    {"kcal": 10**9, "protein_g": 30, "carbs_g": 40, "fat_g": 15},  # absurd
    {"kcal": 450, "protein_g": 10**6, "carbs_g": 40, "fat_g": 15},
    {"kcal": 450, "protein_g": 30, "carbs_g": 40, "fat_g": 10**6},
    {"kcal": float("nan"), "protein_g": 30, "carbs_g": 40, "fat_g": 15},
    {"kcal": float("inf"), "protein_g": 30, "carbs_g": 40, "fat_g": 15},
]


@pytest.mark.parametrize("bad", BAD, ids=[str(i) for i in range(len(BAD))])
def test_invalid_macros_null_never_500(stub, suggest, bad):
    stub([recipe(macros=bad)])
    r = suggest()
    assert r.status_code == 200, r.get_data(as_text=True)
    rec = r.get_json()["recipes"][0]
    assert rec["macros"] is None
    assert rec["title"] == "Soup"  # the recipe itself is kept


def test_mixed_recipes_independent(stub, suggest):
    stub([recipe(title="A"), recipe(title="B", macros="junk"), recipe(title="C")])
    recs = suggest(max_results=3).get_json()["recipes"]
    assert [r["title"] for r in recs] == ["A", "B", "C"]
    assert recs[0]["macros"] and recs[1]["macros"] is None and recs[2]["macros"]


def test_extra_macro_keys_dropped_or_kept_but_valid(stub, suggest):
    stub([recipe(macros=dict(GOOD, sodium_mg=500))])
    r = suggest()
    assert r.status_code == 200
    m = r.get_json()["recipes"][0]["macros"]
    assert m is None or {"kcal", "protein_g", "carbs_g", "fat_g"} <= set(m)


def test_stubbed_suggest_recipes_passthrough_does_not_500(client, user, make_item, monkeypatch):
    """Even if the service layer is stubbed with raw recipes lacking/garbling macros, the route must not 500."""
    make_item(user)
    monkeypatch.setattr(gemini, "suggest_recipes", lambda items, n, d: [
        {"title": "X", "minutes": 5, "uses_items": [], "missing_items": [], "steps": [], "macros": {"kcal": "x"}},
        {"title": "Y"}])
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 200
    for rec in r.get_json()["recipes"]:
        assert "macros" in rec and (rec["macros"] is None or isinstance(rec["macros"], dict))


def test_wrapped_recipes_object_form(stub, suggest):
    stub({"recipes": [recipe()]})
    assert suggest().get_json()["recipes"][0]["macros"]["kcal"] == 450


def test_non_dict_recipe_entries_do_not_500(stub, suggest):
    stub(["junk", 5, None, recipe()])
    r = suggest()
    assert r.status_code in (200, 502)  # must be a handled response, never 500
    if r.status_code == 200:
        assert all(isinstance(x, dict) for x in r.get_json()["recipes"])
