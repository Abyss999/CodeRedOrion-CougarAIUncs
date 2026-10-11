import json
import subprocess
import sys

import pytest
from PIL import Image

from pipeline import cli
from .conftest import REPO, build_drop, make_jpeg, zip_dir


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "pipeline", *map(str, args)], cwd=REPO,
                          capture_output=True, text=True, timeout=120)


def test_help_lists_commands():
    r = run_cli("--help")
    assert r.returncode == 0
    for c in ("ingest-dataset", "prepare", "augment-lighting", "ingest-receipts", "preview-lighting", "run-all"):
        assert c in r.stdout


def test_ingest_requires_exactly_one_source(tmp_path):
    r = run_cli("--data-root", tmp_path, "ingest-dataset", "--name", "x")
    assert r.returncode != 0


def test_end_to_end_cli(tmp_path):
    drop = build_drop(tmp_path / "drop", per_class=20)
    z = zip_dir(drop, tmp_path / "d.zip")
    root = tmp_path / "data"
    r = run_cli("--data-root", root, "ingest-dataset", "--zip", z, "--name", "synth", "--adapter", "agrifreshnet")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["staged"] > 0
    r = run_cli("--data-root", root, "ingest-dataset", "--zip", z, "--name", "synth", "--adapter", "agrifreshnet")
    assert json.loads(r.stdout).get("staged", 0) == 0
    r = run_cli("--data-root", root, "prepare")
    assert r.returncode == 0, r.stderr
    r = run_cli("--data-root", root, "prepare")
    assert r.returncode != 0 and "--replace" in r.stderr
    r = run_cli("--data-root", root, "augment-lighting", "--per-image", "1", "--presets", "low,warm")
    assert r.returncode == 0, r.stderr
    assert (root / "augmented" / "augment_manifest.csv").exists()
    r = run_cli("--data-root", root, "augment-lighting", "--presets", "bogus", "--out", root / "a2")
    assert r.returncode != 0
    sheet = tmp_path / "sheet.jpg"
    r = run_cli("--data-root", root, "preview-lighting", "--image", next(drop.rglob("*.jpg")), "--out", sheet)
    assert r.returncode == 0 and Image.open(sheet).size[0] > 0


def test_run_all(tmp_path):
    z = zip_dir(build_drop(tmp_path / "drop", per_class=15), tmp_path / "d.zip")
    root = tmp_path / "data"
    r = run_cli("--data-root", root, "run-all", "--zip", z, "--name", "synth", "--adapter", "agrifreshnet",
                "--per-image", "1")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout[r.stdout.index('{\n  "ingest"'):])
    assert out["ingest"]["staged"] > 0 and out["augment"]["counts"]
    assert (root / "augmented" / "data.yaml").exists()


def test_ingest_receipts_cli_empty_inbox(tmp_path):
    r = run_cli("--data-root", tmp_path / "d", "ingest-receipts", "--engine", "fake")
    assert r.returncode == 0 and json.loads(r.stdout) == {}


def test_run_all_stdout_is_single_json(tmp_path):
    z = zip_dir(build_drop(tmp_path / "drop", per_class=15), tmp_path / "d.zip")
    r = run_cli("--data-root", tmp_path / "data", "run-all", "--zip", z, "--name", "synth",
                "--adapter", "agrifreshnet", "--per-image", "1")
    json.loads(r.stdout)
