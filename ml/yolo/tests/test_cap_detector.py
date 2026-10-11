"""cap_detector.py: capped detector train set (FAST profile)."""
import json
from pathlib import Path

from PIL import Image


def _fixture(root):
    # food 0 "big": 30 images x 1 box (half fresh, half spoiled, two sources); food 1 "rare": 3 images; 2 multi-object images
    names = {"0": "big", "1": "rare"}
    for sp in ("train", "val", "heldout"):
        for sub in ("images", "labels", "freshness"):
            (root / sub / sp).mkdir(parents=True)
    def img(sp, stem, labels, fresh):
        Image.new("RGB", (8, 8)).save(root / "images" / sp / f"{stem}.jpg")
        (root / "labels" / sp / f"{stem}.txt").write_text("".join(f"{c} .5 .5 .1 .1\n" for c in labels))
        (root / "freshness" / sp / f"{stem}.txt").write_text("".join(f"{f}\n" for f in fresh))
    for i in range(30):
        img("train", f"{'srca' if i % 2 else 'srcb'}_b{i:02d}", [0], [1 if i < 15 else 0])
    for i in range(3):
        img("train", f"srca_r{i}", [1], [0])
    for i in range(2):
        img("train", f"srcb_m{i}", [0, 1], [0, 0])
    img("val", "srca_v0", [0], [0]); img("heldout", "srca_h0", [0], [0])
    (root / "cls" / "train" / "fresh").mkdir(parents=True)
    (root / "class_names.json").write_text(json.dumps(names))
    (root / "dataset_report.json").write_text(json.dumps({"source_by_split": {"srca": {}, "srcb": {}}}))
    (root / "data.yaml").write_text(f"path: {root}\ntrain: images/train\nval: images/val\ntest: images/heldout\nnames:\n  0: big\n  1: rare\n")
    (root / "heldout_gt.jsonl").write_text('{"image": "images/heldout/srca_h0.jpg"}\n')
    (root / "heldout_manifest.csv").write_text("image,lighting\nimages/heldout/srca_h0.jpg,normal\n")


def test_caps_big_food_keeps_rare_and_everything_else(tmp_path):
    from cap_detector import cap_detector
    _fixture(tmp_path / "d")
    r = cap_detector(tmp_path / "d", tmp_path / "o", cap=10)
    out = tmp_path / "o"
    kept = sorted(p.name for p in (out / "images" / "train").iterdir())
    assert all(f"srca_r{i}.jpg" in kept for i in range(3)) and all(f"srcb_m{i}.jpg" in kept for i in range(2))   # rare food: all
    assert r["boxes_by_food"]["big"] == "10/32" and r["boxes_by_food"]["rare"] == "5/5"
    assert r["boxes_by_freshness"]["spoiled"] >= 3 and r["boxes_by_freshness"]["fresh"] >= 3                    # both kept
    assert {p.name[:4] for p in (out / "images" / "train").iterdir() if p.name[5] == "b"} == {"srca", "srcb"}     # both sources
    for p in (out / "images" / "train").iterdir():
        assert (out / "labels" / "train" / f"{Path(p.name).stem}.txt").exists()
    assert (out / "images" / "val" / "srca_v0.jpg").exists() and (out / "images" / "heldout" / "srca_h0.jpg").exists()
    assert (out / "cls" / "train" / "fresh").is_dir() and (out / "heldout_gt.jsonl").read_text().count("\n") == 1
    assert f"path: {out.resolve()}" in (out / "data.yaml").read_text()


def test_deterministic_and_cap_above_total_keeps_all(tmp_path):
    from cap_detector import cap_detector
    _fixture(tmp_path / "d")
    a = cap_detector(tmp_path / "d", tmp_path / "o1", cap=10)
    b = cap_detector(tmp_path / "d", tmp_path / "o2", cap=10)
    assert a == b and sorted(p.name for p in (tmp_path / "o1/images/train").iterdir()) == sorted(p.name for p in (tmp_path / "o2/images/train").iterdir())
    assert cap_detector(tmp_path / "d", tmp_path / "o3", cap=1000)["train_images"] == 35
