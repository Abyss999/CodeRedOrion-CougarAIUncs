"""Freshness normaliser (fresh|semi_fresh|spoiled) on every candidate path; ML and Gemini stubbed."""
import io
import logging

import pytest

from app.services import candidates, gemini, ml

LOGGER = "app.services.candidates"


def img():
    return {"image": (io.BytesIO(b"\xff\xd8\xff\xe0jpegbytes"), "p.jpg", "image/jpeg")}


def raw(freshness="__missing__", name="Banana"):
    d = {"name": name, "category": "produce_hardy", "confidence": 0.9, "bbox": [1, 2, 3, 4]}
    if freshness != "__missing__":
        d["freshness"] = freshness
    return d


def photo(client, user):
    r = client.post("/items/from-photo", data={"mode": "single", **img()}, headers=user["headers"],
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def fallbacks(caplog):
    return [r for r in caplog.records if r.name == LOGGER and "freshness_fallback" in r.getMessage()]


# ---------- unit: normalize_freshness ----------
@pytest.mark.parametrize("value", ["fresh", "semi_fresh", "spoiled"])
def test_valid_values_pass_silently(value, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert candidates.normalize_freshness(value, "yolo") == value
    assert not fallbacks(caplog)


@pytest.mark.parametrize("value,expected", [
    ("Semi-Fresh", "semi_fresh"), ("semi fresh", "semi_fresh"), ("SEMIFRESH", "semi_fresh"),
    ("  semi_fresh  ", "semi_fresh"), ("Semi-fresh", "semi_fresh"), ("use soon", "semi_fresh"),
    ("Use-Soon", "semi_fresh"),
    ("Rotten", "spoiled"), ("stale", "spoiled"), ("SPOILT", "spoiled"), ("bad", "spoiled"),
    ("FRESH", "fresh"), (" Spoiled ", "spoiled"),
])
def test_variants_map_without_warning(value, expected, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert candidates.normalize_freshness(value, "gemini") == expected
    assert not fallbacks(caplog)


@pytest.mark.parametrize("value", ["??", "", "   ", "mouldy", "overripe", None, 3, 1.5, True, ["spoiled"], {"a": 1}])
def test_unknown_or_missing_becomes_fresh_with_one_warning(value, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert candidates.normalize_freshness(value, "gemini") == "fresh"
    recs = fallbacks(caplog)
    assert len(recs) == 1 and recs[0].levelno == logging.WARNING
    assert "source=gemini" in recs[0].getMessage()


def test_warning_truncates_raw_and_has_no_user_data(caplog):
    long = "x" * 500
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        candidates.normalize_freshness(long, "yolo")
    msg = fallbacks(caplog)[0].getMessage()
    assert len(msg) < 200 and "x" * 41 not in msg


# ---------- from-photo, ML path ----------
def test_photo_ml_semi_fresh_passes_through(app, client, user, monkeypatch, caplog):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "detect", lambda *a, **k: [raw("semi_fresh")])
    monkeypatch.setattr(gemini, "detect_from_image", lambda *a, **k: pytest.fail("gemini must not be used"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        b = photo(client, user)
    assert b["source"] == "yolo" and b["candidates"][0]["freshness"] == "semi_fresh"
    assert not fallbacks(caplog)


@pytest.mark.parametrize("sent,expected,warns", [
    ("fresh", "fresh", 0), ("spoiled", "spoiled", 0), ("Semi-Fresh", "semi_fresh", 0),
    ("garbage", "fresh", 1), (None, "fresh", 1), ("__missing__", "fresh", 1),
])
def test_photo_ml_normalised(app, client, user, monkeypatch, caplog, sent, expected, warns):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "detect", lambda *a, **k: [raw(sent)])
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        b = photo(client, user)
    assert b["candidates"][0]["freshness"] == expected
    assert len(fallbacks(caplog)) == warns
    assert all("source=yolo" in r.getMessage() for r in fallbacks(caplog))


def test_photo_ml_mixed_list_one_warning_per_bad_candidate(app, client, user, monkeypatch, caplog):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "detect", lambda *a, **k: [raw("fresh"), raw("zzz", "Apple"), raw("spoiled", "Milk"),
                                                       raw("???", "Egg")])
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        b = photo(client, user)
    assert [c["freshness"] for c in b["candidates"]] == ["fresh", "fresh", "spoiled", "fresh"]
    assert len(fallbacks(caplog)) == 2
    # no user data (item names) in the warnings
    assert not any(n in r.getMessage() for r in fallbacks(caplog) for n in ("Apple", "Egg", "Milk"))


# ---------- from-photo, Gemini fallback (stub _generate: must accept *a, **k) ----------
def _stub_generate(monkeypatch, payload):
    monkeypatch.setattr(gemini, "_generate", lambda *a, **k: payload)


def test_photo_gemini_semi_fresh_variant(client, user, monkeypatch):
    _stub_generate(monkeypatch, [raw("Semi-Fresh")])
    b = photo(client, user)
    assert b["source"] == "gemini" and b["candidates"][0]["freshness"] == "semi_fresh"


def test_photo_gemini_dict_wrapper_and_unknown(client, user, monkeypatch, caplog):
    _stub_generate(monkeypatch, {"candidates": [raw("Rotten"), raw("weird"), raw()]})
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        b = photo(client, user)
    assert [c["freshness"] for c in b["candidates"]] == ["spoiled", "fresh", "fresh"]
    recs = fallbacks(caplog)
    assert len(recs) == 2 and all("source=gemini" in r.getMessage() for r in recs)


def test_photo_ml_down_falls_to_gemini_and_still_normalises(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    def down(*a, **k):
        raise ml.MLUnavailable("x")
    monkeypatch.setattr(ml, "detect", down)
    _stub_generate(monkeypatch, [raw("Semi Fresh")])
    b = photo(client, user)
    assert b["source"] == "gemini" and b["candidates"][0]["freshness"] == "semi_fresh"


def test_gemini_detect_prompt_lists_three_values(monkeypatch):
    seen = {}
    def gen(contents, hint, *a, **k):
        seen["hint"] = hint
        return []
    monkeypatch.setattr(gemini, "_generate", gen)
    gemini.detect_from_image(b"x", "image/jpeg", "single")
    assert "fresh|semi_fresh|spoiled" in seen["hint"]


# ---------- other paths ----------
def test_parse_text_without_freshness_has_no_key_and_no_warning(client, user, monkeypatch, caplog):
    monkeypatch.setattr(gemini, "parse_text", lambda t: [{"name": "Milk", "category": "dairy"}])
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        r = client.post("/items/parse-text", json={"text": "milk"}, headers=user["headers"])
    assert r.status_code == 200 and "freshness" not in r.get_json()["candidates"][0]
    assert not fallbacks(caplog)


def test_parse_text_with_stray_freshness_is_normalised(client, user, monkeypatch):
    monkeypatch.setattr(gemini, "parse_text", lambda t: [{"name": "Milk", "category": "dairy", "freshness": "Rotten"}])
    r = client.post("/items/parse-text", json={"text": "milk"}, headers=user["headers"])
    assert r.get_json()["candidates"][0]["freshness"] == "spoiled"


def test_normalize_all_skips_non_dicts_and_nameless():
    out = candidates.normalize_all([raw("spoiled"), "junk", None, {"freshness": "fresh"}], "yolo")
    assert len(out) == 1 and out[0]["freshness"] == "spoiled"


def test_freshness_not_stored_on_item(client, user):
    r = client.post("/items", json={"items": [{"name": "Milk", "category": "dairy", "storage": "fridge",
                                               "freshness": "semi_fresh"}]}, headers=user["headers"])
    assert r.status_code == 201
    assert "freshness" not in (r.get_json()["items"][0] if isinstance(r.get_json(), dict) else r.get_json()[0])


def test_unauthenticated_photo_401(client):
    r = client.post("/items/from-photo", data=img(), content_type="multipart/form-data")
    assert r.status_code == 401
