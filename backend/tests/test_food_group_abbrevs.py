"""feat/receipt-abbrevs: ~40 receipt abbreviations moved from pipeline/category_cleanup/abbreviations.json
into food_group.ABBREVIATIONS. Name-only receipt lines should reach a useful food group."""
import json
import pathlib

import pytest

from app.services import food_group
from app.services.food_group import ABBREVIATIONS, derive_from_name

ROOT = pathlib.Path(__file__).resolve().parents[2]

NEW_KEYS = """mlk skm whl grk brst stk prk saus ched parm bttr bred tort tom tmto onin ltc lett broc caul crt crts
cuc cuke strawb grps grp avoc appl aple orng lmn lme mshrm mush shrms pepr zuc zucc papya pnapl pinapl jce oj rce slmn""".split()

AMBIGUOUS_KEYS = ["gr", "pot", "pine", "ban", "straw"]

CASES = [
    ("GV SKM MLK GAL", "dairy"),
    ("MLK 2% GAL", "dairy"),
    ("GRK YOGURT PLAIN", "dairy"),
    ("CHED SHRD 8OZ", "dairy"),
    ("PARM GRATED", "dairy"),
    ("BTTR SALTED 1LB", "dairy"),
    ("CHKN BRST BNLS", "protein"),
    ("PRK CHOP BONE IN", "protein"),
    ("STK RIBEYE", "protein"),
    ("SAUS LINKS", "protein"),
    ("SLMN FILLET", "protein"),
    ("BRED WHT", "grains"),
    ("TORT FLOUR 10CT", "grains"),
    ("RCE JASMINE", "grains"),
    ("ORG BROC CROWNS", "veggies"),
    ("CAUL FLORETS", "veggies"),
    ("CRT BABY 1LB", "veggies"),
    ("CRTS SHREDDED", "veggies"),
    ("CUC ENGLISH", "veggies"),
    ("CUKE SEEDLESS", "veggies"),
    ("LTC ROMAINE HEARTS", "veggies"),
    ("LETT ICEBERG", "veggies"),
    ("TMTO VINE RIPE", "veggies"),
    ("ONIN YELLOW 3LB", "veggies"),
    ("MSHRM SLICED 8OZ", "veggies"),
    ("MUSH BABY BELLA", "veggies"),
    ("SHRMS WHITE", "veggies"),
    ("PEPR RED BELL", "veggies"),
    ("ZUC GREEN", "veggies"),
    ("ZUCC SQUASH", "veggies"),
    ("STRAWB 1LB", "fruit"),
    ("GRPS RED SEEDLESS", "fruit"),
    ("GRP GREEN", "fruit"),
    ("AVOC HASS", "fruit"),
    ("APPL GALA 3LB", "fruit"),
    ("APLE FUJI", "fruit"),
    ("ORNG NAVEL 4LB", "fruit"),
    ("LMN", "fruit"),
    ("LME", "fruit"),
    ("PAPYA", "fruit"),
    ("PNAPL CHUNKS", "fruit"),
    ("PINAPL FRESH", "fruit"),
    ("OJ NFC 52OZ", "pantry"),
    ("JCE APPLE 64OZ", "pantry"),
]


@pytest.mark.parametrize("name,want", CASES)
def test_new_abbreviations(name, want):
    assert derive_from_name(name) == want


def test_at_least_30_cases():
    assert len(CASES) >= 30


@pytest.mark.parametrize("key", NEW_KEYS)
def test_key_present(key):
    assert key in ABBREVIATIONS


@pytest.mark.parametrize("key", AMBIGUOUS_KEYS)
def test_ambiguous_keys_stay_out(key):
    assert key not in ABBREVIATIONS


def test_abbreviation_table_shape():
    for k, v in ABBREVIATIONS.items():
        assert k == k.lower() and k.isalpha(), k
        assert isinstance(v, str) and v, k


def test_no_pipeline_json_duplicates():
    extra = json.loads((ROOT / "pipeline/category_cleanup/abbreviations.json").read_text())["expand"]
    dup = set(extra) & set(ABBREVIATIONS)
    # Shared keys are allowed only if they agree (pipeline test enforces too).
    bad = {k for k in dup if extra[k] != ABBREVIATIONS[k]}
    assert not bad, bad


# --- collisions / false positives -----------------------------------------------------------
def test_tom_means_tomato():
    assert derive_from_name("TOM ROMA") == "veggies"
    assert derive_from_name("TOMATO") == "veggies"


@pytest.mark.parametrize("name", ["TOMMY'S PIZZA SAUCE", "TOMMYS BBQ", "TOMMY BAHAMA", "ATOM BOMB", "CUSTOM PRINT"])
def test_tom_not_in_other_words(name):
    assert derive_from_name(name) != "veggies", name


def test_tommys_brand_is_not_tomato():
    # "TOMMY'S" -> tokens "tommy","s": whole-token match, so the brand is not read as tomato.
    assert derive_from_name("TOMMY'S GIFT SET") == "other"


@pytest.mark.parametrize("name", ["CUCINA PASTA SAUCE", "SUCCUCUC", "ACUC", "CUCUMBERS", "CUCCHINI"])
def test_cuc_whole_word_only(name):
    got = derive_from_name(name)
    if name == "CUCUMBERS":
        assert got == "veggies"
    elif name == "CUCINA PASTA SAUCE":
        assert got == "pantry"  # sauce, not cucumber
    else:
        assert got == "other", (name, got)


def test_grp_vs_group():
    assert derive_from_name("GRP RED") == "fruit"
    assert derive_from_name("GROUP PURCHASE FEE") == "other"
    assert derive_from_name("GROUPER FILLET") != "fruit"


def test_breaded_chicken_is_protein():
    assert derive_from_name("BREADED CHICKEN") == "protein"
    assert derive_from_name("BREADED CHICKEN TENDERS") == "protein"
    assert derive_from_name("BRED CHICKEN") == "protein"
    assert derive_from_name("BREADED FISH STICKS") != "grains"


def test_bred_is_bread():
    assert derive_from_name("BRED") == "grains"


@pytest.mark.parametrize("name,want", [
    ("STRAWB YOGURT", "dairy"),        # dairy beats fruit
    ("PEPR JACK CHEESE", "dairy"),
    ("APPL JCE", "pantry"),            # juice wins
    ("ORNG JCE", "pantry"),
    ("TOM TURKEY", "protein"),
    ("TMTO SAUCE", "pantry"),
    ("SAUS EGG BISCUIT", "protein"),
    ("PARM CHIX", "dairy"),
    ("LETTER OPENER", "other"),
    ("STKR LABEL", "other"),
    ("MUSHY PEAS", "veggies"),         # peas, not mushroom; still veggies
    ("WHL WHEAT BRED", "grains"),
])
def test_combinations_and_word_boundaries(name, want):
    assert derive_from_name(name) == want


@pytest.mark.parametrize("name", ["GV WHL MILK GAL", "KS ORG EGGS", "BANANAS"])
def test_pipeline_anchor_inputs_stable(name):
    assert derive_from_name(name) in {"dairy", "protein", "fruit"}


def test_valid_groups_only():
    for n, _ in CASES:
        assert food_group.valid(derive_from_name(n))
