"""Removal flow: the core of waste tracking."""
import uuid

import pytest

from conftest import iso_in


def remove(client, u, item, **body):
    return client.post(f"/items/{item['id']}/remove", json=body, headers=u["headers"])


def row(sql, item_id):
    return sql("SELECT * FROM items WHERE id = :i", i=item_id)[0]


def body_item(r):
    b = r.get_json()
    return b.get("item", b)


@pytest.mark.parametrize("outcome", ["used", "donated"])
def test_remove_saved(client, user, make_item, sql, events, outcome):
    it = make_item(user, category="dairy", quantity=2, est_price=3.5, predicted_expiry=iso_in(5))
    r = remove(client, user, it, outcome=outcome)
    assert r.status_code == 200, r.get_data(as_text=True)
    bi = body_item(r)
    assert bi["outcome"] == outcome and bi["removed_at"] and bi["waste_reason"] is None
    assert bi["removed_after_expiry"] is False
    d = row(sql, it["id"])
    assert d["removed_at"] is not None and d["outcome"] == outcome and d["waste_reason"] is None
    assert d["removed_after_expiry"] is False
    ev = events(item_id=it["id"], event_type="remove")
    assert len(ev) == 1
    e = ev[0]
    assert e["outcome"] == outcome and e["category"] == "dairy" and float(e["quantity"]) == 2
    assert float(e["est_price"]) == 3.5 and e["waste_reason"] is None
    assert e["co2e_kg"] is not None and float(e["co2e_kg"]) > 0
    assert str(e["user_id"]) == user["user"]["id"]


@pytest.mark.parametrize("reason", ["expired", "didnt_like", "forgot", "other"])
def test_remove_thrown_out(client, user, make_item, sql, events, reason):
    it = make_item(user, category="meat", quantity=1, est_price=8, predicted_expiry=iso_in(3))
    r = remove(client, user, it, outcome="thrown_out", waste_reason=reason)
    assert r.status_code == 200, r.get_data(as_text=True)
    d = row(sql, it["id"])
    assert d["outcome"] == "thrown_out" and d["waste_reason"] == reason and d["removed_at"]
    ev = events(item_id=it["id"], event_type="remove")
    assert len(ev) == 1
    assert ev[0]["outcome"] == "thrown_out" and ev[0]["waste_reason"] == reason
    assert ev[0]["category"] == "meat" and float(ev[0]["est_price"]) == 8
    assert float(ev[0]["co2e_kg"]) > 0


def test_removed_after_expiry_true(client, user, make_item, sql):
    it = make_item(user, predicted_expiry=iso_in(-2))
    assert remove(client, user, it, outcome="thrown_out", waste_reason="expired").status_code == 200
    assert row(sql, it["id"])["removed_after_expiry"] is True


def test_removed_after_expiry_false_future(client, user, make_item, sql):
    it = make_item(user, predicted_expiry=iso_in(4))
    remove(client, user, it, outcome="used")
    assert row(sql, it["id"])["removed_after_expiry"] is False


def test_thrown_out_requires_reason(client, user, make_item, sql, events):
    it = make_item(user)
    r = remove(client, user, it, outcome="thrown_out")
    assert r.status_code == 400
    assert r.get_json()["error"]["code"]
    assert row(sql, it["id"])["removed_at"] is None
    assert events(item_id=it["id"], event_type="remove") == []


def test_thrown_out_invalid_reason(client, user, make_item, events):
    it = make_item(user)
    assert remove(client, user, it, outcome="thrown_out", waste_reason="bored").status_code == 400
    assert events(item_id=it["id"], event_type="remove") == []


@pytest.mark.parametrize("outcome", ["used", "donated"])
def test_reason_rejected_on_saved(client, user, make_item, sql, events, outcome):
    it = make_item(user)
    r = remove(client, user, it, outcome=outcome, waste_reason="forgot")
    assert r.status_code == 400
    assert row(sql, it["id"])["removed_at"] is None
    assert events(item_id=it["id"], event_type="remove") == []


@pytest.mark.parametrize("body", [{}, {"outcome": "eaten"}, {"outcome": None}])
def test_invalid_outcome(client, user, make_item, events, body):
    it = make_item(user)
    assert remove(client, user, it, **body).status_code == 400
    assert events(item_id=it["id"], event_type="remove") == []


@pytest.mark.parametrize("outcome,extra", [("used", {}), ("thrown_out", {"waste_reason": "other"})])
def test_recipient_only_on_donated(client, user, user2, make_item, events, outcome, extra):
    it = make_item(user)
    r = remove(client, user, it, outcome=outcome, recipient_id=user2["user"]["id"], **extra)
    assert r.status_code == 400
    assert events(item_id=it["id"], event_type="remove") == []


def test_already_removed_409_single_event(client, user, make_item, events):
    it = make_item(user)
    assert remove(client, user, it, outcome="used").status_code == 200
    r = remove(client, user, it, outcome="thrown_out", waste_reason="forgot")
    assert r.status_code == 409
    assert r.get_json()["error"]["code"]
    assert len(events(item_id=it["id"], event_type="remove")) == 1
    assert events(item_id=it["id"], event_type="remove")[0]["outcome"] == "used"


def test_remove_auth_404_403(client, user, user2, make_item, events):
    it = make_item(user)
    assert client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}).status_code == 401
    assert remove(client, user2, it, outcome="used").status_code == 403
    assert events(item_id=it["id"], event_type="remove") == []
    ghost = {"id": str(uuid.uuid4())}
    assert remove(client, user, ghost, outcome="used").status_code == 404
    assert remove(client, user, {"id": "not-a-uuid"}, outcome="used").status_code in (400, 404)


def test_exactly_one_add_and_one_remove(client, user, make_item, events):
    it = make_item(user)
    remove(client, user, it, outcome="used")
    types = sorted(e["event_type"] for e in events(item_id=it["id"]))
    assert types == ["add", "remove"]


def befriend(client, a, b):
    assert client.post("/friends", json={"email": b["email"]}, headers=a["headers"]).status_code in (200, 201)
    assert client.post(f"/friends/{a['user']['id']}/accept", headers=b["headers"]).status_code == 200


def test_donated_fulfils_open_listing(client, user, user2, make_item, sql, events):
    """Share listings table is Social (wave 3) - inserted directly if the table exists."""
    if not sql("SELECT to_regclass('public.share_listings') AS t")[0]["t"]:
        pytest.skip("share_listings table not present yet")
    befriend(client, user, user2)
    it = make_item(user)
    lid = str(uuid.uuid4())
    sql("INSERT INTO share_listings (id, item_id, owner_id, status) VALUES (:l, :i, :o, 'open')",
        l=lid, i=it["id"], o=user["user"]["id"])
    r = remove(client, user, it, outcome="donated", recipient_id=user2["user"]["id"])
    assert r.status_code == 200, r.get_data(as_text=True)
    s = sql("SELECT * FROM share_listings WHERE id = :l", l=lid)[0]
    assert s["status"] == "fulfilled" and str(s["recipient_id"]) == user2["user"]["id"]
    assert s["fulfilled_at"] is not None
    assert len(events(item_id=it["id"], event_type="remove")) == 1


def test_used_does_not_fulfil_listing(client, user, make_item, sql):
    if not sql("SELECT to_regclass('public.share_listings') AS t")[0]["t"]:
        pytest.skip("share_listings table not present yet")
    it = make_item(user)
    lid = str(uuid.uuid4())
    sql("INSERT INTO share_listings (id, item_id, owner_id, status) VALUES (:l, :i, :o, 'open')",
        l=lid, i=it["id"], o=user["user"]["id"])
    remove(client, user, it, outcome="used")
    assert sql("SELECT status FROM share_listings WHERE id=:l", l=lid)[0]["status"] == "open"


def test_removed_excluded_from_list(client, user, make_item):
    it = make_item(user)
    remove(client, user, it, outcome="used")
    r = client.get("/items", headers=user["headers"])
    body = r.get_json()
    lst = body["items"] if isinstance(body, dict) else body
    assert lst == []


def test_donated_fulfils_listing_created_via_api(client, user, user2, make_item, sql, events):
    befriend(client, user, user2)
    it = make_item(user)
    r = client.post("/share", json={"item_id": it["id"]}, headers=user["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)
    r = remove(client, user, it, outcome="donated", recipient_id=user2["user"]["id"])
    assert r.status_code == 200
    s = sql("SELECT * FROM share_listings WHERE item_id = :i", i=it["id"])
    assert len(s) == 1 and s[0]["status"] == "fulfilled"
    assert str(s[0]["recipient_id"]) == user2["user"]["id"] and s[0]["fulfilled_at"]
    assert len(events(item_id=it["id"], event_type="remove")) == 1


def test_donated_recipient_must_exist(client, user, make_item, events):
    it = make_item(user)
    r = remove(client, user, it, outcome="donated", recipient_id=str(uuid.uuid4()))
    assert r.status_code == 404  # feat/donation-recipient: unknown / unreachable recipient is 404
    assert events(item_id=it["id"], event_type="remove") == []


def test_share_rules(client, user, user2, make_item):
    it = make_item(user)
    assert client.post("/share", json={}, headers=user["headers"]).status_code == 400
    assert client.post("/share", json={"item_id": it["id"]}, headers=user2["headers"]).status_code == 403
    assert client.post("/share", json={"item_id": str(uuid.uuid4())}, headers=user["headers"]).status_code == 404
    assert client.post("/share", json={"item_id": it["id"]}, headers=user["headers"]).status_code == 201
    r = client.post("/share", json={"item_id": it["id"]}, headers=user["headers"])
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "already_shared"
    remove(client, user, it, outcome="used")
    r = client.post("/share", json={"item_id": it["id"]}, headers=user["headers"])
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "already_removed"
