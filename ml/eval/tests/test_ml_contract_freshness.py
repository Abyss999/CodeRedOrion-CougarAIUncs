"""QA contract tests for the 3-way freshness change: taxonomy + infer + serve (no torch needed)."""
import io
import os
import sys

import pytest
from PIL import Image

from conftest import REPO_ROOT

ML = os.path.join(REPO_ROOT, "ml")
for p in (ML, os.path.join(ML, "yolo")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("DETECTOR_BACKEND", "fake")
os.environ.setdefault("OCR_BACKEND", "fake")

from yolo import taxonomy as T  # noqa: E402
from yolo.infer import TwoStage  # noqa: E402

NEW = ("papaya", "pineapple", "bitter_melon")


def test_new_classes_have_group_category_and_are_appended():
    for n in NEW:
        assert n in T.CLASS_NAMES and n in T.CLASS_FOOD_GROUP and n in T.CLASS_CATEGORY
        assert T.CLASS_FOOD_GROUP[n] in T.FOOD_GROUPS and T.CLASS_CATEGORY[n] in T.CATEGORIES
        assert T.food_group_for(n) == T.CLASS_FOOD_GROUP[n]
    assert T.CLASS_FOOD_GROUP["papaya"] == "fruit" and T.CLASS_FOOD_GROUP["bitter_melon"] == "veggies"
    assert T.CLASS_NAMES[-3:] == list(NEW) and len(set(T.CLASS_NAMES)) == len(T.CLASS_NAMES)
    assert set(T.CLASS_FOOD_GROUP) == set(T.CLASS_CATEGORY) == set(T.CLASS_NAMES)


def test_old_class_ids_unchanged():
    # append-only: existing ids must not shift (trained weights depend on them)
    assert T.CLASS_ID["papaya"] == len(T.CLASS_NAMES) - 3
    assert T.CLASS_NAMES.index("banana") < len(T.CLASS_NAMES) - 3


@pytest.mark.parametrize("raw,expected", [
    ("Semi fresh Pineapple (15-25)", ("pineapple", "semi_fresh")),
    ("Semi Fresh Bittermelon ( 3-5)", ("bittermelon", "semi_fresh")),
    ("Semi_Fresh eggplant(4-8)", ("eggplant", "semi_fresh")),
    ("Fresh Banana(1-4)", ("banana", "fresh")),
    ("Rotten Papaya(7-12)", ("papaya", "spoiled")),
    ("semi_ripe_banana", ("banana", "semi_fresh")),
    ("rottenapples", ("apples", "spoiled")),
    ("banana", ("banana", None)),
])
def test_split_freshness(raw, expected):
    assert T.split_freshness(raw) == expected


def test_semi_pineapple_end_to_end_canonical():
    n, f = T.split_freshness("Semi fresh Pineapple (15-25)")
    assert (T.canonical_name(n), f) == ("pineapple", "semi_fresh")
    n, f = T.split_freshness("Semi Fresh Bittermelon ( 3-5)")
    assert (T.canonical_name(n), f) == ("bitter_melon", "semi_fresh")
    assert T.FRESHNESS == ("fresh", "semi_fresh", "spoiled")


# ---- label(): 3-way + 2-class compatibility ----
@pytest.mark.parametrize("probs,expected", [
    ({"fresh": 0.9, "semi_fresh": 0.05, "spoiled": 0.05}, "fresh"),
    ({"fresh": 0.1, "semi_fresh": 0.8, "spoiled": 0.1}, "semi_fresh"),
    ({"fresh": 0.1, "semi_fresh": 0.1, "spoiled": 0.8}, "spoiled"),
    ({"fresh": 0.0, "semi_fresh": 0.5, "spoiled": 0.5}, "spoiled"),     # spoiled wins ties
    ({"fresh": 0.5, "semi_fresh": 0.5, "spoiled": 0.0}, "semi_fresh"),
    ({"fresh": 0.51, "semi_fresh": 0.49, "spoiled": 0.0}, "fresh"),
    ({"fresh": 0.9, "spoiled": 0.1}, "fresh"),                          # 2-class weights
    ({"fresh": 0.1, "spoiled": 0.9}, "spoiled"),
    ({}, "fresh"),
])
def test_label(probs, expected):
    assert TwoStage("x.pt").label(probs) == expected


class _Probs:
    def __init__(self, vals): self.data = vals


class _Res:
    def __init__(self, names, vals): self.names, self.probs = names, _Probs(vals)


class _FakeCls:
    def __init__(self, names, vals): self.r = _Res(names, vals)
    def predict(self, *a, **k): return [self.r]


class _FakeDet:
    def predict(self, *a, **k):
        class Boxes:
            class _L(list):
                def tolist(self): return list(self)
            xyxy = _L([[0, 0, 40, 40]]); conf = _L([0.9]); cls = _L([0])
        class R: boxes = Boxes(); names = {0: "banana"}
        return [R()]


def _predict(cls_names, vals):
    t = TwoStage("det.pt", "cls.pt")
    t._det, t._cls = _FakeDet(), _FakeCls(cls_names, vals)
    return t.predict(Image.new("RGB", (64, 64), (200, 200, 0)))[0]["freshness"]


def test_two_class_weights_compat_simulated():
    names = {0: "fresh", 1: "spoiled"}
    assert _predict(names, [0.9, 0.1]) == "fresh"
    assert _predict(names, [0.2, 0.8]) == "spoiled"


def test_three_class_weights_simulated_any_index_order():
    names = {0: "fresh", 1: "spoiled", 2: "semi_fresh"}  # sidecar code order (FRESHNESS_CODE)
    assert _predict(names, [0.1, 0.1, 0.8]) == "semi_fresh"
    assert _predict(names, [0.1, 0.8, 0.1]) == "spoiled"
    assert _predict(names, [0.8, 0.1, 0.1]) == "fresh"
    names = {0: "fresh", 1: "semi_fresh", 2: "spoiled"}  # alphabetical-ish order as ultralytics sorts folders
    assert _predict(names, [0.1, 0.8, 0.1]) == "semi_fresh"


def test_no_cls_weights_defaults_fresh():
    t = TwoStage("det.pt")
    t._det = _FakeDet()
    assert t.predict(Image.new("RGB", (64, 64)))[0]["freshness"] == "fresh"


# ---- serve ----
def _detect(freshness_values):
    from serve.app import create_app
    from serve.backends import FakeDetector, FakeOCR
    dets = [{"name": "banana", "category": "produce_hardy", "confidence": 0.9 - i * 0.1, "freshness": f,
             "bbox": [1, 2, 30, 40]} for i, f in enumerate(freshness_values)]
    c = create_app(FakeDetector(dets), FakeOCR(), structure_with_gemini=False).test_client()
    b = io.BytesIO(); Image.new("RGB", (200, 100)).save(b, "PNG"); b.seek(0)
    r = c.post("/detect", data={"image": (b, "x.png"), "mode": "fridge"}, content_type="multipart/form-data")
    assert r.status_code == 200
    return [x["freshness"] for x in r.json["candidates"]]


def test_serve_passes_three_values():
    assert _detect(["fresh", "semi_fresh", "spoiled"]) == ["fresh", "semi_fresh", "spoiled"]


@pytest.mark.parametrize("junk,expected", [("??", "fresh"), ("", "fresh"), (None, "fresh"), (3, "fresh"),
                                           pytest.param("semi-fresh", "semi_fresh", marks=pytest.mark.xfail(reason="ML-27: serve is exact-match, no case/variant folding", strict=True)),
                                           pytest.param("Semi Fresh", "semi_fresh", marks=pytest.mark.xfail(reason="ML-27", strict=True)),
                                           pytest.param("SPOILED", "spoiled", marks=pytest.mark.xfail(reason="ML-27: wrong-direction fallback (spoiled shown as fresh)", strict=True))])
def test_serve_normalises(junk, expected):
    assert _detect([junk]) == [expected]
