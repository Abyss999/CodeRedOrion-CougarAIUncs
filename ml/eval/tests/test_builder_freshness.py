"""Verification of the 3-class freshness change (taxonomy, TwoStage.label, serve, prepare_dataset)."""
import io
import json
import os
import sys

import numpy as np
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

FRESH = ["Fresh Banana(1-4)", "Fresh Bittermelon(1-3)", "Fresh Cucumber(1-6)", "Fresh Orange(1-9)",
         "Fresh Papaya(1-4)", "Fresh Tomato(1-10)", "Fresh eggplant(1-4)", "Fresh pineapple(1-15)"]
ROTTEN = ["Rotten Bittermelon(5-8)", "Rotten Cucumber(12-20)", "Rotten Orange(20-35)", "Rotten Papaya(7-12)",
          "Rotten Pineapple(25-35)", "Rotten Tomato(24-35)", "Rotten banana(7-13)", "Rotten eggplant(8-15)"]
SEMI = ["Semi Fresh Bittermelon ( 3-5)", "Semi Fresh Cucumber(6-12)", "Semi Fresh Papaya(4-7)",
        "Semi fresh Orange(9-20)", "Semi fresh Pineapple (15-25)", "Semi fresh Tomato(10-24)",
        "Semi fresh banana(4-7)", "Semi_Fresh eggplant(4-8)"]
ITEMS = ["banana", "bitter_melon", "cucumber", "orange", "papaya", "tomato", "eggplant", "pineapple"]


def _item(raw):
    n, f = T.split_freshness(raw)
    return T.canonical_name(n), f


@pytest.mark.parametrize("group,label", [(FRESH, "fresh"), (SEMI, "semi_fresh"), (ROTTEN, "spoiled")])
def test_all_24_agrifreshnet_folders(group, label):
    got = sorted(_item(r) for r in group)
    assert got == sorted((i, label) for i in ITEMS), got


def test_semi_not_misparsed_as_fresh_semi_x():
    assert T.split_freshness("Semi fresh banana(4-7)") == ("banana", "semi_fresh")
    assert T.split_freshness("Semi_Fresh eggplant(4-8)") == ("eggplant", "semi_fresh")
    assert T.split_freshness("semi_ripe_banana")[1] == "semi_fresh"


def test_old_behaviours_preserved():
    assert T.split_freshness("rottenapples") == ("apples", "spoiled")
    assert T.split_freshness("Fresh_Banana") == ("banana", "fresh")
    assert T.split_freshness("Apple__Rotten") == ("apple", "spoiled")
    assert T.canonical_name("Tomatoes") == "tomato"
    assert T.split_freshness("banana") == ("banana", None)
    assert T.canonical_name("robot") is None


def test_normalize_day_ranges():
    assert T.normalize("Semi fresh Pineapple (15-25)") == "semi_fresh_pineapple"
    assert T.normalize("Fresh Banana(1-4)") == "fresh_banana"
    assert T.normalize("Rotten Bittermelon(5-8)") == "rotten_bittermelon"


def test_constants_and_alias():
    assert T.FRESHNESS == ("fresh", "semi_fresh", "spoiled")
    assert T.FRESHNESS_CODE == {"fresh": 0, "spoiled": 1, "semi_fresh": 2}
    assert T.canonical_name("bittergourd") == "bitter_melon"
    assert T.canonical_name("Bittermelon") == "bitter_melon"
    for n in ("papaya", "pineapple", "bitter_melon"):
        assert T.category_for(n) in T.CATEGORIES and n in T.CLASS_NAMES


def test_class_order_append_only():
    names = T.CLASS_NAMES
    assert names[-3:] == ["papaya", "pineapple", "bitter_melon"]
    assert len(names) == 60 and len(set(names)) == 60
    assert not {"papaya", "pineapple", "bitter_melon"} & set(names[:57])
    assert T.CLASS_ID["papaya"] == 57 and T.CLASS_ID["pineapple"] == 58 and T.CLASS_ID["bitter_melon"] == 59


# ---------- TwoStage.label ----------------------------------------------------------------------
@pytest.mark.parametrize("probs,expected", [
    ({"fresh": 0.9, "semi_fresh": 0.05, "spoiled": 0.05}, "fresh"),
    ({"fresh": 0.1, "semi_fresh": 0.8, "spoiled": 0.1}, "semi_fresh"),
    ({"fresh": 0.1, "semi_fresh": 0.1, "spoiled": 0.8}, "spoiled"),
    ({"fresh": 0.0, "semi_fresh": 0.5, "spoiled": 0.5}, "spoiled"),      # both at threshold: spoiled wins
    ({"fresh": 0.5, "semi_fresh": 0.5, "spoiled": 0.0}, "semi_fresh"),   # semi boundary inclusive
    ({"fresh": 0.51, "semi_fresh": 0.49, "spoiled": 0.0}, "fresh"),
    ({"fresh": 0.51, "semi_fresh": 0.0, "spoiled": 0.49}, "fresh"),
    ({"fresh": 0.9, "spoiled": 0.1}, "fresh"),                           # 2-class probs
    ({"fresh": 0.1, "spoiled": 0.9}, "spoiled"),
    ({}, "fresh"),
])
def test_label_table(probs, expected):
    assert TwoStage("x.pt").label(probs) == expected


def test_label_custom_thresholds():
    t = TwoStage("x.pt", spoiled_threshold=0.3, semi_fresh_threshold=0.7)
    assert t.label({"spoiled": 0.3, "semi_fresh": 0.7}) == "spoiled"
    assert t.label({"spoiled": 0.29, "semi_fresh": 0.69}) == "fresh"
    assert t.label({"spoiled": 0.29, "semi_fresh": 0.7}) == "semi_fresh"
    assert TwoStage("x.pt").semi_fresh_threshold == 0.5


def test_export_predictions_has_semi_flag():
    src = open(os.path.join(ML, "yolo", "export_predictions.py"), encoding="utf-8").read()
    assert "--semi-fresh-threshold" in src


# ---------- serve /detect -----------------------------------------------------------------------
def _png():
    b = io.BytesIO(); Image.new("RGB", (200, 100), (200, 30, 30)).save(b, "PNG"); b.seek(0); return b


def _detect(frs):
    from serve.app import create_app
    from serve.backends import FakeDetector, FakeOCR
    dets = [{"name": "banana", "category": "produce_hardy", "confidence": 0.9 - i * 0.1, "freshness": f,
             "bbox": [1, 2, 30, 40]} for i, f in enumerate(frs)]
    c = create_app(FakeDetector(dets), FakeOCR(), structure_with_gemini=False).test_client()
    r = c.post("/detect", data={"image": (_png(), "x.png"), "mode": "fridge"}, content_type="multipart/form-data")
    assert r.status_code == 200
    return [x["freshness"] for x in r.json["candidates"]]


def test_serve_passes_semi_fresh():
    assert _detect(["fresh", "semi_fresh", "spoiled"]) == ["fresh", "semi_fresh", "spoiled"]


@pytest.mark.parametrize("junk", ["??", "", None, "Semi_Fresh", "semi fresh", "rotten", 3])
def test_serve_junk_freshness_becomes_fresh(junk):
    assert _detect([junk]) == ["fresh"]


# ---------- prepare_dataset ---------------------------------------------------------------------
def test_prepare_semi_fresh(tmp_path):
    import prepare_dataset as P
    fr = tmp_path / "raw" / "fr"
    for cls in ("Semi fresh banana(4-7)", "Fresh Banana(1-4)", "Rotten banana(7-13)"):
        for i in range(12):
            d = fr / cls
            d.mkdir(parents=True, exist_ok=True)
            Image.fromarray(np.full((120, 160, 3), 120 + i, np.uint8)).save(d / f"i{i}.jpg")
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps({"sources": [{"name": "fr", "kind": "folders", "root": str(fr)}]}))
    out = tmp_path / "out"
    P.main(["--sources", str(sp), "--out", str(out), "--heldout", "0.2", "--val", "0.2"])
    rep = json.loads((out / "dataset_report.json").read_text())
    bf = rep["boxes_by_freshness"]
    assert set(bf) == {"fresh", "semi_fresh", "spoiled"} and all(v > 0 for v in bf.values()) and sum(bf.values()) == 36
    codes = set()
    for f in (out / "freshness").rglob("*.txt"):
        codes |= {ln.split()[0] for ln in f.read_text().splitlines() if ln.strip()}
    assert codes == {"0", "1", "2"}
    # semi_fresh sidecar code 2 appears only on semi images
    assert list((out / "cls").glob("*/semi_fresh/*.jpg"))
    gt = [json.loads(l) for l in open(out / "heldout_gt.jsonl")]
    assert {l["freshness"] for g in gt for l in g["labels"]} <= {"fresh", "semi_fresh", "spoiled"}
