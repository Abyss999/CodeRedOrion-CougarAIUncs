"""POST /recipes/suggest wave 2: servings, uses_items mapped to the caller's items, and the per-user
cache (active-items hash, 6 h TTL, hit/miss logged, invalidated by any item change, never shared)."""
import logging

import pytest

from app.services import gemini, recipe_cache
from conftest import iso_in

LOGGER = "app.recipes.cache"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


@pytest.fixture
def cache_log():
    lg = logging.getLogger(LOGGER)
    h = _Capture()
    lg.addHandler(h)
    yield h.lines
    lg.removeHandler(h)


@pytest.fixture
def gem(monkeypatch):
    """Stub gemini.suggest_recipes; records each call. Set `.recipes` to change the reply."""
    class G:
        calls = []
        recipes = [{"title": "Soup", "minutes": 20, "servings": 2, "uses_items": ["Milk"],
                    "missing_items": ["salt"], "steps": ["Boil"]}]
        fail = False

    def fake(items, n, dietary):
        G.calls.append({"items": items, "n": n, "dietary": dietary})
        if G.fail:
            raise gemini.UpstreamError("down")
        return [dict(r) for r in G.recipes]

    G.calls = []
    monkeypatch.setattr(gemini, "suggest_recipes", fake)
    return G


def suggest(client, u, **body):
    r = client.post("/recipes/suggest", json=body, headers=u["headers"])
    return r


def ok(client, u, **body):
    r = suggest(client, u, **body)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["recipes"]


# ---- servings -------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,want", [(1, 1), (4, 4), (20, 20), (4.0, 4), (0, None), (21, None), (-2, None),
                                      (2.5, None), ("4", None), (True, None), (None, None), ("x", None),
                                      (float("nan"), None), (float("inf"), None), (1e308, None)])
def test_servings_sanitised(client, user, make_item, gem, raw, want):
    make_item(user, name="Milk")
    gem.recipes = [{"title": "S", "minutes": 5, "servings": raw, "uses_items": [], "missing_items": [], "steps": []}]
    rec = ok(client, user)[0]
    assert rec["servings"] == want and (want is None or isinstance(rec["servings"], int))


def test_servings_missing_key_is_null(client, user, make_item, gem):
    make_item(user)
    gem.recipes = [{"title": "S", "minutes": 5, "uses_items": [], "missing_items": [], "steps": []}]
    assert ok(client, user)[0]["servings"] is None


# ---- uses_items -----------------------------------------------------------------------------------
def test_uses_items_mapped_to_caller_items(client, user, make_item, gem):
    milk = make_item(user, name="Whole Milk", predicted_expiry=iso_in(2))
    eggs = make_item(user, name="Eggs", predicted_expiry=iso_in(5))
    gem.recipes = [{"title": "Custard", "minutes": 30, "servings": 4,
                    "uses_items": ["  EGGS ", "milk", "Unicorn"], "missing_items": ["sugar"], "steps": ["Mix"]}]
    rec = ok(client, user)[0]
    assert rec["uses_items"] == [
        {"item_id": eggs["id"], "name": "Eggs", "predicted_expiry": iso_in(5)},
        {"item_id": milk["id"], "name": "Whole Milk", "predicted_expiry": iso_in(2)},
    ]
    assert rec["missing_items"] == ["sugar"]


def test_uses_items_exact_beats_containment_and_soonest_wins(client, user, make_item, gem):
    late_milk = make_item(user, name="Milk", predicted_expiry=iso_in(9))
    soon_milk = make_item(user, name="Milk", predicted_expiry=iso_in(1))
    oat = make_item(user, name="Oat milk", predicted_expiry=iso_in(0))
    gem.recipes = [{"title": "T", "minutes": 1, "uses_items": ["milk", "milk", "milk", "milk"],
                    "missing_items": [], "steps": []}]
    got = [u["item_id"] for u in ok(client, user)[0]["uses_items"]]
    # exact first (soonest exact first), then containment, each item at most once, extra name dropped
    assert got == [soon_milk["id"], late_milk["id"], oat["id"]]


def test_uses_items_each_item_once_per_recipe_but_reusable_across_recipes(client, user, make_item, gem):
    it = make_item(user, name="Rice")
    gem.recipes = [{"title": t, "minutes": 1, "uses_items": ["rice", "Rice"], "missing_items": [], "steps": []}
                   for t in ("A", "B")]
    recs = ok(client, user, max_results=2)
    for rec in recs:
        assert [u["item_id"] for u in rec["uses_items"]] == [it["id"]]


@pytest.mark.parametrize("raw", [None, "Milk", 5, {"a": 1}, [None, 3, "", "  ", {"name": "Milk"}]])
def test_uses_items_garbage_is_empty_not_500(client, user, make_item, gem, raw):
    make_item(user, name="Milk")
    gem.recipes = [{"title": "T", "minutes": 1, "uses_items": raw, "missing_items": [], "steps": []}]
    assert ok(client, user)[0]["uses_items"] == []


def test_uses_items_never_other_users_or_removed_items(client, user, user2, make_item, gem):
    make_item(user2, name="Milk")  # same name, other user
    gone = make_item(user, name="Milk")
    client.post(f"/items/{gone['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    mine = make_item(user, name="Bread")
    gem.recipes = [{"title": "T", "minutes": 1, "uses_items": ["Milk", "Bread"], "missing_items": [], "steps": []}]
    assert ok(client, user)[0]["uses_items"] == [
        {"item_id": mine["id"], "name": "Bread", "predicted_expiry": mine["predicted_expiry"]}]


def test_uses_items_only_from_the_20_sent_to_gemini(client, user, gem):
    r = client.post("/items", json={"items": [{"name": f"food{n:02d}", "predicted_expiry": iso_in(n)}
                                              for n in range(25)]}, headers=user["headers"])
    assert r.status_code == 201
    gem.recipes = [{"title": "T", "minutes": 1, "uses_items": ["food22", "food03"], "missing_items": [], "steps": []}]
    rec = ok(client, user)[0]
    assert len(gem.calls[0]["items"]) == 20
    assert [u["name"] for u in rec["uses_items"]] == ["food03"]


# ---- cache ----------------------------------------------------------------------------------------
def test_second_call_is_a_logged_hit(client, user, make_item, gem, cache_log):
    make_item(user, name="Milk")
    first = ok(client, user)
    second = ok(client, user)
    assert first == second and len(gem.calls) == 1
    assert any("status=miss" in ln and "reason=empty" in ln for ln in cache_log)
    assert any(ln.startswith("recipes_cache status=hit age_s=") for ln in cache_log)
    for ln in cache_log:  # no user data
        assert user["user"]["id"] not in ln and "Milk" not in ln and user["email"] not in ln


def test_cache_key_includes_options(client, user, make_item, gem):
    make_item(user)
    ok(client, user)
    ok(client, user, max_results=2)
    ok(client, user, max_results=2, dietary=["vegan"])
    assert len(gem.calls) == 3
    ok(client, user, max_results=2, dietary=["vegan"])
    assert len(gem.calls) == 3


def test_cache_dietary_order_insensitive(client, user, make_item, gem):
    make_item(user)
    ok(client, user, dietary=["vegan", "nut-free"])
    ok(client, user, dietary=["nut-free", "vegan"])
    assert len(gem.calls) == 1


@pytest.mark.parametrize("change", ["add", "remove", "remove_batch", "patch_name", "patch_qty",
                                    "patch_expiry", "patch_category", "patch_unit"])
def test_item_changes_invalidate(client, user, make_item, gem, cache_log, change):
    a = make_item(user, name="Milk")
    b = make_item(user, name="Bread")
    ok(client, user)
    h = user["headers"]
    if change == "add":
        make_item(user, name="Jam")
    elif change == "remove":
        client.post(f"/items/{a['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "forgot"}, headers=h)
    elif change == "remove_batch":
        assert client.post("/items/remove-batch", json={"item_ids": [b["id"]], "outcome": "used"},
                           headers=h).status_code == 200
    else:
        field, val = {"patch_name": ("name", "Oat milk"), "patch_qty": ("quantity", 7),
                      "patch_expiry": ("predicted_expiry", iso_in(40)), "patch_category": ("category", "frozen"),
                      "patch_unit": ("unit", "kg")}[change]
        assert client.patch(f"/items/{a['id']}", json={field: val}, headers=h).status_code == 200
    cache_log.clear()
    ok(client, user)
    assert len(gem.calls) == 2, change
    assert any("status=miss" in ln and "reason=items_changed" in ln for ln in cache_log)


def test_restore_after_remove_returns_to_the_same_item_set(client, user, make_item, gem):
    a = make_item(user, name="Milk")
    make_item(user, name="Bread")
    ok(client, user)
    client.post(f"/items/{a['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    ok(client, user)
    assert len(gem.calls) == 2
    assert [i["name"] for i in gem.calls[1]["items"]] == ["Bread"]
    client.post(f"/items/{a['id']}/restore", headers=user["headers"])
    recs = ok(client, user)
    assert len(gem.calls) == 3  # one entry per user: the earlier key was overwritten
    assert {u["name"] for u in recs[0]["uses_items"]} <= {"Milk", "Bread"}


def test_removed_item_never_served_from_cache(client, user, make_item, gem):
    a = make_item(user, name="Milk")
    make_item(user, name="Bread")
    assert ok(client, user)[0]["uses_items"][0]["item_id"] == a["id"]
    client.post(f"/items/{a['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    for rec in ok(client, user):
        assert a["id"] not in {u["item_id"] for u in rec["uses_items"]}


def test_ttl_expiry(app, client, user, make_item, gem, cache_log):
    make_item(user)
    ok(client, user)
    ok(client, user)
    assert len(gem.calls) == 1
    with app.app_context():
        store = app.extensions["recipe_cache"]
        entry = next(iter(store.values()))
        entry["stored_at"] -= 6 * 3600 - 5  # still inside 6 h
    ok(client, user)
    assert len(gem.calls) == 1
    with app.app_context():
        next(iter(app.extensions["recipe_cache"].values()))["stored_at"] -= 10  # now past 6 h
    cache_log.clear()
    ok(client, user)
    assert len(gem.calls) == 2
    assert any("reason=expired" in ln for ln in cache_log)


def test_ttl_zero_disables(app, client, user, make_item, gem, monkeypatch):
    monkeypatch.setitem(app.config, "RECIPE_CACHE_TTL_SECONDS", 0)
    make_item(user)
    ok(client, user)
    ok(client, user)
    assert len(gem.calls) == 2


def test_default_ttl_is_6h(app):
    with app.app_context():
        assert app.config.get("RECIPE_CACHE_TTL_SECONDS", recipe_cache.DEFAULT_TTL_SECONDS) == 6 * 3600


def test_users_never_see_each_others_cache(client, user, user2, make_item, gem):
    make_item(user, name="Milk")
    make_item(user2, name="Milk")
    gem.recipes = [{"title": "Alice's", "minutes": 1, "uses_items": ["Milk"], "missing_items": [], "steps": []}]
    a = ok(client, user)
    gem.recipes = [{"title": "Bob's", "minutes": 1, "uses_items": ["Milk"], "missing_items": [], "steps": []}]
    b = ok(client, user2)
    assert len(gem.calls) == 2
    assert a[0]["title"] == "Alice's" and b[0]["title"] == "Bob's"
    assert a[0]["uses_items"][0]["item_id"] != b[0]["uses_items"][0]["item_id"]
    assert ok(client, user)[0]["title"] == "Alice's" and ok(client, user2)[0]["title"] == "Bob's"
    assert len(gem.calls) == 2


def test_group_member_items_do_not_leak_into_cache_or_prompt(client, user, user2, gem):
    g = client.post("/groups", json={"name": "G"}, headers=user["headers"]).get_json()["group"]
    client.post("/groups/join", json={"invite_code": g["invite_code"]}, headers=user2["headers"])
    client.post("/items", json={"items": [{"name": "Mine"}]}, headers=user2["headers"])
    client.post("/items", json={"group_id": g["id"], "items": [{"name": "Alice group rice"}]},
                headers=user["headers"])
    ok(client, user2)
    assert [i["name"] for i in gem.calls[0]["items"]] == ["Mine"]


def test_502_not_cached(client, user, make_item, gem):
    make_item(user)
    gem.fail = True
    assert suggest(client, user).status_code == 502
    assert suggest(client, user).status_code == 502
    assert len(gem.calls) == 2
    gem.fail = False
    ok(client, user)
    ok(client, user)
    assert len(gem.calls) == 3


def test_no_items_not_cached_and_no_gemini(client, user, make_item, gem):
    assert ok(client, user) == []
    assert gem.calls == []
    make_item(user)
    assert ok(client, user) != []
    assert len(gem.calls) == 1


def test_empty_gemini_result_is_cached(client, user, make_item, gem):
    make_item(user)
    gem.recipes = []
    assert ok(client, user) == [] and ok(client, user) == []
    assert len(gem.calls) == 1


def test_cached_response_identical_and_not_mutated(client, user, make_item, gem):
    make_item(user, name="Milk")
    gem.recipes = [{"title": "S", "minutes": 5, "servings": 3, "uses_items": ["Milk"], "missing_items": [],
                    "steps": ["a"], "macros": {"kcal": 300, "protein_g": 10, "carbs_g": 20, "fat_g": 5}}]
    a = suggest(client, user).get_data()
    b = suggest(client, user).get_data()
    assert a == b
