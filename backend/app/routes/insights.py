import math
from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import text

from ..auth import require_auth
from ..errors import upstream_unavailable, validation_error
from ..extensions import db
from ..models import WASTE_REASONS, Item
from ..services import gemini, recipe_cache
from ._util import json_body

bp = Blueprint("insights", __name__)

_RANGE_DAYS = {"week": 7, "month": 30, "all": None}


_KINDS = ("saved", "wasted", "used", "donated")
_KIND_FILTER = {"saved": "outcome IN ('used','donated')", "wasted": "outcome = 'thrown_out'",
                "used": "outcome = 'used'", "donated": "outcome = 'donated'"}


def _agg_cols(prefix: str, window: str) -> str:
    """count/kg/money/co2 per kind for one time window, as `<prefix>_<kind>_<metric>` columns."""
    cols = []
    for k in _KINDS:
        f = f"({_KIND_FILTER[k]}) AND ({window})"
        cols += [f"count(*) FILTER (WHERE {f}) AS {prefix}_{k}_count",
                 f"coalesce(sum(est_weight_kg) FILTER (WHERE {f}),0) AS {prefix}_{k}_kg",
                 f"coalesce(sum(est_price) FILTER (WHERE {f}),0) AS {prefix}_{k}_money",
                 f"coalesce(sum(co2e_kg) FILTER (WHERE {f}),0) AS {prefix}_{k}_co2"]
    return ",\n  ".join(cols)


# Current and previous period in ONE scan (range=all: no previous window, current = everything).
_TOTALS_ALL = f"""
SELECT {_agg_cols("c", "true")}
FROM food_events WHERE user_id = :uid AND event_type = 'remove'
"""
_TOTALS_RANGE = f"""
SELECT {_agg_cols("c", "time >= :since")},
  {_agg_cols("p", "time < :since")}
FROM food_events WHERE user_id = :uid AND event_type = 'remove' AND time >= :prev_since
"""

_REASONS = """
SELECT waste_reason, count(*) AS n, coalesce(sum(est_weight_kg),0) AS kg,
       coalesce(sum(est_price),0) AS money, coalesce(sum(co2e_kg),0) AS co2
FROM food_events
WHERE user_id = :uid AND event_type = 'remove' AND outcome = 'thrown_out' {since_clause}
GROUP BY waste_reason
"""

_WEEKLY = """
SELECT (time_bucket('1 week', time) AT TIME ZONE 'UTC')::date AS week,
       count(*) FILTER (WHERE outcome IN ('used','donated')) AS saved,
       count(*) FILTER (WHERE outcome = 'thrown_out')        AS wasted
FROM food_events
WHERE user_id = :uid AND event_type = 'remove' {since_clause}
GROUP BY week ORDER BY week
"""

# Last 6 weekly buckets (Monday 00:00 UTC, the time_bucket default), current week included, zero-filled.
# Everything is converted to UTC wall-clock `timestamp` (no tz) before generate_series / ::date, so
# neither the bucket dates nor the 1-week steps depend on the session TimeZone or DST (BE-10).
_LAST_6_WEEKS = """
WITH cur AS (
  SELECT time_bucket('1 week', now()) AT TIME ZONE 'UTC' AS wk
), weeks AS (
  SELECT generate_series(cur.wk - interval '5 weeks', cur.wk, interval '1 week') AS week FROM cur
), ev AS (
  SELECT time_bucket('1 week', time) AT TIME ZONE 'UTC' AS week, outcome FROM food_events
  WHERE user_id = :uid AND event_type = 'remove'
    AND time >= ((SELECT wk FROM cur) - interval '5 weeks') AT TIME ZONE 'UTC'  -- UTC arithmetic, DST-proof
)
SELECT w.week::date AS week,
       count(ev.outcome) FILTER (WHERE ev.outcome = 'used')       AS used,
       count(ev.outcome) FILTER (WHERE ev.outcome = 'donated')    AS donated,
       count(ev.outcome) FILTER (WHERE ev.outcome = 'thrown_out') AS wasted
FROM weeks w LEFT JOIN ev ON ev.week = w.week
GROUP BY w.week ORDER BY w.week
"""

_r = lambda v: round(float(v), 2)  # noqa: E731


def _period(t, prefix) -> dict:
    out = {}
    for k in _KINDS:
        g_ = lambda m: getattr(t, f"{prefix}_{k}_{m}", 0) if t is not None else 0  # noqa: E731
        out[k] = {"count": int(g_("count")), "kg": _r(g_("kg")), "money": _r(g_("money")),
                  "co2e_kg": _r(g_("co2"))}
    total = out["saved"]["count"] + out["wasted"]["count"]
    out["waste_rate"] = out["wasted"]["count"] / total if total else 0.0
    return out


@bp.get("/impact")
@require_auth
def get_impact():
    rng = request.args.get("range", "all")
    if rng not in _RANGE_DAYS:
        raise validation_error("range must be week, month or all.")
    days = _RANGE_DAYS[rng]
    since = prev_since = None
    if days:
        since, prev_since = db.session.execute(
            text("SELECT now() - make_interval(hours => :h), now() - make_interval(hours => :h2)"),
            {"h": 24 * days, "h2": 48 * days}).one()  # exact N x 24 h, whatever the session zone / DST
    params = {"uid": g.user.id}
    clause = ""
    if since is not None:
        params.update(since=since, prev_since=prev_since)
        clause = "AND time >= :since"
    # A fixed query count whatever the data (5 for week/month incl. the `since` lookup, 4 for all) (no per-week / per-reason round trips).
    t = db.session.execute(text(_TOTALS_RANGE if since is not None else _TOTALS_ALL), params).first()  # may be None under TimescaleDB 2.17 (BE-1)
    reasons = {row.waste_reason: row for row in
               db.session.execute(text(_REASONS.format(since_clause=clause)), params)}
    weekly = db.session.execute(text(_WEEKLY.format(since_clause=clause)), params).all()
    last6 = db.session.execute(text(_LAST_6_WEEKS), {"uid": g.user.id}).all()

    cur = _period(t, "c")
    wasted_n = cur["wasted"]["count"]
    waste_reasons = []
    for reason in WASTE_REASONS:
        row = reasons.get(reason)
        n = int(row.n) if row else 0
        waste_reasons.append({"reason": reason, "count": n,
                              "kg": _r(row.kg) if row else 0.0, "money": _r(row.money) if row else 0.0,
                              "co2e_kg": _r(row.co2) if row else 0.0,
                              "share": n / wasted_n if wasted_n else 0.0})
    waste_reasons.sort(key=lambda x: -x["count"])  # stable: ties keep the enum order
    return jsonify(
        range=rng,
        saved=cur["saved"], wasted=cur["wasted"], used=cur["used"], donated=cur["donated"],
        waste_rate=cur["waste_rate"],
        waste_reasons=waste_reasons,
        previous=_period(t, "p") if since is not None else None,
        weekly=[{"week": w.week.isoformat(), "saved": w.saved, "wasted": w.wasted}
                for w in weekly],
        last_6_weeks=[{"week": w.week.isoformat(), "used": w.used, "donated": w.donated,
                       "saved": w.used + w.donated, "wasted": w.wasted} for w in last6],
    )


_REASON_TIPS = {
    "expired": "Most of your waste is food that expired. Check the 'expiring soon' list when you shop.",
    "forgot": "Most of your waste is food you forgot about. Keep older items at the front of the shelf.",
    "didnt_like": "Most of your waste is food you didn't like. Try buying smaller amounts of new things.",
    "other": "Most of your waste has 'other' reasons. Add notes next time to spot a pattern.",
}

_BY_REASON = text("""
SELECT waste_reason, count(*) AS n FROM food_events
WHERE user_id = :uid AND event_type = 'remove' AND outcome = 'thrown_out'
  AND time >= now() - interval '90 days'
GROUP BY waste_reason ORDER BY n DESC, waste_reason
""")
_BY_ITEM = text("""
SELECT i.name, e.waste_reason, count(*) AS n
FROM food_events e JOIN items i ON i.id = e.item_id
WHERE e.user_id = :uid AND e.event_type = 'remove' AND e.outcome = 'thrown_out'
  AND e.time >= now() - interval '90 days'
GROUP BY lower(i.name), i.name, e.waste_reason ORDER BY n DESC, i.name LIMIT 1
""")
_BY_CATEGORY = text("""
SELECT category, count(*) AS n, coalesce(sum(est_price),0) AS money FROM food_events
WHERE user_id = :uid AND event_type = 'remove' AND outcome = 'thrown_out'
  AND time >= now() - interval '90 days'
GROUP BY category ORDER BY n DESC, category LIMIT 1
""")


@bp.get("/tips")
@require_auth
def get_tips():
    uid = {"uid": g.user.id}
    tips = []
    soon = (Item.query.filter(Item.owner_id == g.user.id, Item.removed_at.is_(None),
                              Item.predicted_expiry <= date.today() + timedelta(days=2))
            .order_by(Item.predicted_expiry).all())
    if soon:
        names = ", ".join(i.name for i in soon[:3])
        tips.append({"code": "expiring_soon",
                     "message": f"{len(soon)} item(s) expire within 2 days: {names}. Use them first."})
    top_reason = db.session.execute(_BY_REASON, uid).first()
    if top_reason:
        tips.append({"code": f"top_reason_{top_reason.waste_reason}",
                     "message": _REASON_TIPS[top_reason.waste_reason]})
    top_item = db.session.execute(_BY_ITEM, uid).first()
    if top_item:
        verb = "forgotten" if top_item.waste_reason == "forgot" else "thrown out"
        tips.append({"code": "top_wasted_item",
                     "message": f"{top_item.name} is the item you've {verb} most "
                                f"({top_item.n}x in 90 days). Buy less of it or plan a meal around it."})
    top_cat = db.session.execute(_BY_CATEGORY, uid).first()
    if top_cat:
        tips.append({"code": "top_wasted_category",
                     "message": f"{top_cat.category.replace('_', ' ').title()} is your biggest waste "
                                f"category ({top_cat.n} thrown out, about ${float(top_cat.money):.2f})."})
    if not tips:
        tips.append({"code": "getting_started",
                     "message": "Add what's in your fridge and mark things used, donated or thrown "
                                "out. Your personalised tips appear as you do."})
    return jsonify(tips=tips)


def _num_in(v, hi):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return None
    return float(v) if 0 <= v <= hi else None


def clean_macros(m):
    """Per-serving macros or None when missing/invalid (never an error)."""
    if not isinstance(m, dict):
        return None
    kcal, p, c, f = (_num_in(m.get(k), hi) for k, hi in
                     (("kcal", 3000), ("protein_g", 300), ("carbs_g", 300), ("fat_g", 300)))
    if None in (kcal, p, c, f):
        return None
    return {"kcal": int(round(kcal)), "protein_g": round(p, 1), "carbs_g": round(c, 1),
            "fat_g": round(f, 1)}


def clean_servings(v):
    """Integer 1-20, else None (never an error)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v != int(v):
        return None
    return int(v) if 1 <= v <= 20 else None


def _norm(name) -> str:
    return " ".join(str(name).lower().split())


def match_uses_items(names, items) -> list:
    """Map Gemini's item names back to the caller's items -> [{item_id, name, predicted_expiry}].
    Exact (case/space-insensitive) match first, then containment either way; the soonest-expiring
    unmatched item wins ties. Each item is used at most once per recipe; unmatched names are dropped."""
    if not isinstance(names, list):
        return []
    out, taken = [], set()
    for raw in names:
        if not isinstance(raw, str) or not raw.strip():
            continue
        want = _norm(raw)
        free = [i for i in items if i.id not in taken]  # `items` is already soonest-first
        hit = (next((i for i in free if _norm(i.name) == want), None)
               or next((i for i in free if want in _norm(i.name) or _norm(i.name) in want), None))
        if hit is None:
            continue
        taken.add(hit.id)
        out.append({"item_id": str(hit.id), "name": hit.name,
                    "predicted_expiry": hit.predicted_expiry.isoformat()})
    return out


@bp.post("/recipes/suggest")
@require_auth
def suggest_recipes():
    body = request.get_json(silent=True) if request.data else {}
    if not isinstance(body, dict):
        raise validation_error("Request body must be a JSON object.")
    n = body.get("max_results", 3)
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 10:
        raise validation_error("max_results must be an integer 1-10.")
    dietary = body.get("dietary", [])
    if not isinstance(dietary, list) or not all(isinstance(d, str) for d in dietary):
        raise validation_error("dietary must be a list of strings.")
    active = (Item.query.filter(Item.owner_id == g.user.id, Item.removed_at.is_(None))
              .order_by(Item.predicted_expiry, Item.added_at, Item.id).all())
    if not active:
        return jsonify(recipes=[])
    key = recipe_cache.make_key(active, n, dietary)
    cached = recipe_cache.get(g.user.id, key)
    if cached is not None:
        return jsonify(recipes=cached)
    items = active[:20]  # the 20 soonest-expiring go to Gemini
    payload = [{"name": i.name, "category": i.category, "quantity": float(i.quantity),
                "unit": i.unit, "expires": i.predicted_expiry.isoformat()} for i in items]
    try:
        recipes = gemini.suggest_recipes(payload, n, dietary)
    except gemini.UpstreamError as e:
        raise upstream_unavailable(str(e))
    out = []
    for r in recipes:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        r["servings"] = clean_servings(r.get("servings"))
        r["uses_items"] = match_uses_items(r.get("uses_items"), items)
        r["macros"] = clean_macros(r.get("macros"))
        r["macros_estimated"] = True
        out.append(r)
    recipe_cache.put(g.user.id, key, out)
    return jsonify(recipes=out)
