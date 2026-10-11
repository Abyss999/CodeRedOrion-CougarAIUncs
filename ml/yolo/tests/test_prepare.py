import json, csv
from pathlib import Path
from PIL import Image
import numpy as np
import taxonomy as T
import lighting as L
import prepare_dataset as P


def img(path, color=(120, 130, 110), size=(160, 120), noise=True):
    """Distinct pseudo-random texture per file name (identical images would be merged as near-duplicates)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    a = np.full((size[1], size[0], 3), color, np.float32)
    if noise:
        seed = int.from_bytes(__import__("hashlib").md5(str(path.name).encode()).digest()[:4], "little")
        a = a + np.random.default_rng(seed).uniform(-45, 45, a.shape)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(path)


def nm(prefix, i):
    """letters-only unique names (digits would make a numbered series = one split group)"""
    return prefix + "".join(chr(97 + int(d)) for d in str(i))


def make_sources(tmp):
    # yolo-style source
    root = tmp / "raw" / "fridge"
    (root / "data.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "data.yaml").write_text("names: ['Milk', 'Robot', 'rotten_apple']\n")
    for i in range(30):
        img(root / "train" / "images" / f"{nm('a', i)}.jpg")
        (root / "train" / "labels").mkdir(parents=True, exist_ok=True)
        (root / "train" / "labels" / f"{nm('a', i)}.txt").write_text("0 0.5 0.5 0.4 0.4\n1 0.2 0.2 0.1 0.1\n2 0.7 0.7 0.2 0.2\n")
    # folder-style source
    fr = tmp / "raw" / "fr"
    for i in range(20):
        img(fr / "rotten_apples" / f"{nm('r', i)}.jpg"); img(fr / "freshbanana" / f"{nm('f', i)}.jpg")
    src = {"sources": [
        {"name": "fridge", "kind": "yolo", "root": str(root), "freshness_default": "fresh", "class_map": {}},
        {"name": "fr", "kind": "folders", "root": str(fr)}]}
    p = tmp / "sources.json"; p.write_text(json.dumps(src)); return p


def test_taxonomy_maps_to_valid_categories():
    assert set(T.CLASS_CATEGORY.values()) <= set(T.CATEGORIES)
    assert T.split_freshness("rottenapples") == ("apples", "spoiled")
    assert T.split_freshness("Fresh_Banana") == ("banana", "fresh")
    assert T.split_freshness("Apple__Rotten") == ("apple", "spoiled")
    assert T.canonical_name("Tomatoes") == "tomato" and T.canonical_name("robot") is None
    assert T.category_for("whatever") == "other"


def test_lighting_tags_and_synth():
    base = Image.new("RGB", (64, 64), (130, 130, 130))
    assert L.tag(base) == "normal"
    assert L.tag(L.synth(base, "low")) == "low"
    assert L.tag(L.synth(base, "warm")) == "warm"


def test_prepare_end_to_end(tmp_path):
    out = tmp_path / "out"
    P.main(["--sources", str(make_sources(tmp_path)), "--out", str(out), "--heldout", "0.3", "--val", "0.2"])
    names = json.loads((out / "class_names.json").read_text())
    assert set(names.values()) >= {"milk", "apple"} and set(names.values()) <= set(T.CLASS_NAMES)
    assert list(names) == [str(i) for i in range(len(names))]            # contiguous ids
    assert set(json.loads((out / "dataset_report.json").read_text())["active_classes"]) == set(names.values())
    assert 0 < len(names) < len(T.CLASS_NAMES)                           # ML-16: only classes with data
    ids = {int(l.split()[0]) for f in (out / "labels").rglob("*.txt") for l in f.read_text().splitlines()}
    assert ids <= set(map(int, names))
    rows = list(csv.DictReader(open(out / "heldout_manifest.csv")))
    assert rows and {r["lighting"] for r in rows} == {"normal", "low", "warm"}
    gt = [json.loads(l) for l in open(out / "heldout_gt.jsonl")]
    assert len(gt) == len(rows)
    for g in gt:
        assert (out / g["image"]).exists() and g["lighting"] in ("normal", "low", "warm")
        for lab in g["labels"]:
            assert lab["category"] in T.CATEGORIES and lab["freshness"] in T.FRESHNESS
            x1, y1, x2, y2 = lab["bbox"]; assert x2 > x1 and y2 > y1
    # unmapped 'Robot' dropped; rotten_apple -> apple/spoiled; label & sidecar line counts agree
    rep = json.loads((out / "dataset_report.json").read_text())
    assert any("Robot" in k for k in rep["classes_unmapped_skipped"])
    lab = next((out / "labels" / "train").glob("*.txt")) if list((out / "labels" / "train").glob("*.txt")) else None
    if lab:
        n = len(lab.read_text().splitlines())
        assert n == len((out / "freshness" / "train" / lab.name).read_text().splitlines())
    assert list((out / "cls" / "train" / "spoiled").glob("*.jpg"))
    # no group leakage: every synth variant sits in heldout with its original
    assert all(r["variant_of"] in {x["image"] for x in rows} for r in rows if r["variant_of"])
    # refuses to overwrite
    try:
        P.main(["--sources", str(make_sources(tmp_path)), "--out", str(out)]); assert False
    except SystemExit:
        pass


def test_parse_capture_time_formats():
    P_ = P.parse_capture_time
    assert P_(Path("IMG20250926100615_jpg.rf.abc.jpg")) == ("compact", P_(Path("IMG_20250926_100615.jpg"))[1])
    assert P_(Path("IMG_20251004_163630_jpg.rf.x.jpg"))[0] == "compact"
    k, t = P_(Path("1758873619153_jpg.rf.x.jpg")); assert k == "epoch_ms" and t == 1758873619.153
    assert P_(Path("Defected_begun_100_jpg.rf.x.jpg")) is None
    assert P_(Path("12345.jpg")) is None


def _rec(src, name):
    return dict(src=src, path=Path(name), boxes=[], group=P.group_key(src, Path(name)))


def test_assign_sessions_groups_by_gap_and_keeps_rf_groups():
    recs = [_rec("v", "IMG20250926100000_jpg.rf.a.jpg"), _rec("v", "IMG20250926100000_jpg.rf.b.jpg"),
            _rec("v", "IMG20250926100030_jpg.rf.c.jpg"),      # +30 s: same session (chained)
            _rec("v", "IMG20250926100120_jpg.rf.d.jpg"),      # +50 s after previous: still same
            _rec("v", "IMG20250926100500_jpg.rf.e.jpg"),      # +220 s: new session
            _rec("v", "Defected_begun_1_jpg.rf.f.jpg"), _rec("v", "Defected_begun_1_jpg.rf.g.jpg"),
            _rec("w", "IMG20250926100000_jpg.rf.h.jpg")]      # other source: never merged
    info = P.assign_sessions(recs, 60)
    g = [r["group"] for r in recs]
    assert g[0] == g[1] == g[2] == g[3] and g[4] != g[0] and g[7] != g[0]
    assert g[5] == g[6] == "v/Defected_begun" and info["images_without_timestamp"] == 2
    assert info["split_grouping"] == "session" and info["largest_session_images"] == 4
    # disabled -> stem grouping only
    recs2 = [_rec("v", "IMG20250926100000_jpg.rf.a.jpg"), _rec("v", "IMG20250926100010_jpg.rf.b.jpg")]
    # sessions off -> numbered-series grouping only (IMG<digits> is one series)
    assert P.assign_sessions(recs2, 0)["split_grouping"] == "series" and recs2[0]["group"] == recs2[1]["group"]
    # 301 s apart with gap 300 -> two sessions; 300 s apart -> one (gap is inclusive)
    r3 = [_rec("v", "IMG20250926100000_jpg.rf.a.jpg"), _rec("v", "IMG20250926100500_jpg.rf.b.jpg"),
          _rec("v", "IMG20250926101001_jpg.rf.c.jpg")]
    P.assign_sessions(r3, 300)
    assert r3[0]["group"] == r3[1]["group"] != r3[2]["group"]


def test_series_and_staged_names():
    assert P.series_stem(Path("Defected_begun_3_jpg.rf.abc.jpg")) == "Defected_begun"
    assert P.series_stem(Path("Defected_begun_4_jpg.rf.def.jpg")) == "Defected_begun"
    assert P.base_stem(Path("IMG_20200822_223831.jpg_0_1039.jpg")) == "IMG_20200822_223831"   # kaggle augmentation
    assert P.base_stem(Path("Copy of IMG_20200727_223202.jpg_0_1614.jpg")) == "IMG_20200727_223202"
    # staged PR-B name: class/freshness prefix, timestamp BEFORE '.rf.'
    k, t = P.parse_capture_time(Path("banana__fresh__IMG_20250101_123456.rf.0a1b2c3d.jpg"))
    assert k == "compact" and t == P.parse_capture_time(Path("IMG20250101123456.jpg"))[1]
    assert P.parse_capture_time(Path("20250101_123456.jpg"))[0] == "compact"
    assert P.group_key("s", Path("banana__fresh__IMG_20250101_123456.rf.x.jpg")) == \
        P.group_key("s", Path("banana__fresh__IMG_20250101_123456.rf.y.jpg"))
    k, t = P.parse_capture_time(Path("Screen Shot 2018-06-08 at 4.59.36 PM.png"))
    assert k == "screenshot" and P.parse_capture_time(Path("Screen Shot 2018-06-08 at 4.59.36 AM.png"))[1] == t - 12 * 3600
    # Kaggle augmentation prefixes and WhatsApp names share the screenshot clock
    kk, tt = P.parse_capture_time(Path("rotated_by_15_Screen Shot 2018-06-08 at 4.59.36 PM.png"))
    assert (kk, tt) == ("screenshot", t) and P.parse_capture_time(Path("saltandpepper_Screen Shot 2018-06-08 at 4.59.36 PM.png"))[1] == t
    assert P.parse_capture_time(Path("WhatsApp Image 2020-11-07 at 11.35.36 PM.jpg_0_577.jpg"))[0] == "screenshot"
    assert P.parse_capture_time(Path("fresh_stale_rotated_by_15_Screen_Shot_2018-06-08_at_4_59_36_PM_a3db64.jpg"))[1] == t
    assert P.base_stem(Path("vertical_flip_Screen Shot 2018-06-08 at 4.59.36 PM.png")) == "Screen Shot 2018-06-08 at 4.59.36 PM"
    assert P.parse_capture_time(Path("0000000004053_jpg.rf.x.jpg")) is None        # barcode, not an epoch


def test_sessions_never_straddle_splits(tmp_path):
    from datetime import datetime, timedelta
    root = tmp_path / "raw" / "v"; (root / "data.yaml").parent.mkdir(parents=True)
    (root / "data.yaml").write_text("names: ['fresh_potato']\n")
    t0 = datetime(2025, 9, 26, 10, 0, 0)
    for s in range(40):                       # 40 sessions x 4 shots 5 s apart, sessions 10 min apart
        for k in range(4):
            stem = "IMG" + (t0 + timedelta(minutes=10 * s, seconds=5 * k)).strftime("%Y%m%d%H%M%S") + "_jpg.rf.x%d" % k
            img(root / "train" / "images" / f"{stem}.jpg")
            (root / "train" / "labels").mkdir(parents=True, exist_ok=True)
            (root / "train" / "labels" / f"{stem}.txt").write_text("0 0.5 0.5 0.6 0.6\n")
    src = tmp_path / "s.json"
    src.write_text(json.dumps({"sources": [{"name": "v", "kind": "yolo", "root": str(root),
                                            "class_map": {"fresh_potato": "potato:fresh"}}]}))
    out = tmp_path / "o"
    P.main(["--sources", str(src), "--out", str(out), "--no-synth-lighting"])
    rep = json.loads((out / "dataset_report.json").read_text())
    assert rep["split_grouping"] == "session" and rep["grouping"]["session_groups"] == 40
    lk = rep["leakage_by_source"]["v"]
    assert lk["ts_neighbour_within_300s"] == 0 and lk["ts_neighbour_within_60s"] == 0 and lk["phash_near_dup_in_train_val"] == 0
    sess_split = {}
    for sp in ("train", "val", "heldout"):
        for f in (out / "images" / sp).glob("*.jpg"):
            ts = f.stem.split("IMG")[1][:12]                  # yyyymmddHHMM -> 10-min session via minute//10
            sess_split.setdefault(ts[:11], set()).add(sp)     # yyyymmddHHM (10-minute bucket)
    assert all(len(v) == 1 for v in sess_split.values())
    assert rep["source_by_split"]["v"]["train/images"] + rep["source_by_split"]["v"].get("val/images", 0) \
        + rep["source_by_split"]["v"].get("heldout/images", 0) == 160


def test_report_drop_reasons_and_crops(tmp_path):
    root = tmp_path / "raw" / "v"; (root / "data.yaml").parent.mkdir(parents=True)
    (root / "data.yaml").write_text("names: ['fresh_potato', 'fresh_gourd']\n")
    for n, lab in (("ok", "0 0.5 0.5 0.6 0.6\n"), ("gourd", "1 0.5 0.5 0.5 0.5\n"), ("empty", ""),
                   ("tiny", "0 0.5 0.5 0.01 0.01\n")):
        img(root / "train" / "images" / f"{n}.jpg"); (root / "train" / "labels").mkdir(exist_ok=True)
        (root / "train" / "labels" / f"{n}.txt").write_text(lab)
    src = tmp_path / "s.json"
    src.write_text(json.dumps({"sources": [{"name": "v", "kind": "yolo", "root": str(root),
                  "class_map": {"fresh_potato": "potato:fresh", "fresh_gourd": None}}]}))
    out = tmp_path / "o"
    P.main(["--sources", str(src), "--out", str(out), "--heldout", "0", "--val", "0"])
    rep = json.loads((out / "dataset_report.json").read_text())
    assert rep["dropped_images"] == {"v:all_boxes_unmapped": 1, "v:empty_label_file": 1}
    assert rep["empty_label_images"] == 1 and rep["active_classes"] == ["potato"]
    assert rep["crops"]["expected"] == 2 and rep["crops"]["written"] == 1
    assert rep["crops"]["missing"] == {"missing_too_small/train/fresh": 1}


def test_near_duplicates_share_a_split_and_report_is_consistent(tmp_path):
    root = tmp_path / "raw" / "v"; (root / "data.yaml").parent.mkdir(parents=True)
    (root / "data.yaml").write_text("names: ['milk']\n")
    (root / "train" / "labels").mkdir(parents=True)
    base = Image.fromarray(np.random.default_rng(7).integers(0, 255, (120, 160, 3), dtype=np.uint8))
    for i in range(60):                       # 60 unrelated singletons ...
        img(root / "train" / "images" / f"item{i}_{'abcdefghijklmnopqrstuvwxyz'[i % 26]}x.jpg")
        (root / "train" / "labels" / f"item{i}_{'abcdefghijklmnopqrstuvwxyz'[i % 26]}x.txt").write_text("0 0.5 0.5 0.6 0.6\n")
    for k in range(10):                       # ... plus 10 re-uploads of ONE picture under unrelated names
        nm = f"upload{'abcdefghij'[k]}zz"
        base.save(root / "train" / "images" / f"{nm}.jpg")
        (root / "train" / "labels" / f"{nm}.txt").write_text("0 0.5 0.5 0.6 0.6\n")
    src = tmp_path / "s.json"
    src.write_text(json.dumps({"sources": [{"name": "v", "kind": "yolo", "root": str(root), "freshness_default": "fresh"}]}))
    out = tmp_path / "o"
    P.main(["--sources", str(src), "--out", str(out), "--heldout", "0.3", "--val", "0.2", "--no-synth-lighting"])
    where = {sp: {f.name for f in (out / "images" / sp).glob("*upload*")} for sp in ("train", "val", "heldout")}
    assert sorted(len(v) for v in where.values()) == [0, 0, 10]          # all 10 copies in ONE split
    rep = json.loads((out / "dataset_report.json").read_text())
    assert rep["leakage_by_source"]["v"]["phash_near_dup_in_train_val"] == 0
    # ML-24: report counts come from the same data as the manifest
    rows = list(csv.DictReader(open(out / "heldout_manifest.csv")))
    assert rep["heldout_originals"] == rep["splits"]["heldout"]["images"] == len([r for r in rows if not r["variant_of"]])
    assert sum(v for k, v in rep["heldout_original_boxes_by_class"].items()) == rep["splits"]["heldout"]["milk/fresh"]


def test_stratified_split_covers_every_cell_with_two_groups():
    def rec(i, cell):
        n, f = cell.split("/")
        return dict(src="s", path=Path(f"x{i}.jpg"), group=f"g{i}", boxes=[dict(name=n, freshness=f)])
    recs, n = [], 0
    for cell, k in (("potato/fresh", 40), ("potato/spoiled", 40), ("tomato/spoiled", 30)):
        for _ in range(k):
            recs.append(rec(n, cell)); n += 1
    recs.append(rec(n, "kale/fresh"))               # 1 image: too small -> listed, not silently dropped
    split, info = P.assign_splits(recs, 0.1, 0.1, 42)
    assert not info["cells_not_in_heldout"] and not info["cells_not_in_val"]
    assert "kale/fresh" in info["not_measurable_cells_lt_min_images"]
    # a cell held by ONE group cannot be split without leakage: stays in train and is reported
    one = [dict(src="s", path=Path(f"o{i}.jpg"), group="same", boxes=[dict(name="onion", freshness="spoiled")]) for i in range(20)]
    split, info = P.assign_splits(recs + one, 0.1, 0.1, 42)
    assert split["same"] == "train" and "onion/spoiled" in info["single_group_cells_kept_in_train_not_measurable"]


def test_no_cell_exists_only_outside_train():
    import random
    for seed in range(25):
        rnd = random.Random(seed)
        recs, n = [], 0
        for cell in ("eggplant/spoiled", "onion/fresh", "potato/spoiled", "tomato/fresh", "apple/spoiled"):
            for gi in range(rnd.choice([1, 2, 2, 3, 5])):             # few big groups per cell
                for _ in range(rnd.choice([5, 40, 300])):
                    nme, fr = cell.split("/")
                    recs.append(dict(src="s", path=Path(f"x{n}.jpg"), group=f"{cell}#{gi}",
                                     boxes=[dict(name=nme, freshness=fr)])); n += 1
        split, info = P.assign_splits(recs, 0.1, 0.1, seed)
        per = {}
        for r in recs:
            k = f"{r['boxes'][0]['name']}/{r['boxes'][0]['freshness']}"
            per.setdefault(k, set()).add(split[r["group"]])
        for k, sp in per.items():
            assert "train" in sp, (seed, k, sp)                           # never held-out/val only
            if k in info["single_group_cells_kept_in_train_not_measurable"]:
                assert sp == {"train"}


def _sess_recs(spec):
    """spec: {cell: [session sizes]} -> one group per session, one image per box"""
    recs, n = [], 0
    for cell, sizes in spec.items():
        nm_, fr = cell.split("/")
        for si, sz in enumerate(sizes):
            for _ in range(sz):
                recs.append(dict(src="s", path=Path(f"x{n}.jpg"), group=f"{cell}#{si}",
                                 boxes=[dict(name=nm_, freshness=fr)])); n += 1
    return recs


def test_required_cells_get_a_whole_session_in_heldout_and_others_stay_in_train():
    # real cases: apple/spoiled 26/125/1/98, bell_pepper/spoiled 45/158/47/6/332, eggplant/spoiled 369+3
    recs = _sess_recs({"apple/spoiled": [26, 125, 1, 98], "bell_pepper/spoiled": [45, 158, 47, 6, 332],
                       "eggplant/spoiled": [369, 3], "onion/fresh": [411], "potato/fresh": [300, 200, 150]})
    split, info = P.assign_splits(recs, 0.1, 0.1, 42, min_session_images=10)
    d = info["cell_decisions"]
    assert d["apple/spoiled"]["decision"] == "required_in_heldout" and split["apple/spoiled#3"] == "heldout"   # the 98
    assert split["apple/spoiled#1"] == "train" and split["apple/spoiled#0"] in ("train", "val")                 # 125 stays; 26 may feed val
    assert d["bell_pepper/spoiled"]["decision"] == "required_in_heldout"
    assert any(split[f"bell_pepper/spoiled#{i}"] == "heldout" for i in range(5))
    assert any(split[f"bell_pepper/spoiled#{i}"] == "train" for i in range(5))
    assert d["eggplant/spoiled"]["decision"] == "not_measurable_on_heldout" and d["eggplant/spoiled"]["sessions"] == 2
    assert split["eggplant/spoiled#0"] == split["eggplant/spoiled#1"] == "train"                              # entirely train
    assert d["onion/fresh"]["decision"] == "not_measurable_on_heldout" and split["onion/fresh#0"] == "train"
    assert not info["required_cells_missing_from_heldout"]
    # configurable: with --min-session-images 1 the 3-image eggplant session counts and the cell becomes required
    _, info1 = P.assign_splits(recs, 0.1, 0.1, 42, min_session_images=1)
    assert info1["cell_decisions"]["eggplant/spoiled"]["decision"] == "required_in_heldout"
