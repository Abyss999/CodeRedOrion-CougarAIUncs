"""items.freshness / freshness_checked_at / confidence: stored on create, editable on PATCH, serialised."""
from datetime import datetime, timezone

import pytest

from conftest import items_of, iso_in

VALUES = ("fresh", "semi_fresh", "spoiled")


def post(client, u, **over):
    p = {"name": "Spinach", "category": "produce_leafy", "storage": "fridge", "quantity": 1, "unit": "bag",
         "source": "photo"}
    p.update(over)
    return client.post("/items", json={"items": [p]}, headers=u["headers"])


def db_row(sql, item_id):
    return sql("SELECT * FROM items WHERE id=:i", i=item_id)[0]


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_new_item_without_freshness_is_null(client, user, sql):
    it = items_of(post(client, user))[0]
    assert it["freshness"] is None
    assert it["freshness_checked_at"] is None
    assert it["confidence"] is None
    row = db_row(sql, it["id"])
    assert row["freshness"] is None and row["freshness_checked_at"] is None and row["confidence"] is None


@pytest.mark.parametrize("val", VALUES)
def test_create_with_each_value(client, user, sql, val):
    r = post(client, user, freshness=val)
    assert r.status_code == 201, r.get_data(as_text=True)
    it = items_of(r)[0]
    assert it["freshness"] == val
    assert db_row(sql, it["id"])["freshness"] == val
    assert it["freshness_checked_at"] is not None, "freshness set -> checked_at stamped"
    assert abs((datetime.now(timezone.utc) - parse_ts(it["freshness_checked_at"])).total_seconds()) < 120


@pytest.mark.parametrize("raw,expected", [
    ("Semi-Fresh", "semi_fresh"), ("semi fresh", "semi_fresh"), ("SPOILED", "spoiled"), ("Fresh", "fresh"),
    ("rotten", "spoiled"), ("use soon", "semi_fresh"), (" fresh ", "fresh"),
])
def test_create_variants_normalised_or_rejected(client, user, raw, expected):
    """Per API.md: variants are either normalised to the enum value or rejected with 400 (never stored raw)."""
    r = post(client, user, freshness=raw)
    assert r.status_code in (201, 400), r.get_data(as_text=True)
    if r.status_code == 201:
        assert items_of(r)[0]["freshness"] == expected
    else:
        assert r.get_json()["error"]["code"]


@pytest.mark.parametrize("bad", ["bogus", "", "mouldy-ish-maybe", "ripe"])
def test_create_unknown_string_becomes_fresh(client, user, caplog, bad):
    """API.md: unknown strings are normalised to `fresh` (with a WARNING), never stored raw."""
    with caplog.at_level("WARNING"):
        r = post(client, user, freshness=bad)
    assert r.status_code == 201, r.get_data(as_text=True)
    assert items_of(r)[0]["freshness"] == "fresh" and items_of(r)[0]["freshness_checked_at"]
    assert any("freshness_fallback" in m for m in caplog.messages)


@pytest.mark.parametrize("bad", [5, True, ["fresh"], {"a": 1}, 1.5])
def test_create_non_string_freshness_400(client, user, sql, bad):
    r = post(client, user, freshness=bad)
    assert r.status_code == 400, r.get_data(as_text=True)
    assert r.get_json()["error"]["code"]
    assert sql("SELECT count(*) AS n FROM items")[0]["n"] == 0, "400 must write nothing"


def test_create_freshness_null_explicit(client, user):
    r = post(client, user, freshness=None)
    assert r.status_code == 201
    it = items_of(r)[0]
    assert it["freshness"] is None and it["freshness_checked_at"] is None


def test_create_batch_mixed(client, user):
    ps = [{"name": "A", "freshness": "fresh"}, {"name": "B"}, {"name": "C", "freshness": "spoiled"}]
    r = client.post("/items", json={"items": ps}, headers=user["headers"])
    assert r.status_code == 201
    by = {i["name"]: i for i in items_of(r)}
    assert by["A"]["freshness"] == "fresh" and by["B"]["freshness"] is None and by["C"]["freshness"] == "spoiled"


def test_patch_set_and_change_and_clear(client, user, make_item, sql):
    it = make_item(user)
    assert it["freshness"] is None
    h = user["headers"]
    r = client.patch(f"/items/{it['id']}", json={"freshness": "semi_fresh"}, headers=h)
    assert r.status_code == 200, r.get_data(as_text=True)
    a = r.get_json()["item"]
    assert a["freshness"] == "semi_fresh" and a["freshness_checked_at"]
    r = client.patch(f"/items/{it['id']}", json={"freshness": "spoiled"}, headers=h)
    b = r.get_json()["item"]
    assert b["freshness"] == "spoiled"
    assert parse_ts(b["freshness_checked_at"]) >= parse_ts(a["freshness_checked_at"])
    assert db_row(sql, it["id"])["freshness"] == "spoiled"
    r = client.patch(f"/items/{it['id']}", json={"freshness": None}, headers=h)
    assert r.status_code == 200
    c = r.get_json()["item"]
    assert c["freshness"] is None
    assert c["freshness_checked_at"] is None, "clearing freshness clears the checked_at stamp"
    row = db_row(sql, it["id"])
    assert row["freshness"] is None and row["freshness_checked_at"] is None


def test_patch_other_fields_leaves_freshness_and_stamp(client, user, make_item):
    it = make_item(user, freshness="fresh")
    stamp = it["freshness_checked_at"]
    assert stamp
    r = client.patch(f"/items/{it['id']}", json={"name": "Renamed", "quantity": 3}, headers=user["headers"])
    out = r.get_json()["item"]
    assert out["freshness"] == "fresh" and out["freshness_checked_at"] == stamp


def test_patch_same_value_keeps_value(client, user, make_item):
    it = make_item(user, freshness="spoiled")
    out = client.patch(f"/items/{it['id']}", json={"freshness": "spoiled"}, headers=user["headers"]).get_json()["item"]
    assert out["freshness"] == "spoiled" and out["freshness_checked_at"]


@pytest.mark.parametrize("bad", [3, ["fresh"], False, {"x": 1}])
def test_patch_non_string_freshness_400(client, user, make_item, sql, bad):
    it = make_item(user, freshness="fresh")
    r = client.patch(f"/items/{it['id']}", json={"freshness": bad}, headers=user["headers"])
    assert r.status_code == 400, r.get_data(as_text=True)
    assert db_row(sql, it["id"])["freshness"] == "fresh"


def test_patch_unknown_string_becomes_fresh(client, user, make_item):
    it = make_item(user, freshness="spoiled")
    r = client.patch(f"/items/{it['id']}", json={"freshness": "bogus"}, headers=user["headers"])
    assert r.status_code == 200 and r.get_json()["item"]["freshness"] == "fresh"


def test_patch_variant(client, user, make_item):
    it = make_item(user)
    r = client.patch(f"/items/{it['id']}", json={"freshness": "Semi-Fresh"}, headers=user["headers"])
    assert r.status_code == 200 and r.get_json()["item"]["freshness"] == "semi_fresh"


def test_patch_freshness_other_users_item_403(client, user, user2, make_item):
    it = make_item(user)
    r = client.patch(f"/items/{it['id']}", json={"freshness": "spoiled"}, headers=user2["headers"])
    assert r.status_code == 403


def test_freshness_does_not_change_expiry(client, user, make_item):
    it = make_item(user, predicted_expiry=iso_in(5))
    out = client.patch(f"/items/{it['id']}", json={"freshness": "spoiled"}, headers=user["headers"]).get_json()["item"]
    assert out["predicted_expiry"] == it["predicted_expiry"] and out["expiry_source"] == it["expiry_source"]


def test_in_list_and_group_by_sections(client, user, make_item):
    make_item(user, name="Spinach", category="produce_leafy", freshness="spoiled")
    make_item(user, name="Milk", category="dairy", freshness="semi_fresh")
    make_item(user, name="Cheese", category="dairy")
    flat = items_of(client.get("/items", headers=user["headers"]))
    assert {i["name"]: i["freshness"] for i in flat} == {"Spinach": "spoiled", "Milk": "semi_fresh", "Cheese": None}
    for i in flat:
        assert "freshness_checked_at" in i and "confidence" in i
    secs = client.get("/items?group_by=food_group", headers=user["headers"]).get_json()["sections"]
    got = {i["name"]: i["freshness"] for s in secs for i in s["items"]}
    assert got == {"Spinach": "spoiled", "Milk": "semi_fresh", "Cheese": None}
    for s in secs:
        for i in s["items"]:
            assert "freshness_checked_at" in i and "confidence" in i


def test_in_remove_response(client, user, make_item):
    it = make_item(user, freshness="semi_fresh")
    out = client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=user["headers"]).get_json()["item"]
    assert out["freshness"] == "semi_fresh"


# ---- confidence ----
@pytest.mark.parametrize("c", [0, 0.0, 0.5, 1, 1.0, 0.873])
def test_confidence_stored(client, user, sql, c):
    r = post(client, user, confidence=c)
    assert r.status_code == 201, r.get_data(as_text=True)
    it = items_of(r)[0]
    assert it["confidence"] == pytest.approx(c)
    assert float(db_row(sql, it["id"])["confidence"]) == pytest.approx(c)


@pytest.mark.parametrize("bad", [-0.01, 1.01, 2, -1, "0.5", "high", True, [0.5]])
def test_confidence_out_of_range_rejected(client, user, sql, bad):
    r = post(client, user, confidence=bad)
    assert r.status_code == 400, r.get_data(as_text=True)
    assert r.get_json()["error"]["code"]
    assert sql("SELECT count(*) AS n FROM items")[0]["n"] == 0


def test_confidence_null_ok_and_in_list(client, user, make_item):
    make_item(user, name="A", confidence=0.91)
    make_item(user, name="B")
    by = {i["name"]: i["confidence"] for i in items_of(client.get("/items", headers=user["headers"]))}
    assert by["A"] == pytest.approx(0.91) and by["B"] is None


def test_confidence_not_editable_on_patch(client, user, make_item):
    """API.md: confidence is detector output, so PATCH rejects it like any unknown field."""
    it = make_item(user, confidence=0.4)
    for v in (0.9, 7):
        assert client.patch(f"/items/{it['id']}", json={"confidence": v}, headers=user["headers"]).status_code == 400
    assert client.get("/items", headers=user["headers"]).get_json()["items"][0]["confidence"] == pytest.approx(0.4)


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["confidence", "est_price", "quantity", "est_weight_kg"])
def test_non_finite_numbers_rejected_on_create(client, user, sql, field, raw):
    body = '{"items": [{"name": "x", "%s": %s}]}' % (field, raw)
    r = client.post("/items", data=body, content_type="application/json", headers=user["headers"])
    assert r.status_code == 400, r.get_data(as_text=True)
    assert "finite" in r.get_json()["error"]["message"] or "between" in r.get_json()["error"]["message"] \
        or "must be" in r.get_json()["error"]["message"]
    assert sql("SELECT count(*) AS n FROM items")[0]["n"] == 0


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["quantity", "est_price", "est_weight_kg"])
def test_non_finite_numbers_rejected_on_patch(client, user, make_item, field, raw):
    it = make_item(user)
    r = client.patch(f"/items/{it['id']}", data='{"%s": %s}' % (field, raw), content_type="application/json",
                     headers=user["headers"])
    assert r.status_code == 400, r.get_data(as_text=True)
    now = client.get("/items", headers=user["headers"]).get_json()["items"][0]
    assert now[field] == it[field]


@pytest.mark.parametrize("val", [1e8, 1e12, 1e300])
def test_huge_est_price_is_400_not_500(client, user, sql, val):
    """BE-9 (fixed in backend PR 2): est_price beyond numeric(10,2) is a 400, nothing written."""
    r = post(client, user, est_price=val)
    assert r.status_code == 400, r.status_code
    assert r.get_json()["error"]["code"] == "validation_error"
    assert sql("SELECT count(*) AS n FROM items")[0]["n"] == 0
