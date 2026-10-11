#!/usr/bin/env python
"""Check metrics JSON (from detection_metrics.py and/or ocr_metrics.py) against docs/QA.md thresholds.

Usage: python ml/eval/check_thresholds.py det.json [ocr.json ...]
Gates are binary (spoiled vs not-spoiled); semi_fresh is never gated (see ml/eval/README.md).
Prints PASS/FAIL per metric; exit 1 if any FAIL. A metric that is missing or not computable
(None) is a FAIL ("not evaluable"), never a silent pass. Sections absent from the inputs are
reported as SKIP only with --allow-missing-section det|ocr.
"""
from __future__ import annotations

import argparse
import json
import sys

T = {
    "map50": 0.60,
    "precision": 0.80,
    "spoiled_recall": 0.85,
    "recall_drop_points": 10.0,
    "ocr_line_recall": 0.85,
    "ocr_price_exact": 0.90,
    "ocr_total_exact": 0.90,
    "ocr_min_receipts": 20,
}


def _get(d, *path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def run_checks(m: dict, skip=()):
    """Returns list of (name, status, detail) with status PASS/FAIL/SKIP."""
    out = []

    def ge(name, val, thr, pct=False):
        if val is None:
            out.append((name, "FAIL", f"not evaluable (need >= {thr})"))
        else:
            ok = val >= thr
            fmt = (lambda x: f"{x:.1%}") if pct else (lambda x: f"{x:.3f}")
            out.append((name, "PASS" if ok else "FAIL", f"{fmt(val)} (need >= {fmt(thr)})"))

    def le(name, val, thr):
        if val is None:
            out.append((name, "FAIL", f"not evaluable (need <= {thr} points)"))
        else:
            out.append((name, "PASS" if val <= thr else "FAIL", f"{val:.1f} points (need <= {thr:.0f})"))

    if "det" in skip:
        out.append(("YOLO", "SKIP", "no detection metrics supplied"))
    else:
        d = m.get("detection")
        ge("YOLO mAP@0.5", _get(d, "map50"), T["map50"])
        # Gates are binary (semi_fresh folded into not-spoiled). "fresh precision" = NOT-SPOILED precision.
        # "not_spoiled" is preferred; the legacy "fresh" key (an alias) is accepted for old metric files.
        # semi_fresh / freshness_3way are information only and are never read here.
        fr = _get(d, "freshness") or {}
        ns = fr.get("not_spoiled") if "not_spoiled" in fr else fr.get("fresh")
        ge("YOLO precision [not-spoiled]", _get(ns, "precision"), T["precision"])
        ge("YOLO precision [spoiled]", _get(fr, "spoiled", "precision"), T["precision"])
        ge("YOLO recall [spoiled]", _get(d, "freshness", "spoiled", "recall"), T["spoiled_recall"])
        drops = _get(d, "recall_drop_points") or {}
        for lt in ("low", "warm"):
            le(f"YOLO recall drop {lt} vs normal (overall)", _get(drops, lt, "overall"), T["recall_drop_points"])
            le(f"YOLO recall drop {lt} vs normal (spoiled)", _get(drops, lt, "spoiled"), T["recall_drop_points"])
    if "ocr" in skip:
        out.append(("OCR", "SKIP", "no OCR metrics supplied"))
    else:
        o = m.get("ocr")
        n = _get(o, "n_receipts")
        out.append(("OCR sample size", "PASS" if n is not None and n >= T["ocr_min_receipts"] else "FAIL",
                    f"{n} receipts (need >= {T['ocr_min_receipts']})"))
        ge("OCR line-item recall", _get(o, "line_recall"), T["ocr_line_recall"], True)
        ge("OCR price exact", _get(o, "price_exact"), T["ocr_price_exact"], True)
        ge("OCR total exact", _get(o, "total_exact"), T["ocr_total_exact"], True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("metrics", nargs="+", help="metrics JSON file(s); merged")
    ap.add_argument("--allow-missing-section", action="append", default=[], choices=["det", "ocr"])
    a = ap.parse_args(argv)
    merged = {}
    for p in a.metrics:
        with open(p, encoding="utf-8") as f:
            merged.update(json.load(f))
    skip = [s for s in a.allow_missing_section if ("detection" if s == "det" else "ocr") not in merged]
    results = run_checks(merged, skip)
    for name, st, detail in results:
        print(f"{st:4s}  {name}: {detail}")
    bad = [r for r in results if r[1] == "FAIL"]
    print(f"\n{'FAIL' if bad else 'PASS'}: {len(bad)} failing of {len([r for r in results if r[1] != 'SKIP'])} checked")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
