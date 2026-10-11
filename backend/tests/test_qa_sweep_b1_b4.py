"""QA sweep B1-B4: group-item membership, NUL bytes, string caps, path-id messages."""
import pytest


def mk_group(client, owner, name="Flat"):
    r = client.post("/groups", json={"name": name}, headers=owner["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["group"]


def join(client, u, group):
    r = client.post("/groups/join", json={"invite_code": group["invite_code"]}, headers=u["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)


def leave(client, u, group):
    assert client.post(f"/groups/{group['id']}/leave", headers=u["headers"]).status_code == 200


def group_item(client, u, group, name="Rice"):
    r = client.post("/items", json={"items": [{"name": name, "group_id": group["id"]}]}, headers=u["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["items"][0]


def impact(client, u):
    r = client.get("/impact?range=all", headers=u["headers"])
    assert r.status_code == 200
    return r.get_json()


def db_item(sql, iid):
    return sql("SELECT removed_at, outcome, name FROM items WHERE id = :i", i=iid)[0]


def err(r, status, code):
    assert r.status_code == status, (r.status_code, r.get_data(as_text=True))
    assert r.get_json()["error"]["code"] == code
    return r.get_json()["error"]["message"]


@pytest.fixture
def ex(client, user, user2):
    """user created the group and a group item, user2 joined; then user LEFT (ex-member, still the item owner)."""
    grp = mk_group(client, user)
    join(client, user2, grp)
    it = group_item(client, user, grp)
    leave(client, user, grp)
    return grp, it


# ---- B1 -----------------------------------------------------------------------------------------
def test_ex_member_owner_patch_is_403(client, user, ex, sql):
    _, it = ex
    err(client.patch(f"/items/{it['id']}", json={"name": "Hacked"}, headers=user["headers"]), 403, "forbidden")
    assert db_item(sql, it["id"])["name"] == "Rice"


def test_ex_member_owner_remove_is_403_and_nothing_written(client, user, ex, sql, events):
    _, it = ex
    before = impact(client, user)
    err(client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=user["headers"]), 403, "forbidden")
    assert db_item(sql, it["id"])["removed_at"] is None
    assert events(item_id=it["id"], event_type="remove") == []
    assert impact(client, user) == before


def test_ex_member_restore_is_403_and_impact_unchanged(client, user, user2, sql, events):
    grp = mk_group(client, user)
    join(client, user2, grp)
    it = group_item(client, user, grp)
    r = client.post(f"/items/{it['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "expired"},
                    headers=user["headers"])
    assert r.status_code == 200
    leave(client, user, grp)
    before = impact(client, user)
    err(client.post(f"/items/{it['id']}/restore", headers=user["headers"]), 403, "forbidden")
    assert db_item(sql, it["id"])["removed_at"] is not None
    assert len(events(item_id=it["id"], event_type="remove")) == 1
    assert impact(client, user) == before


def test_ex_member_batch_alone_404_nothing_removed(client, user, ex, sql, events):
    _, it = ex
    before = impact(client, user)
    err(client.post("/items/remove-batch", json={"item_ids": [it["id"]], "outcome": "used"},
                    headers=user["headers"]), 404, "not_found")
    assert db_item(sql, it["id"])["removed_at"] is None
    assert events(item_id=it["id"], event_type="remove") == []
    assert impact(client, user) == before


def test_ex_member_batch_mixed_with_personal_item_is_atomic(client, user, ex, make_item, sql):
    _, it = ex
    mine = make_item(user)
    before = impact(client, user)
    err(client.post("/items/remove-batch", json={"item_ids": [mine["id"], it["id"]], "outcome": "used"},
                    headers=user["headers"]), 404, "not_found")
    assert db_item(sql, mine["id"])["removed_at"] is None
    assert db_item(sql, it["id"])["removed_at"] is None
    assert impact(client, user) == before


def test_ex_member_restore_batch_404_nothing_changed(client, user, user2, make_item, sql):
    grp = mk_group(client, user)
    join(client, user2, grp)
    it = group_item(client, user, grp)
    mine = make_item(user)
    for i in (it, mine):
        assert client.post(f"/items/{i['id']}/remove", json={"outcome": "used"}, headers=user["headers"]).status_code == 200
    leave(client, user, grp)
    before = impact(client, user)
    err(client.post("/items/restore-batch", json={"item_ids": [mine["id"], it["id"]]}, headers=user["headers"]),
        404, "not_found")
    assert db_item(sql, it["id"])["removed_at"] is not None
    assert db_item(sql, mine["id"])["removed_at"] is not None
    assert impact(client, user) == before


def test_current_member_control_owner_and_other_member(client, user, user2, make_item):
    grp = mk_group(client, user)
    join(client, user2, grp)
    it = group_item(client, user, grp)
    assert client.patch(f"/items/{it['id']}", json={"name": "Brown rice"}, headers=user["headers"]).status_code == 200
    # a non-owner member may remove/restore (existing behaviour), but not PATCH
    err(client.patch(f"/items/{it['id']}", json={"name": "x"}, headers=user2["headers"]), 403, "forbidden")
    assert client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=user2["headers"]).status_code == 200
    assert client.post(f"/items/{it['id']}/restore", headers=user2["headers"]).status_code == 200
    it2 = group_item(client, user, grp, "Beans")
    r = client.post("/items/remove-batch", json={"item_ids": [it["id"], it2["id"]], "outcome": "used"},
                    headers=user["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    r = client.post("/items/restore-batch", json={"item_ids": [it["id"], it2["id"]]}, headers=user["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)


def test_rejoined_member_regains_access(client, user, user2, ex):
    grp, it = ex
    join(client, user, grp)
    assert client.patch(f"/items/{it['id']}", json={"name": "Back"}, headers=user["headers"]).status_code == 200


def test_ex_member_cannot_share_group_item(client, user, ex):
    _, it = ex
    r = client.post("/share", json={"item_id": it["id"]}, headers=user["headers"])
    assert r.status_code in (400, 403, 404), r.get_data(as_text=True)


def test_ex_member_group_item_not_in_group_pantry(client, user, ex):
    grp, _ = ex
    assert client.get(f"/groups/{grp['id']}/pantry", headers=user["headers"]).status_code in (403, 404)


# ---- B2 -----------------------------------------------------------------------------------------
NUL = "a\x00b"
ITEM_ID = "00000000-0000-0000-0000-000000000001"


def _nul_cases():
    return [
        ("post", "/auth/signup", {"email": "n@example.com", "password": "pw-correct-horse-9", "display_name": NUL}),
        ("post", "/auth/signup", {"email": "n@example.com", "password": "pw\x00correct-horse", "display_name": "N"}),
        ("post", "/auth/signup", {"email": "n\x00@example.com", "password": "pw-correct-horse-9", "display_name": "N"}),
        ("post", "/auth/login", {"email": "n@example.com", "password": NUL}),
        ("post", "/auth/login", {"email": NUL, "password": "x"}),
        ("post", "/friends", {"email": NUL}),
        ("post", "/groups", {"name": NUL}),
        ("post", "/groups/join", {"invite_code": NUL}),
        ("post", "/items", {"items": [{"name": NUL}]}),
        ("post", "/items", {"items": [{"name": "Milk", "unit": NUL}]}),
        ("post", "/items", {"items": [{"name": "Milk", "storage": NUL}]}),  # nested in list -> dict
        ("post", "/items", {"items": [{"name": "Milk"}], "extra": {"deep": [{"k": NUL}]}}),
        ("post", "/items", {"items": [{"name": "Milk"}], "ke\x00y": 1}),  # dict KEY
        ("post", "/items", {"items": [{"name": "Milk", "n\x00": 1}]}),  # nested dict KEY
        ("post", "/items/parse-text", {"text": NUL}),
        ("post", "/requests", {"text": NUL}),
        ("post", "/items/remove-batch", {"item_ids": [ITEM_ID], "outcome": "used", "x": NUL}),
        ("post", "/share", {"item_id": ITEM_ID, "group_id": NUL}),
    ]


@pytest.mark.parametrize("method,path,body", _nul_cases())
def test_nul_in_json_is_400_not_500(client, user, method, path, body):
    r = getattr(client, method)(path, json=body, headers=user["headers"])
    assert r.status_code == 400, (path, r.status_code, r.get_data(as_text=True))
    assert r.get_json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("field", ["name", "unit", "notes"])
def test_nul_in_patch_is_400(client, user, make_item, sql, field):
    it = make_item(user)
    r = client.patch(f"/items/{it['id']}", json={field: NUL}, headers=user["headers"])
    assert r.status_code == 400, r.get_data(as_text=True)
    assert r.get_json()["error"]["code"] == "validation_error"
    assert db_item(sql, it["id"])["name"] == "Milk"


def test_nul_in_remove_body_is_400(client, user, make_item):
    it = make_item(user)
    r = client.post(f"/items/{it['id']}/remove", json={"outcome": "thrown_out", "waste_reason": NUL},
                    headers=user["headers"])
    assert r.status_code == 400


def test_nul_escape_in_raw_body_is_400(client, user):
    r = client.post("/groups", data='{"name": "a\\u0000b"}', content_type="application/json",
                    headers=user["headers"])
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "validation_error"


def test_nul_in_query_string_is_not_500(client, user):
    r = client.get("/items?q=a%00b", headers=user["headers"])
    assert r.status_code < 500, r.get_data(as_text=True)


def test_recipes_suggest_nul_is_not_500(client, user, make_item):
    """/recipes/suggest parses its own body (not json_body): NUL is not rejected, but must not 500."""
    make_item(user)
    r = client.post("/recipes/suggest", json={"dietary": [NUL]}, headers=user["headers"])
    assert r.status_code != 500, r.get_data(as_text=True)  # 502 upstream_unavailable here (no Gemini key)


def test_data_error_handler_returns_400_rolls_back_and_session_recovers(app, client, user, monkeypatch):
    from sqlalchemy.exc import DataError
    from app.extensions import db
    from app.services import social

    def boom(*a, **k):
        raise DataError("stmt", {}, Exception("invalid byte sequence"))

    monkeypatch.setattr(social, "my_groups", boom)
    calls = []
    real = db.session.rollback
    monkeypatch.setattr(db.session, "rollback", lambda: (calls.append(1), real())[1], raising=False)
    r = client.get("/share", headers=user["headers"])
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "validation_error"
    assert "invalid byte" not in r.get_data(as_text=True)  # no driver text leaked
    monkeypatch.undo()
    assert client.get("/items", headers=user["headers"]).status_code == 200


# ---- B3 -----------------------------------------------------------------------------------------
def _post_item(client, u, **over):
    p = {"name": "Milk"}
    p.update(over)
    return client.post("/items", json={"items": [p]}, headers=u["headers"])


def test_item_name_cap(client, user):
    assert _post_item(client, user, name="n" * 200).status_code == 201
    r = _post_item(client, user, name="n" * 201)
    assert err(r, 400, "validation_error")
    assert _post_item(client, user, name=("n" * 200) + "   ").status_code == 201  # cap applies after strip


def test_item_unit_cap(client, user):
    assert _post_item(client, user, unit="u" * 32).status_code == 201
    err(_post_item(client, user, unit="u" * 33), 400, "validation_error")


def test_patch_name_unit_caps(client, user, make_item):
    it = make_item(user)
    url = f"/items/{it['id']}"
    assert client.patch(url, json={"name": "n" * 200}, headers=user["headers"]).status_code == 200
    err(client.patch(url, json={"name": "n" * 201}, headers=user["headers"]), 400, "validation_error")
    assert client.patch(url, json={"unit": "u" * 32}, headers=user["headers"]).status_code == 200
    err(client.patch(url, json={"unit": "u" * 33}, headers=user["headers"]), 400, "validation_error")


def test_failed_patch_cap_does_not_half_apply(client, user, make_item, sql):
    it = make_item(user)
    r = client.patch(f"/items/{it['id']}", json={"quantity": 9, "name": "n" * 201}, headers=user["headers"])
    assert r.status_code == 400
    again = client.get("/items", headers=user["headers"]).get_json()
    rows = again["items"] if isinstance(again, dict) else again
    assert float(rows[0]["quantity"]) == 2 and rows[0]["name"] == "Milk"


def test_batch_with_one_overlong_name_creates_nothing(client, user, sql):
    r = client.post("/items", json={"items": [{"name": "ok"}, {"name": "n" * 201}]}, headers=user["headers"])
    assert r.status_code == 400
    assert sql("SELECT count(*) AS c FROM items")[0]["c"] == 0


def _email(total):
    local = "a" * (total - len("@example.com"))
    return local + "@example.com"


def test_signup_email_cap(client):
    ok = client.post("/auth/signup", json={"email": _email(254), "password": "pw-correct-horse-9", "display_name": "E"})
    assert ok.status_code == 201, ok.get_data(as_text=True)
    r = client.post("/auth/signup", json={"email": _email(255), "password": "pw-correct-horse-9", "display_name": "E"})
    err(r, 400, "validation_error")


def test_signup_display_name_cap(client):
    pw = "pw-correct-horse-9"
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": pw, "display_name": "d" * 60}).status_code == 201
    err(client.post("/auth/signup", json={"email": "b@example.com", "password": pw, "display_name": "d" * 61}),
        400, "validation_error")


def test_signup_password_cap(client):
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": "p" * 256, "display_name": "D"}).status_code == 201
    err(client.post("/auth/signup", json={"email": "b@example.com", "password": "p" * 257, "display_name": "D"}),
        400, "validation_error")
    err(client.post("/auth/signup", json={"email": "c@example.com", "password": "p" * 7, "display_name": "D"}),
        400, "validation_error")


def test_login_caps_and_exact_limit_password_works(client):
    pw = "p" * 256
    client.post("/auth/signup", json={"email": "a@example.com", "password": pw, "display_name": "D"})
    assert client.post("/auth/login", json={"email": "a@example.com", "password": pw}).status_code == 200
    err(client.post("/auth/login", json={"email": "a@example.com", "password": "p" * 257}), 400, "validation_error")
    err(client.post("/auth/login", json={"email": _email(255), "password": "x"}), 400, "validation_error")
    err(client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-pass"}), 401, "invalid_credentials")


def test_friends_email_cap(client, user, user2):
    err(client.post("/friends", json={"email": _email(255)}, headers=user["headers"]), 400, "validation_error")
    # exactly 254 is accepted by the cap and falls through to the normal lookup (404 no such user)
    assert client.post("/friends", json={"email": _email(254)}, headers=user["headers"]).status_code == 404


def test_group_name_and_invite_code_caps(client, user):
    assert client.post("/groups", json={"name": "g" * 60}, headers=user["headers"]).status_code == 201
    err(client.post("/groups", json={"name": "g" * 61}, headers=user["headers"]), 400, "validation_error")
    err(client.post("/groups/join", json={"invite_code": "c" * 65}, headers=user["headers"]), 400, "validation_error")
    assert client.post("/groups/join", json={"invite_code": "c" * 64}, headers=user["headers"]).status_code == 404


# ---- B4 -----------------------------------------------------------------------------------------
BAD = "not-a-uuid"


@pytest.mark.parametrize("method,path,msg", [
    ("get", f"/groups/{BAD}", "Group not found."),
    ("post", f"/groups/{BAD}/leave", "Group not found."),
    ("get", f"/groups/{BAD}/pantry", "Group not found."),
    ("post", f"/friends/{BAD}/accept", "User not found."),
    ("delete", f"/friends/{BAD}", "User not found."),
    ("delete", f"/requests/{BAD}", "Request not found."),
    ("post", f"/requests/{BAD}/fulfil", "Request not found."),
    ("delete", f"/share/{BAD}", "Listing not found."),
    ("post", f"/share/{BAD}/claim", "Listing not found."),
    ("patch", f"/items/{BAD}", "Item not found."),
    ("post", f"/items/{BAD}/remove", "Item not found."),
    ("post", f"/items/{BAD}/restore", "Item not found."),
])
def test_malformed_path_id_messages(client, user, method, path, msg):
    kw = {"headers": user["headers"]}
    if method in ("post", "patch"):
        kw["json"] = {"outcome": "used"} if path.endswith("/remove") else {}
    r = getattr(client, method)(path, **kw)
    assert r.status_code == 404, (path, r.status_code, r.get_data(as_text=True))
    assert r.get_json()["error"]["code"] == "not_found"
    assert r.get_json()["error"]["message"] == msg


def test_well_formed_unknown_ids_still_404(client, user):
    z = "00000000-0000-0000-0000-000000000009"
    assert client.get(f"/groups/{z}", headers=user["headers"]).status_code in (403, 404)
    assert client.delete(f"/requests/{z}", headers=user["headers"]).status_code == 404
