"""Independent stratification / source-confound / report-consistency check (ML-16, ML-23, ML-24).

Reads only the prepared dataset on disk (labels/, freshness/, images/, class_names.json,
heldout_manifest.csv, dataset_report.json); no code from ml/yolo is imported.

  python ml/eval/stratification_check.py /path/to/fwr_data [--json out.json]

Rules (QA.md + orchestrator #28): a class x freshness cell with >= 10 images AND >= 2 capture
sessions must appear in held-out; single-session cells are "not measurable on held-out"; no cell
may exist only in held-out/val (never trained on).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from leakage_check import SOURCES, SPLITS, originals, source_of, stamp, series_key  # noqa: E402

GAP = 300.0


def image_cells(root: Path, split: str, p: Path):
    stem = p.stem
    lab = (root / "labels" / split / f"{stem}.txt").read_text().split()
    cls = [int(l.split()[0]) for l in (root / "labels" / split / f"{stem}.txt").read_text().splitlines() if l.strip()]
    fr = [int(x) for x in (root / "freshness" / split / f"{stem}.txt").read_text().split()]
    names = json.loads((root / "class_names.json").read_text())
    return {(names[str(c)], "spoiled" if f else "fresh") for c, f in zip(cls, fr)}


def check(root: Path) -> dict:
    files = originals(root)
    rows = []  # (split, src, cells, ts or None, key)
    for s in SPLITS:
        for p in files[s]:
            st = stamp(p.name)
            sk = series_key(p.name, source_of(p.name))
            rows.append({"split": s, "src": source_of(p.name), "cells": image_cells(root, s, p),
                         "ts": st[1] if st else None, "name": p.name,
                         "key": (sk[0] if sk else p.name.split("_jpg")[0])})
    # capture sessions: chain timestamps per source with a 300 s gap; untimestamped -> series stem / original stem
    sess = {}
    for src in SOURCES:
        ts = sorted((r["ts"], i) for i, r in enumerate(rows) if r["src"] == src and r["ts"] is not None)
        sid, last = -1, None
        for t, i in ts:
            if last is None or t - last > GAP:
                sid += 1
            sess[i] = f"{src}/t{sid}"
            last = t
    for i, r in enumerate(rows):
        r["session"] = sess.get(i, f"{r['src']}/s:{r['key']}")
    by_cell = defaultdict(lambda: {"images": Counter(), "sessions": set(), "sources": Counter()})
    for r in rows:
        for c in r["cells"]:
            k = f"{c[0]}/{c[1]}"
            by_cell[k]["images"][r["split"]] += 1
            by_cell[k]["sessions"].add(r["session"])
            by_cell[k]["sources"][r["src"]] += 1
    out = {"cells": {}, "missing_from_heldout_required": [], "single_session_not_measurable": [],
           "small_not_measurable": [], "never_trained_cells": []}
    for k, v in sorted(by_cell.items()):
        n = sum(v["images"].values())
        out["cells"][k] = {"train": v["images"]["train"], "val": v["images"]["val"], "heldout": v["images"]["heldout"],
                           "sessions": len(v["sessions"]), "sources": dict(v["sources"])}
        if n < 10:
            out["small_not_measurable"].append(k)
        elif v["images"]["heldout"] == 0:
            (out["single_session_not_measurable"] if len(v["sessions"]) < 2 else out["missing_from_heldout_required"]).append(k)
        if v["images"]["train"] == 0:
            out["never_trained_cells"].append(k)
    # class x source x freshness
    cs = defaultdict(lambda: defaultdict(Counter))
    for r in rows:
        for c in r["cells"]:
            cs[c[0]][r["src"]][c[1]] += 1
    out["class_by_source"] = {c: {s: dict(f) for s, f in v.items()} for c, v in sorted(cs.items())}
    out["spoiled_single_source"] = {c: list(s for s, f in v.items() if f.get("spoiled")) for c, v in cs.items()
                                    if sum(1 for f in v.values() if f.get("spoiled")) == 1}
    out["no_spoiled_at_all"] = [c for c, v in cs.items() if not any(f.get("spoiled") for f in v.values())]
    # per source split sizes
    out["source_by_split"] = {s: dict(Counter(r["split"] for r in rows if r["src"] == s)) for s in SOURCES}
    # report vs manifest (ML-24)
    rep = json.loads((root / "dataset_report.json").read_text())
    man = list(csv.DictReader((root / "heldout_manifest.csv").open()))
    orig = [m for m in man if not m["variant_of"]]
    chk = {
        "report.heldout_manifest_rows == manifest rows": (rep.get("heldout_manifest_rows"), len(man)),
        "report.heldout_originals == manifest originals": (rep.get("heldout_originals"), len(orig)),
        "report.heldout_originals == disk originals": (rep.get("heldout_originals"), len(files["heldout"])),
        "report.splits.heldout.images == disk originals": (rep["splits"]["heldout"]["images"], len(files["heldout"])),
        "report.splits.train.images == disk": (rep["splits"]["train"]["images"], len(files["train"])),
        "report.splits.val.images == disk": (rep["splits"]["val"]["images"], len(files["val"])),
        "manifest rows == gt.jsonl rows": (len(man), sum(1 for _ in (root / "heldout_gt.jsonl").open())),
        "manifest rows == files in images/heldout": (len(man), len(list((root / "images" / "heldout").glob("*.jpg")))),
    }
    lm = Counter(f"{m['lighting']}/{m['lighting_method']}" for m in man)
    chk["report.heldout_images_by_lighting_method == manifest"] = (rep.get("heldout_images_by_lighting_method"), dict(lm))
    sbs = {s: {"train/images": 0, "val/images": 0, "heldout/images": 0} for s in SOURCES}
    for r in rows:
        sbs[r["src"]][f"{r['split']}/images"] += 1
    for s in SOURCES:
        rs = rep["source_by_split"].get(s, {})
        for k in ("train/images", "val/images", "heldout/images"):
            chk[f"report.source_by_split[{s}][{k}] == disk"] = (rs.get(k), sbs[s][k])
    out["report_vs_manifest"] = {k: {"report": a, "actual": b, "ok": a == b} for k, (a, b) in chk.items()}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    a = ap.parse_args()
    r = check(Path(a.root))
    print(json.dumps({k: v for k, v in r.items() if k not in ("cells", "report_vs_manifest")}, indent=1))
    print("CELLS (train/val/heldout, sessions):")
    for k, v in r["cells"].items():
        print(f"  {k:24s} {v['train']:5d} {v['val']:5d} {v['heldout']:5d}  sess={v['sessions']}")
    bad = {k: v for k, v in r["report_vs_manifest"].items() if not v["ok"]}
    print("report vs manifest mismatches:", json.dumps(bad, indent=1) if bad else "none")
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2))
    ok = not r["missing_from_heldout_required"] and not r["never_trained_cells"] and not bad
    print("STRATIFICATION:", "PASS" if ok else "FAIL")
