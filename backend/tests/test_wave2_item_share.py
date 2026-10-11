"""Owner's items carry `share: {id, status, claimed_by: {id, name}|null} | null`, without N+1 queries."""
import pytest
from sqlalchemy import event

from app.extensions import db
from conftest import _signup, items_of


@pytest.fixture
def pair(client):
    a = _signup(client, name="Alice")
    b = _signup(client, name="Bob")
    r = client.post("/friends", json={"email": b["email"]}, headers=a["headers"])
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    r = client.post(f"/friends/{a['user']['id']}/accept", headers=b["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    return a, b


def share(client, u, item, **kw):
    r = client.post("/share", json={"item_id": item["id"], **kw}, headers=u["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["listing"]


def listing_of(client, u, item_id):
    its = items_of(client.get("/items?include_removed=true", headers=u["headers"]))
    return next(i for i in its if i["id"] == item_id)


def test_unshared_item_share_is_null(client, user, make_item):
    it = make_item(user)
    assert "share" in it and it["share"] is None
    got = listing_of(client, user, it["id"])
    assert "share" in got and got["share"] is None


def test_create_response_has_share_null(client, user):
    r = client.post("/items", json={"items": [{"name": "x"}]}, headers=user["headers"])
    assert items_of(r)[0]["share"] is None


def test_patch_response_has_share(client, pair, make_item):
    a, b = pair
    it = make_item(a)
    lst = share(client, a, it)
    out = client.patch(f"/items/{it['id']}", json={"name": "Z"}, headers=a["headers"]).get_json()["item"]
    assert out["share"]["id"] == lst["id"] and out["share"]["status"] == "open"


def test_open_listing(client, pair, make_item):
    a, b = pair
    it = make_item(a)
    lst = share(client, a, it)
    s = listing_of(client, a, it["id"])["share"]
    assert s == {"id": lst["id"], "status": "open", "claimed_by": None}


def test_group_listing_also_reported(client, pair, make_item):
    a, b = pair
    g = client.post("/groups", json={"name": "G"}, headers=a["headers"]).get_json()
    g = g.get("group", g)
    it = make_item(a)
    lst = share(client, a, it, group_id=g["id"])
    s = listing_of(client, a, it["id"])["share"]
    assert s["id"] == lst["id"] and s["status"] == "open"


def test_claimed_listing_shows_claimer(client, pair, make_item):
    a, b = pair
    it = make_item(a)
    lst = share(client, a, it)
    r = client.post(f"/share/{lst['id']}/claim", headers=b["headers"])
    assert r.status_code == 200
    s = listing_of(client, a, it["id"])["share"]
    assert s["id"] == lst["id"]
    assert s["claimed_by"] == {"id": b["user"]["id"], "name": "Bob"}
    assert set(s) == {"id", "status", "claimed_by"}
    assert set(s["claimed_by"]) == {"id", "name"}


def test_cancelled_listing_not_reported_as_open(client, pair, make_item):
    a, b = pair
    it = make_item(a)
    lst = share(client, a, it)
    assert client.delete(f"/share/{lst['id']}", headers=a["headers"]).status_code == 200
    s = listing_of(client, a, it["id"])["share"]
    assert s is None or s["status"] == "cancelled"
    # relisting after cancel: the current (open) listing wins
    new = share(client, a, it)
    s = listing_of(client, a, it["id"])["share"]
    assert s["id"] == new["id"] and s["status"] == "open"


def test_fulfilled_after_donation(client, pair, make_item):
    a, b = pair
    it = make_item(a)
    lst = share(client, a, it)
    client.post(f"/share/{lst['id']}/claim", headers=b["headers"])
    r = client.post(f"/items/{it['id']}/remove", json={"outcome": "donated"}, headers=a["headers"])
    assert r.status_code == 200
    s = r.get_json()["item"]["share"]
    assert s["id"] == lst["id"] and s["status"] == "fulfilled"
    assert s["claimed_by"]["id"] == b["user"]["id"]
    assert listing_of(client, a, it["id"])["share"]["status"] == "fulfilled"


def test_claim_visible_after_claimer_changes_name_not_needed_but_name_is_display_name(client, pair, make_item, sql):
    a, b = pair
    it = make_item(a)
    lst = share(client, a, it)
    client.post(f"/share/{lst['id']}/claim", headers=b["headers"])
    sql("UPDATE users SET display_name='Robert' WHERE id=:i", i=b["user"]["id"])
    assert listing_of(client, a, it["id"])["share"]["claimed_by"]["name"] == "Robert"


def test_other_users_never_see_share_object(client, pair, make_item, signup):
    a, b = pair
    it = make_item(a)
    lst = share(client, a, it)
    client.post(f"/share/{lst['id']}/claim", headers=b["headers"])
    # claimer and bystanders' own lists never include Alice's item
    for u in (b, signup()):
        assert it["id"] not in {i["id"] for i in items_of(client.get("/items", headers=u["headers"]))}
    # the Food Pantry entry's embedded item summary carries no share object
    c = signup()
    client.post("/friends", json={"email": a["email"]}, headers=c["headers"])
    client.post(f"/friends/{c['user']['id']}/accept", headers=a["headers"])
    it2 = make_item(a, name="Eggs")
    share(client, a, it2)
    for u in (b, c):
        for l in client.get("/share", headers=u["headers"]).get_json()["listings"]:
            assert "share" not in l["item"]
            assert "share" not in l


def test_group_pantry_items_have_no_foreign_share(client, pair, make_item):
    a, b = pair
    g = client.post("/groups", json={"name": "G"}, headers=a["headers"]).get_json()
    g = g.get("group", g)
    r = client.post("/groups/join", json={"invite_code": g["invite_code"]}, headers=b["headers"])
    it = make_item(a)
    share(client, a, it)
    client.post("/items", json={"group_id": g["id"], "items": [{"name": "Pot"}]}, headers=a["headers"])
    assert r.status_code == 200
    pantry = client.get(f"/groups/{g['id']}/pantry", headers=b["headers"]).get_json()
    assert pantry["items"] and all("share" not in i for i in pantry["items"])


def _count_queries(app, fn):
    n = []

    def hook(conn, cur, stmt, params, ctx, many):
        n.append(stmt)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", hook)
        try:
            fn()
        finally:
            event.remove(db.engine, "before_cursor_execute", hook)
    return n


def test_no_n_plus_one(app, client, pair, make_item):
    a, b = pair

    claimed = []

    def make(n, start):
        for k in range(start, start + n):
            it = make_item(a, name=f"Item{k}")
            lst = share(client, a, it)
            if k % 2 == 0:
                client.post(f"/share/{lst['id']}/claim", headers=b["headers"])
                claimed.append(k)

    make(1, 0)
    one = _count_queries(app, lambda: client.get("/items", headers=a["headers"]))
    make(19, 1)
    twenty = _count_queries(app, lambda: client.get("/items", headers=a["headers"]))
    got = items_of(client.get("/items", headers=a["headers"]))
    assert len(got) == 20 and all(i["share"] for i in got)
    assert sum(1 for i in got if i["share"]["claimed_by"]) == len(claimed)
    assert len(twenty) == len(one), f"query count grew with items: {len(one)} -> {len(twenty)}\n" + "\n".join(twenty)


def test_no_n_plus_one_grouped(app, client, pair, make_item):
    a, b = pair
    for k in range(20):
        share(client, a, make_item(a, name=f"I{k}", category="dairy" if k % 2 else "meat"))
    n20 = _count_queries(app, lambda: client.get("/items?group_by=food_group", headers=a["headers"]))
    assert len(n20) <= 8, "\n".join(n20)
