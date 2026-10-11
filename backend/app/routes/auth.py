import re

from flask import Blueprint, Response, g, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import make_token, require_auth
from ..errors import ApiError, validation_error
from ..extensions import db
from ..models import (TOMBSTONE_USER_ID, FoodEvent, Friendship, Group, GroupMember, HelpRequest, Item,
                      ShareListing, User)
from ._util import iso, json_body

bp = Blueprint("auth", __name__, url_prefix="/auth")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _user(u):
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name,
            "created_at": iso(u.created_at)}


def _str(body, key):
    v = body.get(key)
    if not isinstance(v, str) or not v.strip():
        raise validation_error(f"{key} is required.")
    return v.strip()


@bp.post("/signup")
def signup():
    body = json_body()
    email = _str(body, "email").lower()
    name = _str(body, "display_name")
    password = body.get("password")
    if not _EMAIL.match(email):
        raise validation_error("email is not a valid address.")
    if not isinstance(password, str) or len(password) < 8:
        raise validation_error("password must be at least 8 characters.")
    if User.query.filter_by(email=email).first():
        raise ApiError(409, "email_taken", "An account with that email already exists.")
    user = User(email=email, display_name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError(409, "email_taken", "An account with that email already exists.")
    return jsonify(token=make_token(user.id), user=_user(user)), 201


@bp.post("/login")
def login():
    body = json_body()
    email = _str(body, "email").lower()
    password = body.get("password")
    user = User.query.filter_by(email=email).first()
    if not user or not isinstance(password, str) or not check_password_hash(user.password_hash, password):
        raise ApiError(401, "invalid_credentials", "Incorrect email or password.")
    return jsonify(token=make_token(user.id), user=_user(user))


@bp.delete("/me")
@require_auth
def delete_account():
    """Delete the caller and everything they own, in one transaction (App Store requirement).

    Deleted: their items, listings on those items and their own listings, friendships, group
    memberships, requests they wrote. Detached from other people's rows: listings they claimed or
    received (claimed_by/recipient_id -> null, so the listing is open again), requests they fulfilled
    (reopened). Groups they created lose `created_by` (ownership passes to the longest-standing
    remaining member). food_events are ANONYMISED, not deleted: user_id -> the nil-UUID tombstone, so
    aggregate data survives but nothing links to a person.
    """
    uid = g.user.id
    item_ids = db.select(Item.id).where(Item.owner_id == uid)
    # Ownership of groups they owned passes on before their membership goes.
    for m in GroupMember.query.filter_by(user_id=uid, role="owner").all():
        heir = (GroupMember.query.filter(GroupMember.group_id == m.group_id, GroupMember.user_id != uid)
                .order_by(GroupMember.joined_at).first())
        if heir:
            heir.role = "owner"
    Group.query.filter_by(created_by=uid).update({"created_by": None})
    GroupMember.query.filter_by(user_id=uid).delete()
    ShareListing.query.filter(ShareListing.owner_id == uid).delete(synchronize_session=False)
    ShareListing.query.filter(ShareListing.item_id.in_(item_ids)).delete(synchronize_session=False)
    ShareListing.query.filter_by(claimed_by=uid).update({"claimed_by": None})
    ShareListing.query.filter_by(recipient_id=uid).update({"recipient_id": None})
    HelpRequest.query.filter_by(author_id=uid).delete()
    HelpRequest.query.filter_by(fulfilled_by=uid).update({"status": "open", "fulfilled_by": None})
    Friendship.query.filter((Friendship.user_id == uid) | (Friendship.friend_id == uid)
                            ).delete(synchronize_session=False)
    FoodEvent.query.filter_by(user_id=uid).update({"user_id": TOMBSTONE_USER_ID}, synchronize_session=False)
    Item.query.filter_by(owner_id=uid).delete()
    User.query.filter_by(id=uid).delete()
    db.session.commit()
    return Response(status=204)
