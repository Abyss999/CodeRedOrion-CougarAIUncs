"""Independent QA for fix/recipes-gemini-timeout (BE-23 unbounded Gemini timeouts, BE-24 unvalidated recipe
title/minutes). Runs through the real routes + gemini._generate with a fake `genai.Client`. Never calls Google."""
import io
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services import enrich, gemini, recipe_cache


class Fake:
    def __init__(self, outcome):
        self.outcome, self.calls, self.client_kwargs = outcome, 0, []

    def install(self, monkeypatch):
        import google.genai as genai
        me = self

        class Models:
            def generate_content(self, **kw):
                me.calls += 1
                return SimpleNamespace(text=me.outcome(me.calls), usage_metadata=None)

        class Client:
            def __init__(self, api_key=None, **kw):
                me.client_kwargs.append(kw)
                self.models = Models()

        monkeypatch.setattr(genai, "Client", Client)
        return self


@pytest.fixture
def on(app, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "AIzaSy-FAKE-QA")
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)


def raiser(exc):
    def f(n):
        raise exc
    return f


def jpeg():
    b = io.BytesIO()
    Image.new("RGB", (200, 150), (190, 40, 40)).save(b, "JPEG")
    return b.getvalue()


def _item(client, user, make_item):
    make_item(user, name="Milk", predicted_expiry=(date.today() + timedelta(days=2)).isoformat())


def _good(**kw):
    return {"title": "Soup", "minutes": 20, "servings": 4, "uses_items": ["Milk"], "missing_items": [],
            "steps": ["boil"], "macros": {"kcal": 450, "protein_g": 30, "carbs_g": 40, "fat_g": 15}} | kw


# ---- a timeout is a 502 (UpstreamError), never a 500, on every route that calls Gemini ------------------
class ReadTimeout(Exception):  # stands in for httpx.ReadTimeout / the SDK's wrapped timeout
    pass


def test_recipes_timeout_is_502(client, user, make_item, on, monkeypatch):
    _item(client, user, make_item)
    f = Fake(raiser(ReadTimeout("The read operation timed out"))).install(monkeypatch)
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 502 and r.get_json()["error"]["code"] == "upstream_unavailable"
    assert f.client_kwargs[0]["http_options"].timeout == 30000
    assert f.calls == 1, "a plain read timeout is not transient: no retry"


def test_deadline_exceeded_retries_once_then_502(client, user, make_item, on, monkeypatch):
    _item(client, user, make_item)
    f = Fake(raiser(Exception("504 DEADLINE_EXCEEDED"))).install(monkeypatch)
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 502 and f.calls == 2


def test_parse_text_timeout_is_502(client, user, on, monkeypatch):
    Fake(raiser(ReadTimeout("timed out"))).install(monkeypatch)
    r = client.post("/items/parse-text", json={"text": "milk and eggs"}, headers=user["headers"])
    assert r.status_code == 502, r.get_data(as_text=True)


def test_from_photo_detect_timeout_is_502(client, user, on, monkeypatch):
    f = Fake(raiser(ReadTimeout("timed out"))).install(monkeypatch)
    form = {"image": (io.BytesIO(jpeg()), "p.jpg", "image/jpeg"), "enrich": "expiry,nutrition"}
    r = client.post("/items/from-photo", data=form, headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 502, r.get_data(as_text=True)
    assert f.client_kwargs[0]["http_options"].timeout == 30000


def test_from_photo_enrich_timeout_is_not_an_error(app, client, user, on, monkeypatch):
    def outcome(n):
        if n == 1:
            return json.dumps([{"name": "Apple", "category": "produce_hardy", "confidence": 0.9,
                                "freshness": "fresh", "bbox": [1, 1, 100, 100]}])
        raise ReadTimeout("timed out")
    f = Fake(outcome).install(monkeypatch)
    form = {"image": (io.BytesIO(jpeg()), "p.jpg", "image/jpeg"), "enrich": "expiry,nutrition"}
    r = client.post("/items/from-photo", data=form, headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert [kw.get("http_options").timeout for kw in f.client_kwargs] == [30000, 25000]
    assert r.get_json()["enrichment"]["status"] == "failed"


def test_from_photo_worst_case_arithmetic():
    """Detect: 2 attempts x 30 s + 1.5 s = 61.5 s, but enrichment is skipped once detect took > 30 s, so
    the longest route that also enriches is 30 + 25 = 55 s; the longest route overall is 61.5 s."""
    assert enrich.SKIP_AFTER_S == 30
    assert enrich.SKIP_AFTER_S + 25 < 90 and 2 * 30 + sum(gemini.RETRY_DELAYS_S) < 90


# ---- bounded for every genai entry point (source scan, not only _generate) ---------------------------
def test_only_generate_constructs_a_client():
    import pathlib
    import re
    root = pathlib.Path(gemini.__file__).parents[1]
    hits = [str(p.relative_to(root)) for p in root.rglob("*.py")
            if re.search(r"genai\.Client\(|generate_content\(|\.models\.|google\.genai\b", p.read_text())
            and p.name != "gemini.py"]
    assert hits == [], hits
    src = pathlib.Path(gemini.__file__).read_text()
    assert src.count("genai.Client(") == 1 and src.count("generate_content(") == 1


def test_every_generate_call_site_passes_timeout():
    import pathlib
    import re
    src = pathlib.Path(gemini.__file__).read_text()
    sites = [m.start() for m in re.finditer(r"_generate\(", src) if not src[:m.start()].endswith("def ")]
    assert len(sites) == 7  # + receipt_from_image (#95)
    for i in sites:
        call = src[i:i + 400].split("), \"")[0]  # up to the end of the _unwrap(...) key argument
        assert "timeout_s=" in call, call[:100]


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_timeout_config_falls_back(app, on, monkeypatch, bad):
    """BE-25 fixed: inf used to overflow int(inf * 1000) inside _generate and 502 every Gemini call."""
    monkeypatch.setitem(app.config, "GEMINI_TIMEOUT_S", bad)
    f = Fake(lambda n: "[]").install(monkeypatch)
    with app.app_context():
        gemini.parse_text("milk")
    assert f.client_kwargs[0]["http_options"].timeout == 30000


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "Infinity"])
def test_env_non_finite_falls_back_in_create_app(monkeypatch, raw):
    from app import create_app
    monkeypatch.setenv("GEMINI_TIMEOUT_S", raw)
    cfg = create_app({"TESTING": True}).config["GEMINI_TIMEOUT_S"]
    assert cfg == 30.0


# ---- recipe filter x max_results x cache ---------------------------------------------------------------
def _real_suggest(client, user, make_item, on, monkeypatch, recipes, n=None):
    _item(client, user, make_item)
    f = Fake(lambda c: json.dumps(recipes)).install(monkeypatch)
    body = {} if n is None else {"max_results": n}
    r = client.post("/recipes/suggest", json=body, headers=user["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["recipes"], f


def test_filter_happens_before_the_cut(client, user, make_item, on, monkeypatch):
    """Fixed: the route filters the whole list, then cuts to max_results (a bad first recipe no longer
    empties max_results=1)."""
    out, _ = _real_suggest(client, user, make_item, on, monkeypatch,
                           [_good(title=None), _good(title="Keeper")], n=1)
    assert [r["title"] for r in out] == ["Keeper"]


def test_over_returning_gemini_is_cut_to_n_and_cached_cut(client, user, make_item, on, monkeypatch):
    out, f = _real_suggest(client, user, make_item, on, monkeypatch,
                           [_good(title=f"R{i}") for i in range(12)], n=3)
    assert [r["title"] for r in out] == ["R0", "R1", "R2"]
    again = client.post("/recipes/suggest", json={"max_results": 3}, headers=user["headers"]).get_json()["recipes"]
    assert again == out and f.calls == 1


@pytest.mark.parametrize("n,asked", [(1, 3), (3, 5), (9, 11), (10, 12)])
def test_gemini_is_asked_for_n_plus_2_capped_at_12(client, user, make_item, on, monkeypatch, n, asked):
    _item(client, user, make_item)
    seen = []
    import google.genai as genai

    class Models:
        def generate_content(self, **kw):
            seen.append(json.loads(kw["contents"]))
            return SimpleNamespace(text="[]", usage_metadata=None)

    class Client:
        def __init__(self, api_key=None, **kw):
            self.models = Models()
    monkeypatch.setattr(genai, "Client", Client)
    assert client.post("/recipes/suggest", json={"max_results": n}, headers=user["headers"]).status_code == 200
    assert seen[0]["max_results"] == asked


def test_cache_key_uses_n_not_the_over_request(client, user, make_item, on, monkeypatch):
    out, f = _real_suggest(client, user, make_item, on, monkeypatch, [_good(title=f"R{i}") for i in range(5)], n=2)
    client.post("/recipes/suggest", json={"max_results": 2}, headers=user["headers"])
    assert f.calls == 1
    out3 = client.post("/recipes/suggest", json={"max_results": 3}, headers=user["headers"]).get_json()["recipes"]
    assert f.calls == 2 and len(out3) == 3


def test_filter_keeps_up_to_max_results(client, user, make_item, on, monkeypatch):
    out, _ = _real_suggest(client, user, make_item, on, monkeypatch,
                           [_good(title="A"), _good(minutes=0), _good(title="C")], n=3)
    assert [r["title"] for r in out] == ["A", "C"]


def test_filtered_to_empty_is_cached_and_not_retried(client, user, make_item, on, monkeypatch):
    """Low-severity note: [] after filtering is cached for the 6 h TTL like any other result (same as an
    empty Gemini answer before the fix). A new item or request option changes the key."""
    out, f = _real_suggest(client, user, make_item, on, monkeypatch, [_good(minutes="soon")])
    assert out == [] and f.calls == 1
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.get_json()["recipes"] == [] and f.calls == 1, "served from cache"
    r = client.post("/recipes/suggest", json={"max_results": 4}, headers=user["headers"])
    assert f.calls == 2, "a different option misses the cache"
    make_item(user, name="Eggs", predicted_expiry=(date.today() + timedelta(days=3)).isoformat())
    client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert f.calls == 3, "item change invalidates"


def test_cache_stores_the_cleaned_list(client, user, make_item, on, monkeypatch):
    out, f = _real_suggest(client, user, make_item, on, monkeypatch,
                           [_good(title="  Soup ", minutes=24.6, steps=["a", 1]), _good(title="")])
    again = client.post("/recipes/suggest", json={}, headers=user["headers"]).get_json()["recipes"]
    assert f.calls == 1 and again == out
    assert out[0]["title"] == "Soup" and out[0]["minutes"] == 25 and out[0]["steps"] == ["a"]


def test_timeout_is_not_cached(client, user, make_item, on, monkeypatch):
    _item(client, user, make_item)
    state = {"fail": True}

    def outcome(n):
        if state["fail"]:
            raise ReadTimeout("timed out")
        return json.dumps([_good()])
    f = Fake(outcome).install(monkeypatch)
    assert client.post("/recipes/suggest", json={}, headers=user["headers"]).status_code == 502
    state["fail"] = False
    r = client.post("/recipes/suggest", json={}, headers=user["headers"])
    assert r.status_code == 200 and len(r.get_json()["recipes"]) == 1 and f.calls == 2


# ---- cleanup preserves existing behaviour ----------------------------------------------------------------
def test_good_recipe_keeps_servings_uses_items_macros(client, user, make_item, on, monkeypatch):
    out, _ = _real_suggest(client, user, make_item, on, monkeypatch, [_good(servings=4)])
    r = out[0]
    assert r["servings"] == 4 and r["macros_estimated"] is True
    assert r["macros"] == {"kcal": 450, "protein_g": 30, "carbs_g": 40, "fat_g": 15}
    assert [u["name"] for u in r["uses_items"]] == ["Milk"] and r["uses_items"][0]["item_id"]
    assert set(r) >= {"title", "minutes", "steps", "missing_items", "servings", "uses_items", "macros"}


def test_extra_gemini_keys_pass_through_unchanged(client, user, make_item, on, monkeypatch):
    out, _ = _real_suggest(client, user, make_item, on, monkeypatch, [_good(cuisine="thai")])
    assert out[0]["cuisine"] == "thai"


def test_minutes_boundaries_and_rounding(client, user, make_item, on, monkeypatch):
    out, _ = _real_suggest(client, user, make_item, on, monkeypatch,
                           [_good(title="a", minutes=0.4), _good(title="b", minutes=0.5),
                            _good(title="c", minutes=600.4), _good(title="d", minutes=600.5)], n=4)
    # Python's round() is half-to-even: 0.5 -> 0 (dropped), 600.5 -> 600 (kept). Harmless, but not "1-600 after rounding half up".
    assert [(r["title"], r["minutes"]) for r in out] == [("c", 600), ("d", 600)]
