"""Independent QA for ML-63: Colab cell 1 failed at pip("unrar-cffi==0.2.2") with metadata-generation-failed.

unrar-cffi 0.2.2 has no wheel past cp39, so it builds from sdist. On pip's legacy setup.py path its setup_requires are
fetched by setuptools as eggs, which picks setuptools_scm 10.x without vcs_versioning -> ModuleNotFoundError.
Fix: install the build tools pinned with pip first, then build with --no-build-isolation; the pip() helper prints
pip's own output on failure (Colab hides a subprocess's stderr) and re-raises. Offline: the real cell-1 source is
executed against a recorder in place of subprocess.run. Live install matrix: docs/qa/ml.md (2026-10-11).

  .venv-ml/bin/python -m pytest ml/eval/tests/qa_ml63_unrar_build.py -q
"""
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
NB = REPO / "ml" / "yolo" / "train_colab.ipynb"
BUILD_TOOLS = ("cffi==2.1.1", "setuptools_scm==8.1.0", "pytest-runner==6.0.1", "wheel==0.45.1")


def cell1():
    return "".join([c for c in json.loads(NB.read_text())["cells"] if c["cell_type"] == "code"][0]["source"])


def helper_src():
    m = re.search(r"^def pip\(\*args\):.*?\n(?:[ \t]+.*\n)+", cell1(), re.M)
    assert m, "cell 1 has no pip() helper"
    return m.group(0)


def unrar_block():
    """Cell-1 lines between the requirements.txt install and the pipeline requirements install."""
    lines = cell1().splitlines()
    s = next(i for i, l in enumerate(lines) if l.startswith('pip("-r", "requirements.txt"'))
    e = next(i for i, l in enumerate(lines) if l.startswith("pip(") and "pipeline/requirements.txt" in l)
    return "\n".join(lines[s + 1:e])


def run_block(setuptools_present: bool, fail_on=None):
    """Exec helper + unrar block with a recorder; returns the recorded pip argv tails."""
    seen = []

    def fake_run(argv, check=False, **kw):
        seen.append((argv, check, kw))
        if fail_on and fail_on in argv:
            raise subprocess.CalledProcessError(1, argv, output="OUT-TAIL", stderr="ERR vcs_versioning")
        return subprocess.CompletedProcess(argv, 0, "", "")
    fake_util = types.SimpleNamespace(find_spec=lambda n: object() if setuptools_present else None)
    ns = {"subprocess": types.SimpleNamespace(run=fake_run, CalledProcessError=subprocess.CalledProcessError,
                                              CompletedProcess=subprocess.CompletedProcess), "sys": sys}
    src = helper_src() + unrar_block().replace("import importlib.util", "")
    ns["importlib"] = types.SimpleNamespace(util=fake_util)
    exec(src, ns)
    return seen, ns


def _args(seen):
    for argv, check, kw in seen:
        assert argv[:5] == [sys.executable, "-m", "pip", "install", "-q"]
    return [argv[5:] for argv, _, _ in seen]


def test_ml63_build_tools_pinned_then_no_build_isolation():
    seen, _ = run_block(setuptools_present=True)
    assert _args(seen) == [list(BUILD_TOOLS), ["--no-build-isolation", "unrar-cffi==0.2.2"]]


def test_ml63_setuptools_installed_pinned_only_when_missing():
    seen, _ = run_block(setuptools_present=False)
    assert _args(seen) == [["setuptools==80.9.0"], list(BUILD_TOOLS), ["--no-build-isolation", "unrar-cffi==0.2.2"]]


def test_ml63_no_isolated_or_bare_unrar_install_left():
    calls = re.findall(r"^pip\((.*)\)", cell1(), re.M)
    unrar = [c for c in calls if "unrar-cffi" in c]
    assert unrar == ['"--no-build-isolation", "unrar-cffi==0.2.2"']
    assert all(re.search(r"==\d", a) for c in calls for a in re.findall(r'"([^"]+)"', c)
               if not a.startswith("-") and "requirements.txt" not in a and a not in ("roboflow", "imagehash"))


def test_ml63_helper_keeps_check_true_and_captures(capsys):
    seen, ns = run_block(setuptools_present=True)
    for _, check, kw in seen:
        assert check is True and kw.get("capture_output") is True and kw.get("text") is True


def test_ml63_failure_prints_pip_output_and_reraises(capsys):
    with pytest.raises(subprocess.CalledProcessError) as ei:
        run_block(setuptools_present=True, fail_on="unrar-cffi==0.2.2")
    out = capsys.readouterr().out
    assert "OUT-TAIL" in out and "ERR vcs_versioning" in out
    assert ei.value.returncode == 1


def test_ml63_failure_with_none_streams_still_raises(capsys):
    exec_ns = {"sys": sys}

    def fake_run(argv, check=False, **kw):
        raise subprocess.CalledProcessError(2, argv)   # stdout/stderr None
    exec_ns["subprocess"] = types.SimpleNamespace(run=fake_run, CalledProcessError=subprocess.CalledProcessError)
    exec(helper_src(), exec_ns)
    with pytest.raises(subprocess.CalledProcessError) as ei:
        exec_ns["pip"]("x==1")
    assert ei.value.returncode == 2


def test_ml63_pipeline_doc_matches_notebook_pins():
    doc = (REPO / "docs" / "PIPELINE.md").read_text()
    line = next(l for l in doc.splitlines() if "--no-build-isolation" in l)
    for pin in BUILD_TOOLS + ("unrar-cffi==0.2.2",):
        assert pin in line, pin
