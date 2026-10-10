"""Wave 3 social features: friends, groups, group pantries, share board, requests.

Visibility / authorization is the focus. Response shapes follow docs/API.md; the small `_rows` /
`_uid` helpers tolerate a bare list vs. a keyed object and `id` vs `user_id` so the tests assert
behaviour, not incidental naming.
"""
import uuid

import pytest

from conftest import _signup

MISSING = str(uuid.uuid4())
INVISIBLE = (404,)  # resources the caller may not see must not leak existence
NOT_MEMBER = (403,)  # API.md: group-addressed endpoints give 403 for non-members, 404 only for unknown groups


# ---------- helpers ----------
def _rows(resp, *keys):
    body = resp.get_json()
    if isinstance(body, list):
        return body
    for k in keys:
        if k in body:
            return body[k]
    raise AssertionError(f"none of {keys} in {body}")


def _uid(row):
    for k in ("user_id", "friend_id", "id"):
        if k in row:
            return row[k]
    if "user" in row:
        return row["user"]["id"]
    raise AssertionError(row)


def _one(resp, *keys):
    body = resp.get_json()
    for k in keys:
        if k in body:
            return body[k]
    return body


class W:
    """The fixture world, with small API wrappers."""

    def __init__(self, client, users, groups):
        self.c = client
        self.__dict__.update(users)
        self.G, self.H = groups

    def req(self, who, method, path, **kw):
        return getattr(self.c, method)(path, headers=who["headers"], **kw)

    def get(self, who, path, **kw):
        return self.req(who, "get", path, **kw)

    def post(self, who, path, body=None, **kw):
        return self.req(who, "post", path, json=body if body is not None else {}, **kw)

    def delete(self, who, path):
        return self.req(who, "delete", path)

    def item(self, who, **over):
        payload = {"name": "Milk", "category": "dairy", "storage": "fridge", "quantity": 2,
                   "unit": "l", "est_price": 3.5, "source": "manual"}
        payload.update(over)
        r = self.post(who, "/items", {"items": [payload]})
        assert r.status_code == 201, r.get_data(as_text=True)
        return r.get_json()["items"][0]

    def share(self, who, item, group=None):
        body = {"item_id": item["id"]}
        if group:
            body["group_id"] = group["id"]
        return self.post(who, "/share", body)

    def listings(self, who):
        r = self.get(who, "/share")
        assert r.status_code == 200, r.get_data(as_text=True)
        return _rows(r, "listings", "items")

    def requests_for(self, who):
        r = self.get(who, "/requests")
        assert r.status_code == 200, r.get_data(as_text=True)
        return _rows(r, "requests")


@pytest.fixture
def world(client):
    users = {n: _signup(client, name=n.capitalize()) for n in ("alice", "bob", "carol", "dave", "erin")}
    w = W(client, users, (None, None))
    # Alice <-> Bob accepted; Carol -> Alice pending only; Dave stranger.
    assert w.post(w.alice, "/friends", {"email": w.bob["email"]}).status_code in (200, 201)
    assert w.post(w.bob, f"/friends/{w.alice['user']['id']}/accept").status_code == 200
    assert w.post(w.carol, "/friends", {"email": w.alice["email"]}).status_code in (200, 201)
    # Group G: Alice (owner) + Erin. Group H: Dave only.
    g = w.post(w.alice, "/groups", {"name": "Flat G"})
    assert g.status_code == 201, g.get_data(as_text=True)
    G = _one(g, "group")
    h = w.post(w.dave, "/groups", {"name": "Club H"})
    assert h.status_code == 201
    H = _one(h, "group")
    j = w.post(w.erin, "/groups/join", {"invite_code": G["invite_code"]})
    assert j.status_code in (200, 201), j.get_data(as_text=True)
    w.G, w.H = G, H
    return w


def _ids(users):
    return {_uid(r) for r in users}


# ---------- friends ----------
def test_friends_lifecycle_symmetric(world):
    w = world
    a, b = w.alice["user"]["id"], w.bob["user"]["id"]
    fa = _rows(w.get(w.alice, "/friends"), "friends")
    fb = _rows(w.get(w.bob, "/friends"), "friends")
    assert b in _ids(fa) and a in _ids(fb)
    # pending Carol must not be listed as an accepted friend of Alice
    accepted = [r for r in fa if r.get("status", "accepted") == "accepted"]
    assert w.carol["user"]["id"] not in _ids(accepted)


def test_friend_request_errors(world):
    w = world
    assert w.post(w.alice, "/friends", {"email": "nobody@example.com"}).status_code == 404
    assert w.post(w.alice, "/friends", {"email": w.alice["email"]}).status_code == 400
    assert w.post(w.alice, "/friends", {"email": w.bob["email"]}).status_code == 409   # already friends
    assert w.post(w.carol, "/friends", {"email": w.alice["email"]}).status_code == 409  # already pending
    assert w.post(w.alice, "/friends", {}).status_code == 400
    assert w.post(w.alice, "/friends", {"email": w.dave["email"].upper()}).status_code in (200, 201)  # case-insens.


@pytest.mark.parametrize("path", ["/friends", "/groups", "/groups/join", "/share", "/requests"])
def test_social_routes_require_auth(client, path):
    assert client.get(path).status_code in (401, 405)
    assert client.post(path, json={}).status_code in (401, 405)


def test_accept_authorization(world):
    w = world
    a, c = w.alice["user"]["id"], w.carol["user"]["id"]
    # the requester cannot accept their own request, a stranger cannot accept someone else's
    assert w.post(w.carol, f"/friends/{a}/accept").status_code in INVISIBLE
    assert w.post(w.dave, f"/friends/{c}/accept").status_code in INVISIBLE
    assert w.post(w.bob, f"/friends/{c}/accept").status_code in INVISIBLE
    # Alice's inbound request: not yet accepted -> Carol still sees nothing of Alice
    assert w.listings(w.carol) == []
    # no pending request between these two at all
    assert w.post(w.alice, f"/friends/{w.dave['user']['id']}/accept").status_code in INVISIBLE
    assert w.post(w.alice, f"/friends/{MISSING}/accept").status_code in INVISIBLE
    assert w.post(w.alice, "/friends/not-a-uuid/accept").status_code in INVISIBLE
    # Alice accepts Carol -> becomes friends
    assert w.post(w.alice, f"/friends/{c}/accept").status_code == 200
    assert c in _ids(_rows(w.get(w.alice, "/friends"), "friends"))
    # accepting twice is not a silent success
    assert w.post(w.alice, f"/friends/{c}/accept").status_code in (404, 409)


@pytest.mark.parametrize("by", ["alice", "bob"])
def test_delete_friend_either_side(world, by):
    w = world
    a, b = w.alice["user"], w.bob["user"]
    item = w.item(w.alice)
    assert w.share(w.alice, item).status_code == 201
    assert len(w.listings(w.bob)) == 1
    me, other = (w.alice, b) if by == "alice" else (w.bob, a)
    assert w.delete(me, f"/friends/{other['id']}").status_code == 204
    assert b["id"] not in _ids(_rows(w.get(w.alice, "/friends"), "friends"))
    assert a["id"] not in _ids(_rows(w.get(w.bob, "/friends"), "friends"))
    assert w.listings(w.bob) == []
    assert w.delete(me, f"/friends/{other['id']}").status_code == 404  # already gone
    assert w.delete(w.dave, f"/friends/{a['id']}").status_code == 404  # never friends


def test_delete_pending_request_can_be_cancelled_or_declined(world):
    w = world
    assert w.delete(w.carol, f"/friends/{w.alice['user']['id']}").status_code in (200, 204, 404)


def test_friend_list_does_not_leak_other_users_graph(world):
    w = world
    assert _ids(_rows(w.get(w.dave, "/friends"), "friends")) == set()
    assert _ids(_rows(w.get(w.erin, "/friends"), "friends")) == set()
    # Bob sees Alice only
    assert _ids(_rows(w.get(w.bob, "/friends"), "friends")) == {w.alice["user"]["id"]}


# ---------- groups ----------
def test_group_create_and_list(world):
    w = world
    assert w.G["name"] == "Flat G" and w.G.get("invite_code")
    mine = _rows(w.get(w.alice, "/groups"), "groups")
    assert {g["id"] for g in mine} == {w.G["id"]}
    assert {g["id"] for g in _rows(w.get(w.erin, "/groups"), "groups")} == {w.G["id"]}
    assert _rows(w.get(w.bob, "/groups"), "groups") == []
    assert {g["id"] for g in _rows(w.get(w.dave, "/groups"), "groups")} == {w.H["id"]}
    g = w.get(w.alice, f"/groups/{w.G['id']}")
    assert g.status_code == 200
    body = _one(g, "group")
    members = body.get("members")
    if members is not None:
        assert _ids(members) == {w.alice["user"]["id"], w.erin["user"]["id"]}
    count = body.get("member_count")
    if count is not None:
        assert count == 2


def test_group_validation(world):
    w = world
    assert w.post(w.alice, "/groups", {}).status_code == 400
    assert w.post(w.alice, "/groups", {"name": ""}).status_code == 400
    assert w.post(w.alice, "/groups", {"name": "x" * 500}).status_code == 400


def test_group_join_and_errors(world):
    w = world
    code = w.G["invite_code"]
    assert w.post(w.erin, "/groups/join", {"invite_code": code}).status_code == 409
    assert w.post(w.alice, "/groups/join", {"invite_code": code}).status_code == 409
    assert w.post(w.bob, "/groups/join", {"invite_code": "NOPE-0000"}).status_code in (400, 404)
    assert w.post(w.bob, "/groups/join", {}).status_code == 400
    r = w.post(w.bob, "/groups/join", {"invite_code": code})
    assert r.status_code in (200, 201)
    assert w.get(w.bob, f"/groups/{w.G['id']}").status_code == 200
    body = _one(w.get(w.alice, f"/groups/{w.G['id']}"), "group")
    if "member_count" in body:
        assert body["member_count"] == 3


def test_group_read_blocked_for_non_members(world):
    w = world
    gid = w.G["id"]
    for who in (w.bob, w.carol, w.dave):  # friend-of-owner, pending, stranger
        assert w.get(who, f"/groups/{gid}").status_code in NOT_MEMBER
        assert w.get(who, f"/groups/{gid}/pantry").status_code in NOT_MEMBER
    assert w.get(w.alice, f"/groups/{w.H['id']}").status_code in NOT_MEMBER
    assert w.get(w.alice, f"/groups/{w.H['id']}/pantry").status_code in NOT_MEMBER
    assert w.get(w.alice, f"/groups/{MISSING}").status_code == 404
    assert w.get(w.alice, "/groups/not-a-uuid").status_code == 404


def test_group_leave(world):
    w = world
    gid = w.G["id"]
    assert w.post(w.bob, f"/groups/{gid}/leave").status_code in NOT_MEMBER  # not a member
    assert w.post(w.erin, f"/groups/{gid}/leave").status_code in (200, 204)
    assert w.get(w.erin, f"/groups/{gid}").status_code in NOT_MEMBER
    assert w.get(w.erin, f"/groups/{gid}/pantry").status_code in NOT_MEMBER
    assert _rows(w.get(w.erin, "/groups"), "groups") == []
    assert w.post(w.erin, f"/groups/{gid}/leave").status_code in NOT_MEMBER  # twice
    body = _one(w.get(w.alice, f"/groups/{gid}"), "group")
    if "member_count" in body:
        assert body["member_count"] == 1
    # Erin can rejoin with the code
    assert w.post(w.erin, "/groups/join", {"invite_code": w.G["invite_code"]}).status_code in (200, 201)


def test_group_gone_after_all_members_leave_or_owner_leaves_is_not_500(world):
    w = world
    gid = w.G["id"]
    assert w.post(w.alice, f"/groups/{gid}/leave").status_code in (200, 204)
    assert w.post(w.erin, f"/groups/{gid}/leave").status_code in (200, 204)
    assert w.get(w.alice, f"/groups/{gid}").status_code in NOT_MEMBER


# ---------- group pantry ----------
def test_group_item_add_requires_membership(world):
    w = world
    gid = w.G["id"]
    r = w.post(w.dave, "/items", {"items": [{"name": "Rice", "group_id": gid}]})
    assert r.status_code == 403
    assert w.post(w.bob, "/items", {"items": [{"name": "Rice", "group_id": gid}]}).status_code == 403
    # all-or-nothing: a bad row + good row writes nothing
    r = w.post(w.alice, "/items", {"items": [{"name": "Ok", "group_id": gid},
                                              {"name": "Bad", "group_id": w.H["id"]}]})
    assert r.status_code == 403
    assert _rows(w.get(w.alice, f"/groups/{gid}/pantry"), "items") == []
    assert w.post(w.alice, "/items", {"items": [{"name": "X", "group_id": MISSING}]}).status_code == 404
    assert w.post(w.alice, "/items", {"items": [{"name": "X", "group_id": "junk"}]}).status_code in (400, 404)


def test_group_pantry_visible_to_members_only_and_not_in_personal_list(world):
    w = world
    gid = w.G["id"]
    r = w.post(w.alice, "/items", {"items": [{"name": "Rice", "category": "pantry_dry", "group_id": gid}]})
    assert r.status_code == 201
    item = r.get_json()["items"][0]
    assert item["group_id"] == gid and item["owner_id"] == w.alice["user"]["id"]
    for who in (w.alice, w.erin):
        assert [i["id"] for i in _rows(w.get(who, f"/groups/{gid}/pantry"), "items")] == [item["id"]]
    for who in (w.bob, w.carol, w.dave):
        assert w.get(who, f"/groups/{gid}/pantry").status_code in NOT_MEMBER
    # personal pantry stays personal
    assert w.get(w.erin, "/items").get_json()["items"] == []
    assert item["id"] not in [i["id"] for i in w.get(w.alice, "/items").get_json()["items"]]
    # personal item is not in the group pantry
    mine = w.item(w.alice)
    ids = [i["id"] for i in _rows(w.get(w.alice, f"/groups/{gid}/pantry"), "items")]
    assert mine["id"] not in ids
    # add event carries the group


def test_member_removes_group_item_event_attribution(world, sql):
    w = world
    gid = w.G["id"]
    item = w.post(w.alice, "/items", {"items": [{"name": "Rice", "group_id": gid}]}).get_json()["items"][0]
    r = w.post(w.erin, f"/items/{item['id']}/remove", {"outcome": "used"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["item"]["removed_at"] and r.get_json()["item"]["outcome"] == "used"
    ev = sql("SELECT * FROM food_events WHERE item_id = :i AND event_type='remove'", i=item["id"])
    assert len(ev) == 1
    assert str(ev[0]["user_id"]) == w.erin["user"]["id"]
    assert str(ev[0]["group_id"]) == gid
    assert ev[0]["outcome"] == "used"
    # gone from the pantry
    assert _rows(w.get(w.alice, f"/groups/{gid}/pantry"), "items") == []
    # removing again -> 409
    assert w.post(w.alice, f"/items/{item['id']}/remove", {"outcome": "used"}).status_code == 409
    assert len(sql("SELECT 1 FROM food_events WHERE item_id=:i AND event_type='remove'", i=item["id"])) == 1


def test_group_item_removal_rules_still_apply(world, sql):
    w = world
    gid = w.G["id"]
    item = w.post(w.alice, "/items", {"items": [{"name": "Rice", "group_id": gid}]}).get_json()["items"][0]
    url = f"/items/{item['id']}/remove"
    assert w.post(w.erin, url, {"outcome": "thrown_out"}).status_code == 400
    assert w.post(w.erin, url, {"outcome": "used", "waste_reason": "expired"}).status_code == 400
    assert w.post(w.erin, url, {"outcome": "bogus"}).status_code == 400
    assert w.post(w.erin, url, {"outcome": "donated", "waste_reason": "other"}).status_code == 400
    assert sql("SELECT 1 FROM food_events WHERE item_id=:i AND event_type='remove'", i=item["id"]) == []
    # outsiders cannot remove it (and must not learn it exists, or at least not touch it)
    for who in (w.bob, w.carol, w.dave):
        assert w.post(who, url, {"outcome": "used"}).status_code in (403, 404)
    assert sql("SELECT removed_at FROM items WHERE id=:i", i=item["id"])[0]["removed_at"] is None
    r = w.post(w.erin, url, {"outcome": "thrown_out", "waste_reason": "forgot"})
    assert r.status_code == 200
    ev = sql("SELECT * FROM food_events WHERE item_id=:i AND event_type='remove'", i=item["id"])
    assert len(ev) == 1 and ev[0]["outcome"] == "thrown_out" and ev[0]["waste_reason"] == "forgot"
    assert str(ev[0]["user_id"]) == w.erin["user"]["id"]


def test_group_item_removal_donated_with_recipient(world, sql):
    w = world
    item = w.post(w.alice, "/items", {"items": [{"name": "Rice", "group_id": w.G["id"]}]}).get_json()["items"][0]
    r = w.post(w.erin, f"/items/{item['id']}/remove",
               {"outcome": "donated", "recipient_id": w.bob["user"]["id"]})
    assert r.status_code == 200
    assert w.post(w.erin, f"/items/{item['id']}/remove", {"outcome": "used"}).status_code == 409


def test_left_member_cannot_remove_group_item(world):
    w = world
    gid = w.G["id"]
    item = w.post(w.alice, "/items", {"items": [{"name": "Rice", "group_id": gid}]}).get_json()["items"][0]
    assert w.post(w.erin, f"/groups/{gid}/leave").status_code in (200, 204)
    assert w.post(w.erin, f"/items/{item['id']}/remove", {"outcome": "used"}).status_code in (403, 404)


def test_personal_item_not_removable_by_friend_or_group_member(world):
    w = world
    item = w.item(w.alice)
    for who in (w.bob, w.erin, w.carol, w.dave):
        assert w.post(who, f"/items/{item['id']}/remove", {"outcome": "used"}).status_code == 403
        assert w.req(who, "patch", f"/items/{item['id']}", json={"name": "x"}).status_code == 403


# ---------- share board ----------
def test_share_visibility_matrix(world):
    w = world
    personal = w.item(w.alice, name="Personal")
    ingroup = w.item(w.alice, name="InGroup")
    assert w.share(w.alice, personal).status_code == 201
    assert w.share(w.alice, ingroup, w.G).status_code == 201

    names = lambda who: sorted(_item_name(l) for l in w.listings(who))
    # Bob (friend, not in G): only the friends-wide listing
    assert names(w.bob) == ["Personal"]
    # Erin (in G, not a friend): only the group listing
    assert names(w.erin) == ["InGroup"]
    # Alice sees neither of her own
    assert w.listings(w.alice) == []
    # pending-only and stranger see nothing
    assert w.listings(w.carol) == []
    assert w.listings(w.dave) == []


def _item_name(listing):
    if "item" in listing:
        return listing["item"]["name"]
    return listing["name"]


def test_share_listing_shape_has_owner_and_source(world):
    w = world
    p = w.item(w.alice, name="Personal")
    g = w.item(w.alice, name="InGroup")
    w.share(w.alice, p)
    w.share(w.alice, g, w.G)
    (lp,) = w.listings(w.bob)
    (lg,) = w.listings(w.erin)
    for l in (lp, lg):
        assert l["status"] == "open"
        owner = l.get("owner") or {}
        name = owner.get("display_name") or l.get("owner_name")
        assert name == "Alice"
    src = lambda l: l.get("source")
    if src(lp) is not None:
        assert src(lp)["type"] == "friend"
    if src(lg) is not None:
        assert src(lg)["type"] == "group" and src(lg)["name"] == "Flat G"


def test_share_group_listing_hidden_from_group_member_after_leaving(world):
    w = world
    w.share(w.alice, w.item(w.alice), w.G)
    assert len(w.listings(w.erin)) == 1
    w.post(w.erin, f"/groups/{w.G['id']}/leave")
    assert w.listings(w.erin) == []


def test_share_to_group_requires_membership(world):
    w = world
    item = w.item(w.alice)
    assert w.share(w.alice, item, w.H).status_code == 403
    # no listing and no share event was created
    assert w.listings(w.dave) == []
    assert w.share(w.alice, item, w.G).status_code == 201


def test_share_not_owner_and_missing(world):
    w = world
    item = w.item(w.alice)
    assert w.share(w.bob, item).status_code == 403
    assert w.share(w.dave, item).status_code == 403
    assert w.post(w.alice, "/share", {"item_id": MISSING}).status_code == 404
    assert w.post(w.alice, "/share", {}).status_code == 400


def test_share_double_and_removed_conflicts(world, sql):
    w = world
    item = w.item(w.alice)
    assert w.share(w.alice, item).status_code == 201
    r = w.share(w.alice, item)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "already_shared"
    assert w.share(w.alice, item, w.G).status_code == 409
    gone = w.item(w.alice, name="Gone")
    w.post(w.alice, f"/items/{gone['id']}/remove", {"outcome": "used"})
    r = w.share(w.alice, gone)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "already_removed"
    assert len(sql("SELECT 1 FROM share_listings")) == 1


def test_share_cancel_authorization_and_effect(world):
    w = world
    item = w.item(w.alice)
    lid = w.share(w.alice, item).get_json()["listing"]["id"]
    assert w.delete(w.bob, f"/share/{lid}").status_code == 403
    for who in (w.carol, w.dave, w.erin):
        assert w.delete(who, f"/share/{lid}").status_code == 404
    assert len(w.listings(w.bob)) == 1  # still there
    assert w.delete(w.alice, f"/share/{lid}").status_code in (200, 204)
    assert w.listings(w.bob) == []
    assert w.delete(w.alice, f"/share/{lid}").status_code in (404, 409)
    assert w.delete(w.alice, f"/share/{MISSING}").status_code == 404
    # item is still active and can be shared again
    assert w.share(w.alice, item).status_code == 201


def test_share_claim_authorization(world):
    w = world
    pl = w.share(w.alice, w.item(w.alice)).get_json()["listing"]["id"]
    gl = w.share(w.alice, w.item(w.alice), w.G).get_json()["listing"]["id"]
    # owner cannot claim own
    assert w.post(w.alice, f"/share/{pl}/claim").status_code in (400, 403, 404, 409)
    # invisible listings: stranger / pending / wrong audience
    for who in (w.carol, w.dave):
        assert w.post(who, f"/share/{pl}/claim").status_code in INVISIBLE
        assert w.post(who, f"/share/{gl}/claim").status_code in INVISIBLE
    assert w.post(w.erin, f"/share/{pl}/claim").status_code in INVISIBLE  # group member, not friend
    assert w.post(w.bob, f"/share/{gl}/claim").status_code in INVISIBLE   # friend, not in group
    assert w.post(w.bob, f"/share/{MISSING}/claim").status_code in INVISIBLE


def test_share_flow_end_to_end(world, sql, events):
    w = world
    item = w.item(w.alice, name="Cheese")
    lid = w.share(w.alice, item).get_json()["listing"]["id"]
    assert len(w.listings(w.bob)) == 1
    r = w.post(w.bob, f"/share/{lid}/claim")
    assert r.status_code == 200, r.get_data(as_text=True)
    # Alice hands it over: donated removal with the claimer as recipient
    r = w.post(w.alice, f"/items/{item['id']}/remove",
               {"outcome": "donated", "recipient_id": w.bob["user"]["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = sql("SELECT * FROM share_listings WHERE id=:i", i=lid)[0]
    assert row["status"] == "fulfilled"
    assert str(row["recipient_id"]) == w.bob["user"]["id"]
    assert row["fulfilled_at"] is not None
    assert w.listings(w.bob) == []
    assert len(events(item["id"], "remove")) == 1
    # a fulfilled listing can no longer be claimed or cancelled into oblivion
    assert w.post(w.bob, f"/share/{lid}/claim").status_code in (404, 409)
    # impact credit is Alice's
    imp = w.get(w.alice, "/impact").get_json()
    assert imp["saved"]["count"] == 1
    assert w.get(w.bob, "/impact").get_json()["saved"]["count"] == 0


def test_claim_twice_and_by_two_people(world, sql):
    w = world
    p = w.item(w.alice)
    lid = w.share(w.alice, p).get_json()["listing"]["id"]
    w.post(w.dave, "/friends", {"email": w.alice["email"]})
    w.post(w.alice, f"/friends/{w.dave['user']['id']}/accept")
    assert w.post(w.bob, f"/share/{lid}/claim").status_code == 200
    again = w.post(w.bob, f"/share/{lid}/claim")
    assert again.status_code in (200, 409)
    other = w.post(w.dave, f"/share/{lid}/claim")
    assert other.status_code in (200, 409)  # either first-come-first-served or multiple interested


def test_donated_removal_unshared_item_has_no_listing_side_effect(world, sql):
    w = world
    item = w.item(w.alice)
    r = w.post(w.alice, f"/items/{item['id']}/remove", {"outcome": "donated"})
    assert r.status_code == 200
    assert sql("SELECT 1 FROM share_listings") == []


def test_used_removal_leaves_listing_open_or_closes_it_but_never_fulfils(world, sql):
    w = world
    item = w.item(w.alice)
    lid = w.share(w.alice, item).get_json()["listing"]["id"]
    w.post(w.alice, f"/items/{item['id']}/remove", {"outcome": "used"})
    st = sql("SELECT status FROM share_listings WHERE id=:i", i=lid)[0]["status"]
    assert st != "fulfilled"
    # a removed item must not stay on friends' board
    assert w.listings(w.bob) == [], "removed item still offered on the Food Pantry board"


# ---------- requests ----------
def test_request_create_validation(world):
    w = world
    assert w.post(w.alice, "/requests", {"text": ""}).status_code == 400
    assert w.post(w.alice, "/requests", {}).status_code == 400
    assert w.post(w.alice, "/requests", {"text": "x" * 281}).status_code == 400
    assert w.post(w.alice, "/requests", {"text": 123}).status_code == 400
    assert w.post(w.alice, "/requests", {"text": "x" * 280}).status_code == 201
    assert w.post(w.alice, "/requests", {"text": "y"}).status_code == 201
    assert w.post(w.alice, "/requests", {"text": "hi", "group_id": w.H["id"]}).status_code == 403
    assert w.post(w.alice, "/requests", {"text": "hi", "group_id": "junk"}).status_code in (400, 404)


def _req_text(r):
    return r["text"]


def test_request_visibility_and_source(world):
    w = world
    assert w.post(w.alice, "/requests", {"text": "need eggs"}).status_code == 201
    assert w.post(w.alice, "/requests", {"text": "need flour", "group_id": w.G["id"]}).status_code == 201

    def texts(who):
        return sorted(_req_text(r) for r in w.requests_for(who))

    assert texts(w.bob) == ["need eggs"]                # friend, not in group
    assert texts(w.erin) == ["need flour"]              # group member, not friend
    assert texts(w.alice) == ["need eggs", "need flour"]
    assert texts(w.carol) == []
    assert texts(w.dave) == []

    def src(who, text):
        return next(r for r in w.requests_for(who) if r["text"] == text).get("source")

    s = src(w.bob, "need eggs")
    if s is not None:
        assert s["type"] == "friend" and s["name"] == "Alice"
    s = src(w.erin, "need flour")
    if s is not None:
        assert s["type"] == "group" and s["name"] == "Flat G"
    s = src(w.alice, "need eggs")
    if s is not None:
        assert s["type"] == "me"


def test_request_dave_group_requests_do_not_leak(world):
    w = world
    w.post(w.dave, "/requests", {"text": "dave group", "group_id": w.H["id"]})
    for who in (w.alice, w.bob, w.carol, w.erin):
        assert w.requests_for(who) == []
    assert [r["text"] for r in w.requests_for(w.dave)] == ["dave group"]


def test_request_visibility_follows_friendship_and_membership_changes(world):
    w = world
    w.post(w.alice, "/requests", {"text": "need eggs"})
    w.post(w.alice, "/requests", {"text": "grp", "group_id": w.G["id"]})
    w.delete(w.bob, f"/friends/{w.alice['user']['id']}")
    assert w.requests_for(w.bob) == []
    w.post(w.erin, f"/groups/{w.G['id']}/leave")
    assert w.requests_for(w.erin) == []
    # Carol accepted later sees the older request
    w.post(w.alice, f"/friends/{w.carol['user']['id']}/accept")
    assert [r["text"] for r in w.requests_for(w.carol)] == ["need eggs"]


def test_request_fulfil_rules(world):
    w = world
    pid = w.post(w.alice, "/requests", {"text": "need eggs"}).get_json()
    pid = _one(w.get(w.alice, "/requests"), "requests")[0]["id"]
    # author cannot fulfil own
    assert w.post(w.alice, f"/requests/{pid}/fulfil").status_code == 403
    # invisible users cannot fulfil
    for who in (w.carol, w.dave, w.erin):
        assert w.post(who, f"/requests/{pid}/fulfil").status_code in INVISIBLE
    assert w.post(w.bob, f"/requests/{MISSING}/fulfil").status_code == 404
    assert w.post(w.bob, "/requests/not-a-uuid/fulfil").status_code == 404
    r = w.post(w.bob, f"/requests/{pid}/fulfil")
    assert r.status_code == 200, r.get_data(as_text=True)
    # no longer open; second fulfil conflicts
    assert w.post(w.bob, f"/requests/{pid}/fulfil").status_code in (404, 409)
    open_now = [x for x in w.requests_for(w.bob) if x.get("status", "open") == "open"]
    assert open_now == []


def test_group_request_fulfil_by_member_not_by_outside_friend(world):
    w = world
    w.post(w.alice, "/requests", {"text": "grp", "group_id": w.G["id"]})
    rid = w.requests_for(w.erin)[0]["id"]
    assert w.post(w.bob, f"/requests/{rid}/fulfil").status_code in INVISIBLE
    assert w.post(w.erin, f"/requests/{rid}/fulfil").status_code == 200


def test_request_cancel_author_only(world):
    w = world
    w.post(w.alice, "/requests", {"text": "need eggs"})
    rid = w.requests_for(w.alice)[0]["id"]
    assert w.delete(w.bob, f"/requests/{rid}").status_code == 403  # visible, not author
    for who in (w.carol, w.dave, w.erin):
        assert w.delete(who, f"/requests/{rid}").status_code == 404  # invisible: no leak
    assert len(w.requests_for(w.bob)) == 1
    assert w.delete(w.alice, f"/requests/{rid}").status_code in (200, 204)
    assert w.requests_for(w.bob) == [] and w.requests_for(w.alice) == []
    assert w.delete(w.alice, f"/requests/{rid}").status_code == 409
    assert w.post(w.bob, f"/requests/{rid}/fulfil").status_code == 409


# ---------- contract details from API.md ----------
def test_friends_response_shapes(world):
    w = world
    body = w.get(w.alice, "/friends").get_json()
    assert set(body) >= {"friends", "incoming", "outgoing"}
    assert [f["user_id"] for f in body["friends"]] == [w.bob["user"]["id"]]
    assert body["friends"][0]["display_name"] == "Bob" and body["friends"][0]["status"] == "accepted"
    assert [f["user_id"] for f in body["incoming"]] == [w.carol["user"]["id"]]
    assert [f["user_id"] for f in w.get(w.carol, "/friends").get_json()["outgoing"]] == [w.alice["user"]["id"]]
    assert w.get(w.dave, "/friends").get_json() == {"friends": [], "incoming": [], "outgoing": []}


def test_duplicate_friend_codes_both_directions(world):
    w = world
    r = w.post(w.bob, "/friends", {"email": w.alice["email"]})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "already_friends"
    r = w.post(w.alice, "/friends", {"email": w.carol["email"]})  # reverse of pending
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "request_pending"
    # decline / cancel via DELETE ends the pending state; Carol can re-request
    assert w.delete(w.alice, f"/friends/{w.carol['user']['id']}").status_code == 204
    assert w.post(w.carol, "/friends", {"email": w.alice["email"]}).status_code == 201


def test_group_item_cannot_be_shared(world):
    w = world
    item = w.post(w.alice, "/items", {"items": [{"name": "Rice", "group_id": w.G["id"]}]}).get_json()["items"][0]
    assert w.share(w.alice, item).status_code == 400
    assert w.share(w.alice, item, w.G).status_code == 400
    assert w.listings(w.bob) == [] and w.listings(w.erin) == []


def test_pantry_items_have_added_by_and_items_list_is_personal_only(world):
    w = world
    w.post(w.erin, "/items", {"items": [{"name": "Rice", "group_id": w.G["id"]}]})
    (it,) = w.get(w.alice, f"/groups/{w.G['id']}/pantry").get_json()["items"]
    assert it["added_by"] == "Erin"
    assert w.get(w.erin, "/items").get_json()["items"] == []


def test_donated_removal_without_recipient_defaults_to_claimer(world, sql):
    w = world
    item = w.item(w.alice)
    lid = w.share(w.alice, item).get_json()["listing"]["id"]
    assert w.post(w.bob, f"/share/{lid}/claim").status_code == 200
    assert w.post(w.alice, f"/items/{item['id']}/remove", {"outcome": "donated"}).status_code == 200
    row = sql("SELECT status, recipient_id FROM share_listings WHERE id=:i", i=lid)[0]
    assert row["status"] == "fulfilled" and str(row["recipient_id"]) == w.bob["user"]["id"]


def test_claimed_listing_second_claimer_conflicts(world):
    w = world
    lid = w.share(w.alice, w.item(w.alice)).get_json()["listing"]["id"]
    w.post(w.dave, "/friends", {"email": w.alice["email"]})
    w.post(w.alice, f"/friends/{w.dave['user']['id']}/accept")
    assert w.post(w.bob, f"/share/{lid}/claim").status_code == 200
    r = w.post(w.dave, f"/share/{lid}/claim")
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "already_claimed"


def test_leave_cancels_leavers_group_listings_and_requests(world, sql):
    w = world
    gid = w.G["id"]
    w.share(w.erin, w.item(w.erin), w.G)
    w.post(w.erin, "/requests", {"text": "from erin", "group_id": gid})
    w.post(w.erin, "/requests", {"text": "personal erin"})
    assert len(w.listings(w.alice)) == 1 and len(w.requests_for(w.alice)) == 1
    r = w.post(w.erin, f"/groups/{gid}/leave")
    assert r.status_code == 200 and r.get_json() == {"left": True}
    assert w.listings(w.alice) == [] and w.requests_for(w.alice) == []
    assert sql("SELECT status FROM share_listings")[0]["status"] == "cancelled"


def test_owner_leave_transfers_ownership_to_longest_member(world):
    w = world
    gid = w.G["id"]
    w.post(w.bob, "/groups/join", {"invite_code": w.G["invite_code"]})
    assert w.post(w.alice, f"/groups/{gid}/leave").status_code == 200
    g = w.get(w.erin, f"/groups/{gid}").get_json()["group"]
    roles = {m["user_id"]: m["role"] for m in g["members"]}
    assert roles == {w.erin["user"]["id"]: "owner", w.bob["user"]["id"]: "member"}
    assert g["member_count"] == 2 and g["role"] == "owner"


def test_invite_code_format_and_normalisation(world):
    w = world
    code = w.G["invite_code"]
    assert len(code) == 8 and not set(code) & set("01OIL")
    spaced = f"{code[:4].lower()}-{code[4:].lower()} "
    assert w.post(w.bob, "/groups/join", {"invite_code": spaced}).status_code == 200


def test_group_shapes(world):
    w = world
    g = w.get(w.alice, f"/groups/{w.G['id']}").get_json()["group"]
    assert g["role"] == "owner" and g["member_count"] == 2 and g["created_by"] == w.alice["user"]["id"]
    assert {m["user_id"] for m in g["members"]} == {w.alice["user"]["id"], w.erin["user"]["id"]}
    assert w.get(w.erin, f"/groups/{w.G['id']}").get_json()["group"]["role"] == "member"


def test_request_shape_and_fulfil_fields(world):
    w = world
    r = w.post(w.alice, "/requests", {"text": "eggs", "group_id": w.G["id"]})
    q = r.get_json()["request"]
    assert q["author_id"] == w.alice["user"]["id"] and q["author_name"] == "Alice"
    assert q["group_name"] == "Flat G" and q["status"] == "open"
    f = w.post(w.erin, f"/requests/{q['id']}/fulfil").get_json()["request"]
    assert f["status"] == "fulfilled" and f["fulfilled_by"] == w.erin["user"]["id"]
    c = w.post(w.alice, "/requests", {"text": "milk"}).get_json()["request"]
    d = w.delete(w.alice, f"/requests/{c['id']}")
    assert d.status_code == 200 and d.get_json()["request"]["status"] == "cancelled"


def test_requests_newest_first(world):
    w = world
    for t in ("one", "two", "three"):
        w.post(w.alice, "/requests", {"text": t})
    assert [r["text"] for r in w.requests_for(w.bob)] == ["three", "two", "one"]


def test_invalid_uuid_resources_404(world):
    w = world
    assert w.post(w.bob, "/share/not-a-uuid/claim").status_code == 404
    assert w.delete(w.bob, "/share/not-a-uuid").status_code == 404
    assert w.delete(w.bob, "/requests/not-a-uuid").status_code == 404
    assert w.delete(w.bob, "/friends/not-a-uuid").status_code == 404
