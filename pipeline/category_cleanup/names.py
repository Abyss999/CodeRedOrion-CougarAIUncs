"""Label / receipt-line text -> canonical detector class + backend category.

    clean("GV 2% MLK GAL")        -> {"canonical": "milk",    "category": "dairy",      "match": "alias"}
    clean("CHKN BRST 2.1 LB")     -> {"canonical": "chicken", "category": "meat",       "match": "alias"}
    clean("HONEY NUT CEREAL")     -> {"canonical": None,      "category": "pantry_dry", "match": "keyword"}
    clean("XQZT 4411")            -> {"canonical": None,      "category": "other",      "match": "none"}

Every result also has "food_group" (protein/veggies/fruit/dairy/grains/pantry/leftovers/frozen/other):
taxonomy.food_group_for(canonical) when the line maps to a detector class, otherwise the backend's
name-only heuristic (backend/app/services/food_group.derive_from_name).

match: exact (whole text is a class), alias (class found after abbreviation/alias expansion),
keyword (no class, but a category keyword), none. Taxonomy is ml/yolo/taxonomy.py (single source). The abbreviation table is the backend's
(food_group.ABBREVIATIONS) plus the extras in abbreviations.json; nothing is duplicated.
"""
from __future__ import annotations
import importlib.util
import json
import re
from functools import lru_cache
from pathlib import Path

from .. import config  # noqa: F401  (puts ml/yolo on sys.path)
import taxonomy as T  # noqa: E402

_ABBR = Path(__file__).with_name("abbreviations.json")
_FOOD_GROUP_PY = config.REPO / "backend" / "app" / "services" / "food_group.py"


@lru_cache(maxsize=1)
def backend_food_group():
    """backend/app/services/food_group.py, loaded by file path. Importing it as app.services.food_group
    would run backend/app/__init__.py, which imports Flask and SQLAlchemy; the module itself is stdlib-only."""
    spec = importlib.util.spec_from_file_location("_backend_food_group", _FOOD_GROUP_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=1)
def _tables():
    d = json.loads(_ABBR.read_text())
    return d["expand"], set(d["noise"]), d["keywords"], d.get("phrases", {})


def tokens(text: str) -> list[str]:
    expand, noise, _, _ = _tables()
    out = []
    shared = backend_food_group().ABBREVIATIONS
    for t in re.findall(r"[a-z]+", text.lower()):
        t = shared.get(t, t)   # backend table first, then the pipeline-only extras
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


def food_group_of(canonical: str | None, text: str) -> str:
    if canonical:
        return T.food_group_for(canonical)
    derive = backend_food_group().derive_from_name
    g = derive(text)
    if g == "other":  # the backend only knows its own abbreviations; retry on our expanded tokens
        g = derive(" ".join(tokens(text)))
    return g


def clean(text: str) -> dict:
    r = _clean(text)
    return {**r, "food_group": food_group_of(r["canonical"], text)}


def _clean(text: str) -> dict:
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
