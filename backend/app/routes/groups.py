from flask import Blueprint, g, jsonify
from sqlalchemy import func

from ..auth import require_auth
from ..errors import ApiError, not_found, validation_error
from ..extensions import db
from ..models import (Group, GroupMember, HelpRequest, Item, RequestAudience, ShareListing, User)
from ..services import social
from ._util import iso, json_body, path_uuid, serialize_item

bp = Blueprint("groups", __name__, url_prefix="/groups")


def _group(group, role, member_count):
    return {"id": str(group.id), "name": group.name, "role": role, "member_count": member_count,
            "invite_code": group.invite_code, "created_by": str(group.created_by) if group.created_by else None,
            "created_at": iso(group.created_at)}


def _count(group_id):
    return GroupMember.query.filter_by(group_id=group_id).count()


@bp.post("")
@require_auth
def create_group():
    name = json_body().get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
        raise validation_error("name must be 1-60 characters.")
    group = Group(name=name.strip(), created_by=g.user.id, invite_code=social.new_invite_code())
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMember(group_id=group.id, user_id=g.user.id, role="owner"))
    db.session.commit()
    return jsonify(group=_group(group, "owner", 1)), 201


@bp.get("")
@require_auth
def list_groups():
    rows = (db.session.query(Group, GroupMember.role,
                             db.select(func.count()).where(GroupMember.group_id == Group.id)
                             .correlate(Group).scalar_subquery())
            .join(GroupMember, GroupMember.group_id == Group.id)
            .filter(GroupMember.user_id == g.user.id).order_by(Group.created_at).all())
    return jsonify(groups=[_group(grp, role, n) for grp, role, n in rows])


@bp.post("/join")
@require_auth
def join():
    code = json_body().get("invite_code")
    if not isinstance(code, str) or not code.strip():
        raise validation_error("invite_code is required.")
    group = Group.query.filter_by(invite_code=social.normalize_code(code)).first()
    if group is None:
        raise not_found("No group with that invite code.")
    if social.membership(group.id, g.user.id):
        raise ApiError(409, "already_member", "You are already in this group.")
    db.session.add(GroupMember(group_id=group.id, user_id=g.user.id, role="member"))
    db.session.commit()
    return jsonify(group=_group(group, "member", _count(group.id))), 200


@bp.get("/<group_id>")
@require_auth
def get_group(group_id):
    gid = path_uuid(group_id)
    group = social.require_member(gid, g.user.id)
    members = (db.session.query(User, GroupMember).join(GroupMember, GroupMember.user_id == User.id)
               .filter(GroupMember.group_id == gid).order_by(GroupMember.joined_at).all())
    me = social.membership(gid, g.user.id)
    body = _group(group, me.role, len(members))
    body["members"] = [{"user_id": str(u.id), "display_name": u.display_name, "role": m.role,
                        "joined_at": iso(m.joined_at)} for u, m in members]
    return jsonify(group=body)


@bp.post("/<group_id>/leave")
@require_auth
def leave(group_id):
    gid = path_uuid(group_id)
    social.require_member(gid, g.user.id)
    me = social.membership(gid, g.user.id)
    was_owner = me.role == "owner"
    db.session.delete(me)
    db.session.flush()
    # Anything the leaver offered into this group would otherwise stay visible to it.
    ShareListing.query.filter_by(owner_id=g.user.id, group_id=gid, status="open"
                                 ).update({"status": "cancelled"})
    # The leaver's open requests lose only this group's audience; one with no other audience is
    # cancelled instead (its last audience row is kept as history). Closed requests are untouched.
    ra = RequestAudience
    here = db.session.execute(
        db.select(ra.id, ra.request_id).join(HelpRequest, HelpRequest.id == ra.request_id)
        .where(HelpRequest.author_id == g.user.id, HelpRequest.status == "open",
               ra.kind == "group", ra.group_id == gid).with_for_update(of=HelpRequest)).all()
    if here:
        counts = dict(db.session.execute(
            db.select(ra.request_id, func.count()).where(ra.request_id.in_([rid for _, rid in here]))
            .group_by(ra.request_id)).all())
        sole = [rid for _, rid in here if counts[rid] == 1]
        drop = [aid for aid, rid in here if counts[rid] > 1]
        if sole:
            HelpRequest.query.filter(HelpRequest.id.in_(sole)).update({"status": "cancelled"},
                                                                      synchronize_session=False)
        if drop:
            ra.query.filter(ra.id.in_(drop)).delete(synchronize_session=False)
    if was_owner:
        heir = (GroupMember.query.filter_by(group_id=gid).order_by(GroupMember.joined_at).first())
        if heir:
            heir.role = "owner"
    db.session.commit()
    return jsonify(left=True)


@bp.get("/<group_id>/pantry")
@require_auth
def pantry(group_id):
    gid = path_uuid(group_id)
    social.require_member(gid, g.user.id)
    rows = (db.session.query(Item, User.display_name).join(User, User.id == Item.owner_id)
            .filter(Item.group_id == gid, Item.removed_at.is_(None))
            .order_by(Item.predicted_expiry, Item.added_at).all())
    return jsonify(items=[serialize_item(i, include_share=False) | {"added_by": name} for i, name in rows])
