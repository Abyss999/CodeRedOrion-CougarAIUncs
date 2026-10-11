"""items.nutrition: stored on create (candidate round trip), served everywhere, never editable."""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from conftest import items_of, iso_in

NUT = {"basis": "per_100g", "kcal": 52, "protein_g": 0.3, "carbs_g": 13.8, "fat_g": 0.2,
       "fiber_g": 2.4, "sugar_g": 10.4, "sodium_mg": 1, "estimated": True}


def post(client, u, **over):
    p = {"name": "Apple", "category": "produce_hardy", "storage": "fridge", "quantity": 3, "unit": "piece",
         "source": "photo"}
    p.update(over)
    return client.post("/items", json={"items": [p]}, headers=u["headers"])


def count_items(sql):
    return sql("SELECT count(*) AS n FROM items")[0]["n"]


def is_sql_null(sql, item_id):
    return sql("SELECT nutrition IS NULL AS is_null FROM items WHERE id=:i", i=item_id)[0]["is_null"]


def impact(client, u):
    return client.get("/impact?range=all", headers=u["headers"]).get_json()


def test_new_item_without_nutrition_is_sql_null(client, user, sql):
    it = items_of(post(client, user))[0]
    assert it["nutrition"] is None
    assert is_sql_null(sql, it["id"]) is True, "an absent nutrition must be SQL NULL, not JSON null"


def test_explicit_null_means_none(client, user, sql):
    r = post(client, user, nutrition=None)
    assert r.status_code == 201, r.get_data(as_text=True)
    it = items_of(r)[0]
    assert it["nutrition"] is None
    assert is_sql_null(sql, it["id"]) is True


def test_create_stores_and_serves_nutrition(client, user, sql):
    r = post(client, user, nutrition=NUT)
    assert r.status_code == 201, r.get_data(as_text=True)
    it = items_of(r)[0]
    assert it["nutrition"] == NUT
    assert sql("SELECT nutrition FROM items WHERE id=:i", i=it["id"])[0]["nutrition"] == NUT
    listed = items_of(client.get("/items", headers=user["headers"]))
    assert listed[0]["nutrition"] == NUT


def test_unknown_keys_dropped_and_estimated_forced_true(client, user):
    it = items_of(post(client, user, nutrition=dict(NUT, estimated=False, brand="Acme")))[0]
    assert it["nutrition"] == NUT


def test_candidate_round_trip_with_every_candidate_field(client, user):
    """A candidate posted back as-is: expiry_source, freshness, confidence, bbox and nutrition together."""
    r = post(client, user, predicted_expiry=iso_in(6), expiry_source="gemini", freshness="semi_fresh",
             confidence=0.9, bbox=[1, 2, 30, 40], food_group="fruit", nutrition=NUT)
    assert r.status_code == 201, r.get_data(as_text=True)
    it = items_of(r)[0]
    assert it["nutrition"] == NUT and it["expiry_source"] == "gemini" and it["freshness"] == "semi_fresh"
    assert it["confidence"] == 0.9 and it["predicted_expiry"] == iso_in(6)


@pytest.mark.parametrize("bad", [
    "52", 5, True, [], {}, [NUT],
    {"kcal": 52},                                              # core keys missing
    dict(NUT, basis="per_serving"),
    dict(NUT, kcal="52"),                                      # numeric string
    dict(NUT, kcal=1e9),                                       # out of bounds
    dict(NUT, protein_g=-1),
    dict(NUT, fiber_g="lots"),                                 # invalid optional key
    dict(NUT, kcal=900, protein_g=40, carbs_g=40, fat_g=30),   # 110 g of macros in 100 g of food
    dict(NUT, kcal=500),                                       # nowhere near 4P + 4C + 9F
])
def test_invalid_nutrition_is_400_and_writes_nothing(client, user, sql, bad):
    r = post(client, user, nutrition=bad)
    assert r.status_code == 400, r.get_data(as_text=True)
    assert r.get_json()["error"]["code"] == "validation_error"
    assert count_items(sql) == 0, "a 400 must write nothing"


def test_one_bad_item_rejects_the_whole_batch(client, user, sql):
    ps = [{"name": "A", "nutrition": NUT}, {"name": "B", "nutrition": {"kcal": 1}}]
    r = client.post("/items", json={"items": ps}, headers=user["headers"])
    assert r.status_code == 400
    assert count_items(sql) == 0
    assert sql("SELECT count(*) AS n FROM food_events")[0]["n"] == 0, "no add events for a rejected batch"


def test_batch_mixed_with_and_without_nutrition(client, user):
    ps = [{"name": "A", "nutrition": NUT}, {"name": "B"}]
    r = client.post("/items", json={"items": ps}, headers=user["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)
    by = {i["name"]: i for i in items_of(r)}
    assert by["A"]["nutrition"] == NUT and by["B"]["nutrition"] is None


def test_patch_rejects_nutrition_and_leaves_it_alone(client, user, make_item):
    it = make_item(user, nutrition=NUT)
    h = user["headers"]
    r = client.patch(f"/items/{it['id']}", json={"nutrition": dict(NUT, kcal=60)}, headers=h)
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "validation_error"
    r = client.patch(f"/items/{it['id']}", json={"nutrition": None}, headers=h)
    assert r.status_code == 400, "nutrition cannot be cleared through PATCH either"
    r = client.patch(f"/items/{it['id']}", json={"name": "Renamed", "quantity": 4}, headers=h)
    assert r.status_code == 200
    assert r.get_json()["item"]["nutrition"] == NUT


def test_served_by_group_by_remove_restore_and_batches(client, user, make_item):
    h = user["headers"]
    it = make_item(user, nutrition=NUT)
    sections = client.get("/items?group_by=food_group", headers=h).get_json()["sections"]
    assert [i["nutrition"] for s in sections for i in s["items"]] == [NUT]
    r = client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=h)
    assert r.status_code == 200 and r.get_json()["item"]["nutrition"] == NUT
    r = client.post(f"/items/{it['id']}/restore", headers=h)
    assert r.status_code == 200 and r.get_json()["item"]["nutrition"] == NUT
    r = client.post("/items/remove-batch", json={"item_ids": [it["id"]], "outcome": "donated"}, headers=h)
    assert r.status_code == 200 and r.get_json()["items"][0]["nutrition"] == NUT
    r = client.post("/items/restore-batch", json={"item_ids": [it["id"]]}, headers=h)
    assert r.status_code == 200 and r.get_json()["items"][0]["nutrition"] == NUT


def test_served_in_the_group_pantry(client, user):
    h = user["headers"]
    gid = client.post("/groups", json={"name": "Flat 4"}, headers=h).get_json()["group"]["id"]
    r = post(client, user, nutrition=NUT, group_id=gid)
    assert r.status_code == 201, r.get_data(as_text=True)
    pantry = client.get(f"/groups/{gid}/pantry", headers=h).get_json()["items"]
    assert [i["nutrition"] for i in pantry] == [NUT]


def test_nutrition_does_not_change_events_or_impact(client, user, user2, make_item, events):
    """The same flow with and without nutrition: one `add` and one `remove` event each, identical /impact."""
    a = make_item(user, nutrition=NUT)
    b = make_item(user2)
    for u, it in ((user, a), (user2, b)):
        assert len(events(it["id"], "add")) == 1
        r = client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=u["headers"])
        assert r.status_code == 200
        assert len(events(it["id"], "remove")) == 1
    assert impact(client, user) == impact(client, user2)


def test_remove_then_restore_leaves_impact_as_before(client, user, make_item):
    before = impact(client, user)
    it = make_item(user, nutrition=NUT)
    r = client.post(f"/items/{it['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "forgot"},
                    headers=user["headers"])
    assert r.status_code == 200
    assert client.post(f"/items/{it['id']}/restore", headers=user["headers"]).status_code == 200
    assert impact(client, user) == before


def test_db_check_rejects_anything_but_an_object(client, user, sql):
    it = items_of(post(client, user, nutrition=NUT))[0]
    for bad in ("[1]", '"x"', "5", "true", "null"):
        with pytest.raises(IntegrityError):
            sql("UPDATE items SET nutrition = CAST(:v AS jsonb) WHERE id=:i", v=bad, i=it["id"])
    sql("UPDATE items SET nutrition = CAST(:v AS jsonb) WHERE id=:i", v="{}", i=it["id"])  # shape is the app's job
    sql("UPDATE items SET nutrition = NULL WHERE id=:i", i=it["id"])


def test_orm_none_is_sql_null_never_json_null(app, client, user, sql):
    """none_as_null=True: assigning None through the ORM must not store JSON null (the CHECK would reject it)."""
    from app.extensions import db
    from app.models import Item

    it = items_of(post(client, user, nutrition=NUT))[0]
    with app.app_context():
        row = db.session.get(Item, uuid.UUID(it["id"]))
        row.nutrition = None
        db.session.commit()
    assert is_sql_null(sql, it["id"]) is True
