"""Download helpers for sources that are not a single small zip.

fetch_dafif   Mendeley `vx4ptwk3pb` (DaFiF fish). 2,536 single-file JPEGs (~11 MB each), no class folders.
              Each Mendeley folder holds one sensor workbook named like `24-01-2024(MakarelSesi1).xlsx`
              or `Rekap Makarel 22 Sesi 1.xlsx`; that name gives the folder's date, species and session.
              Day 1 = 19 Jan 2024. Only the kept days are downloaded (default fresh 1-3, spoiled 9-11),
              round-robin over (species, session, day) up to `max_per_cell` per freshness, each file's
              SHA-256 checked against the API, then downscaled to `max_side` px.
fetch_meatscan Zenodo 16764338 (MeatScan cow meat), one 25.4 GB RAR5. Never downloaded whole: HTTP range
              reads of its QuickOpen index, the metadata CSV and only the chosen originals (see below).

Both write a folder-per-class tree that `python -m pipeline ingest-dataset --dir ...` stages with the
matching adapter (dafif / meatscan). Network and 7z calls are injectable so tests run offline.
"""
from __future__ import annotations
import hashlib
import io
import json
import re
import shutil
import subprocess
import urllib.request
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (compatible; fwr-pipeline)"}  # Mendeley answers 403 to urllib's default UA (ML-42)
DAFIF_API = "https://data.mendeley.com/public-api/datasets/vx4ptwk3pb"
DAFIF_DAY1 = date(2024, 1, 19)
DAFIF_SPECIES = {"makarel": "mackerel", "mujair": "tilapia", "muajir": "tilapia", "tongkol": "tuna"}
MEATSCAN_URL = "https://zenodo.org/api/records/16764338/files/MeatScan_Dataset.rar/content"
MEATSCAN_BYTES = 25416554933


# ----------------------------------------------------------------------------------------- shared
def _get(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def save_downscaled(data: bytes, dst: Path, max_side: int) -> tuple[int, int]:
    """Decode, shrink so the long side <= max_side, write RGB JPEG q92. Returns the saved size."""
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        if max_side and max(im.size) > max_side:
            im.thumbnail((max_side, max_side), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")   # atomic: an interrupted write never looks "cached" on a re-run
        im.save(tmp, "JPEG", quality=92)
        tmp.replace(dst)
        return im.size


def round_robin(items: list, key, limit: int | None) -> list:
    """Take items one per bucket in turn (buckets sorted by key, items in given order) until `limit`."""
    buckets: dict = defaultdict(list)
    for it in items:
        buckets[key(it)].append(it)
    queues = [list(buckets[k]) for k in sorted(buckets)]
    out = []
    while any(queues):
        for q in queues:
            if q and (limit is None or len(out) < limit):
                out.append(q.pop(0))
        if limit is not None and len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------------------------------ DaFiF
_WB_DATED = re.compile(r"(?P<d>\d{1,2})-(?P<m>\d{1,2})-(?P<y>\d{4})\W*\(?\W*(?P<sp>[A-Za-z]+?)\W*(?:_?sesi\W*(?P<s>\d))?\)?\.xlsx$", re.I)
_WB_REKAP = re.compile(r"Rekap\s+(?P<sp>[A-Za-z]+)\s+(?P<d>\d{1,2})\s+sesi\s*(?P<s>\d)", re.I)


def parse_workbook_name(name: str) -> dict | None:
    """'24-01-2024(MakarelSesi1).xlsx' / '19-01-2024(Mujair).xlsx' / '29-01-2024(t(TongkolSesi1).xlsx' /
    'Rekap Tongkol 28 Sesi 2.xlsx' -> {date, day, species, session}. Rekap files are January 2024."""
    clean = name.replace("t(Tongkol", "(Tongkol")
    try:
        m = _WB_DATED.search(clean)
        if m:
            d = date(int(m["y"]), int(m["m"]), int(m["d"]))
            sp, s = m["sp"].lower(), int(m["s"] or 1)
        else:
            m = _WB_REKAP.search(clean)
            if not m:
                return None
            d, sp, s = date(2024, 1, int(m["d"])), m["sp"].lower(), int(m["s"])
    except ValueError:  # impossible date in the name (PL-6): unparsed, reported by dafif_plan
        return None
    sp = re.sub(r"sesi$", "", sp)
    species = DAFIF_SPECIES.get(sp)
    if species is None:
        return None
    return {"date": d.isoformat(), "day": (d - DAFIF_DAY1).days + 1, "species": species, "session": s}


def dafif_plan(meta: dict, fresh_days=(1, 2, 3), spoiled_days=(9, 10, 11), max_per_cell: int | None = 300) -> dict:
    """Pick the images to download from the Mendeley file list. Returns {"items": [...], "report": {...}}."""
    folders: dict[str, dict] = {}
    unparsed = []
    for f in meta["files"]:
        if f["filename"].lower().endswith(".xlsx"):
            info = parse_workbook_name(f["filename"])
            if info:
                folders.setdefault(f.get("folder_id"), info)
            else:
                unparsed.append(f["filename"])
    label_of = {**{d: "fresh" for d in fresh_days}, **{d: "spoiled" for d in spoiled_days}}
    cand: dict[str, list] = defaultdict(list)
    skipped_days, no_folder = defaultdict(int), 0
    for f in meta["files"]:
        if not f["filename"].lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        info = folders.get(f.get("folder_id"))
        if info is None:
            no_folder += 1
            continue
        fr = label_of.get(info["day"])
        if fr is None:
            skipped_days[info["day"]] += 1
            continue
        cd = f.get("content_details") or {}
        cand[fr].append({**info, "freshness": fr, "filename": f["filename"], "url": cd.get("download_url"),
                         "sha256": cd.get("sha256_hash"), "size": f.get("size")})
    items = []
    for fr in sorted(cand):
        lst = sorted(cand[fr], key=lambda x: (x["day"], x["species"], x["session"], x["filename"]))
        items += round_robin(lst, lambda x: (x["species"], x["session"], x["day"]), max_per_cell)
    report = {"workbook_folders": len(folders), "unparsed_workbooks": unparsed, "images_without_folder": no_folder,
              "candidates": {k: len(v) for k, v in cand.items()}, "selected": {k: sum(1 for i in items if i["freshness"] == k) for k in cand},
              "skipped_middle_days": dict(sorted(skipped_days.items())),
              "rule": {"fresh_days": list(fresh_days), "spoiled_days": list(spoiled_days), "day1": DAFIF_DAY1.isoformat()}}
    return {"items": items, "report": report}


def fetch_dafif(dest: Path, fresh_days=(1, 2, 3), spoiled_days=(9, 10, 11), max_per_cell: int | None = 300,
                max_side: int = 1280, workers: int = 6, get=_get, meta: dict | None = None) -> dict:
    """Download the selected DaFiF images into dest/fish__<freshness>/<species>_s<n>_d<day>__<file>.jpg."""
    dest = Path(dest)
    meta = meta or json.loads(get(DAFIF_API))
    plan = dafif_plan(meta, fresh_days, spoiled_days, max_per_cell)
    bad: list[str] = []

    def one(it):
        out = dest / f"fish__{it['freshness']}" / f"{it['species']}_s{it['session']}_d{it['day']}__{Path(it['filename']).stem}.jpg"
        if out.exists():
            return "cached"
        data = get(it["url"])
        if it.get("sha256") and hashlib.sha256(data).hexdigest() != it["sha256"]:
            bad.append(f"{it['filename']}: sha256 mismatch")
            return "bad"
        try:
            save_downscaled(data, out, max_side)
        except Exception as e:  # one undecodable image must not abort the whole fetch
            bad.append(f"{it['filename']}: {type(e).__name__}")
            return "bad"
        return "ok"

    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(one, plan["items"]))
    report = {**plan["report"], "downloaded": results.count("ok"), "cached": results.count("cached"),
              "sha_mismatch": [b for b in bad if "sha256" in b], "failed": [b for b in bad if "sha256" not in b],
              "max_side": max_side}
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "fetch_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


# --------------------------------------------------------------------------------------- MeatScan
# MeatScan_Dataset.rar is a NON-solid RAR5 (each file compressed on its own) with a QuickOpen index near the
# end that caches every file header and its offset. So instead of downloading 25.4 GB we fetch the ~1 MB
# index, the metadata CSV and only the chosen images with HTTP range requests. Each range (file header +
# packed data) is wrapped in a minimal one-file RAR5 container and decompressed with `unrar-cffi` (pip;
# the official UnRAR code, which also verifies each file's CRC32). Debian/Ubuntu `7z` builds lack the RAR codec.
#
# The release's file names are `Fresh (N).jpg` / `Spoiled (N).jpg`; the CSV lists the 6,995 ORIGINALS as
# `fresh_meat_N.jpg` / `spoiled_meat_N.jpg` with date, time and market. Originals are exactly N <= 3487 (fresh)
# and N <= 3508 (spoiled); higher N are the authors' 4,005 augmented copies, which we never fetch.
MS_QO_LOCATOR = 25415504475          # QuickOpen offset from the main header (main header starts at byte 8)
MS_QO_ABS = MS_QO_LOCATOR + 8
_MS_NAME = re.compile(r"/(Fresh|Spoiled) \((\d+)\)\.jpg$")
_MS_CSV_NAME = re.compile(r"(fresh|spoiled)_meat_(\d+)", re.I)


def _vint(b: bytes, i: int) -> tuple[int, int]:
    v = s = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return v, i


def _vint_enc(n: int) -> bytes:
    out = bytearray()
    while True:
        c, n = n & 0x7F, n >> 7
        out.append(c | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _rar_block(body: bytes) -> bytes:
    size = _vint_enc(len(body))
    return zlib.crc32(size + body).to_bytes(4, "little") + size + body


RAR5_SIG = b"Rar!\x1a\x07\x01\x00"


def wrap_single_file(raw: bytes) -> bytes:
    """file header + packed data (as stored in the big archive) -> a valid one-file RAR5 archive."""
    return RAR5_SIG + _rar_block(b"\x01\x00\x00") + raw + _rar_block(b"\x05\x00\x00")


def parse_quick_open(block: bytes, block_abs: int) -> list[dict]:
    """Parse a RAR5 QuickOpen service block (starting at absolute offset block_abs) into
    [{name, abs, hdr_len, packed, unpacked, header}] - abs is where the file header starts in the archive."""
    hs, j = _vint(block, 4)
    k = j
    _, k = _vint(block, k)            # header type (3 = service)
    hf, k = _vint(block, k)
    if hf & 1:
        _, k = _vint(block, k)
    ds = 0
    if hf & 2:
        ds, k = _vint(block, k)
    p, end, out = j + hs, j + hs + ds, []
    while p < end:
        sz, q = _vint(block, p + 4)
        nxt = q + sz
        _, q = _vint(block, q)        # cache flags
        off, q = _vint(block, q)      # distance from the QuickOpen block back to the cached header
        dsz, q = _vint(block, q)
        hdr = block[q:q + dsz]
        _, r = _vint(hdr, 4)
        _, r = _vint(hdr, r)          # header type 2 = file
        hf2, r = _vint(hdr, r)
        if hf2 & 1:
            _, r = _vint(hdr, r)
        packed = 0
        if hf2 & 2:
            packed, r = _vint(hdr, r)
        ff, r = _vint(hdr, r)
        unpacked, r = _vint(hdr, r)
        _, r = _vint(hdr, r)          # attributes
        r += 4 if ff & 2 else 0       # mtime
        r += 4 if ff & 4 else 0       # crc32
        _, r = _vint(hdr, r)          # compression info
        _, r = _vint(hdr, r)          # host os
        nl, r = _vint(hdr, r)
        out.append({"name": hdr[r:r + nl].decode("utf-8", "replace"), "abs": block_abs - off, "hdr_len": len(hdr),
                    "packed": packed, "unpacked": unpacked, "header": hdr})
        p = nxt
    return out


def curl_range(url: str, start: int, length: int) -> bytes:
    """Zenodo answers 403 to urllib's client for ranged reads; curl works."""
    r = subprocess.run(["curl", "-sfL", "--retry", "5", "-r", f"{start}-{start + length - 1}", url],
                       capture_output=True, check=True)
    if len(r.stdout) != length:
        raise RuntimeError(f"range {start}+{length}: got {len(r.stdout)} bytes")
    return r.stdout


def unrar_bytes(archive: bytes) -> bytes:
    """Decompress the only member of a one-file RAR5 archive (CRC-checked by UnRAR)."""
    import tempfile
    from unrar.cffi import rarfile  # pip install unrar-cffi (fetch-time only; not a test dependency)
    with tempfile.NamedTemporaryFile(suffix=".rar") as t:
        t.write(archive)
        t.flush()
        rf = rarfile.RarFile(t.name)
        return rf.read(rf.namelist()[0])


def meatscan_originals(csv_text: str) -> dict[tuple[str, int], dict]:
    """{("fresh"|"spoiled", N): csv row} for every original listed in MeatScan_Metadata.csv."""
    import csv as _csv
    out = {}
    for r in _csv.DictReader(io.StringIO(csv_text)):
        m = _MS_CSV_NAME.search(r.get("Filename", ""))
        if m:
            out[(m.group(1).lower(), int(m.group(2)))] = r
    return out


def meatscan_plan(entries: list[dict], originals: dict, per_class: int = 450) -> dict:
    """Originals only (in the CSV), spread round-robin over capture (date, market, hour) buckets per class."""
    cand = defaultdict(list)
    aug = defaultdict(int)
    for e in entries:
        m = _MS_NAME.search(e["name"])
        if not m:
            continue
        cls, n = m.group(1).lower(), int(m.group(2))
        row = originals.get((cls, n))
        if row is None:
            aug[cls] += 1
            continue
        hour = (row.get("Time_Captured") or "")[:2]
        cand[cls].append({**e, "cls": cls, "n": n, "bucket": (row.get("Date_Captured"), row.get("Location"), hour)})
    pick = {cls: round_robin(sorted(lst, key=lambda x: x["n"]), lambda x: x["bucket"], per_class) for cls, lst in cand.items()}
    return {"items": [x for v in pick.values() for x in v],
            "report": {"originals_in_archive": {k: len(v) for k, v in cand.items()},
                       "augmented_copies_skipped": dict(aug), "selected": {k: len(v) for k, v in pick.items()},
                       "buckets": {k: len({x["bucket"] for x in v}) for k, v in cand.items()}}}


def fetch_meatscan(dest: Path, per_class: int = 450, max_side: int = 1280, workers: int = 8, url: str = MEATSCAN_URL,
                   total_bytes: int = MEATSCAN_BYTES, rng=curl_range, decompress=unrar_bytes) -> dict:
    """Write dest/{Fresh_CowMeat,Spoiled_CowMeat}/<name>.jpg (downscaled) + dest/MeatScan_Metadata.csv."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    block = rng(url, MS_QO_ABS, total_bytes - MS_QO_ABS)
    entries = parse_quick_open(block, MS_QO_ABS)
    if not entries:
        raise RuntimeError("MeatScan QuickOpen index is empty: the release changed; stop and check")

    def member(e) -> bytes:
        raw = rng(url, e["abs"], e["hdr_len"] + e["packed"])
        if raw[:e["hdr_len"]] != e["header"]:
            raise RuntimeError(f"{e['name']}: header at the indexed offset does not match (changed release?)")
        return decompress(wrap_single_file(raw))

    csv_e = next((e for e in entries if e["name"].lower().endswith(".csv")), None)
    if csv_e is None:  # PL-7
        raise RuntimeError("MeatScan archive index has no metadata CSV: the release changed; stop and check")
    csv_text = member(csv_e).decode("utf-8-sig", "replace")
    (dest / "MeatScan_Metadata.csv").write_text(csv_text)
    plan = meatscan_plan(entries, meatscan_originals(csv_text), per_class)

    def one(e):
        out = dest / Path(e["name"]).parent.name / Path(e["name"]).name
        if out.exists():
            return "cached"
        save_downscaled(member(e), out, max_side)
        return "ok"

    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(one, plan["items"]))
    report = {**plan["report"], "downloaded": res.count("ok"), "cached": res.count("cached"), "max_side": max_side,
              "index_entries": len(entries)}
    (dest / "fetch_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
