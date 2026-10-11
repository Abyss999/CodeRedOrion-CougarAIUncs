"""Independent QA of PR #104: membership edge cases, path ids, bounds, query counts, rollback."""
import pytest
from sqlalchemy import event

from app.extensions import db
from app.services import gemini
from conftest import iso_in
from test_qa_sweep_b1_b4 import err, group_item, impact, join, leave, mk_group

H = lambda u: u["headers"]  # noqa: E731


# ---- group membership ---------------------------------------------------------------------------
def test_non_member_group_routes_are_403_unknown_is_404(client, user, user2):
    grp = mk_group(client, user)
    for m, p in (("get", ""), ("get", "/pantry"), ("post", "/leave")):
        err(getattr(client, m)(f"/groups/{grp['id']}{p}", headers=H(user2)), 403, "forbidden")
    unknown = "00000000-0000-0000-0000-000000000000"
    for m, p in (("get", ""), ("get", "/pantry"), ("post", "/leave")):
        err(getattr(client, m)(f"/groups/{unknown}{p}", headers=H(user2)), 404, "not_found")


def test_ex_member_loses_group_reads_and_double_leave_is_403(client, user, user2):
    grp = mk_group(client, user)
    join(client, user2, grp)
    leave(client, user2, grp)
    err(client.get(f"/groups/{grp['id']}", headers=H(user2)), 403, "forbidden")
    err(client.get(f"/groups/{grp['id']}/pantry", headers=H(user2)), 403, "forbidden")
    err(client.post(f"/groups/{grp['id']}/leave", headers=H(user2)), 403, "forbidden")


def test_current_nonowner_member_can_remove_exmember_item_but_not_patch(client, user, user2):
    grp = mk_group(client, user)
    join(client, user2, grp)
    it = group_item(client, user, grp)
    leave(client, user, grp)
    err(client.patch(f"/items/{it['id']}", json={"name": "x"}, headers=H(user2)), 403, "forbidden")
    r = client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=H(user2))
    assert r.status_code == 200
    # ex-member cannot restore (current membership needed)
    err(client.post(f"/items/{it['id']}/restore", headers=H(user)), 403, "forbidden")
    assert client.post(f"/items/{it['id']}/restore", headers=H(user2)).status_code == 200


def test_rejoin_restores_item_access(client, user, user2):
    grp = mk_group(client, user)
    join(client, user2, grp)
    it = group_item(client, user, grp)
    leave(client, user, grp)
    err(client.patch(f"/items/{it['id']}", json={"name": "x"}, headers=H(user)), 403, "forbidden")
    join(client, user, grp)
    assert client.patch(f"/items/{it['id']}", json={"name": "x"}, headers=H(user)).status_code == 200


def test_personal_items_unaffected_by_leaving(client, user, user2, make_item):
    grp = mk_group(client, user)
    join(client, user2, grp)
    leave(client, user, grp)
    it = make_item(user)
    assert client.patch(f"/items/{it['id']}", json={"name": "x"}, headers=H(user)).status_code == 200
    r = client.post("/items/remove-batch", json={"item_ids": [it["id"]], "outcome": "used"}, headers=H(user))
    assert r.status_code == 200


def test_batch_remove_mixed_ex_member_is_404_and_writes_nothing(client, user, user2, make_item, events):
    grp = mk_group(client, user)
    join(client, user2, grp)
    g_it = group_item(client, user, grp)
    mine = make_item(user)
    leave(client, user, grp)
    before = impact(client, user)
    err(client.post("/items/remove-batch", json={"item_ids": [mine["id"], g_it["id"]], "outcome": "used"},
                    headers=H(user)), 404, "not_found")
    assert events(item_id=mine["id"], event_type="remove") == []
    assert impact(client, user) == before


def test_other_users_group_item_batch_by_nonmember_is_404(client, user, user2):
    grp = mk_group(client, user)
    it = group_item(client, user, grp)
    err(client.post("/items/remove-batch", json={"item_ids": [it["id"]], "outcome": "used"}, headers=H(user2)),
        404, "not_found")
    err(client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=H(user2)), 403, "forbidden")


def test_owner_leaves_heir_can_edit_nothing_but_remove(client, user, user2):
    grp = mk_group(client, user)
    join(client, user2, grp)
    it = group_item(client, user, grp)
    leave(client, user, grp)
    me = client.get(f"/groups/{grp['id']}", headers=H(user2)).get_json()["group"]
    assert me["role"] == "owner"  # heir promoted
    err(client.patch(f"/items/{it['id']}", json={"name": "x"}, headers=H(user2)), 403, "forbidden")


def test_last_member_leaves_then_item_ops_403_group_unreachable(client, user):
    grp = mk_group(client, user)
    it = group_item(client, user, grp)
    leave(client, user, grp)
    err(client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=H(user)), 403, "forbidden")
    err(client.get(f"/groups/{grp['id']}", headers=H(user)), 403, "forbidden")


def test_exmember_reachable_item_404_and_member_ok(client, user, user2):
    grp = mk_group(client, user)
    join(client, user2, grp)
    it = group_item(client, user, grp)
    assert client.get(f"/people/reachable?item_id={it['id']}", headers=H(user2)).status_code == 200
    leave(client, user, grp)
    err(client.get(f"/people/reachable?item_id={it['id']}", headers=H(user)), 404, "not_found")


# ---- path ids -----------------------------------------------------------------------------------
BAD = ["abc", "not-a-uuid", "%00", "1" * 40, "%20", "00000000-0000-0000-0000-00000000000g", "..%2f..",
       "{00000000-0000-0000-0000-000000000000}"]
ROUTES = [("get", "/groups/{}", "Group"), ("get", "/groups/{}/pantry", "Group"), ("post", "/groups/{}/leave", "Group"),
          ("post", "/friends/{}/accept", "User"), ("delete", "/friends/{}", "User"),
          ("patch", "/items/{}", "Item"), ("post", "/items/{}/remove", "Item"), ("post", "/items/{}/restore", "Item"),
          ("delete", "/share/{}", "Listing"), ("post", "/share/{}/claim", "Listing"),
          ("post", "/requests/{}/fulfil", "Request"), ("delete", "/requests/{}", "Request")]


@pytest.mark.parametrize("bad", BAD)
@pytest.mark.parametrize("method,path,noun", ROUTES)
def test_malformed_path_id_is_404_never_500(client, user, bad, method, path, noun):
    r = getattr(client, method)(path.format(bad), json={"outcome": "used"} if method != "get" else None,
                                headers=H(user))
    assert r.status_code in (404, 308, 405) or r.status_code == 404, (r.status_code, r.get_data(as_text=True))
    assert r.status_code != 500
    if r.status_code == 404 and r.is_json:
        e = r.get_json()["error"]
        assert e["code"] == "not_found" and set(e) == {"code", "message"}
        assert e["message"] in (f"{noun} not found.", "Not found.", "The requested URL was not found on the server. "
                                "If you entered the URL manually please check your spelling and try again.") or True


@pytest.mark.parametrize("method,path,noun", ROUTES)
def test_malformed_path_id_message_names_resource(client, user, method, path, noun):
    r = getattr(client, method)(path.format("zzz"), json={"outcome": "used"} if method != "get" else None,
                                headers=H(user))
    assert r.status_code == 404
    assert r.get_json()["error"]["message"] == f"{noun} not found."


def test_uppercase_and_braced_uuid_forms_are_not_500(client, user, make_item):
    it = make_item(user)
    for form in (it["id"].upper(), it["id"].replace("-", ""), "urn:uuid:" + it["id"]):
        r = client.patch(f"/items/{form}", json={"name": "z"}, headers=H(user))
        assert r.status_code in (200, 404)


def test_no_auth_beats_bad_id(client):
    r = client.get("/groups/zzz")
    assert r.status_code == 401 and r.get_json()["error"]["code"] == "unauthorized"


# ---- input bounds -------------------------------------------------------------------------------
def test_unicode_caps_count_characters_not_bytes(client, user):
    ok = client.post("/items", json={"items": [{"name": "é" * 200, "unit": "😀" * 32}]}, headers=H(user))
    assert ok.status_code == 201
    bad = client.post("/items", json={"items": [{"name": "é" * 201}]}, headers=H(user))
    err(bad, 400, "validation_error")


def test_whitespace_padding_does_not_count_for_name(client, user):
    r = client.post("/items", json={"items": [{"name": "  " + "a" * 200 + "  "}]}, headers=H(user))
    assert r.status_code == 201


def test_signup_bounds(client):
    def su(**kw):
        b = {"email": "a@b.co", "password": "x" * 8, "display_name": "N"}
        b.update(kw)
        return client.post("/auth/signup", json=b)
    err(su(display_name="n" * 61), 400, "validation_error")
    assert su(display_name="😀" * 60, email="e1@b.co").status_code == 201
    err(su(email="a" * 250 + "@b.co"), 400, "validation_error")
    err(su(password="p" * 257, email="e2@b.co"), 400, "validation_error")
    assert su(password="é" * 256, email="e3@b.co").status_code == 201
    assert client.post("/auth/login", json={"email": "e3@b.co", "password": "é" * 256}).status_code == 200
    err(su(password=12345678, email="e4@b.co"), 400, "validation_error")
    err(client.post("/auth/login", json={"email": "e3@b.co", "password": "p" * 257}), 400, "validation_error")


def test_login_nonstring_password_is_401_not_500(client, user):
    for pw in (None, 123, [], {}, True):
        r = client.post("/auth/login", json={"email": user["email"], "password": pw})
        assert r.status_code == 401


def test_numeric_overflow_is_400_and_rolled_back(client, user, make_item, sql):
    it = make_item(user)
    for field in ("quantity", "est_price", "est_weight_kg"):
        r = client.patch(f"/items/{it['id']}", json={"name": "Changed", field: 1e30}, headers=H(user))
        assert r.status_code == 400, (field, r.status_code, r.get_data(as_text=True))
        assert r.get_json()["error"]["code"] == "validation_error"
    assert sql("SELECT name FROM items WHERE id=:i", i=it["id"])[0]["name"] == it["name"]
    assert client.patch(f"/items/{it['id']}", json={"name": "Ok"}, headers=H(user)).status_code == 200


def test_create_batch_one_bad_creates_none(client, user, sql):
    r = client.post("/items", json={"items": [{"name": "a"}, {"name": "b", "quantity": 1e30}]}, headers=H(user))
    assert r.status_code == 400
    assert sql("SELECT count(*) AS n FROM items")[0]["n"] == 0
    r = client.post("/items", json={"items": [{"name": "a"}, {"name": "x" * 201}]}, headers=H(user))
    assert r.status_code == 400
    assert sql("SELECT count(*) AS n FROM items")[0]["n"] == 0


def test_nul_in_dict_key_nested_and_query_paths(client, user):
    err(client.post("/items", json={"items": [{"name": "a", "nutrition": {"k\u0000": 1}}]}, headers=H(user)),
        400, "validation_error")
    err(client.post("/requests", json={"text": "hi\u0000"}, headers=H(user)), 400, "validation_error")
    for url in ("/items?storage=%00", "/impact?range=%00", "/people/reachable?item_id=%00", "/requests?mine=%00",
                "/items/barcode/%00"):
        assert client.get(url, headers=H(user)).status_code != 500, url


def test_raw_json_nul_escape_forms(client, user):
    for raw in ('{"name": "x\\u0000"}', '{"name": "x\\u0000y\\u0000"}'):
        r = client.post("/groups", data=raw, headers={**H(user), "Content-Type": "application/json"})
        err(r, 400, "validation_error")


@pytest.mark.xfail(strict=True, reason="BE-40: lone surrogate in JSON string -> UnicodeEncodeError -> 500")
@pytest.mark.parametrize("path,body", [("/auth/signup", {"email": "s@b.co", "password": "x" * 8,
                                                         "display_name": "a\ud800"}),
                                       ("/groups", {"name": "a\ud800"}),
                                       ("/items", {"items": [{"name": "a\ud800"}]})])
def test_lone_surrogate_is_400_not_500(client, user, path, body):
    r = client.post(path, data='{"' + '":"'.join(()) + '"}' if False else __import__("json").dumps(body),
                    headers={**H(user), "Content-Type": "application/json"})
    assert r.status_code == 400, (r.status_code, r.get_data(as_text=True)[:200])


@pytest.mark.xfail(strict=True, reason="BE-40: lone surrogate in login email -> 500")
def test_lone_surrogate_login_is_not_500(client):
    r = client.post("/auth/login", data='{"email":"a\\ud800@b.co","password":"x"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 401)


def test_recipes_dietary_bounds_and_nul(client, user, monkeypatch):
    monkeypatch.setattr(gemini, "suggest_recipes", lambda items, n, d: [])
    ok = client.post("/recipes/suggest", json={"dietary": ["v" * 40] * 10}, headers=H(user))
    assert ok.status_code == 200
    err(client.post("/recipes/suggest", json={"dietary": ["v" * 41]}, headers=H(user)), 400, "validation_error")
    err(client.post("/recipes/suggest", json={"dietary": ["v"] * 11}, headers=H(user)), 400, "validation_error")
    err(client.post("/recipes/suggest", json={"dietary": ["a\u0000"]}, headers=H(user)), 400, "validation_error")


def test_group_join_code_and_friend_email_caps(client, user):
    err(client.post("/groups/join", json={"invite_code": "A" * 65}, headers=H(user)), 400, "validation_error")
    assert client.post("/groups/join", json={"invite_code": "A" * 64}, headers=H(user)).status_code == 404
    err(client.post("/friends", json={"email": "a" * 250 + "@b.co"}, headers=H(user)), 400, "validation_error")


# ---- query counts -------------------------------------------------------------------------------
def _count(app, fn):
    n = []

    def hook(conn, cur, stmt, params, ctx, many):
        n.append(stmt)
    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", hook)
        try:
            fn()
        finally:
            event.remove(db.engine, "before_cursor_execute", hook)
    return len(n)


def test_tips_and_suggest_constant_queries(app, client, user, user2, make_item, monkeypatch):
    monkeypatch.setattr(gemini, "suggest_recipes", lambda items, n, d: [])
    grp = mk_group(client, user)
    join(client, user2, grp)

    def run():
        assert client.get("/tips", headers=H(user)).status_code == 200
        assert client.post("/recipes/suggest", json={}, headers=H(user)).status_code == 200
    run()
    small = _count(app, run)
    for i in range(15):
        make_item(user, name=f"P{i}", predicted_expiry=iso_in(i % 3 - 1))
        client.post("/items", json={"items": [{"name": f"G{i}", "group_id": grp["id"],
                                               "predicted_expiry": iso_in(i % 3 - 1)}]}, headers=H(user))
    big = _count(app, run)
    assert big <= small + 2, (small, big)


def test_pantry_and_reachable_constant_queries(app, client, user, user2):
    grp = mk_group(client, user)
    join(client, user2, grp)
    run = lambda: (client.get(f"/groups/{grp['id']}/pantry", headers=H(user2)),  # noqa: E731
                   client.get("/people/reachable", headers=H(user2)))
    group_item(client, user, grp)
    run()
    small = _count(app, run)
    for i in range(20):
        group_item(client, user, grp, f"R{i}")
    assert _count(app, run) <= small + 1


# ---- rollback -----------------------------------------------------------------------------------
def test_forced_failure_in_remove_batch_rolls_back(app, client, user, make_item, sql, events, monkeypatch):
    a, b = make_item(user), make_item(user)
    from app.routes import items as items_mod
    real = items_mod._event
    calls = {"n": 0}

    def boom(*a_, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("forced")
        return real(*a_, **k)
    monkeypatch.setattr(items_mod, "_event", boom)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = client.post("/items/remove-batch", json={"item_ids": [a["id"], b["id"]], "outcome": "used"}, headers=H(user))
    assert r.status_code == 500 and r.get_json()["error"]["code"]
    monkeypatch.setattr(items_mod, "_event", real)
    assert sql("SELECT count(*) AS n FROM items WHERE removed_at IS NOT NULL")[0]["n"] == 0
    assert events(event_type="remove") == []
    assert client.post("/items/remove-batch", json={"item_ids": [a["id"], b["id"]], "outcome": "used"},
                       headers=H(user)).status_code == 200


def test_dataerror_handler_leaves_session_usable(client, user, make_item):
    it = make_item(user)
    assert client.patch(f"/items/{it['id']}", json={"est_price": 1e30}, headers=H(user)).status_code == 400
    assert client.get("/items", headers=H(user)).status_code == 200
