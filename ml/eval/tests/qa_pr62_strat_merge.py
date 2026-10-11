"""Independent QA (food-main-mac) for PR #62: the pHash session merge that `stratification_check.py` applies by
default (`--no-phash-merge` turns it off), and the span rules of `verify()`. Written against the old code (ML-59 and
ML-60 were strict xfails there); now pinned to the fixed behaviour of a2d88f5:
- the span rule runs on UNMERGED sessions with an explicit per-session timestamp flag (ML-59);
- the merge feeds only the measurability count, is capped like prepare_dataset (dataset_report
  grouping.near_duplicates.max_unit_images, default 600), and a cross-split pHash pair inside a merged unit is a
  FAILURE (ML-60; that one rule is pending an owner ruling, see CROSS_SPLIT_PAIR_IS_FAILURE).

Synthetic prepared datasets under tmp_path (real JPEGs, so the merge's imagehash pHash runs). Needs `imagehash`
(skipped without it: `.venv-ml` lacks it, `mldata/.venv-train` has it). Not collected by the default pattern:

  mldata/.venv-train/bin/python -m pytest ml/eval/tests/qa_pr62_strat_merge.py -q
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("imagehash")
import leakage_check as L  # noqa: E402
import stratification_check as S  # noqa: E402

MS = 1_700_000_000_000  # epoch-ms base: names carry a 13-digit epoch, which leakage_check.stamp() reads


def _img(path: Path, seed: int, jitter: int = 0):
    """A distinct random-block picture per seed; jitter > 0 gives a pHash near-duplicate of the same seed."""
    rng = np.random.default_rng(seed)
    a = np.kron(rng.integers(0, 255, (8, 8, 3)), np.ones((16, 16, 1))).astype(np.int16)
    if jitter:
        a = np.clip(a + jitter, 0, 255)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a.astype(np.uint8)).save(path, "JPEG", quality=95)


def build(root: Path, files, decision="required_in_heldout", units=2, max_unit=None):
    """files: [(split, name, seed, jitter)] all one cell (apple/fresh), source vegqual. Writes a dataset that
    stratification_check reads: images, labels, freshness, class_names, dataset_report, manifest, gt."""
    for sp in L.SPLITS:
        for d in ("images", "labels", "freshness"):
            (root / d / sp).mkdir(parents=True, exist_ok=True)
    count = {sp: 0 for sp in L.SPLITS}
    for sp, name, seed, jit in files:
        _img(root / "images" / sp / name, seed, jit)
        stem = Path(name).stem
        (root / "labels" / sp / f"{stem}.txt").write_text("0 0.5 0.5 0.9 0.9\n")
        (root / "freshness" / sp / f"{stem}.txt").write_text("0\n")
        count[sp] += 1
    (root / "class_names.json").write_text(json.dumps({"0": "apple"}))
    held = [n for sp, n, *_ in files if sp == "heldout"]
    with (root / "heldout_manifest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, ["image", "variant_of", "lighting", "lighting_method"])
        w.writeheader()
        for n in held:
            w.writerow({"image": n, "variant_of": "", "lighting": "normal", "lighting_method": "auto"})
    (root / "heldout_gt.jsonl").write_text("".join(json.dumps({"image": n}) + "\n" for n in held))
    rep = {"heldout_manifest_rows": len(held), "heldout_originals": len(held),
           "heldout_images_by_lighting_method": {"normal/auto": len(held)} if held else {},
           "splits": {sp: {"images": count[sp]} for sp in L.SPLITS},
           "source_by_split": {"vegqual": {f"{sp}/images": count[sp] for sp in L.SPLITS if count[sp]}},
           "stratification": {"min_session_images": 1,
                              "cell_decisions": {"apple/fresh": {"decision": decision, "units": {"units": units}}}}}
    if max_unit is not None:
        rep["grouping"] = {"near_duplicates": {"max_unit_images": max_unit}}
    (root / "dataset_report.json").write_text(json.dumps(rep))
    return root


def at(sec, tag="x"):
    return f"vegqual_{MS + int(sec * 1000)}_{tag}.jpg"


def run(root, merge):
    out = S.check(root, phash_merge=merge)
    return out, S.verify(root, out)


# Owner ruling pending: is a cross-split pHash pair inside a merged unit a strat FAILURE (a2d88f5) or info only
# (leakage_check already gates identity pHash <= 1% per source)? Flip this one constant if the ruling is "info".
CROSS_SPLIT_PAIR_IS_FAILURE = False

# ---------------------------------------------------------------------------------------------------- the merge
def test_merge_unites_two_capture_sessions_of_one_shot(tmp_path):
    """Two timestamp sessions 1 h apart that re-shoot the same specimen (pHash near-duplicates) are one independence
    unit with the merge, two without. This is the case the merge was added for (MeatScan beef, ML-52)."""
    root = build(tmp_path, [("train", at(0, "a"), 1, 0), ("train", at(3600, "b"), 1, 3),
                            ("heldout", at(90000, "c"), 2, 0)])
    out_m, _ = run(root, True)
    out_n, _ = run(root, False)
    assert out_n["cells"]["apple/fresh"]["sessions"] == 3
    assert out_m["cells"]["apple/fresh"]["sessions"] == 2


def test_merge_never_changes_split_membership_session_ids_or_leakage_gate(tmp_path):
    """The merge only feeds the unit count. Session ids and splits are untouched, and the cross-split near-duplicate
    is still seen by the independent leakage gate (identity pHash)."""
    root = build(tmp_path, [("train", "vegqual_a.jpg", 7, 0), ("heldout", "vegqual_b.jpg", 7, 2),
                            ("heldout", "vegqual_c.jpg", 8, 0)])
    out_m, _ = run(root, True)
    out_n, _ = run(root, False)
    key = lambda o: [(r["split"], r["name"], r["session"]) for r in o["_rows"]]
    assert key(out_m) == key(out_n)
    files = L.originals(root)
    tr = files["train"] + files["val"]
    hs = L.hash_images(tr + files["heldout"], None)
    near = [h for h in files["heldout"]
            if any(bin(hs[h.name][0] ^ hs[t.name][0]).count("1") <= L.PHASH_T for t in tr)]
    assert [p.name for p in near] == ["vegqual_b.jpg"]


def test_ml60_cross_split_phash_pair_in_merged_unit(tmp_path):
    """ML-60 (b), the ONE rule pending the owner: a train/held-out pHash twin inside a merged unit."""
    root = build(tmp_path, [("train", "vegqual_a.jpg", 7, 0), ("train", "vegqual_d.jpg", 9, 0),
                            ("heldout", "vegqual_b.jpg", 7, 2), ("heldout", "vegqual_c.jpg", 8, 0)])
    _, v_n = run(root, False)
    _, v_m = run(root, True)
    assert not v_n["failures"]                                    # unmerged: two separate stem groups, nothing spans
    assert v_m["info"]["stem_groups_spanning_splits"] == 0        # sessions are no longer relabelled by the merge
    assert v_m["info"]["phash_cross_split_pairs"] == 1
    pair_fails = [f for f in v_m["failures"] if "pHash near-duplicate pair" in f]
    if CROSS_SPLIT_PAIR_IS_FAILURE:
        assert len(pair_fails) == 1 and "vegqual_a.jpg" in pair_fails[0] and "vegqual_b.jpg" in pair_fails[0]
    else:                                                         # owner ruling 2026-10-11: warning only
        assert pair_fails == []
        ex = json.dumps(v_m["info"]["phash_cross_split_pair_examples"])
        assert "vegqual_a.jpg" in ex and "vegqual_b.jpg" in ex


# ------------------------------------------------------------------------------ ML-59: the span rule (fixed)
def test_timestamped_session_spanning_splits_is_a_failure_without_merge(tmp_path):
    root = build(tmp_path, [("train", at(0), 1, 0), ("train", at(60), 2, 0), ("heldout", at(120), 3, 0)])
    _, v = run(root, False)
    assert any("timestamped sessions span" in f for f in v["failures"]), v["failures"]
    assert v["info"]["timestamped_sessions_spanning_splits"] == 1


def _relabel_case(tmp_path):
    # one timestamped session (t0) split over train and held-out, plus an untimestamped held-out pHash twin of the
    # train frame: under the old code the union made the stem group the root and t0 lost its '/t' marker
    return build(tmp_path, [("train", at(0), 3, 0), ("train", at(9000, "y"), 5, 0), ("heldout", at(120), 4, 0),
                            ("heldout", "vegqual_untimed.jpg", 3, 2)])


def test_timestamped_session_spanning_splits_is_a_failure_with_merge(tmp_path):
    out, v = run(_relabel_case(tmp_path), True)
    assert any("timestamped sessions span" in f for f in v["failures"]), v["failures"]


def test_merge_does_not_relabel_a_timestamped_session(tmp_path):
    out, v = run(_relabel_case(tmp_path), True)
    ts_ids = {r["session"] for r in out["_rows"] if r["ts"] is not None}
    assert ts_ids == {"vegqual/t0", "vegqual/t1"}
    assert all(r["session_ts"] for r in out["_rows"] if r["ts"] is not None)
    assert v["info"]["stem_groups_spanning_splits"] == 0
    assert v["info"]["timestamped_sessions_spanning_splits"] == 1


def test_untimestamped_stem_group_span_stays_info(tmp_path):
    """A numbered/stem group spanning splits is info, not a failure (unchanged rule)."""
    root = build(tmp_path, [("train", "vegqual_IMG_5_jpg.rf.a.jpg", 1, 0), ("heldout", "vegqual_IMG_6_jpg.rf.b.jpg", 2, 0),
                            ("train", "vegqual_z.jpg", 4, 0)])
    _, v = run(root, False)
    assert v["info"]["stem_groups_spanning_splits"] == 1
    assert not any("span" in f for f in v["failures"])


# ------------------------------------------------------------------------------ ML-60 (c): the max_unit cap
def _chain(tmp_path, max_unit):
    # three re-shoots of one specimen, hours apart (3 timestamp sessions, one pHash component of 3 images)
    return build(tmp_path, [("train", at(0, "a"), 1, 0), ("train", at(7200, "b"), 1, 2), ("train", at(14400, "c"), 1, 4),
                            ("heldout", at(90000, "d"), 2, 0)], max_unit=max_unit)


@pytest.mark.parametrize("max_unit,units", [(3, 2), (2, 4)])
def test_merge_cap_is_read_from_dataset_report(tmp_path, max_unit, units):
    out, v = run(_chain(tmp_path, max_unit), True)
    assert out["phash_merge"]["max_unit_images"] == max_unit
    assert out["cells"]["apple/fresh"]["sessions"] == units      # component of 3 > cap 2: left unmerged
    assert out["phash_merge"]["oversized_components_not_merged"] == (1 if max_unit < 3 else 0)
    assert v["info"]["phash_max_unit_images"] == max_unit


def test_merge_cap_defaults_to_600(tmp_path):
    out, _ = run(_chain(tmp_path, None), True)
    assert out["phash_merge"]["max_unit_images"] == 600
    assert out["cells"]["apple/fresh"]["sessions"] == 2


def test_cross_split_pair_inside_an_oversized_component_is_not_a_strat_failure(tmp_path):
    """Documents the cap's consequence: pairs inside a component over the cap are left to leakage_check (<= 1%)."""
    root = build(tmp_path, [("train", "vegqual_a.jpg", 7, 0), ("train", "vegqual_e.jpg", 7, 1),
                            ("heldout", "vegqual_b.jpg", 7, 2), ("heldout", "vegqual_c.jpg", 8, 0)], max_unit=2)
    out, v = run(root, True)
    assert out["phash_merge"]["oversized_components_not_merged"] == 1
    assert v["info"]["phash_cross_split_pairs"] == 0
    assert not [f for f in v["failures"] if "pHash near-duplicate pair" in f]
