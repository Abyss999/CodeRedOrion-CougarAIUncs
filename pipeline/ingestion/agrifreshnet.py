"""AgriFreshNET Freshness and Shelf-Life Image Dataset (8 produce x Fresh / Semi fresh / Rotten).

Licence: CC BY 4.0. Mendeley Data, DOI 10.17632/42m5tb7yv9.1 (v1). Authors: Risdin, Salauddin,
Tufa, Hossain. https://data.mendeley.com/datasets/42m5tb7yv9  (attribution lives in docs/PIPELINE.md
and docs/ML.md).

Folder names carry an age range in days: 'Fresh Banana(1-4)', 'Semi fresh Pineapple (15-25)',
'Semi_Fresh eggplant(4-8)', 'Rotten Orange(20-35)'. Files named 'aug_<n>_<original>' are the
authors' own augmentations of <original>; they are grouped with it. Phone shots taken in the same
minute used to be merged into one group by truncating the timestamp. The FULL timestamp now stays in
the staged name (`<cls>__IMG_20250101_123456.rf.<sha>`) so prepare_dataset's session grouping
(parse_capture_time) sees it and groups bursts by time gap instead.

Semi-fresh folders keep their own label when the taxonomy has a semi_fresh class, and are mapped to
fresh (and counted in the ingest report) when it does not. Folders for produce the taxonomy has no
class for (papaya, pineapple, bitter melon on a 2-class main) are reported under unmapped_dirs.
"""
from __future__ import annotations
import re

from .generic import parse_dir as _parse_generic, safe_base, _AUG

LICENCE = "CC BY 4.0"
VERSION = "v1"
SPECIMEN_GROUPING = True  # see specimens.py: cross-stage, dihedral-variant-aware pHash components
URL = "https://data.mendeley.com/datasets/42m5tb7yv9"
DOI = "10.17632/42m5tb7yv9.1"
CITATION = ("Risdin, Salauddin, Tufa, Hossain. AgriFreshNET Freshness and Shelf-Life Image Dataset. "
            "Mendeley Data, v1, doi:10.17632/42m5tb7yv9.1. CC BY 4.0.")
_SUFFIX = re.compile(r"(_HDR|_AE|_\d)+$", re.I)


def parse_dir(dirname: str) -> dict | None:
    d = _parse_generic(dirname)
    if d and d["source_freshness"] is None:
        return None  # every AgriFreshNET folder has a freshness word; anything else is unexpected
    return d


def group_of(cls_dir: str, stem: str) -> tuple[str, bool]:
    is_aug = bool(_AUG.match(stem))
    base = safe_base(_SUFFIX.sub("", _AUG.sub("", stem)))  # keeps the whole capture timestamp
    return f"{cls_dir}__{base}", is_aug
