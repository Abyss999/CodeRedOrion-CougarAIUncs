from flask import Blueprint, g, jsonify, request

from ..auth import require_auth
from ..errors import not_found
from ..extensions import db
from ..models import GroupMember, Item, ShareListing, User
from ..services import social
from ._util import parse_uuid

bp = Blueprint("people", __name__, url_prefix="/people")


def _can_see_item(item, me) -> bool:
    """Owner; a member of the item's group pantry; or anyone the item's open listing is visible to."""
    if item.group_id is not None:  # group pantry: CURRENT membership only (an ex-member owner is out)
        if social.membership(item.group_id, me) is not None:
            return True
    elif item.owner_id == me:
        return True
    listing = ShareListing.query.filter_by(item_id=item.id, status="open").first()
    if listing is None:
        return False
    if listing.group_id is not None:
        return social.membership(listing.group_id, me) is not None
    return social.are_friends(listing.owner_id, me)


@bp.get("/reachable")
@require_auth
def reachable():
    """Everyone the caller may hand food to: accepted friends plus current fellow group members, one
    entry per person. Constant query count (friends, my groups, fellow members, the reachable check,
    the users), however many friends or groups. `?item_id=`: the claimer of the owner's open listing
    is flagged `is_claimer` and sorts first."""
    me = g.user.id
    claimer_id = None
    raw_item = request.args.get("item_id")
    if raw_item is not None:
        item = db.session.get(Item, parse_uuid(raw_item))
        if item is None or not _can_see_item(item, me):
            raise not_found("Item not found.")
        if item.owner_id == me:  # only the owner learns who claimed it
            claimer_id = db.session.scalar(db.select(ShareListing.claimed_by).where(
                ShareListing.item_id == item.id, ShareListing.status == "open").limit(1))

    friends = social.friend_ids(me)
    groups = social.my_groups(me)
    shared = {}  # user_id -> [group, ...] they share with the caller
    if groups:
        for uid, gid in db.session.execute(db.select(GroupMember.user_id, GroupMember.group_id).where(
                GroupMember.group_id.in_(list(groups)), GroupMember.user_id != me)).all():
            shared.setdefault(uid, []).append(groups[gid])
    ids = social.reachable_users(me, friends | set(shared))
    users = User.query.filter(User.id.in_(ids)).all() if ids else []

    people = [{"id": str(u.id), "display_name": u.display_name,
               "kind": "friend" if u.id in friends else "group_member",
               "groups": [{"id": str(gr.id), "name": gr.name}
                          for gr in sorted(shared.get(u.id, []), key=lambda x: (x.name.casefold(), str(x.id)))],
               "is_claimer": claimer_id is not None and u.id == claimer_id} for u in users]
    people.sort(key=lambda p: (not p["is_claimer"], p["display_name"].casefold(), p["id"]))
    return jsonify(people=people)
