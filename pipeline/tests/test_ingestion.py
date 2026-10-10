import csv
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from pipeline import config
from pipeline.ingestion import agrifreshnet, datasets, generic
from pipeline.ingestion.ledger import Ledger
from .conftest import build_drop, jpeg_bytes, make_jpeg, zip_dir


@pytest.mark.parametrize("name,canon,fr,lo,hi", [
    ("Fresh Banana(1-4)", "banana", "fresh", 1, 4),
    ("Semi fresh Pineapple (15-25)", "pineapple", "semi_fresh", 15, 25),
    ("Semi_Fresh eggplant(4-8)", "eggplant", "semi_fresh", 4, 8),
    ("Rotten Orange(20-35)", "orange", "spoiled", 20, 35),
    ("Semi Fresh Bittermelon ( 3-5)", "bitter_melon", "semi_fresh", 3, 5),
])
def test_agrifreshnet_folder_names(name, canon, fr, lo, hi):
    from pipeline.ingestion.datasets import T
    p = agrifreshnet.parse_dir(name)
    assert p and T.canonical_name(p["item"]) == canon
    assert p["freshness"] == fr and (p["age_days_min"], p["age_days_max"]) == (lo, hi)


def test_agrifreshnet_requires_freshness_word():
    assert agrifreshnet.parse_dir("Banana") is None
    assert generic.parse_dir("Banana")["freshness"] is None


@pytest.mark.parametrize("stem,aug", [("aug_3_IMG_0001", True), ("IMG_0001", False)])
def test_group_aug_shares_group_with_original(stem, aug):
    g, is_aug = agrifreshnet.group_of("banana__fresh", stem)
    assert is_aug is aug
    assert g == agrifreshnet.group_of("banana__fresh", "IMG_0001")[0]


def test_group_burst_and_suffixes():
    a = agrifreshnet.group_of("c", "IMG_20240101_101015_HDR")[0]
    b = agrifreshnet.group_of("c", "IMG_20240101_101059_AE")[0]
    c = agrifreshnet.group_of("c", "IMG_20240101_101159")[0]
    assert a == b and a != c
    assert "HDR" not in a and "_AE" not in b


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
    assert set(rep["unmapped_dirs"]) == {"Mystery Thing", "Fresh Unobtainium(1-2)"}
    rows = list(csv.DictReader(open(out / "manifest.csv")))
    assert len(rows) == rep["staged"]
    assert json.loads((out / "ingest_report.json").read_text())["staged"] == rep["staged"]
    assert sum(rep[f"freshness:{f}"] for f in ("fresh", "semi_fresh", "spoiled")) == rep["staged"]


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
        assert f.name.endswith(f".rf.{r['sha1'][:16]}.jpg")
        with Image.open(f) as im:
            assert im.mode == "RGB" and im.size == (int(r["width"]), int(r["height"]))
    names = {p.name for p in out.iterdir() if p.is_dir()}
    assert {"banana__fresh", "pineapple__semi_fresh", "eggplant__semi_fresh", "orange__spoiled",
            "bitter_melon__semi_fresh"} <= names
    assert any(r["age_days_min"] == "15" and r["age_days_max"] == "25"
               for r in csv.DictReader(open(out / "manifest.csv")) if r["canonical"] == "pineapple")


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
    assert s["class_map"]["pineapple__semi_fresh"] == "pineapple:semi_fresh"
    assert s["class_map"]["bitter_melon__semi_fresh"] == "bitter_melon:semi_fresh"


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
