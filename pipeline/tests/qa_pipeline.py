"""Pipeline QA tests (independent of the builder's tests). Not named test_*.py, so run by path:

    .venv/bin/python -m pytest pipeline/tests/qa_pipeline.py -q

All data lives under pytest tmp_path.
"""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from pipeline import config
from pipeline.ingestion import agrifreshnet, datasets, receipts
from pipeline.transformation import lighting_aug as LA
from pipeline.transformation.stage import prepare
from pipeline.ingestion.ledger import Ledger
from .conftest import REPO, make_jpeg, zip_dir

import taxonomy as T  # on sys.path via pipeline.config

HAS_SEMI = "semi_fresh" in getattr(T, "FRESHNESS", ("fresh", "spoiled"))
needs_2class = pytest.mark.skipif(HAS_SEMI, reason="2-class behaviour: taxonomy has semi_fresh (PR A merged)")


def _backend_fg():
    p = REPO / "backend" / "app" / "services" / "food_group.py"
    spec = importlib.util.spec_from_file_location("_qa_backend_fg", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ 2-class ingest
def _agri_drop(drop: Path, n=8):
    """AgriFreshNET-like: 5 produce types in main's taxonomy + one that main lacks (pineapple)."""
    seed = 100
    counts = {"fresh": 0, "semi": 0, "rotten": 0, "unmapped": 0}
    layout = {"Fresh Banana(1-4)": "fresh", "Semi fresh Banana(5-9)": "semi", "Rotten Banana(10-20)": "rotten",
              "Fresh Orange(1-5)": "fresh", "Semi_Fresh Orange(6-12)": "semi", "Rotten Orange(20-35)": "rotten",
              "Semi fresh Tomato (4-8)": "semi", "Semi fresh Pineapple (15-25)": "unmapped"}
    for d, kind in layout.items():
        for i in range(n):
            seed += 1
            make_jpeg(drop / d / f"IMG_{i:03d}.jpg", seed, base=(40 + seed % 150, 120, 80))
            counts[kind] += 1
    return counts


@needs_2class
def test_two_class_semi_maps_to_fresh_and_is_counted(tmp_path):
    drop = tmp_path / "drop"
    c = _agri_drop(drop)
    zp = zip_dir(drop, tmp_path / "agri.zip")
    dirs = config.data_dirs(tmp_path / "data")
    rep = datasets.ingest_zip(zp, "agri", "agrifreshnet", dirs)  # must not crash
    total = sum(c.values())
    assert rep["semi_fresh_mapped_to_fresh"] == c["semi"]
    assert rep.get("freshness:semi_fresh", 0) == 0
    assert rep["freshness:fresh"] == c["fresh"] + c["semi"]
    assert rep["freshness:spoiled"] == c["rotten"]
    assert any("semi" in n.lower() for n in rep["notes"])
    # unmapped produce is reported, with its image count
    assert rep["unmapped_dirs"] == {"Semi fresh Pineapple (15-25)": c["unmapped"]}
    # nothing silently dropped: every file is staged or accounted for
    accounted = (rep["staged"] + sum(rep["unmapped_dirs"].values()) + len(rep["bad_images"])
                 + rep.get("label_conflicts_dropped", 0) + rep.get("duplicates_in_drop", 0)
                 + rep.get("skipped_seen", 0) + rep.get("label_conflicts_cross_drop", 0))
    assert accounted == total
    out = dirs["staged"] / "agri"
    assert not [p for p in out.iterdir() if p.name.endswith("__semi_fresh")]
    rows = list(csv.DictReader(open(out / "manifest.csv")))
    assert sum(r["source_freshness"] == "semi_fresh" for r in rows) == c["semi"]
    assert all(r["freshness"] in ("fresh", "spoiled") for r in rows)
    assert all(r["licence"] == "CC BY 4.0" for r in rows)
    assert json.loads((out / "ingest_report.json").read_text())["semi_fresh_mapped_to_fresh"] == c["semi"]
    # the staged set still prepares against main's taxonomy with only classes 0/1
    prep = prepare(dirs["staged"], dirs["prepared"])
    codes = set()
    for s in ("train", "val", "heldout"):
        for f in (dirs["prepared"] / "freshness" / s).glob("*.txt"):
            codes.add(f.read_text().split()[0])
    assert codes <= {"0", "1"} and codes
    assert prep["splits"]


@needs_2class
def test_two_class_fresh_vs_semi_same_bytes_is_still_a_conflict(tmp_path):
    drop = tmp_path / "drop"
    a = make_jpeg(drop / "Fresh Banana(1-4)" / "x.jpg", 1)
    (drop / "Semi fresh Banana(5-9)").mkdir(parents=True)
    (drop / "Semi fresh Banana(5-9)" / "y.jpg").write_bytes(a.read_bytes())
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    rep = datasets.ingest(drop, "c", "agrifreshnet", dirs["staged"], led)
    led.close()
    assert rep.get("staged", 0) == 0 and rep["label_conflicts_dropped"] == 2


# ------------------------------------------------------------------ timestamp token (ML-21 on another branch)
GROUPING_RX = re.compile(r"IMG_?(\d{8})_?(\d{6})")


@pytest.mark.parametrize("stem,tok", [
    ("IMG_20250101_123456", ("20250101", "123456")),
    ("IMG_20250101_123456_HDR", ("20250101", "123456")),
    ("aug_7_IMG_20250101_123456", ("20250101", "123456")),
    ("IMG_20250101_123456_AE", ("20250101", "123456")),
    ("IMG-20250101-123456", None),   # dash form: the other branch's regex does not match it either
])
def test_staged_name_keeps_capture_timestamp(tmp_path, stem, tok):
    drop = tmp_path / "drop"
    make_jpeg(drop / "Fresh Banana(1-4)" / f"{stem}.jpg", 5)
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    datasets.ingest(drop, "t", "agrifreshnet", dirs["staged"], led)
    led.close()
    files = list((dirs["staged"] / "t").rglob("*.jpg"))
    assert len(files) == 1
    name = files[0].name
    m = GROUPING_RX.search(name.split(".rf.")[0])
    if tok:
        assert m and m.groups() == tok, name
    # whatever the form, the original HHMMSS digits are not truncated to the minute
    assert "1234" not in name or "123456" in name


def test_distinct_seconds_stay_distinct_and_long_names_keep_token(tmp_path):
    drop = tmp_path / "drop"
    d = drop / "Fresh Banana(1-4)"
    make_jpeg(d / "IMG_20250101_123456.jpg", 1)
    make_jpeg(d / "IMG_20250101_123459.jpg", 2)
    make_jpeg(d / ("x" * 120 + "_IMG_20250101_123500.jpg"), 3)
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    datasets.ingest(drop, "t", "agrifreshnet", dirs["staged"], led)
    led.close()
    toks = sorted(GROUPING_RX.search(p.name.split(".rf.")[0]).group(0) for p in (dirs["staged"] / "t").rglob("*.jpg"))
    assert toks == ["IMG_20250101_123456", "IMG_20250101_123459", "IMG_20250101_123500"]


# ------------------------------------------------------------------ extraction safety (extra variants)
def test_safety_absolute_member_rejected(tmp_path):
    z = tmp_path / "abs.zip"
    target = tmp_path / "abs_escape.txt"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(str(target), "x")
    with pytest.raises(datasets.ExtractError):
        datasets.extract(z, tmp_path / "out")
    assert not target.exists()


def test_safety_zip_slip_inside_nested_zip(tmp_path):
    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as f:
        f.writestr("../../nested_escape.txt", "x")
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as f:
        f.write(inner, "inner.zip")
    with pytest.raises(datasets.ExtractError):
        datasets.extract(outer, tmp_path / "a" / "out")
    assert not list(tmp_path.rglob("nested_escape.txt"))


def test_safety_oversize_via_env_limit_stops_ingest_zip(tmp_path):
    z = tmp_path / "big.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Fresh Banana(1-4)/a.jpg", b"0" * 4000)
    with pytest.raises(datasets.ExtractError):
        datasets.extract(z, tmp_path / "out", max_bytes=3999)
    datasets.extract(z, tmp_path / "ok", max_bytes=4000)  # boundary: exactly the cap is allowed


def test_safety_forged_small_header_cannot_bypass_size_cap(tmp_path):
    """A zip whose central-directory file_size lies (says small, real data large) must not write the
    real, large data. Either it raises, or the written file is capped at the declared size."""
    z = tmp_path / "forged.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as f:
        f.writestr("a.bin", b"A" * 100_000)
    raw = bytearray(z.read_bytes())
    # patch BOTH local header and central directory uncompressed size (and compressed size) to 10
    for sig, off_c, off_u in ((b"PK\x03\x04", 18, 22), (b"PK\x01\x02", 20, 24)):
        i = raw.find(sig)
        raw[i + off_c:i + off_c + 4] = struct.pack("<I", 10)
        raw[i + off_u:i + off_u + 4] = struct.pack("<I", 10)
    z.write_bytes(raw)
    out = tmp_path / "out"
    try:
        datasets.extract(z, out, max_bytes=1000)
    except (datasets.ExtractError, zipfile.BadZipFile):
        pass
    written = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) if out.exists() else 0
    assert written <= 1000, f"wrote {written} bytes past a 1000-byte cap"


# ------------------------------------------------------------------ food_group on the receipt inbox
def test_receipt_food_group_matches_backend(tmp_path):
    fg = _backend_fg()
    dirs = config.data_dirs(tmp_path / "data")
    inbox = dirs["incoming"] / "receipts"
    p = make_jpeg(inbox / "r.jpg", 9, size=(40, 40))
    p.with_suffix(".txt").write_text("GV WHL MILK GAL    3.98\nKS ORG EGGS        7.49\nBANANAS            1.12\n"
                                     "TOTAL             12.59\n")
    c = receipts.process_inbox(dirs, engine="fake", timeout_s=5, load_grace_s=30)
    assert c["processed"] == 1
    lines = [json.loads(l) for l in (dirs["processed"] / "receipts.jsonl").read_text().splitlines()][0]["lines"]
    got = {l["name"]: l["food_group"] for l in lines}
    assert len(lines) == 3, lines
    groups = list(got.values())
    assert groups == ["dairy", "protein", "fruit"], got
    for l in lines:
        assert l["food_group"] == fg.derive_from_name(l["name"]), l
    rows = list(csv.DictReader(open(dirs["processed"] / "receipt_lines.csv")))
    assert [r["food_group"] for r in rows] == ["dairy", "protein", "fruit"]
    assert all(g in fg.FOOD_GROUPS for g in groups)


def test_food_group_values_always_valid_for_odd_lines():
    from pipeline.category_cleanup.names import clean
    fg = _backend_fg()
    for t in ["", "XQZT 4411", "GV 2% MLK GAL", "ORANGE JUICE", "PNUT BTR", "HONEY NUT CEREAL", "12", "%%%"]:
        assert clean(t)["food_group"] in fg.FOOD_GROUPS, t


# ------------------------------------------------------------------ no duplicate table / no Flask
def test_no_duplicated_abbreviation_entries():
    fg = _backend_fg()
    ex = json.loads((REPO / "pipeline" / "category_cleanup" / "abbreviations.json").read_text())["expand"]
    assert not (set(ex) & set(fg.ABBREVIATIONS)), sorted(set(ex) & set(fg.ABBREVIATIONS))
    # no second copy of the backend table anywhere in pipeline/ (python or json)
    hits = []
    for p in (REPO / "pipeline").rglob("*"):
        if p.suffix in (".py", ".json") and "tests" not in p.parts and "data" not in p.parts:
            t = p.read_text()
            hits += [(p.name, k) for k in ("chkn", "shrmp", "trky", "sausg") if f'"{k}"' in t and p.name != "qa_pipeline.py"]
    assert not hits, hits


def test_names_module_loads_without_flask():
    code = ("import sys\nfor m in ('flask','sqlalchemy','flask_sqlalchemy','flask_migrate'): sys.modules[m]=None\n"
            "from pipeline.category_cleanup.names import clean, backend_food_group\n"
            "assert clean('GV WHL MILK GAL')['food_group']=='dairy'\n"
            "assert 'app' not in sys.modules and 'app.services' not in sys.modules\nprint('ok')")
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


# ------------------------------------------------------------------ licence
def test_licence_set_and_no_unverified_in_agrifreshnet_path():
    assert agrifreshnet.LICENCE == "CC BY 4.0"
    assert "42m5tb7yv9" in agrifreshnet.URL and agrifreshnet.DOI == "10.17632/42m5tb7yv9.1"
    src = (REPO / "pipeline" / "ingestion" / "agrifreshnet.py").read_text()
    assert "UNVERIFIED" not in src
    doc = (REPO / "docs" / "PIPELINE.md").read_text()
    assert "unverified" not in doc.lower()
    assert "10.17632/42m5tb7yv9.1" in doc and "CC BY 4.0" in doc


# ------------------------------------------------------------------ lighting
@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    base = tmp_path_factory.mktemp("light")
    drop = base / "drop"
    seed = 500
    for d in ("Fresh Banana(1-4)", "Rotten Banana(10-20)", "Fresh Orange(1-5)", "Rotten Orange(20-35)"):
        for i in range(30):
            seed += 1
            make_jpeg(drop / d / f"IMG_20250101_{i:02d}0000.jpg", seed, base=(50 + seed % 120, 110, 90))
    dirs = config.data_dirs(base / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    datasets.ingest(drop, "s", "agrifreshnet", dirs["staged"], led)
    led.close()
    prepare(dirs["staged"], dirs["prepared"])
    return dirs


def _h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.parametrize("presets", [None, ["all"], ["low", "warm"]])
def test_heldout_never_augmented(prepared, tmp_path, presets):
    dirs = prepared
    out = tmp_path / "aug"
    rep = LA.augment(dirs["prepared"], out, per_image=2, presets=presets, seed=1)
    P = dirs["prepared"]
    assert not [p for p in out.rglob("*__lt_*") if "heldout" in p.parts]
    n = 0
    for p in P.rglob("*"):
        if p.is_file() and "heldout" in p.relative_to(P).parts:
            q = out / p.relative_to(P)
            assert q.exists() and _h(q) == _h(p), q
            n += 1
    assert n > 0
    assert "heldout_family_presets_used" in rep and "lighting_signoff" in rep
    if presets is None:
        assert rep["heldout_family_presets_used"] == [] and not (set(rep["presets"]) & {"low", "warm", "mixed"})
        assert rep["lighting_signoff"].startswith("n/a")
    else:
        assert rep["lighting_signoff"].startswith("none")


def test_lighting_signoff_rule_documented():
    doc = (REPO / "docs" / "PIPELINE.md").read_text()
    assert "no lighting sign-off" in doc
    assert "ML-17" in doc and "ML-22" in doc and "opt-in" in doc.lower()
