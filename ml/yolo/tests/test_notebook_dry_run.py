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
    assert '"--semi-fresh-threshold", str(SEMI_FRESH_THRESHOLD)' in code
    assert "DRY RUN OK" in code and 'run_train("/content/fwr_data_dry", 1, 1)' in code and 'run_train("/content/fwr_data", 80, 30)' in code
    # ML-57: training runs with check=True (never `!python train.py`), and a stale RUN_DIR/export is dropped before it
    assert "!python train.py" not in code and 'shutil.rmtree(f"{RUN_DIR}/export", ignore_errors=True)' in code
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


def _code():
    return "\n".join(t for t, k in cells() if k == "code")


def test_mendeley_requests_send_a_user_agent_and_verify_sha256():
    code = _code()
    assert code.count("headers=UA") == 2 and "Mozilla/5.0" in code                  # API call AND file download (ML-42)
    assert "urlretrieve(url" not in code
    assert '6607a48bf2817f9dfc8d4a1c32ce663c1d8308b4b1251e9bf65f074fcac53f11' in code   # ML-43: never silently skipped
    assert 'h.hexdigest() == AGRI_SHA256' in code and "if want:" not in code
    assert 'f["filename"] == "Processed Data.zip"' in code and "meta[\"files\"][:1]" not in code


def test_gate_message_matches_the_ml35_ruling():
    code = _code()
    assert "pending ML-35" not in code and "identity pHash <= 6 and <= 1% per source" in code and "ML-40" in code
    assert "pending ML-35" not in (Path(__file__).resolve().parents[3] / "docs" / "ML.md").read_text()


def test_run_id_ending_in_dry_is_rejected():
    code = _code()
    assert 'assert not RUN_ID.endswith("_dry")' in code
    # behaviour of the guard, extracted from the cell
    guard = next(l for l in code.splitlines() if l.startswith('assert not RUN_ID.endswith("_dry")'))
    for rid, ok in (("fwr_20261010", True), ("fwr_x_dry", False), ("dry", True)):
        try:
            exec(guard, {"RUN_ID": rid}); passed = True
        except AssertionError:
            passed = False
        assert passed is ok, rid
