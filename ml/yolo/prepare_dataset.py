#!/usr/bin/env python
"""Merge public datasets into ONE YOLO dataset (detector = food NAME classes) plus a freshness
sidecar, a crop set for the fresh/semi_fresh/spoiled classifier, and a held-out split with lighting tags.

Sources are listed in a JSON file (see sources.example.json). Two source kinds:
  "yolo"    - a YOLO/Roboflow export dir: data.yaml + {train,valid,test}/{images,labels}
  "folders" - classification layout: <root>/**/<class_dir>/*.jpg ; each image becomes one
              whole-frame box (single-item photos). Class dir names like "rotten_apple" /
              "FreshBanana" are split into (name, freshness) by taxonomy.split_freshness.

Usage:  python prepare_dataset.py --sources sources.json --out /content/fwr_data
Needs only Pillow, numpy, pyyaml (pyyaml is optional: a tiny fallback parser is used otherwise).
"""
from __future__ import annotations
import argparse, calendar, csv, hashlib, json, random, re, shutil, sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dedup as D  # noqa: E402
import lighting as L  # noqa: E402
import taxonomy as T  # noqa: E402

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLIT_DIRS = ("train", "valid", "val", "test")


def load_names(data_yaml: Path) -> list[str]:
    try:
        import yaml
        names = yaml.safe_load(data_yaml.read_text())["names"]
        return [names[k] for k in sorted(names)] if isinstance(names, dict) else list(names)
    except ImportError:  # fallback: handles `names: [a, b]` and `names:\n- a`
        txt = data_yaml.read_text()
        m = re.search(r"^names:\s*\[(.*?)\]", txt, re.M | re.S)
        if m:
            return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
        return [x.strip().strip("'\"") for x in re.findall(r"^\s*-\s*(.+)$", txt.split("names:")[1], re.M)]


def resolve(raw: str, class_map: dict) -> tuple[str | None, str | None]:
    """source label -> (canonical name | None, freshness | None). class_map overrides win."""
    if raw in class_map:
        v = class_map[raw]
        if v is None:
            return None, None
        name, fr = (v.split(":") + [None])[:2] if ":" in v else (v, None)
        n, f2 = T.split_freshness(name)
        return T.canonical_name(n), fr or f2
    n, fr = T.split_freshness(raw)
    return T.canonical_name(n), fr


_EXT_TAIL = re.compile(r"(?:[._](?:jpe?g|png|bmp|webp))+$", re.I)
_AUG_TAIL = re.compile(r"(?:\.(?:jpe?g|png))?_\d+_\d+$", re.I)   # Kaggle augmentation suffix: name.jpg_0_1039


def base_stem(path: Path) -> str:
    """Name of the ORIGINAL photo: strips Roboflow '.rf.<hash>', the Kaggle '_0_1039' augmentation tail,
    the staged-name prefix '<cls>__' and a leading 'Copy of '."""
    st = path.stem
    st = st.split(".rf.")[0]
    st = re.sub(r"_rf_[0-9a-f]{32}(?:_[0-9a-f]{6})?$", "", st)          # already-sanitised staged names
    st = st.split("__")[-1]
    st = _AUG_PREFIX.sub("", re.sub(r"^Copy of ", "", st))
    st = _AUG_TAIL.sub("", st)
    return st


def series_stem(path: Path) -> str:
    """Numbered series key: 'Defected_begun_3_jpg' and 'Defected_begun_4_jpg' -> 'Defected_begun'."""
    st = _EXT_TAIL.sub("", base_stem(path))
    key = re.sub(r"[\d_\-. ]+$", "", st)
    return key or st


def group_key(src: str, path: Path, series: bool = False) -> str:
    """Pre-session group. series=True (per-source option "series_grouping": true, for sources whose files are numbered
    camera series such as Defected_begun_3/_4 or ID11_apple_001) groups the whole numbered series; otherwise one group per
    ORIGINAL photo (the stem before '.rf.', so Roboflow augmentations stay together but different photos are independent;
    the class prefix of staged names is kept). Capture sessions (timestamps) and pHash merging apply on top."""
    if series:
        return f"{src}/{series_stem(path)}"
    return f"{src}/{_AUG_PREFIX.sub('', path.stem.split('.rf.')[0])}"


# Capture-time patterns found in filenames. SEARCHED (not anchored) so staged names such as
# '<cls>__IMG_20250101_123456.rf.<sha>' work. Different 'kinds' are different clocks.
_RX_COMPACT = re.compile(r"(?<!\d)((?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))[_-]?([01]\d|2[0-3])([0-5]\d)([0-5]\d)(?:\d{3})?(?!\d)")   # optional ms: IMG_20251102_075610660
_RX_EPOCH_MS = re.compile(r"(?<!\d)(1[4-9]\d{11}|20\d{11})(?!\d)")      # 2014..2033 in ms
# 'Screen Shot 2018-06-08 at 4.59.36 PM', 'WhatsApp Image 2020-11-07 at 11.35.36 PM' (also sanitised with '_')
_RX_SCREENSHOT = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})[ _]at[ _](\d{1,2})[._:](\d{2})[._:](\d{2})(?:[ _]*([AP]M))?", re.I)
_AUG_PREFIX = re.compile(r"^(?:rotated_by_-?\d+|saltandpepper|translation|(?:vertical|horizontal)_flip|gaussian_noise|blur)_")


def parse_capture_time(path: Path) -> tuple[str, float] | None:
    """-> (clock kind, seconds) from the filename, or None."""
    name = path.name
    try:
        m = _RX_SCREENSHOT.search(name)
        if m:
            y, mo, d, h, mi, se, ap = m.groups()
            h = int(h) % 12 + (12 if ap and ap.upper() == "PM" else 0) if ap else int(h)
            return "screenshot", float(calendar.timegm(datetime(int(y), int(mo), int(d), h, int(mi), int(se)).timetuple()))
        m = _RX_COMPACT.search(name)
        if m:
            dt = datetime.strptime("".join(m.groups()[:1]) + "".join(m.groups()[1:]), "%Y%m%d%H%M%S")
            return "compact", float(calendar.timegm(dt.timetuple()))
        m = _RX_EPOCH_MS.search(name)
        if m:
            return "epoch_ms", int(m.group(1)) / 1000.0
    except ValueError:
        return None
    return None


def assign_sessions(recs: list[dict], gap: float) -> dict:
    """Timestamped photos of one source and clock kind: any two shot <= `gap` seconds apart (chained) share a
    session group. NO span cap: a cap re-introduced leakage (ML-21). Untimestamped photos keep their series group.
    gap <= 0 disables sessions."""
    by_clock = defaultdict(list)
    n_ts = 0
    if gap > 0:
        for r in recs:
            t = parse_capture_time(r["path"])
            r["ts"] = t
            if t:
                by_clock[(r["src"], t[0])].append((t[1], r))
                n_ts += 1
    for (src, kind), items in by_clock.items():
        items.sort(key=lambda x: (x[0], str(x[1]["path"])))
        sid, prev = None, None
        for t, r in items:
            if prev is None or t - prev > gap:
                sid = f"{src}/session/{kind}/{int(t)}"
            r["group"], prev = sid, t
    sizes = Counter(r["group"] for r in recs)
    sess = Counter(r["group"] for r in recs if "/session/" in r["group"])
    return {"split_grouping": "session" if gap > 0 else "series", "session_gap_s": gap,
            "images_with_timestamp": n_ts, "images_without_timestamp": len(recs) - n_ts,
            "session_groups": len(sess), "largest_session_images": max(sess.values(), default=0)}


def merge_near_duplicates(recs: list[dict], thresh: int, max_unit: int) -> tuple[dict, set]:
    """Union capture-groups whose images are pHash-64 near-duplicates (Hamming <= thresh, any source) so that
    near-duplicates cannot straddle splits. Look-alike clusters can chain into huge components (white-background
    fruit photos), which would make whole classes unmeasurable; a component of more than `max_unit` images is NOT
    merged: its capture groups stay separate, and after the split the few images that have a near-duplicate in
    another split are dropped from the held-out/val side (drop_cross_split_near_duplicates). Needs r['phash'].
    Returns (report, forced_train_groups) (forced set is empty; kept for API compatibility)."""
    from dedup import near_pairs
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    pairs = 0
    for r in recs:
        r["group0"] = r["group"]
    for i, j in near_pairs([r["phash"] for r in recs], thresh):
        pairs += 1
        ra, rb = find(recs[i]["group"]), find(recs[j]["group"])
        if ra != rb:
            parent[ra] = rb
    before = len({r["group"] for r in recs})
    comp = Counter(find(r["group"]) for r in recs)
    over = {c for c, n in comp.items() if n > max_unit}
    by_src_over = Counter()
    for r in recs:
        c = find(r["group"])
        if c in over:
            by_src_over[r["src"]] += 1          # keep the capture group as its own unit
            r["oversized"] = True
        else:
            r["group"] = c
    sizes = Counter(r["group"] for r in recs)
    return ({"phash_threshold": thresh, "near_pairs": pairs, "groups_before": before, "groups_after": len(sizes),
             "max_unit_images": max_unit, "largest_group_images": max(sizes.values(), default=0),
             "oversized_components_not_merged": len(over),
             "images_in_oversized_components_by_source": dict(by_src_over)}, set())


def drop_cross_split_near_duplicates(recs: list[dict], thresh: int) -> dict:
    """After the split: an image in held-out/val that has a pHash near-duplicate (Hamming <= thresh) in a DIFFERENT
    split is dropped from the dataset (held-out vs val: the val image goes; vs train: the held-out/val image goes).
    Dropped, not moved to train, so that capture-session neighbours cannot leak either. Sets r['dropped']."""
    from dedup import near_pairs
    dropped: Counter = Counter()
    for i, j in near_pairs([r["phash"] for r in recs], thresh):
        si, sj = recs[i]["split"], recs[j]["split"]
        if si == sj:
            continue
        k = i if si != "train" and (sj == "train" or si == "val") else j
        if not recs[k].get("dropped"):
            recs[k]["dropped"] = True
            dropped[f"{recs[k]['src']}:{recs[k]['split']}"] += 1
    return {"phash_threshold": thresh, "dropped_images": dict(dropped), "dropped_total": sum(dropped.values())}


def purge_near_duplicates(recs: list[dict], thresh: int = 6) -> dict:
    """After the group split: any held-out/val image that has a pHash-64 near-duplicate (Hamming <= thresh, any
    source) in ANOTHER split is moved to train (held-out vs val clashes: val moves). Repeats to a fixpoint, so no
    near-duplicate pair straddles splits (structural ML-21 guarantee for untimestamped images / numbered series).
    Merging groups instead chained 4,900 look-alike white-background photos into one group, so we purge. Needs
    r['phash'] and r['split']."""
    from dedup import near_pairs
    pairs = list(near_pairs([r["phash"] for r in recs], thresh))
    moved: Counter = Counter()
    changed = True
    while changed:
        changed = False
        for i, j in pairs:
            si, sj = recs[i]["split"], recs[j]["split"]
            if si == sj:
                continue
            if "train" in (si, sj):
                k = i if si != "train" else j
            else:                                   # heldout vs val
                k = i if si == "val" else j
            moved[f"{recs[k]['src']}:{recs[k]['split']}->train"] += 1
            recs[k]["split"] = "train"
            changed = True
    return {"phash_threshold": thresh, "near_pairs": len(pairs), "moved_to_train": dict(moved),
            "moved_total": sum(moved.values())}


def iter_yolo(src: dict):
    root = Path(src["root"])
    names = load_names(next(root.rglob("data.yaml")))
    for sd in SPLIT_DIRS:
        idir, ldir = root / sd / "images", root / sd / "labels"
        if not idir.is_dir():
            continue
        for ip in sorted(idir.iterdir()):
            if ip.suffix.lower() not in IMG_EXT:
                continue
            lp = ldir / (ip.stem + ".txt")
            boxes = []
            if lp.exists():
                for ln in lp.read_text().splitlines():
                    p = ln.split()
                    if len(p) >= 5 and int(p[0]) < len(names):
                        boxes.append((names[int(p[0])], *map(float, p[1:5])))
            yield ip, boxes


def iter_folders(src: dict):
    root = Path(src["root"])
    for ip in sorted(root.rglob("*")):
        if ip.suffix.lower() in IMG_EXT:
            yield ip, [(ip.parent.name, 0.5, 0.5, 1.0, 1.0)]


def collect(sources: list[dict], skipped: Counter, drops: Counter | None = None, max_per_class: int | None = None,
            seed: int = 42):
    drops = drops if drops is not None else Counter()
    recs = []
    for src in sources:
        if src.get("pending") or not Path(src["root"]).is_dir():
            print(f"[prepare] skipping source {src['name']!r}: root missing or marked pending ({src['root']})",
                  file=sys.stderr)
            skipped[f"{src['name']}:<source skipped, root missing>"] += 1
            continue
        it = iter_yolo(src) if src["kind"] == "yolo" else iter_folders(src)
        cmap = src.get("class_map", {})
        assumed = src.get("freshness_default")  # e.g. "fresh" for fridge sets without freshness info
        # labels we do not model but which are real objects: drop the WHOLE image if one is present,
        # so they are never left unlabeled (an unlabeled object trains as background).
        drop_img = set(src.get("drop_image_if_label", []))
        srecs = []
        for ip, boxes in it:
            if drop_img and any(b[0] in drop_img for b in boxes):
                skipped[f"{src['name']}:<image dropped, contains unmodelled object>"] += 1
                mixed = any(resolve(b[0], cmap)[0] for b in boxes)
                drops[f"{src['name']}:" + ("mixed_with_unmodelled_object" if mixed else "only_unmodelled_objects")] += 1
                continue
            out = []
            for raw, xc, yc, w, h in boxes:
                name, fr = resolve(raw, cmap)
                if name is None:
                    skipped[f"{src['name']}:{raw}"] += 1
                    continue
                known = fr is not None
                out.append(dict(name=name, freshness=fr or assumed or "fresh", known=known,
                                box=(xc, yc, w, h)))
            if out:
                srecs.append(dict(src=src["name"], path=ip, boxes=out, group=group_key(src["name"], ip, bool(src.get("series_grouping")))))
            elif not boxes:
                drops[f"{src['name']}:empty_label_file"] += 1
            else:
                drops[f"{src['name']}:all_boxes_unmapped"] += 1   # e.g. gourd-only, 'others'-only
        cap = max_per_class if max_per_class is not None else src.get("max_per_class")
        if cap and src["kind"] == "folders":
            # whole-image folder sources are huge and single-item: cap images per class x freshness, picked by
            # a deterministic hash so the choice is reproducible and spread over the source.
            byc = defaultdict(list)
            for r in srecs:
                byc[(r["boxes"][0]["name"], r["boxes"][0]["freshness"])].append(r)
            srecs = []
            for k, lst in sorted(byc.items()):
                lst.sort(key=lambda r: hashlib.sha1(f"{seed}:{r['path']}".encode()).hexdigest())
                srecs += lst[:cap]
                if len(lst) > cap:
                    drops[f"{src['name']}:capped_max_per_class({k[0]}/{k[1]})"] += len(lst) - cap
            srecs.sort(key=lambda r: str(r["path"]))
        recs.extend(srecs)
    return recs


def group_hash(group: str, seed: int) -> float:
    return int(hashlib.sha1(f"{seed}:{group}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


MIN_CELL_IMAGES = 10      # a class x freshness cell with >= this many images must appear in held-out (and val)


def _cells(r: dict) -> Counter:
    c = Counter(f"{b['name']}/{b['freshness']}" for b in r["boxes"])
    c[f"src:{r['src']}"] += 1
    c["__images__"] += 1
    return c


def assign_splits(recs: list[dict], heldout: float, val: float, seed: int,
                  forced_train: set = frozenset(), min_session_images: int = 10) -> tuple[dict, dict]:
    """group -> split, stratified on class x freshness (+ source + image count) by greedy balancing.
    Groups (sessions / series / near-duplicate clusters) are indivisible. Largest weighted groups are placed first,
    each into the split that minimises the squared relative deficit of the cells it contains; then a repair pass
    moves the smallest group that holds a missing cell into held-out / val. Returns (split_of, info)."""
    frac = {"heldout": heldout, "val": val, "train": 1.0 - heldout - val}
    gcells: dict = defaultdict(Counter)
    for r in recs:
        gcells[r["group"]].update(_cells(r))
    total = Counter()
    for c in gcells.values():
        total.update(c)
    bad_pool = {r["group"] for r in recs if r.get("oversized")}
    # poolable = a WHOLE group that is itself small (< min_session_images images in total: a web photo, or a complete
    # one-shot session), and not part of a pHash-chained component. A few images of a cell inside a LARGE session are
    # fragments of that session and are never pooled.
    elig = {g: (gcells[g]["__images__"] < min_session_images and g not in bad_pool) for g in gcells}

    def unit_detail(k):
        sz = [(g, gcells[g][k]) for g in gcells if gcells[g][k] > 0]
        big = sorted((n for g, n in sz if n >= min_session_images), reverse=True)
        small = sorted((n for g, n in sz if n < min_session_images and elig[g]), reverse=True)
        pooled = len(small) >= 2 and sum(small) >= min_session_images
        return {"sessions_ge_min": big, "pool_groups": len(small) if pooled else 0,
                "pool_images": sum(small) if pooled else 0,
                "ignored_small_session_fragments": sorted((n for g, n in sz if n < min_session_images and not elig[g]), reverse=True),
                "units": len(big) + (2 if pooled else 0)}

    def n_units(k):
        """independent units of a cell: sessions with >= min_session_images images of it, plus a POOL of smaller groups
        that counts as 2 units when it holds >= 2 groups and >= min_session_images images altogether. Only groups from
        untimestamped sources (not capture-session fragments, not members of a pHash-chained component) are pooled."""
        return unit_detail(k)["units"]

    # cells that are NOT measurable on held-out (>= MIN_CELL_IMAGES images but < 2 sessions with >= min_session_images
    # images of the cell) go ENTIRELY to train: every group holding them is forced into train.
    _ci = Counter()
    for r in recs:
        for k in {f"{b['name']}/{b['freshness']}" for b in r["boxes"]}:
            _ci[k] += 1
    not_meas = {k for k, n in _ci.items() if n >= MIN_CELL_IMAGES
                and n_units(k) < 2}
    forced_train = set(forced_train) | {g for g in gcells for k in not_meas if gcells[g][k] > 0}
    assigned = {s: Counter() for s in frac}
    out: dict = {}

    def delta(s, c):
        return sum(n * (2 * (assigned[s][k] - frac[s] * total[k]) + n) / (total[k] ** 2) for k, n in c.items())

    def put(g, s):
        out[g] = s
        assigned[s].update(gcells[g])

    for g in forced_train:
        if g in gcells:
            put(g, "train")
    order = sorted((g for g in gcells if g not in forced_train), key=lambda g: (-sum(n / total[k] for k, n in gcells[g].items()), group_hash(g, seed)))
    for g in order:
        put(g, min(frac, key=lambda s: (delta(s, gcells[g]), group_hash(f"{s}:{g}", seed))))
    cell_imgs = Counter()
    for r in recs:
        for k in {f"{b['name']}/{b['freshness']}" for b in r["boxes"]}:
            cell_imgs[k] += 1
    pinned: set = set()
    moves: list = []
    single: set = set()
    n_total = max(total["__images__"], 1)

    def qualifying(k):
        return [g for g in gcells if gcells[g][k] > 0] if n_units(k) >= 2 else []

    # REQUIRED cells (>= MIN_CELL_IMAGES images and >= 2 qualifying sessions, i.e. sessions with >= min_session_images
    # images of the cell) must get ONE WHOLE session in held-out while train keeps at least one session. Among the
    # candidates, least collateral first (cells losing their last train image, then val coverage), then the LARGEST
    # session that still leaves train with at least as many images of the cell as were moved (apple/spoiled: 98 of
    # 26/125/98 goes to held-out, train keeps 125 + 26). Moves and their collateral are reported.
    impossible = []
    for k in sorted(cell_imgs, key=lambda k: cell_imgs[k]):
        q = qualifying(k)
        if cell_imgs[k] < MIN_CELL_IMAGES or n_units(k) < 2 or assigned["heldout"][k] >= min_session_images:
            continue
        best = None
        for g in q:
            if g in forced_train or out[g] == "heldout":
                continue
            src = out[g]
            tr_after = assigned["train"][k] - (gcells[g][k] if src == "train" else 0)
            if tr_after <= 0:
                continue
            broken = [c for c in gcells[g] if c in cell_imgs and src == "train" and c != k
                      and assigned["train"][c] > 0 and assigned["train"][c] - gcells[g][c] <= 0]
            lostval = [c for c in gcells[g] if c in cell_imgs and src == "val"
                       and assigned["val"][c] > 0 and assigned["val"][c] - gcells[g][c] <= 0]
            ok_major = tr_after >= gcells[g][k]
            cost = (len(broken), len(lostval), 0 if ok_major else 1,
                    -gcells[g][k] if ok_major else gcells[g][k], group_hash(g, seed))
            if best is None or cost < best[0]:
                best = (cost, g, src, broken, lostval)
        if best is None:
            impossible.append(k); continue
        _, g, src, broken, lostval = best
        assigned[src].subtract(gcells[g]); assigned["heldout"].update(gcells[g]); out[g] = "heldout"; pinned.add(g)
        moves.append({"cell": k, "group": g, "from": src, "session_cell_images": gcells[g][k],
                      "group_images": gcells[g]["__images__"],
                      "cells_in_group": {c: n for c, n in gcells[g].items() if "/" in c and not c.startswith("src:")},
                      "cells_losing_last_train_image": broken, "cells_losing_val": lostval})
    # UPGRADE: if the greedy balancer satisfied a required cell only with a small session, but a clearly larger whole
    # session fits the rule (train keeps at least as many images of the cell as are moved), swap to the larger one
    # (apple/spoiled: the 98-image session instead of the 26-image one) provided no other cell loses its held-out or
    # last train presence by the swap.
    swaps = []
    not_meas_late: set = set()
    for k in sorted(cell_imgs, key=lambda k: cell_imgs[k]):
        grp_k = [g for g in gcells if gcells[g][k] > 0]
        if cell_imgs[k] < MIN_CELL_IMAGES or n_units(k) < 2 or assigned["heldout"][k] == 0 or len(grp_k) > 5:
            continue                                     # only scarce cells (<= 5 sessions) where the choice matters
        cur = [g for g in grp_k if out[g] == "heldout"]
        if any(g in pinned for g in cur):
            continue
        cur_n = sum(gcells[g][k] for g in cur)
        cands = [g for g in grp_k if out[g] != "heldout" and g not in forced_train
                 and gcells[g][k] >= max(2 * cur_n, min_session_images)
                 and (assigned["train"][k] - (gcells[g][k] if out[g] == "train" else 0) + cur_n) >= gcells[g][k]]
        if not cands:
            continue
        g = max(cands, key=lambda g: (gcells[g][k], group_hash(g, seed)))
        src = out[g]
        snap = ({x: Counter(c) for x, c in assigned.items()}, dict(out))
        for h in cur:
            assigned["heldout"].subtract(gcells[h]); assigned["train"].update(gcells[h]); out[h] = "train"
        assigned[src].subtract(gcells[g]); assigned["heldout"].update(gcells[g]); out[g] = "heldout"
        bad = [c for c in cell_imgs if (snap[0]["heldout"][c] > 0 and assigned["heldout"][c] <= 0)
               or (snap[0]["val"][c] > 0 and assigned["val"][c] <= 0)
               or (snap[0]["train"][c] > 0 and assigned["train"][c] <= 0)]
        if bad:                                           # the swap would cost another cell its coverage: undo
            assigned.clear(); assigned.update(snap[0]); out.clear(); out.update(snap[1])
            continue
        swaps.append({"cell": k, "from": src, "session_cell_images": gcells[g][k], "replaced_heldout_sessions": cur_n})
    # TRAIN MAJORITY (approved rule): train keeps >= 50% of every measurable cell. A cell below that is re-cut at
    # session level: largest session -> train, next -> held-out (so held-out keeps one whole session), the rest -> val.
    # If no such cut reaches 50% in train while leaving held-out a qualifying unit, the whole cell goes to train and is
    # marked not measurable. Another cell must not lose its train/held-out presence through a re-cut (else it is undone).
    majority_actions = []
    import itertools

    def _required(c):
        return cell_imgs[c] >= MIN_CELL_IMAGES and n_units(c) >= 2 and c not in not_meas_late

    def _viol(cells, counts):
        v = 0
        for c in cells:
            t, vv, h = counts["train"][c], counts["val"][c], counts["heldout"][c]
            tot = t + vv + h
            if _required(c):
                v += (t * 2 < tot) + (h == 0)
            if t == 0 and vv + h > 0:
                v += 3
        return v

    def enforce_majority():
        """Train keeps >= 50% of every measurable cell (approved rule). A violating cell is re-cut at SESSION level by
        searching all train/val/held-out assignments of its (<= 7) movable sessions, scored jointly over every cell those
        sessions contain (so coupled cells such as potato/fresh + potato/spoiled are solved together). If no assignment
        gives train >= 50% with a held-out unit, the whole cell goes to train and is marked not measurable."""
        for k in sorted(cell_imgs, key=lambda k: cell_imgs[k]):
            tot = assigned["train"][k] + assigned["val"][k] + assigned["heldout"][k]
            if cell_imgs[k] < MIN_CELL_IMAGES or not _required(k) or tot == 0 or assigned["train"][k] * 2 >= tot:
                continue
            hs = [g for g in gcells if gcells[g][k] > 0 and g not in forced_train and g not in pinned]
            before = (assigned["train"][k], assigned["val"][k], assigned["heldout"][k])
            best = None
            if 2 <= len(hs) <= 7:
                cells = {c for g in hs for c in gcells[g] if c in cell_imgs}
                base = {sp: Counter(assigned[sp]) for sp in assigned}
                for g in hs:
                    base[out[g]].subtract(gcells[g])
                for plan in itertools.product(("train", "val", "heldout"), repeat=len(hs)):
                    cnt = {sp: Counter(base[sp]) for sp in base}
                    for g, sp in zip(hs, plan):
                        cnt[sp].update(gcells[g])
                    sc = (_viol(cells, cnt), sum(1 for g, sp in zip(hs, plan) if out[g] != sp))
                    if best is None or sc < best[0]:
                        best = (sc, plan)
                cur = {sp: Counter(assigned[sp]) for sp in assigned}
                if best[0][0] < _viol(cells, cur) and best[0][0] == 0 or (best[0][0] < _viol(cells, cur)
                                                                          and (lambda c: c["train"][k] * 2 >= sum(c[x][k] for x in c))(
                                                                              _apply_plan(hs, best[1], base))):
                    for g, sp in zip(hs, best[1]):
                        if out[g] != sp:
                            assigned[out[g]].subtract(gcells[g]); assigned[sp].update(gcells[g]); out[g] = sp
                    majority_actions.append({"cell": k, "action": "recut_by_session", "before_train_val_heldout": before,
                                             "after_train_val_heldout": (assigned["train"][k], assigned["val"][k], assigned["heldout"][k]),
                                             "violations_left_in_coupled_cells": best[0][0]})
                    continue
            for g in [g for g in gcells if gcells[g][k] > 0 and g not in pinned]:       # no cut works: whole cell to train
                if out[g] != "train":
                    assigned[out[g]].subtract(gcells[g]); assigned["train"].update(gcells[g]); out[g] = "train"
            not_meas_late.add(k)
            majority_actions.append({"cell": k, "action": "all_to_train_not_measurable", "before_train_val_heldout": before})

    def _apply_plan(hs, plan, base):
        cnt = {sp: Counter(base[sp]) for sp in base}
        for g, sp in zip(hs, plan):
            cnt[sp].update(gcells[g])
        return cnt

    enforce_majority()
    # val coverage for cells >= MIN_CELL_IMAGES images (best effort, from train groups only)
    moved = 0
    for k in sorted(cell_imgs, key=lambda k: cell_imgs[k]):
        if cell_imgs[k] < MIN_CELL_IMAGES or assigned["val"][k] > 0:
            continue
        holders = [g for g in gcells if gcells[g][k] > 0]
        tot_k = assigned["train"][k] + assigned["val"][k] + assigned["heldout"][k]
        cands = [g for g in holders if out[g] == "train" and g not in forced_train and g not in pinned
                 and (assigned["train"][k] - gcells[g][k]) * 2 >= tot_k and k not in not_meas_late]
        if len(holders) < 2 or not cands:
            continue
        g = min(cands, key=lambda g: (gcells[g]["__images__"], group_hash(g, seed)))
        assigned["train"].subtract(gcells[g]); assigned["val"].update(gcells[g]); out[g] = "val"; moved += 1
    for k in cell_imgs:
        if len([g for g in gcells if gcells[g][k] > 0]) < 2:
            single.add(k)
    # no cell may exist only outside train (e.g. only in held-out): move the largest held-out/val holder groups back
    # to train until train has the cell, and (held-out) until train holds at least as many images as held-out.
    keys = set(cell_imgs)
    gmoves = 0
    for _ in range(3):
        changed = False
        for k in sorted(keys):
            for sp in ("heldout", "val"):
                while assigned[sp][k] > 0 and (assigned["train"][k] == 0
                                              or (sp == "heldout" and assigned["train"][k] < assigned["heldout"][k]
                                                  and sum(1 for g in gcells if out[g] == "heldout" and gcells[g][k]) > 1)):
                    hold = [g for g in gcells if out[g] == sp and gcells[g][k] > 0]
                    hold = [g for g in hold if g not in pinned] or hold      # keep required-cell sessions if possible
                    g = max(hold, key=lambda g: (gcells[g][k], group_hash(g, seed)))
                    assigned[sp].subtract(gcells[g]); assigned["train"].update(gcells[g]); out[g] = "train"
                    gmoves += 1; changed = True
        if not changed:
            break
    bad = [k for k in keys for sp in ("heldout", "val") if assigned[sp][k] > 0 and assigned["train"][k] == 0]
    assert not bad, f"cells present outside train only: {bad}"
    for _ in range(2):                  # audit after the restore pass: the majority rule must hold at the end
        enforce_majority()
    for k in cell_imgs:
        if assigned['heldout'][k] > 0 and assigned['train'][k] == 0:
            raise AssertionError(k)
    decisions = {}
    for k in sorted(cell_imgs):
        q = sorted((gcells[g][k] for g in gcells if gcells[g][k] >= min_session_images), reverse=True)
        allsess = sorted((gcells[g][k] for g in gcells if gcells[g][k] > 0), reverse=True)
        req = cell_imgs[k] >= MIN_CELL_IMAGES and n_units(k) >= 2
        reason = ("" if req else "fewer than %d images" % MIN_CELL_IMAGES if cell_imgs[k] < MIN_CELL_IMAGES else
                  "fewer than 2 independent units (sessions with >= %d images of the cell, or a pool of >= 2 smaller groups); whole cell goes to train" % min_session_images)
        decisions[k] = {"images": cell_imgs[k], "sessions": len(allsess), "session_sizes": allsess,
                        "decision": "required_in_heldout" if req and k not in not_meas_late else "not_measurable_on_heldout",
                        "reason": reason if not (req and k in not_meas_late) else
                        "no session-respecting cut keeps train >= 50% and leaves held-out a qualifying unit; whole cell goes to train",
                        "units": unit_detail(k),
                        "boxes_train_val_heldout": [assigned["train"][k], assigned["val"][k], assigned["heldout"][k]]}
    info = {"cell_decisions": decisions, "required_cell_moves": moves, "heldout_session_upgrades": swaps, "train_majority_actions": majority_actions, "required_cells_impossible": impossible,
            "required_cells_missing_from_heldout": sorted(k for k, d in decisions.items()
                if d["decision"] == "required_in_heldout" and assigned["heldout"][k] == 0),
            "min_session_images": min_session_images,
            "repair_moves": moved, "train_restore_moves": gmoves,
            "cells_not_in_heldout": sorted(k for k in cell_imgs if cell_imgs[k] >= MIN_CELL_IMAGES and assigned["heldout"][k] == 0),
            "cells_not_in_val": sorted(k for k in cell_imgs if cell_imgs[k] >= MIN_CELL_IMAGES and assigned["val"][k] == 0),
            "single_group_cells_kept_in_train_not_measurable": sorted(single),
            "not_measurable_cells_lt_min_images": {k: v for k, v in sorted(cell_imgs.items()) if v < MIN_CELL_IMAGES},
            "min_cell_images": MIN_CELL_IMAGES}
    return out, info


def cell_summary(recs: list[dict]) -> dict:
    """class/freshness -> {train,val,heldout images}, plus which cells with >= MIN_CELL_IMAGES images are missing
    from held-out/val after all moves (so nothing is dropped silently)."""
    t: dict = defaultdict(Counter)
    for r in recs:
        for k in {f"{b['name']}/{b['freshness']}" for b in r["boxes"]}:
            t[k][r["split"]] += 1
    miss = lambda sp: sorted(k for k, v in t.items() if sum(v.values()) >= MIN_CELL_IMAGES and v[sp] == 0)
    return {"images_by_cell_and_split": {k: dict(v) for k, v in sorted(t.items())},
            "not_in_heldout": miss("heldout"), "not_in_val": miss("val")}


def class_by_source(recs: list[dict]) -> dict:
    """class -> source -> {fresh, spoiled} box counts (all splits): the ML-16 source/label confound table."""
    t: dict = defaultdict(lambda: defaultdict(Counter))
    for r in recs:
        for b in r["boxes"]:
            t[b["name"]][r["src"]][b["freshness"] + ("" if b["known"] else "_assumed")] += 1
    return {c: {s: dict(v) for s, v in d.items()} for c, d in sorted(t.items())}


def leakage_report(recs: list[dict], split_of: dict, hthresh: int = 6) -> dict:
    """Per source, for held-out originals: timestamp neighbours in train/val within 60 s / 300 s, and perceptual
    near-duplicates (pHash and, as an independent hash, dHash, Hamming <= hthresh) in train/val."""
    import bisect
    from dedup import hamming
    out = {}
    for src in sorted({r["src"] for r in recs}):
        rs = [r for r in recs if r["src"] == src]
        ho = [r for r in rs if r["split"] == "heldout"]
        tv = [r for r in recs if r["split"] != "heldout"]          # cross-source too
        ref = defaultdict(list)
        for r in tv:
            if r["src"] == src and r.get("ts"):
                ref[r["ts"][0]].append(r["ts"][1])
        for v in ref.values():
            v.sort()
        n_ts = w60 = w300 = 0
        for r in ho:
            if not r.get("ts"):
                continue
            n_ts += 1
            arr = ref.get(r["ts"][0], [])
            if not arr:
                continue
            i = bisect.bisect_left(arr, r["ts"][1])
            g = min(abs(arr[j] - r["ts"][1]) for j in (i - 1, i) if 0 <= j < len(arr))
            w60 += g <= 60; w300 += g <= 300
        nd = {}
        for key in ("phash", "dhash"):
            hs = [r[key] for r in tv]
            cnt = 0
            if hs and ho:
                import numpy as np
                from dedup import _POP
                arr = np.array(hs, dtype=np.uint64)
                for r in ho:
                    x = arr ^ np.uint64(r[key])
                    d = _POP[x.view(np.uint8).reshape(len(arr), 8)].sum(axis=1)
                    cnt += bool((d <= hthresh).any())
            nd[key] = cnt
        n = len(ho)
        out[src] = {"heldout_originals": n, "with_timestamp": n_ts,
                    "ts_neighbour_within_60s": w60, "ts_neighbour_within_300s": w300,
                    "phash_near_dup_in_train_val": nd["phash"], "dhash_near_dup_in_train_val": nd["dhash"],
                    "dhash_near_dup_pct": round(100 * nd["dhash"] / n, 2) if n else None}
    return out


def px_box(box, W, H):
    xc, yc, w, h = box
    return [round((xc - w / 2) * W, 1), round((yc - h / 2) * H, 1),
            round((xc + w / 2) * W, 1), round((yc + h / 2) * H, 1)]


def gt_line(rel, lighting, boxes, W, H):
    return {"image": rel, "lighting": lighting, "labels": [
        {"name": b["name"], "category": T.category_for(b["name"]), "freshness": b["freshness"],
         "confidence": 1.0, "bbox": px_box(b["box"], W, H)} for b in boxes]}


def write_yolo(out: Path, split: str, stem: str, img: Image.Image, boxes, ids: dict, ext=".jpg"):
    (out / "images" / split).mkdir(parents=True, exist_ok=True)
    (out / "labels" / split).mkdir(parents=True, exist_ok=True)
    (out / "freshness" / split).mkdir(parents=True, exist_ok=True)
    rel = f"images/{split}/{stem}{ext}"
    img.convert("RGB").save(out / rel, quality=92)
    (out / "labels" / split / f"{stem}.txt").write_text("".join(
        f"{ids[b['name']]} " + " ".join(f"{v:.6f}" for v in b["box"]) + "\n" for b in boxes))
    # sidecar: one taxonomy.FRESHNESS_CODE per label line (0 fresh, 1 spoiled, 2 semi_fresh), same order
    (out / "freshness" / split / f"{stem}.txt").write_text(
        "".join(f"{T.FRESHNESS_CODE[b['freshness']]}\n" for b in boxes))
    return rel


def write_crops(out: Path, split: str, stem: str, img: Image.Image, boxes, include_assumed: bool):
    W, H = img.size
    res = Counter()
    for i, b in enumerate(boxes):
        if not (b["known"] or include_assumed):
            continue
        res["expected"] += 1
        x1, y1, x2, y2 = px_box(b["box"], W, H)
        pw, ph = (x2 - x1) * 0.05, (y2 - y1) * 0.05
        crop = img.crop((max(0, x1 - pw), max(0, y1 - ph), min(W, x2 + pw), min(H, y2 + ph)))
        if min(crop.size) < 32:
            res[f"missing_too_small/{split}/{b['freshness']}"] += 1
            continue
        d = out / "cls" / split / b["freshness"]
        d.mkdir(parents=True, exist_ok=True)
        crop.convert("RGB").save(d / f"{stem}_{i}.jpg", quality=92)
        res["written"] += 1
    return res


def write_data_yaml(out: Path, active: list[str]):
    """Training data.yaml lists ONLY classes that have data (contiguous ids); class_names.json maps the trained
    id -> canonical taxonomy name. Trained weights carry these names, so infer/serve need no id translation."""
    lines = [f"path: {out.resolve()}", "train: images/train", "val: images/val",
             "test: images/heldout", "names:"]
    lines += [f"  {i}: {n}" for i, n in enumerate(active)]
    (out / "data.yaml").write_text("\n".join(lines) + "\n")
    (out / "class_names.json").write_text(json.dumps({str(i): n for i, n in enumerate(active)}, indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--heldout", type=float, default=0.10)
    ap.add_argument("--val", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--session-gap", type=float, default=300.0,
                    help="seconds; photos from one source shot within this gap of the previous one (chained, no "
                         "span cap) share a split group (ML-21). 0 = group by numbered series stem only")
    ap.add_argument("--phash-threshold", type=int, default=6,
                    help="near-duplicate threshold: images with pHash-64 Hamming <= this share a split group; "
                         "in another split is moved to train. Default 6; our pHash matches imagehash.phash (max 2 bits "
                         "apart, identical <=6 decisions on 44,850 pairs); -1 disables")
    ap.add_argument("--max-unit-images", type=int, default=600,
                    help="a merged near-duplicate/session group larger than this is forced into train (not stratified)")
    ap.add_argument("--min-session-images", type=int, default=10,
                    help="a session (merged group) with fewer than this many images of a cell does not count toward "
                         "the '>= 2 sessions' rule that makes a cell required in held-out")
    ap.add_argument("--max-per-class", type=int, default=None,
                    help="cap images per class x freshness for 'folders' sources (overrides sources.json max_per_class)")
    ap.add_argument("--no-synth-lighting", action="store_true", help="skip synthetic low/warm heldout copies")
    ap.add_argument("--lighting-overrides", help="CSV image,lighting to override auto tags (hand-tagged)")
    ap.add_argument("--include-assumed-fresh-crops", action="store_true")
    ap.add_argument("--min-class-images", type=int, default=0, help="report classes below this count")
    a = ap.parse_args(argv)

    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty; refusing to overwrite")
    out.mkdir(parents=True, exist_ok=True)
    sources = json.loads(Path(a.sources).read_text())["sources"]
    skipped: Counter = Counter()
    drops: Counter = Counter()
    recs = collect(sources, skipped, drops, a.max_per_class, a.seed)
    grouping = assign_sessions(recs, a.session_gap)
    for r in recs:                      # perceptual hashes (used to merge near-duplicates, and re-checked below)
        with Image.open(r["path"]) as im:
            r["phash"], r["dhash"] = D.phash64(im), D.dhash64(im)
    near = None
    forced: set = set()
    if a.phash_threshold >= 0:
        near, forced = merge_near_duplicates(recs, a.phash_threshold, a.max_unit_images)
    grouping["groups"] = len({r["group"] for r in recs})
    grouping["largest_group_images"] = max(Counter(r["group"] for r in recs).values(), default=0)
    # ML-16: train only on classes that have data; ids are contiguous in taxonomy order.
    present = {b["name"] for r in recs for b in r["boxes"]}
    active = [n for n in T.CLASS_NAMES if n in present]
    ids = {n: i for i, n in enumerate(active)}
    overrides = {}
    if a.lighting_overrides:
        overrides = {r["image"]: r["lighting"] for r in csv.DictReader(open(a.lighting_overrides))}

    split_of, strat = assign_splits(recs, a.heldout, a.val, a.seed, forced, a.min_session_images)
    for r in recs:
        r["split"] = split_of[r["group"]]
    grouping["near_duplicates"] = near
    grouping["near_duplicate_drops"] = drop_cross_split_near_duplicates(recs, a.phash_threshold) if near else None
    recs = [r for r in recs if not r.get("dropped")]
    # safety net: with merged groups this must move nothing
    grouping["near_duplicate_purge_safety_net"] = purge_near_duplicates(recs, a.phash_threshold) if near else None
    strat["cells_after_purge"] = cell_summary(recs)
    leakage = leakage_report(recs, None, a.phash_threshold if a.phash_threshold >= 0 else 6)
    stats = {s: Counter() for s in ("train", "val", "heldout")}
    src_split: dict = defaultdict(Counter)       # source -> split/images|boxes
    crops = Counter()
    ho_boxes: dict = defaultdict(Counter)        # "lighting/method" -> "name/freshness" -> boxes
    ho_imgs: Counter = Counter()
    cls_count: Counter = Counter()
    manifest, gt = [], []
    fresh_count: Counter = Counter()
    for r in recs:
        split = r["split"]
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{r['src']}_{r['path'].stem}")[:120]
        stem += "_" + hashlib.md5(str(r["path"]).encode()).hexdigest()[:6]
        img = Image.open(r["path"]); img.load()
        W, H = img.size
        rel = write_yolo(out, split, stem, img, r["boxes"], ids)
        stats[split]["images"] += 1
        src_split[r["src"]][f"{split}/images"] += 1
        src_split[r["src"]][f"{split}/boxes"] += len(r["boxes"])
        for b in r["boxes"]:
            stats[split][f"{b['name']}/{b['freshness']}"] += 1
            cls_count[b["name"]] += 1
            fresh_count[b["freshness"]] += 1
        if split != "heldout":
            crops.update(write_crops(out, split, stem, img, r["boxes"], a.include_assumed_fresh_crops))
            continue
        lt = overrides.get(rel) or L.tag(img)
        method = "manual" if rel in overrides else "auto"
        n_sp = sum(b["freshness"] == "spoiled" for b in r["boxes"])
        manifest.append(dict(image=rel, lighting=lt, lighting_method=method, source=r["src"],
                             group=r["group"], n_boxes=len(r["boxes"]), n_spoiled=n_sp, width=W, height=H,
                             variant_of=""))
        gt.append(gt_line(rel, lt, r["boxes"], W, H))
        ho_imgs[f"{lt}/{method}"] += 1
        for b in r["boxes"]:
            ho_boxes[f"{lt}/{method}"][f"{b['name']}/{b['freshness']}"] += 1
        if not a.no_synth_lighting and lt == "normal":
            for kind in ("low", "warm"):
                vrel = write_yolo(out, "heldout", stem + f"__{kind}", L.synth(img, kind), r["boxes"], ids)
                ho_imgs[f"{kind}/synthetic"] += 1
                for b in r["boxes"]:
                    ho_boxes[f"{kind}/synthetic"][f"{b['name']}/{b['freshness']}"] += 1
                manifest.append(dict(image=vrel, lighting=kind, lighting_method="synthetic", source=r["src"],
                                     group=r["group"], n_boxes=len(r["boxes"]), n_spoiled=n_sp,
                                     width=W, height=H, variant_of=rel))
                gt.append(gt_line(vrel, kind, r["boxes"], W, H))

    for sp in ("train", "val", "heldout"):                       # split dirs always exist, even when empty
        for sub in ("images", "labels", "freshness"):
            (out / sub / sp).mkdir(parents=True, exist_ok=True)
    for sp in ("train", "val"):
        for fr in sorted({b["freshness"] for r in recs for b in r["boxes"]}):
            (out / "cls" / sp / fr).mkdir(parents=True, exist_ok=True)
    write_data_yaml(out, active)
    with open(out / "heldout_manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image", "lighting", "lighting_method", "source", "group",
                                          "n_boxes", "n_spoiled", "width", "height", "variant_of"])
        w.writeheader(); w.writerows(manifest)
    with open(out / "heldout_gt.jsonl", "w") as f:
        for g in gt:
            f.write(json.dumps(g) + "\n")
    crop_report = {"expected": crops["expected"], "written": crops["written"],
                   "missing": {k: v for k, v in crops.items() if k.startswith("missing")}}
    report = {"split_grouping": grouping["split_grouping"], "grouping": grouping,
              "active_classes": active, "n_active_classes": len(active),
              "stratification": strat, "leakage_by_source": leakage,
              "class_by_source": class_by_source(recs), "max_per_class": a.max_per_class,
              "splits": {k: dict(v) for k, v in stats.items()},
              "heldout_originals": sum(1 for m in manifest if not m["variant_of"]),
              "heldout_manifest_rows": len(manifest),
              "heldout_original_boxes_by_class": dict(sorted(Counter(
                  f"{n}/{fr}" for g in gt if "__low" not in g["image"] and "__warm" not in g["image"]
                  for n, fr in ((lb["name"], lb["freshness"]) for lb in g["labels"])).items())),
              "source_by_split": {k: dict(v) for k, v in src_split.items()},
              "train_share_by_source": {k: round(v.get("train/images", 0) / max(1, sum(x.get("train/images", 0) for x in src_split.values())), 4)
                                        for k, v in src_split.items()},
              "source_curation": {x["name"]: x["curation"] for x in sources if x.get("curation")},
              "dropped_images": dict(drops),
              "empty_label_images": sum(v for k, v in drops.items() if k.endswith(":empty_label_file")),
              "crops": crop_report,
              "heldout_images_by_lighting_method": dict(ho_imgs),
              "heldout_boxes_by_lighting_method_class": {k: dict(v) for k, v in sorted(ho_boxes.items())},
              "classes_unmapped_skipped": dict(skipped),
              "classes_below_min": [n for n in T.CLASS_NAMES if cls_count[n] < a.min_class_images and cls_count[n]],
              "classes_with_no_data": [n for n in T.CLASS_NAMES if not cls_count[n]],
              "heldout_by_lighting": dict(Counter(m["lighting"] for m in manifest)),
              "boxes_by_freshness": {f: fresh_count[f] for f in T.FRESHNESS}}
    (out / "dataset_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"heldout_by_lighting": report["heldout_by_lighting"],
                      "images": {k: v["images"] for k, v in stats.items()},
                      "no_data": len(report["classes_with_no_data"]),
                      "active_classes": len(active), "grouping": grouping}))


if __name__ == "__main__":
    main()
