"""Opt-in photo enrichment for POST /items/from-photo: better expiry dates and per-100 g nutrition.

`run()` picks the candidates worth asking about, cuts one crop per detection when YOLO produced boxes
(services/crops.py), makes ONE Gemini call (`gemini.enrich_items`), validates the answer and writes it onto the
candidates in place. It never raises and never changes the HTTP status: whatever goes wrong, the candidates keep
their table dates and the returned `enrichment` block says why. With the Gemini-fallback detector there are no
boxes, so the call is text-only (`detect_from_image` has already looked at the photo).
"""
import logging
import math
import time
from datetime import date, timedelta

from flask import current_app

from . import crops, expiry, gemini, nutrition

log = logging.getLogger("app.enrich")
if not log.handlers:  # gunicorn's root logger drops INFO; same pattern as app.gemini.usage
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False

FACETS = ("expiry", "nutrition")
MIN_CONFIDENCE = 0.5     # below this the app shows "not sure": a guessed name would get a confident date
MAX_ITEMS = 12           # unique foods per call (config ENRICH_MAX_ITEMS)
SKIP_AFTER_S = 30        # detection alone took this long: do not add a Gemini call on top (ENRICH_SKIP_AFTER_S)
DAYS_CEILING = 3650


def parse_facets(raw) -> tuple:
    """'expiry,nutrition' -> ('expiry', 'nutrition') in canonical order. None or '' -> (). Unknown -> ValueError."""
    if raw is None:
        return ()
    names = [p.strip().lower() for p in str(raw).split(",") if p.strip()]
    if any(n not in FACETS for n in names):
        raise ValueError(f"enrich must be a comma-separated list of: {', '.join(FACETS)}.")
    return tuple(f for f in FACETS if f in names)


def _conf(c):
    v = c.get("confidence")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def plan(cands: list, max_items: int) -> list:
    """[{rep, members}] (indexes into `cands`), most confident first, at most `max_items`.

    Eligible: not detector-spoiled (those go to the Toss/Keep section) and confidence unknown or >= 0.5.
    Candidates with the same (name, category, storage, freshness) share one group: one crop, one answer."""
    groups = {}
    for i, c in enumerate(cands):
        conf = _conf(c)
        if c.get("freshness") == "spoiled" or (conf is not None and conf < MIN_CONFIDENCE):
            continue
        key = (str(c.get("name")).strip().lower(), c.get("category"), c.get("storage"), c.get("freshness"))
        g = groups.setdefault(key, {"rep": i, "members": []})
        g["members"].append(i)
        # the member with a box, then the most confident, is the one whose crop is sent
        if (c.get("bbox") is not None, conf or 0.0) > (cands[g["rep"]].get("bbox") is not None,
                                                         _conf(cands[g["rep"]]) or 0.0):
            g["rep"] = i
    ordered = sorted(groups.values(), key=lambda g: -(_conf(cands[g["rep"]]) or 0.0))
    return ordered[:max_items]


def clamp_days(days, category, storage):
    """Whole days for the expiry date, or None when `days` is unusable. Negative -> 0 (today); above
    min(3650, 2 x the table default + 3) -> that ceiling: Gemini may shorten freely but not stretch far."""
    if isinstance(days, bool) or not isinstance(days, (int, float)) or not math.isfinite(days) or days != int(days):
        return None
    ceiling = min(DAYS_CEILING, 2 * expiry.default_days(category, storage) + 3)
    return max(0, min(int(days), ceiling))


def apply(cands: list, groups: list, rows: list, facets: tuple, today: date | None = None) -> int:
    """Write Gemini's answer per group onto every member candidate. Returns how many candidates got something."""
    today = today or date.today()
    got = set()
    for g, row in zip(groups, rows):
        row = row if isinstance(row, dict) else {}
        rep = cands[g["rep"]]
        days = clamp_days(row.get("shelf_life_days"), rep["category"], rep["storage"]) if "expiry" in facets else None
        nut = nutrition.clean_nutrition(row.get("nutrition")) if "nutrition" in facets else None
        for i in g["members"]:
            if days is not None:
                cands[i]["predicted_expiry"] = (today + timedelta(days=days)).isoformat()
                cands[i]["expiry_source"] = "gemini"
            if nut is not None:
                cands[i]["nutrition"] = dict(nut)
            if days is not None or nut is not None:
                got.add(i)
    return len(got)


def _humanize(name) -> str:
    """Readable and on one line: underscores become spaces and all whitespace (newlines too) collapses, so a
    name read off a label cannot start a new line of the prompt. At most 80 characters."""
    return " ".join(str(name).replace("_", " ").split())[:80]


def _enrich(cands, facets, image, source, started):
    """(status, reason, sent, images, enriched). Raises only on programming errors; `run` catches those."""
    cfg = current_app.config
    if not gemini.is_configured():
        return "skipped", "not_configured", 0, 0, 0
    if time.monotonic() - started > float(cfg.get("ENRICH_SKIP_AFTER_S", SKIP_AFTER_S)):
        return "skipped", "time_budget", 0, 0, 0
    groups = plan(cands, int(cfg.get("ENRICH_MAX_ITEMS", MAX_ITEMS)))
    if not groups:
        return "skipped", "no_eligible", 0, 0, 0
    boxes = [cands[g["rep"]].get("bbox") for g in groups]
    images = crops.make(image, boxes) if source == "yolo" else [None] * len(groups)
    items = [{"name": _humanize(cands[g["rep"]]["name"]), "category": cands[g["rep"]]["category"],
              "storage": cands[g["rep"]]["storage"], "freshness": cands[g["rep"]].get("freshness", "fresh")}
             for g in groups]
    sent, with_image = len(groups), sum(1 for c in images if c)
    try:
        rows = gemini.enrich_items(items, images, facets)
    except gemini.UpstreamError as e:
        log.warning("enrich upstream_error=%s", e)  # "Gemini request failed: <ExceptionType>", no user data
        return "failed", "upstream_error", sent, with_image, 0
    got = apply(cands, groups, rows, facets)
    if got == 0:
        return "failed", "unusable_response", sent, with_image, 0
    return ("ok" if got == len(cands) else "partial"), None, sent, with_image, got


def run(cands: list, facets: tuple, *, image: bytes, source: str, started: float) -> dict:
    """Enrich `cands` in place; returns the response's `enrichment` block. Never raises."""
    t0 = time.monotonic()
    if "nutrition" in facets:  # the key is there whenever it was asked for, null where nothing was found
        for c in cands:
            c["nutrition"] = None
    try:
        status, reason, sent, images, got = _enrich(cands, facets, image, source, started)
    except Exception as e:  # last resort: enrichment must never fail the request
        status, reason, sent, images, got = "failed", "unexpected_error", 0, 0, 0
        log.warning("enrich unexpected_error=%s", type(e).__name__)
    log.info("enrich status=%s reason=%s source=%s facets=%s total=%d sent=%d images=%d enriched=%d latency_ms=%d",
             status, reason or "none", source, ",".join(facets), len(cands), sent, images, got,
             int((time.monotonic() - t0) * 1000))
    return {"status": status, "requested": list(facets), "enriched": got, "total": len(cands), "reason": reason}
