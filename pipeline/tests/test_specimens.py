"""Cross-stage, dihedral-variant-aware specimen grouping (pipeline/ingestion/specimens.py)."""
import numpy as np
import pytest
from PIL import Image

from pipeline import config
from pipeline.ingestion import datasets, specimens
from pipeline.ingestion.ledger import Ledger
from .conftest import make_jpeg


def _pic(seed, size=96):
    """Smooth random blobs, not white noise: a stable pHash that survives resampling."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (6, 6, 3), dtype=np.uint8)
    return Image.fromarray(small).resize((size, size), Image.BICUBIC)


@pytest.mark.parametrize("op", [Image.FLIP_LEFT_RIGHT, Image.FLIP_TOP_BOTTOM, Image.ROTATE_90, Image.ROTATE_180,
                                Image.ROTATE_270, Image.TRANSPOSE, Image.TRANSVERSE])
def test_variant_distance_is_zero_for_every_dihedral_copy(op):
    im = _pic(1)
    a = np.array([specimens.variant_hashes(im), specimens.variant_hashes(im.transpose(op))], dtype=np.uint64)
    assert specimens.min_dist_matrix(a, slice(0, 2))[0, 1] <= 2


def test_variant_hash_index0_matches_dedup_phash():
    import dedup
    im = _pic(2)
    assert specimens.variant_hashes(im)[0] == dedup.phash64(im)


def test_different_pictures_stay_apart():
    H = np.array([specimens.variant_hashes(_pic(s)) for s in range(10, 20)], dtype=np.uint64)
    comp, st = specimens.group_class(H)
    assert st["components"] == 10 and st["threshold"] == 10 and not st["tightened"]


def test_flipped_and_rotated_copy_share_a_component():
    base = [_pic(s) for s in (3, 4, 5)]
    ims = base + [base[0].transpose(Image.FLIP_LEFT_RIGHT), base[1].transpose(Image.ROTATE_90)]
    H = np.array([specimens.variant_hashes(i) for i in ims], dtype=np.uint64)
    comp, st = specimens.group_class(H)
    assert comp[0] == comp[3] and comp[1] == comp[4] and len({comp[0], comp[1], comp[2]}) == 3


def test_giant_component_tightens_threshold_and_is_reported():
    # near-identical images chain into one blob at 10 but not at tighter thresholds
    rng = np.random.default_rng(0)
    base = specimens.variant_hashes(_pic(7))[0]
    hs = []
    for i in range(20):                      # flip 3 random bits per step -> chain of growing distance
        base ^= int(1 << int(rng.integers(0, 64))) | int(1 << int(rng.integers(0, 64)))
        hs.append([base] * 8)
    H = np.array(hs, dtype=np.uint64)
    comp, st = specimens.group_class(H, max_frac=0.3, thresholds=(64, 8, 4, 0))
    assert st["tightened"] and st["tried"][0][1] == 1.0
    assert st["largest_frac"] <= 0.3 or st["threshold"] == 0


def _drop(tmp_path, copies):
    """Same specimen photographed in Fresh and Rotten folders (+ a flipped copy); one unrelated image."""
    d = tmp_path / "drop"
    a = _pic(21)
    (d / "Fresh Banana(1-4)").mkdir(parents=True)
    (d / "Rotten banana(7-13)").mkdir(parents=True)
    a.save(d / "Fresh Banana(1-4)" / "Banana (1).jpeg", quality=95)
    a.transpose(Image.FLIP_LEFT_RIGHT).save(d / "Fresh Banana(1-4)" / "aug_0_Banana (1).jpeg", quality=95)
    a.transpose(Image.ROTATE_90).save(d / "Rotten banana(7-13)" / "Banana (2).jpeg", quality=95)
    _pic(22).save(d / "Rotten banana(7-13)" / "Banana (3).jpeg", quality=95)
    return d


def test_ingest_groups_across_stages_and_keeps_original_stem(tmp_path):
    d = _drop(tmp_path, 1)
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    rep = datasets.ingest(d, "s", "agrifreshnet", dirs["staged"], led, specimen_groups=True)
    led.close()
    files = sorted((dirs["staged"] / "s").rglob("*.rf.*.jpg"))
    assert rep["staged"] == 4 and len(files) == 4
    groups = {f.name.split(".rf.")[0] for f in files}
    assert len(groups) == 2 and all(g.startswith("banana__spec_") for g in groups)
    cross = [f for f in files if "Banana_2" in f.name][0]
    fresh = [f for f in files if "Banana_1" in f.name]
    assert cross.name.split(".rf.")[0] == fresh[0].name.split(".rf.")[0] == fresh[1].name.split(".rf.")[0]
    assert cross.parent.name != fresh[0].parent.name        # stages differ, group is shared
    r = rep["specimen_grouping"]["classes"]["banana"]
    assert r["images"] == 4 and r["components"] == 2


def test_ingest_default_is_off(tmp_path, monkeypatch):
    monkeypatch.delenv("PIPELINE_SPECIMEN_GROUPS", raising=False)
    d = _drop(tmp_path, 1)
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    rep = datasets.ingest(d, "s", "agrifreshnet", dirs["staged"], led)
    led.close()
    assert "specimen_grouping" not in rep
    assert all("__spec_" not in f.name for f in (dirs["staged"] / "s").rglob("*.jpg"))


def test_capture_seconds_reads_milliseconds_and_sessions_chain():
    assert specimens.capture_seconds("IMG_20251102_075610660_HDR.jpg") is not None
    assert specimens.capture_seconds("IMG-20251122-WA0003.jpg") is None
    t = [specimens.capture_seconds(n) for n in ("IMG_20251102_075610660.jpg", "IMG_20251102_075900123.jpg",
                                                "IMG_20251102_090000000.jpg", "IMG-20251122-WA0003.jpg")]
    assert specimens.sessions(t) == [0, 0, 1, -1]


def test_sessions_split_giant_union_falls_back_to_session_units(tmp_path):
    """Two specimens, each photographed in two stages on different days: the union (specimen + session) is
    one unit, so the class falls back to session units for timestamped files."""
    d = tmp_path / "drop"
    for stage, day in (("Fresh Banana(1-4)", "20251102"), ("Rotten banana(7-13)", "20251201")):
        (d / stage).mkdir(parents=True)
        for i in range(4):
            _pic(30 + i).save(d / stage / f"IMG_{day}_1200{i}0000.jpg", quality=95 if day == "20251102" else 80)     # 10 s apart: one session per stage
    dirs = config.data_dirs(tmp_path / "data")
    led = Ledger(dirs["staged"] / "l.sqlite")
    rep = datasets.ingest(d, "s", "agrifreshnet", dirs["staged"], led, specimen_groups=True)
    led.close()
    sg = rep["specimen_grouping"]
    assert sg["classes"]["banana"]["components"] == 4 and sg["union_specimen_and_session"]["largest_frac"] == 1.0
    assert sg["unit"].startswith("timestamped -> capture session") and sg["final_units"] == 2
    assert {f.name.split(".rf.")[0][:5] for f in (dirs["staged"] / "s").rglob("*.jpg")} == {"sess_"}
