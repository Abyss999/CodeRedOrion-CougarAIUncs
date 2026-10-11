"""QA follow-ups: ex-member items out of recipes/tips/people-reachable; /recipes/suggest body hygiene."""
import pytest

from app.services import gemini
from conftest import iso_in
from test_qa_sweep_b1_b4 import err, impact, join, leave, mk_group


@pytest.fixture
def gem(monkeypatch):
    class G:
        calls = []

    def fake(items, n, dietary):
        G.calls.append({"items": items, "n": n, "dietary": dietary})
        return [{"title": "Stew", "minutes": 20, "servings": 2, "uses_items": [i["name"] for i in items],
                 "missing_items": [], "steps": ["Boil"]}]

    G.calls = []
    monkeypatch.setattr(gemini, "suggest_recipes", fake)
    return G


def gitem(client, u, grp, name, days):
    r = client.post("/items", json={"items": [{"name": name, "group_id": grp["id"],
                                               "predicted_expiry": iso_in(days)}]}, headers=u["headers"])
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["items"][0]


def suggest(client, u, **body):
    return client.post("/recipes/suggest", json=body, headers=u["headers"])


@pytest.fixture
def world(client, user, user2, make_item):
    """user: personal Beans + group item Tofu (user2 is another member). user is a member; call leave() to eject."""
    grp = mk_group(client, user)
    join(client, user2, grp)
    tofu = gitem(client, user, grp, "Tofu", -1)
    beans = make_item(user, name="Beans", predicted_expiry=iso_in(5))
    return grp, tofu, beans


# ---- recipes ------------------------------------------------------------------------------------
def test_member_group_item_goes_to_gemini(client, user, world, gem):
    r = suggest(client, user)
    assert r.status_code == 200
    assert sorted(i["name"] for i in gem.calls[0]["items"]) == ["Beans", "Tofu"]


def test_ex_member_item_excluded_from_payload_and_uses_items(client, user, world, gem):
    grp, _, _ = world
    leave(client, user, grp)
    r = suggest(client, user)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert [i["name"] for i in gem.calls[0]["items"]] == ["Beans"]
    for rec in r.get_json()["recipes"]:
        assert "Tofu" not in str(rec["uses_items"])


def test_ex_member_only_group_items_gives_empty_without_gemini(client, user, user2, gem):
    grp = mk_group(client, user)
    join(client, user2, grp)
    gitem(client, user, grp, "Tofu", 2)
    leave(client, user, grp)
    r = suggest(client, user)
    assert r.status_code == 200 and r.get_json() == {"recipes": []}
    assert gem.calls == []


def test_item_ids_ex_member_item_404_and_member_ok(client, user, world, gem):
    grp, tofu, beans = world
    assert suggest(client, user, item_ids=[tofu["id"]]).status_code == 200
    leave(client, user, grp)
    gem.calls.clear()
    err(suggest(client, user, item_ids=[tofu["id"]]), 404, "not_found")
    err(suggest(client, user, item_ids=[beans["id"], tofu["id"]]), 404, "not_found")
    assert gem.calls == []
    assert suggest(client, user, item_ids=[beans["id"]]).status_code == 200


def test_rejoin_restores_group_item_in_recipes(client, user, world, gem):
    grp, tofu, _ = world
    leave(client, user, grp)
    join(client, user, grp)
    assert suggest(client, user, item_ids=[tofu["id"]]).status_code == 200


def test_recipe_cache_not_served_after_leaving(client, user, world, gem):
    """Same options before/after leaving: the item set changed, so the cached result must not be replayed."""
    grp, _, _ = world
    first = suggest(client, user).get_json()
    assert "Tofu" in str(first)
    leave(client, user, grp)
    again = suggest(client, user).get_json()
    assert "Tofu" not in str(again)
    assert len(gem.calls) == 2


# ---- tips ---------------------------------------------------------------------------------------
def tips(client, u):
    r = client.get("/tips", headers=u["headers"])
    assert r.status_code == 200
    return {t["code"]: t["message"] for t in r.get_json()["tips"]}


def test_tips_ex_member_item_not_past_expiry_or_expiring(client, user, user2, make_item):
    grp = mk_group(client, user)
    join(client, user2, grp)
    gitem(client, user, grp, "Tofu", -1)
    gitem(client, user, grp, "Tempeh", 1)
    make_item(user, name="Kale", predicted_expiry=iso_in(-2))
    make_item(user, name="Yogurt", predicted_expiry=iso_in(1))
    t = tips(client, user)
    assert "Tofu" in t["past_expiry"] and "Tempeh" in t["expiring_soon"]
    leave(client, user, grp)
    t = tips(client, user)
    assert "Tofu" not in " ".join(t.values()) and "Tempeh" not in " ".join(t.values())
    assert "Kale" in t["past_expiry"] and "Yogurt" in t["expiring_soon"]


def test_tips_only_ex_member_items_gives_no_expiry_tips(client, user, user2):
    grp = mk_group(client, user)
    join(client, user2, grp)
    gitem(client, user, grp, "Tofu", -1)
    gitem(client, user, grp, "Tempeh", 1)
    leave(client, user, grp)
    t = tips(client, user)
    assert "past_expiry" not in t and "expiring_soon" not in t


# ---- people/reachable ---------------------------------------------------------------------------
def reach(client, u, item_id):
    return client.get(f"/people/reachable?item_id={item_id}", headers=u["headers"])


def test_reachable_item_id_member_ok_ex_member_404_personal_ok(client, user, world):
    grp, tofu, beans = world
    assert reach(client, user, tofu["id"]).status_code == 200
    assert reach(client, user, beans["id"]).status_code == 200
    leave(client, user, grp)
    err(reach(client, user, tofu["id"]), 404, "not_found")
    assert reach(client, user, beans["id"]).status_code == 200


def test_reachable_other_member_still_sees_group_item(client, user, user2, world):
    grp, tofu, _ = world
    leave(client, user, grp)
    assert reach(client, user2, tofu["id"]).status_code == 200


# ---- impact / tips history unchanged ------------------------------------------------------------
def test_ex_member_past_events_still_counted(client, user, user2):
    grp = mk_group(client, user)
    join(client, user2, grp)
    g1 = gitem(client, user, grp, "Tofu", 3)
    g2 = gitem(client, user, grp, "Tempeh", 3)
    assert client.post(f"/items/{g1['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "forgot"},
                       headers=user["headers"]).status_code == 200
    assert client.post(f"/items/{g2['id']}/remove", json={"outcome": "used"},
                       headers=user["headers"]).status_code == 200
    before_impact = impact(client, user)
    before_tips = tips(client, user)
    assert "Tofu" in before_tips["top_wasted_item"] and "saved_recent" in before_tips
    leave(client, user, grp)
    assert impact(client, user) == before_impact
    after = tips(client, user)
    assert after["top_wasted_item"] == before_tips["top_wasted_item"]
    assert after["saved_recent"] == before_tips["saved_recent"]


# ---- /recipes/suggest body ----------------------------------------------------------------------
def raw(client, u, data=None, **kw):
    return client.post("/recipes/suggest", data=data, headers=u["headers"], **kw)


def test_no_body_ok(client, user, make_item, gem):
    make_item(user)
    assert raw(client, user).status_code == 200
    assert raw(client, user, content_type="application/json").status_code == 200
    assert gem.calls[-1]["n"] == 3 and gem.calls[-1]["dietary"] == []


def test_empty_object_ok_and_bad_bodies_400(client, user, make_item, gem):
    make_item(user)
    assert raw(client, user, "{}", content_type="application/json").status_code == 200
    for data, ct in (("[]", "application/json"), ("null", "application/json"), ("{bad", "application/json"),
                     ("   ", "application/json"), ('{"max_results": 2}', "text/plain")):
        err(raw(client, user, data, content_type=ct), 400, "validation_error")


@pytest.mark.parametrize("body", [
    {"dietary": ["vegan\u0000"]},
    {"dietary": ["ok"], "extra": {"k": ["a\u0000b"]}},
    {"dietary": [], "x\u0000": 1},
    {"item_ids": ["\u0000"]},
])
def test_nul_anywhere_400(client, user, make_item, gem, body):
    make_item(user)
    err(suggest(client, user, **body), 400, "validation_error")
    assert gem.calls == []


def test_dietary_limits(client, user, make_item, gem):
    make_item(user)
    assert suggest(client, user, dietary=[f"d{i}" for i in range(10)]).status_code == 200
    err(suggest(client, user, dietary=[f"d{i}" for i in range(11)]), 400, "validation_error")
    assert suggest(client, user, dietary=["x" * 40]).status_code == 200
    err(suggest(client, user, dietary=["x" * 41]), 400, "validation_error")
    err(suggest(client, user, dietary=["ok", 5]), 400, "validation_error")
    assert suggest(client, user, dietary=[]).status_code == 200
