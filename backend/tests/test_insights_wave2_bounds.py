"""BE-9 and friends: numbers that are finite in JSON but overflow a column, or overflow to
Infinity in derived values (weight estimate, co2e), must be 400, never 500 or invalid JSON."""
import json

import pytest

from conftest import items_of


def post(client, u, **fields):
    return client.post("/items", json={"items": [dict({"name": "x"}, **fields)]}, headers=u["headers"])


def strict_json(resp):
    """Parse the body with a strict parser: bare NaN / Infinity tokens are not JSON."""
    def bad(tok):
        raise ValueError(f"non-standard JSON token {tok}")
    return json.loads(resp.get_data(as_text=True), parse_constant=bad)


def n_items(sql):
    return sql("SELECT count(*) AS n FROM items")[0]["n"]


# ---- est_price: numeric(10,2) --------------------------------------------------------------
@pytest.mark.parametrize("val", [0, 0.01, 99999999.99, 12345678.9])
def test_est_price_in_range_ok(client, user, val):
    r = post(client, user, est_price=val)
    assert r.status_code == 201, r.get_data(as_text=True)
    assert items_of(r)[0]["est_price"] == pytest.approx(val)


@pytest.mark.parametrize("val", [100000000, 100000000.0, 1e8 + 0.01, 1e12, 1e300, 99999999.995])
def test_est_price_over_numeric_10_2_is_400(client, user, sql, val):
    """99999999.995 rounds to 100000000.00 in numeric(10,2) and overflows too."""
    r = post(client, user, est_price=val)
    assert r.status_code == 400, r.get_data(as_text=True)
    assert r.get_json()["error"]["code"] == "validation_error"
    assert n_items(sql) == 0


@pytest.mark.parametrize("val", [-0.01, -1, -1e300])
def test_est_price_negative_is_400(client, user, sql, val):
    r = post(client, user, est_price=val)
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "validation_error"
    assert n_items(sql) == 0


@pytest.mark.parametrize("val", [1e8, 1e300, 99999999.995])
def test_est_price_overflow_on_patch_is_400(client, user, make_item, val):
    it = make_item(user, est_price=3.5)
    r = client.patch(f"/items/{it['id']}", json={"est_price": val}, headers=user["headers"])
    assert r.status_code == 400, r.get_data(as_text=True)
    now = items_of(client.get("/items", headers=user["headers"]))[0]
    assert now["est_price"] == pytest.approx(3.5)


def test_est_price_max_on_patch_ok(client, user, make_item):
    it = make_item(user)
    r = client.patch(f"/items/{it['id']}", json={"est_price": 99999999.99}, headers=user["headers"])
    assert r.status_code == 200
    assert r.get_json()["item"]["est_price"] == pytest.approx(99999999.99)


def test_est_price_max_batch_one_bad_writes_nothing(client, user, sql):
    r = client.post("/items", json={"items": [{"name": "a", "est_price": 1.0},
                                              {"name": "b", "est_price": 1e9}]}, headers=user["headers"])
    assert r.status_code == 400
    assert n_items(sql) == 0


# ---- quantity / est_weight_kg: unbounded numeric, but derived values can hit Infinity ---------
@pytest.mark.parametrize("fields", [
    {"quantity": 1e308, "unit": "gallon"},          # weight estimate = 1e308 * 3.785 -> inf
    {"quantity": 1e308, "unit": "dozen", "category": "eggs"},
    {"est_weight_kg": 1e308, "category": "meat"},   # co2e on removal = 1e308 * 15 -> inf
    {"quantity": 1e300}, {"est_weight_kg": 1e300},
])
def test_huge_quantity_or_weight_never_500_or_bad_json(client, user, sql, fields):
    """Either rejected with 400 up front, or accepted and every later response (list, remove,
    impact) stays valid JSON with finite numbers."""
    r = post(client, user, **fields)
    assert r.status_code in (201, 400), r.get_data(as_text=True)
    if r.status_code == 400:
        assert n_items(sql) == 0
        return
    strict_json(r)
    it = items_of(r)[0]
    lst = client.get("/items", headers=user["headers"])
    assert lst.status_code == 200
    strict_json(lst)
    rm = client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    assert rm.status_code in (200, 400), rm.get_data(as_text=True)
    strict_json(rm)
    imp = client.get("/impact", headers=user["headers"])
    assert imp.status_code == 200, imp.get_data(as_text=True)
    strict_json(imp)


@pytest.mark.parametrize("val", [1e308])
def test_huge_quantity_patch_never_500(client, user, make_item, val):
    it = make_item(user, unit="gallon")
    r = client.patch(f"/items/{it['id']}", json={"quantity": val}, headers=user["headers"])
    assert r.status_code in (200, 400), r.get_data(as_text=True)
    strict_json(r)
    lst = client.get("/items", headers=user["headers"])
    assert lst.status_code == 200
    strict_json(lst)


# ---- exact caps (API.md / _util.MAX_NUMBER): quantity <= 1,000,000, est_weight_kg <= 100,000 ----
@pytest.mark.parametrize("field,ok,bad", [
    ("quantity", 1_000_000, 1_000_000.01),
    ("est_weight_kg", 100_000, 100_000.01),
])
def test_quantity_weight_caps_create(client, user, sql, field, ok, bad):
    r = post(client, user, **{field: ok})
    assert r.status_code == 201, r.get_data(as_text=True)
    assert items_of(r)[0][field] == pytest.approx(ok)
    r = post(client, user, **{field: bad})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "validation_error"
    assert n_items(sql) == 1


@pytest.mark.parametrize("field,ok,bad", [
    ("quantity", 1_000_000, 1_000_000.01),
    ("est_weight_kg", 100_000, 100_000.01),
])
def test_quantity_weight_caps_patch(client, user, make_item, field, ok, bad):
    it = make_item(user)
    r = client.patch(f"/items/{it['id']}", json={field: ok}, headers=user["headers"])
    assert r.status_code == 200
    r = client.patch(f"/items/{it['id']}", json={field: bad}, headers=user["headers"])
    assert r.status_code == 400
    assert items_of(client.get("/items", headers=user["headers"]))[0][field] == pytest.approx(ok)


def test_max_values_remove_and_impact_finite(client, user):
    """Every field at its cap: remove + /impact still produce finite, exact JSON numbers."""
    r = post(client, user, quantity=1_000_000, unit="gallon", est_price=99999999.99, category="meat")
    assert r.status_code == 201
    it = items_of(r)[0]
    rm = client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    assert rm.status_code == 200
    imp = strict_json(client.get("/impact", headers=user["headers"]))
    assert imp["saved"]["money"] == pytest.approx(99999999.99)
    assert imp["saved"]["kg"] > 0 and imp["saved"]["co2e_kg"] > 0
