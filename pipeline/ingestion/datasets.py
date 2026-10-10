"""Dataset ingestion: safe (nested) zip extraction -> adapter parses each class folder ->
staged layout that ml/yolo/prepare_dataset.py reads as a `kind: folders` source.

    staged/<dataset>/<canonical>__<freshness>/<group>.rf.<sha1>.jpg
    staged/<dataset>/manifest.csv        one row per staged image (adds age_days_min/max, group, ...)
    staged/<dataset>/source.json         the prepare_dataset `sources` entry (explicit class_map)
    staged/<dataset>/ingest_report.json  counts, unmapped folders, bad images, duplicates

The '.rf.' in the filename is deliberate: prepare_dataset.group_key() keeps every file that shares
the part before '.rf.' in ONE split, so a photo and the dataset's own augmentations of it (or a
burst of near-identical shots) never straddle train/heldout.
"""
from __future__ import annotations
import csv
import io
import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .. import config
from .ledger import Ledger, sha1_file
from . import agrifreshnet, generic
import taxonomy as T  # noqa: E402  (on sys.path via config)

ADAPTERS = {"agrifreshnet": agrifreshnet, "folders": generic}
MANIFEST_COLS = ["image", "source_dir", "source_file", "item", "canonical", "freshness", "category",
                 "age_days_min", "age_days_max", "group", "is_source_aug", "sha1", "width", "height", "licence"]


class ExtractError(RuntimeError):
    pass


def _safe_target(dest: Path, member: str) -> Path:
    t = (dest / member).resolve()
    if dest.resolve() not in t.parents and t != dest.resolve():
        raise ExtractError(f"unsafe path in archive: {member!r}")
    return t


def extract(zip_path: Path, dest: Path, max_bytes: int | None = None, _depth: int = 0) -> Path:
    """Extract zip_path into dest. Inner .zip members are extracted recursively into a folder named
    after them (then deleted). Rejects path traversal and archives whose declared size > max_bytes."""
    max_bytes = max_bytes or int(config.MAX_EXTRACT_GB * 1e9)
    if _depth > 3:
        raise ExtractError("zip nesting deeper than 3")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if sum(i.file_size for i in infos) > max_bytes:
            raise ExtractError(f"{zip_path.name}: declared size exceeds {max_bytes} bytes")
        for i in infos:
            t = _safe_target(dest, i.filename)
            t.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, open(t, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
            if t.suffix.lower() == ".zip":
                extract(t, t.with_suffix(""), max_bytes, _depth + 1)
                t.unlink()
    return dest


def _image_dirs(root: Path):
    for d in sorted({p.parent for p in root.rglob("*") if p.suffix.lower() in config.IMG_EXT}):
        yield d


def _stage_image(src: Path, dst: Path) -> tuple[int, int]:
    """Verify + write an RGB JPEG. JPEG/RGB sources are copied byte-for-byte (lossless, fast)."""
    with Image.open(src) as im:
        im.load()
        w, h = im.size
        dst.parent.mkdir(parents=True, exist_ok=True)
        if im.format == "JPEG" and im.mode == "RGB":
            shutil.copyfile(src, dst)
        else:
            im.convert("RGB").save(dst, "JPEG", quality=95)
    return w, h


def ingest(raw_root: Path, name: str, adapter: str, staged_root: Path, ledger: Ledger) -> dict:
    ad = ADAPTERS[adapter]
    out = staged_root / name
    out.mkdir(parents=True, exist_ok=True)
    mpath = out / "manifest.csv"
    new_manifest = not mpath.exists()
    counts: Counter = Counter()
    unmapped: Counter = Counter()
    bad: list[str] = []
    class_map: dict[str, str] = {}
    if (out / "source.json").exists():
        class_map = json.loads((out / "source.json").read_text()).get("class_map", {})
    # pass 1: parse folders + hash files, so duplicates and cross-class label conflicts are known up front
    plan: list[tuple[Path, str, dict, str, str]] = []  # (file, sha, parsed, canonical, cls_dir)
    for d in _image_dirs(raw_root):
        parsed = ad.parse_dir(d.name)
        canonical = T.canonical_name(parsed["item"]) if parsed else None
        files = [p for p in sorted(d.iterdir()) if p.suffix.lower() in config.IMG_EXT]
        if not canonical:
            unmapped[d.name] += len(files)
            continue
        cls_dir = f"{canonical}__{parsed['freshness'] or 'fresh'}"
        plan += [(p, sha1_file(p), parsed, canonical, cls_dir) for p in files]
    classes_of: dict[str, set] = {}
    for p, sha, _, _, cls_dir in plan:
        classes_of.setdefault(sha, set()).add(cls_dir)
    conflicts = {sha: sorted(c) for sha, c in classes_of.items() if len(c) > 1}
    conflict_files = [f"{p.parent.name}/{p.name}" for p, sha, *_ in plan if sha in conflicts]
    done: set[str] = set()
    cross_conflicts: list[str] = []  # same bytes as an image staged by an EARLIER run, under another class
    with open(mpath, "a", newline="") as mf:
        w = csv.DictWriter(mf, fieldnames=MANIFEST_COLS)
        if new_manifest:
            w.writeheader()
        for p, sha, parsed, canonical, cls_dir in plan:
            fr = cls_dir.split("__", 1)[1]
            class_map[cls_dir] = f"{canonical}:{fr}"
            if sha in conflicts:  # same pixels labelled two ways: trust neither
                counts["label_conflicts_dropped"] += 1
                continue
            if sha in done:
                counts["duplicates_in_drop"] += 1
                continue
            done.add(sha)
            prev = ledger.ref(f"dataset:{name}", sha)
            if prev is not None:
                if prev and Path(prev).parts[0] != cls_dir:  # staged earlier under ANOTHER class
                    counts["label_conflicts_cross_drop"] += 1
                    cross_conflicts.append(f"{p.parent.name}/{p.name} (already staged as {prev})")
                else:
                    counts["skipped_seen"] += 1
                continue
            group, is_aug = ad.group_of(cls_dir, p.stem)
            rel = Path(cls_dir) / f"{group}.rf.{sha[:16]}.jpg"
            try:
                W, H = _stage_image(p, out / rel)
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
                bad.append(f"{p}: {e.__class__.__name__}")
                ledger.mark(f"dataset:{name}", sha, "bad", str(p))
                continue
            w.writerow(dict(image=str(rel), source_dir=p.parent.name, source_file=p.name, item=parsed["item"],
                            canonical=canonical, freshness=fr, category=T.category_for(canonical),
                            age_days_min=parsed.get("age_days_min", ""), age_days_max=parsed.get("age_days_max", ""),
                            group=group, is_source_aug=int(is_aug), sha1=sha, width=W, height=H,
                            licence=ad.LICENCE))
            ledger.mark(f"dataset:{name}", sha, "staged", str(rel))
            counts["staged"] += 1
            counts[f"freshness:{fr}"] += 1
    source = {"name": name, "kind": "folders", "root": str(out.resolve()), "license": ad.LICENCE,
              "url": ad.URL, "class_map": dict(sorted(class_map.items()))}
    (out / "source.json").write_text(json.dumps(source, indent=2) + "\n")
    report = {"dataset": name, "adapter": adapter, **dict(counts), "unmapped_dirs": dict(unmapped),
              "bad_images": bad, "label_conflict_files": conflict_files,
              "label_conflicts_cross_drop_files": cross_conflicts, "classes": len(class_map)}
    (out / "ingest_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def ingest_zip(zip_path: Path, name: str, adapter: str, dirs: dict[str, Path], keep_raw: bool = True) -> dict:
    raw = dirs["raw"] / name
    marker = raw / ".extracted"
    stamp = f"{zip_path.resolve()}|{zip_path.stat().st_size}|{int(zip_path.stat().st_mtime)}"
    if not (marker.exists() and marker.read_text() == stamp):
        if raw.exists():
            shutil.rmtree(raw)
        extract(zip_path, raw)
        marker.write_text(stamp)
    ledger = Ledger(dirs["staged"] / "ledger.sqlite")
    try:
        rep = ingest(raw, name, adapter, dirs["staged"], ledger)
    finally:
        ledger.close()
    if not keep_raw:
        shutil.rmtree(raw)
    return rep
