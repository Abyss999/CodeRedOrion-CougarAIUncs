import csv
import json
import re
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from pipeline import config
from pipeline.ingestion import agrifreshnet, datasets, generic
from pipeline.ingestion.ledger import Ledger
from .conftest import HAS_SEMI, build_drop, jpeg_bytes, make_jpeg, needs_class, needs_semi, semi_label, zip_dir
import taxonomy as T


@pytest.mark.parametrize("name,canon,fr,lo,hi", [
    ("Fresh Banana(1-4)", "banana", "fresh", 1, 4),
    pytest.param("Semi fresh Pineapple (15-25)", "pineapple", "semi", 15, 25, marks=needs_class("pineapple")),
    ("Semi_Fresh eggplant(4-8)", "eggplant", "semi", 4, 8),
    ("Rotten Orange(20-35)", "orange", "spoiled", 20, 35),
    pytest.param("Semi Fresh Bittermelon ( 3-5)", "bitter_melon", "semi", 3, 5, marks=needs_class("bitter_melon")),
])
def test_agrifreshnet_folder_names(name, canon, fr, lo, hi):
    p = agrifreshnet.parse_dir(name)
    assert p and T.canonical_name(p["item"]) == canon
    assert p["freshness"] == (semi_label() if fr == "semi" else fr)
    assert (p["age_days_min"], p["age_days_max"]) == (lo, hi)
    assert p["source_freshness"] == ("semi_fresh" if fr == "semi" else fr)


def test_semi_fresh_mapped_to_fresh_is_flagged_not_silent():
    p = agrifreshnet.parse_dir("Semi_Fresh eggplant(4-8)")
    assert p["item"] == "eggplant" and p["source_freshness"] == "semi_fresh"
    assert p["semi_mapped_to_fresh"] is (not HAS_SEMI)
    assert agrifreshnet.parse_dir("Fresh Banana(1-4)")["semi_mapped_to_fresh"] is False


def test_agrifreshnet_licence_recorded():
    assert agrifreshnet.LICENCE == "CC BY 4.0"
    assert "42m5tb7yv9" in agrifreshnet.URL and agrifreshnet.DOI == "10.17632/42m5tb7yv9.1"
    assert "UNVERIFIED" not in agrifreshnet.LICENCE + agrifreshnet.URL + agrifreshnet.CITATION


def test_agrifreshnet_requires_freshness_word():
    assert agrifreshnet.parse_dir("Banana") is None
    assert generic.parse_dir("Banana")["freshness"] is None


@pytest.mark.parametrize("stem,aug", [("aug_3_IMG_0001", True), ("IMG_0001", False)])
def test_group_aug_shares_group_with_original(stem, aug):
    g, is_aug = agrifreshnet.group_of("banana__fresh", stem)
    assert is_aug is aug
    assert g == agrifreshnet.group_of("banana__fresh", "IMG_0001")[0]


def test_group_keeps_full_timestamp_and_strips_suffixes():
    a = agrifreshnet.group_of("c", "IMG_20240101_101015_HDR")[0]
    a2 = agrifreshnet.group_of("c", "aug_4_IMG_20240101_101015")[0]
    b = agrifreshnet.group_of("c", "IMG_20240101_101059_AE")[0]
    assert a == a2 == "c__IMG_20240101_101015"          # same shot: HDR copy + authors' augmentation
    assert b == "c__IMG_20240101_101059"                # NOT truncated to the minute any more
    assert "HDR" not in a and "_AE" not in b


# the pattern ml/yolo/prepare_dataset.parse_capture_time uses on feat/ml-full-data, as a search over the
# part before '.rf.' (it is anchored today; the ML branch is switching it to re.search).
_ML_TS = [re.compile(r"(?:IMG|PXL|VID)?_?(\d{8})_?(\d{6})(?!\d)"), re.compile(r"(\d{13})(?!\d)")]


def _ml_time(name: str):
    stem = Path(name).stem.split(".rf.")[0]
    for rx in _ML_TS:
        m = rx.search(stem)
        if m:
            return m.groups()
    return None


@pytest.mark.parametrize("fname,expect", [
    ("IMG_20250101_123456.jpg", ("20250101", "123456")),
    ("aug_7_IMG_20250101_123456.jpg", ("20250101", "123456")),
    ("IMG20250926100615.jpg", ("20250926", "100615")),
    ("IMG_20250101_123456_HDR.jpg", ("20250101", "123456")),
    ("1758873619153.jpg", ("1758873619153",)),
    ("IMG_0042.jpg", None),
])
def test_staged_name_keeps_capture_timestamp(tmp_path, fname, expect):
    d = tmp_path / "drop" / "Fresh Banana(1-4)"
    make_jpeg(d / fname, 7)
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    rep = datasets.ingest(tmp_path / "drop", "s", "agrifreshnet", dirs["staged"], led)
    led.close()
    assert rep["staged"] == 1
    staged = next((dirs["staged"] / "s").rglob("*.rf.*.jpg"))
    assert ".rf." in staged.name and staged.name.startswith("banana__fresh__")
    assert _ml_time(staged.name) == expect
    if expect:
        token = re.sub(r"^aug_\d+_", "", fname).rsplit(".", 1)[0].replace("_HDR", "")
        assert token in staged.name.split(".rf.")[0]


def test_timestamp_survives_long_names_and_other_chars(tmp_path):
    d = tmp_path / "drop" / "Fresh Banana(1-4)"
    make_jpeg(d / ("phone camera roll " * 8 + "IMG_20250101_123456 (2).jpg"), 8)
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    datasets.ingest(tmp_path / "drop", "s", "folders", dirs["staged"], led)
    led.close()
    staged = next((dirs["staged"] / "s").rglob("*.rf.*.jpg"))
    assert _ml_time(staged.name) == ("20250101", "123456")
    assert " " not in staged.name


def test_original_and_source_aug_share_group_with_timestamp(staged_ts):
    rows = staged_ts
    assert len({r["group"] for r in rows}) == 1 and len(rows) == 2
    assert {r["is_source_aug"] for r in rows} == {"0", "1"}
    assert all(".rf." in r["image"] and "IMG_20250101_123456" in r["image"] for r in rows)


@pytest.fixture
def staged_ts(tmp_path):
    d = tmp_path / "drop" / "Fresh Banana(1-4)"
    make_jpeg(d / "IMG_20250101_123456.jpg", 1)
    make_jpeg(d / "aug_2_IMG_20250101_123456.jpg", 2)
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    datasets.ingest(tmp_path / "drop", "s", "agrifreshnet", dirs["staged"], led)
    led.close()
    return list(csv.DictReader(open(dirs["staged"] / "s" / "manifest.csv")))


def test_extract_nested_zip(tmp_path):
    inner_src = tmp_path / "in"
    make_jpeg(inner_src / "Fresh Banana(1-4)" / "a.jpg", 1)
    inner = zip_dir(inner_src, tmp_path / "inner.zip")
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as z:
        z.write(inner, "Processed Data.zip")
    dest = datasets.extract(outer, tmp_path / "out")
    assert list(dest.rglob("a.jpg"))
    assert not list(dest.rglob("*.zip"))


def test_extract_rejects_zip_slip(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../escape.txt", "x")
    with pytest.raises(datasets.ExtractError):
        datasets.extract(z, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_extract_rejects_oversize(tmp_path):
    z = tmp_path / "big.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("a.bin", b"0" * 5000)
    with pytest.raises(datasets.ExtractError):
        datasets.extract(z, tmp_path / "out", max_bytes=1000)


def test_extract_rejects_deep_nesting(tmp_path):
    cur = tmp_path / "l0.zip"
    with zipfile.ZipFile(cur, "w") as f:
        f.writestr("x.txt", "x")
    for i in range(1, 6):
        nxt = tmp_path / f"l{i}.zip"
        with zipfile.ZipFile(nxt, "w") as f:
            f.write(cur, f"l{i-1}.zip")
        cur = nxt
    with pytest.raises(datasets.ExtractError):
        datasets.extract(cur, tmp_path / "out")


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    base = tmp_path_factory.mktemp("ing")
    drop = build_drop(base / "drop", per_class=12)
    # duplicate within a class, label conflict across classes, junk, unmapped
    (drop / "Fresh Banana(1-4)" / "dup.jpg").write_bytes((drop / "Fresh Banana(1-4)" / "IMG_0001.jpg").read_bytes())
    cb = jpeg_bytes(999)
    (drop / "Rotten Orange(20-35)" / "conf.jpg").write_bytes(cb)
    (drop / "Fresh Banana(1-4)" / "conf2.jpg").write_bytes(cb)
    (drop / "Fresh Banana(1-4)" / "broken.jpg").write_bytes(b"not an image")
    make_jpeg(drop / "Mystery Thing" / "z.jpg", 4242)
    make_jpeg(drop / "Fresh Unobtainium(1-2)" / "z.jpg", 4243)
    zp = zip_dir(drop, base / "drop.zip")
    dirs = config.data_dirs(base / "data")
    rep = datasets.ingest_zip(zp, "synth", "agrifreshnet", dirs)
    return dirs, rep, zp


def test_report_counts(staged):
    dirs, rep, _ = staged
    out = dirs["staged"] / "synth"
    assert rep["duplicates_in_drop"] == 1
    assert rep["label_conflicts_dropped"] == 2
    assert sorted(rep["label_conflict_files"]) == ["Fresh Banana(1-4)/conf2.jpg", "Rotten Orange(20-35)/conf.jpg"]
    assert len(rep["bad_images"]) == 1 and "broken.jpg" in rep["bad_images"][0]
    missing = {d for d, c in (("Semi fresh Pineapple (15-25)", "pineapple"), ("Semi Fresh Bittermelon ( 3-5)", "bitter_melon"))
               if c not in T.CLASS_CATEGORY}  # classes main does not model (PR A adds them)
    assert set(rep["unmapped_dirs"]) == {"Mystery Thing", "Fresh Unobtainium(1-2)"} | missing
    rows = list(csv.DictReader(open(out / "manifest.csv")))
    assert len(rows) == rep["staged"]
    assert json.loads((out / "ingest_report.json").read_text())["staged"] == rep["staged"]
    assert sum(rep.get(f"freshness:{f}", 0) for f in ("fresh", "semi_fresh", "spoiled")) == rep["staged"]
    # semi-fresh folders are reported, never dropped silently
    if HAS_SEMI:
        assert not rep.get("semi_fresh_mapped_to_fresh")
    else:
        assert rep["semi_fresh_mapped_to_fresh"] > 0 and rep.get("freshness:semi_fresh", 0) == 0
        assert "semi_fresh" in rep["notes"][0]
        assert any("Semi" in d and "eggplant" in d for d in [m["source_dir"] for m in csv.DictReader(
            open(dirs["staged"] / "synth" / "manifest.csv"))])
    if "pineapple" not in T.CLASS_CATEGORY:  # a class main does not model is listed as unmapped
        assert "Semi fresh Pineapple (15-25)" in rep["unmapped_dirs"]


def test_layout_and_manifest(staged):
    dirs, rep, _ = staged
    out = dirs["staged"] / "synth"
    cols = datasets.MANIFEST_COLS
    rd = csv.DictReader(open(out / "manifest.csv"))
    assert rd.fieldnames == cols
    for r in rd:
        f = out / r["image"]
        assert f.exists() and f.suffix == ".jpg"
        assert ".rf." in f.name and f.parent.name == f"{r['canonical']}__{r['freshness']}"
        assert f.name.endswith(f".rf.{r['sha1'][:16]}.jpg")  # <group>.rf.<sha>
        with Image.open(f) as im:
            assert im.mode == "RGB" and im.size == (int(r["width"]), int(r["height"]))
    names = {p.name for p in out.iterdir() if p.is_dir()}
    assert {"banana__fresh", f"eggplant__{semi_label()}", "orange__spoiled"} <= names
    if "pineapple" in T.CLASS_CATEGORY:
        assert f"pineapple__{semi_label()}" in names
        assert any(r["age_days_min"] == "15" and r["age_days_max"] == "25"
                   for r in csv.DictReader(open(out / "manifest.csv")) if r["canonical"] == "pineapple")
    assert any(r["age_days_min"] == "4" and r["source_freshness"] == "semi_fresh"
               for r in csv.DictReader(open(out / "manifest.csv")) if r["canonical"] == "eggplant")


def test_conflict_not_staged_anywhere(staged):
    dirs, _, _ = staged
    shas = [r["sha1"] for r in csv.DictReader(open(dirs["staged"] / "synth" / "manifest.csv"))]
    assert len(shas) == len(set(shas))
    import hashlib
    assert hashlib.sha1(jpeg_bytes(999)).hexdigest() not in shas


def test_source_json(staged):
    dirs, _, _ = staged
    s = json.loads((dirs["staged"] / "synth" / "source.json").read_text())
    assert s["kind"] == "folders" and s["name"] == "synth"
    assert s["class_map"][f"eggplant__{semi_label()}"] == f"eggplant:{semi_label()}"
    assert s["license"] == "CC BY 4.0" and "mendeley" in s["url"]
    if "pineapple" in T.CLASS_CATEGORY:
        assert s["class_map"][f"pineapple__{semi_label()}"] == f"pineapple:{semi_label()}"


def test_idempotent_rerun(staged):
    dirs, rep1, zp = staged
    n_files = len(list((dirs["staged"] / "synth").rglob("*.jpg")))
    rep2 = datasets.ingest_zip(zp, "synth", "agrifreshnet", dirs)
    assert rep2.get("staged", 0) == 0
    assert len(list((dirs["staged"] / "synth").rglob("*.jpg"))) == n_files
    rows = list(csv.DictReader(open(dirs["staged"] / "synth" / "manifest.csv")))
    assert len(rows) == rep1["staged"]


def test_non_jpeg_reencoded_and_rgba(tmp_path):
    d = tmp_path / "drop" / "Fresh Banana(1-4)"
    d.mkdir(parents=True)
    Image.new("RGBA", (20, 20), (255, 0, 0, 128)).save(d / "a.png")
    dirs = config.data_dirs(tmp_path / "data")
    rep = datasets.ingest(tmp_path / "drop", "p", "folders", dirs["staged"], Ledger(dirs["staged"] / "l.sqlite"))
    assert rep["staged"] == 1
    f = next((dirs["staged"] / "p").rglob("*.jpg"))
    with Image.open(f) as im:
        assert im.format == "JPEG" and im.mode == "RGB"


def test_zip_slip_via_ingest_zip_leaves_no_data(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../../evil.txt", "x")
    with pytest.raises(datasets.ExtractError):
        datasets.ingest_zip(z, "evil", "folders", config.data_dirs(tmp_path / "data"))
    assert not (tmp_path.parent / "evil.txt").exists()


def test_cross_drop_conflict_and_same_class_redrop(tmp_path):
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    a = make_jpeg(tmp_path / "a" / "Fresh Banana(1-4)" / "x.jpg", 1)
    r1 = datasets.ingest(tmp_path / "a", "s", "agrifreshnet", dirs["staged"], led)
    assert r1["staged"] == 1
    # same bytes, different class, later drop -> conflict, not staged
    (tmp_path / "b" / "Rotten Banana(9-9)").mkdir(parents=True)
    (tmp_path / "b" / "Rotten Banana(9-9)" / "x.jpg").write_bytes(a.read_bytes())
    r2 = datasets.ingest(tmp_path / "b", "s", "agrifreshnet", dirs["staged"], led)
    assert r2.get("staged", 0) == 0 and r2["label_conflicts_cross_drop"] == 1
    assert len(r2["label_conflicts_cross_drop_files"]) == 1
    assert "skipped_seen" not in r2
    rep = json.loads((dirs["staged"] / "s" / "ingest_report.json").read_text())
    assert rep["label_conflicts_cross_drop"] == 1
    assert len(list((dirs["staged"] / "s").rglob("*.jpg"))) == 1  # earlier copy kept
    assert not (dirs["staged"] / "s" / "banana__spoiled").exists()
    # same bytes, same class, re-dropped -> plain skipped_seen
    (tmp_path / "c" / "Fresh Banana(1-4)").mkdir(parents=True)
    (tmp_path / "c" / "Fresh Banana(1-4)" / "y.jpg").write_bytes(a.read_bytes())
    r3 = datasets.ingest(tmp_path / "c", "s", "agrifreshnet", dirs["staged"], led)
    assert r3["skipped_seen"] == 1 and not r3.get("label_conflicts_cross_drop")
    assert r3.get("staged", 0) == 0
    led.close()
