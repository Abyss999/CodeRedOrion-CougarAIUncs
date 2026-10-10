"""Impact computed from food_events against a hand-computed fixture."""
import pytest

REMOVE = ("INSERT INTO food_events (time, user_id, item_id, event_type, category, quantity, est_weight_kg,"
          " est_price, outcome, waste_reason, co2e_kg) VALUES (now() - make_interval(days => :d), :u, gen_random_uuid(),"
          " 'remove', 'dairy', 1, :kg, :p, :o, :r, :c)")


def seed(sql, uid, rows):
    for d, o, r, kg, p, c in rows:
        sql(REMOVE, d=d, u=uid, o=o, r=r, kg=kg, p=p, c=c)


FIXTURE = [
    (0, "used", None, 1.0, 4.00, 2.0),
    (0, "donated", None, 0.5, 6.00, 1.5),
    (0, "thrown_out", "forgot", 0.8, 5.00, 3.0),
    (14, "used", None, 0.4, 2.50, 1.0),
    (14, "thrown_out", "expired", 0.2, 1.50, 0.5),
    (60, "used", None, 2.0, 10.00, 4.0),
]


def approx(v, x):
    return float(v) == pytest.approx(x, abs=1e-6)


def test_zero_data(client, user):
    for rng in ("week", "month", "all"):
        r = client.get(f"/impact?range={rng}", headers=user["headers"])
        assert r.status_code == 200
        b = r.get_json()
        for k in ("saved", "wasted"):
            assert b[k]["count"] == 0
            assert approx(b[k]["money"], 0) and approx(b[k]["co2e_kg"], 0) and approx(b[k]["kg"], 0)
        assert approx(b["waste_rate"], 0)
        assert b["weekly"] == []


def test_all_range(client, user, sql):
    seed(sql, user["user"]["id"], FIXTURE)
    b = client.get("/impact?range=all", headers=user["headers"]).get_json()
    assert b["saved"]["count"] == 4 and approx(b["saved"]["kg"], 3.9)
    assert approx(b["saved"]["money"], 22.5) and approx(b["saved"]["co2e_kg"], 8.5)
    assert b["wasted"]["count"] == 2 and approx(b["wasted"]["kg"], 1.0)
    assert approx(b["wasted"]["money"], 6.5) and approx(b["wasted"]["co2e_kg"], 3.5)
    assert approx(b["waste_rate"], 2 / 6)


def test_month_range(client, user, sql):
    seed(sql, user["user"]["id"], FIXTURE)
    b = client.get("/impact?range=month", headers=user["headers"]).get_json()
    assert b["saved"]["count"] == 3 and approx(b["saved"]["money"], 12.5)
    assert approx(b["saved"]["kg"], 1.9) and approx(b["saved"]["co2e_kg"], 4.5)
    assert b["wasted"]["count"] == 2 and approx(b["wasted"]["money"], 6.5) and approx(b["wasted"]["co2e_kg"], 3.5)
    assert approx(b["waste_rate"], 0.4)
    wk = b["weekly"]
    assert len(wk) == 2
    assert wk[0]["week"] < wk[1]["week"]
    assert (wk[0]["saved"], wk[0]["wasted"]) == (1, 1)
    assert (wk[1]["saved"], wk[1]["wasted"]) == (2, 1)


def test_week_range(client, user, sql):
    seed(sql, user["user"]["id"], FIXTURE)
    b = client.get("/impact?range=week", headers=user["headers"]).get_json()
    assert b["saved"]["count"] == 2 and approx(b["saved"]["money"], 10.0)
    assert approx(b["saved"]["kg"], 1.5) and approx(b["saved"]["co2e_kg"], 3.5)
    assert b["wasted"]["count"] == 1 and approx(b["wasted"]["money"], 5.0) and approx(b["wasted"]["co2e_kg"], 3.0)
    assert approx(b["waste_rate"], 1 / 3)


def test_default_range_and_bad_range(client, user):
    assert client.get("/impact", headers=user["headers"]).status_code == 200
    assert client.get("/impact?range=decade", headers=user["headers"]).status_code == 400


def test_scoped_to_user_and_ignores_add_events(client, user, user2, sql):
    seed(sql, user2["user"]["id"], FIXTURE)
    sql("INSERT INTO food_events (user_id, item_id, event_type, category, est_price) VALUES (:u, gen_random_uuid(), 'add', 'dairy', 99)",
        u=user["user"]["id"])
    b = client.get("/impact?range=all", headers=user["headers"]).get_json()
    assert "saved" in b, b
    assert b["saved"]["count"] == 0 and b["wasted"]["count"] == 0


def test_end_to_end_via_api(client, user, make_item):
    a = make_item(user, est_price=4.0)
    b = make_item(user, est_price=6.0, category="meat")
    client.post(f"/items/{a['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    client.post(f"/items/{b['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "forgot"}, headers=user["headers"])
    r = client.get("/impact?range=all", headers=user["headers"]).get_json()
    assert r["saved"]["count"] == 1 and approx(r["saved"]["money"], 4.0) and r["saved"]["co2e_kg"] > 0
    assert r["wasted"]["count"] == 1 and approx(r["wasted"]["money"], 6.0) and r["wasted"]["co2e_kg"] > 0
    assert approx(r["waste_rate"], 0.5)


def test_impact_requires_auth(client):
    assert client.get("/impact").status_code == 401
