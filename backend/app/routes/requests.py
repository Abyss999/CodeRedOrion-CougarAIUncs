from flask import Blueprint, g, jsonify
from sqlalchemy import and_, or_

from ..auth import require_auth
from ..errors import ApiError, not_found, validation_error
from ..extensions import db
from ..models import HelpRequest, User
from ..services import social
from ._util import iso, json_body, parse_uuid, path_uuid

bp = Blueprint("requests", __name__, url_prefix="/requests")


def _ser(r, author, groups, me, fulfiller=None):
    if r.author_id == me:
        source = {"type": "me", "name": author.display_name}
    elif r.group_id:
        source = {"type": "group", "name": groups[r.group_id].name}
    else:
        source = {"type": "friend", "name": author.display_name}
    return {"id": str(r.id), "author_id": str(r.author_id), "author_name": author.display_name,
            "group_id": str(r.group_id) if r.group_id else None,
            "group_name": groups[r.group_id].name if r.group_id in groups else None,
            "text": r.text, "status": r.status,
            "fulfilled_by": str(r.fulfilled_by) if r.fulfilled_by else None,
            "fulfilled_by_name": fulfiller.display_name if fulfiller else None,
            "created_at": iso(r.created_at), "source": source}


def _visible_to(r, uid) -> bool:
    if r.author_id == uid:
        return True
    if r.group_id is not None:
        return social.membership(r.group_id, uid) is not None
    return social.are_friends(r.author_id, uid)


def _visible_request(request_id) -> HelpRequest:
    r = db.session.execute(db.select(HelpRequest).where(HelpRequest.id == path_uuid(request_id))
                           .with_for_update()).scalar_one_or_none()
    if r is None or not _visible_to(r, g.user.id):
        raise not_found("Request not found.")
    return r


def _one(r, fulfiller_id=None):
    groups = social.my_groups(g.user.id)
    author = db.session.get(User, r.author_id)
    fid = fulfiller_id or r.fulfilled_by
    return _ser(r, author, groups, g.user.id, db.session.get(User, fid) if fid else None)


@bp.post("")
@require_auth
def create_request():
    body = json_body()
    text = body.get("text")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 280:
        raise validation_error("text must be 1-280 characters.")
    group_id = parse_uuid(body.get("group_id"), missing_ok=True)
    if group_id is not None:
        social.require_member(group_id, g.user.id)
    r = HelpRequest(author_id=g.user.id, group_id=group_id, text=text.strip(), status="open")
    db.session.add(r)
    db.session.commit()
    return jsonify(request=_one(r)), 201


@bp.get("")
@require_auth
def board():
    me = g.user.id
    groups = social.my_groups(me)
    friends = social.friend_ids(me)
    visible = or_(
        HelpRequest.author_id == me,
        and_(HelpRequest.group_id.is_(None), HelpRequest.author_id.in_(friends or {me})),
        HelpRequest.group_id.in_(list(groups) or [me]))
    rows = (db.session.query(HelpRequest, User).join(User, User.id == HelpRequest.author_id)
            .filter(HelpRequest.status == "open", visible)
            .order_by(HelpRequest.created_at.desc()).all())
    return jsonify(requests=[_ser(r, u, groups, me) for r, u in rows])


@bp.post("/<request_id>/fulfil")
@require_auth
def fulfil(request_id):
    r = _visible_request(request_id)
    if r.author_id == g.user.id:
        raise ApiError(403, "forbidden", "You cannot fulfil your own request.")
    if r.status != "open":
        raise ApiError(409, "request_closed", f"Request is already {r.status}.")
    r.status, r.fulfilled_by = "fulfilled", g.user.id
    db.session.commit()
    return jsonify(request=_one(r))


@bp.delete("/<request_id>")
@require_auth
def cancel(request_id):
    r = _visible_request(request_id)
    if r.author_id != g.user.id:
        raise ApiError(403, "forbidden", "Only the author can cancel a request.")
    if r.status != "open":
        raise ApiError(409, "request_closed", f"Request is already {r.status}.")
    r.status = "cancelled"
    db.session.commit()
    return jsonify(request=_one(r))
