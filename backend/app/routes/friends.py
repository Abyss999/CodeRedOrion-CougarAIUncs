from flask import Blueprint, g, jsonify
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from ..auth import require_auth
from ..errors import ApiError, not_found, validation_error
from ..extensions import db
from ..models import Friendship, User
from ..services import social
from ._util import check_len, iso, json_body, path_uuid

bp = Blueprint("friends", __name__, url_prefix="/friends")


def _entry(other, row):
    return {"user_id": str(other.id), "display_name": other.display_name,
            "status": row.status, "created_at": iso(row.created_at)}


@bp.get("/code")
@require_auth
def my_code():
    code, expires_at = social.make_friend_code(g.user.id)
    return jsonify(code=code, expires_at=iso(expires_at), url=f"bitedown://friend/{code}")


def _add_by_code(code):
    uid = social.parse_friend_code(code)
    target = db.session.get(User, uid) if uid is not None else None
    if target is None:
        raise ApiError(400, "invalid_code", "That code isn't valid any more.")
    if target.id == g.user.id:
        raise validation_error("You cannot add yourself.")
    existing = social.friendship_between(g.user.id, target.id)
    if existing is not None:
        if existing.status != "accepted":
            existing.status = "accepted"  # pending in either direction: the scan settles it
            db.session.commit()
        return jsonify(friend=_entry(target, existing)), 200  # already friends: idempotent
    row = Friendship(user_id=g.user.id, friend_id=target.id, status="accepted")
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = social.friendship_between(g.user.id, target.id)  # lost a race: settle it
        if existing is None:
            raise ApiError(409, "request_pending", "A friend request is already pending.")
        if existing.status != "accepted":
            existing.status = "accepted"
            db.session.commit()
        return jsonify(friend=_entry(target, existing)), 200
    return jsonify(friend=_entry(target, row)), 201


@bp.post("")
@require_auth
def send_request():
    body = json_body()
    email, code = body.get("email"), body.get("code")
    if (email is None) == (code is None):
        raise validation_error("Provide exactly one of email or code.")
    if code is not None:
        if not isinstance(code, str) or not code.strip():
            raise validation_error("code must be a non-empty string.")
        return _add_by_code(code.strip())
    if not isinstance(email, str) or not email.strip():
        raise validation_error("email is required.")
    check_len(email, "email", 254)
    target = User.query.filter_by(email=email.strip().lower()).first()
    if target is None:
        raise not_found("No user with that email.")
    if target.id == g.user.id:
        raise validation_error("You cannot add yourself.")
    existing = social.friendship_between(g.user.id, target.id)
    if existing is not None:
        code = "already_friends" if existing.status == "accepted" else "request_pending"
        raise ApiError(409, code, "Already friends." if code == "already_friends"
                       else "A friend request is already pending.")
    row = Friendship(user_id=g.user.id, friend_id=target.id, status="pending")
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError(409, "request_pending", "A friend request is already pending.")
    return jsonify(friend=_entry(target, row)), 201


@bp.post("/<user_id>/accept")
@require_auth
def accept(user_id):
    other_id = path_uuid(user_id, "User")
    row = Friendship.query.filter_by(user_id=other_id, friend_id=g.user.id, status="pending").first()
    if row is None:
        raise not_found("No pending friend request from that user.")
    row.status = "accepted"
    db.session.commit()
    return jsonify(friend=_entry(db.session.get(User, other_id), row))


@bp.get("")
@require_auth
def list_friends():
    me = g.user.id
    rows = Friendship.query.filter(or_(Friendship.user_id == me, Friendship.friend_id == me)
                                   ).order_by(Friendship.created_at.desc()).all()
    users = {u.id: u for u in User.query.filter(User.id.in_(
        {r.friend_id if r.user_id == me else r.user_id for r in rows} or {me})).all()}
    out = {"friends": [], "incoming": [], "outgoing": []}
    for r in rows:
        other = users[r.friend_id if r.user_id == me else r.user_id]
        bucket = ("friends" if r.status == "accepted"
                  else "outgoing" if r.user_id == me else "incoming")
        out[bucket].append(_entry(other, r))
    return jsonify(**out)


@bp.delete("/<user_id>")
@require_auth
def remove(user_id):
    row = social.friendship_between(g.user.id, path_uuid(user_id, "User"))
    if row is None:
        raise not_found("No friendship or request with that user.")
    db.session.delete(row)
    db.session.commit()
    return "", 204
