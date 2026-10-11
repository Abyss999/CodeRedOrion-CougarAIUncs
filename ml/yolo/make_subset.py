#!/usr/bin/env python
"""Deterministic ~5% subset of a prepared dataset, for the Colab DRY RUN (symlinks, no copies).

Ultralytics' own `fraction=0.05` train arg takes the FIRST 5% of the sorted file list (verified in 8.4.175,
data/base.py and ClassificationDataset): that is one or two sources / one class folder, so it would not exercise the
3-class freshness head or most detector classes. This takes every STRIDE-th file instead (starting at the first), per
split for the detector set and per split x class folder for the classifier crops, so every class that has data keeps
at least one image and the choice is identical on every run.

  python make_subset.py --data /content/fwr_data --out /content/fwr_data_dry [--stride 20]
"""
import argparse, csv, json, os, re, shutil
from pathlib import Path


def _pick(items, stride):
    return items[::stride]


def make_subset(data, out, stride=20):
    data, out = Path(data).resolve(), Path(out)
    if out.exists():
        shutil.rmtree(out)
    stats = {}
    chosen_heldout = set()
    for sp in ("train", "val", "heldout"):
        imgs = sorted(p for p in (data / "images" / sp).glob("*") if p.is_file())
        sel = _pick(imgs, stride)
        for sub in ("images", "labels", "freshness"):
            (out / sub / sp).mkdir(parents=True, exist_ok=True)
        for p in sel:
            os.symlink(p, out / "images" / sp / p.name)
            for sub in ("labels", "freshness"):
                src = data / sub / sp / (p.stem + ".txt")
                if src.exists():
                    os.symlink(src, out / sub / sp / src.name)
        stats[sp] = len(sel)
        if sp == "heldout":
            chosen_heldout = {f"images/heldout/{p.name}" for p in sel}
    for sp in ("train", "val"):
        base = data / "cls" / sp
        if not base.is_dir():
            continue
        for cdir in sorted(d for d in base.iterdir() if d.is_dir()):
            (out / "cls" / sp / cdir.name).mkdir(parents=True, exist_ok=True)
            files = sorted(p for p in cdir.iterdir() if p.is_file())
            for p in _pick(files, stride):
                os.symlink(p, out / "cls" / sp / cdir.name / p.name)
            stats[f"cls/{sp}/{cdir.name}"] = len(_pick(files, stride))
    y = (data / "data.yaml").read_text()
    (out / "data.yaml").write_text(re.sub(r"(?m)^path:.*$", f"path: {out.resolve()}", y))
    for f in ("class_names.json", "dataset_report.json"):
        if (data / f).exists():
            shutil.copy(data / f, out / f)
    with open(data / "heldout_gt.jsonl") as fi, open(out / "heldout_gt.jsonl", "w") as fo:
        for line in fi:
            if json.loads(line)["image"] in chosen_heldout:
                fo.write(line)
    with open(data / "heldout_manifest.csv", newline="") as fi, open(out / "heldout_manifest.csv", "w", newline="") as fo:
        r = csv.DictReader(fi)
        w = csv.DictWriter(fo, fieldnames=r.fieldnames)
        w.writeheader()
        w.writerows(row for row in r if row["image"] in chosen_heldout)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=int, default=20, help="keep every Nth file (20 = 5%%)")
    a = ap.parse_args()
    print(json.dumps(make_subset(a.data, a.out, a.stride), indent=1))
