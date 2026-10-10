import csv
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline import cli, config
from pipeline.ingestion import datasets
from pipeline.ingestion.ledger import Ledger
from pipeline.shots.preview import contact_sheet
from pipeline.transformation import lighting_aug as LA
from pipeline.transformation.stage import prepare, collect_sources
from .conftest import build_drop, make_jpeg


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("w")
    drop = build_drop(base / "drop", per_class=40)
    dirs = config.data_dirs(base / "data")
    led = Ledger(dirs["staged"] / "ledger.sqlite")
    datasets.ingest(drop, "synth", "agrifreshnet", dirs["staged"], led)
    led.close()
    rep = prepare(dirs["staged"], dirs["prepared"])
    return dirs, rep


def _md5_tree(root):
    return {str(p.relative_to(root)): hashlib.md5(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def test_prepare_outputs(world):
    dirs, rep = world
    P = dirs["prepared"]
    assert rep["boxes_by_freshness"]["semi_fresh"] > 0 and rep["boxes_by_freshness"]["spoiled"] > 0
    for s in ("train", "val"):
        assert list((P / "cls" / s / "semi_fresh").glob("*.jpg")), s
    codes = set()
    for s in ("train", "val", "heldout"):
        for f in (P / "freshness" / s).glob("*.txt"):
            codes.add(f.read_text().split()[0])
    assert codes == {"0", "1", "2"}
    # a semi_fresh pineapple image carries code 2
    f = next(p for p in (P / "freshness" / "train").glob("*.txt") if "pineapple" in p.name)
    assert f.read_text().split()[0] == "2"
    assert (P / "data.yaml").exists() and (P / "dataset_report.json").exists()


def test_no_group_straddles_splits(world):
    dirs, _ = world
    P = dirs["prepared"]
    man = list(csv.DictReader(open(dirs["staged"] / "synth" / "manifest.csv")))
    by_group = defaultdict(set)
    for r in man:
        pat = f"synth_{r['group']}_rf_{r['sha1'][:16]}_"
        for s in ("train", "val", "heldout"):
            if any(p.name.startswith(pat) for p in (P / "images" / s).iterdir()):
                by_group[r["group"]].add(s)
    assert len(by_group) == len({r["group"] for r in man})
    assert all(len(v) == 1 for v in by_group.values()), {g: v for g, v in by_group.items() if len(v) > 1}
    assert any(r["is_source_aug"] == "1" for r in man)


def test_prepare_refuses_nonempty_without_replace(world):
    dirs, _ = world
    with pytest.raises(SystemExit):
        prepare(dirs["staged"], dirs["prepared"])


def test_prepare_replace_and_no_staged(tmp_path, world):
    dirs, _ = world
    out = tmp_path / "out"
    prepare(dirs["staged"], out)
    (out / "stale.txt").write_text("x")
    prepare(dirs["staged"], out, replace=True)
    assert not (out / "stale.txt").exists()
    with pytest.raises(SystemExit):
        prepare(tmp_path / "nostaged", tmp_path / "o2")


def test_duplicate_source_names_rejected(world, tmp_path):
    dirs, _ = world
    extra = tmp_path / "s.json"
    extra.write_text(json.dumps({"sources": [{"name": "synth", "kind": "folders", "root": str(tmp_path)}]}))
    with pytest.raises(ValueError):
        collect_sources(dirs["staged"], [extra])


# ------------------------------------------------------------------ augmentation
@pytest.fixture(scope="module")
def aug(world):
    dirs, _ = world
    before = _md5_tree(dirs["prepared"])
    rep = LA.augment(dirs["prepared"], dirs["augmented"], per_image=2, seed=3)
    return dirs, rep, before


def test_prepared_untouched(aug):
    dirs, _, before = aug
    assert _md5_tree(dirs["prepared"]) == before
    assert "augmented" not in (dirs["prepared"] / "data.yaml").read_text()


def test_data_yaml_points_at_augmented(aug):
    dirs, _, _ = aug
    txt = (dirs["augmented"] / "data.yaml").read_text()
    m = re.search(r"^path:\s*(.+)$", txt, re.M)
    assert Path(m.group(1).strip()) == dirs["augmented"].resolve()
    assert re.search(r"^path:\s*(.+)$", (dirs["prepared"] / "data.yaml").read_text(), re.M).group(1).strip() \
        != m.group(1).strip()


def test_heldout_identical(aug):
    dirs, _, _ = aug
    P, A = dirs["prepared"], dirs["augmented"]
    for sub in ("images", "labels", "freshness"):
        a = sorted((A / sub / "heldout").iterdir()) if (A / sub / "heldout").exists() else []
        b = sorted((P / sub / "heldout").iterdir()) if (P / sub / "heldout").exists() else []
        assert [x.name for x in a] == [x.name for x in b]
        assert all(x.read_bytes() == y.read_bytes() for x, y in zip(a, b))
    assert not [p for p in A.rglob("*__lt_*") if "heldout" in p.parts]


def test_variants_labels_and_counts(aug):
    dirs, rep, _ = aug
    P, A = dirs["prepared"], dirs["augmented"]
    rows = list(csv.DictReader(open(A / "augment_manifest.csv")))
    assert rows and all(r["split"] in ("train", "val") for r in rows)
    det = [r for r in rows if r["kind"] == "detector"]
    crops = [r for r in rows if r["kind"] == "crop"]
    assert crops
    for r in rows:
        assert (A / r["image"]).exists()
    # per image: 2 distinct presets
    per = defaultdict(list)
    for r in det:
        per[r["variant_of"]].append(r["preset"])
    assert all(len(v) == 2 and len(set(v)) == 2 for v in per.values())
    n_orig = {s: len(list((P / "images" / s).iterdir())) for s in ("train", "val")}
    assert len(det) == 2 * (n_orig["train"] + n_orig["val"])
    for r in det:
        stem = Path(r["image"]).stem
        orig = Path(r["variant_of"]).stem
        assert stem == f"{orig}__lt_{r['preset']}"
        for sub in ("labels", "freshness"):
            o, v = P / sub / r["split"] / f"{orig}.txt", A / sub / r["split"] / f"{stem}.txt"
            assert o.exists() == v.exists()
            if o.exists():
                assert o.read_text() == v.read_text()
    for r in crops:
        v, o = Path(r["image"]), Path(r["variant_of"])
        assert v.parent == o.parent and v.parent.name in ("fresh", "semi_fresh", "spoiled")
    # report consistent with disk
    c = rep["counts"]
    assert sum(v for k, v in c.items() if k.endswith(":images")) == len(det)
    assert sum(v for k, v in c.items() if k.endswith(":crops")) == len(crops)
    assert json.loads((A / "augment_report.json").read_text())["counts"] == c
    on_disk = [p for p in (A / "images").rglob("*__lt_*")]
    assert len(on_disk) == len(det)


def test_deterministic(world, tmp_path):
    dirs, _ = world
    a = LA.augment(dirs["prepared"], tmp_path / "a", per_image=1, seed=11, include_crops=False)
    b = LA.augment(dirs["prepared"], tmp_path / "b", per_image=1, seed=11, include_crops=False)
    assert a["counts"] == b["counts"]
    fa = {p.name: p.read_bytes() for p in (tmp_path / "a" / "images").rglob("*__lt_*")}
    fb = {p.name: p.read_bytes() for p in (tmp_path / "b" / "images").rglob("*__lt_*")}
    assert fa == fb and fa
    c = LA.augment(dirs["prepared"], tmp_path / "c", per_image=1, seed=12, include_crops=False)
    fc = {p.name: p.read_bytes() for p in (tmp_path / "c" / "images").rglob("*__lt_*")}
    assert fc != fa


def test_refuse_nonempty_replace_unknown_preset(world, tmp_path):
    dirs, _ = world
    with pytest.raises(SystemExit):
        LA.augment(dirs["prepared"], dirs["augmented"])
    with pytest.raises(SystemExit):
        LA.augment(dirs["prepared"], tmp_path / "x", presets=["lowlight"])
    assert not (tmp_path / "x").exists()
    with pytest.raises(SystemExit):
        LA.augment(tmp_path, tmp_path / "y")  # not a prepared dataset
    out = tmp_path / "r"
    LA.augment(dirs["prepared"], out, per_image=1, include_crops=False)
    (out / "stale").write_text("x")
    LA.augment(dirs["prepared"], out, per_image=1, include_crops=False, replace=True)
    assert not (out / "stale").exists()


def test_presets_subset_and_per_image_clamped(world, tmp_path):
    dirs, _ = world
    rep = LA.augment(dirs["prepared"], tmp_path / "o", per_image=5, presets=["low", "warm"], include_crops=False)
    assert rep["per_image"] == 2
    assert {r["preset"] for r in csv.DictReader(open(tmp_path / "o" / "augment_manifest.csv"))} == {"low", "warm"}


def _img(seed=5, size=(64, 64)):
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(60, 200, (size[1], size[0], 3), dtype=np.uint8))


def _luma(im):
    a = np.asarray(im, np.float32)
    return float((0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]).mean())


def _rb(im):
    a = np.asarray(im, np.float32)
    return float(a[..., 0].mean() / a[..., 2].mean())


@pytest.mark.parametrize("seed", range(5))
def test_preset_directions(seed):
    specs = LA.load_presets()
    base = _img(seed)
    out = {n: LA.variant(base, n, specs[n], seed)[0] for n in specs}
    for n, im in out.items():
        a = np.asarray(im)
        assert a.dtype == np.uint8 and im.size == base.size and im.mode == "RGB", n
    assert _luma(out["low"]) < _luma(base) * 0.65
    assert _luma(out["bright"]) > _luma(base) * 1.15
    assert _rb(out["warm"]) > _rb(base) * 1.05
    assert _rb(out["cool"]) < _rb(base) * 0.95
    assert _luma(out["mixed"]) < _luma(base)
    assert _luma(out["shadow"]) < _luma(base) and _luma(out["spot"]) < _luma(base)


def test_unknown_preset_apply_raises():
    with pytest.raises(ValueError):
        LA.apply(_img(), "nope", {})


def test_max_side_shrinks_only_larger(tmp_path, world):
    dirs, _ = world
    src = tmp_path / "p"
    LA._link_tree(dirs["prepared"], src)
    big = next((src / "images" / "train").iterdir())
    big.unlink()
    make_jpeg(big.with_suffix(".jpg"), 1, size=(200, 100))
    lab = src / "labels" / "train" / (big.stem + ".txt")
    LA.augment(src, tmp_path / "o", per_image=1, max_side=100, include_crops=False)
    v = next((tmp_path / "o" / "images" / "train").glob(f"{big.stem}__lt_*"))
    assert max(Image.open(v).size) == 100
    other = next(p for p in (tmp_path / "o" / "images" / "train").glob("*__lt_*") if p.name != v.name)
    assert Image.open(other).size == (48, 48)


def test_preview_contact_sheet(tmp_path):
    src = make_jpeg(tmp_path / "a.jpg", 3, size=(80, 60))
    out = contact_sheet(src, tmp_path / "s" / "sheet.jpg", tile=64)
    with Image.open(out) as im:
        assert im.width == 4 * 64 and im.height >= 2 * 64
