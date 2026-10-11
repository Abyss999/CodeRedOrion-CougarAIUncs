"""Specimen grouping for datasets that photograph the same produce item at several shelf-life stages
and ship their own augmentations (AgriFreshNET). Conservative default: assume the same specimens
appear across Fresh / Semi fresh / Rotten, and that an augmented copy may be flipped or rotated.

Method (specimens per produce class, ACROSS all stages):
  1. pHash-64 of each image under all 8 dihedral variants (identity, 3 rotations, and the same four
     after a horizontal flip). The variant transform is applied to the 32x32 grey thumbnail that the
     DCT hash reads (same pipeline as ml/yolo/dedup.phash64), so it costs one image decode.
  2. Variant-aware distance d(a, b) = min over the 8 variants v of hamming(H_a[identity], H_b[v]).
     The dihedral group is closed under inversion, so this is symmetric up to resampling noise.
  3. Connected components of the graph "d <= threshold" (union-find). Each component is ONE split unit.
  4. Capture sessions (dataset-wide, all classes): shots <= 300 s apart (milliseconds in the name allowed, no
     span cap) form a session. ml/eval's leakage check (ML-21) requires 0 held-out images within 300 s of a
     train/val image of the same source, whatever the class, and prepare_dataset cannot read AgriFreshNET's
     `HHMMSSmmm` times, so the sessions are built here. Units = specimen components UNION sessions when the
     largest unit stays <= 30% of the dataset and of every class; otherwise (specimens chain sessions across days
     into one giant unit) timestamped images use their session (`sess_<id>`) and only untimestamped ones
     (WhatsApp `IMG-YYYYMMDD-WA`, `Banana (3).jpeg`) use their specimen component.
  5. Giant-component guard: if the largest component holds more than MAX_FRAC of the class, the
     threshold is tightened (10 -> 8 -> 6 -> 4) for that class until it does not (or 4 is reached);
     the chosen threshold and the largest fraction are reported.

The staged group name is `<canonical>__spec_<8 hex>` (or `sess_<8 hex>`); prepare_dataset keeps
everything that shares the text before '.rf.' in one split, so no prepare_dataset change is needed.
"""
from __future__ import annotations
import hashlib
import re
from datetime import datetime
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config  # noqa: F401  (puts ml/yolo on sys.path)
import dedup  # noqa: E402

SESSION_GAP_S = 300.0
# Capture time in a file name, milliseconds allowed (IMG_20251102_075610660). ml/yolo/prepare_dataset.parse_capture_time
# does not read 9-digit times, so the sessions are built here instead (same pattern ml/eval/leakage_check.py uses).
_TS = re.compile(r"(?<!\d)(20\d{6})[_-]?([0-2]\d[0-5]\d[0-5]\d)(?:\d{3})?(?!\d)")
_EPOCH_MS = re.compile(r"(?<!\d)(1[4-9]\d{11})(?!\d)")
THRESHOLDS = (10, 8, 6, 4)
MAX_FRAC = 0.30
NEAR_DUP = 6
_POP = dedup._POP


def _bits(blk: np.ndarray) -> int:
    med = np.median(blk.ravel()[1:])
    return dedup._pack(blk > med)


def variant_hashes(img: Image.Image) -> list[int]:
    """pHash-64 under the 8 dihedral variants; index 0 is the plain image (== dedup.phash64)."""
    a = dedup._grey(img, (dedup._N, dedup._N))
    out = []
    for flip in (False, True):
        b = a[:, ::-1] if flip else a
        for k in range(4):
            r = np.rot90(b, k)
            out.append(_bits((dedup._DCT @ r @ dedup._DCT.T)[:8, :8]))
    return out


def capture_seconds(name: str) -> float | None:
    m = _EPOCH_MS.search(name)
    if m:
        return int(m.group(1)) / 1000.0
    m = _TS.search(name)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
        except ValueError:
            return None
    return None


def sessions(times: list[float | None], gap: float = SESSION_GAP_S) -> list[int]:
    """Session index per image (-1 = no timestamp): shots <= gap seconds apart are chained, no span cap."""
    order = sorted((t, i) for i, t in enumerate(times) if t is not None)
    out = [-1] * len(times)
    sid, prev = -1, None
    for t, i in order:
        if prev is None or t - prev > gap:
            sid += 1
        out[i], prev = sid, t
    return out


def hash_file(path: Path) -> list[int]:
    with Image.open(path) as im:
        return variant_hashes(im)


def min_dist_matrix(H: np.ndarray, rows: slice) -> np.ndarray:
    """H: (n, 8) uint64. -> (len(rows), n) minimum Hamming distance, identity of rows vs every variant."""
    n = H.shape[0]
    a = H[rows, 0]
    best = np.full((a.shape[0], n), 64, dtype=np.int16)
    for v in range(8):
        x = a[:, None] ^ H[None, :, v]
        d = _POP[x.view(np.uint8).reshape(x.shape[0], n, 8)].sum(axis=2)
        best = np.minimum(best, d)
    return best


def _components(H: np.ndarray, thresh: int, chunk: int = 256) -> np.ndarray:
    n = H.shape[0]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for s in range(0, n, chunk):
        d = min_dist_matrix(H, slice(s, s + chunk))
        ii, jj = np.nonzero(d <= thresh)
        for i, j in zip(ii, jj):
            i += s
            if i != j:
                ri, rj = find(int(i)), find(int(j))
                if ri != rj:
                    parent[ri] = rj
    return np.array([find(i) for i in range(n)])


def near_dup_rate(H: np.ndarray, labels: list[str] | None = None, thresh: int = NEAR_DUP, chunk: int = 256) -> dict:
    """Share of images with another image (variant-aware d <= thresh) in the whole set, and, if `labels`
    (e.g. folder names) is given, within the same label."""
    n = H.shape[0]
    any_nd = np.zeros(n, bool)
    same_nd = np.zeros(n, bool)
    lab = np.array(labels) if labels is not None else None
    for s in range(0, n, chunk):
        d = min_dist_matrix(H, slice(s, s + chunk))
        idx = np.arange(s, min(s + chunk, n))
        d[np.arange(len(idx)), idx] = 99
        hit = d <= thresh
        any_nd[idx] = hit.any(axis=1)
        if lab is not None:
            same_nd[idx] = (hit & (lab[idx][:, None] == lab[None, :])).any(axis=1)
    out = {"n": n, "near_dup_in_class": int(any_nd.sum()), "rate_in_class": round(float(any_nd.mean()), 4) if n else 0.0}
    if lab is not None:
        out.update(near_dup_in_folder=int(same_nd.sum()), rate_in_folder=round(float(same_nd.mean()), 4) if n else 0.0)
    return out


def group_class(H: np.ndarray, max_frac: float = MAX_FRAC, thresholds=THRESHOLDS) -> tuple[np.ndarray, dict]:
    """-> (component label per row, stats) using the loosest threshold whose largest component <= max_frac."""
    n = H.shape[0]
    tried = []
    for t in thresholds:
        comp = _components(H, t)
        sizes = Counter(comp.tolist())
        top = max(sizes.values())
        tried.append((t, round(top / n, 4)))
        if top <= max_frac * n or t == thresholds[-1]:
            ss = sorted(sizes.values(), reverse=True)
            return comp, {"images": n, "threshold": t, "components": len(sizes), "singletons": sum(1 for v in ss if v == 1),
                          "largest": ss[0], "largest_frac": round(ss[0] / n, 4), "top5": ss[:5],
                          "tightened": t != thresholds[0], "tried": tried,
                          "over_cap": ss[0] > max_frac * n}
    raise AssertionError


def assign(items: list[tuple[Path, str, str, str]], cache: dict | None = None) -> tuple[dict[str, str], dict]:
    """items: (file, sha1, canonical, folder). Returns ({sha1: group name}, report).
    Specimen components are per class (across stages); capture sessions are DATASET-wide (ml/eval's leakage check
    compares timestamps across all classes of a source). Group names: `<class>__spec_<8 hex>` for a specimen
    component, `sess_<8 hex>` for a capture session (class-free, so one session is one unit)."""
    cache = cache if cache is not None else {}
    by_cls: dict[str, list] = defaultdict(list)
    for it in items:
        by_cls[it[2]].append(it)
    report: dict = {"method": f"8-variant pHash min-distance, connected components, <= {THRESHOLDS[0]} "
                              f"(tightened per class if the largest component > {int(MAX_FRAC*100)}%), "
                              f"+ {int(SESSION_GAP_S)} s capture sessions over the whole dataset",
                    "classes": {}}
    rows = []                     # (sha, class, specimen key, capture seconds)
    for cls, its in sorted(by_cls.items()):
        ok = []
        for t in sorted(its, key=lambda t: t[1]):
            try:
                cache[t[1]] = cache.get(t[1]) or hash_file(t[0])
                ok.append(t)
            except (OSError, ValueError, Image.DecompressionBombError):  # unreadable: staging reports it as bad
                report.setdefault("unhashable", []).append(str(t[0]))
        if not ok:
            continue
        H = np.array([cache[t[1]] for t in ok], dtype=np.uint64)
        comp, st = group_class(H)
        st["near_dup_le6"] = near_dup_rate(H, [t[3] for t in ok])
        report["classes"][cls] = st
        for k, t in zip(comp.tolist(), ok):
            rows.append((t[1], cls, (cls, k), capture_seconds(t[0].name)))
    n = len(rows)
    sess = sessions([r[3] for r in rows])
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    first: dict = {}
    for i, r in enumerate(rows):
        parent[find(i)] = find(first.setdefault(r[2], i))
    first_s: dict = {}
    for i, sid in enumerate(sess):
        if sid >= 0:
            parent[find(i)] = find(first_s.setdefault(sid, i))
    union = Counter(find(i) for i in range(n))
    top = max(union.values(), default=0)
    report["sessions"] = {"timestamped": sum(1 for x in sess if x >= 0), "sessions": len(set(x for x in sess if x >= 0)),
                          "largest": max(Counter(x for x in sess if x >= 0).values(), default=0)}
    report["union_specimen_and_session"] = {"components": len(union), "largest": top,
                                            "largest_frac": round(top / n, 4) if n else 0.0}
    per_class_union: dict[str, float] = {}
    for cls in report["classes"]:
        idx = [i for i, r in enumerate(rows) if r[1] == cls]
        c = Counter(find(i) for i in idx)
        per_class_union[cls] = round(max(c.values()) / len(idx), 4)
    for cls, v in per_class_union.items():
        report["classes"][cls]["union_largest_frac_in_class"] = v
    use_union = bool(n) and top <= MAX_FRAC * n and max(per_class_union.values()) <= MAX_FRAC
    report["unit"] = ("specimen+session union" if use_union else
                      "timestamped -> capture session; untimestamped -> specimen component "
                      "(the union chained specimens across days into one giant unit)")
    label = []
    for i, r in enumerate(rows):
        if use_union:
            label.append(("spec", find(i)))
        elif sess[i] >= 0:
            label.append(("sess", sess[i]))
        else:
            label.append(("spec", r[2]))
    rep: dict = {}
    groups: dict[str, str] = {}
    for lb, r in zip(label, rows):
        rep.setdefault(lb, r[0])      # rows are class- then sha-sorted: first member is deterministic
    for lb, r in zip(label, rows):
        h = hashlib.sha1((lb[0] + rep[lb]).encode()).hexdigest()[:8]
        groups[r[0]] = f"sess_{h}" if lb[0] == "sess" else f"{r[1]}__spec_{h}"
    sizes = Counter(label)
    report["final_units"] = len(sizes)
    report["final_largest"] = max(sizes.values(), default=0)
    report["final_largest_frac"] = round(max(sizes.values(), default=0) / n, 4) if n else 0.0
    return groups, report


def round_robin(items: list[tuple[str, str]], cap: int, seed: int = 42) -> list[str]:
    """items: (sha1, unit). Pick `cap` shas, one per unit per round, units and members in a seeded-hash order, so
    the choice is reproducible and spread over all units (never 'the first N')."""
    if len(items) <= cap:
        return [sha for sha, _ in items]
    h = lambda t: hashlib.sha1(f"{seed}:{t}".encode()).hexdigest()  # noqa: E731
    units: dict[str, list[str]] = defaultdict(list)
    for sha, u in items:
        units[u].append(sha)
    order = sorted(units, key=h)
    for u in order:
        units[u].sort(key=h)
    out: list[str] = []
    r = 0
    while len(out) < cap:
        progressed = False
        for u in order:
            if r < len(units[u]):
                out.append(units[u][r])
                progressed = True
                if len(out) == cap:
                    break
        if not progressed:
            break
        r += 1
    return out
