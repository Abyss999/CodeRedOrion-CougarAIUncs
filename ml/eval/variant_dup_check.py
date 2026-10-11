"""Variant-aware near-duplicate check (ML-33 follow-up; orchestrator ruling on augmented sets).

pHash-64 is not flip/rotation invariant, so an augmented set (AgriFreshNET ships flips/rotations/crops of
one photo) can leak through the plain pHash gate. Here every image is hashed in its 8 dihedral variants
(identity, hflip, rot90/180/270, each with and without a flip) and the MINIMUM Hamming distance to the
reference set is used (querying 8 variants against identity hashes of the reference is equivalent to all
64 pairings because the dihedral group is closed under inverse).

Reports, per source:
  * held-out -> train+val near-duplicates (min variant distance <= T, default 6) and the rate;
  * val -> train likewise;
  * within-set augmentation duplicate rate (every original whose nearest OTHER image, any split, is <= T);
  * how many of those pairs straddle splits;
and optionally specimen components (connected components at --component-t, default 10, per source+class
key given by --class-regex on the file name) and how many straddle splits.

  python ml/eval/variant_dup_check.py /path/to/fwr_data [--json out.json] [--cache hashes.json] [-T 6]
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


def variants(im):
    from PIL import Image
    T = Image.Transpose
    out = []
    for flip in (False, True):
        b = im.transpose(T.FLIP_LEFT_RIGHT) if flip else im
        out += [b, b.transpose(T.ROTATE_90), b.transpose(T.ROTATE_180), b.transpose(T.ROTATE_270)]
    return out


def _hash(path: str):
    import imagehash
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        return Path(path).name, [int(str(imagehash.phash(v, hash_size=8)), 16) for v in variants(im)]


def hash_all(paths, cache_path: Path | None, workers: int = 4):
    cache = json.loads(cache_path.read_text()) if cache_path and cache_path.exists() else {}
    todo = [str(p) for p in paths if p.name not in cache]
    if todo and workers <= 1:
        for t in todo:
            n, hh = _hash(t)
            cache[n] = hh
    elif todo:
        with Pool(workers) as pool:
            for n, hh in pool.imap_unordered(_hash, todo, chunksize=16):
                cache[n] = hh
    if todo:
        if cache_path:
            cache_path.write_text(json.dumps(cache))
    return cache


def min_dist(qvars, ref):
    """qvars: (n,8) uint64; ref: (m,) uint64 -> (min dist (n,), argmin (n,)) over the 8 variants."""
    import numpy as np
    pop = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    best = np.full(len(qvars), 99, dtype=np.int32)
    arg = np.zeros(len(qvars), dtype=np.int64)
    for i in range(len(qvars)):
        x = qvars[i][:, None] ^ ref[None, :]                       # (8, m)
        d = pop[x.view(np.uint8).reshape(8, len(ref), 8)].sum(axis=2)
        mn = d.min(axis=0)
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


def check(root: Path, T=6, cache: Path | None = None, sources=None, comp_t=10, class_regex=None, workers=4):
    import numpy as np
    files = originals(root)
    allp = [p for s in SPLITS for p in files[s]]
    h = hash_all(allp, cache, workers)
    srcs = source_names(files, sources)

    def src_of(n):
        for s in sorted(srcs, key=len, reverse=True):
            if n.startswith(s + "_") or n.startswith(s + "__"):
                return s
        return n.partition("_")[0]

    rows = [(p.name, s, src_of(p.name)) for s in SPLITS for p in files[s]]
    rep = {}
    for src in sorted({r[2] for r in rows}):
        R = [r for r in rows if r[2] == src]
        V = np.array([h[r[0]] for r in R], dtype=np.uint64)             # (n,8)
        ident = V[:, 0]
        split = np.array([r[1] for r in R])
        o = {"images": len(R), "by_split": {s: int((split == s).sum()) for s in SPLITS}}
        trv = np.where(split != "heldout")[0]
        for tag, q_idx, r_idx in (("heldout_vs_trainval", np.where(split == "heldout")[0], trv),
                                  ("val_vs_train", np.where(split == "val")[0], np.where(split == "train")[0])):
            if len(q_idx) and len(r_idx):
                d, a = min_dist(V[q_idx], ident[r_idx])
                bad = d <= T
                # plain (identity-only) rate for comparison
                d0, _ = min_dist(V[q_idx][:, :1].repeat(8, axis=1), ident[r_idx])
                o[tag] = {"n": int(len(q_idx)), "variant_near_dup": int(bad.sum()), "variant_pct": round(100 * bad.mean(), 2),
                          "identity_only_near_dup": int((d0 <= T).sum()), "identity_only_pct": round(100 * (d0 <= T).mean(), 2),
                          "example_pairs": [(R[q_idx[i]][0], R[r_idx[a[i]]][0], int(d[i])) for i in np.where(bad)[0][:8]]}
        # within-set: nearest other image, any split, variant-aware
        n = len(R)
        nn = np.full(n, 99, dtype=np.int32); nj = np.zeros(n, dtype=np.int64)
        for i in range(n):
            x = V[i][:, None] ^ ident[None, :]
            pop = np.array([bin(k).count("1") for k in range(256)], dtype=np.uint8)
            d = pop[x.view(np.uint8).reshape(8, n, 8)].sum(axis=2).min(axis=0)
            d[i] = 99
            j = int(d.argmin()); nn[i], nj[i] = d[j], j
        dup = nn <= T
        straddle = [(R[i][0], R[nj[i]][0], int(nn[i])) for i in np.where(dup)[0] if split[i] != split[nj[i]]]
        o["within_set"] = {"images_with_variant_dup_le_T": int(dup.sum()), "pct": round(100 * dup.mean(), 2),
                           "pairs_straddling_splits": len(straddle), "examples_straddling": straddle[:10]}
        o["criterion_variant_phash_le_1pct_heldout"] = bool(o.get("heldout_vs_trainval", {}).get("variant_pct", 0.0) <= 1.0)
        # specimen components (union-find, variant-aware) within source+class key
        if class_regex:
            cre = re.compile(class_regex)
            key = [(cre.search(r[0]).group(1) if cre.search(r[0]) else "?") for r in R]
            parent = list(range(n))
            def f(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]; x = parent[x]
                return x
            pop = np.array([bin(k).count("1") for k in range(256)], dtype=np.uint8)
            for i in range(n):
                x = V[i][:, None] ^ ident[None, :]
                d = pop[x.view(np.uint8).reshape(8, n, 8)].sum(axis=2).min(axis=0)
                for j in np.where(d <= comp_t)[0]:
                    if j != i and key[j] == key[i]:
                        parent[f(i)] = f(int(j))
            comp = defaultdict(set)
            for i in range(n):
                comp[f(i)].add(split[i])
            strad = [c for c, s in comp.items() if len(s) > 1]
            o["components_le_%d" % comp_t] = {"components": len(comp), "straddling_splits": len(strad),
                                              "images_in_straddling": int(sum(1 for i in range(n) if f(i) in set(strad)))}
        rep[src] = o
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    ap.add_argument("--cache")
    ap.add_argument("-T", type=int, default=6)
    ap.add_argument("--component-t", type=int, default=10)
    ap.add_argument("--class-regex", help="regex with 1 group on the file name giving the class key (enables component check)")
    ap.add_argument("--sources", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    r = check(Path(a.root), a.T, Path(a.cache) if a.cache else None, a.sources, a.component_t, a.class_regex, a.workers)
    print(json.dumps(r, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2))
    ok = all(v["criterion_variant_phash_le_1pct_heldout"] for v in r.values())
    print("VARIANT-AWARE pHash gate (held-out->train+val <= 1%):", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
