"""Visibility primitives for the social layer. Everything a user may see flows through here."""
import secrets

from sqlalchemy import or_

from ..errors import ApiError, not_found
from ..extensions import db
from ..models import Friendship, Group, GroupMember

# No 0/O, 1/I/L: codes get read aloud and typed by hand.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 8


def new_invite_code() -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
        if not Group.query.filter_by(invite_code=code).first():
            return code


def normalize_code(raw: str) -> str:
    return raw.strip().upper().replace("-", "").replace(" ", "")


def friendship_between(a, b):
    return Friendship.query.filter(
        or_((Friendship.user_id == a) & (Friendship.friend_id == b),
            (Friendship.user_id == b) & (Friendship.friend_id == a))).first()


def are_friends(a, b) -> bool:
    f = friendship_between(a, b)
    return f is not None and f.status == "accepted"


def friend_ids(uid) -> set:
    rows = Friendship.query.filter(
        Friendship.status == "accepted",
        or_(Friendship.user_id == uid, Friendship.friend_id == uid)).all()
    return {r.friend_id if r.user_id == uid else r.user_id for r in rows}


def my_groups(uid) -> dict:
    """{group_id: Group} for every group the user belongs to."""
    rows = (db.session.query(Group).join(GroupMember, GroupMember.group_id == Group.id)
            .filter(GroupMember.user_id == uid).all())
    return {g.id: g for g in rows}


def membership(group_id, uid):
    return db.session.get(GroupMember, (group_id, uid))


def require_member(group_id, uid) -> Group:
    """404 if the group does not exist, 403 if the caller is not in it."""
    group = db.session.get(Group, group_id)
    if group is None:
        raise not_found("Group not found.")
    if membership(group_id, uid) is None:
        raise ApiError(403, "forbidden", "You are not a member of this group.")
    return group
