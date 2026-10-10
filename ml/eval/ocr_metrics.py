#!/usr/bin/env python
"""Receipt OCR metrics from ground-truth / prediction files. Pure stdlib.

Ground truth: {"receipt": str, "lines": [{"name","quantity","price"}], "total": float}
Predictions:  {"receipt": str, "lines": [...], "total": float|null, "raw_text": str}  (the /ocr shape)
Either side may be a directory of *.json files (receipt id = "receipt" key, else the file stem),
a .jsonl file, or a .json file holding one object or a list.

Metrics (micro-averaged over all receipts):
  line_recall  = GT lines matched / GT lines.
      Name match: both names normalised (lowercase, non-alphanumerics -> space, whitespace
      collapsed) then difflib.SequenceMatcher ratio >= NAME_THRESHOLD (0.80). Matching is
      one-to-one, greedy on the highest ratio first, within a receipt.
  price_exact  = matched lines whose price equals the GT price to the cent / matched lines.
  quantity_exact (informational) = same idea for quantity (compared as floats, tolerance 1e-6).
  total_exact  = receipts whose predicted total equals GT total to the cent / receipts with a GT total.
  line_precision (informational) = matched predicted lines / predicted lines.
A receipt with no prediction scores zero lines and a missed total.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

NAME_THRESHOLD = 0.80


def normalise(s) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", str(s or "").lower())
    return " ".join(s.split())


def name_ratio(a, b) -> float:
    return difflib.SequenceMatcher(None, normalise(a), normalise(b)).ratio()


def cents(x):
    if x is None:
        return None
    try:
        return int(round(float(x) * 100))
    except (TypeError, ValueError):
        return None


def match_lines(gt_lines, pred_lines, threshold=NAME_THRESHOLD):
    """One-to-one greedy matching; returns list of (gt_idx, pred_idx, ratio)."""
    pairs = []
    for i, g in enumerate(gt_lines):
        for j, p in enumerate(pred_lines):
            r = name_ratio(g.get("name"), p.get("name"))
            if r >= threshold:
                pairs.append((r, i, j))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    ug, up, out = set(), set(), []
    for r, i, j in pairs:
        if i in ug or j in up:
            continue
        ug.add(i); up.add(j)
        out.append((i, j, r))
    return out


def load_records(path):
    recs = []
    if os.path.isdir(path):
        for fn in sorted(os.listdir(path)):
            if fn.endswith(".json"):
                with open(os.path.join(path, fn), encoding="utf-8") as f:
                    d = json.load(f)
                d.setdefault("receipt", os.path.splitext(fn)[0])
                recs.append(d)
    elif path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            recs = [json.loads(l) for l in f if l.strip()]
    else:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        recs = d if isinstance(d, list) else [d]
    out = {}
    for r in recs:
        if r["receipt"] in out:
            raise ValueError(f"duplicate receipt {r['receipt']!r} in {path}")
        out[r["receipt"]] = r
    return out


def evaluate(gt: dict, pred: dict, threshold=NAME_THRESHOLD) -> dict:
    unknown = sorted(set(pred) - set(gt))
    if unknown:
        raise ValueError(f"predictions for receipts absent from ground truth: {unknown[:5]}")
    n_gt = n_pred = n_match = n_price = n_qty = 0
    n_tot = n_tot_ok = 0
    per = {}
    for rid, g in gt.items():
        p = pred.get(rid) or {"lines": [], "total": None}
        gl, pl = g.get("lines", []), p.get("lines") or []
        m = match_lines(gl, pl, threshold)
        price_ok = sum(1 for i, j, _ in m if cents(gl[i].get("price")) is not None
                       and cents(gl[i].get("price")) == cents(pl[j].get("price")))
        qty_ok = 0
        for i, j, _ in m:
            try:
                qty_ok += abs(float(gl[i].get("quantity", 1)) - float(pl[j].get("quantity"))) < 1e-6
            except (TypeError, ValueError):
                pass
        t_ok = None
        if g.get("total") is not None:
            n_tot += 1
            t_ok = cents(p.get("total")) == cents(g["total"])
            n_tot_ok += t_ok
        n_gt += len(gl); n_pred += len(pl); n_match += len(m); n_price += price_ok; n_qty += qty_ok
        per[rid] = {"gt_lines": len(gl), "pred_lines": len(pl), "matched": len(m), "price_ok": price_ok,
                    "total_ok": t_ok,
                    "missed": [gl[i].get("name") for i in range(len(gl)) if i not in {a for a, _, _ in m}]}
    r = lambda a, b: None if b == 0 else a / b
    return {"ocr": {"n_receipts": len(gt), "name_threshold": threshold,
                    "gt_lines": n_gt, "pred_lines": n_pred, "matched_lines": n_match,
                    "line_recall": r(n_match, n_gt), "line_precision": r(n_match, n_pred),
                    "price_exact": r(n_price, n_match), "quantity_exact": r(n_qty, n_match),
                    "total_exact": r(n_tot_ok, n_tot), "per_receipt": per}}


def print_report(res):
    o = res["ocr"]
    f = lambda x: "n/a" if x is None else f"{x:.1%}"
    print(f"receipts: {o['n_receipts']}  lines gt/pred/matched: {o['gt_lines']}/{o['pred_lines']}/{o['matched_lines']}")
    print(f"line recall {f(o['line_recall'])} | price exact {f(o['price_exact'])} | total exact {f(o['total_exact'])}"
          f" | (info) line precision {f(o['line_precision'])}, quantity exact {f(o['quantity_exact'])}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gt", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--json")
    ap.add_argument("--threshold", type=float, default=NAME_THRESHOLD)
    a = ap.parse_args(argv)
    res = evaluate(load_records(a.gt), load_records(a.pred), a.threshold)
    print_report(res)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
