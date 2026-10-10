"""Generic folder-per-class adapter: the folder name is parsed by taxonomy.split_freshness
('rotten_apples', 'FreshBanana', 'Semi fresh Tomato(10-24)'). Use for any classification drop."""
from __future__ import annotations
import re

from .. import config  # noqa: F401
import taxonomy as T  # noqa: E402

LICENCE = "UNVERIFIED - record it in docs/PIPELINE.md"
URL = ""
_DAYS = re.compile(r"\(\s*(\d+)\s*-\s*(\d+)\s*\)\s*$")
_AUG = re.compile(r"^aug_\d+_", re.I)


def parse_dir(dirname: str) -> dict | None:
    name, fr = T.split_freshness(dirname)
    if not name:
        return None
    m = _DAYS.search(dirname)
    return {"item": name, "freshness": fr,
            "age_days_min": int(m.group(1)) if m else "", "age_days_max": int(m.group(2)) if m else ""}


def group_of(cls_dir: str, stem: str) -> tuple[str, bool]:
    is_aug = bool(_AUG.match(stem))
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", _AUG.sub("", stem)).strip("_")[:80]
    return f"{cls_dir}__{base}", is_aug
