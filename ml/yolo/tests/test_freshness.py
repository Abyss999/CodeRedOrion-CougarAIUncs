import pytest
import taxonomy as T
from infer import TwoStage


@pytest.mark.parametrize("raw,expected", [
    ("Semi fresh banana(4-7)", ("banana", "semi_fresh")),
    ("Semi_Fresh eggplant", ("eggplant", "semi_fresh")),
    ("semifresh_apple", ("apple", "semi_fresh")),
    ("Semi fresh Pineapple (15-25)", ("pineapple", "semi_fresh")),
    ("rotten_apple", ("apple", "spoiled")),
    ("freshapples", ("apples", "fresh")),
    ("Fresh banana (7-10)", ("banana", "fresh")),
    ("apple", ("apple", None)),
])
def test_split_freshness(raw, expected):
    assert T.split_freshness(raw) == expected


def test_normalize_strips_day_range():
    assert T.normalize("Pineapple (15-25)") == "pineapple"
    assert T.normalize("Banana ( 4 - 7 )") == "banana"


def test_freshness_constants():
    assert T.FRESHNESS == ("fresh", "semi_fresh", "spoiled")
    assert T.FRESHNESS_CODE == {"fresh": 0, "spoiled": 1, "semi_fresh": 2}


def test_new_classes_appended_with_groups():
    names = T.CLASS_NAMES
    assert names[-3:] == ["papaya", "pineapple", "bitter_melon"]
    assert names[names.index("frozen_food")] == "frozen_food"
    assert T.CLASS_ID["lettuce"] == 0  # existing ids unchanged
    assert [T.food_group_for(n) for n in names[-3:]] == ["fruit", "fruit", "veggies"]
    assert all(T.category_for(n) == "produce_leafy" for n in names[-3:])
    assert set(T.CLASS_FOOD_GROUP) == set(T.CLASS_CATEGORY)


@pytest.mark.parametrize("raw", ["bitter_gourd", "Bittergourd", "bitter melon", "karela"])
def test_bitter_melon_aliases(raw):
    assert T.canonical_name(raw) == "bitter_melon"


def test_canonical_after_split_semi():
    name, f = T.split_freshness("Semi fresh Papaya (5-8)")
    assert T.canonical_name(name) == "papaya" and f == "semi_fresh"


def ts(**kw):
    return TwoStage("d.pt", "c.pt", **kw)


def test_label_three_way():
    t = ts()
    assert t.label({"fresh": 0.9, "semi_fresh": 0.05, "spoiled": 0.05}) == "fresh"
    assert t.label({"fresh": 0.2, "semi_fresh": 0.6, "spoiled": 0.2}) == "semi_fresh"
    assert t.label({"fresh": 0.1, "semi_fresh": 0.3, "spoiled": 0.6}) == "spoiled"


def test_label_spoiled_wins_when_both_meet_threshold():
    assert ts(spoiled_threshold=0.4, semi_fresh_threshold=0.4).label(
        {"fresh": 0.1, "semi_fresh": 0.45, "spoiled": 0.45}) == "spoiled"


def test_label_thresholds_configurable():
    assert ts(semi_fresh_threshold=0.3).label({"fresh": 0.6, "semi_fresh": 0.3, "spoiled": 0.1}) == "semi_fresh"
    assert ts(spoiled_threshold=0.3).label({"fresh": 0.6, "spoiled": 0.35}) == "spoiled"


def test_label_two_class_weights_backward_compatible():
    t = ts()
    assert t.label({"fresh": 0.7, "spoiled": 0.3}) == "fresh"
    assert t.label({"fresh": 0.3, "spoiled": 0.7}) == "spoiled"
    assert t.label({}) == "fresh"


def test_from_env_reads_semi_threshold(monkeypatch):
    monkeypatch.setenv("YOLO_WEIGHTS", "d.pt")
    monkeypatch.setenv("SEMI_FRESH_THRESHOLD", "0.7")
    assert TwoStage.from_env().semi_fresh_threshold == 0.7
