from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, exists, or_

from ..auth import require_auth
from ..errors import ApiError, not_found, validation_error
from ..extensions import db
from ..models import GroupMember, HelpRequest, RequestAudience, User
from ..services import social
from ._util import iso, json_body, parse_uuid, path_uuid

bp = Blueprint("requests", __name__, url_prefix="/requests")

MAX_GROUP_IDS = 50


def _ser(r, author, audiences, me, my_groups, friends_with_author, fulfiller=None):
    view = social.audience_view(r.author_id, audiences, me, my_groups, friends_with_author)
    first_group = view["groups"][0] if view["groups"] else None
    if r.author_id == me:
        source = {"type": "me", "name": author.display_name}
    elif first_group:
        source = {"type": "group", "name": first_group["name"]}
    else:
        source = {"type": "friend", "name": author.display_name}
    return {"id": str(r.id), "author_id": str(r.author_id), "author_name": author.display_name,
            # Deprecated (one release): the first audience group the caller can see, else null.
            "group_id": first_group["id"] if first_group else None,
            "group_name": first_group["name"] if first_group else None,
            "audiences": view,
            "text": r.text, "status": r.status,
            "fulfilled_by": str(r.fulfilled_by) if r.fulfilled_by else None,
            "fulfilled_by_name": fulfiller.display_name if fulfiller else None,
            "created_at": iso(r.created_at), "source": source}


def _visible_request(request_id):
    """(request, its audiences) or 404 if the caller cannot see it."""
    r = db.session.execute(db.select(HelpRequest).where(HelpRequest.id == path_uuid(request_id))
                           .with_for_update()).scalar_one_or_none()
    if r is None:
        raise not_found("Request not found.")
    auds = social.request_audiences([r.id])[r.id]
    me = g.user.id
    aud_groups = [a.group_id for a in auds if a.kind == "group"]
    my_group_ids = set(db.session.scalars(db.select(GroupMember.group_id).where(
        GroupMember.user_id == me, GroupMember.group_id.in_(aud_groups)))) if aud_groups else set()
    friends = r.author_id != me and any(a.kind == "friends" for a in auds) and social.are_friends(r.author_id, me)
    if not social.request_visible(r.author_id, auds, me, my_group_ids, friends):
        raise not_found("Request not found.")
    return r, auds


def _one(r, auds, fulfiller_id=None):
    me = g.user.id
    groups = social.my_groups(me)
    friends = r.author_id != me and social.are_friends(r.author_id, me)
    author = db.session.get(User, r.author_id)
    fid = fulfiller_id or r.fulfilled_by
    return _ser(r, author, auds, me, groups, friends, db.session.get(User, fid) if fid else None)


def _parse_audiences(body) -> tuple[bool, list]:
    """-> (friends, [group_id, ...] deduplicated, order kept). Validates shape and membership."""
    me = g.user.id
    if "audiences" in body:
        if "group_id" in body:
            raise validation_error("Send audiences or the deprecated group_id, not both.")
        aud = body["audiences"]
        if not isinstance(aud, dict):
            raise validation_error("audiences must be an object.")
        friends = aud.get("friends", False)
        if not isinstance(friends, bool):
            raise validation_error("audiences.friends must be a boolean.")
        raw = aud.get("group_ids", [])
        if not isinstance(raw, list):
            raise validation_error("audiences.group_ids must be a list of group ids.")
        if len(raw) > MAX_GROUP_IDS:
            raise validation_error(f"audiences.group_ids may hold at most {MAX_GROUP_IDS} groups.")
        group_ids = list(dict.fromkeys(parse_uuid(x) for x in raw))
        if not friends and not group_ids:
            raise validation_error("Choose at least one audience: friends or a group.")
        if group_ids:
            mine = set(db.session.scalars(db.select(GroupMember.group_id).where(
                GroupMember.user_id == me, GroupMember.group_id.in_(group_ids))))
            if len(mine) != len(group_ids):
                # Unknown group or one you are not in: same 404, so group ids do not leak.
                raise not_found("Group not found.")
        return friends, group_ids
    # Deprecated single-scope body: no group_id = friends, group_id = that group (404 unknown, 403 not in it).
    group_id = parse_uuid(body.get("group_id"), missing_ok=True)
    if group_id is None:
        return True, []
    social.require_member(group_id, me)
    return False, [group_id]


@bp.post("")
@require_auth
def create_request():
    body = json_body()
    text = body.get("text")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 280:
        raise validation_error("text must be 1-280 characters.")
    friends, group_ids = _parse_audiences(body)
    r = HelpRequest(author_id=g.user.id, text=text.strip(), status="open")
    db.session.add(r)
    db.session.flush()
    auds = ([RequestAudience(request_id=r.id, kind="friends")] if friends else []) + [
        RequestAudience(request_id=r.id, kind="group", group_id=gid) for gid in group_ids]
    db.session.add_all(auds)
    db.session.commit()
    return jsonify(request=_one(r, auds)), 201


def _mine_flag() -> bool:
    raw = request.args.get("mine")
    if raw is None:
        return False
    if raw.strip().lower() in ("1", "true"):
        return True
    raise validation_error("mine must be 1 or true.")


@bp.get("")
@require_auth
def board():
    """Fixed query count: my groups, my friends, the board rows (+ authors), their audiences.
    `?mine=1`: only my own requests, every status (+ the fulfillers' names in one more query)."""
    me = g.user.id
    if _mine_flag():
        groups = social.my_groups(me)
        rows = (db.session.query(HelpRequest, User).join(User, User.id == HelpRequest.author_id)
                .filter(HelpRequest.author_id == me)
                .order_by(HelpRequest.created_at.desc(), HelpRequest.id).all())
        fids = {r.fulfilled_by for r, _ in rows if r.fulfilled_by}
        fulfillers = {u.id: u for u in User.query.filter(User.id.in_(fids)).all()} if fids else {}
        auds = social.request_audiences(r.id for r, _ in rows)
        return jsonify(requests=[_ser(r, u, auds[r.id], me, groups, False, fulfillers.get(r.fulfilled_by))
                                 for r, u in rows])
    groups = social.my_groups(me)
    friends = social.friend_ids(me)
    ra = RequestAudience
    visible = [HelpRequest.author_id == me]
    if friends:
        visible.append(and_(HelpRequest.author_id.in_(friends),
                            exists().where(ra.request_id == HelpRequest.id, ra.kind == "friends")))
    if groups:
        visible.append(exists().where(ra.request_id == HelpRequest.id, ra.kind == "group",
                                      ra.group_id.in_(list(groups))))
    rows = (db.session.query(HelpRequest, User).join(User, User.id == HelpRequest.author_id)
            .filter(HelpRequest.status == "open", or_(*visible))
            .order_by(HelpRequest.created_at.desc(), HelpRequest.id).all())
    auds = social.request_audiences(r.id for r, _ in rows)
    return jsonify(requests=[_ser(r, u, auds[r.id], me, groups, r.author_id in friends)
                             for r, u in rows])


@bp.post("/<request_id>/fulfil")
@require_auth
def fulfil(request_id):
    r, auds = _visible_request(request_id)
    if r.author_id == g.user.id:
        raise ApiError(403, "forbidden", "You cannot fulfil your own request.")
    if r.status != "open":
        raise ApiError(409, "request_closed", f"Request is already {r.status}.")
    r.status, r.fulfilled_by = "fulfilled", g.user.id
    db.session.commit()
    return jsonify(request=_one(r, auds))


@bp.delete("/<request_id>")
@require_auth
def cancel(request_id):
    r, auds = _visible_request(request_id)
    if r.author_id != g.user.id:
        raise ApiError(403, "forbidden", "Only the author can cancel a request.")
    if r.status != "open":
        raise ApiError(409, "request_closed", f"Request is already {r.status}.")
    r.status = "cancelled"
    db.session.commit()
    return jsonify(request=_one(r, auds))
