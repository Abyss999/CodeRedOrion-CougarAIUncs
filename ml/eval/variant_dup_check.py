"""Variant-aware near-duplicate REPORT (informational; NOT a gate; orchestrator ruling ML-40).

The gate for held-out leakage stays identity pHash <= 6, <= 1% per source (`leakage_check.py`). This tool measures
something the identity hash cannot: flipped / rotated copies. Every image is hashed in its 8 dihedral variants
(identity, hflip, rot90/180/270, each with and without a flip) and the MINIMUM Hamming distance to the reference set is
used (querying 8 variants against identity hashes of the reference is equivalent to all 64 pairings because the
dihedral group is closed under inverse).

Why it cannot be a gate (ML-40): a min over 8 variants gives 8 chances per pair, and plain / padded backgrounds make
unrelated images collide. So this report is computed with two safeguards and always printed next to a noise floor:
  * SAME CLASS ONLY. A pair counts only if the two images share a food class (from the YOLO label files; images
    without labels share the key "?" and are compared with each other). A tomato "matching" a bitter melon is not leakage.
  * NO PADDING ARTIFACTS. Rotated-and-padded copies (Kaggle set: black corners from a 45 degree rotation) hash on the
    black corners. Before hashing, a corner-black padding region is filled with the mean colour of the rest of the
    image (`--no-mask` disables), and only the CENTRAL 80% of the image is hashed (`--crop`, default 0.8).
  * NOISE FLOOR next to every rate: the nearest DIFFERENT-class image, drawn from a random subset of different-class
    references of the same size as the query's same-class reference set (so the two numbers are comparable); the
    unmatched all-different-class rate is reported too. Excess = same-class minus matched floor, in points. If the excess
    is about zero, the rate is background similarity, not duplication.

Per source: held-out -> train+val and val -> train (same-class, different-class floor, identity-only same-class),
within-set rate (nearest other same-class image, any split) and how many such pairs straddle splits, and optionally
specimen components. Exit code is always 0 (reported only).

  python ml/eval/variant_dup_check.py /path/to/fwr_data [--json out.json] [--cache hashes.json] [-T 6] [--crop 0.8] [--no-mask]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from leakage_check import SPLITS, originals  # noqa: E402

CROP = 0.8
BLACK = 12            # max channel value counted as "black" padding
_POP = None


def pop8():
    import numpy as np
    global _POP
    if _POP is None:
        _POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    return _POP


def mask_padding(im):
    """Fill black rotation padding (dark corners) with the mean colour of the remaining pixels.
    Applies only when at least 3 of the 4 corner pixels are black and 2-60% of the pixels are black.
    Returns (image, masked: bool)."""
    import numpy as np
    from PIL import Image
    a = np.asarray(im.convert("RGB")).copy()
    h, w = a.shape[:2]
    dark = a.max(axis=2) <= BLACK
    corners = int(dark[0, 0]) + int(dark[0, w - 1]) + int(dark[h - 1, 0]) + int(dark[h - 1, w - 1])
    frac = float(dark.mean())
    if corners >= 3 and 0.02 <= frac <= 0.6:
        rest = a[~dark]
        a[dark] = rest.mean(axis=0).astype(np.uint8) if len(rest) else 128
        return Image.fromarray(a), True
    return im.convert("RGB"), False


def central_crop(im, frac=CROP):
    w, h = im.size
    if frac >= 1.0:
        return im
    dx, dy = int(round(w * (1 - frac) / 2)), int(round(h * (1 - frac) / 2))
    return im.crop((dx, dy, w - dx, h - dy))


def variants(im):
    from PIL import Image
    T = Image.Transpose
    out = []
    for flip in (False, True):
        b = im.transpose(T.FLIP_LEFT_RIGHT) if flip else im
        out += [b, b.transpose(T.ROTATE_90), b.transpose(T.ROTATE_180), b.transpose(T.ROTATE_270)]
    return out


def _hash(args):
    path, crop, mask = args
    import imagehash
    from PIL import Image
    with Image.open(path) as im:
        im.draft("RGB", (512, 512))
        im = im.convert("RGB")
        masked = False
        if mask:
            im, masked = mask_padding(im)
        im = central_crop(im, crop)
        return Path(path).name, [int(str(imagehash.phash(v, hash_size=8)), 16) for v in variants(im)], masked


def hash_all(paths, cache_path: Path | None, workers: int = 4, crop: float = CROP, mask: bool = True):
    """Returns ({name: [8 hashes]}, set(names whose padding was masked)). The cache is keyed on (crop, mask)."""
    params = {"crop": crop, "mask": mask, "v": 2}
    cache, masked = {}, set()
    if cache_path and cache_path.exists():
        raw = json.loads(cache_path.read_text())
        if raw.get("_params") == params:
            cache, masked = raw["hashes"], set(raw["masked"])
    todo = [(str(p), crop, mask) for p in paths if p.name not in cache]
    if todo and workers <= 1:
        results = map(_hash, todo)
        for n, hh, m in results:
            cache[n] = hh
            if m:
                masked.add(n)
    elif todo:
        with Pool(workers) as pool:
            for n, hh, m in pool.imap_unordered(_hash, todo, chunksize=16):
                cache[n] = hh
                if m:
                    masked.add(n)
    if todo and cache_path:
        cache_path.write_text(json.dumps({"_params": params, "hashes": cache, "masked": sorted(masked)}))
    return cache, masked


def dist_row(qv, ref):
    """qv: (8,) uint64 variants of one query; ref: (m,) uint64 -> (m,) min Hamming over the 8 variants."""
    import numpy as np
    x = qv[:, None] ^ ref[None, :]
    return pop8()[x.view(np.uint8).reshape(8, len(ref), 8)].sum(axis=2).min(axis=0)


def min_dist(qvars, ref):
    """qvars: (n,8) uint64; ref: (m,) uint64 -> (min dist (n,), argmin (n,)) over the 8 variants."""
    import numpy as np
    best = np.full(len(qvars), 99, dtype=np.int32)
    arg = np.zeros(len(qvars), dtype=np.int64)
    for i in range(len(qvars)):
        mn = dist_row(qvars[i], ref)
        j = int(mn.argmin())
        best[i], arg[i] = mn[j], j
    return best, arg


def source_names(files, sources_hint=None):
    names = {p.name for s in SPLITS for p in files[s]}
    if sources_hint:
        return list(sources_hint)
    return sorted({n.split("_")[0] if not n.startswith(("fresh_stale", "fridge_objects", "hien_fridge")) else
                   ("fresh_stale_fruits_veg" if n.startswith("fresh_stale") else "fridge_objects" if n.startswith("fridge_objects") else "hien_fridge")
                   for n in names})


def class_sets(root: Path, rows, class_regex=None):
    """One frozenset of class keys per row (name, split, src). From the YOLO label file; '?' when absent."""
    out = []
    cre = re.compile(class_regex) if class_regex and class_regex != "labels" else None
    for name, split, _ in rows:
        if cre:
            m = cre.search(name)
            out.append(frozenset([m.group(1) if m else "?"]))
            continue
        lf = root / "labels" / split / (Path(name).stem + ".txt")
        ids = {ln.split()[0] for ln in lf.read_text().splitlines() if ln.strip()} if lf.exists() else set()
        out.append(frozenset(ids or {"?"}))
    return out


def class_matrix(cls):
    """(n, K) uint8 multi-hot of the class sets, so 'shares a class' is a matrix product."""
    import numpy as np
    keys = sorted({k for c in cls for k in c})
    ix = {k: i for i, k in enumerate(keys)}
    m = np.zeros((len(cls), max(len(keys), 1)), dtype=np.uint8)
    for i, c in enumerate(cls):
        for k in c:
            m[i, ix[k]] = 1
    return m


def _pct(k, n):
    return round(100 * k / n, 2) if n else None


def compare_sets(V, ident, CM, q_idx, r_idx, T, rng):
    """For every query: nearest same-class reference vs nearest different-class reference (size-matched random subset
    of the different-class refs, plus the unmatched all-different-class minimum). Returns a report dict."""
    import numpy as np
    same_hit = diff_hit = diffall_hit = ident_hit = 0
    n_same = n_diff = 0
    ex = []
    for qi in q_idx:
        d = dist_row(V[qi], ident[r_idx])
        same = (CM[r_idx].astype(np.int32) @ CM[qi].astype(np.int32)) > 0
        if same.any():
            n_same += 1
            ds = d[same]
            k = int(ds.argmin())
            if ds[k] <= T:
                same_hit += 1
                if len(ex) < 8:
                    ex.append((int(qi), int(r_idx[np.where(same)[0][k]]), int(ds[k])))
            x = ident[qi] ^ ident[r_idx[same]]
            ident_hit += int(pop8()[x.view(np.uint8).reshape(-1, 8)].sum(axis=1).min() <= T)
        if (~same).any() and same.any():
            n_diff += 1
            dd = d[~same]
            diffall_hit += int(dd.min() <= T)
            m = int(same.sum())
            sub = rng.choice(len(dd), size=min(m, len(dd)), replace=False)
            diff_hit += int(dd[sub].min() <= T)
    out = {"queries_with_same_class_ref": n_same, "same_class_near_dup": same_hit, "same_class_pct": _pct(same_hit, n_same),
           "same_class_identity_only_pct": _pct(ident_hit, n_same),
           "diff_class_floor_matched_pct": _pct(diff_hit, n_diff), "diff_class_floor_all_pct": _pct(diffall_hit, n_diff),
           "queries_with_diff_class_ref": n_diff}
    if out["same_class_pct"] is not None and out["diff_class_floor_matched_pct"] is not None:
        out["excess_over_floor_points"] = round(out["same_class_pct"] - out["diff_class_floor_matched_pct"], 2)
    return out, ex


def check(root: Path, T=6, cache: Path | None = None, sources=None, comp_t=10, class_regex="labels", workers=4,
          crop=CROP, mask=True, seed=0):
    import numpy as np
    files = originals(root)
    allp = [p for s in SPLITS for p in files[s]]
    h, masked = hash_all(allp, cache, workers, crop, mask)
    srcs = source_names(files, sources)

    def src_of(n):
        for s in sorted(srcs, key=len, reverse=True):
            if n.startswith(s + "_") or n.startswith(s + "__"):
                return s
        return n.partition("_")[0]

    rows = [(p.name, s, src_of(p.name)) for s in SPLITS for p in files[s]]
    rep = {}
    for src in sorted({r[2] for r in rows}):
        rng = np.random.default_rng(seed)
        R = [r for r in rows if r[2] == src]
        V = np.array([h[r[0]] for r in R], dtype=np.uint64)             # (n,8)
        ident = V[:, 0]
        split = np.array([r[1] for r in R])
        CM = class_matrix(class_sets(root, R, class_regex))
        CM32 = CM.astype(np.int32)
        o = {"images": len(R), "by_split": {s: int((split == s).sum()) for s in SPLITS},
             "settings": {"T": T, "crop": crop, "mask_padding": mask, "same_class_only": True},
             "padding_masked_images": sum(1 for r in R if r[0] in masked)}
        for tag, q_idx, r_idx in (("heldout_vs_trainval", np.where(split == "heldout")[0], np.where(split != "heldout")[0]),
                                  ("val_vs_train", np.where(split == "val")[0], np.where(split == "train")[0])):
            if len(q_idx) and len(r_idx):
                rep_t, ex = compare_sets(V, ident, CM, q_idx, r_idx, T, rng)
                rep_t["n"] = int(len(q_idx))
                rep_t["example_same_class_pairs"] = [(R[a][0], R[b][0], d) for a, b, d in ex]
                o[tag] = rep_t
        # within-set: nearest OTHER same-class image, any split
        n = len(R)
        dup = np.zeros(n, dtype=bool)
        straddle = []
        for i in range(n):
            d = dist_row(V[i], ident).astype(np.int32)
            same = (CM32 @ CM32[i]) > 0
            d[~same] = 99
            d[i] = 99
            j = int(d.argmin())
            if d[j] <= T:
                dup[i] = True
                if split[i] != split[j]:
                    straddle.append((R[i][0], R[j][0], int(d[j])))
        o["within_set_same_class"] = {"images_with_variant_dup_le_T": int(dup.sum()), "pct": _pct(int(dup.sum()), n),
                                      "pairs_straddling_splits": len(straddle), "examples_straddling": straddle[:10]}
        if comp_t:
            parent = list(range(n))

            def f(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            for i in range(n):
                d = dist_row(V[i], ident)
                for j in np.where(d <= comp_t)[0]:
                    if j != i and (CM32[int(j)] @ CM32[i]) > 0:
                        parent[f(i)] = f(int(j))
            comp = defaultdict(set)
            for i in range(n):
                comp[f(i)].add(split[i])
            strad = {c for c, s in comp.items() if len(s) > 1}
            o["components_le_%d" % comp_t] = {"components": len(comp), "straddling_splits": len(strad),
                                              "images_in_straddling": int(sum(1 for i in range(n) if f(i) in strad))}
        rep[src] = o
    return rep


def summary_table(rep):
    lines = ["source | held-out n | same-class <=T | floor (size-matched) | floor (all) | excess pts | identity-only same-class | padding masked",
             "--- | --- | --- | --- | --- | --- | --- | ---"]
    for s, v in rep.items():
        t = v.get("heldout_vs_trainval")
        if t:
            lines.append(f"{s} | {t['n']} | {t['same_class_pct']}% | {t['diff_class_floor_matched_pct']}% | "
                         f"{t['diff_class_floor_all_pct']}% | {t.get('excess_over_floor_points')} | "
                         f"{t['same_class_identity_only_pct']}% | {v['padding_masked_images']}")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--json")
    ap.add_argument("--cache")
    ap.add_argument("-T", type=int, default=6)
    ap.add_argument("--component-t", type=int, default=10, help="0 to skip the specimen components")
    ap.add_argument("--class-regex", default="labels",
                    help="`labels` (default: class ids from the YOLO label files) or a regex with 1 group on the file name")
    ap.add_argument("--crop", type=float, default=CROP, help="hash only the central fraction of each image (default 0.8; 1 = whole image)")
    ap.add_argument("--no-mask", action="store_true", help="do not fill black rotation padding before hashing")
    ap.add_argument("--sources", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    r = check(Path(a.root), a.T, Path(a.cache) if a.cache else None, a.sources, a.component_t, a.class_regex, a.workers,
              a.crop, not a.no_mask)
    print(json.dumps(r, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2))
    print(summary_table(r))
    print("VARIANT-AWARE report only (not a gate; the gate is identity pHash <= 6, <= 1% per source in leakage_check.py).")
    sys.exit(0)
