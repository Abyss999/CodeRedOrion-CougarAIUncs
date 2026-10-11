"""DELETE /auth/me: cascade personal data, anonymise food_events, leave everybody else alone."""
import uuid

import pytest

from conftest import _signup

NIL = "00000000-0000-0000-0000-000000000000"


def j(client, u, method, path, body=None):
    kw = {"headers": u["headers"]}
    if body is not None:
        kw["json"] = body
    return getattr(client, method)(path, **kw)


def count(sql, table, where="true", **p):
    return sql(f"SELECT count(*) AS n FROM {table} WHERE {where}", **p)[0]["n"]


@pytest.fixture
def world(client, sql):
    """alice (to be deleted), bob, carol, dave. Everything that references alice, plus bystander data."""
    w = {n: _signup(client, name=n.capitalize()) for n in ("alice", "bob", "carol", "dave")}
    A, B, C, D = (w[n] for n in ("alice", "bob", "carol", "dave"))
    w["ids"] = {n: w[n]["user"]["id"] for n in ("alice", "bob", "carol", "dave")}

    def item(u, group_id=None, **kw):
        p = {"name": "Milk", "category": "dairy", "est_price": 4, "quantity": 1, "unit": "l"} | kw
        body = {"items": [p]}
        if group_id:
            body["group_id"] = group_id
        r = client.post("/items", json=body, headers=u["headers"])
        assert r.status_code == 201, r.get_data(as_text=True)
        return r.get_json()["items"][0]

    w["item"] = item
    # friendships: alice<->bob accepted, alice->carol pending, dave->alice pending, bob<->carol accepted
    client.post("/friends", json={"email": B["email"]}, headers=A["headers"])
    client.post(f"/friends/{A['user']['id']}/accept", headers=B["headers"])
    client.post("/friends", json={"email": C["email"]}, headers=A["headers"])
    client.post("/friends", json={"email": A["email"]}, headers=D["headers"])
    client.post("/friends", json={"email": C["email"]}, headers=B["headers"])
    client.post(f"/friends/{B['user']['id']}/accept", headers=C["headers"])
    # groups: G owned by alice with bob; H owned by bob with alice and carol; S solo group of alice
    G = client.post("/groups", json={"name": "G"}, headers=A["headers"]).get_json()["group"]
    client.post("/groups/join", json={"invite_code": G["invite_code"]}, headers=B["headers"])
    H = client.post("/groups", json={"name": "H"}, headers=B["headers"]).get_json()["group"]
    client.post("/groups/join", json={"invite_code": H["invite_code"]}, headers=A["headers"])
    client.post("/groups/join", json={"invite_code": H["invite_code"]}, headers=C["headers"])
    S = client.post("/groups", json={"name": "Solo"}, headers=A["headers"]).get_json()["group"]
    w["G"], w["H"], w["S"] = G, H, S
    # alice's data
    w["a_active"] = item(A, name="A-active")
    w["a_removed"] = item(A, name="A-removed")
    client.post(f"/items/{w['a_removed']['id']}/remove", json={"outcome": "used"}, headers=A["headers"])
    w["a_thrown"] = item(A, name="A-thrown")
    client.post(f"/items/{w['a_thrown']['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "forgot"},
                headers=A["headers"])
    w["a_shared"] = item(A, name="A-shared")
    w["a_listing"] = client.post("/share", json={"item_id": w["a_shared"]["id"]}, headers=A["headers"]
                                 ).get_json()["listing"]
    client.post(f"/share/{w['a_listing']['id']}/claim", headers=B["headers"])
    w["a_grp_item"] = item(A, name="A-in-H", group_id=H["id"])
    w["a_req"] = client.post("/requests", json={"text": "need onions"}, headers=A["headers"]).get_json()["request"]
    # bob's data that references alice
    w["b_item"] = item(B, name="B-item")
    w["b_removed"] = item(B, name="B-removed")
    client.post(f"/items/{w['b_removed']['id']}/remove", json={"outcome": "used"}, headers=B["headers"])
    w["b_listing"] = client.post("/share", json={"item_id": w["b_item"]["id"]}, headers=B["headers"]
                                 ).get_json()["listing"]
    r = client.post(f"/share/{w['b_listing']['id']}/claim", headers=A["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    w["b_req"] = client.post("/requests", json={"text": "bob wants eggs"}, headers=B["headers"]).get_json()["request"]
    r = client.post(f"/requests/{w['b_req']['id']}/fulfil", headers=A["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    # carol's bystander data
    w["c_item"] = item(C, name="C-item")
    client.post(f"/items/{item(C, name='C-gone')['id']}/remove", json={"outcome": "thrown_out",
                "waste_reason": "expired"}, headers=C["headers"])
    w["c_req"] = client.post("/requests", json={"text": "carol thing"}, headers=C["headers"]).get_json()["request"]
    return w


def delete(client, u, **kw):
    return client.delete("/auth/me", headers=u["headers"], **kw)


def test_requires_auth(client):
    assert client.delete("/auth/me").status_code == 401
    assert client.delete("/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_delete_basic_204_then_token_dead(client, user):
    r = delete(client, user)
    assert r.status_code == 204 and r.get_data() == b""
    assert client.get("/items", headers=user["headers"]).status_code == 401
    assert delete(client, user).status_code == 401
    assert client.post("/auth/login", json={"email": user["email"], "password": user["password"]}).status_code == 401


def test_email_can_be_reused_with_clean_slate(client, user, make_item):
    make_item(user)
    delete(client, user)
    again = _signup(client, email=user["email"])
    assert again["user"]["id"] != user["user"]["id"]
    assert client.get("/items", headers=again["headers"]).get_json()["items"] == []


def test_personal_data_gone(client, sql, world):
    ids = world["ids"]
    A = world["alice"]
    pre_events = count(sql, "food_events", "user_id=:u", u=ids["alice"])
    assert pre_events >= 5  # adds + removes + share
    assert delete(client, A).status_code == 204
    a = ids["alice"]
    assert count(sql, "users", "id=:u", u=a) == 0
    assert count(sql, "items", "owner_id=:u", u=a) == 0
    assert count(sql, "share_listings", "owner_id=:u", u=a) == 0
    assert count(sql, "share_listings", "item_id=:i", i=world["a_shared"]["id"]) == 0
    assert count(sql, "share_listings", "claimed_by=:u OR recipient_id=:u", u=a) == 0
    assert count(sql, "friendships", "user_id=:u OR friend_id=:u", u=a) == 0
    assert count(sql, "group_members", "user_id=:u", u=a) == 0
    assert count(sql, "requests", "author_id=:u OR fulfilled_by=:u", u=a) == 0
    assert count(sql, "groups", "created_by=:u", u=a) == 0
    # nothing anywhere still references her id
    for tbl, col in [("food_events", "user_id"), ("items", "owner_id"), ("groups", "created_by"),
                     ("group_members", "user_id"), ("requests", "author_id"), ("requests", "fulfilled_by"),
                     ("share_listings", "owner_id"), ("share_listings", "claimed_by"),
                     ("share_listings", "recipient_id"), ("friendships", "user_id"), ("friendships", "friend_id")]:
        assert count(sql, tbl, f"{col}=:u", u=a) == 0, f"{tbl}.{col} still references the deleted user"


def test_food_events_anonymised_not_deleted(client, sql, world):
    ids = world["ids"]
    a_items = [world[k]["id"] for k in ("a_active", "a_removed", "a_thrown", "a_shared")]
    before = sql("SELECT event_type, category, outcome, waste_reason, est_price, co2e_kg, quantity "
                 "FROM food_events WHERE user_id=:u ORDER BY time, id", u=ids["alice"])
    total_before = count(sql, "food_events")
    removes_before = sql("SELECT coalesce(sum(co2e_kg),0) AS c, coalesce(sum(est_price),0) AS p, count(*) AS n "
                         "FROM food_events WHERE event_type='remove'")[0]
    assert delete(client, world["alice"]).status_code == 204
    assert count(sql, "food_events") == total_before, "no event may be dropped"
    assert count(sql, "food_events", "user_id=:u", u=ids["alice"]) == 0
    anon = sql("SELECT event_type, category, outcome, waste_reason, est_price, co2e_kg, quantity "
               "FROM food_events WHERE user_id=:u ORDER BY time, id", u=NIL)
    assert len(anon) == len(before) and sorted(map(str, anon)) == sorted(map(str, before))
    removes_after = sql("SELECT coalesce(sum(co2e_kg),0) AS c, coalesce(sum(est_price),0) AS p, count(*) AS n "
                        "FROM food_events WHERE event_type='remove'")[0]
    assert removes_after == removes_before  # aggregates unchanged
    # the tombstone is not a real account
    assert count(sql, "users", "id=:u", u=NIL) == 0
    # a fresh user can never inherit the anonymised history
    fresh = _signup(client)
    r = client.get("/impact?range=all", headers=fresh["headers"]).get_json()
    assert r["saved"]["count"] == 0 and r["wasted"]["count"] == 0
    del a_items


def test_other_users_unaffected(client, sql, world):
    B, C = world["bob"], world["carol"]
    imp_b = client.get("/impact?range=all", headers=B["headers"]).get_json()
    imp_c = client.get("/impact?range=all", headers=C["headers"]).get_json()
    b_events = sql("SELECT id FROM food_events WHERE user_id=:u ORDER BY id", u=world["ids"]["bob"])
    assert delete(client, world["alice"]).status_code == 204
    assert client.get("/impact?range=all", headers=B["headers"]).get_json() == imp_b
    assert client.get("/impact?range=all", headers=C["headers"]).get_json() == imp_c
    assert sql("SELECT id FROM food_events WHERE user_id=:u ORDER BY id", u=world["ids"]["bob"]) == b_events
    names = {i["name"] for i in client.get("/items", headers=B["headers"]).get_json()["items"]}
    assert "B-item" in names
    assert [i["name"] for i in client.get("/items", headers=C["headers"]).get_json()["items"]] == ["C-item"]
    # bob and carol are still friends; carol's request survives
    fr = client.get("/friends", headers=C["headers"]).get_json()
    assert any(f.get("id") == world["ids"]["bob"] or f.get("user_id") == world["ids"]["bob"]
               for f in fr.get("friends", []))
    assert any(r["id"] == world["c_req"]["id"] for r in client.get("/requests", headers=C["headers"]).get_json()["requests"])
    for u in (B, C, world["dave"]):
        assert client.get("/groups", headers=u["headers"]).status_code == 200
        assert client.get("/share", headers=u["headers"]).status_code == 200
        assert client.get("/friends", headers=u["headers"]).status_code == 200
        assert client.get("/requests", headers=u["headers"]).status_code == 200


def test_rows_of_others_that_pointed_at_her_are_detached_not_broken(client, sql, world):
    assert delete(client, world["alice"]).status_code == 204
    l = sql("SELECT * FROM share_listings WHERE id=:i", i=world["b_listing"]["id"])
    assert len(l) == 1 and l[0]["claimed_by"] is None and l[0]["status"] == "open"
    # still visible/claimable in the pantry by a friend of bob
    C = world["carol"]
    ids = {x["id"] for x in client.get("/share", headers=C["headers"]).get_json()["listings"]}
    assert world["b_listing"]["id"] in ids
    r = sql("SELECT * FROM requests WHERE id=:i", i=world["b_req"]["id"])
    assert len(r) == 1 and r[0]["fulfilled_by"] is None and r[0]["status"] == "open"


def test_group_ownership_passes_to_oldest_remaining_member(client, sql, world):
    G, H, S = world["G"], world["H"], world["S"]
    assert delete(client, world["alice"]).status_code == 204
    # G: alice owned, bob member -> bob inherits ownership, group survives
    mem = sql("SELECT user_id, role FROM group_members WHERE group_id=:g", g=G["id"])
    assert [(str(m["user_id"]), m["role"]) for m in mem] == [(world["ids"]["bob"], "owner")]
    g = client.get(f"/groups/{G['id']}", headers=world["bob"]["headers"])
    assert g.status_code == 200
    # H (owned by bob; alice was a member): unchanged apart from alice leaving
    mem = {str(m["user_id"]): m["role"] for m in sql("SELECT user_id, role FROM group_members WHERE group_id=:g", g=H["id"])}
    assert mem == {world["ids"]["bob"]: "owner", world["ids"]["carol"]: "member"}
    # alice's items in H's pantry went with her
    pantry = client.get(f"/groups/{H['id']}/pantry", headers=world["bob"]["headers"]).get_json()["items"]
    assert "A-in-H" not in {i["name"] for i in pantry}
    # S: sole member -> memberless orphan group is harmless
    assert sql("SELECT created_by FROM groups WHERE id=:g", g=S["id"])[0]["created_by"] is None
    assert client.get(f"/groups/{S['id']}", headers=world["bob"]["headers"]).status_code in (403, 404)
    r = client.post("/groups/join", json={"invite_code": S["invite_code"]}, headers=world["dave"]["headers"])
    assert r.status_code < 500
    assert client.get("/groups", headers=world["dave"]["headers"]).status_code == 200


def test_group_with_member_listing_created_by_none_serialises(client, sql, world):
    delete(client, world["alice"])
    gs = client.get("/groups", headers=world["bob"]["headers"])
    assert gs.status_code == 200
    one = client.get(f"/groups/{world['G']['id']}", headers=world["bob"]["headers"]).get_json()["group"]
    assert one["id"] == world["G"]["id"]
    # the new owner can still manage: invite code works for newcomers
    r = client.post("/groups/join", json={"invite_code": world["G"]["invite_code"]}, headers=world["dave"]["headers"])
    assert r.status_code == 200


def test_owner_who_leaves_flow_not_broken_for_heir(client, sql, world):
    delete(client, world["alice"])
    r = client.post(f"/groups/{world['G']['id']}/leave", headers=world["bob"]["headers"])
    assert r.status_code < 500


def test_pending_friend_requests_gone_for_both_directions(client, sql, world):
    delete(client, world["alice"])
    D, C = world["dave"], world["carol"]
    for u in (D, C):
        body = client.get("/friends", headers=u["headers"]).get_json()
        flat = str(body)
        assert world["ids"]["alice"] not in flat and "Alice" not in flat


def test_alice_data_not_leaking_in_other_responses(client, world):
    delete(client, world["alice"])
    for u, path in [(world["bob"], "/share"), (world["carol"], "/share"), (world["bob"], "/requests"),
                    (world["carol"], "/requests"), (world["bob"], "/friends"), (world["bob"], "/groups")]:
        body = client.get(path, headers=u["headers"]).get_data(as_text=True)
        assert world["ids"]["alice"] not in body, path
        assert "Alice" not in body, path


def test_delete_is_atomic(app, client, sql, world):
    """If anything fails mid-way nothing is deleted (one transaction)."""
    from sqlalchemy import event as sa_event

    from app.extensions import db

    def boom(conn, cur, stmt, params, ctx, many):
        if stmt.lstrip().upper().startswith("DELETE FROM USERS"):
            raise RuntimeError("boom")

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", boom)
        try:
            app.config["PROPAGATE_EXCEPTIONS"] = False
            r = app.test_client().delete("/auth/me", headers=world["alice"]["headers"])
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", boom)
    assert r.status_code == 500
    a = world["ids"]["alice"]
    assert count(sql, "users", "id=:u", u=a) == 1
    assert count(sql, "items", "owner_id=:u", u=a) >= 4
    assert count(sql, "food_events", "user_id=:u", u=a) >= 5
    assert count(sql, "friendships", "user_id=:u OR friend_id=:u", u=a) >= 1
    assert client.get("/items", headers=world["alice"]["headers"]).status_code == 200
