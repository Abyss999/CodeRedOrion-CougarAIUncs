"""train_colab.ipynb: valid JSON, every code cell parses, dry-run wiring, make_subset determinism."""
import ast, json, re, sys
from pathlib import Path

import pytest
from PIL import Image

NB = Path(__file__).resolve().parents[1] / "train_colab.ipynb"


def cells():
    nb = json.loads(NB.read_text())
    return [("".join(c["source"]), c["cell_type"]) for c in nb["cells"]]


def test_every_code_cell_parses():
    for t, kind in cells():
        if kind == "code":
            ast.parse(re.sub(r"(?m)^(\s*)[!%].*$", r"\1pass", t))


def test_dry_run_wiring_and_safety_properties():
    code = "\n".join(t for t, k in cells() if k == "code")
    assert re.search(r"^DRY_RUN = True\s+#@param \{type:\"boolean\"\}", code, re.M)
    assert 'RUN_DIR = CACHE_DIR + ("_dry" if DRY_RUN else "")' in code
    assert "fwr_data.tar" in code and "{CACHE_DIR}/fwr_data.tar" in code       # dataset cache is shared, checkpoints are not
    assert code.count("check=True") >= 3 and "RUN_ID must start with a letter or digit" in code and "run_check(" in code
    assert "--specimen-groups" in code and "--exclude-source-augs" in code and "--max-per-cell" in code and "pipeline/requirements.txt" in code
    assert "--semi-fresh-threshold {SEMI_FRESH_THRESHOLD}" in code
    assert "DRY RUN OK" in code and "--epochs 1 --cls-epochs 1" in code
    assert "if DATA_ON_DRIVE" in code and "skipping all downloads" in code


def test_train_py_plumbs_semi_fresh_threshold(monkeypatch):
    import train
    src = (Path(train.__file__)).read_text()
    assert '"--semi-fresh-threshold", str(a.semi_fresh_threshold)' in src and "SEMI_FRESH_THRESHOLD" in src


def _fixture(root):
    for sp in ("train", "val", "heldout"):
        for sub in ("images", "labels", "freshness"):
            (root / sub / sp).mkdir(parents=True)
        for i in range(45):
            Image.new("RGB", (8, 8)).save(root / "images" / sp / f"im{i:03d}.jpg")
            (root / "labels" / sp / f"im{i:03d}.txt").write_text("0 .5 .5 .1 .1\n")
            (root / "freshness" / sp / f"im{i:03d}.txt").write_text("2\n")
    for sp in ("train", "val"):
        for c in ("fresh", "semi_fresh", "spoiled"):
            (root / "cls" / sp / c).mkdir(parents=True)
            for i in range(25):
                Image.new("RGB", (8, 8)).save(root / "cls" / sp / c / f"c{i:03d}.jpg")
    (root / "data.yaml").write_text(f"path: {root}\ntrain: images/train\nval: images/val\ntest: images/heldout\nnames:\n  0: x\n")
    rows = [{"image": f"images/heldout/im{i:03d}.jpg", "lighting": "normal", "labels": []} for i in range(45)]
    (root / "heldout_gt.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (root / "heldout_manifest.csv").write_text("image,lighting\n" + "".join(f"{r['image']},normal\n" for r in rows))


def test_make_subset_is_deterministic_and_keeps_every_class(tmp_path):
    from make_subset import make_subset
    _fixture(tmp_path / "d")
    a = make_subset(tmp_path / "d", tmp_path / "s1", 20)
    b = make_subset(tmp_path / "d", tmp_path / "s2", 20)
    assert a == b and a["train"] == 3 and a["cls/train/semi_fresh"] == 2 and a["cls/val/spoiled"] == 2
    assert sorted(p.name for p in (tmp_path / "s1" / "images" / "train").iterdir()) == sorted(p.name for p in (tmp_path / "s2" / "images" / "train").iterdir())
    assert sorted(p.name for p in (tmp_path / "s1" / "cls" / "train").iterdir()) == ["fresh", "semi_fresh", "spoiled"]
    assert len((tmp_path / "s1" / "heldout_gt.jsonl").read_text().splitlines()) == a["heldout"] == 3
    assert (tmp_path / "s1" / "labels" / "train" / "im000.txt").exists()
