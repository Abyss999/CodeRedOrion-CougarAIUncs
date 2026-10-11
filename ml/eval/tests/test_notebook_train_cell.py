"""ML QA regression (2026-10-11): train_colab.ipynb cells 4 (leakage print loop, ML-58) and 5 (training, ML-57).

ML-57: cell 5 ran `!python train.py ...`, so a crashed training run was ignored and cell 6 could pass on (or download)
an export left in RUN_DIR/export by an earlier run with the same RUN_ID. The fix drops RUN_DIR/export, then runs
train.py through subprocess.run([...], check=True). These tests execute the real cell 5 source against a stub
train.py in a temp dir (never the real one) and pin the exact argument list of the old command.

ML-58: cell 4 prints `phash_near_dup` for every source in leakage.json, but leakage_check.py omits the pHash keys
for a source with 0 held-out originals (meatscan is train-only), so the cell raised KeyError before training.
"""
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
NB = REPO / "ml" / "yolo" / "train_colab.ipynb"

STUB = """import json, os, sys
open(os.environ["ARGV_LOG"], "w").write(json.dumps(sys.argv[1:]))
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
"""


def cell(prefix):
    srcs = ["".join(c["source"]) for c in json.loads(NB.read_text())["cells"] if c["cell_type"] == "code"]
    hits = [s for s in srcs if s.lstrip().startswith(prefix)]
    assert len(hits) == 1, f"expected one code cell starting with {prefix!r}, got {len(hits)}"
    return hits[0]


def expected(data, ep, cls_ep, thr, run_dir):
    # the old `!python train.py ...` line, token by token
    return ["--data", data, "--epochs", str(ep), "--cls-epochs", str(cls_ep), "--device", "auto", "--weights", "last",
            "--resume", "--semi-fresh-threshold", str(thr), "--project", run_dir]


def run_cell5(tmp_path, monkeypatch, dry, exit_code=0, fast=False):
    work = tmp_path / "yolo"
    work.mkdir()
    (work / "train.py").write_text(STUB)
    run_dir = tmp_path / "run"
    (run_dir / "export").mkdir(parents=True)
    (run_dir / "export" / "predictions.jsonl").write_text('{"stale": true}\n')
    for st in ("det", "cls"):
        (run_dir / st / "weights").mkdir(parents=True)
        (run_dir / st / "weights" / "last.pt").write_text("ckpt")
    log = tmp_path / "argv.json"
    monkeypatch.setenv("ARGV_LOG", str(log))
    monkeypatch.setenv("STUB_EXIT", str(exit_code))
    monkeypatch.chdir(work)                                  # cell 1: %cd /content/repo/ml/yolo
    subset_calls = []
    monkeypatch.setitem(sys.modules, "make_subset",
                        types.SimpleNamespace(make_subset=lambda *a, **k: subset_calls.append((a, k)) or "subset"))
    monkeypatch.setitem(sys.modules, "cap_detector", types.SimpleNamespace(cap_detector=lambda *a, **k: {
        "train_images": 1, "train_images_full": 2, "boxes_by_freshness": {}}))
    import shutil
    ns = {"os": os, "shutil": shutil, "subprocess": subprocess, "sys": sys, "RUN_DIR": str(run_dir), "DRY_RUN": dry,
          "FAST": fast}   # FAST=False: the full profile keeps the old command exactly (FAST=True: qa_fast_profile.py)
    err = None
    try:
        exec(compile(cell("# 5."), "cell5", "exec"), ns)
    except subprocess.CalledProcessError as e:
        err = e
    argv = json.loads(log.read_text()) if log.exists() else None
    return run_dir, argv, err, ns, subset_calls


@pytest.mark.parametrize("dry", [True, False])
def test_cell5_args_match_old_command_and_keep_checkpoints(tmp_path, monkeypatch, dry):
    run_dir, argv, err, ns, subset_calls = run_cell5(tmp_path, monkeypatch, dry)
    assert err is None
    thr = ns["SEMI_FRESH_THRESHOLD"]
    want = expected("/content/fwr_data_dry", 1, 1, thr, str(run_dir)) if dry else expected("/content/fwr_data", 80, 30, thr, str(run_dir))
    assert argv == want
    assert bool(subset_calls) == dry
    assert not (run_dir / "export").exists(), "stale export survived: cell 6 could pass on it"
    assert (run_dir / "det/weights/last.pt").exists() and (run_dir / "cls/weights/last.pt").exists()


def test_cell5_crash_raises(tmp_path, monkeypatch):
    run_dir, argv, err, _, _ = run_cell5(tmp_path, monkeypatch, dry=False, exit_code=3)
    assert isinstance(err, subprocess.CalledProcessError) and err.returncode == 3
    assert not (run_dir / "export").exists()


def test_no_shell_python_left_in_cell5():
    assert not [ln for ln in cell("# 5.").splitlines() if ln.lstrip().startswith("!")]


def leakage_loop():
    src = cell("# 4.")
    a = src.index('lk = json.load(open("/content/leakage.json"))["per_source"]')
    b = src.index("# ML-23/24 gate")
    return src[a:b]


def test_ml58_cell4_leakage_loop_handles_train_only_source(tmp_path):
    """A source with 0 held-out originals (meatscan) has no pHash keys in leakage.json; the loop must not crash."""
    lk = {"per_source": {
        "agrifreshnet": {"heldout_originals": 754, "within_60s": 0, "within_300s": 0, "phash_near_dup": 2,
                         "phash_near_dup_pct": 0.27, "criterion": {"timestamp_300s_zero": True, "phash_le_1pct": True}},
        "meatscan": {"heldout_originals": 0, "within_60s": 0, "within_300s": 0,
                     "criterion": {"timestamp_300s_zero": True, "phash_le_1pct": True}}}}
    p = tmp_path / "leakage.json"
    p.write_text(json.dumps(lk))
    code = leakage_loop().replace("/content/leakage.json", str(p))
    exec(compile(code, "cell4_leakage_loop", "exec"), {"json": json})
