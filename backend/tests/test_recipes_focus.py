"""POST /recipes/suggest with `item_ids`: build recipes around the items the person wants to cook now."""
import hashlib
import json
import logging
import uuid
from types import SimpleNamespace

import pytest

from app.services import gemini, recipe_cache
from conftest import iso_in


@pytest.fixture
def gem(monkeypatch):
    """Stub gemini.suggest_recipes; records each call."""
    class G:
        calls = []
        recipes = [{"title": "Soup", "minutes": 20, "servings": 2, "uses_items": [], "missing_items": [],
                    "steps": ["Boil"]}]

    def fake(items, n, dietary):
        G.calls.append({"items": items, "n": n, "dietary": dietary})
        return [dict(r) for r in G.recipes]

    G.calls = []
    monkeypatch.setattr(gemini, "suggest_recipes", fake)
    return G


def suggest(client, u, **body):
    return client.post("/recipes/suggest", json=body, headers=u["headers"])


def ok(client, u, **body):
    r = suggest(client, u, **body)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["recipes"]


def three(make_item, user):
    return [make_item(user, name=n, predicted_expiry=iso_in(d)) for n, d in (("Spinach", 1), ("Rice", 30), ("Milk", 4))]


def test_without_item_ids_the_payload_has_no_must_use_key(client, user, make_item, gem):
    three(make_item, user)
    ok(client, user)
    assert [i["name"] for i in gem.calls[0]["items"]] == ["Spinach", "Milk", "Rice"]
    assert all("must_use" not in i for i in gem.calls[0]["items"])


def test_focus_items_are_flagged_and_the_order_stays_soonest_first(client, user, make_item, gem):
    spinach, rice, milk = three(make_item, user)
    ok(client, user, item_ids=[rice["id"], milk["id"]])
    sent = gem.calls[0]["items"]
    assert [i["name"] for i in sent] == ["Spinach", "Milk", "Rice"]
    assert [i.get("must_use") for i in sent] == [None, True, True]


def test_a_focus_item_beyond_the_20_soonest_is_still_sent(client, user, gem):
    r = client.post("/items", json={"items": [{"name": f"food{n:02d}", "predicted_expiry": iso_in(n)}
                                              for n in range(25)]}, headers=user["headers"])
    assert r.status_code == 201
    late = next(i for i in r.get_json()["items"] if i["name"] == "food24")
    gem.recipes = [dict(gem.recipes[0], uses_items=["food24", "food03", "food22"])]
    rec = ok(client, user, item_ids=[late["id"]])[0]
    sent = gem.calls[0]["items"]
    assert len(sent) == 20
    assert [i["name"] for i in sent] == [f"food{n:02d}" for n in range(19)] + ["food24"]
    assert [i["name"] for i in sent if i.get("must_use")] == ["food24"]
    assert [u["name"] for u in rec["uses_items"]] == ["food24", "food03"], "food22 was not sent, food24 was"


def test_max_results_and_dietary_still_apply(client, user, make_item, gem):
    spinach, *_ = three(make_item, user)
    ok(client, user, item_ids=[spinach["id"]], max_results=5, dietary=["vegetarian"])
    assert gem.calls[0]["n"] == 5 and gem.calls[0]["dietary"] == ["vegetarian"]


def test_null_item_ids_means_not_given(client, user, make_item, gem):
    three(make_item, user)
    ok(client, user, item_ids=None)
    assert all("must_use" not in i for i in gem.calls[0]["items"])


@pytest.mark.parametrize("bad", ["abc", {"a": 1}, 5, True, [], [None], [5], ["not-a-uuid"], [[]], [{"id": "x"}]])
def test_malformed_item_ids_are_400(client, user, make_item, gem, bad):
    three(make_item, user)
    r = suggest(client, user, item_ids=bad)
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "validation_error"
    assert gem.calls == []


def test_more_than_ten_or_duplicate_ids_are_400(client, user, make_item, gem):
    it = three(make_item, user)[0]
    assert suggest(client, user, item_ids=[str(uuid.uuid4()) for _ in range(11)]).status_code == 400
    assert suggest(client, user, item_ids=[it["id"], it["id"]]).status_code == 400
    assert gem.calls == []


def test_unknown_removed_and_other_users_items_are_404_and_nothing_is_called(client, user, user2, make_item, gem):
    mine = make_item(user, name="Milk")
    theirs = make_item(user2, name="Eggs")
    gone = make_item(user, name="Bread")
    client.post(f"/items/{gone['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    for ids in ([str(uuid.uuid4())], [theirs["id"]], [gone["id"]], [mine["id"], theirs["id"]]):
        r = suggest(client, user, item_ids=ids)
        assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found", ids
    assert gem.calls == []


def test_an_empty_fridge_with_item_ids_is_404_not_an_empty_list(client, user, gem):
    r = suggest(client, user, item_ids=[str(uuid.uuid4())])
    assert r.status_code == 404
    assert ok(client, user) == [], "without ids an empty fridge is still an empty, call-free answer"
    assert gem.calls == []


def test_uppercase_uuids_work(client, user, make_item, gem):
    it = make_item(user, name="Milk")
    ok(client, user, item_ids=[it["id"].upper()])
    assert gem.calls[0]["items"][0]["must_use"] is True


# ---- cache ----------------------------------------------------------------------------------------
def test_same_focus_is_a_hit_and_a_different_focus_is_a_miss(client, user, make_item, gem):
    spinach, rice, milk = three(make_item, user)
    first = ok(client, user, item_ids=[rice["id"], milk["id"]])
    again = ok(client, user, item_ids=[milk["id"], rice["id"]])  # order does not matter
    assert first == again and len(gem.calls) == 1
    ok(client, user, item_ids=[rice["id"]])
    ok(client, user)
    assert len(gem.calls) == 3, "another focus, and no focus, are different questions"
    ok(client, user)
    assert len(gem.calls) == 3, "the cache keeps one entry per user: the last question is still a hit"


def test_the_key_is_unchanged_without_focus_and_ignores_focus_order(app, client, user, make_item):
    spinach, rice, milk = three(make_item, user)
    from app.models import Item
    with app.app_context():
        items = Item.query.order_by(Item.predicted_expiry).all()
        rows = sorted([str(i.id), i.name, i.category, str(i.quantity), i.unit, i.predicted_expiry.isoformat()]
                      for i in items)
        legacy = hashlib.sha256(json.dumps({"items": rows, "n": 3, "dietary": ["a"]}, sort_keys=True)
                                .encode()).hexdigest()
        assert recipe_cache.make_key(items, 3, ["a"]) == legacy
        assert recipe_cache.make_key(items, 3, ["a"], []) == legacy
        a, b = uuid.UUID(rice["id"]), uuid.UUID(milk["id"])
        assert recipe_cache.make_key(items, 3, ["a"], [a, b]) == recipe_cache.make_key(items, 3, ["a"], [b, a])
        assert recipe_cache.make_key(items, 3, ["a"], [a]) not in (legacy, recipe_cache.make_key(items, 3, ["a"], [b]))


def test_a_focus_error_is_not_cached(client, user, make_item, gem):
    make_item(user, name="Milk")
    assert suggest(client, user, item_ids=[str(uuid.uuid4())]).status_code == 404
    ok(client, user)
    assert len(gem.calls) == 1


# ---- the Gemini prompt ----------------------------------------------------------------------------
@pytest.fixture
def fake_client(app, monkeypatch):
    import google.genai as genai

    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    seen = []

    class Models:
        def generate_content(self, **kw):
            seen.append(kw)
            return SimpleNamespace(text="[]", usage_metadata=None)

    monkeypatch.setattr(genai, "Client", lambda api_key=None, **k: SimpleNamespace(models=Models()))
    with app.app_context():
        yield seen


def test_the_prompt_mentions_must_use_only_when_an_item_is_flagged(fake_client):
    base = [{"name": "Milk", "category": "dairy", "quantity": 1.0, "unit": "l", "expires": iso_in(3)}]
    gemini.suggest_recipes(base, 2, [])
    plain_hint = str(fake_client[-1]["config"].system_instruction)
    gemini.suggest_recipes([dict(base[0], must_use=True)], 2, [])
    focus_hint = str(fake_client[-1]["config"].system_instruction)
    assert "must_use" not in plain_hint
    assert "must_use" in focus_hint and "at least one" in focus_hint
    assert focus_hint.startswith(plain_hint), "the focus sentence is appended; the rest is unchanged"


def test_the_focus_flag_travels_in_the_prompt_payload(fake_client):
    gemini.suggest_recipes([{"name": "Milk", "must_use": True}, {"name": "Rice"}], 2, [])
    payload = json.loads(fake_client[-1]["contents"])
    assert [i.get("must_use") for i in payload["items_soonest_expiring_first"]] == [True, None]


def test_the_cache_log_line_still_has_no_user_data(client, user, make_item, gem):
    lg = logging.getLogger("app.recipes.cache")
    lines = []

    class H(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())
    h = H()
    lg.addHandler(h)
    try:
        it = make_item(user, name="Milk")
        ok(client, user, item_ids=[it["id"]])
        ok(client, user, item_ids=[it["id"]])
    finally:
        lg.removeHandler(h)
    assert lines and all(it["id"] not in ln and "Milk" not in ln for ln in lines)
