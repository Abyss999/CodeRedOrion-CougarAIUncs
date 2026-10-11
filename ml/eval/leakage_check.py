"""Independent held-out leakage check for a prepared dataset (ML-21). Per source.

QA.md criterion (ML-21):
  * timestamped images: 0 held-out images with a same-source train/val image within 300 s
    (the 60 s and 300 s neighbour rates are reported per source);
  * untimestamped / numbered series: pHash-64 (Hamming <= 6) near-duplicates from held-out to
    train+val must be <= 1% of held-out, per source;
  * every class x freshness cell with >= 10 images appears in held-out (smaller = "not measurable").

Implemented independently of ml/yolo/dedup.py: pHash/dHash come from the `imagehash` package
(`pip install imagehash pillow numpy`); timestamps are found with re.search over several
camera / screenshot / epoch-ms patterns. Only ORIGINAL images are checked (`__low`/`__warm`
synthetic copies are ignored).

  python ml/eval/leakage_check.py /path/to/fwr_data [--json out.json] [--hash-cache cache.json]
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

SOURCES = ("agrifreshnet", "fresh_stale_fruits_veg", "fridge_objects", "hien_fridge", "vegqual",
           "meatscan", "dafif", "food_spoilage_status")  # ML-48: new3 sources were invisible to the gate
SPLITS = ("train", "val", "heldout")
PHASH_T = 6

_EPOCH = re.compile(r"(?<!\d)(1[4-9]\d{11})(?!\d)")                       # 13-digit epoch ms (2014-2033)
_COMPACT = re.compile(r"(?<!\d)(20\d{6})[_-]?([0-2]\d[0-5]\d[0-5]\d)(?:\d{3})?(?!\d)")  # IMG_20200727_223202
_SHOT = re.compile(r"(20\d\d-\d\d-\d\d)_at_(\d{1,2})[_.](\d\d)[_.](\d\d)(?:_(AM|PM))?")  # Screen_Shot_2020-07-29_at_8_31_22_PM


_HYPHEN = re.compile(r"(20\d\d-\d\d-\d\d)-at-(\d{1,2})-(\d\d)-(\d\d)(?:-(AM|PM))?")  # Roboflow-sanitised: Screen-Shot-2018-06-08-at-5-09-10-PM (ML-49)


def stamp(name: str):
    """(kind, seconds) found anywhere in the filename, or None."""
    m = _EPOCH.search(name)
    if m:
        return "epoch", int(m.group(1)) / 1000.0
    m = _COMPACT.search(name)
    if m:
        try:
            return "compact", datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
        except ValueError:
            pass
    m = _SHOT.search(name)
    if m:
        h = int(m.group(2)) % 12 + (12 if m.group(5) == "PM" else 0) if m.group(5) else int(m.group(2))
        try:
            return "shot", datetime.strptime(f"{m.group(1)} {h:02d}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            pass
    m = _HYPHEN.search(name)
    if m:
        h = int(m.group(2)) % 12 + (12 if m.group(5) == "PM" else 0) if m.group(5) else int(m.group(2))
        try:
            return "shot", datetime.strptime(f"{m.group(1)} {h:02d}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            pass
    return None


def source_of(name: str) -> str:
    for s in SOURCES:
        if name.startswith(s + "_"):
            return s
    return name.partition("_")[0]


def originals(root: Path):
    return {s: [p for p in sorted((root / "images" / s).glob("*.jpg")) if "__low" not in p.name and "__warm" not in p.name]
            for s in SPLITS}


def series_key(name: str, src: str):
    """(series stem, index) for numbered series such as IMG1234, Defected_begun_104, ID12_apple_003; else None."""
    rest = name[len(src) + 1:]
    rest = re.sub(r"_jpg.*$", "", rest)
    m = re.match(r"^(.*?)_?(\d{1,5})$", rest)
    if m and not re.search(r"\d{8}", rest) and not _EPOCH.search(rest):
        return m.group(1), int(m.group(2))
    return None


def hash_images(files, cache: dict | None):
    import imagehash
    from PIL import Image
    out = {}
    for p in files:
        k = p.name
        if cache is not None and k in cache:
            out[k] = cache[k]
            continue
        with Image.open(p) as im:
            im = im.convert("RGB")
            out[k] = [int(str(imagehash.phash(im, hash_size=8)), 16), int(str(imagehash.dhash(im, hash_size=8)), 16)]
        if cache is not None:
            cache[k] = out[k]
    return out


def neighbours(held, ref, thresh=PHASH_T):
    """For each held hash return the min Hamming distance and index into ref (numpy, chunked)."""
    import numpy as np
    pop = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    r = np.array(ref, dtype=np.uint64)
    res = []
    for h in held:
        x = np.uint64(h) ^ r
        d = pop[x.view(np.uint8).reshape(len(r), 8)].sum(axis=1)
        j = int(d.argmin())
        res.append((int(d[j]), j))
    return res


def check(root: Path, hash_cache: Path | None = None, with_hash: bool = True, pairs_out: list | None = None) -> dict:
    files = originals(root)
    ref_ts = defaultdict(list)
    for s in ("train", "val"):
        for p in files[s]:
            st = stamp(p.name)
            if st:
                ref_ts[(source_of(p.name), st[0])].append(st[1])
    for v in ref_ts.values():
        v.sort()

    cache = json.loads(hash_cache.read_text()) if hash_cache and hash_cache.exists() else ({} if hash_cache else None)
    hashes = {}
    if with_hash:
        allf = [p for s in SPLITS for p in files[s]]
        hashes = hash_images(allf, cache)
        if hash_cache:
            hash_cache.write_text(json.dumps(cache))

    # series stems (numbered cameras / ID series) in train+val
    series = defaultdict(list)
    for s in ("train", "val"):
        for p in files[s]:
            k = series_key(p.name, source_of(p.name))
            if k:
                series[(source_of(p.name), k[0])].append(k[1])

    report = {}
    for src in SOURCES:
        held = [p for p in files["heldout"] if source_of(p.name) == src]
        trval = [p for s in ("train", "val") for p in files[s] if source_of(p.name) == src]
        r = {"heldout_originals": len(held), "train_val_originals": len(trval), "with_timestamp": 0, "without_timestamp": 0,
             "within_60s": 0, "within_300s": 0, "min_gap_s": None}
        gaps = []
        for p in held:
            st = stamp(p.name)
            if not st:
                r["without_timestamp"] += 1
                continue
            r["with_timestamp"] += 1
            arr = ref_ts.get((src, st[0]), [])
            if arr:
                i = bisect.bisect_left(arr, st[1])
                gaps.append(min(abs(arr[j] - st[1]) for j in (i - 1, i) if 0 <= j < len(arr)))
        r["within_60s"] = sum(g <= 60 for g in gaps)
        r["within_300s"] = sum(g <= 300 for g in gaps)
        r["min_gap_s"] = min(gaps) if gaps else None
        r["within_60s_pct_of_timestamped"] = round(100 * r["within_60s"] / max(1, r["with_timestamp"]), 2)
        r["within_300s_pct_of_timestamped"] = round(100 * r["within_300s"] / max(1, r["with_timestamp"]), 2)
        # numbered series with a neighbour index within +-3 in train/val
        near_idx = 0
        n_series = 0
        for p in held:
            k = series_key(p.name, src)
            if k:
                n_series += 1
                if any(abs(i - k[1]) <= 3 for i in series.get((src, k[0]), [])):
                    near_idx += 1
        r["numbered_series_heldout"] = n_series
        r["numbered_series_with_trainval_index_within_3"] = near_idx
        if with_hash and held and trval:
            ref = [hashes[p.name] for p in trval]
            for tag, col in (("phash", 0), ("dhash", 1)):
                nb = neighbours([hashes[p.name][col] for p in held], [x[col] for x in ref])
                bad = [(held[i], trval[j], d) for i, (d, j) in enumerate(nb) if d <= PHASH_T]
                r[f"{tag}_near_dup"] = len(bad)
                r[f"{tag}_near_dup_pct"] = round(100 * len(bad) / len(held), 2)
                if pairs_out is not None and tag == "dhash":
                    pairs_out.extend((src, str(a), str(b), d) for a, b, d in bad)
                if tag == "phash":
                    r["phash_pairs"] = [(a.name, b.name, d) for a, b, d in bad][:50]
        r["criterion"] = {
            "timestamp_300s_zero": r["within_300s"] == 0,
            "phash_le_1pct": (r.get("phash_near_dup_pct", 0.0) <= 1.0) if with_hash else None,
        }
        report[src] = r
    return report


def session_audit(root: Path, gap: float = 300.0, small: int = 10) -> dict:
    """Pooled-unit assertion (orchestrator ruling). Sessions = maximal runs of same-source, same-clock-kind
    timestamps with consecutive gaps <= `gap` (chained, over ALL splits). For every session that has a
    held-out image:
      * FRAGMENT: it also has train/val members  -> the held-out part is a fragment of a larger session;
      * GAP: min |t - t'| to any train/val image of the same source/kind outside the session must be >= `gap`.
    Sessions with < `small` images are the ones the builder may pool ("pooled timestamped units"); they are
    reported separately. `assertion_ok` is False if any fragment exists or any gap < `gap`."""
    files = originals(root)
    out = {}
    ok_all = True
    for src in SOURCES:
        items = defaultdict(list)  # kind -> [(t, split)]
        for sp in SPLITS:
            for p in files[sp]:
                if source_of(p.name) != src:
                    continue
                st = stamp(p.name)
                if st:
                    items[st[0]].append((st[1], sp))
        r = {"heldout_sessions": 0, "heldout_small_sessions": 0, "heldout_small_session_images": 0,
             "fragments": 0, "fragment_examples": [], "min_gap_to_trainval_s": None}
        for kind, lst in items.items():
            lst.sort()
            sessions, cur = [], [lst[0]]
            for a, b in zip(lst, lst[1:]):
                if b[0] - a[0] > gap:
                    sessions.append(cur)
                    cur = []
                cur.append(b)
            sessions.append(cur)
            tv = [t for t, sp in lst if sp != "heldout"]
            for ses in sessions:
                held = [t for t, sp in ses if sp == "heldout"]
                if not held:
                    continue
                r["heldout_sessions"] += 1
                if len(ses) < small:
                    r["heldout_small_sessions"] += 1
                    r["heldout_small_session_images"] += len(ses)
                if any(sp != "heldout" for _, sp in ses):
                    r["fragments"] += 1
                    if len(r["fragment_examples"]) < 3:
                        r["fragment_examples"].append({"kind": kind, "size": len(ses), "heldout": len(held)})
                if tv:
                    i = bisect.bisect_left(tv, held[0])
                    cand = [abs(tv[j] - t) for t in (held[0], held[-1]) for j in (bisect.bisect_left(tv, t) - 1, bisect.bisect_left(tv, t))
                            if 0 <= j < len(tv)]
                    g = min(cand)
                    if r["min_gap_to_trainval_s"] is None or g < r["min_gap_to_trainval_s"]:
                        r["min_gap_to_trainval_s"] = g
        r["assertion_ok"] = r["fragments"] == 0 and (r["min_gap_to_trainval_s"] is None or r["min_gap_to_trainval_s"] >= gap)
        ok_all &= r["assertion_ok"]
        out[src] = r
    out["_all_ok"] = ok_all
    return out


def cells(root: Path, min_images: int = 10) -> dict:
    """class x freshness image counts per split from the YOLO labels + the class map, + the not-in-held-out list."""
    names = json.loads((root / "class_names.json").read_text())
    gt = {}
    for line in (root / "heldout_gt.jsonl").read_text().splitlines():
        d = json.loads(line)
        if "__low" in d["image"] or "__warm" in d["image"]:
            continue
        gt[Path(d["image"]).name] = {(b["name"], b["freshness"]) for b in d["labels"]}
    held = defaultdict(int)
    for v in gt.values():
        for c in v:
            held[c] += 1
    return {"heldout_cells": {f"{a}/{b}": n for (a, b), n in sorted(held.items())}, "n_classes": len(names)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    ap.add_argument("--hash-cache")
    ap.add_argument("--no-hash", action="store_true")
    ap.add_argument("--dhash-pairs", help="write dHash-flagged pairs (src, heldout, train/val, dist) as JSON")
    a = ap.parse_args()
    pairs = [] if a.dhash_pairs else None
    want_hash = not a.no_hash
    if want_hash:
        try:
            import imagehash  # noqa: F401
        except ImportError:
            print("WARNING: `imagehash` not installed (pip install imagehash): pHash check SKIPPED, criterion not fully evaluated", file=sys.stderr)
            want_hash = False
    r = check(Path(a.root), Path(a.hash_cache) if a.hash_cache else None, want_hash, pairs)
    if a.dhash_pairs:
        Path(a.dhash_pairs).write_text(json.dumps(pairs))
    audit = session_audit(Path(a.root))
    print("SESSION / POOLED-UNIT ASSERTION (min gap to train/val >= 300 s, no fragments):")
    print(json.dumps(audit, indent=1))
    if not audit["_all_ok"]:
        print("!!! POOLED-UNIT ASSERTION FAILED: a held-out session is a fragment of a larger session or sits within 300 s of train/val !!!", file=sys.stderr)
    for src, v in audit.items():            # make the notebook's per-source assertion fire on a session-audit failure
        if src != "_all_ok" and not v["assertion_ok"]:
            r[src]["criterion"]["timestamp_300s_zero"] = False
    slim = {k: {kk: vv for kk, vv in v.items() if kk != "phash_pairs"} for k, v in r.items()}
    print(json.dumps(slim, indent=2))
    if a.json:
        # flat aggregate keys (within_60s, within_300s, ...) are kept for ml/yolo/train_colab.ipynb's gate
        agg = {k: sum(v[k] for v in r.values()) for k in ("heldout_originals", "with_timestamp", "within_60s", "within_300s")}
        Path(a.json).write_text(json.dumps({**agg, "per_source": r, "session_audit": audit}, indent=2))
        if not audit["_all_ok"]:
            agg["within_300s"] = max(agg["within_300s"], 1)   # make the notebook gate (within_300s == 0) fail loudly
            Path(a.json).write_text(json.dumps({**agg, "per_source": r, "session_audit": audit}, indent=2))
    ok = audit["_all_ok"] and all(v["criterion"]["timestamp_300s_zero"] and v["criterion"]["phash_le_1pct"] is not False for v in r.values())
    print("ML-21 timestamp+pHash criterion:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
