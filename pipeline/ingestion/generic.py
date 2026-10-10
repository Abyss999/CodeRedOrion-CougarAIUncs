"""Generic folder-per-class adapter: the folder name is parsed by taxonomy.split_freshness
('rotten_apples', 'FreshBanana', 'Semi fresh Tomato(10-24)'). Use for any classification drop.

Works against whatever taxonomy is on the branch. A "semi fresh" folder keeps its own freshness
label only if the taxonomy has a semi_fresh class (``FRESHNESS``); otherwise it is mapped to
``fresh`` and the parsed dict says so (``semi_mapped_to_fresh``), so the ingest report can count it.

Capture timestamps: ``capture_token(stem)`` returns the full original timestamp text found in a
file name (IMG_YYYYMMDD_HHMMSS, YYYYMMDD_HHMMSS or a 13-digit epoch in ms). ``ingestion.datasets``
keeps it in the group part of the staged file name (before '.rf.') so
ml/yolo/prepare_dataset.parse_capture_time() can find it.
"""
from __future__ import annotations
import re

from .. import config  # noqa: F401
import taxonomy as T  # noqa: E402

LICENCE = "UNKNOWN - generic folder source; record the real licence in sources.json and docs/PIPELINE.md before use"
URL = ""
_DAYS = re.compile(r"\(\s*(\d+)\s*-\s*(\d+)\s*\)\s*$")
_AUG = re.compile(r"^aug_\d+_", re.I)
_SEMI = re.compile(r"(^|_)semi(_?fresh)?(_|$)")
_ITEM_ALIASES = {"bittermelon": "bitter_melon", "bitter_gourd": "bitter_melon", "bittergourd": "bitter_melon"}

# Timestamps worth keeping in a staged name (searched, not anchored, in the original stem).
_TS_IMG = re.compile(r"IMG[_-]?(\d{8})[_-]?(\d{6})(?!\d)", re.I)
_TS_BARE = re.compile(r"(?<!\d)((?:19|20)\d{6})[_-]?(\d{6})(?!\d)")
_TS_EPOCH_MS = re.compile(r"(?<!\d)(1[0-9]{12})(?!\d)")


def taxonomy_freshness() -> tuple[str, ...]:
    """Freshness classes the current taxonomy knows (main: fresh/spoiled; with PR A: + semi_fresh)."""
    return tuple(getattr(T, "FRESHNESS", ("fresh", "spoiled")))


def has_semi_fresh() -> bool:
    return "semi_fresh" in taxonomy_freshness()


def parse_dir(dirname: str) -> dict | None:
    base = _DAYS.sub("", dirname).strip()
    n = T.normalize(base)
    semi = bool(_SEMI.search(n))
    if semi:
        n = T.normalize(_SEMI.sub("_", n))
        item, _ = T.split_freshness(n)
        src_fr = "semi_fresh"
        fr = "semi_fresh" if has_semi_fresh() else "fresh"
    else:
        item, fr = T.split_freshness(base)
        src_fr = fr
    item = _ITEM_ALIASES.get(item, item)
    if not item:
        return None
    m = _DAYS.search(dirname)
    return {"item": item, "freshness": fr, "source_freshness": src_fr,
            "semi_mapped_to_fresh": bool(semi and fr != "semi_fresh"),
            "age_days_min": int(m.group(1)) if m else "", "age_days_max": int(m.group(2)) if m else ""}


def capture_token(stem: str) -> str | None:
    """The full capture-timestamp text found in a file stem (as written), or None."""
    s = _AUG.sub("", stem)
    for rx in (_TS_IMG, _TS_BARE, _TS_EPOCH_MS):
        m = rx.search(s)
        if m:
            return m.group(0)
    return None


def safe_base(stem: str, max_len: int = 80) -> str:
    """Stem made filesystem-safe and capped at max_len, but the capture timestamp always survives whole,
    even for a long name (the cap would otherwise cut it)."""
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
    tok = capture_token(base)
    if len(base) > max_len:
        base = base[:max_len]
        if tok and tok not in base:
            base = f"{base[:max_len - len(tok) - 1]}_{tok}"
    return base


def group_of(cls_dir: str, stem: str) -> tuple[str, bool]:
    is_aug = bool(_AUG.match(stem))
    return f"{cls_dir}__{safe_base(_AUG.sub('', stem))}", is_aug
