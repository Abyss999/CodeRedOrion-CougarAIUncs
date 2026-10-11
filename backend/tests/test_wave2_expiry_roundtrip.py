"""A candidate posted back unchanged keeps its expiry_source (default/gemini/ml); an edited expiry -> user."""
import pytest

from conftest import items_of, iso_in


def post(client, u, **over):
    p = {"name": "Yogurt", "category": "dairy", "storage": "fridge", "quantity": 1, "unit": "piece",
         "source": "photo", "predicted_expiry": iso_in(6)}
    p.update(over)
    return client.post("/items", json={"items": [p]}, headers=u["headers"])


@pytest.mark.parametrize("src", ["default", "gemini", "ml"])
def test_unchanged_candidate_keeps_source(client, user, sql, src):
    r = post(client, user, expiry_source=src)
    assert r.status_code == 201, r.get_data(as_text=True)
    it = items_of(r)[0]
    assert it["expiry_source"] == src
    assert sql("SELECT expiry_source FROM items WHERE id=:i", i=it["id"])[0]["expiry_source"] == src


def test_no_source_with_expiry_is_user(client, user):
    assert items_of(post(client, user))[0]["expiry_source"] == "user"


def test_explicit_user(client, user):
    assert items_of(post(client, user, expiry_source="user"))[0]["expiry_source"] == "user"


@pytest.mark.parametrize("bad", ["bogus", "", 3, None, ["ml"], "ML"])
def test_invalid_source(client, user, bad):
    r = post(client, user, expiry_source=bad)
    assert r.status_code in (201, 400), r.get_data(as_text=True)
    if r.status_code == 201:  # null/absent treated as not supplied
        assert items_of(r)[0]["expiry_source"] in ("user", "default", "gemini", "ml")
        assert bad is None or bad == "ML"  # only null (or case-folded) may be tolerated
    else:
        assert r.get_json()["error"]["code"]


def test_source_without_expiry_is_predicted(client, user):
    """No predicted_expiry -> the server predicts and sets default/gemini itself (a client claim of ml is ignored)."""
    r = client.post("/items", json={"items": [{"name": "Milk", "category": "dairy", "expiry_source": "ml"}]},
                    headers=user["headers"])
    assert r.status_code in (201, 400)
    if r.status_code == 201:
        assert items_of(r)[0]["expiry_source"] in ("default", "gemini")


def test_patch_expiry_edit_sets_user(client, user, sql):
    it = items_of(post(client, user, expiry_source="ml"))[0]
    out = client.patch(f"/items/{it['id']}", json={"predicted_expiry": iso_in(9)}, headers=user["headers"]).get_json()["item"]
    assert out["expiry_source"] == "user" and out["predicted_expiry"] == iso_in(9)


def test_patch_same_expiry_keeps_source(client, user):
    it = items_of(post(client, user, expiry_source="gemini"))[0]
    out = client.patch(f"/items/{it['id']}", json={"predicted_expiry": it["predicted_expiry"]},
                       headers=user["headers"]).get_json()["item"]
    assert out["expiry_source"] == "gemini"


def test_patch_other_field_keeps_source(client, user):
    it = items_of(post(client, user, expiry_source="ml"))[0]
    out = client.patch(f"/items/{it['id']}", json={"quantity": 4}, headers=user["headers"]).get_json()["item"]
    assert out["expiry_source"] == "ml"


def test_patch_cannot_set_source_directly_to_junk(client, user):
    it = items_of(post(client, user))[0]
    r = client.patch(f"/items/{it['id']}", json={"expiry_source": "bogus"}, headers=user["headers"])
    assert r.status_code == 400


def test_candidate_roundtrip_via_normalize(app, client, user):
    """A candidate produced by the candidates service posts back with its source intact."""
    from app.services import candidates

    with app.app_context():
        cand = candidates.normalize({"name": "Milk", "category": "dairy"})
    assert cand["expiry_source"] == "default"
    payload = {k: cand[k] for k in ("name", "category", "storage", "quantity", "unit", "predicted_expiry",
                                     "expiry_source")}
    payload["source"] = "photo"
    it = items_of(client.post("/items", json={"items": [payload]}, headers=user["headers"]))[0]
    assert it["expiry_source"] == "default" and it["predicted_expiry"] == cand["predicted_expiry"]
    payload["predicted_expiry"] = iso_in(30)
    payload["expiry_source"] = "user"
    it = items_of(client.post("/items", json={"items": [payload]}, headers=user["headers"]))[0]
    assert it["expiry_source"] == "user"


def test_confidence_survives_roundtrip(client, user):
    it = items_of(post(client, user, confidence=0.77, freshness="semi_fresh", expiry_source="ml"))[0]
    assert it["confidence"] == pytest.approx(0.77) and it["freshness"] == "semi_fresh"
    assert it["expiry_source"] == "ml"
