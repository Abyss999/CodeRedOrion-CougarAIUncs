"""MeatScan: fresh vs spoiled cow meat, phone photos from two Kumasi (Ghana) markets, 14-16 Feb 2024
(Data in Brief 2025, doi:10.1016/j.dib.2025.112045). Licence: CC BY 4.0.
Zenodo record 16764338 (doi:10.5281/zenodo.16764338), one file `MeatScan_Dataset.rar` (25.4 GB). Fetch it with
`python -m pipeline fetch-meatscan` (range reads, originals only; see fetch.py), never the whole archive.

Layout after the fetch: <root>/{Fresh_CowMeat,Spoiled_CowMeat}/{Fresh,Spoiled} (N).jpg + MeatScan_Metadata.csv.
The CSV lists the 6,995 originals as fresh_meat_N.jpg / spoiled_meat_N.jpg with Date_Captured, Time_Captured
(minute resolution) and Location. `Fresh (N)` is `fresh_meat_N`; higher N not in the CSV are the authors'
augmented copies.

- `include()` keeps only files listed in the CSV (originals); with no CSV it keeps everything.
- `group_of()` puts the capture time into the staged name as `IMG_YYYYMMDD_HHMMSS`, so prepare_dataset's session
  grouping keeps photos taken within 300 s of each other (same stall, same cut) in one split.
"""
from __future__ import annotations
import csv
import re
from datetime import datetime
from pathlib import Path

from .generic import parse_dir as _parse_generic, safe_base

LICENCE = "CC BY 4.0"
VERSION = "zenodo-16764338"
URL = "https://doi.org/10.5281/zenodo.16764338"
DOI = "10.5281/zenodo.16764338"
CITATION = ("MeatScan: An image dataset for machine learning-based classification of fresh and spoiled cow meat. "
            "Data in Brief (2025), doi:10.1016/j.dib.2025.112045. Data: Zenodo, doi:10.5281/zenodo.16764338. CC BY 4.0.")

_rows: dict[tuple[str, int], dict] = {}   # ("fresh"|"spoiled", N) -> CSV row
_CSV_NAME = re.compile(r"(fresh|spoiled)_meat_(\d+)", re.I)
_FILE_NAME = re.compile(r"(fresh|spoiled)\W*\(?\s*(\d+)\s*\)?", re.I)


def _key(stem: str) -> tuple[str, int] | None:
    m = _FILE_NAME.search(stem)
    return (m.group(1).lower(), int(m.group(2))) if m else None


def load_metadata(csv_path: Path) -> dict[tuple[str, int], dict]:
    out = {}
    with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            m = _CSV_NAME.search(r.get("Filename", ""))
            if m:
                out[(m.group(1).lower(), int(m.group(2)))] = r
    return out


def capture_stamp(row: dict) -> str | None:
    try:
        dt = datetime.strptime(f"{row.get('Date_Captured', '').strip()} {row.get('Time_Captured', '').strip()}",
                               "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.strftime("IMG_%Y%m%d_%H%M%S")


def setup(raw_root: Path) -> dict:
    """Called once by datasets.ingest before staging."""
    _rows.clear()
    csvs = sorted(Path(raw_root).rglob("*etadata*.csv"))
    if csvs:
        _rows.update(load_metadata(csvs[0]))
    return {"metadata_csv": csvs[0].name if csvs else None, "originals_listed": len(_rows),
            "timestamped": sum(1 for r in _rows.values() if capture_stamp(r))}


def include(path: Path) -> bool:
    if not _rows:
        return True
    k = _key(Path(path).stem)
    return k is not None and k in _rows


def parse_dir(dirname: str) -> dict | None:
    d = _parse_generic(dirname)
    if d and d["source_freshness"] is None:
        return None  # only Fresh_CowMeat / Spoiled_CowMeat are image folders
    return d


def group_of(cls_dir: str, stem: str) -> tuple[str, bool]:
    k = _key(stem)
    ts = capture_stamp(_rows[k]) if k in _rows else None
    base = safe_base(f"{ts}_{stem}" if ts else stem)
    return f"{cls_dir}__{base}", False
