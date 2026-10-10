from flask import Blueprint, g, jsonify

from ..auth import require_auth
from ..errors import ApiError, not_found, validation_error
from ..extensions import db
from ..models import FoodEvent, Item, ShareListing
from ._util import json_body, parse_uuid, serialize_listing

bp = Blueprint("share", __name__, url_prefix="/share")


@bp.post("")
@require_auth
def create_listing():
    body = json_body()
    if body.get("item_id") is None:
        raise validation_error("item_id is required.")
    item_id = parse_uuid(body["item_id"])
    group_id = parse_uuid(body.get("group_id"), missing_ok=True)
    item = db.session.execute(db.select(Item).where(Item.id == item_id).with_for_update()
                              ).scalar_one_or_none()
    if item is None:
        raise not_found("Item not found.")
    if item.owner_id != g.user.id:
        raise ApiError(403, "forbidden", "This item belongs to another user.")
    if item.removed_at is not None:
        raise ApiError(409, "already_removed", "Item has already been removed.")
    if ShareListing.query.filter_by(item_id=item.id, status="open").first():
        raise ApiError(409, "already_shared", "Item already has an open listing.")
    listing = ShareListing(item_id=item.id, owner_id=g.user.id, group_id=group_id, status="open")
    db.session.add(listing)
    db.session.add(FoodEvent(user_id=g.user.id, item_id=item.id, group_id=group_id,
                             event_type="share", category=item.category, quantity=item.quantity,
                             est_weight_kg=item.est_weight_kg, est_price=item.est_price))
    db.session.commit()
    return jsonify(listing=serialize_listing(listing)), 201
