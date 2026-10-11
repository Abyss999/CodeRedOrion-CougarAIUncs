"""Independent QA (food-main-mac) for PR #73 / ML-63: Colab cell 1 unrar-cffi build fix.

Checks the author's tests do not cover:
  1. ML-61 holds in cell 1 (every install through pip(), check=True, no !pip / %pip in ANY cell).
  2. The helper source, extracted from the notebook and run in a SUBPROCESS, surfaces pip's error AND still dies non-zero
     (real failing pip via --no-index, and a stub interpreter; no network).
  3. Every pip() argument in cell 1 is listed with its pin; build tools must be exact `==`.
  4. A real RAR5 archive (hand-built, stored method, valid CRCs: no `rar` binary or download needed) goes through the real
     unrar-cffi via pipeline.ingestion.fetch.unrar_bytes. Skipped where unrar-cffi is not installed (use venv-pipeline).

  .venv-ml/bin/python -m pytest ml/eval/tests/qa_pr73_unrar_independent.py -q      (4 skips there: no unrar-cffi)
  <venv-pipeline>/bin/python -m pytest ml/eval/tests/qa_pr73_unrar_independent.py -q
"""
import ast
import importlib.util
import json
import os
import re
import stat
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
NB = REPO / "ml" / "yolo" / "train_colab.ipynb"
BUILD_TOOLS = ("setuptools", "wheel", "cffi", "setuptools_scm", "pytest-runner", "unrar-cffi")


def code_cells():
    return ["".join(c["source"]) for c in json.loads(NB.read_text())["cells"] if c["cell_type"] == "code"]


def cell1():
    return code_cells()[0]


def helper_src():
    m = re.search(r"^def pip\(\*args\):.*?\n(?:[ \t]+.*\n)+", cell1(), re.M)
    assert m, "cell 1 has no pip() helper"
    return m.group(0)


def pip_calls():
    """[(lineno, [str args])] for every top-level/nested pip(...) call in cell 1 (AST, so comments are ignored)."""
    out = []
    src = "\n".join(l for l in cell1().splitlines() if not l.lstrip().startswith(("%", "!")))
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "pip":
            out.append((n.lineno, [a.value for a in n.args if isinstance(a, ast.Constant)]))
    return out


# ------------------------------------------------------------------------------------------ 1. ML-61 still holds
def test_no_bang_or_percent_pip_in_any_cell():
    bad = [(i, ln.strip()) for i, s in enumerate(code_cells()) for ln in s.splitlines()
           if re.match(r"\s*[!%]\s*(pip|python\s+-m\s+pip)\b", ln)]
    assert bad == []


def test_no_other_install_route_in_any_cell():
    """No subprocess/os.system install that bypasses the checked helper."""
    for i, s in enumerate(code_cells()):
        for ln in s.splitlines():
            t = ln.split("#", 1)[0]
            if "pip" in t and re.search(r"\binstall\b", t):
                assert i == 0 and ("def pip" in t or t.lstrip().startswith("subprocess.run([sys.executable")), (i, ln)
            assert "os.system" not in t and "get_ipython" not in t, (i, ln)


def test_helper_is_the_only_pip_runner_and_checks():
    runs = re.findall(r"subprocess\.run\(\[sys\.executable, \"-m\", \"pip\"[^\n]*", cell1())
    assert len(runs) == 1 and "check=True" in runs[0]
    assert "except subprocess.CalledProcessError" in helper_src() and re.search(r"^\s+raise\s*$", helper_src(), re.M)


def test_every_install_in_cell1_goes_through_pip_helper():
    calls = pip_calls()
    assert len(calls) == 5, calls   # -r reqs, setuptools (conditional), build tools, unrar, pipeline reqs
    assert not [l for l in cell1().splitlines() if l.startswith("!")  and "pip" in l]


# ----------------------------------------------------------------- 2. error shown AND still fails (subprocess, no network)
def _run_helper(prelude, call, tmp_path):
    prog = prelude + "\n" + helper_src() + "\nimport subprocess, sys\n" + call + "\nprint('CONTINUED-AFTER-PIP')\n"
    # the helper needs subprocess and sys in scope, as cell 1 has them
    prog = "import subprocess, sys\n" + prog
    return subprocess.run([sys.executable, "-I", "-c", prog], capture_output=True, text=True, timeout=120, cwd=tmp_path)


def test_real_pip_failure_shows_error_and_exits_nonzero(tmp_path):
    r = _run_helper("", 'pip("--no-index", "qa-pr73-nonexistent-pkg==0.0.0")', tmp_path)
    assert r.returncode != 0
    assert "CONTINUED-AFTER-PIP" not in r.stdout
    assert "CalledProcessError" in r.stderr                                   # traceback: the cell aborts
    assert "No matching distribution" in r.stdout or "No matching distribution" in r.stderr   # pip's own message is visible
    assert "qa-pr73-nonexistent-pkg" in r.stdout + r.stderr


def test_stub_interpreter_stderr_is_surfaced_and_step_raises(tmp_path):
    stub = tmp_path / "fakepython"
    stub.write_text("#!/bin/sh\necho 'STUB-STDERR: ModuleNotFoundError: No module named vcs_versioning' >&2\n"
                    "echo 'STUB-STDOUT-line' \nexit 7\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    r = _run_helper(f"import sys\nsys.executable = {str(stub)!r}", 'pip("unrar-cffi==0.2.2")', tmp_path)
    assert r.returncode == 1                      # uncaught exception -> interpreter exit 1
    assert "STUB-STDERR: ModuleNotFoundError" in r.stdout          # surfaced (printed to the cell's stdout)
    assert "STUB-STDOUT-line" in r.stdout
    assert "returned non-zero exit status 7" in r.stderr           # raised with pip's rc
    assert "CONTINUED-AFTER-PIP" not in r.stdout


def test_stub_success_is_silent_and_continues(tmp_path):
    stub = tmp_path / "okpython"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    r = _run_helper(f"import sys\nsys.executable = {str(stub)!r}", 'pip("x==1")', tmp_path)
    assert r.returncode == 0 and "CONTINUED-AFTER-PIP" in r.stdout


def test_stderr_tail_is_capped_but_the_end_survives(tmp_path):
    """pip's real error is at the END of a long log: the [-4000:] tail must keep it."""
    stub = tmp_path / "noisy"
    stub.write_text("#!/bin/sh\npython3 -c \"import sys; sys.stderr.write('x'*50000 + 'THE-REAL-ERROR')\"\nexit 1\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    r = _run_helper(f"import sys\nsys.executable = {str(stub)!r}", 'pip("y==1")', tmp_path)
    assert r.returncode == 1 and "THE-REAL-ERROR" in r.stdout and len(r.stdout) < 9000


# ---------------------------------------------------------------------------------------------------- 3. pinning
EXACT = re.compile(r"^[A-Za-z0-9_.\-]+==\d+(\.\d+)*$")


def test_build_tools_are_exact_pins():
    seen = {}
    for _, args in pip_calls():
        for a in args:
            if a.startswith("-") or a.endswith(".txt"):
                continue
            name = re.split(r"[=<>~!]", a)[0]
            if name in BUILD_TOOLS:
                assert EXACT.match(a), f"build tool not exactly pinned: {a}"
                seen[name] = a
    assert seen == {"setuptools": "setuptools==80.9.0", "cffi": "cffi==2.1.1", "setuptools_scm": "setuptools_scm==8.1.0",
                    "pytest-runner": "pytest-runner==6.0.1", "wheel": "wheel==0.45.1", "unrar-cffi": "unrar-cffi==0.2.2"}


def test_pip_itself_is_not_installed_or_upgraded():
    assert not any(a.split("==")[0] == "pip" for _, args in pip_calls() for a in args)   # uses the runtime's pip, unpinned


def test_unpinned_installs_are_the_known_preexisting_ones():
    """Documents (does not bless) what is NOT an exact pin: roboflow, imagehash and the >= ranges of the -r files."""
    loose = sorted(a for _, args in pip_calls() for a in args
                   if not a.startswith("-") and not a.endswith(".txt") and not EXACT.match(a))
    assert loose == ["imagehash", "roboflow"]
    ranges = []
    for f in ("ml/yolo/requirements.txt", "pipeline/requirements.txt"):
        ranges += [l.strip() for l in (REPO / f).read_text().splitlines()
                   if l.strip() and not l.startswith("#") and "==" not in l]
    assert "pyyaml>=6.0" in ranges and "pytest>=8.0" in ranges


def test_order_build_tools_before_unrar_and_isolation_off():
    flat = [a for _, args in pip_calls() for a in args]
    assert flat.index("--no-build-isolation") == flat.index("unrar-cffi==0.2.2") - 1
    assert flat.index("wheel==0.45.1") < flat.index("--no-build-isolation")


# ------------------------------------------------------------------------- 4. real RAR5 through real unrar-cffi
def _vint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _block(htype, hflags, body, data_size=None):
    rest = _vint(htype) + _vint(hflags | (2 if data_size is not None else 0))
    if data_size is not None:
        rest += _vint(data_size)
    rest += body
    sized = _vint(len(rest)) + rest
    return struct.pack("<I", zlib.crc32(sized)) + sized


def build_rar5(name: str, payload: bytes) -> bytes:
    """Minimal valid RAR5: signature, main header, one stored file (CRC32 present), end-of-archive."""
    sig = b"Rar!\x1a\x07\x01\x00"
    main = _block(1, 0, _vint(0))
    nm = name.encode()
    body = (_vint(0x4) + _vint(len(payload)) + _vint(0x20) + struct.pack("<I", zlib.crc32(payload))
            + _vint(0) + _vint(1) + _vint(len(nm)) + nm)       # filefl=CRC32, size, attr, crc, comp=store, os=unix, name
    fhdr = _block(2, 0, body, data_size=len(payload))
    return sig + main + fhdr + payload + _block(5, 0, _vint(0))


needs_unrar = pytest.mark.skipif(importlib.util.find_spec("unrar") is None, reason="unrar-cffi not installed (use venv-pipeline)")


@pytest.fixture
def unrar_bytes():
    sys.path.insert(0, str(REPO))
    try:
        from pipeline.ingestion.fetch import unrar_bytes as f
        return f
    finally:
        sys.path.remove(str(REPO))


@needs_unrar
def test_real_rar5_roundtrip_through_unrar_cffi(unrar_bytes):
    payload = bytes(range(256)) * 40 + b"qa-pr73 real RAR5"
    arc = build_rar5("meat/fresh_1.jpg", payload)
    assert arc[:8] == b"Rar!\x1a\x07\x01\x00"
    assert unrar_bytes(arc) == payload


@needs_unrar
def test_real_rar5_with_rarfile_api_reports_crc_and_name():
    from unrar.cffi import rarfile
    payload = b"hello rar5" * 100
    p = Path(os.environ.get("TMPDIR", "/tmp")) / "qa_pr73_hello.rar"
    p.write_bytes(build_rar5("a.txt", payload))
    try:
        rf = rarfile.RarFile(str(p))
        info = rf.infolist()[0]
        assert rf.namelist() == ["a.txt"] and info.CRC == zlib.crc32(payload) and info.file_size == len(payload)
    finally:
        p.unlink()


@needs_unrar
def test_real_rar5_corrupt_data_is_rejected_by_crc(unrar_bytes):
    payload = b"A" * 500
    arc = bytearray(build_rar5("a.bin", payload))
    i = arc.index(payload) + 10
    arc[i] ^= 0xFF
    with pytest.raises(Exception) as e:
        unrar_bytes(bytes(arc))
    assert "BadRarFile" in type(e.value).__name__ or "CRC" in str(e.value).upper() or "bad" in str(e.value).lower()


@needs_unrar
def test_import_matches_what_cell1_installs():
    from unrar.cffi import rarfile      # the import fetch.py does after the notebook's install
    assert hasattr(rarfile, "RarFile")
