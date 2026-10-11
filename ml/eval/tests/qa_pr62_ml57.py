"""Independent QA (food-main-mac) for PR #62, ML-57: notebook cell 5 must stop on a crash of the REAL train.py.

The author's test_notebook_train_cell.py drives cell 5 with a stub train.py. This one runs the real
ml/yolo/train.py, made to crash before any training: the interpreter used has no `ultralytics`, so train.py dies on
`from ultralytics import YOLO` (after argparse accepted the exact cell-5 argument list). No model, no data, no GPU.
Also scans every code cell for a shell-bang call of train.py / prepare_dataset.py / pipeline whose exit code would be
swallowed. Run in .venv-ml (no ultralytics there):

  .venv-ml/bin/python -m pytest ml/eval/tests/qa_pr62_ml57.py -q
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
NB = REPO / "ml" / "yolo" / "train_colab.ipynb"


def code_cells():
    return ["".join(c["source"]) for c in json.loads(NB.read_text())["cells"] if c["cell_type"] == "code"]


def cell5():
    hits = [s for s in code_cells() if s.lstrip().startswith("# 5.")]
    assert len(hits) == 1
    return hits[0]


@pytest.mark.skipif(importlib.util.find_spec("ultralytics") is not None,
                    reason="needs an interpreter WITHOUT ultralytics so the real train.py crashes before training")
@pytest.mark.parametrize("dry", [True, False])
def test_cell5_stops_when_the_real_train_py_crashes(tmp_path, monkeypatch, dry):
    run_dir = tmp_path / "run"
    (run_dir / "export").mkdir(parents=True)
    (run_dir / "export" / "detector.pt").write_text("stale")
    (run_dir / "det" / "weights").mkdir(parents=True)
    (run_dir / "det" / "weights" / "last.pt").write_text("ckpt")
    monkeypatch.chdir(REPO / "ml" / "yolo")                     # cell 1: %cd /content/repo/ml/yolo -> the real train.py
    monkeypatch.setitem(sys.modules, "make_subset", types.SimpleNamespace(make_subset=lambda *a, **k: "subset"))
    ns = {"os": os, "shutil": shutil, "subprocess": subprocess, "sys": sys, "RUN_DIR": str(run_dir), "DRY_RUN": dry}
    with pytest.raises(subprocess.CalledProcessError) as e:
        exec(compile(cell5(), "cell5", "exec"), ns)
    assert e.value.returncode == 1          # ImportError in train.py (argparse errors exit 2)
    assert e.value.cmd[1] == "train.py"
    assert not (run_dir / "export").exists(), "stale export kept: cell 6 could pass it on"
    assert (run_dir / "det" / "weights" / "last.pt").exists(), "a checkpoint was deleted"


def test_argparse_accepts_the_exact_cell5_arguments():
    """The crash above must not be an argparse error: parse the cell-5 argv with train.py's own parser."""
    src = (REPO / "ml" / "yolo" / "train.py").read_text()
    for flag in ("--data", "--epochs", "--cls-epochs", "--device", "--weights", "--resume", "--semi-fresh-threshold", "--project"):
        assert f'"{flag}"' in src, flag
        assert f'"{flag}"' in cell5(), flag


def test_no_shell_bang_runs_a_pipeline_step():
    """`!python ...` ignores the exit code. No such call may run train.py, prepare_dataset.py, the pipeline or a gate."""
    bad = []
    for i, s in enumerate(code_cells()):
        for ln in s.splitlines():
            t = ln.split("#", 1)[0].strip()                 # comments may name the pipeline (cell 1 pip line)
            if t.startswith("!") and re.search(r"train\.py|prepare_dataset|-m pipeline|leakage_check|stratification_check|parent_sibling", t):
                bad.append((i, t))
    assert bad == []


# ------------------------------------------------------------------------------ ML-61: cell 1 installs (fixed)
def test_ml61_no_bang_pip_in_any_cell():
    bad = [(i, ln.strip()) for i, s in enumerate(code_cells()) for ln in s.splitlines()
           if re.match(r"\s*[!%]pip\b", ln)]
    assert bad == []


def _pip_helper_source():
    c1 = code_cells()[0]
    m = re.search(r"^def pip\(\*args\):.*?\n(?:[ \t]+.*\n)+", c1, re.M)
    assert m, "cell 1 has no pip() helper"
    return c1, m.group(0)


def test_ml61_installs_go_through_check_true():
    c1, helper = _pip_helper_source()
    assert "check=True" in helper and '"-m", "pip", "install"' in helper and "sys.executable" in helper
    calls = re.findall(r"^pip\((.*)\)", c1, re.M)
    joined = " ".join(calls)
    for req in ('"requirements.txt"', '"roboflow"', '"imagehash"', '"unrar-cffi==0.2.2"', "pipeline/requirements.txt"):
        assert req in joined, req


def test_ml61_failed_install_raises(monkeypatch):
    """Execute the real helper with a recorder in place of subprocess.run: argv and check=True are passed through."""
    _, helper = _pip_helper_source()
    seen = []

    def fake_run(argv, check=False, **kw):
        seen.append((argv, check))
        raise subprocess.CalledProcessError(1, argv)
    ns = {"subprocess": types.SimpleNamespace(run=fake_run, CalledProcessError=subprocess.CalledProcessError), "sys": sys}
    exec(helper, ns)
    with pytest.raises(subprocess.CalledProcessError):
        ns["pip"]("unrar-cffi==0.2.2")
    assert seen == [([sys.executable, "-m", "pip", "install", "-q", "unrar-cffi==0.2.2"], True)]
