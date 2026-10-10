"""Staged datasets -> one sources.json -> ml/yolo/prepare_dataset.py (unchanged) -> prepared/.

Every staged/<name>/source.json is included, plus any extra sources files (e.g. the Roboflow/Kaggle
sources.json from docs/ML.md), so new drops and the original sources merge into ONE dataset.
"""
from __future__ import annotations
import contextlib
import json
import shutil
import sys
from pathlib import Path

from .. import config  # noqa: F401
import prepare_dataset as P  # noqa: E402


def collect_sources(staged: Path, extra: list[Path] | None = None) -> list[dict]:
    srcs = [json.loads(p.read_text()) for p in sorted(staged.glob("*/source.json"))]
    for e in extra or []:
        srcs += json.loads(Path(e).read_text())["sources"]
    names = [s["name"] for s in srcs]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f"duplicate source names: {sorted(dup)}")
    return srcs


def prepare(staged: Path, out: Path, extra: list[Path] | None = None, replace: bool = False,
            prepare_args: list[str] | None = None) -> dict:
    srcs = collect_sources(staged, extra)
    if not srcs:
        raise SystemExit(f"no staged datasets under {staged}; run ingest-dataset first")
    if out.exists() and any(out.iterdir()):
        if not replace:
            raise SystemExit(f"{out} is not empty; pass --replace to rebuild it")
        shutil.rmtree(out)
    sources_file = staged / "sources.json"
    sources_file.write_text(json.dumps({"sources": srcs}, indent=2) + "\n")
    with contextlib.redirect_stdout(sys.stderr):  # prepare_dataset prints a summary; keep CLI stdout pure JSON
        P.main(["--sources", str(sources_file), "--out", str(out), *(prepare_args or [])])
    return json.loads((out / "dataset_report.json").read_text())
