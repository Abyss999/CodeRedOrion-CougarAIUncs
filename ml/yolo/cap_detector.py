#!/usr/bin/env python
"""Capped DETECTOR training set, for the Colab FAST profile (symlinks, no copies).

The detector only learns food names; freshness comes from the crop classifier. So the detector does not need every
image of the big classes (bell_pepper 2.5k boxes, butter 184). This keeps up to CAP boxes per food name in the TRAIN
split and leaves everything else untouched:
  - val, heldout, cls (classifier crops), heldout_gt / manifest: linked or copied whole, so the gates, the classifier
    and every held-out metric are exactly as for the full set;
  - a class with <= CAP boxes keeps all its images.
Selection is deterministic (no RNG): images are taken round-robin over (food, freshness, source) cells, so fresh /
semi_fresh / spoiled and every source keep a share, and within a cell multi-object images come first (one image covers
several foods), then a stable hash order. An image is taken if it adds a box to any food still under CAP.

  python cap_detector.py --data /content/fwr_data --out /content/fwr_data_fast [--cap 400]
"""
import argparse, hashlib, json, os, re, shutil
from collections import Counter, defaultdict
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import FRESHNESS_CODE  # noqa: E402

CODE_TO_FRESHNESS = {str(v): k for k, v in FRESHNESS_CODE.items()}   # sidecar: 0 fresh, 1 spoiled, 2 semi_fresh


def _boxes(data, stem, names):
    """[(food, freshness)] for one train image. Freshness sidecar: one FRESHNESS_CODE per label line (missing -> fresh)."""
    lab = [l.split()[0] for l in (data / "labels" / "train" / f"{stem}.txt").read_text().splitlines() if l.strip()]
    fp = data / "freshness" / "train" / f"{stem}.txt"
    fr = [l.strip() for l in fp.read_text().splitlines() if l.strip()] if fp.exists() else []
    return [(names[c], CODE_TO_FRESHNESS.get(fr[i], "fresh") if i < len(fr) else "fresh") for i, c in enumerate(lab)]


def _source(stem, sources):
    return next((s for s in sources if stem.startswith(s + "_")), "unknown")


def select(data, cap):
    """Deterministic list of train image paths kept under CAP boxes per food name."""
    data = Path(data)
    names = {str(k): v for k, v in json.loads((data / "class_names.json").read_text()).items()}
    rep = data / "dataset_report.json"
    sources = sorted(json.loads(rep.read_text()).get("source_by_split", {}) if rep.exists() else {}, key=len, reverse=True)
    imgs = {}
    for p in sorted(q for q in (data / "images" / "train").iterdir() if q.is_file()):
        lp = data / "labels" / "train" / f"{p.stem}.txt"
        imgs[p] = _boxes(data, p.stem, names) if lp.exists() else []
    total = Counter(f for bx in imgs.values() for f, _ in bx)
    keep, got = [], Counter()
    cells = defaultdict(list)
    for p, bx in imgs.items():
        if not bx or any(total[f] <= cap for f, _ in bx):     # background images and rare foods: keep everything
            keep.append(p); got.update(f for f, _ in bx)
            continue
        f, fr = Counter(bx).most_common(1)[0][0]            # the image's main (food, freshness)
        cells[(f, fr, _source(p.stem, sources))].append(p)
    for k in cells:
        cells[k].sort(key=lambda p: (-len({f for f, _ in imgs[p]}), hashlib.sha1(p.name.encode()).hexdigest()))
    queues = [cells[k] for k in sorted(cells)]
    while any(queues):
        for q in queues:
            if q:
                p = q.pop(0)
                if any(got[f] < cap for f, _ in imgs[p]):
                    keep.append(p); got.update(f for f, _ in imgs[p])
    return sorted(keep), total, got, Counter(fr for p in keep for _, fr in imgs[p])


def cap_detector(data, out, cap=400):
    data, out = Path(data).resolve(), Path(out)
    if out.exists():
        shutil.rmtree(out)
    keep, total, got, fresh = select(data, cap)
    for sub in ("images", "labels", "freshness"):
        (out / sub / "train").mkdir(parents=True, exist_ok=True)
        for sp in ("val", "heldout"):
            if (data / sub / sp).exists():
                os.symlink(data / sub / sp, out / sub / sp)
    for p in keep:
        os.symlink(p, out / "images" / "train" / p.name)
        for sub in ("labels", "freshness"):
            src = data / sub / "train" / f"{p.stem}.txt"
            if src.exists():
                os.symlink(src, out / sub / "train" / src.name)
    if (data / "cls").exists():
        os.symlink(data / "cls", out / "cls")
    y = (data / "data.yaml").read_text()
    (out / "data.yaml").write_text(re.sub(r"(?m)^path:.*$", f"path: {out.resolve()}", y))
    for f in ("class_names.json", "dataset_report.json", "heldout_gt.jsonl", "heldout_manifest.csv"):
        if (data / f).exists():
            shutil.copy(data / f, out / f)
    n_train = sum(1 for q in (data / "images" / "train").iterdir() if q.is_file())
    stats = {"cap": cap, "train_images": len(keep), "train_images_full": n_train,
             "boxes_by_freshness": dict(sorted(fresh.items())),
             "boxes_by_food": {f: f"{got[f]}/{total[f]}" for f in sorted(total)}}
    (out / "cap_report.json").write_text(json.dumps(stats, indent=1))
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--cap", type=int, default=400, help="max train boxes per food name (default 400)")
    a = ap.parse_args()
    print(json.dumps(cap_detector(a.data, a.out, a.cap), indent=1))
