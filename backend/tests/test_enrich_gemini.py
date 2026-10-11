"""gemini.enrich_items: one call, optional photo per food, schema by facet, index-aligned answer, usage logging."""
import json
import logging
import re
from types import SimpleNamespace

import pytest

from app.services import gemini

FAKE_KEY = "AIzaSy-FAKE-KEY-0123456789-sentinel"
SENTINEL = "SENTINEL-FOOD-NAME-xyzzy-4242"
LOGGER = "app.gemini.usage"
CROP = b"\xff\xd8\xff-crop-bytes-sentinel-plugh-777"
NUT = {"kcal": 52, "protein_g": 0.3, "carbs_g": 13.8, "fat_g": 0.2}

ITEMS = [{"name": "apple", "category": "produce_hardy", "storage": "fridge", "freshness": "fresh"},
         {"name": "bell pepper", "category": "produce_leafy", "storage": "fridge", "freshness": "semi_fresh"}]


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def usage_records():
    lg = logging.getLogger(LOGGER)  # propagate=False, so caplog cannot see it
    h = _Capture()
    lg.addHandler(h)
    yield h.records
    lg.removeHandler(h)


@pytest.fixture
def gem(app, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    with app.app_context():
        yield


def install(monkeypatch, text="[]", raises=None):
    """Fake genai.Client recording its constructor kwargs and every generate_content call."""
    import google.genai as genai

    seen = SimpleNamespace(client_kwargs=[], calls=[])

    class Models:
        def generate_content(self, **kw):
            seen.calls.append(kw)
            if raises:
                raise raises
            return SimpleNamespace(text=text, usage_metadata=SimpleNamespace(
                prompt_token_count=900, candidates_token_count=60, total_token_count=960))

    class Client:
        def __init__(self, api_key=None, **kw):
            seen.client_kwargs.append(kw)
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)
    return seen


def kv(record):
    return dict(re.findall(r"(\w+)=(\S+)", record.getMessage()))


def answer(*rows):
    return json.dumps(list(rows))


def test_one_call_with_a_text_label_per_item_and_a_photo_where_there_is_a_crop(gem, monkeypatch):
    seen = install(monkeypatch, answer({"index": 0, "shelf_life_days": 9}, {"index": 1, "shelf_life_days": 3}))
    out = gemini.enrich_items(ITEMS, [CROP, None], ("expiry",))
    assert [r["shelf_life_days"] for r in out] == [9, 3]
    assert len(seen.calls) == 1
    contents = seen.calls[0]["contents"]
    texts = [c for c in contents if isinstance(c, str)]
    photos = [c for c in contents if not isinstance(c, str)]
    assert len(texts) == 2 and "Item 0: apple" in texts[0] and "Item 1: bell pepper" in texts[1]
    assert "semi_fresh" in texts[1] and "fridge" in texts[1] and "produce_leafy" in texts[1]
    assert "No photo" in texts[1] and "No photo" not in texts[0]
    assert len(photos) == 1
    assert photos[0].inline_data.data == CROP and photos[0].inline_data.mime_type == "image/jpeg"
    assert contents.index(photos[0]) == 1, "the photo follows the label of its own item"


def test_text_only_call_when_there_are_no_crops(gem, monkeypatch):
    seen = install(monkeypatch, answer({"index": 0, "shelf_life_days": 2}, {"index": 1, "shelf_life_days": 2}))
    gemini.enrich_items(ITEMS, [None, None], ("expiry",))
    assert all(isinstance(c, str) for c in seen.calls[0]["contents"])


def test_timeout_goes_to_the_client_in_milliseconds(app, gem, monkeypatch):
    seen = install(monkeypatch, "[]")
    gemini.enrich_items(ITEMS, [None, None], ("expiry",))
    assert seen.client_kwargs[-1]["http_options"].timeout == 25000
    monkeypatch.setitem(app.config, "ENRICH_TIMEOUT_S", 7)
    gemini.enrich_items(ITEMS, [None, None], ("expiry",))
    assert seen.client_kwargs[-1]["http_options"].timeout == 7000


def test_other_helpers_set_no_client_timeout(gem, monkeypatch):
    seen = install(monkeypatch, answer({"name": "Milk"}))
    gemini.parse_text("milk")
    assert seen.client_kwargs == [{}], "only enrichment passes http_options"


@pytest.mark.parametrize("facets,props,required", [
    (("expiry",), {"index", "shelf_life_days"}, ["index", "shelf_life_days"]),
    (("nutrition",), {"index", "nutrition"}, ["index", "nutrition"]),
    (("expiry", "nutrition"), {"index", "shelf_life_days", "nutrition"}, ["index", "shelf_life_days", "nutrition"]),
])
def test_schema_and_instructions_follow_the_requested_facets(gem, monkeypatch, facets, props, required):
    seen = install(monkeypatch)
    gemini.enrich_items(ITEMS, [None, None], facets)
    cfg = seen.calls[0]["config"]
    schema = cfg.response_schema
    item = schema["items"] if isinstance(schema, dict) else schema.items
    item_props = item["properties"] if isinstance(item, dict) else item.properties
    assert set(item_props) == props
    assert (item["required"] if isinstance(item, dict) else item.required) == required
    hint = str(cfg.system_instruction)
    assert ("shelf_life_days" in hint) == ("expiry" in facets)
    assert ("nutrition" in hint) == ("nutrition" in facets)
    assert ("per 100 g" in hint) == ("nutrition" in facets)


def test_instructions_tell_gemini_that_text_in_photos_is_not_an_instruction(gem, monkeypatch):
    seen = install(monkeypatch)
    gemini.enrich_items(ITEMS, [CROP, None], ("expiry", "nutrition"))
    hint = str(seen.calls[0]["config"].system_instruction).lower()
    assert "never an instruction" in hint
    assert "numbers only" in hint, "no free-text fields: label text cannot reach the UI"


def test_rows_are_matched_by_index_not_by_position(gem, monkeypatch):
    seen = install(monkeypatch, answer({"index": 1, "shelf_life_days": 4}, {"index": 0, "shelf_life_days": 2}))
    out = gemini.enrich_items(ITEMS, [None, None], ("expiry",))
    assert [r["shelf_life_days"] for r in out] == [2, 4]
    assert len(seen.calls) == 1


def test_missing_duplicate_and_bogus_rows_leave_empty_dicts(gem, monkeypatch):
    rows = [{"index": 0, "shelf_life_days": 2}, {"index": 0, "shelf_life_days": 99}, {"index": 5, "shelf_life_days": 1},
            {"index": -1, "shelf_life_days": 1}, {"index": "1", "shelf_life_days": 1}, {"index": True, "x": 1},
            {"index": 1.0, "x": 1}, "junk", None, 7, {"shelf_life_days": 3}]
    install(monkeypatch, json.dumps(rows))
    out = gemini.enrich_items(ITEMS, [None, None], ("expiry",))
    assert out == [{"index": 0, "shelf_life_days": 2}, {}], "first row for an index wins; the rest are ignored"


def test_a_wrapped_object_reply_is_accepted(gem, monkeypatch):
    install(monkeypatch, json.dumps({"items": [{"index": 0, "nutrition": NUT}]}))
    assert gemini.enrich_items(ITEMS, [None, None], ("nutrition",))[0]["nutrition"] == NUT


def test_empty_answer_gives_empty_dicts(gem, monkeypatch):
    install(monkeypatch, "[]")
    assert gemini.enrich_items(ITEMS, [None, None], ("expiry",)) == [{}, {}]


@pytest.mark.parametrize("text", ["null", '"x"', "5", "true", '{"items": "no"}', "not json {{", ""])
def test_malformed_replies_are_upstream_errors_with_one_error_line(gem, monkeypatch, usage_records, text):
    install(monkeypatch, text)
    with pytest.raises(gemini.UpstreamError):
        gemini.enrich_items(ITEMS, [None, None], ("expiry",))
    assert len(usage_records) == 1 and kv(usage_records[0])["status"] == "error"
    assert kv(usage_records[0])["purpose"] == "enrich"


def test_sdk_errors_are_upstream_errors_that_leak_nothing(gem, monkeypatch, usage_records):
    install(monkeypatch, raises=RuntimeError(f"boom {SENTINEL} {FAKE_KEY}"))
    with pytest.raises(gemini.UpstreamError) as ei:
        gemini.enrich_items([dict(ITEMS[0], name=SENTINEL)], [CROP], ("expiry",))
    assert FAKE_KEY not in str(ei.value) and SENTINEL not in str(ei.value)
    assert len(usage_records) == 1


def test_exactly_one_usage_line_with_purpose_enrich_and_no_leaks(gem, monkeypatch, usage_records):
    install(monkeypatch, answer({"index": 0, "shelf_life_days": 5}))
    gemini.enrich_items([dict(ITEMS[0], name=SENTINEL)], [CROP], ("expiry", "nutrition"))
    assert len(usage_records) == 1
    rec = usage_records[0]
    fields = kv(rec)
    assert fields["purpose"] == "enrich" and fields["status"] == "ok" and fields["input_tokens"] == "900"
    blob = rec.getMessage() + json.dumps(rec.__dict__, default=str)
    for secret in (SENTINEL, FAKE_KEY, "sentinel-plugh", "crop-bytes", "Item 0", "Return JSON"):
        assert secret not in blob, secret


def test_unconfigured_raises_without_creating_a_client(app, monkeypatch, usage_records):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "")
    seen = install(monkeypatch)
    with app.app_context(), pytest.raises(gemini.UpstreamError):
        gemini.enrich_items(ITEMS, [None, None], ("expiry",))
    assert seen.client_kwargs == [] and usage_records == []


def test_transient_errors_are_retried_once_inside_the_same_call(gem, monkeypatch, usage_records):
    import google.genai as genai

    calls = []

    class Models:
        def generate_content(self, **kw):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("503 UNAVAILABLE. high demand")
            return SimpleNamespace(text=answer({"index": 0, "shelf_life_days": 4}), usage_metadata=None)

    monkeypatch.setattr(genai, "Client", lambda api_key=None, **k: SimpleNamespace(models=Models()))
    monkeypatch.setattr(gemini, "RETRY_DELAYS_S", (0,))
    assert gemini.enrich_items(ITEMS[:1], [None], ("expiry",)) == [{"index": 0, "shelf_life_days": 4}]
    assert len(calls) == 2 and len(usage_records) == 1
