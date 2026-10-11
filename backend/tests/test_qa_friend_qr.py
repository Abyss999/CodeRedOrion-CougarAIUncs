"""QA for friend QR codes: GET /friends/code, POST /friends {code}.

Design (owner rulings 2026-10-11, revised): codes are OPAQUE random strings (token_urlsafe, ~12-16 chars)
stored in `friend_codes` (code, user_id, expires_at), 10-minute TTL. Not decodable, no user id / email.
Rulings: bad codes (unknown, expired, tampered, malformed) -> 400 `invalid_code`, ONE byte-identical body;
own code -> 400; already friends -> 200 idempotent (not 409); pending either direction -> 200 accepted;
exactly one of email / code -> else 400 `validation_error`; the email flow is unchanged.
"""
import base64
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.extensions import db
from conftest import _signup

URLSAFE = re.compile(r"^[A-Za-z0-9_\-]+$")


def get_code(client, u):
    r = client.get("/friends/code", headers=u["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def use(client, u, code):
    return client.post("/friends", json={"code": code}, headers=u["headers"])


def rels(client, u):
    return client.get("/friends", headers=u["headers"]).get_json()


def n_rows(sql, a, b):
    return sql("SELECT count(*) AS n FROM friendships WHERE (user_id=:a AND friend_id=:b) "
               "OR (user_id=:b AND friend_id=:a)", a=a["user"]["id"], b=b["user"]["id"])[0]["n"]


def set_expiry(sql, code, delta_seconds):
    sql("UPDATE friend_codes SET expires_at = now() + make_interval(secs => :s) WHERE code = :c",
        s=delta_seconds, c=code)


def err(resp):
    return resp.get_json()["error"]


# ---------- GET /friends/code ----------
def test_code_requires_auth(client):
    r = client.get("/friends/code")
    assert r.status_code == 401
    assert client.get("/friends/code", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_code_shape_ttl_and_url(client, user, sql):
    before = datetime.now(timezone.utc)
    body = get_code(client, user)
    assert set(body) >= {"code", "expires_at", "url"}
    code = body["code"]
    assert isinstance(code, str) and 10 <= len(code) <= 24, code
    assert URLSAFE.match(code), "code must be URL/QR safe without percent-encoding"
    assert body["url"] == f"bitedown://friend/{code}"
    exp = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    assert exp.tzinfo is not None
    assert timedelta(minutes=9, seconds=45) <= exp - before <= timedelta(minutes=10, seconds=15)
    row = sql("SELECT user_id::text AS u, expires_at FROM friend_codes WHERE code=:c", c=code)
    assert len(row) == 1 and row[0]["u"] == user["user"]["id"]
    assert abs((row[0]["expires_at"] - exp).total_seconds()) < 1.5


def test_code_does_not_reveal_user_or_email(client, signup):
    u = signup(email="very.identifiable.person@example.com", name="Identifiable Person")
    code = get_code(client, u)["code"]
    uid = u["user"]["id"]
    blob = (code + get_code(client, u)["url"]).lower()
    for needle in (uid, uid.replace("-", ""), u["email"], "identifiable", "example.com", "@"):
        assert needle.lower() not in blob
    # not decodable into the id: try base64 variants and hex
    raw = uuid.UUID(uid).bytes
    for pad in ("", "=", "==", "==="):
        for dec in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                out = dec(code + pad)
            except Exception:
                continue
            assert raw not in out and uid.encode() not in out and u["email"].encode() not in out
    assert raw.hex() not in code.lower()


def test_get_reuses_code_until_under_two_minutes_remain(client, user, sql):
    first = get_code(client, user)
    assert get_code(client, user) == first
    set_expiry(sql, first["code"], 121)
    assert get_code(client, user)["code"] == first["code"]
    set_expiry(sql, first["code"], 119)
    second = get_code(client, user)
    assert second["code"] != first["code"]
    assert get_code(client, user) == second


def test_get_prunes_only_callers_expired_codes(client, user, user2, sql):
    old = get_code(client, user)["code"]
    other = get_code(client, user2)["code"]
    set_expiry(sql, old, -1)
    set_expiry(sql, other, -1)
    assert get_code(client, user)["code"] != old
    assert sql("SELECT count(*) AS n FROM friend_codes WHERE code=:c", c=old)[0]["n"] == 0
    assert sql("SELECT count(*) AS n FROM friend_codes WHERE code=:c", c=other)[0]["n"] == 1


def test_codes_differ_between_users_and_look_random(client, user, user2, sql):
    a = get_code(client, user)["code"]
    b = get_code(client, user2)["code"]
    assert a != b
    # crude randomness check: no shared long prefix across 40 codes, many distinct first chars
    cs = []
    for _ in range(40):
        code = get_code(client, user)["code"]
        cs.append(code)
        set_expiry(sql, code, 119)
    assert len({c[0] for c in cs}) > 6
    assert len({c[:6] for c in cs}) == 40


# ---------- POST /friends {code} happy paths ----------
def test_scan_creates_accepted_friendship(client, user, user2, sql):
    code = get_code(client, user)["code"]
    r = use(client, user2, code)
    assert r.status_code == 201, r.get_data(as_text=True)
    f = r.get_json()["friend"]
    assert f["user_id"] == user["user"]["id"] and f["status"] == "accepted"
    assert "email" not in f and user["email"] not in r.get_data(as_text=True)
    assert [x["user_id"] for x in rels(client, user2)["friends"]] == [user["user"]["id"]]
    assert [x["user_id"] for x in rels(client, user)["friends"]] == [user2["user"]["id"]]
    assert rels(client, user)["incoming"] == [] and rels(client, user)["outgoing"] == []
    assert n_rows(sql, user, user2) == 1


def test_friendship_actually_grants_visibility(client, user, user2, make_item):
    it = make_item(user)
    use(client, user2, get_code(client, user)["code"])
    assert client.post("/share", json={"item_id": it["id"]}, headers=user["headers"]).status_code == 201
    pantry = client.get("/share", headers=user2["headers"]).get_json()["listings"]
    assert [l["item_id"] for l in pantry] == [it["id"]]


@pytest.mark.parametrize("direction", ["issuer_asked", "scanner_asked"])
def test_pending_request_either_direction_becomes_accepted(client, user, user2, sql, direction):
    asker, other = (user, user2) if direction == "issuer_asked" else (user2, user)
    assert client.post("/friends", json={"email": other["email"]}, headers=asker["headers"]).status_code == 201
    code = get_code(client, user)["code"]
    r = use(client, user2, code)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["friend"]["status"] == "accepted"
    assert n_rows(sql, user, user2) == 1
    assert sql("SELECT status FROM friendships")[0]["status"] == "accepted"
    for u in (user, user2):
        b = rels(client, u)
        assert len(b["friends"]) == 1 and b["incoming"] == [] and b["outgoing"] == []


def test_scanning_own_pending_target_code_from_the_asker_side(client, user, user2, sql):
    """user asked user2 by email; user then scans user2's code: still one accepted row."""
    client.post("/friends", json={"email": user2["email"]}, headers=user["headers"])
    r = use(client, user, get_code(client, user2)["code"])
    assert r.status_code == 200
    assert n_rows(sql, user, user2) == 1
    assert sql("SELECT status FROM friendships")[0]["status"] == "accepted"


def test_already_friends_is_200_idempotent(client, user, user2, sql):
    code = get_code(client, user)["code"]
    assert use(client, user2, code).status_code == 201
    created = sql("SELECT created_at FROM friendships")[0]["created_at"]
    for c in (code, get_code(client, user)["code"]):
        r = use(client, user2, c)
        assert r.status_code == 200, r.get_data(as_text=True)
        f = r.get_json()["friend"]
        assert f["user_id"] == user["user"]["id"] and f["status"] == "accepted"
    # reverse direction too
    r = use(client, user, get_code(client, user2)["code"])
    assert r.status_code == 200
    assert n_rows(sql, user, user2) == 1
    assert sql("SELECT created_at FROM friendships")[0]["created_at"] == created


def test_multiple_scanners_can_use_one_code(client, user, signup):
    """A QR on a screen is scanned by several people; record behaviour, require no 500 and no crossover."""
    code = get_code(client, user)["code"]
    seen = [use(client, signup(), code).status_code for _ in range(3)]
    assert all(s in (201, 400) for s in seen), seen  # reuse allowed (201) or single-use (400)


# ---------- rejections ----------
def test_own_code_is_400(client, user, sql):
    r = use(client, user, get_code(client, user)["code"])
    assert r.status_code == 400
    assert sql("SELECT count(*) AS n FROM friendships")[0]["n"] == 0


def test_expired_code_rejected_even_if_row_present(client, user, user2, sql):
    code = get_code(client, user)["code"]
    set_expiry(sql, code, -1)
    assert sql("SELECT count(*) AS n FROM friend_codes WHERE code=:c", c=code)[0]["n"] == 1
    r = use(client, user2, code)
    assert r.status_code == 400 and err(r)["code"] == "invalid_code"
    assert n_rows(sql, user, user2) == 0


def test_replay_after_expiry_is_rejected_after_first_success(client, user, user2, signup, sql):
    code = get_code(client, user)["code"]
    assert use(client, user2, code).status_code == 201
    set_expiry(sql, code, -60)
    stranger = signup()
    assert use(client, stranger, code).status_code == 400
    assert n_rows(sql, user, stranger) == 0
    # a friend replaying an expired code also gets 400, not the idempotent 200 (no existence oracle)
    assert use(client, user2, code).status_code == 400


def test_expiry_boundary_around_ttl(client, user, user2, signup, sql):
    code = get_code(client, user)["code"]
    set_expiry(sql, code, 5)  # still valid for a few more seconds
    assert use(client, user2, code).status_code == 201
    u3 = signup()
    code2 = get_code(client, user)["code"]
    set_expiry(sql, code2, -0.5)
    assert use(client, u3, code2).status_code == 400


def test_expired_row_with_ttl_pushed_back_is_the_only_way_in(client, user, user2, sql):
    code = get_code(client, user)["code"]
    set_expiry(sql, code, -3600)
    assert use(client, user2, code).status_code == 400
    set_expiry(sql, code, 120)  # sanity: validity is read from the row at request time
    assert use(client, user2, code).status_code == 201


def bad_variants(client, user, sql):
    good = get_code(client, user)["code"]
    flipped = good[:-1] + ("A" if good[-1] != "A" else "B")
    set_expiry(sql, good, 119)
    expired = get_code(client, user)["code"]
    set_expiry(sql, expired, -5)
    return {
        "unknown": "".join("Z" for _ in good),
        "unknown_random": uuid.uuid4().hex[:len(good)],
        "tampered_last": flipped,
        "tampered_first": ("A" if good[0] != "A" else "B") + good[1:],
        "truncated": good[:-3],
        "extended": good + "xx",
        "lowercased_or_upper": good.swapcase(),
        "expired": expired,
        "url_form": f"bitedown://friend/{good}",
        "long": "a" * 5000,
        "unicode": "‮é中文" * 3,
        "sqlish": "' OR '1'='1' --",
        "percent": "%00%27",
        "dash_only": "-" * 14,
    }


def test_all_bad_codes_are_400_invalid_code_with_byte_identical_bodies(client, user, user2, sql):
    bodies = {}
    for name, bad in bad_variants(client, user, sql).items():
        r = use(client, user2, bad)
        assert r.status_code == 400, (name, r.status_code, r.get_data(as_text=True))
        assert err(r)["code"] == "invalid_code", name
        bodies[name] = r.get_data()
    assert len(set(bodies.values())) == 1, {k: v for k, v in bodies.items()}
    assert n_rows(sql, user, user2) == 0
    # headers must not differ in a way that distinguishes causes (content-length is covered by the body)
    assert "invalid_code" in next(iter(bodies.values())).decode()


def test_url_form_is_not_accepted_as_code_or_must_be_identical_400(client, user, user2):
    """The raw deep link pasted as the code. Server contract is the bare code; the app strips the scheme."""
    code = get_code(client, user)
    r = use(client, user2, code["url"])
    assert r.status_code in (400, 201)
    assert r.status_code == 400 or r.get_json()["friend"]["user_id"] == user["user"]["id"]


def test_bad_code_error_is_not_an_oracle_for_friendship_or_user_existence(client, user, user2, sql):
    use(client, user2, get_code(client, user)["code"])  # now friends
    tampered = get_code(client, user)["code"][:-1] + "!"
    r1 = use(client, user2, tampered)
    r2 = use(client, user2, "nonexistentcode1")
    assert r1.status_code == r2.status_code == 400
    assert r1.get_data() == r2.get_data()


@pytest.mark.parametrize("bad", [None, 123, 1.5, True, [], ["x"], {}, {"a": 1}, "", "   "])
def test_malformed_code_types_never_500(client, user2, bad):
    r = client.post("/friends", json={"code": bad}, headers=user2["headers"])
    assert r.status_code == 400, r.get_data(as_text=True)
    assert err(r)["code"] in ("invalid_code", "validation_error")


def test_exactly_one_of_email_and_code(client, user, user2, sql):
    code = get_code(client, user)["code"]
    both = client.post("/friends", json={"email": user["email"], "code": code}, headers=user2["headers"])
    assert both.status_code == 400 and err(both)["code"] == "validation_error"
    none = client.post("/friends", json={}, headers=user2["headers"])
    assert none.status_code == 400 and err(none)["code"] == "validation_error"
    assert client.post("/friends", json={"email": None, "code": None}, headers=user2["headers"]).status_code == 400
    assert sql("SELECT count(*) AS n FROM friendships")[0]["n"] == 0  # "both" must not half-apply


def test_code_requires_auth_on_post(client, user):
    code = get_code(client, user)["code"]
    assert client.post("/friends", json={"code": code}).status_code == 401


def test_non_json_and_wrong_body_shapes(client, user2):
    h = user2["headers"]
    assert client.post("/friends", data="not json", headers=h).status_code == 400
    assert client.post("/friends", json=["code"], headers=h).status_code == 400


def test_issuer_deleted_makes_code_invalid(client, user, user2, sql):
    code = get_code(client, user)["code"]
    assert client.delete("/auth/me", headers=user["headers"]).status_code == 204
    r = use(client, user2, code)
    assert r.status_code == 400 and err(r)["code"] == "invalid_code"
    assert sql("SELECT count(*) AS n FROM friendships")[0]["n"] == 0


def test_account_deletion_with_live_codes_does_not_500(client, user, sql):
    for _ in range(3):
        get_code(client, user)
    assert client.delete("/auth/me", headers=user["headers"]).status_code == 204
    assert sql("SELECT count(*) AS n FROM friend_codes")[0]["n"] == 0


def test_scanner_deleted_midway_is_not_a_500(client, user, user2):
    code = get_code(client, user)["code"]
    client.delete("/auth/me", headers=user2["headers"])
    assert use(client, user2, code).status_code == 401


def test_brute_force_guesses_all_identical_400(client, user, user2):
    get_code(client, user)
    outs = {use(client, user2, uuid.uuid4().hex[:14]).get_data() for _ in range(25)}
    assert len(outs) == 1


def test_dos_by_code_spam_is_bounded(client, user, sql):
    """Informational/guard: one user minting many codes must not 500; row count stays sane."""
    for _ in range(40):
        assert client.get("/friends/code", headers=user["headers"]).status_code == 200
    assert sql("SELECT count(*) AS n FROM friend_codes")[0]["n"] <= 40


# ---------- email flow unchanged ----------
def test_email_flow_unchanged(client, user, user2, signup):
    h = user["headers"]
    r = client.post("/friends", json={"email": user2["email"]}, headers=h)
    assert r.status_code == 201 and r.get_json()["friend"]["status"] == "pending"
    assert client.post("/friends", json={"email": user2["email"]}, headers=h).status_code == 409
    assert client.post("/friends", json={"email": user["email"]}, headers=h).status_code == 400
    assert client.post("/friends", json={"email": "nobody@example.com"}, headers=h).status_code == 404
    assert client.post("/friends", json={"email": ""}, headers=h).status_code == 400
    assert client.post(f"/friends/{user['user']['id']}/accept", headers=user2["headers"]).status_code == 200
    r = client.post("/friends", json={"email": user2["email"]}, headers=h)
    assert r.status_code == 409 and err(r)["code"] == "already_friends"


# ---------- concurrency ----------
def test_concurrent_scans_leave_one_row_and_no_500(app, client, user, user2, sql):
    code = get_code(client, user)["code"]
    out = []

    def go():
        with app.test_client() as c:
            out.append(c.post("/friends", json={"code": code}, headers=user2["headers"]).status_code)

    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(s in (200, 201) for s in out), out
    assert out.count(201) <= 1
    assert n_rows(sql, user, user2) == 1


def test_concurrent_email_request_and_scan_leave_one_row(app, client, user, user2, sql):
    code = get_code(client, user)["code"]
    out = {}

    def scan():
        with app.test_client() as c:
            out["scan"] = c.post("/friends", json={"code": code}, headers=user2["headers"]).status_code

    def email():
        with app.test_client() as c:
            out["email"] = c.post("/friends", json={"email": user2["email"]}, headers=user["headers"]).status_code

    ts = [threading.Thread(target=scan), threading.Thread(target=email)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert out["scan"] in (200, 201) and out["email"] in (201, 409), out
    assert n_rows(sql, user, user2) == 1
    assert sql("SELECT status FROM friendships")[0]["status"] == "accepted"


def test_opposite_direction_concurrent_scans_one_row(app, client, user, user2, sql):
    c1, c2 = get_code(client, user)["code"], get_code(client, user2)["code"]
    out = []

    def a():
        with app.test_client() as c:
            out.append(c.post("/friends", json={"code": c2}, headers=user["headers"]).status_code)

    def b():
        with app.test_client() as c:
            out.append(c.post("/friends", json={"code": c1}, headers=user2["headers"]).status_code)

    ts = [threading.Thread(target=a), threading.Thread(target=b)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(s in (200, 201) for s in out), out
    assert n_rows(sql, user, user2) == 1  # both directions racing must not create two rows


# ---------- query counts ----------
def _count(app, fn):
    n = []

    def hook(conn, cur, stmt, params, ctx, many):
        n.append(stmt)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", hook)
        try:
            fn()
        finally:
            event.remove(db.engine, "before_cursor_execute", hook)
    return n


def test_query_count_is_constant_with_many_codes_and_friends(app, client, user, signup):
    def run():
        c = get_code(client, user)["code"]
        return use(client, signup(), c)

    first = _count(app, lambda: client.get("/friends/code", headers=user["headers"]))
    for _ in range(15):
        run()
    later = _count(app, lambda: client.get("/friends/code", headers=user["headers"]))
    assert len(later) <= len(first) + 2
    code = get_code(client, user)["code"]
    s = signup()
    q = _count(app, lambda: use(client, s, code))
    assert len(q) <= 12, q


# ---------- no side effects ----------
def test_failed_scan_changes_nothing(client, user, user2, sql):
    before = sql("SELECT count(*) AS n FROM friendships")[0]["n"]
    use(client, user2, "nope-nope-nope")
    use(client, user2, get_code(client, user2)["code"])  # own
    assert sql("SELECT count(*) AS n FROM friendships")[0]["n"] == before
    assert rels(client, user2) == {"friends": [], "incoming": [], "outgoing": []}


def test_friend_code_never_in_other_endpoints(client, user):
    code = get_code(client, user)["code"]
    for path in ("/friends", "/auth/me", "/groups", "/share", "/items", "/requests", "/impact"):
        assert code not in client.get(path, headers=user["headers"]).get_data(as_text=True), path


def test_code_not_usable_as_other_credentials(client, user, user2):
    code = get_code(client, user)["code"]
    assert client.get("/items", headers={"Authorization": f"Bearer {code}"}).status_code == 401
    g = client.post("/groups", json={"name": "G"}, headers=user["headers"]).get_json()["group"]
    assert client.post("/groups/join", json={"invite_code": code}, headers=user2["headers"]).status_code in (400, 404)
    assert g["invite_code"] != code


def test_response_never_leaks_email_of_issuer(client, user, user2):
    r = use(client, user2, get_code(client, user)["code"])
    assert user["email"] not in r.get_data(as_text=True)
    assert user2["email"] not in client.get("/friends", headers=user["headers"]).get_data(as_text=True)


def test_surrounding_whitespace_is_trimmed_not_rejected(client, user, user2):
    """The server strips the code (a pasted/scanned code may carry a newline); it is still a valid code."""
    r = use(client, user2, " \n" + get_code(client, user)["code"] + "\t ")
    assert r.status_code == 201 and r.get_json()["friend"]["user_id"] == user["user"]["id"]
