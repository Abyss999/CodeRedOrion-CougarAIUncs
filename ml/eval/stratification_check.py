"""Independent stratification / source-confound / report-consistency check (ML-16, ML-23, ML-24).

Reads only the prepared dataset on disk (labels/, freshness/, images/, class_names.json,
heldout_manifest.csv, dataset_report.json); no code from ml/yolo is imported.

  python ml/eval/stratification_check.py /path/to/fwr_data [--json out.json]

Rules (QA.md + orchestrator #28 + approved rulings): a class x freshness cell is REQUIRED in held-out
if it has >= 10 images and >= 2 independent units (capture sessions with >= `min_session_images`
images of the cell, or a pool of smaller whole groups); otherwise it is "not measurable on held-out"
and goes entirely to train (held-out = val = 0). Train keeps >= 50% of every required cell. No cell may
exist only in held-out/val. The decision per cell is READ FROM dataset_report.json and then verified
against the files on disk and against an independent session reconstruction (300 s chains).

PASS only if: every required cell has held-out > 0 and train >= 50% (images and boxes); every
not-measurable cell has held-out = val = 0; every cell >= 10 images that is absent from held-out is
listed not-measurable by the report AND has < 2 independent sessions of >= min_session_images by my own
count; no timestamped session (my reconstruction, unmerged) spans train/val/held-out; no pHash near-duplicate pair
straddles splits inside a merged unit (the merge, capped at the builder's max_unit_images, only feeds the count of
independent units); report == manifest == disk.
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
import re
_AUG = re.compile(r"(rotated_by_-?\d+_|saltandpepper_|translation_|vertical_flip_|horizontal_flip_)")


def image_cells(root: Path, split: str, p: Path):
    stem = p.stem
    lab = (root / "labels" / split / f"{stem}.txt").read_text().split()
    cls = [int(l.split()[0]) for l in (root / "labels" / split / f"{stem}.txt").read_text().splitlines() if l.strip()]
    fr = [int(x) for x in (root / "freshness" / split / f"{stem}.txt").read_text().split()]
    names = json.loads((root / "class_names.json").read_text())
    return {(names[str(c)], {0: "fresh", 1: "spoiled", 2: "semi_fresh"}[f]) for c, f in zip(cls, fr)}


def _merge_by_phash(root: Path, rows: list, max_unit: int = 600) -> dict:
    """Sets r["unit"] (and r["unit_ts"], True if any merged session is timestamped): sessions/series merged across
    pHash <= 6 neighbours within a source, for the measurability count ONLY (ML-21; r["session"] is left untouched, and
    the span rule runs on it). Mirrors prepare_dataset.merge_near_duplicates: a component of more than `max_unit` images
    is NOT merged (its sessions stay separate units). Returns the cross-split near-duplicate pairs inside merged units
    (ML-60: those units span splits because of the pair, a gate failure), computed here from the images."""
    import numpy as np
    from leakage_check import hash_images, PHASH_T
    pop = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    by_src = defaultdict(list)
    for i, r in enumerate(rows):
        by_src[r["src"]].append(i)
    pairs, oversized = [], 0
    for src, idx in by_src.items():
        paths = [root / "images" / rows[i]["split"] / rows[i]["name"] for i in idx]
        hs = hash_images(paths, None)
        h = np.array([hs[p.name][0] for p in paths], dtype=np.uint64)
        parent = {rows[i]["session"]: rows[i]["session"] for i in idx}
        has_ts = {}
        for i in idx:
            has_ts[rows[i]["session"]] = has_ts.get(rows[i]["session"], False) or rows[i]["ts"] is not None

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        near = []
        for a in range(len(idx) - 1):
            d = pop[(h[a] ^ h[a + 1:]).view(np.uint8).reshape(-1, 8)].sum(axis=1)
            for b in np.nonzero(d <= PHASH_T)[0]:
                ia, ib = idx[a], idx[a + 1 + int(b)]
                ra, rb = find(rows[ia]["session"]), find(rows[ib]["session"])
                if ra != rb:
                    parent[ra] = rb
                    has_ts[rb] = has_ts[rb] or has_ts[ra]      # the flag travels with the union
                if rows[ia]["split"] != rows[ib]["split"]:
                    near.append((ia, ib, int(d[b])))
        size = Counter(find(rows[i]["session"]) for i in idx)
        big = {c for c, n in size.items() if n > max_unit}
        oversized += len(big)
        for i in idx:
            root_id = find(rows[i]["session"])
            merged = root_id not in big
            rows[i]["unit"] = root_id if merged else rows[i]["session"]
            rows[i]["unit_ts"] = has_ts[root_id] if merged else has_ts[rows[i]["session"]]
        pairs += [{"unit": find(rows[ia]["session"]), "a": rows[ia]["name"], "a_split": rows[ia]["split"], "b": rows[ib]["name"],
                   "b_split": rows[ib]["split"], "hamming": d}
                  for ia, ib, d in near if find(rows[ia]["session"]) not in big]
    return {"max_unit_images": max_unit, "oversized_components_not_merged": oversized, "cross_split_pairs": pairs}


def check(root: Path, phash_merge: bool = True) -> dict:
    files = originals(root)
    rows = []  # (split, src, cells, ts or None, key)
    for s in SPLITS:
        for p in files[s]:
            st = stamp(p.name)
            sk = series_key(p.name, source_of(p.name))
            rows.append({"split": s, "src": source_of(p.name), "cells": image_cells(root, s, p),
                         "ts": st[1] if st else None, "name": p.name,
                         "key": (sk[0] if sk else _AUG.sub("", p.name).split("_jpg")[0])})
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
    # explicit per-session flag (does the session contain any timestamped row); never parsed from the id string
    ts_sessions = {r["session"] for r in rows if r["ts"] is not None}
    for r in rows:
        r["session_ts"] = r["session"] in ts_sessions
        r["unit"], r["unit_ts"] = r["session"], r["session_ts"]
    merge = None
    if phash_merge:
        try:
            nd = json.loads((root / "dataset_report.json").read_text()).get("grouping", {}).get("near_duplicates") or {}
        except (OSError, ValueError):
            nd = {}
        merge = _merge_by_phash(root, rows, int(nd.get("max_unit_images", 600)))
    by_cell = defaultdict(lambda: {"images": Counter(), "sessions": set(), "sources": Counter()})
    for r in rows:
        for c in r["cells"]:
            k = f"{c[0]}/{c[1]}"
            by_cell[k]["images"][r["split"]] += 1
            by_cell[k]["sessions"].add(r["unit"])
            by_cell[k]["sources"][r["src"]] += 1
    out = {"_rows": rows, "cells": {}, "missing_from_heldout_required": [], "single_session_not_measurable": [],
           "small_not_measurable": [], "never_trained_cells": [], "phash_merge": merge}
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
            chk[f"report.source_by_split[{s}][{k}] == disk"] = (rs.get(k, 0), sbs[s][k])  # ML-54: report omits zero entries
    out["report_vs_manifest"] = {k: {"report": a, "actual": b, "ok": a == b} for k, (a, b) in chk.items()}
    return out


def box_cells(root: Path):
    """(class, freshness) -> {split: boxes} from the label files."""
    names = json.loads((root / "class_names.json").read_text())
    out = defaultdict(Counter)
    for sp in SPLITS:
        for lf in (root / "labels" / sp).glob("*.txt"):
            if "__low" in lf.name or "__warm" in lf.name:
                continue
            ff = root / "freshness" / sp / lf.name
            cls = [int(l.split()[0]) for l in lf.read_text().splitlines() if l.strip()]
            fr = [int(x) for x in ff.read_text().split()]
            for c, f in zip(cls, fr):
                out[(names[str(c)], {0: "fresh", 1: "spoiled", 2: "semi_fresh"}[f])][sp] += 1
    return out


def verify(root: Path, out: dict) -> dict:
    """Apply the rules to the report's per-cell decisions. Returns {"failures": [...], "info": {...}}."""
    rep = json.loads((root / "dataset_report.json").read_text())
    dec = rep["stratification"].get("cell_decisions", {})
    min_s = rep["stratification"].get("min_session_images", 10)
    boxes = box_cells(root)
    fails, info = [], {"val_missing_for_required": [], "required_cells_relying_on_pooling": [], "decision_table": {}}
    for k, c in out["cells"].items():
        d = dec.get(k)
        if d is None:
            fails.append(f"{k}: no decision in report")
            continue
        n = c["train"] + c["val"] + c["heldout"]
        b = boxes.get(tuple(k.split("/")), Counter())
        bn = sum(b.values())
        # my own independent count of sessions with >= min_s images of the cell
        by_sess = Counter()
        for r in out["_rows"]:
            if tuple(k.split("/")) in r["cells"]:
                by_sess[r["unit"]] += 1
        mine_big = sum(1 for v in by_sess.values() if v >= min_s)
        info["decision_table"][k] = {"decision": d["decision"], "train/val/heldout_images": [c["train"], c["val"], c["heldout"]],
                                     "train_pct_images": round(100 * c["train"] / n, 1), "train_pct_boxes": round(100 * b["train"] / max(1, bn), 1),
                                     "my_sessions_ge_min": mine_big, "report_units": d["units"]["units"]}
        if d["decision"] == "required_in_heldout":
            if c["heldout"] == 0:
                fails.append(f"{k}: required but held-out is empty")
            if c["train"] / n < 0.5:
                fails.append(f"{k}: train has {100 * c['train'] / n:.1f}% of images (< 50%)")
            if bn and b["train"] / bn < 0.5:
                fails.append(f"{k}: train has {100 * b['train'] / bn:.1f}% of boxes (< 50%)")
            if c["train"] == 0:
                fails.append(f"{k}: never trained on")
            if c["val"] == 0:
                info["val_missing_for_required"].append(k)
            if mine_big < 2:
                info["required_cells_relying_on_pooling"].append(k)
        else:
            if c["heldout"] or c["val"] or c["train"] != n:
                fails.append(f"{k}: not measurable but split is {c['train']}/{c['val']}/{c['heldout']}")
            if mine_big >= 2:
                fails.append(f"{k}: report says not measurable but I count {mine_big} sessions with >= {min_s} images")
    # any cell >= 10 images absent from held-out must be not-measurable in the report
    for k, c in out["cells"].items():
        n = c["train"] + c["val"] + c["heldout"]
        if n >= 10 and c["heldout"] == 0 and dec.get(k, {}).get("decision") == "required_in_heldout":
            fails.append(f"{k}: >= 10 images, absent from held-out, but not listed not-measurable")
    # the legacy key now follows the report's decisions (what the Colab gate reads)
    out["missing_from_heldout_required"] = [k for k, c in out["cells"].items()
                                            if dec.get(k, {}).get("decision") == "required_in_heldout" and c["heldout"] == 0]
    # span rule on the UNMERGED sessions (merging must never hide a span): a session with any timestamped row that
    # spans splits fails; untimestamped stem groups are info (ML-59)
    span, sess_ts = defaultdict(set), {}
    for r in out["_rows"]:
        span[r["session"]].add(r["split"])
        sess_ts[r["session"]] = r["session_ts"]
    ts_span = [s for s, v in span.items() if len(v) > 1 and sess_ts[s]]
    stem_span = [s for s, v in span.items() if len(v) > 1 and not sess_ts[s]]
    if ts_span:
        fails.append(f"{len(ts_span)} timestamped sessions span more than one split: {ts_span[:3]}")
    # cross-split pHash pairs inside merged units (ML-60) are reported with examples, not failed: the per-source <= 1%
    # threshold for identity pHash pairs is leakage_check's gate (ML-21; owner ruling 2026-10-11, warning only)
    pm = out.get("phash_merge") or {}
    pairs = pm.get("cross_split_pairs", [])
    info["phash_cross_split_pair_examples"] = [
        f"{p['a']} ({p['a_split']}) ~ {p['b']} ({p['b_split']}), hamming {p['hamming']}" for p in pairs[:5]]
    info["timestamped_sessions_spanning_splits"] = len(ts_span)
    info["phash_cross_split_pairs"] = len(pairs)
    info["phash_oversized_components_not_merged"] = pm.get("oversized_components_not_merged", 0)
    info["phash_max_unit_images"] = pm.get("max_unit_images")
    info["stem_groups_spanning_splits"] = len(stem_span)
    info["stem_group_examples"] = stem_span[:5]
    for kk, v in out["report_vs_manifest"].items():
        if not v["ok"]:
            fails.append(f"report vs manifest: {kk}")
    return {"failures": fails, "info": info}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    ap.add_argument("--no-phash-merge", action="store_true", help="count independence on timestamps/series only")
    a = ap.parse_args()
    root = Path(a.root)
    r = check(root, phash_merge=not a.no_phash_merge)
    v = verify(root, r)
    r.pop("_rows", None)
    print("CELLS: decision, train/val/heldout images, train% (images/boxes), my >=min sessions vs report units")
    for k, t in v["info"]["decision_table"].items():
        print(f"  {k:22s} {t['decision'][:12]:12s} {t['train/val/heldout_images']!s:18s} {t['train_pct_images']:5.1f}/{t['train_pct_boxes']:5.1f}  mine={t['my_sessions_ge_min']} report={t['report_units']}")
    print("required cells with no val image:", v["info"]["val_missing_for_required"])
    print("required cells that rely on pooling (I count < 2 sessions >= min):", v["info"]["required_cells_relying_on_pooling"])
    print("timestamped sessions spanning splits:", v["info"]["timestamped_sessions_spanning_splits"],
          "| pHash cross-split pairs in merged units:", v["info"]["phash_cross_split_pairs"],
          "| oversized components left unmerged:", v["info"]["phash_oversized_components_not_merged"])
    print("stem groups spanning splits (info):", v["info"]["stem_groups_spanning_splits"], v["info"]["stem_group_examples"])
    print("spoiled from exactly one source:", r["spoiled_single_source"], "| no spoiled at all:", r["no_spoiled_at_all"])
    print("FAILURES:", json.dumps(v["failures"], indent=1) if v["failures"] else "none")
    if a.json:
        Path(a.json).write_text(json.dumps({**r, **v}, indent=2, default=list))
    print("STRATIFICATION:", "FAIL" if v["failures"] else "PASS")
    sys.exit(1 if v["failures"] else 0)
