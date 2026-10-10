from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import text

from ..auth import require_auth
from ..errors import upstream_unavailable, validation_error
from ..extensions import db
from ..models import Item
from ..services import gemini
from ._util import json_body

bp = Blueprint("insights", __name__)

_RANGE_DAYS = {"week": 7, "month": 30, "all": None}

_TOTALS = """
SELECT
  count(*) FILTER (WHERE outcome IN ('used','donated'))                       AS s_count,
  coalesce(sum(est_weight_kg) FILTER (WHERE outcome IN ('used','donated')),0) AS s_kg,
  coalesce(sum(est_price)     FILTER (WHERE outcome IN ('used','donated')),0) AS s_money,
  coalesce(sum(co2e_kg)       FILTER (WHERE outcome IN ('used','donated')),0) AS s_co2,
  count(*) FILTER (WHERE outcome = 'thrown_out')                              AS w_count,
  coalesce(sum(est_weight_kg) FILTER (WHERE outcome = 'thrown_out'),0)        AS w_kg,
  coalesce(sum(est_price)     FILTER (WHERE outcome = 'thrown_out'),0)        AS w_money,
  coalesce(sum(co2e_kg)       FILTER (WHERE outcome = 'thrown_out'),0)        AS w_co2
FROM food_events
WHERE user_id = :uid AND event_type = 'remove' {since_clause}
"""

_WEEKLY = """
SELECT time_bucket('1 week', time) AS week,
       count(*) FILTER (WHERE outcome IN ('used','donated')) AS saved,
       count(*) FILTER (WHERE outcome = 'thrown_out')        AS wasted
FROM food_events
WHERE user_id = :uid AND event_type = 'remove' {since_clause}
GROUP BY week ORDER BY week
"""


from types import SimpleNamespace

_ZERO = SimpleNamespace(s_count=0, s_kg=0, s_money=0, s_co2=0, w_count=0, w_kg=0, w_money=0, w_co2=0)


@bp.get("/impact")
@require_auth
def get_impact():
    rng = request.args.get("range", "all")
    if rng not in _RANGE_DAYS:
        raise validation_error("range must be week, month or all.")
    days = _RANGE_DAYS[rng]
    since = db.session.execute(text("SELECT now() - make_interval(days => :d)"),
                               {"d": days}).scalar() if days else None
    params = {"uid": g.user.id}
    clause = ""
    if since is not None:
        params["since"], clause = since, "AND time >= :since"
    t = db.session.execute(text(_TOTALS.format(since_clause=clause)), params).first()
    weekly = db.session.execute(text(_WEEKLY.format(since_clause=clause)), params).all()
    if t is None:  # observed once under TimescaleDB 2.17: an ungrouped aggregate returned no row
        t = _ZERO
    total = t.s_count + t.w_count
    r = lambda v: round(float(v), 2)
    return jsonify(
        saved={"count": t.s_count, "kg": r(t.s_kg), "money": r(t.s_money), "co2e_kg": r(t.s_co2)},
        wasted={"count": t.w_count, "kg": r(t.w_kg), "money": r(t.w_money), "co2e_kg": r(t.w_co2)},
        waste_rate=t.w_count / total if total else 0.0,
        weekly=[{"week": w.week.date().isoformat(), "saved": w.saved, "wasted": w.wasted}
                for w in weekly],
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
    items = (Item.query.filter(Item.owner_id == g.user.id, Item.removed_at.is_(None))
             .order_by(Item.predicted_expiry).limit(20).all())
    if not items:
        return jsonify(recipes=[])
    payload = [{"name": i.name, "category": i.category, "quantity": float(i.quantity),
                "unit": i.unit, "expires": i.predicted_expiry.isoformat()} for i in items]
    try:
        recipes = gemini.suggest_recipes(payload, n, dietary)
    except gemini.UpstreamError as e:
        raise upstream_unavailable(str(e))
    return jsonify(recipes=recipes)
