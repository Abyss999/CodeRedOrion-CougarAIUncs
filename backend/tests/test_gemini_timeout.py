"""Every Gemini entry point sets an HTTP timeout; enrichment keeps ENRICH_TIMEOUT_S and no retry."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services import gemini


@pytest.fixture
def seen(app, monkeypatch):
    """Records (timeout in ms or None) per Client construction and per generate_content call."""
    import google.genai as genai

    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "AIzaSy-FAKE")
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    rec = {"timeouts": [], "calls": 0, "reply": "[]", "fail": None}

    class Models:
        def generate_content(self, **kw):
            rec["calls"] += 1
            if rec["fail"]:
                raise rec["fail"]
            return SimpleNamespace(text=rec["reply"], usage_metadata=None)

    class Client:
        def __init__(self, api_key=None, http_options=None, **kw):
            rec["timeouts"].append(getattr(http_options, "timeout", None))
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)
    with app.app_context():
        yield rec


ENRICH_ITEMS = [{"name": "Milk", "category": "dairy", "storage": "fridge", "freshness": "fresh"}]

ENTRY_POINTS = {
    "parse_text": lambda: gemini.parse_text("milk"),
    "detect": lambda: gemini.detect_from_image(b"\xff\xd8x", "image/jpeg", "single"),
    "receipt": lambda: gemini.categorize_receipt_lines(["MLK"]),
    "recipes": lambda: gemini.suggest_recipes([{"name": "Milk"}], 3, []),
    "shelf_life": lambda: gemini.estimate_shelf_life([{"name": "Milk", "category": "dairy", "storage": "fridge"}]),
}


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_every_entry_point_passes_default_timeout(seen, name):
    ENTRY_POINTS[name]()
    assert seen["timeouts"] == [30000]


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_config_override_respected(app, seen, monkeypatch, name):
    monkeypatch.setitem(app.config, "GEMINI_TIMEOUT_S", 12.5)
    ENTRY_POINTS[name]()
    assert seen["timeouts"] == [12500]


@pytest.mark.parametrize("bad", [0, -3, "abc", None])
def test_bad_config_falls_back_to_30(app, seen, monkeypatch, bad):
    monkeypatch.setitem(app.config, "GEMINI_TIMEOUT_S", bad)
    gemini.parse_text("milk")
    assert seen["timeouts"] == [30000]


def test_enrich_keeps_its_own_timeout_and_no_retry(app, seen, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_TIMEOUT_S", 99)
    monkeypatch.setitem(app.config, "ENRICH_TIMEOUT_S", 7)
    gemini.enrich_items(ENRICH_ITEMS, [None])
    assert seen["timeouts"] == [7000]
    seen["fail"] = Exception("503 UNAVAILABLE")
    seen["calls"] = 0
    with pytest.raises(gemini.UpstreamError):
        gemini.enrich_items(ENRICH_ITEMS, [None])
    assert seen["calls"] == 1


def test_enrich_default_still_25(seen):
    gemini.enrich_items(ENRICH_ITEMS, [None])
    assert seen["timeouts"] == [25000]


def test_worst_case_with_retry_under_gunicorn_timeout(seen):
    worst = 2 * 30 + sum(gemini.RETRY_DELAYS_S)
    assert worst == 61.5 < 120


def test_app_reads_env(monkeypatch):
    from app import create_app

    monkeypatch.setenv("GEMINI_TIMEOUT_S", "20")
    assert create_app({"TESTING": True}).config["GEMINI_TIMEOUT_S"] == 20.0
    monkeypatch.setenv("GEMINI_TIMEOUT_S", "junk")
    assert create_app({"TESTING": True}).config["GEMINI_TIMEOUT_S"] == 30.0
    monkeypatch.delenv("GEMINI_TIMEOUT_S")
    assert create_app({"TESTING": True}).config["GEMINI_TIMEOUT_S"] == 30.0


# ---- /recipes/suggest cleanup ---------------------------------------------------------------------
def _good(**kw):
    return {"title": "Soup", "minutes": 20, "servings": 2, "uses_items": ["Milk"], "missing_items": ["salt"],
            "steps": ["boil"], "macros": None} | kw


def _suggest(client, user, make_item, monkeypatch, recipes):
    make_item(user, name="Milk", predicted_expiry=(date.today() + timedelta(days=2)).isoformat())
    monkeypatch.setattr(gemini, "suggest_recipes", lambda items, n, dietary: recipes)
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["recipes"]


@pytest.mark.parametrize("title", [None, "", "   ", 5, ["x"], {"a": 1}, True])
def test_bad_title_drops_recipe(client, user, make_item, monkeypatch, title):
    out = _suggest(client, user, make_item, monkeypatch, [_good(title=title), _good(title="Keeper")])
    assert [r["title"] for r in out] == ["Keeper"]


def test_missing_title_key_dropped(client, user, make_item, monkeypatch):
    bad = _good()
    del bad["title"]
    assert _suggest(client, user, make_item, monkeypatch, [bad]) == []


@pytest.mark.parametrize("minutes", [None, "20", "soon", 0, -5, 601, 1e9, float("nan"), True, [], {}])
def test_bad_minutes_drops_recipe(client, user, make_item, monkeypatch, minutes):
    out = _suggest(client, user, make_item, monkeypatch, [_good(minutes=minutes), _good(title="Keeper")])
    assert [r["title"] for r in out] == ["Keeper"]


@pytest.mark.parametrize("raw,want", [(1, 1), (600, 600), (25.0, 25), (24.6, 25), (45, 45)])
def test_minutes_coerced_to_int(client, user, make_item, monkeypatch, raw, want):
    out = _suggest(client, user, make_item, monkeypatch, [_good(minutes=raw)])
    assert out[0]["minutes"] == want and type(out[0]["minutes"]) is int


def test_steps_and_missing_filtered_to_strings(client, user, make_item, monkeypatch):
    out = _suggest(client, user, make_item, monkeypatch,
                   [_good(steps=["a", 3, None, "b", {"x": 1}], missing_items=["salt", 7, ["y"]])])
    assert out[0]["steps"] == ["a", "b"] and out[0]["missing_items"] == ["salt"]


@pytest.mark.parametrize("val", [None, "text", 5, {"a": "b"}])
def test_non_list_steps_and_missing_become_empty(client, user, make_item, monkeypatch, val):
    out = _suggest(client, user, make_item, monkeypatch, [_good(steps=val, missing_items=val)])
    assert out[0]["steps"] == [] and out[0]["missing_items"] == []


def test_absent_steps_and_missing_default_empty_and_title_stripped(client, user, make_item, monkeypatch):
    bad = _good(title="  Soup  ")
    del bad["steps"], bad["missing_items"]
    out = _suggest(client, user, make_item, monkeypatch, [bad, "junk", None])
    assert len(out) == 1 and out[0]["steps"] == [] and out[0]["missing_items"] == [] and out[0]["title"] == "Soup"


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_timeout_falls_back(app, seen, monkeypatch, bad):
    monkeypatch.setitem(app.config, "GEMINI_TIMEOUT_S", bad)
    gemini.parse_text("milk")
    assert seen["timeouts"] == [30000]


@pytest.mark.parametrize("raw", ["inf", "nan", "-1", "0"])
def test_app_env_non_finite_falls_back(monkeypatch, raw):
    from app import create_app

    monkeypatch.setenv("GEMINI_TIMEOUT_S", raw)
    assert create_app({"TESTING": True}).config["GEMINI_TIMEOUT_S"] == 30.0


def test_route_truncates_after_filtering(client, user, make_item, monkeypatch):
    recipes = [_good(title=None)] + [_good(title=f"R{i}") for i in range(5)]
    seen_n = []
    make_item(user, name="Milk", predicted_expiry=(date.today() + timedelta(days=2)).isoformat())
    monkeypatch.setattr(gemini, "suggest_recipes", lambda items, n, d: seen_n.append(n) or recipes)
    r = client.post("/recipes/suggest", json={"max_results": 3}, headers=user["headers"])
    assert seen_n == [3]  # the cache key / caller value is unchanged
    assert [x["title"] for x in r.get_json()["recipes"]] == ["R0", "R1", "R2"]


@pytest.mark.parametrize("n,asked", [(1, 3), (3, 5), (10, 12)])
def test_service_prompt_asks_for_spares_and_keeps_them(app, monkeypatch, n, asked):
    import json
    captured = {}
    monkeypatch.setattr(gemini, "_generate", lambda prompt, *a, **k: captured.setdefault("p", prompt) and
                        [{"title": str(i)} for i in range(20)])
    with app.app_context():
        out = gemini.suggest_recipes([{"name": "Milk"}], n, [])
    assert json.loads(captured["p"])["max_results"] == asked and len(out) == asked
