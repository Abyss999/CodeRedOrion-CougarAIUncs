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


# ---------- request audiences ----------
def request_audiences(request_ids) -> dict:
    """{request_id: [RequestAudience, ...]} for all the given requests in ONE query."""
    from ..models import RequestAudience
    ids = list(request_ids)
    out = {rid: [] for rid in ids}
    if not ids:
        return out
    rows = (RequestAudience.query.filter(RequestAudience.request_id.in_(ids))
            .order_by(RequestAudience.created_at, RequestAudience.id).all())
    for a in rows:
        out[a.request_id].append(a)
    return out


def request_visible(author_id, audiences, uid, my_group_ids, friends_with_author: bool) -> bool:
    """The author always; accepted friends if a `friends` audience exists; current members of any
    `group` audience. `friends_with_author` is whether `uid` and the author are accepted friends."""
    if author_id == uid:
        return True
    return any((a.kind == "friends" and friends_with_author)
               or (a.kind == "group" and a.group_id in my_group_ids) for a in audiences)


def audience_view(author_id, audiences, uid, my_groups: dict, friends_with_author: bool) -> dict:
    """What the caller may see of a request's audiences. `friends` is shown to the author and the
    author's accepted friends; a group only to its current members. Everything else is counted in
    `hidden_count` and never named."""
    friends = False
    groups, hidden_n = [], 0
    for a in audiences:
        if a.kind == "friends":
            if author_id == uid or friends_with_author:
                friends = True
            else:
                hidden_n += 1
        elif a.group_id in my_groups:
            groups.append({"id": str(a.group_id), "name": my_groups[a.group_id].name})
        else:
            hidden_n += 1
    groups.sort(key=lambda x: (x["name"].casefold(), x["id"]))
    return {"friends": friends, "groups": groups, "hidden_count": hidden_n}
