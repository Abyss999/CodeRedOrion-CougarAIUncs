"""Independent near-duplicate leakage check for a prepared dataset (stdlib only).

For every held-out ORIGINAL image whose filename carries a capture timestamp (13-digit epoch ms, or
IMG_YYYYMMDD_HHMMSS), find the nearest-in-time train/val image of the same source and report how many
sit within 10 s / 60 s / 300 s. Also checks '.rf.' stem groups straddling splits. Images without a
timestamp are counted but cannot be tested this way.

  python ml/eval/leakage_check.py /path/to/fwr_data [--json out.json]
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

EPOCH = re.compile(r"^(\d{13})(?!\d)")
COMPACT = re.compile(r"^(?:IMG|PXL|VID)?_?(\d{8})_?(\d{6})(?!\d)")


def stamp(name: str):
    """(kind, seconds) from a filename with the 'source_' prefix removed, or None."""
    m = EPOCH.match(name)
    if m:
        return "epoch", int(m.group(1)) / 1000.0
    m = COMPACT.match(name)
    if m:
        return "compact", datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
    return None


def parse(path: Path):
    stem = path.name
    src, _, rest = stem.partition("_")
    return src, rest, stamp(rest)


def check(root: Path) -> dict:
    split_files = {s: [p for p in sorted((root / "images" / s).glob("*.jpg")) if "__low" not in p.name and "__warm" not in p.name]
                   for s in ("train", "val", "heldout")}
    ref = defaultdict(list)  # (src, kind) -> sorted timestamps of train/val
    for s in ("train", "val"):
        for p in split_files[s]:
            src, _, st = parse(p)
            if st:
                ref[(src, st[0])].append(st[1])
    for v in ref.values():
        v.sort()
    stems = defaultdict(set)
    for s, files in split_files.items():
        for p in files:
            stems[p.name.split("_rf_")[0]].add(s)
    out = {"heldout_originals": len(split_files["heldout"]), "with_timestamp": 0, "without_timestamp": 0,
           "within_10s": 0, "within_60s": 0, "within_300s": 0, "min_gap_s": None,
           "rf_stems_in_multiple_splits": sum(len(v) > 1 for v in stems.values())}
    gaps = []
    for p in split_files["heldout"]:
        src, _, st = parse(p)
        if not st:
            out["without_timestamp"] += 1
            continue
        out["with_timestamp"] += 1
        arr = ref.get((src, st[0]), [])
        if not arr:
            continue
        i = bisect.bisect_left(arr, st[1])
        g = min(abs(arr[j] - st[1]) for j in (i - 1, i) if 0 <= j < len(arr))
        gaps.append(g)
    for k, t in (("within_10s", 10), ("within_60s", 60), ("within_300s", 300)):
        out[k] = sum(g <= t for g in gaps)
    out["min_gap_s"] = min(gaps) if gaps else None
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    a = ap.parse_args()
    r = check(Path(a.root))
    print(json.dumps(r, indent=2))
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2))
    sys.exit(0)
