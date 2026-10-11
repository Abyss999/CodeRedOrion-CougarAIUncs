import pytest

from pipeline.category_cleanup.names import clean
import taxonomy as T


@pytest.mark.parametrize("text,canon,cat,match", [
    ("GV 2% MLK GAL", "milk", "dairy", None),
    ("CHKN BRST", "chicken", "meat", None),
    ("HONEY NUT CEREAL", None, "pantry_dry", "keyword"),
    ("JIF PEANUT BUTTER", None, "pantry_dry", None),
    ("XQZT 4411", None, "other", "none"),
    ("BANANAS ORG", "banana", "produce_leafy", None),
    ("milk", "milk", "dairy", "exact"),
])
def test_clean_examples(text, canon, cat, match):
    r = clean(text)
    assert (r["canonical"], r["category"]) == (canon, cat)
    if match:
        assert r["match"] == match


def test_peanut_butter_is_not_dairy():
    assert clean("PEANUT BUTTER CREAMY")["category"] != "dairy"
    assert clean("BUTTER UNSALTED")["category"] == "dairy"


@pytest.mark.parametrize("text", ["", "   ", "123 456", "!!!", "ÄÖÜ 日本語", "EGGS LG 12CT", "SOURDOUGH LOAF",
                                  "ICE CREAM VAN", "ORG BNNA", "a" * 500, "TOMATO SAUCE", "APPLE JUICE 64OZ"])
def test_category_always_valid(text):
    r = clean(text)
    assert r["category"] in T.CATEGORIES
    assert r["match"] in {"exact", "alias", "keyword", "none"}
    assert r["canonical"] is None or r["canonical"] in T.CLASS_CATEGORY


def test_all_abbreviation_targets_valid():
    import json
    from pipeline.category_cleanup import names
    d = json.loads(names._ABBR.read_text())
    for ph, v in d["phrases"].items():
        assert v["category"] in T.CATEGORIES, ph
        assert v["canonical"] is None or v["canonical"] in T.CLASS_CATEGORY, ph
    for kw, cat in d["keywords"].items():
        assert cat in T.CATEGORIES, kw


# ------------------------------------------------------------------ food_group + shared abbreviations
def _backend():
    from pipeline.category_cleanup.names import backend_food_group
    return backend_food_group()


def test_backend_table_loads_without_flask():
    import sys
    fg = _backend()
    assert fg.ABBREVIATIONS and callable(fg.derive_from_name)
    assert "app.services.food_group" not in sys.modules  # loaded by file path, not through backend/app/__init__


def _local_expand():
    import json
    from pipeline.category_cleanup import names
    return json.loads(names._ABBR.read_text())["expand"]


def test_shared_abbreviation_keys_agree():
    shared = set(_local_expand()) & set(_backend().ABBREVIATIONS)
    for k in shared:
        assert _local_expand()[k] == _backend().ABBREVIATIONS[k], k


def test_abbreviations_json_does_not_duplicate_backend_table():
    assert not set(_local_expand()) & set(_backend().ABBREVIATIONS)


def test_backend_abbreviations_are_applied():
    from pipeline.category_cleanup.names import tokens
    assert tokens("CHKN") == ["chicken"] and tokens("MOZZ") == ["cheese"]  # backend 'mozzarella' -> class word
    assert tokens("SPAG") == ["pasta"] and tokens("LG EGGS") == ["egg"]


@pytest.mark.parametrize("text,canon,group", [
    ("milk", "milk", "dairy"), ("CHKN BRST", "chicken", "protein"), ("BANANAS ORG", "banana", "fruit"),
    ("BROCC CROWNS", "broccoli", "veggies"), ("PASTA SPAG 16OZ", "pasta", "grains"),
    ("HONEY NUT CEREAL", None, "grains"), ("JIF PEANUT BUTTER", None, "pantry"),
    ("ICE CREAM VAN", None, "frozen"), ("XQZT 4411", None, "other"), ("", None, "other"),
])
def test_food_group_on_every_line(text, canon, group):
    r = clean(text)
    assert r["canonical"] == canon and r["food_group"] == group
    assert r["food_group"] in T.FOOD_GROUPS


def test_food_group_uses_taxonomy_when_class_matches():
    for text in ("milk", "CHKN BRST", "BANANAS ORG", "TORT", "SPNCH", "orange juice"):
        r = clean(text)
        if r["canonical"]:
            assert r["food_group"] == T.food_group_for(r["canonical"]), text


def test_food_group_falls_back_to_backend_heuristic():
    fg = _backend()
    r = clean("KIND GRANOLA BARS")
    assert r["canonical"] is None and r["food_group"] == fg.derive_from_name("KIND GRANOLA BARS")


@pytest.mark.parametrize("text", ["", "123", "ÄÖÜ 日本語", "a" * 500, "TOMATO SAUCE", "APPLE JUICE 64OZ"])
def test_food_group_always_valid(text):
    assert clean(text)["food_group"] in T.FOOD_GROUPS
