"""QA for the share pickup spot (listing fields pickup_note/lat/lng/place; API `pickup` object).

Rulings: `pickup` is populated ONLY for the owner and the claimer; everyone else gets `pickup: null`
plus `pickup_set: bool`. Optional on POST /share; PATCH /share/:id {pickup | null} owner only
(403 viewer, 404 invisible), only while `open` (409 listing_closed). Pickup never changes events or Impact.

The request/response shape of the `pickup` object lives in `pk()` / `PICKUP` below (one place to adapt).
"""
import math
import re
import uuid

import pytest
from sqlalchemy import event as sa_event

from app.extensions import db
from conftest import _signup, items_of

TAG = uuid.uuid4().hex[:10]
NOTE = f"CANARYNOTE{TAG} left of the gate"
PLACE = f"CANARYPLACE{TAG} Cafe"
LAT, LNG = 33.7491234, -84.3881234
CANARIES = (f"CANARYNOTE{TAG}", f"CANARYPLACE{TAG}", "33.74912", "84.38812")

PICKUP = {"note": NOTE, "lat": LAT, "lng": LNG, "place_name": PLACE}


def has_canary(text: str) -> bool:
    return any(c in text for c in CANARIES)


def pk(obj):
    """The pickup object of a listing-ish dict (or None)."""
    return obj.get("pickup")


# ---------- world ----------
class W:
    pass


@pytest.fixture
def w(client, make_item):
    """A owner; B,C friends of A; D friend of B only (friend of a friend); E stranger; F pending requester;
    M group mate (group G with A); X ex-member of G; Y friend of nobody but member of G."""
    x = W()
    x.c = client
    for n in "ABCDEFMXY":
        setattr(x, n, _signup(client, name=f"User{n}"))

    def befriend(p, q):
        assert client.post("/friends", json={"email": q["email"]}, headers=p["headers"]).status_code == 201
        assert client.post(f"/friends/{p['user']['id']}/accept", headers=q["headers"]).status_code == 200

    befriend(x.A, x.B)
    befriend(x.A, x.C)
    befriend(x.B, x.D)
    assert client.post("/friends", json={"email": x.A["email"]}, headers=x.F["headers"]).status_code == 201
    g = client.post("/groups", json={"name": "Flat"}, headers=x.A["headers"]).get_json()
    x.g = g.get("group", g)
    for m in (x.M, x.X, x.Y):
        assert client.post("/groups/join", json={"invite_code": x.g["invite_code"]}, headers=m["headers"]).status_code == 200
    assert client.post(f"/groups/{x.g['id']}/leave", headers=x.X["headers"]).status_code in (200, 204)
    x.item = make_item(x.A, name="Soup")
    return x


def post_share(c, u, item, **extra):
    return c.post("/share", json={"item_id": item["id"], **extra}, headers=u["headers"])


def mk(c, u, item, pickup=PICKUP, **extra):
    r = post_share(c, u, item, pickup=pickup, **extra) if pickup is not None else post_share(c, u, item, **extra)
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["listing"]


def patch(c, u, lid, body):
    return c.patch(f"/share/{lid}", json=body, headers=u["headers"])


def claim(c, u, lid):
    return c.post(f"/share/{lid}/claim", headers=u["headers"])


def pantry(c, u):
    return c.get("/share", headers=u["headers"]).get_json()["listings"]


def impact(c, u, rng="all"):
    r = c.get(f"/impact?range={rng}", headers=u["headers"])
    assert r.status_code == 200
    return r.get_json()


def impact_all(c, u):
    return {r: impact(c, u, r) for r in ("week", "month", "all")}


def ev_count(sql, kind=None):
    if kind:
        return sql("SELECT count(*) AS n FROM food_events WHERE event_type=:k", k=kind)[0]["n"]
    return sql("SELECT count(*) AS n FROM food_events")[0]["n"]


def owner_item(c, u, item_id):
    its = items_of(c.get("/items?include_removed=true", headers=u["headers"]))
    return next(i for i in its if i["id"] == item_id)


def crawl(c, u, w, lid=None):
    """GET every read endpoint that could embed a listing or its item; returns {path: text}."""
    paths = ["/share", "/items?include_removed=true", "/items", "/groups", f"/groups/{w.g['id']}",
             f"/groups/{w.g['id']}/pantry", "/requests", "/requests?mine=1", "/friends", "/impact?range=all",
             "/auth/me", f"/people/reachable?item_id={w.item['id']}", "/people/reachable", "/tips"]
    out = {}
    for p in paths:
        r = c.get(p, headers=u["headers"])
        out[p] = r.get_data(as_text=True)
    return out


# ---------- POST /share validation ----------
def test_create_with_pickup_roundtrips_for_owner(w):
    l = mk(w.c, w.A, w.item)
    p = pk(l)
    assert p["note"] == NOTE and p["place_name"] == PLACE
    assert p["lat"] == pytest.approx(LAT, abs=1e-5) and p["lng"] == pytest.approx(LNG, abs=1e-5)
    assert l.get("pickup_set") is True


def test_create_without_pickup_is_null_and_not_set(w):
    l = mk(w.c, w.A, w.item, pickup=None)
    assert pk(l) is None and l.get("pickup_set") is False


def test_note_only_and_coords_only_are_valid(w, make_item):
    l = mk(w.c, w.A, w.item, pickup={"note": "  side door  "})
    assert pk(l)["note"] == "side door"  # trimmed
    assert pk(l).get("lat") is None and pk(l).get("lng") is None
    l2 = mk(w.c, w.A, make_item(w.A, name="B"), pickup={"lat": 10, "lng": 20})
    assert pk(l2)["lat"] == 10 and pk(l2)["lng"] == 20 and pk(l2).get("note") in (None, "")


@pytest.mark.parametrize("bad", [
    {}, {"note": ""}, {"note": "   "}, {"place_name": "Cafe"}, {"place_name": "Cafe", "note": "  "},
    {"lat": 10}, {"lng": 10}, {"note": "ok", "lat": 10}, {"note": "ok", "lng": 10},
    {"lat": 10, "lng": None}, {"lat": None, "lng": 10},
    {"lat": 90.0001, "lng": 0}, {"lat": -90.0001, "lng": 0}, {"lat": 0, "lng": 180.0001},
    {"lat": 0, "lng": -180.0001}, {"lat": 1e308, "lng": 0}, {"lat": "10", "lng": "20"},
    {"lat": True, "lng": False}, {"lat": [1], "lng": 2}, {"lat": {}, "lng": 2},
    {"note": "x" * 121}, {"note": "ok", "place_name": "p" * 121}, {"note": 5}, {"note": ["a"]}, {"note": {"a": 1}},
    {"note": "ok", "place_name": 7}, {"note": "\n\t "},
])
def test_invalid_pickup_is_400_and_nothing_written(w, sql, bad):
    n_ev, n_l = ev_count(sql), sql("SELECT count(*) AS n FROM share_listings")[0]["n"]
    r = post_share(w.c, w.A, w.item, pickup=bad)
    assert r.status_code == 400, (bad, r.get_data(as_text=True))
    assert r.get_json()["error"]["code"] == "validation_error"
    assert ev_count(sql) == n_ev
    assert sql("SELECT count(*) AS n FROM share_listings")[0]["n"] == n_l


@pytest.mark.parametrize("raw", ['{"item_id": "%s", "pickup": {"lat": NaN, "lng": 1}}',
                                 '{"item_id": "%s", "pickup": {"lat": 1, "lng": Infinity}}',
                                 '{"item_id": "%s", "pickup": {"lat": -Infinity, "lng": 1}}'])
def test_nan_inf_coordinates_are_400(w, raw):
    r = w.c.post("/share", data=raw % w.item["id"], content_type="application/json", headers=w.A["headers"])
    assert r.status_code == 400


@pytest.mark.parametrize("bad", ["a note", ["x"], 5, True])
def test_pickup_must_be_object_or_absent(w, bad):
    assert post_share(w.c, w.A, w.item, pickup=bad).status_code == 400


def test_pickup_null_on_create_is_no_pickup_not_500(w):
    r = post_share(w.c, w.A, w.item, pickup=None)
    assert r.status_code in (201, 400)
    if r.status_code == 201:
        assert pk(r.get_json()["listing"]) is None


@pytest.mark.parametrize("lat,lng", [(90, 180), (-90, -180), (0, 0), (0.0, -0.0)])
def test_range_boundaries_inclusive(w, lat, lng):
    assert pk(mk(w.c, w.A, w.item, pickup={"lat": lat, "lng": lng}))["lat"] == lat


def test_length_boundaries_exact(w):
    l = mk(w.c, w.A, w.item, pickup={"note": "n" * 120, "place_name": "p" * 120})
    assert len(pk(l)["note"]) == 120 and len(pk(l)["place_name"]) == 120


def test_length_counts_after_trim_and_unicode_codepoints(w, make_item):
    assert pk(mk(w.c, w.A, w.item, pickup={"note": "  " + "n" * 120 + "  "}))["note"] == "n" * 120
    it = make_item(w.A, name="E")
    assert pk(mk(w.c, w.A, it, pickup={"note": "é" * 120}))["note"] == "é" * 120
    it2 = make_item(w.A, name="F")
    assert post_share(w.c, w.A, it2, pickup={"note": "é" * 121}).status_code == 400


def test_html_and_sql_text_stored_verbatim_not_executed(w):
    evil = "<script>alert(1)</script>'; DROP TABLE items;--"
    l = mk(w.c, w.A, w.item, pickup={"note": evil})
    assert pk(l)["note"] == evil
    assert w.c.get("/items", headers=w.A["headers"]).status_code == 200


def test_group_listing_accepts_pickup(w):
    l = mk(w.c, w.A, w.item, group_id=w.g["id"])
    assert pk(l)["note"] == NOTE


# ---------- PATCH /share/:id ----------
def test_patch_set_replace_and_clear_by_owner(w):
    l = mk(w.c, w.A, w.item, pickup=None)
    r = patch(w.c, w.A, l["id"], {"pickup": {"note": "porch"}})
    assert r.status_code == 200
    got = r.get_json()["listing"]
    assert pk(got)["note"] == "porch" and got["pickup_set"] is True
    r = patch(w.c, w.A, l["id"], {"pickup": {"lat": 1, "lng": 2, "place_name": "Park"}})
    got = r.get_json()["listing"]
    assert pk(got)["lat"] == 1 and pk(got)["place_name"] == "Park"
    assert pk(got).get("note") in (None, ""), "PATCH replaces the whole pickup, it must not merge stale fields"
    r = patch(w.c, w.A, l["id"], {"pickup": None})
    assert r.status_code == 200
    got = r.get_json()["listing"]
    assert pk(got) is None and got["pickup_set"] is False


def test_patch_clear_wipes_every_column(w, sql):
    l = mk(w.c, w.A, w.item)
    patch(w.c, w.A, l["id"], {"pickup": None})
    row = sql("SELECT pickup_note, pickup_lat, pickup_lng, pickup_place FROM share_listings")[0]
    assert all(v is None for v in row.values()), row


@pytest.mark.parametrize("body", [{}, {"other": 1}, {"pickup": {}}, {"pickup": {"lat": 5}}, {"pickup": "x"},
                                  {"pickup": {"note": "x" * 121}}, {"pickup": {"lat": 91, "lng": 0}}, []])
def test_patch_invalid_is_400_and_leaves_pickup(w, body):
    l = mk(w.c, w.A, w.item)
    r = patch(w.c, w.A, l["id"], body)
    assert r.status_code == 400, (body, r.get_data(as_text=True))
    assert pk(owner_item(w.c, w.A, w.item["id"])["share"])["note"] == NOTE


def test_patch_viewer_403_stranger_404_unknown_404(w):
    l = mk(w.c, w.A, w.item)
    for viewer in (w.B, w.C):
        r = patch(w.c, viewer, l["id"], {"pickup": {"note": "hijack"}})
        assert r.status_code == 403 and not has_canary(r.get_data(as_text=True))
    for hidden in (w.D, w.E, w.F, w.X, w.M, w.Y):  # fof, stranger, pending, ex-member, group mates of a friends listing
        r = patch(w.c, hidden, l["id"], {"pickup": {"note": "hijack"}})
        assert r.status_code == 404, (hidden["user"]["display_name"], r.status_code)
        assert not has_canary(r.get_data(as_text=True))
    assert patch(w.c, w.A, str(uuid.uuid4()), {"pickup": None}).status_code == 404
    assert patch(w.c, w.A, "not-a-uuid", {"pickup": None}).status_code == 404
    assert pk(owner_item(w.c, w.A, w.item["id"])["share"])["note"] == NOTE  # untouched by every attempt


def test_patch_claimer_cannot_edit(w):
    l = mk(w.c, w.A, w.item)
    assert claim(w.c, w.B, l["id"]).status_code == 200
    r = patch(w.c, w.B, l["id"], {"pickup": None})
    assert r.status_code == 403
    assert pk(owner_item(w.c, w.A, w.item["id"])["share"]) is not None


def test_patch_requires_auth(w):
    l = mk(w.c, w.A, w.item)
    assert w.c.patch(f"/share/{l['id']}", json={"pickup": None}).status_code == 401


def test_patch_only_while_open(w, sql):
    # cancelled
    l = mk(w.c, w.A, w.item)
    assert w.c.delete(f"/share/{l['id']}", headers=w.A["headers"]).status_code == 200
    r = patch(w.c, w.A, l["id"], {"pickup": None})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "listing_closed"
    # fulfilled
    it = w.c.post("/items", json={"items": [{"name": "Rice"}]}, headers=w.A["headers"]).get_json()["items"][0]
    l2 = mk(w.c, w.A, it)
    claim(w.c, w.B, l2["id"])
    assert w.c.post(f"/items/{it['id']}/remove", json={"outcome": "donated"}, headers=w.A["headers"]).status_code == 200
    r = patch(w.c, w.A, l2["id"], {"pickup": {"note": "late"}})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "listing_closed"
    assert sql("SELECT pickup_note FROM share_listings WHERE id=:i", i=l2["id"])[0]["pickup_note"] == NOTE


def test_patch_when_item_removed_but_listing_open_is_not_500(w):
    """Removed as `used`/`thrown_out`: the listing stays `open` in the current model. Must not 500."""
    l = mk(w.c, w.A, w.item)
    assert w.c.post(f"/items/{w.item['id']}/remove", json={"outcome": "used"}, headers=w.A["headers"]).status_code == 200
    assert patch(w.c, w.A, l["id"], {"pickup": {"note": "x"}}).status_code in (200, 409)


def test_patch_precedence_viewer_closed_listing_is_403_not_409(w):
    l = mk(w.c, w.A, w.item)
    w.c.delete(f"/share/{l['id']}", headers=w.A["headers"])
    assert patch(w.c, w.B, l["id"], {"pickup": None}).status_code in (403, 404)  # never leaks via 409 body


def test_patch_on_claimed_open_listing_updates_what_claimer_sees(w):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    patch(w.c, w.A, l["id"], {"pickup": {"note": "moved to the lobby"}})
    mine = next(x for x in pantry(w.c, w.B) if x["id"] == l["id"])
    assert pk(mine)["note"] == "moved to the lobby"
    patch(w.c, w.A, l["id"], {"pickup": None})
    mine = next(x for x in pantry(w.c, w.B) if x["id"] == l["id"])
    assert pk(mine) is None and mine["pickup_set"] is False


# ---------- visibility ----------
def test_friend_viewer_sees_redacted_pickup_in_pantry(w):
    l = mk(w.c, w.A, w.item)
    for viewer in (w.B, w.C):
        e = next(x for x in pantry(w.c, viewer) if x["id"] == l["id"])
        assert "pickup" in e and e["pickup"] is None and e["pickup_set"] is True
        assert not has_canary(str(e))


def test_pickup_set_false_for_viewer_when_none(w):
    l = mk(w.c, w.A, w.item, pickup=None)
    e = next(x for x in pantry(w.c, w.B) if x["id"] == l["id"])
    assert e["pickup"] is None and e["pickup_set"] is False


def test_claimer_sees_full_pickup_in_claim_response_and_pantry(w):
    l = mk(w.c, w.A, w.item)
    r = claim(w.c, w.B, l["id"])
    assert r.status_code == 200
    got = r.get_json()["listing"]
    assert pk(got)["note"] == NOTE and pk(got)["place_name"] == PLACE and got["pickup_set"] is True
    mine = next(x for x in pantry(w.c, w.B) if x["id"] == l["id"])
    assert pk(mine)["note"] == NOTE and mine["claimed_by_me"] is True
    # the other friend no longer sees the listing at all
    assert all(x["id"] != l["id"] for x in pantry(w.c, w.C))


def test_failed_claim_responses_never_leak(w):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    r = claim(w.c, w.C, l["id"])  # already claimed: C is a visible friend
    assert r.status_code == 409 and not has_canary(r.get_data(as_text=True))
    r = claim(w.c, w.A, l["id"])  # owner own listing
    assert r.status_code == 400 and not has_canary(r.get_data(as_text=True))
    for u in (w.D, w.E, w.F, w.X):
        r = claim(w.c, u, l["id"])
        assert r.status_code == 404 and not has_canary(r.get_data(as_text=True))


def test_owner_sees_pickup_everywhere_owner_view(w):
    l = mk(w.c, w.A, w.item)
    s = owner_item(w.c, w.A, w.item["id"])["share"]
    assert pk(s)["note"] == NOTE and s["id"] == l["id"]
    created = w.c.post("/items", json={"items": [{"name": "Z"}]}, headers=w.A["headers"])
    assert items_of(created)[0]["share"] is None
    got = w.c.patch(f"/items/{w.item['id']}", json={"name": "Soup2"}, headers=w.A["headers"]).get_json()["item"]
    assert pk(got["share"])["note"] == NOTE
    r = w.c.delete(f"/share/{l['id']}", headers=w.A["headers"])
    assert pk(r.get_json()["listing"])["note"] == NOTE  # owner's cancel response


def test_nobody_but_owner_and_claimer_sees_canary_on_any_endpoint(w):
    l = mk(w.c, w.A, w.item)
    # a group listing too, to cover group members
    it2 = w.c.post("/items", json={"items": [{"name": "Beans"}]}, headers=w.A["headers"]).get_json()["items"][0]
    l2 = mk(w.c, w.A, it2, group_id=w.g["id"])
    gp = w.c.post("/items", json={"group_id": w.g["id"], "items": [{"name": "PantryThing"}]}, headers=w.A["headers"])
    assert gp.status_code == 201
    w.c.post("/requests", json={"text": "need food", "audiences": {"friends": True}}, headers=w.B["headers"])
    for viewer in (w.B, w.C, w.D, w.E, w.F, w.M, w.X, w.Y):
        for path, txt in crawl(w.c, viewer, w).items():
            assert not has_canary(txt), (viewer["user"]["display_name"], path)
    # owner still sees it
    assert has_canary(crawl(w.c, w.A, w)["/items?include_removed=true"])


def test_group_member_non_claimer_gets_redacted(w):
    it2 = w.c.post("/items", json={"items": [{"name": "Beans"}]}, headers=w.A["headers"]).get_json()["items"][0]
    l2 = mk(w.c, w.A, it2, group_id=w.g["id"])
    for m in (w.M, w.Y):
        e = next(x for x in pantry(w.c, m) if x["id"] == l2["id"])
        assert e["pickup"] is None and e["pickup_set"] is True
    r = claim(w.c, w.M, l2["id"])
    assert pk(r.get_json()["listing"])["note"] == NOTE
    assert all(x["id"] != l2["id"] for x in pantry(w.c, w.Y))  # claimed by M: hidden from Y
    # a friend of the owner who is not in the group never sees the group listing
    assert all(x["id"] != l2["id"] for x in pantry(w.c, w.B))
    assert claim(w.c, w.B, l2["id"]).status_code == 404


def test_ex_group_member_loses_everything(w):
    it2 = w.c.post("/items", json={"items": [{"name": "Beans"}]}, headers=w.A["headers"]).get_json()["items"][0]
    l2 = mk(w.c, w.A, it2, group_id=w.g["id"])
    assert claim(w.c, w.M, l2["id"]).status_code == 200
    assert pk(next(x for x in pantry(w.c, w.M) if x["id"] == l2["id"])) is not None
    assert w.c.post(f"/groups/{w.g['id']}/leave", headers=w.M["headers"]).status_code in (200, 204)
    assert all(x["id"] != l2["id"] for x in pantry(w.c, w.M))
    for path, txt in crawl(w.c, w.M, w).items():
        assert not has_canary(txt), path
    r = claim(w.c, w.M, l2["id"])
    assert r.status_code == 404 and not has_canary(r.get_data(as_text=True))
    assert patch(w.c, w.M, l2["id"], {"pickup": None}).status_code == 404


def test_friend_removed_after_claim_loses_visibility(w):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    assert w.c.delete(f"/friends/{w.B['user']['id']}", headers=w.A["headers"]).status_code == 204
    for path, txt in crawl(w.c, w.B, w).items():
        assert not has_canary(txt), path
    assert claim(w.c, w.B, l["id"]).status_code == 404


def test_friend_of_friend_and_pending_see_nothing(w):
    l = mk(w.c, w.A, w.item)
    for u in (w.D, w.F, w.E):
        assert all(x["id"] != l["id"] for x in pantry(w.c, u))
        assert claim(w.c, u, l["id"]).status_code == 404
        assert w.c.get(f"/people/reachable?item_id={w.item['id']}", headers=u["headers"]).status_code == 404


def test_people_reachable_never_embeds_pickup(w):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    r = w.c.get(f"/people/reachable?item_id={w.item['id']}", headers=w.A["headers"])
    assert r.status_code == 200 and not has_canary(r.get_data(as_text=True))
    assert not any("pickup" in p for p in r.get_json()["people"])


def test_requests_fulfil_and_board_do_not_carry_pickup(w):
    mk(w.c, w.A, w.item)
    rq = w.c.post("/requests", json={"text": "soup?", "audiences": {"friends": True}}, headers=w.B["headers"])
    rid = rq.get_json()["request"]["id"]
    r = w.c.post(f"/requests/{rid}/fulfil", headers=w.A["headers"])
    assert r.status_code == 200 and not has_canary(r.get_data(as_text=True))
    assert "pickup" not in r.get_data(as_text=True)


# ---------- unclaim / remove / restore ----------
def unclaim(w, user, lid):
    r = w.c.delete(f"/share/{lid}/claim", headers=user["headers"])
    if r.status_code in (404, 405) and "Listing not found" not in r.get_data(as_text=True):
        pytest.skip("no unclaim endpoint in this build")
    return r


def test_after_unclaim_old_claimer_loses_pickup(w):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    r = unclaim(w, w.B, l["id"])
    assert r.status_code == 200, r.get_data(as_text=True)
    assert pk(r.get_json()["listing"]) is None  # B is no longer the claimer
    e = next(x for x in pantry(w.c, w.B) if x["id"] == l["id"])
    assert e["pickup"] is None and e["pickup_set"] is True and not e["claimed_by_me"]
    for path, txt in crawl(w.c, w.B, w).items():
        assert not has_canary(txt), path
    # pickup kept for the owner and for the next claimer
    assert pk(owner_item(w.c, w.A, w.item["id"])["share"])["note"] == NOTE
    assert pk(claim(w.c, w.C, l["id"]).get_json()["listing"])["note"] == NOTE


def test_donate_then_restore_keeps_pickup_and_claimer_sees_it_again(w, sql):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    r = w.c.post(f"/items/{w.item['id']}/remove", json={"outcome": "donated"}, headers=w.A["headers"])
    assert r.status_code == 200
    assert pk(r.get_json()["item"]["share"])["note"] == NOTE  # owner response
    assert all(x["id"] != l["id"] for x in pantry(w.c, w.B))  # fulfilled: not on the board
    for path, txt in crawl(w.c, w.B, w).items():
        assert not has_canary(txt), path
    r = w.c.post(f"/items/{w.item['id']}/restore", headers=w.A["headers"])
    assert r.status_code == 200
    s = r.get_json()["item"]["share"]
    assert s["status"] == "open" and pk(s)["note"] == NOTE
    assert pk(next(x for x in pantry(w.c, w.B) if x["id"] == l["id"]))["note"] == NOTE
    row = sql("SELECT pickup_note, pickup_lat FROM share_listings")[0]
    assert row["pickup_note"] == NOTE


def test_remove_donated_to_other_friend_recipient_never_sees_pickup(w):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    r = w.c.post(f"/items/{w.item['id']}/remove", json={"outcome": "donated", "recipient_id": w.C["user"]["id"]},
                 headers=w.A["headers"])
    assert r.status_code == 200
    for u in (w.B, w.C):
        for path, txt in crawl(w.c, u, w).items():
            assert not has_canary(txt), (u["user"]["display_name"], path)


def test_batch_remove_and_restore_responses_show_pickup_to_owner_only(w, make_item):
    other = make_item(w.A, name="Eggs")
    l1 = mk(w.c, w.A, w.item)
    l2 = mk(w.c, w.A, other, pickup={"note": "second"})
    claim(w.c, w.B, l1["id"])
    ids = [w.item["id"], other["id"]]
    r = w.c.post("/items/remove-batch", json={"item_ids": ids, "outcome": "donated"}, headers=w.A["headers"])
    assert r.status_code == 200
    got = {i["id"]: i for i in r.get_json()["items"]}
    assert pk(got[w.item["id"]]["share"])["note"] == NOTE and pk(got[other["id"]]["share"])["note"] == "second"
    r = w.c.post("/items/restore-batch", json={"item_ids": ids}, headers=w.A["headers"])
    got = {i["id"]: i for i in r.get_json()["items"]}
    assert pk(got[w.item["id"]]["share"])["note"] == NOTE and got[w.item["id"]]["share"]["status"] == "open"
    # the claimer (B) never sees the second (unclaimed) listing's pickup, and sees his own again
    mine = {x["id"]: x for x in pantry(w.c, w.B)}
    assert pk(mine[l1["id"]])["note"] == NOTE
    assert pk(mine[l2["id"]]) is None and mine[l2["id"]]["pickup_set"] is True


def test_account_delete_of_claimer_opens_listing_and_hides_pickup_from_nobody_new(w):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    assert w.c.delete("/auth/me", headers=w.B["headers"]).status_code == 204
    e = next(x for x in pantry(w.c, w.C) if x["id"] == l["id"])
    assert e["pickup"] is None and e["pickup_set"] is True
    assert pk(owner_item(w.c, w.A, w.item["id"])["share"])["note"] == NOTE


def test_owner_account_delete_removes_listing_with_pickup(w, sql):
    mk(w.c, w.A, w.item)
    assert w.c.delete("/auth/me", headers=w.A["headers"]).status_code == 204
    assert sql("SELECT count(*) AS n FROM share_listings")[0]["n"] == 0


# ---------- impact / events ----------
def test_pickup_never_changes_events_or_impact(w, sql, make_item):
    # give the owner some history so the snapshot is non-trivial
    done = make_item(w.A, name="Done")
    w.c.post(f"/items/{done['id']}/remove", json={"outcome": "used"}, headers=w.A["headers"])
    snap_a, snap_b = impact_all(w.c, w.A), impact_all(w.c, w.B)
    n = ev_count(sql)
    l = mk(w.c, w.A, w.item, pickup=None)
    n_after_share = ev_count(sql)
    assert n_after_share == n + 1 and ev_count(sql, "share") == 1  # the share event only
    share_ev = sql("SELECT * FROM food_events WHERE event_type='share'")
    steps = [lambda: patch(w.c, w.A, l["id"], {"pickup": PICKUP}),
             lambda: patch(w.c, w.A, l["id"], {"pickup": {"note": "b"}}),
             lambda: claim(w.c, w.B, l["id"]),
             lambda: patch(w.c, w.A, l["id"], {"pickup": None}),
             lambda: patch(w.c, w.A, l["id"], {"pickup": {"lat": 5, "lng": 6}}),
             lambda: patch(w.c, w.A, l["id"], {"pickup": {"lat": 95, "lng": 6}}),
             lambda: patch(w.c, w.C, l["id"], {"pickup": None})]
    for s in steps:
        s()
        assert ev_count(sql) == n_after_share
    assert impact_all(w.c, w.A) == snap_a and impact_all(w.c, w.B) == snap_b
    assert sql("SELECT * FROM food_events WHERE event_type='share'") == share_ev


def test_create_with_pickup_writes_same_event_as_without(w, sql, make_item):
    a = make_item(w.A, name="P1")
    b = make_item(w.A, name="P2")
    mk(w.c, w.A, a, pickup=None)
    mk(w.c, w.A, b)
    rows = sql("SELECT category, quantity, est_weight_kg, est_price, co2e_kg, outcome FROM food_events "
               "WHERE event_type='share' ORDER BY item_id")
    assert len(rows) == 2 and rows[0] == rows[1]


def test_remove_and_restore_impact_exact_with_pickup(w):
    l = mk(w.c, w.A, w.item)
    claim(w.c, w.B, l["id"])
    base = impact_all(w.c, w.A)
    w.c.post(f"/items/{w.item['id']}/remove", json={"outcome": "donated"}, headers=w.A["headers"])
    w.c.post(f"/items/{w.item['id']}/restore", headers=w.A["headers"])
    assert impact_all(w.c, w.A) == base


# ---------- rollback / atomicity ----------
def test_forced_failure_on_create_rolls_back_listing_and_event(app, w, sql):
    def boom(conn, cur, stmt, params, ctx, many):
        if stmt.lstrip().upper().startswith("INSERT INTO FOOD_EVENTS"):
            raise RuntimeError("boom")

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", boom)
        try:
            c = app.test_client()
            app.config["PROPAGATE_EXCEPTIONS"] = False
            r = c.post("/share", json={"item_id": w.item["id"], "pickup": PICKUP}, headers=w.A["headers"])
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", boom)
            app.config.pop("PROPAGATE_EXCEPTIONS", None)
    assert r.status_code == 500
    assert sql("SELECT count(*) AS n FROM share_listings")[0]["n"] == 0
    assert ev_count(sql, "share") == 0
    assert mk(w.c, w.A, w.item)  # item is shareable afterwards


def test_forced_failure_on_patch_leaves_pickup_unchanged(app, w, sql):
    l = mk(w.c, w.A, w.item)

    def boom(conn, cur, stmt, params, ctx, many):
        if stmt.lstrip().upper().startswith("UPDATE SHARE_LISTINGS"):
            raise RuntimeError("boom")

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", boom)
        try:
            app.config["PROPAGATE_EXCEPTIONS"] = False
            r = app.test_client().patch(f"/share/{l['id']}", json={"pickup": {"note": "new"}}, headers=w.A["headers"])
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", boom)
            app.config.pop("PROPAGATE_EXCEPTIONS", None)
    assert r.status_code == 500
    assert sql("SELECT pickup_note FROM share_listings")[0]["pickup_note"] == NOTE


def test_concurrent_patch_and_cancel_is_consistent(app, w, sql):
    import threading
    l = mk(w.c, w.A, w.item)
    out = {}

    def p():
        with app.test_client() as c:
            out["p"] = patch(c, w.A, l["id"], {"pickup": {"note": "late"}}).status_code

    def d():
        with app.test_client() as c:
            out["d"] = c.delete(f"/share/{l['id']}", headers=w.A["headers"]).status_code

    ts = [threading.Thread(target=p), threading.Thread(target=d)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert out["d"] == 200 and out["p"] in (200, 409), out
    row = sql("SELECT status, pickup_note FROM share_listings")[0]
    assert row["status"] == "cancelled"


# ---------- queries ----------
def _count(app, fn):
    n = []

    def hook(conn, cur, stmt, params, ctx, many):
        n.append(stmt)

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", hook)
        try:
            fn()
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", hook)
    return n


def test_no_n_plus_one_on_pantry_and_owner_items(app, w, make_item):
    def add(k):
        for i in range(k):
            it = make_item(w.A, name=f"I{i}-{uuid.uuid4().hex[:4]}")
            mk(w.c, w.A, it, pickup={"note": f"n{i}"} if i % 2 else None)

    add(2)
    p1 = len(_count(app, lambda: w.c.get("/share", headers=w.B["headers"])))
    o1 = len(_count(app, lambda: w.c.get("/items", headers=w.A["headers"])))
    add(10)
    p2 = len(_count(app, lambda: w.c.get("/share", headers=w.B["headers"])))
    o2 = len(_count(app, lambda: w.c.get("/items", headers=w.A["headers"])))
    assert p2 <= p1 + 1 and o2 <= o1 + 1, (p1, p2, o1, o2)
    assert len(pantry(w.c, w.B)) == 12


def test_batch_remove_query_count_constant_with_pickup(app, w, make_item):
    def batch(k):
        its = [make_item(w.A, name=f"B{k}-{i}") for i in range(k)]
        for it in its:
            mk(w.c, w.A, it)
        ids = [i["id"] for i in its]
        q = _count(app, lambda: w.c.post("/items/remove-batch", json={"item_ids": ids, "outcome": "donated"},
                                         headers=w.A["headers"]))
        return len(q)

    assert batch(10) <= batch(2) + 2


# ---------- misc ----------
def test_pickup_set_present_on_every_listing_serialisation(w):
    l = mk(w.c, w.A, w.item)
    assert "pickup_set" in l and "pickup" in l
    assert "pickup_set" in w.c.delete(f"/share/{l['id']}", headers=w.A["headers"]).get_json()["listing"]
    it = w.c.post("/items", json={"items": [{"name": "Q"}]}, headers=w.A["headers"]).get_json()["items"][0]
    l2 = mk(w.c, w.A, it, pickup=None)
    assert "pickup_set" in claim(w.c, w.B, l2["id"]).get_json()["listing"]
    for e in pantry(w.c, w.B):
        assert "pickup" in e and "pickup_set" in e


def test_trim_applies_to_place_and_response_contains_no_raw_columns(w):
    l = mk(w.c, w.A, w.item, pickup={"note": "x", "place_name": "  Cafe  "})
    assert pk(l)["place_name"] == "Cafe"
    assert not any(k.startswith("pickup_") and k != "pickup_set" for k in l)


def test_pantry_hides_pickup_even_for_viewer_who_is_also_in_group_and_friend(w):
    """B is a friend; join B to the group too: a friends listing has no group audience, still redacted."""
    w.c.post("/groups/join", json={"invite_code": w.g["invite_code"]}, headers=w.B["headers"])
    l = mk(w.c, w.A, w.item)
    e = next(x for x in pantry(w.c, w.B) if x["id"] == l["id"])
    assert e["pickup"] is None


def test_float_precision_roundtrip(w):
    l = mk(w.c, w.A, w.item, pickup={"lat": 33.123456, "lng": -84.654321})
    assert pk(l)["lat"] == pytest.approx(33.123456, abs=1e-6)
    assert not math.isnan(pk(l)["lng"])
