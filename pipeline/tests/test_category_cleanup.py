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
