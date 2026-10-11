import math
import uuid
from datetime import date, datetime

from flask import request

from ..errors import ApiError, not_found, validation_error
from ..services import food_group


def json_body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise validation_error("Request body must be a JSON object.")
    return body


def parse_uuid(value, *, missing_ok=False):
    if value is None and missing_ok:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise validation_error("Invalid UUID.")


def path_uuid(value):
    """Path ids that are malformed cannot exist -> 404."""
    try:
        return uuid.UUID(value)
    except ValueError:
        raise not_found("Item not found.")


def parse_date(value, field):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise validation_error(f"{field} must be an ISO date (YYYY-MM-DD).")


# Upper bounds (BE-9). est_price is numeric(10,2): the largest storable value is 99,999,999.99 and
# anything bigger overflows in Postgres (was a 500). quantity / est_weight_kg are unbounded numeric
# columns, but huge finite floats overflow to inf in the derived weight / CO2e maths and the JSON
# output, so they get generous sanity caps.
MAX_NUMBER = {
    "est_price": 99_999_999.99,
    "quantity": 1_000_000,
    "est_weight_kg": 100_000,
}


def parse_number(value, field, *, positive=False, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise validation_error(f"{field} must be a number.")
    if isinstance(value, float) and not math.isfinite(value):  # bare NaN / Infinity parse as floats
        raise validation_error(f"{field} must be a finite number.")
    if value < 0 or (positive and value == 0):
        raise validation_error(f"{field} must be {'positive' if positive else 'non-negative'}.")
    hi = MAX_NUMBER.get(field)
    if hi is not None and value > hi:
        raise validation_error(f"{field} must be at most {hi:,}.")
    return value


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def f(num):
    return float(num) if num is not None else None


def serialize_item(i, share=None, include_share=True) -> dict:
    """`share` is the owner-view listing summary (see `share_summaries`); `include_share=False`
    omits the key (group pantry / other users' views)."""
    out = {
        "id": str(i.id), "owner_id": str(i.owner_id),
        "group_id": str(i.group_id) if i.group_id else None,
        "name": i.name, "category": i.category,
        "food_group": i.food_group or food_group.derive(i.category, i.name), "storage": i.storage,
        "quantity": f(i.quantity), "unit": i.unit, "est_weight_kg": f(i.est_weight_kg),
        "est_price": f(i.est_price), "source": i.source, "added_at": iso(i.added_at),
        "predicted_expiry": i.predicted_expiry.isoformat(), "expiry_source": i.expiry_source,
        "removed_at": iso(i.removed_at), "outcome": i.outcome, "waste_reason": i.waste_reason,
        "removed_after_expiry": i.removed_after_expiry,
        "freshness": i.freshness, "freshness_checked_at": iso(i.freshness_checked_at),
        "confidence": i.confidence,
    }
    if include_share:
        out["share"] = share
    return out


def share_summaries(item_ids) -> dict:
    """{item_id: {id, status, claimed_by: {id, name}|None}} for the most recent NOT-cancelled listing of
    each item, in ONE query (no N+1). Items without such a listing are absent from the dict."""
    from ..extensions import db
    from ..models import ShareListing, User
    ids = list(item_ids)
    if not ids:
        return {}
    rows = (db.session.query(ShareListing, User.id, User.display_name)
            .outerjoin(User, User.id == ShareListing.claimed_by)
            .filter(ShareListing.item_id.in_(ids), ShareListing.status != "cancelled")
            .order_by(ShareListing.created_at.desc(), ShareListing.id).all())
    out = {}
    for l, uid, name in rows:
        if l.item_id in out:
            continue
        out[l.item_id] = {"id": str(l.id), "status": l.status,
                          "claimed_by": {"id": str(uid), "name": name} if uid else None}
    return out


def serialize_listing(l) -> dict:
    return {
        "id": str(l.id), "item_id": str(l.item_id), "owner_id": str(l.owner_id),
        "group_id": str(l.group_id) if l.group_id else None, "status": l.status,
        "recipient_id": str(l.recipient_id) if l.recipient_id else None,
        "claimed_by": str(l.claimed_by) if l.claimed_by else None,
        "created_at": iso(l.created_at), "fulfilled_at": iso(l.fulfilled_at),
    }


__all__ = ["ApiError"]
