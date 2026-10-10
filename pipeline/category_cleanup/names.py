"""Label / receipt-line text -> canonical detector class + backend category.

    clean("GV 2% MLK GAL")        -> {"canonical": "milk",    "category": "dairy",      "match": "alias"}
    clean("CHKN BRST 2.1 LB")     -> {"canonical": "chicken", "category": "meat",       "match": "alias"}
    clean("HONEY NUT CEREAL")     -> {"canonical": None,      "category": "pantry_dry", "match": "keyword"}
    clean("XQZT 4411")            -> {"canonical": None,      "category": "other",      "match": "none"}

match: exact (whole text is a class), alias (class found after abbreviation/alias expansion),
keyword (no class, but a category keyword), none. Taxonomy is ml/yolo/taxonomy.py (single source).
"""
from __future__ import annotations
import json
import re
from functools import lru_cache
from pathlib import Path

from .. import config  # noqa: F401  (puts ml/yolo on sys.path)
import taxonomy as T  # noqa: E402

_ABBR = Path(__file__).with_name("abbreviations.json")


@lru_cache(maxsize=1)
def _tables():
    d = json.loads(_ABBR.read_text())
    return d["expand"], set(d["noise"]), d["keywords"], d.get("phrases", {})


def tokens(text: str) -> list[str]:
    expand, noise, _, _ = _tables()
    out = []
    for t in re.findall(r"[a-z]+", text.lower()):
        t = expand.get(t, t)
        for w in t.split():
            if w and w not in noise and len(w) > 1:
                out.append(w)
    return out


def _lookup(phrase: str) -> str | None:
    n = T.canonical_name(phrase)
    if n is None and phrase.endswith("s"):
        n = T.canonical_name(phrase[:-1])
    return n


def clean(text: str) -> dict:
    _, _, keywords, phrases = _tables()
    raw = T.normalize(text)
    toks = tokens(text)
    joined = " ".join(toks)
    for ph, v in phrases.items():  # compound names first: 'peanut butter' is not butter
        if re.search(rf"(^| ){re.escape(ph)}( |$)", joined):
            return {"canonical": v["canonical"], "category": v["category"], "match": "alias" if v["canonical"] else "keyword"}
    n = T.canonical_name(raw) if raw else None
    if n and raw in T.CLASS_CATEGORY:
        return {"canonical": n, "category": T.category_for(n), "match": "exact"}
    # longest phrase first (bigrams such as 'sweet potato', 'bell pepper', 'ground beef')
    for size in (3, 2, 1):
        for i in range(len(toks) - size + 1):
            n = _lookup("_".join(toks[i:i + size]))
            if n:
                return {"canonical": n, "category": T.category_for(n), "match": "alias"}
    for t in toks:
        cat = keywords.get(t) or (keywords.get(t[:-1]) if t.endswith("s") else None)
        if cat:
            return {"canonical": None, "category": cat, "match": "keyword"}
    return {"canonical": None, "category": "other", "match": "none"}
