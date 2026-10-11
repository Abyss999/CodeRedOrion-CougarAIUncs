"""ML QA regression (2026-10-11): train_colab.ipynb cell 4 must build the dataset fresh and stop on a failed prepare.

A Colab run once used `!python prepare_dataset.py ... --out /content/fwr_data` on a /content left over from an earlier
attempt: prepare_dataset.py refused the non-empty --out and exited non-zero, `!` ignored it, and the gates ran on the
stale dataset. These tests pin the fix: rmtree(DATA) then subprocess.run([...], check=True), and no `!python` in the
download/prepare/gate cells (3 and 4) whose failure would be swallowed.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
YOLO = REPO / "ml" / "yolo"
NB = YOLO / "train_colab.ipynb"


def code_cells():
    nb = json.loads(NB.read_text())
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def cell(prefix):
    hits = [c for c in code_cells() if c.lstrip().startswith(prefix)]
    assert len(hits) == 1, f"expected one code cell starting with {prefix!r}, got {len(hits)}"
    return hits[0]


def else_branch(src):
    """The body of the top-level `else:` that pairs with `if DATA_ON_DRIVE:` in cell 4, dedented."""
    lines = src.splitlines()
    i = lines.index("else:")
    body = []
    for ln in lines[i + 1:]:
        if ln and not ln.startswith(" "):
            break
        body.append(ln[4:])
    return "\n".join(body)


def test_no_shell_python_before_or_in_the_gates():
    for prefix in ("# 3.", "# 4."):
        bad = [ln for ln in cell(prefix).splitlines() if re.match(r"\s*!\s*python", ln)]
        assert not bad, f"cell {prefix} runs python through `!` (failure ignored): {bad}"


def test_cell4_rebuilds_fresh_and_checks():
    body = else_branch(cell("# 4."))
    assert "!python" not in body
    code = [ln for ln in body.splitlines() if not ln.lstrip().startswith("#")]
    runs = [ln for ln in code if "prepare_dataset.py" in ln]
    assert len(runs) == 1, runs
    run = runs[0]
    assert run.lstrip().startswith("subprocess.run([sys.executable,") and "check=True" in run and "DATA]" in run
    assert body.index("shutil.rmtree(DATA") < body.index(run)
    # the Drive-restore branch still extracts the tar with check=True and verifies the stamp
    head = cell("# 4.").split("\nelse:")[0]
    assert 'subprocess.run(["tar", "-xf", DRIVE_TAR, "-C", "/content"], check=True)' in head and "_st[\"counts\"]" in head


def _exec_else(tmp_path, data, sources):
    body = else_branch(cell("# 4.")).replace("/content/sources.colab.json", str(sources))
    ns = {"shutil": shutil, "subprocess": subprocess, "sys": sys, "DATA": str(data)}
    import os
    cwd = os.getcwd()
    os.chdir(YOLO)                     # cell 1 does %cd /content/repo/ml/yolo
    try:
        exec(compile(body, "cell4_else", "exec"), ns)
    finally:
        os.chdir(cwd)


def test_failed_prepare_raises_and_stale_data_is_gone(tmp_path):
    data = tmp_path / "fwr_data"
    data.mkdir()
    (data / "dataset_report.json").write_text('{"stale": true}')
    with pytest.raises(subprocess.CalledProcessError):
        _exec_else(tmp_path, data, tmp_path / "missing_sources.json")
    assert not (data / "dataset_report.json").exists(), "the stale report survived: gates could read it"


def test_old_shell_form_was_the_bug(tmp_path):
    """prepare_dataset.py does refuse a non-empty --out with a non-zero exit (what `!` swallowed)."""
    data = tmp_path / "fwr_data"
    data.mkdir()
    (data / "x").write_text("stale")
    p = subprocess.run([sys.executable, "prepare_dataset.py", "--sources", str(tmp_path / "s.json"), "--out", str(data)],
                       cwd=YOLO, capture_output=True, text=True)
    assert p.returncode != 0 and "refusing to overwrite" in p.stderr
