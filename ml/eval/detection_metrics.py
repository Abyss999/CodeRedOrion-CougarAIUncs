#!/usr/bin/env python
"""Detection metrics for the Food Waste Reducer YOLO model, computed from JSONL files.

Pure stdlib: runs anywhere (here on the VPS on fixtures, on Colab output later).

File format (one JSON object per line, one line per image):
  predictions: {"image", "lighting": "normal"|"low"|"warm",
                "predictions": [{"name","category","freshness","confidence","bbox":[x1,y1,x2,y2]}]}
  ground truth: same, with "labels" (no confidence) instead of "predictions".

Definitions (all documented so the numbers can be audited):
  * IoU: standard box IoU on [x1,y1,x2,y2]; zero-area / disjoint boxes give 0.0.
    A pair matches when IoU >= 0.5 (>=, boundary inclusive).
  * Matching is greedy by descending confidence; each GT box is used at most once; a
    prediction takes the unmatched GT of the right kind with the highest IoU (>= 0.5).
  * mAP@0.5: per *item class* (`name`), predictions of that name are matched only to GT of that
    name, across all images, sorted by confidence; AP is the all-point-interpolated area under the
    precision envelope (VOC2010+ / COCO "all point"). Classes with no GT are skipped. A class with
    GT but no predictions has AP 0. No confidence threshold is applied for AP.
  * Freshness is three-class in the data (fresh | semi_fresh | spoiled) but the GATED metrics are
    BINARY, spoiled vs not-spoiled (docs/QA.md "Freshness gates"). semi_fresh is folded into
    not_spoiled in BOTH ground truth and predictions before matching, so a fresh<->semi_fresh
    confusion costs nothing. Two-class files (no semi_fresh) give identical numbers to before.
  * Not-spoiled / spoiled precision & recall: for each binary class c, only predictions with
    folded freshness==c (and confidence >= --conf) compete for GT with folded freshness==c. By
    default matching ignores `name` (localisation + freshness label); pass --match-name to also
    require the name.
        precision = TP/(TP+FP), recall = TP/(TP+FN); None when the denominator is 0.
    The result key "not_spoiled" holds the not-spoiled numbers; the legacy key "fresh" is an
    identical alias (so it means fresh+semi_fresh, NOT fresh alone). The "fresh precision" gate
    reads as NOT-SPOILED precision.
  * INFORMATION ONLY, never gated ("freshness_3way"): every GT box is matched to a prediction on
    localisation alone (IoU >= 0.5, greedy by confidence, freshness ignored), then counted in a
    3x3 confusion matrix confusion[gt][pred] with an extra "missed" column (GT with no match) and
    a "false_positive" row (prediction with no GT). Per-class 3-way precision = diag / column sum
    (incl. false positives), recall = diag / row sum (incl. missed).
  * Lighting split: the same metrics on the images of each lighting group; `recall_drop` is
    (normal recall - group recall) * 100, in percentage points (negative = group is better).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

IOU_THRESHOLD = 0.5
FRESHNESS3 = ("fresh", "semi_fresh", "spoiled")   # data labels
FRESHNESS = ("not_spoiled", "spoiled")             # gated binary classes (semi_fresh folds into not_spoiled)
LIGHTING = ("normal", "low", "warm")


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = min(ax2, bx2) - max(ax1, bx1)
    ih = min(ay2, by2) - max(ay1, by1)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    ua = max(ax2 - ax1, 0) * max(ay2 - ay1, 0) + max(bx2 - bx1, 0) * max(by2 - by1, 0) - inter
    return inter / ua if ua > 0 else 0.0


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: invalid JSON ({e})") from e
    return rows


def _index(rows, key, what):
    out = {}
    for r in rows:
        img = r["image"]
        if img in out:
            raise ValueError(f"duplicate image {img!r} in {what}")
        out[img] = r
    return out


def fold(freshness) -> str:
    """Binary gate class of a freshness label. Unknown labels raise (never silently dropped)."""
    if freshness == "spoiled":
        return "spoiled"
    if freshness in ("fresh", "semi_fresh"):
        return "not_spoiled"
    raise ValueError(f"unknown freshness label {freshness!r} (expected one of {FRESHNESS3})")


def _ratio(num, den):
    return None if den == 0 else num / den


def _match_counts(preds_by_img, gts_by_img, same):
    """Greedy match. preds_by_img: img -> [pred]; gts_by_img: img -> [gt]; same(p, g) -> bool
    (extra compatibility test). Returns (tp, fp, fn)."""
    tp = fp = 0
    n_gt = sum(len(v) for v in gts_by_img.values())
    for img, preds in preds_by_img.items():
        gts = gts_by_img.get(img, [])
        used = [False] * len(gts)
        for p in sorted(preds, key=lambda x: -x["confidence"]):
            best, best_iou = -1, IOU_THRESHOLD
            for i, g in enumerate(gts):
                if used[i] or not same(p, g):
                    continue
                v = iou(p["bbox"], g["bbox"])
                if v >= best_iou and (best < 0 or v > best_iou):
                    best, best_iou = i, v
            if best >= 0:
                used[best] = True
                tp += 1
            else:
                fp += 1
    return tp, fp, n_gt - tp


def freshness_metrics(gt_rows, pred_rows, conf=0.0, match_name=False):
    """Binary (gated) metrics: not_spoiled vs spoiled, semi_fresh folded into not_spoiled."""
    out = {}
    tot_tp = tot_fp = tot_fn = 0
    for cls in FRESHNESS:
        pb = {r["image"]: [p for p in r.get("predictions", []) if fold(p["freshness"]) == cls and p["confidence"] >= conf]
              for r in pred_rows}
        gb = {r["image"]: [g for g in r.get("labels", []) if fold(g["freshness"]) == cls] for r in gt_rows}
        same = (lambda p, g: p["name"] == g["name"]) if match_name else (lambda p, g: True)
        tp, fp, fn = _match_counts(pb, gb, same)
        out[cls] = {"precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
                    "tp": tp, "fp": fp, "fn": fn, "n_gt": tp + fn}
        tot_tp += tp; tot_fp += fp; tot_fn += fn
    out["fresh"] = dict(out["not_spoiled"])  # legacy alias: fresh+semi_fresh, see module docstring
    out["overall"] = {"precision": _ratio(tot_tp, tot_tp + tot_fp), "recall": _ratio(tot_tp, tot_tp + tot_fn),
                      "tp": tot_tp, "fp": tot_fp, "fn": tot_fn, "n_gt": tot_tp + tot_fn}
    return out


def freshness_3way(gt_rows, pred_rows, conf=0.0, match_name=False):
    """INFORMATION ONLY (no gate): 3x3 freshness confusion + per-class P/R, localisation-only matching."""
    pi = {r["image"]: r for r in pred_rows}
    conf_m = {g: {p: 0 for p in FRESHNESS3} for g in FRESHNESS3}
    for g in FRESHNESS3:
        conf_m[g]["missed"] = 0
    fp_row = {p: 0 for p in FRESHNESS3}
    for r in gt_rows:
        gts = r.get("labels", [])
        for g in gts:
            if g["freshness"] not in FRESHNESS3:
                raise ValueError(f"unknown freshness label {g['freshness']!r} (expected one of {FRESHNESS3})")
        preds = [p for p in pi.get(r["image"], {}).get("predictions", []) if p["confidence"] >= conf]
        for p in preds:
            if p["freshness"] not in FRESHNESS3:
                raise ValueError(f"unknown freshness label {p['freshness']!r} (expected one of {FRESHNESS3})")
        used = [False] * len(gts)
        for p in sorted(preds, key=lambda x: -x["confidence"]):
            best, best_iou = -1, IOU_THRESHOLD
            for i, g in enumerate(gts):
                if used[i] or (match_name and p["name"] != g["name"]):
                    continue
                v = iou(p["bbox"], g["bbox"])
                if v >= best_iou and (best < 0 or v > best_iou):
                    best, best_iou = i, v
            if best >= 0:
                used[best] = True
                conf_m[gts[best]["freshness"]][p["freshness"]] += 1
            else:
                fp_row[p["freshness"]] += 1
        for i, g in enumerate(gts):
            if not used[i]:
                conf_m[g["freshness"]]["missed"] += 1
    out = {"gated": False, "labels": list(FRESHNESS3), "confusion": conf_m, "false_positive": fp_row}
    for c in FRESHNESS3:
        tp = conf_m[c][c]
        n_gt = sum(conf_m[c].values())
        n_pred = sum(conf_m[g][c] for g in FRESHNESS3) + fp_row[c]
        out[c] = {"precision": _ratio(tp, n_pred), "recall": _ratio(tp, n_gt), "tp": tp, "n_gt": n_gt, "n_pred": n_pred}
    return out


def average_precision(recalls, precisions) -> float:
    """All-point interpolated AP from a PR curve (recalls ascending)."""
    mrec = [0.0] + list(recalls) + [1.0]
    mpre = [0.0] + list(precisions) + [0.0]
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    ap = 0.0
    for i in range(1, len(mrec)):
        if mrec[i] != mrec[i - 1]:
            ap += (mrec[i] - mrec[i - 1]) * mpre[i]
    return ap


def class_ap(gt_rows, pred_rows, name) -> float | None:
    gts = {r["image"]: [g for g in r.get("labels", []) if g["name"] == name] for r in gt_rows}
    n_gt = sum(len(v) for v in gts.values())
    if n_gt == 0:
        return None
    allp = []
    for r in pred_rows:
        for p in r.get("predictions", []):
            if p["name"] == name:
                allp.append((p["confidence"], r["image"], p))
    allp.sort(key=lambda t: -t[0])  # stable: ties keep file order
    used = {img: [False] * len(v) for img, v in gts.items()}
    tps = []
    for _, img, p in allp:
        best, best_iou = -1, IOU_THRESHOLD
        for i, g in enumerate(gts.get(img, [])):
            if used[img][i]:
                continue
            v = iou(p["bbox"], g["bbox"])
            if v >= best_iou and (best < 0 or v > best_iou):
                best, best_iou = i, v
        if best >= 0:
            used[img][best] = True
            tps.append(1)
        else:
            tps.append(0)
    ctp = cfp = 0
    rec, prec = [], []
    for t in tps:
        ctp += t; cfp += 1 - t
        rec.append(ctp / n_gt)
        prec.append(ctp / (ctp + cfp))
    return average_precision(rec, prec)


def map50(gt_rows, pred_rows):
    names = sorted({g["name"] for r in gt_rows for g in r.get("labels", [])})
    aps = {n: class_ap(gt_rows, pred_rows, n) for n in names}
    vals = list(aps.values())
    return (sum(vals) / len(vals) if vals else None), aps


def evaluate_group(gt_rows, pred_rows, conf=0.0, match_name=False):
    m, aps = map50(gt_rows, pred_rows)
    return {"n_images": len(gt_rows), "map50": m, "ap_per_class": aps,
            "freshness": freshness_metrics(gt_rows, pred_rows, conf, match_name),
            "freshness_3way": freshness_3way(gt_rows, pred_rows, conf, match_name)}


def evaluate(gt_rows, pred_rows, conf=0.0, match_name=False) -> dict:
    gi = _index(gt_rows, "image", "ground truth")
    pi = _index(pred_rows, "image", "predictions")
    unknown = sorted(set(pi) - set(gi))
    if unknown:
        raise ValueError(f"predictions for images absent from ground truth: {unknown[:5]}")
    # images with no prediction row count as empty predictions (every GT is a miss)
    preds = [pi.get(img, {"image": img, "predictions": []}) for img in gi]
    gts = list(gi.values())
    res = {"detection": evaluate_group(gts, preds, conf, match_name)}
    res["detection"]["conf_threshold"] = conf
    res["detection"]["match_name"] = match_name
    by = {}
    for lt in sorted({r.get("lighting", "normal") for r in gts}):
        g = [r for r in gts if r.get("lighting", "normal") == lt]
        p = [pi.get(r["image"], {"image": r["image"], "predictions": []}) for r in g]
        by[lt] = evaluate_group(g, p, conf, match_name)
    res["detection"]["by_lighting"] = by
    drops = _drops(by)
    res["detection"]["recall_drop_points"] = drops
    return res


def load_manifest(path):
    """heldout_manifest.csv -> {image: {"lighting_method", "variant_of"}} (columns per docs/ML.md)."""
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        return {r["image"]: {"lighting_method": r.get("lighting_method", ""), "variant_of": r.get("variant_of", "")}
                for r in csv.DictReader(f)}


def _recall_of(grp, key):
    if key == "semi_fresh":  # information only, from the 3-way block
        return grp["freshness_3way"]["semi_fresh"]["recall"]
    return grp["freshness"][key]["recall"]


def _drops(by):
    """Recall drop in points vs normal. overall/spoiled/not_spoiled(+legacy fresh) are the gated binary
    numbers; semi_fresh is information only."""
    base = by.get("normal")
    out = {}
    for lt, grp in by.items():
        if lt == "normal":
            continue
        out[lt] = {}
        for key in ("overall", "spoiled", "not_spoiled", "fresh", "semi_fresh"):
            b = _recall_of(base, key) if base else None
            v = _recall_of(grp, key)
            out[lt][key] = None if b is None or v is None else (b - v) * 100.0
    return out


def evaluate_lighting_sources(gt_rows, pred_rows, manifest, conf=0.0, match_name=False):
    """Report REAL lighting (method auto/manual) and SYNTHETIC lighting separately.
    real: all non-synthetic images, split by their lighting tag, drop vs real normal.
    synthetic: synthetic low/warm copies vs the original normal images they were derived from (variant_of)."""
    pi = {r["image"]: r for r in pred_rows}
    def pr(r):
        return pi.get(r["image"], {"image": r["image"], "predictions": []})
    meth = lambda r: manifest.get(r["image"], {}).get("lighting_method", "")
    real = [r for r in gt_rows if meth(r) != "synthetic"]
    synth = [r for r in gt_rows if meth(r) == "synthetic"]
    originals = {manifest[r["image"]]["variant_of"] for r in synth}
    out = {"real": {}, "synthetic": {}}
    def split(rows):
        by = {}
        for lt in sorted({r.get("lighting", "normal") for r in rows}):
            g = [r for r in rows if r.get("lighting", "normal") == lt]
            by[lt] = evaluate_group(g, [pr(r) for r in g], conf, match_name)
        return by
    out["real"]["by_lighting"] = split(real)
    out["real"]["recall_drop_points"] = _drops(out["real"]["by_lighting"])
    base_rows = [r for r in gt_rows if r["image"] in originals]
    sby = split(synth)
    if base_rows:
        sby["normal"] = evaluate_group(base_rows, [pr(r) for r in base_rows], conf, match_name)
    out["synthetic"]["by_lighting"] = sby
    out["synthetic"]["recall_drop_points"] = _drops(sby)
    out["n_real"], out["n_synthetic"] = len(real), len(synth)
    return out


def _fmt(x):
    return "n/a" if x is None else f"{x:.3f}"


def print_report(res):
    d = res["detection"]
    print(f"images: {d['n_images']}  mAP@0.5: {_fmt(d['map50'])}")
    for n, ap in d["ap_per_class"].items():
        print(f"  AP[{n}] = {_fmt(ap)}")
    print("-- gated (binary: semi_fresh folded into not_spoiled) --")
    for cls in (*FRESHNESS, "overall"):
        f = d["freshness"][cls]
        print(f"{cls:11s} P={_fmt(f['precision'])} R={_fmt(f['recall'])} (tp={f['tp']} fp={f['fp']} fn={f['fn']})")
    t = d["freshness_3way"]
    print("-- information only, NOT gated: 3x3 freshness confusion (rows = ground truth, cols = prediction) --")
    cols = [*FRESHNESS3, "missed"]
    print(f"{'':11s}" + "".join(f"{c:>12s}" for c in cols))
    for g in FRESHNESS3:
        print(f"{g:11s}" + "".join(f"{t['confusion'][g][c]:12d}" for c in cols))
    print(f"{'false_pos':11s}" + "".join(f"{t['false_positive'][c]:12d}" for c in FRESHNESS3))
    for c in FRESHNESS3:
        print(f"3-way {c:11s} P={_fmt(t[c]['precision'])} R={_fmt(t[c]['recall'])} (n_gt={t[c]['n_gt']})")
    for lt, g in d["by_lighting"].items():
        o = g["freshness"]["overall"]; s = g["freshness"]["spoiled"]
        print(f"[{lt}] n={g['n_images']} mAP={_fmt(g['map50'])} recall={_fmt(o['recall'])} spoiled_recall={_fmt(s['recall'])}")
    for lt, dr in d["recall_drop_points"].items():
        print(f"recall drop {lt} vs normal (points): overall={dr['overall']} spoiled={dr['spoiled']} semi_fresh(info)={dr['semi_fresh']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gt", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--json", help="write metrics JSON here")
    ap.add_argument("--conf", type=float, default=0.25, help="confidence cut-off for fresh/spoiled P/R (default 0.25; mAP ignores it)")
    ap.add_argument("--manifest", help="heldout_manifest.csv; adds real-vs-synthetic lighting reports")
    ap.add_argument("--match-name", action="store_true", help="fresh/spoiled P/R also require the item name to match")
    a = ap.parse_args(argv)
    res = evaluate(load_jsonl(a.gt), load_jsonl(a.pred), a.conf, a.match_name)
    if a.manifest:
        gi = {r["image"]: r for r in load_jsonl(a.gt)}
        res["detection"]["lighting_sources"] = evaluate_lighting_sources(
            list(gi.values()), load_jsonl(a.pred), load_manifest(a.manifest), a.conf, a.match_name)
    print_report(res)
    ls = res["detection"].get("lighting_sources")
    if ls:
        print(f"-- lighting by source (real n={ls['n_real']}, synthetic n={ls['n_synthetic']}; synthetic is usually EASIER) --")
        for src in ("real", "synthetic"):
            for lt, dr in ls[src]["recall_drop_points"].items():
                print(f"{src:9s} {lt}: recall drop overall={dr['overall']} spoiled={dr['spoiled']} semi_fresh(info)={dr['semi_fresh']}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
