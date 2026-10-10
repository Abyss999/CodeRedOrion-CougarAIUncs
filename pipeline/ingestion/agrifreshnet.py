"""AgriFreshNET Freshness and Shelf-Life Image Dataset (8 produce x Fresh / Semi fresh / Rotten).

Folder names carry an age range in days: 'Fresh Banana(1-4)', 'Semi fresh Pineapple (15-25)',
'Semi_Fresh eggplant(4-8)', 'Rotten Orange(20-35)'. Files named 'aug_<n>_<original>' are the
authors' own augmentations of <original>; they are grouped with it. Phone shots taken in the same
minute (IMG_YYYYMMDD_HHMMSS...) are treated as one burst of the same fruit and grouped too.
"""
from __future__ import annotations
import re

from .generic import parse_dir as _parse_generic, _AUG

LICENCE = "UNVERIFIED - check the dataset page before publishing results"
URL = "AgriFreshNET Freshness and Shelf-Life Image Dataset (exact URL to record in docs/PIPELINE.md)"
_IMG_TS = re.compile(r"^IMG[_-](\d{8})[_-](\d{4})\d{2}")
_SUFFIX = re.compile(r"(_HDR|_AE|_\d)+$", re.I)


def parse_dir(dirname: str) -> dict | None:
    d = _parse_generic(dirname)
    if d and d["freshness"] is None:
        return None  # every AgriFreshNET folder has a freshness word; anything else is unexpected
    return d


def group_of(cls_dir: str, stem: str) -> tuple[str, bool]:
    is_aug = bool(_AUG.match(stem))
    base = _SUFFIX.sub("", _AUG.sub("", stem))
    m = _IMG_TS.match(base)
    if m:
        base = f"IMG_{m.group(1)}_{m.group(2)}"  # minute burst
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")[:80]
    return f"{cls_dir}__{base}", is_aug
