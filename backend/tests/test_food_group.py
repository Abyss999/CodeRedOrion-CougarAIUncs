"""food_group: migration 0003 backfill, POST/PATCH validation + derivation, grouping, candidates."""
import io
import uuid
from pathlib import Path

import pytest
import requests as real_requests
from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from app.extensions import db
from app.services import gemini, ml
from conftest import iso_in, items_of

MIG = str(Path(__file__).resolve().parents[1] / "migrations")
GROUPS = ["protein", "veggies", "fruit", "dairy", "grains", "pantry", "leftovers", "frozen", "other"]


def _reset_conn():
    db.session.remove()
    db.engine.dispose()


def _err(r, status=400):
    assert r.status_code == status, r.get_data(as_text=True)
    e = r.get_json()["error"]
    assert e["code"] == "validation_error" and e["message"]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call attempted in test")
    monkeypatch.setattr(real_requests, "get", boom)
    monkeypatch.setattr(real_requests, "post", boom)


def post_item(client, u, **over):
    p = {"name": "Thing", "category": "other", "storage": "fridge", "quantity": 1, "unit": "piece", "source": "manual"}
    p.update(over)
    return client.post("/items", json={"items": [p]}, headers=u["headers"])


# ---------- migration 0003 -------------------------------------------------------------------
BACKFILL = [
    ("Chicken", "meat", "protein"), ("Salmon", "seafood", "protein"), ("Eggs", "eggs", "protein"),
    ("Bread", "bakery", "grains"), ("Rice", "pantry_dry", "pantry"), ("Milk", "dairy", "dairy"),
    ("Soup", "leftovers", "leftovers"), ("Peas", "frozen", "frozen"), ("Widget", "other", "other"),
    ("Banana", "produce_hardy", "fruit"), ("Apple", "produce_hardy", "fruit"),
    ("Strawberries", "produce_leafy", "fruit"), ("Orange", "produce_hardy", "fruit"),
    ("Spinach", "produce_leafy", "veggies"), ("Carrot", "produce_hardy", "veggies"),
    ("Broccoli", "produce_hardy", "veggies"), ("Lettuce", "produce_leafy", "veggies"),
]


def test_0003_backfill_and_downgrade(app):
    with app.app_context():
        _reset_conn()
        downgrade(directory=MIG, revision="0002")
        _reset_conn()
        cols = {r[0] for r in db.session.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='items'")).all()}
        assert "food_group" not in cols
        uid = uuid.uuid4()
        db.session.execute(text("INSERT INTO users (id,email,password_hash,display_name) VALUES (:i,:e,'x','T')"),
                           {"i": uid, "e": f"{uid.hex[:8]}@example.com"})
        ids = {}
        for name, cat, _ in BACKFILL:
            iid = uuid.uuid4()
            ids[name] = iid
            db.session.execute(text(
                "INSERT INTO items (id,owner_id,name,category,storage,quantity,unit,source,predicted_expiry,expiry_source) "
                "VALUES (:i,:o,:n,:c,'fridge',1,'piece','manual',CURRENT_DATE+3,'default')"),
                {"i": iid, "o": uid, "n": name, "c": cat})
        db.session.commit()
        _reset_conn()
        upgrade(directory=MIG)
        _reset_conn()
        got = {r[0]: r[1] for r in db.session.execute(text("SELECT name, food_group FROM items")).all()}
        for name, cat, want in BACKFILL:
            assert got[name] == want, f"{name} ({cat}) -> {got[name]!r}, want {want!r}"
        # column is nullable, CHECK enforced
        assert db.session.execute(text(
            "SELECT is_nullable FROM information_schema.columns WHERE table_name='items' AND column_name='food_group'")
        ).scalar() == "YES"
        with pytest.raises(Exception):
            db.session.execute(text("UPDATE items SET food_group='bogus'"))
        db.session.rollback()
        db.session.execute(text("UPDATE items SET food_group=NULL"))
        db.session.commit()
        # downgrade removes the column, rows survive
        _reset_conn()
        downgrade(directory=MIG, revision="0002")
        _reset_conn()
        cols = {r[0] for r in db.session.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='items'")).all()}
        assert "food_group" not in cols
        assert db.session.execute(text("SELECT count(*) FROM items")).scalar() == len(BACKFILL)
        _reset_conn()
        upgrade(directory=MIG)
        _reset_conn()


def test_single_head_after_0003(app):
    from alembic.script import ScriptDirectory
    sd = ScriptDirectory(MIG)
    assert len(sd.get_heads()) == 1


# ---------- POST / PATCH ---------------------------------------------------------------------
@pytest.mark.parametrize("g", GROUPS)
def test_post_valid_food_group_stored(client, user, g):
    r = post_item(client, user, food_group=g)
    assert r.status_code == 201
    assert items_of(r)[0]["food_group"] == g
    listed = client.get("/items", headers=user["headers"]).get_json()["items"]
    assert listed[0]["food_group"] == g


@pytest.mark.parametrize("bad", ["bogus", "", "PROTEIN", 5, ["dairy"], True])
def test_post_invalid_food_group_400_nothing_written(client, user, bad):
    r = client.post("/items", json={"items": [
        {"name": "Ok", "category": "dairy", "source": "manual"},
        {"name": "Bad", "category": "dairy", "source": "manual", "food_group": bad}]}, headers=user["headers"])
    _err(r)
    assert client.get("/items", headers=user["headers"]).get_json()["items"] == []


def test_post_null_food_group_is_derived(client, user):
    r = post_item(client, user, category="meat", food_group=None)
    assert r.status_code == 201 and items_of(r)[0]["food_group"] == "protein"


@pytest.mark.parametrize("name,cat,want", [
    ("Chicken", "meat", "protein"), ("Salmon", "seafood", "protein"), ("Eggs", "eggs", "protein"),
    ("Bread", "bakery", "grains"), ("Rice", "pantry_dry", "pantry"), ("Milk", "dairy", "dairy"),
    ("Soup", "leftovers", "leftovers"), ("Peas", "frozen", "frozen"), ("Widget", "other", "other"),
    ("Banana", "produce_hardy", "fruit"), ("Spinach", "produce_leafy", "veggies"),
    ("Carrot", "produce_hardy", "veggies"), ("Strawberries", "produce_leafy", "fruit"),
])
def test_post_omitted_food_group_derived(client, user, name, cat, want):
    r = post_item(client, user, name=name, category=cat)
    assert r.status_code == 201
    assert items_of(r)[0]["food_group"] == want


def test_post_explicit_overrides_derivation(client, user):
    assert items_of(post_item(client, user, category="dairy", food_group="pantry"))[0]["food_group"] == "pantry"


def test_post_default_category_other_derives_valid_group(client, user):
    r = client.post("/items", json={"items": [{"name": "Mystery"}]}, headers=user["headers"])
    assert r.status_code == 201 and items_of(r)[0]["food_group"] in GROUPS


def _patch(client, user, it, **body):
    return client.patch(f"/items/{it['id']}", json=body, headers=user["headers"])


def _body(r):
    b = r.get_json()
    return b.get("item", b)


def _stored_group(client, user, it):
    return next(i for i in client.get("/items", headers=user["headers"]).get_json()["items"]
                if i["id"] == it["id"])["food_group"]


def test_patch_food_group_valid_and_invalid(client, user, make_item):
    it = make_item(user)
    assert "food_group" in it
    r = _patch(client, user, it, food_group="frozen")
    assert r.status_code == 200 and _body(r)["food_group"] == "frozen"
    for bad in ["bogus", "", 3, ["dairy"], True]:
        _err(_patch(client, user, it, food_group=bad))
    assert _stored_group(client, user, it) == "frozen"  # rejected writes changed nothing


def test_patch_category_only_rederives_group(client, user, make_item):
    it = make_item(user, name="Thing", category="dairy")
    assert it["food_group"] == "dairy"
    r = _patch(client, user, it, category="meat")
    assert r.status_code == 200 and _body(r)["food_group"] == "protein"
    assert _stored_group(client, user, it) == "protein"


def test_patch_category_only_overrides_earlier_explicit_group(client, user, make_item):
    it = make_item(user, name="Thing", category="dairy", food_group="pantry")
    assert it["food_group"] == "pantry"
    assert _body(_patch(client, user, it, category="frozen"))["food_group"] == "frozen"


def test_patch_category_to_produce_uses_name(client, user, make_item):
    it = make_item(user, name="Banana", category="other")
    assert _body(_patch(client, user, it, category="produce_hardy"))["food_group"] == "fruit"
    it2 = make_item(user, name="Kale", category="other")
    assert _body(_patch(client, user, it2, category="produce_leafy"))["food_group"] == "veggies"


def test_patch_category_and_group_explicit_wins(client, user, make_item):
    it = make_item(user, name="Thing", category="dairy")
    r = _patch(client, user, it, category="meat", food_group="pantry")
    assert r.status_code == 200 and _body(r)["food_group"] == "pantry"
    assert _body(r)["category"] == "meat" and _stored_group(client, user, it) == "pantry"


def test_patch_category_and_invalid_group_400_nothing_written(client, user, make_item):
    it = make_item(user, name="Thing", category="dairy")
    _err(_patch(client, user, it, category="meat", food_group="bogus"))
    got = next(i for i in client.get("/items", headers=user["headers"]).get_json()["items"] if i["id"] == it["id"])
    assert got["category"] == "dairy" and got["food_group"] == "dairy"


def test_patch_invalid_category_400(client, user, make_item):
    it = make_item(user, category="dairy")
    _err(_patch(client, user, it, category="bogus"))
    assert _stored_group(client, user, it) == "dairy"


def test_patch_food_group_only_kept_and_category_untouched(client, user, make_item):
    it = make_item(user, name="Thing", category="dairy")
    r = _patch(client, user, it, food_group="pantry")
    assert _body(r)["food_group"] == "pantry" and _body(r)["category"] == "dairy"
    # an unrelated PATCH keeps the custom group
    r = _patch(client, user, it, quantity=3)
    assert r.status_code == 200 and _body(r)["food_group"] == "pantry"


def test_patch_same_category_without_group_rederives(client, user, make_item):
    """Documented rule: any category in the body without food_group re-derives (a manual group is reset)."""
    it = make_item(user, name="Thing", category="dairy", food_group="pantry")
    assert _body(_patch(client, user, it, category="dairy"))["food_group"] == "dairy"


def test_patch_name_only_keeps_group(client, user, make_item):
    """Builder's documented choice (name change does not re-derive); asserted as: group is unchanged."""
    it = make_item(user, name="Thing", category="other", food_group="pantry")
    r = _patch(client, user, it, name="Banana")
    assert r.status_code == 200 and _body(r)["food_group"] == "pantry"


def test_patch_food_group_null_never_500(client, user, make_item):
    it = make_item(user, name="Thing", category="dairy", food_group="pantry")
    r = _patch(client, user, it, food_group=None)
    assert r.status_code in (200, 400), r.get_data(as_text=True)
    if r.status_code == 400:
        _err(r)
        assert _stored_group(client, user, it) == "pantry"
    else:
        assert _stored_group(client, user, it) in GROUPS
    # null together with a category change must not 500 either
    assert _patch(client, user, it, category="meat", food_group=None).status_code in (200, 400)


def test_patch_food_group_other_user_403(client, user, user2, make_item):
    it = make_item(user)
    assert client.patch(f"/items/{it['id']}", json={"food_group": "fruit"}, headers=user2["headers"]).status_code == 403


def test_food_group_on_every_item_response(client, user, make_item):
    it = make_item(user)
    assert it["food_group"] in GROUPS
    assert client.get("/items", headers=user["headers"]).get_json()["items"][0]["food_group"] in GROUPS
    r = client.post(f"/items/{it['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    b = r.get_json(); b = b.get("item", b)
    assert b["food_group"] in GROUPS
    inc = client.get("/items?include_removed=true", headers=user["headers"]).get_json()["items"]
    assert inc[0]["food_group"] in GROUPS


# ---------- group_by -------------------------------------------------------------------------
def test_without_group_by_unchanged(client, user, make_item):
    make_item(user, name="B", predicted_expiry=iso_in(5))
    make_item(user, name="A", predicted_expiry=iso_in(1))
    b = client.get("/items", headers=user["headers"]).get_json()
    assert set(b) == {"items"} and [i["name"] for i in b["items"]] == ["A", "B"]


def test_group_by_unknown_400(client, user):
    for v in ["bogus", "category", "", "FOOD_GROUP"]:
        _err(client.get(f"/items?group_by={v}", headers=user["headers"]))


def test_group_by_requires_auth(client):
    assert client.get("/items?group_by=food_group").status_code == 401


def test_group_by_empty(client, user):
    r = client.get("/items?group_by=food_group", headers=user["headers"])
    assert r.status_code == 200 and r.get_json() == {"sections": []}


def test_group_by_sections_order_expiry_sort_no_empty(client, user, make_item):
    # created in scrambled order
    make_item(user, name="Rice", category="pantry_dry", storage="pantry", predicted_expiry=iso_in(100))
    make_item(user, name="Milk2", category="dairy", predicted_expiry=iso_in(9))
    make_item(user, name="Chicken", category="meat", predicted_expiry=iso_in(4))
    make_item(user, name="Milk1", category="dairy", predicted_expiry=iso_in(2))
    make_item(user, name="Yogurt", category="dairy", predicted_expiry=iso_in(9))
    make_item(user, name="Bacon", category="meat", predicted_expiry=iso_in(1))
    r = client.get("/items?group_by=food_group", headers=user["headers"])
    assert r.status_code == 200
    secs = r.get_json()["sections"]
    assert set(r.get_json()) == {"sections"}
    names = [s["food_group"] for s in secs]
    assert names == ["protein", "dairy", "pantry"]  # enum order, empty sections omitted
    assert all(s["items"] for s in secs)
    by = {s["food_group"]: [i["name"] for i in s["items"]] for s in secs}
    assert by["protein"] == ["Bacon", "Chicken"]
    assert by["dairy"][0] == "Milk1" and set(by["dairy"][1:3]) == {"Milk2", "Yogurt"}
    # all items live in exactly one section, each tagged with its section's group
    for s in secs:
        assert all(i["food_group"] == s["food_group"] for i in s["items"])


def test_group_by_nulls_last_when_db_has_null_expiry(client, user, make_item, sql):
    """predicted_expiry is NOT NULL in the schema today; skip if so, else nulls must sort last."""
    nullable = sql("SELECT is_nullable FROM information_schema.columns WHERE table_name='items' AND column_name='predicted_expiry'")[0]["is_nullable"]
    if nullable == "NO":
        pytest.skip("predicted_expiry is NOT NULL; nulls-last unreachable")
    a = make_item(user, name="Dated", category="dairy", predicted_expiry=iso_in(3))  # pragma: no cover
    b = make_item(user, name="Undated", category="dairy", predicted_expiry=iso_in(1))  # pragma: no cover
    sql("UPDATE items SET predicted_expiry=NULL WHERE id=:i", i=b["id"])  # pragma: no cover
    secs = client.get("/items?group_by=food_group", headers=user["headers"]).get_json()["sections"]  # pragma: no cover
    assert [i["name"] for i in secs[0]["items"]] == ["Dated", "Undated"]  # pragma: no cover


def test_group_by_only_own_active_personal_items(client, user, user2, make_item):
    mine = make_item(user, name="Mine", category="dairy")
    make_item(user2, name="Theirs", category="meat")
    gone = make_item(user, name="Gone", category="eggs")
    client.post(f"/items/{gone['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    # group-pantry item must not appear in personal view
    g = client.post("/groups", json={"name": "H"}, headers=user["headers"]).get_json()
    g = g.get("group", g)
    r = client.post("/items", json={"items": [{"name": "Shared", "category": "dairy", "source": "manual",
                                               "group_id": g["id"]}]}, headers=user["headers"])
    assert r.status_code == 201
    secs = client.get("/items?group_by=food_group", headers=user["headers"]).get_json()["sections"]
    flat = [i["name"] for s in secs for i in s["items"]]
    assert flat == ["Mine"] and mine["id"]
    secs2 = client.get("/items?group_by=food_group", headers=user2["headers"]).get_json()["sections"]
    assert [i["name"] for s in secs2 for i in s["items"]] == ["Theirs"]


def test_group_by_combines_with_storage_filter(client, user, make_item):
    make_item(user, name="Fridge", category="dairy", storage="fridge")
    make_item(user, name="Pantry", category="pantry_dry", storage="pantry")
    secs = client.get("/items?group_by=food_group&storage=pantry", headers=user["headers"]).get_json()["sections"]
    assert [i["name"] for s in secs for i in s["items"]] == ["Pantry"]
    _err(client.get("/items?group_by=food_group&storage=bogus", headers=user["headers"]))


# ---------- candidates carry food_group ------------------------------------------------------
def _img():
    return {"image": (io.BytesIO(b"\xff\xd8fakejpeg"), "a.jpg", "image/jpeg")}


def test_parse_text_candidates_have_food_group(client, user, monkeypatch):
    monkeypatch.setattr(gemini, "parse_text", lambda t: [
        {"name": "Apples", "category": "produce_hardy", "food_group": "fruit"},
        {"name": "Milk", "category": "dairy"},
        {"name": "Chicken", "category": "meat", "food_group": "protein"},
        {"name": "Spinach", "category": "produce_leafy"}])
    r = client.post("/items/parse-text", json={"text": "x"}, headers=user["headers"])
    assert r.status_code == 200
    c = {x["name"]: x["food_group"] for x in r.get_json()["candidates"]}
    assert c == {"Apples": "fruit", "Milk": "dairy", "Chicken": "protein", "Spinach": "veggies"}


@pytest.mark.parametrize("bad", ["bogus", "", None, 7, ["dairy"], "Dairy"])
def test_parse_text_invalid_gemini_food_group_falls_back(client, user, monkeypatch, bad):
    monkeypatch.setattr(gemini, "parse_text", lambda t: [
        {"name": "Milk", "category": "dairy", "food_group": bad},
        {"name": "Chicken", "category": "meat", "food_group": bad}])
    r = client.post("/items/parse-text", json={"text": "x"}, headers=user["headers"])
    assert r.status_code == 200
    c = {x["name"]: x["food_group"] for x in r.get_json()["candidates"]}
    assert c == {"Milk": "dairy", "Chicken": "protein"}


def test_parse_text_raw_gemini_path_with_invalid_food_group(app, client, user, monkeypatch):
    """Stub one level lower (gemini._generate) so the real parse_text + normalize run."""
    monkeypatch.setattr(gemini, "_generate", lambda contents, hint, *a, **k: [
        {"name": "Whole milk", "category": "dairy", "food_group": "not-a-group", "quantity": 2, "unit": "carton"},
        {"name": "Eggs", "category": "eggs", "quantity": 12, "unit": "piece"},
        {"name": "Spinach", "category": "produce_leafy", "food_group": "veggies"}])
    r = client.post("/items/parse-text", json={"text": "2 cartons of milk, a dozen eggs and some spinach"},
                    headers=user["headers"])
    assert r.status_code == 200
    c = {x["name"]: x["food_group"] for x in r.get_json()["candidates"]}
    assert c == {"Whole milk": "dairy", "Eggs": "protein", "Spinach": "veggies"}


def test_from_photo_ml_candidates_have_food_group(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "detect", lambda *a, **k: [
        {"name": "Banana", "category": "produce_hardy", "confidence": 0.9, "freshness": "fresh", "bbox": None},
        {"name": "Milk", "category": "dairy", "confidence": 0.8, "freshness": "fresh", "bbox": None}])
    r = client.post("/items/from-photo", data=_img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["source"] == "yolo"
    c = {x["name"]: x["food_group"] for x in r.get_json()["candidates"]}
    assert c == {"Banana": "fruit", "Milk": "dairy"}


def test_from_photo_gemini_candidates_have_food_group(client, user, monkeypatch):
    monkeypatch.setattr(gemini, "detect_from_image", lambda *a, **k: [
        {"name": "Carrot", "category": "produce_hardy", "confidence": 0.9, "freshness": "fresh", "food_group": "veggies"},
        {"name": "Cheese", "category": "dairy", "confidence": 0.9, "freshness": "fresh", "food_group": "garbage"},
        {"name": "Steak", "category": "meat", "confidence": 0.7, "freshness": "spoiled"}])
    r = client.post("/items/from-photo", data=_img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["source"] == "gemini"
    c = {x["name"]: x["food_group"] for x in r.get_json()["candidates"]}
    assert c == {"Carrot": "veggies", "Cheese": "dairy", "Steak": "protein"}


def test_from_receipt_candidates_have_food_group(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "ocr", lambda *a, **k: {"lines": [
        {"name": "Milk", "quantity": 2, "price": 3.5}, {"name": "Eggs", "price": 4}], "total": 11.0})
    r = client.post("/items/from-receipt", data=_img(), headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 200
    cs = r.get_json()["candidates"]
    assert len(cs) == 2 and all(c["food_group"] in GROUPS for c in cs)


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body
    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.HTTPError("x")
    def json(self):
        return self._b


def test_barcode_candidate_has_food_group(client, user, monkeypatch):
    monkeypatch.setattr(real_requests, "get", lambda *a, **k: _Resp(200, {"status": 1, "product": {
        "product_name": "Whole Milk", "brands": "Acme", "categories_tags": ["en:dairies", "en:milks"], "quantity": "1 l"}}))
    r = client.get("/items/barcode/5000112637922", headers=user["headers"])
    assert r.status_code == 200
    assert r.get_json()["candidate"]["food_group"] == "dairy"


def test_candidate_posted_back_round_trips(client, user, monkeypatch):
    monkeypatch.setattr(gemini, "parse_text", lambda t: [{"name": "Apples", "category": "produce_hardy"}])
    c = client.post("/items/parse-text", json={"text": "x"}, headers=user["headers"]).get_json()["candidates"][0]
    payload = {k: c[k] for k in ("name", "category", "storage", "quantity", "unit", "food_group", "predicted_expiry")}
    payload["source"] = "text"
    r = client.post("/items", json={"items": [payload]}, headers=user["headers"])
    assert r.status_code == 201 and items_of(r)[0]["food_group"] == c["food_group"] == "fruit"
