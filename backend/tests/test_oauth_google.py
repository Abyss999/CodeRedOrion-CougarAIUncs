"""POST /auth/oauth/google {id_token}: verification, account resolution, JWKS cache, errors.

Google is never called: tokens are signed with local RSA keys and the JWKS fetch is replaced with
`google_auth.set_fetcher`. Contract: docs/API.md "Auth".
"""
import base64
import hashlib
import hmac
import json
import threading
import time
import uuid
from types import SimpleNamespace

import jwt
import pytest
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import event as sa_event
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.services import google_auth
from conftest import _signup

URL = "/auth/oauth/google"
CID_A = "111-ios-a.apps.googleusercontent.com"
CID_B = "222-ios-b.apps.googleusercontent.com"
ISS = "https://accounts.google.com"


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


K1, K2, K_ROGUE = _key(), _key(), _key()


def _jwk(priv, kid):
    d = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    d.update(kid=kid, alg="RS256", use="sig")
    return d


class FakeJWKS:
    def __init__(self):
        self.keys = [_jwk(K1, "k1")]
        self.max_age = 3600
        self.calls = 0
        self.fail = None  # exception instance to raise
        self.payload = None  # override the returned jwks dict

    def __call__(self):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return (self.payload if self.payload is not None else {"keys": list(self.keys)}), self.max_age


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def monotonic(self):
        return self.t


@pytest.fixture
def jwks(app, monkeypatch):
    monkeypatch.setitem(app.config, "GOOGLE_IOS_CLIENT_IDS", f"{CID_A}, {CID_B}")
    fake = FakeJWKS()
    google_auth.set_fetcher(fake)
    yield fake
    google_auth.clear_cache()


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(google_auth, "time", SimpleNamespace(monotonic=c.monotonic))
    return c


def claims(**over):
    now = int(time.time())
    c = {"iss": ISS, "aud": CID_A, "azp": CID_A, "sub": "10769150350006150715", "email": "pat@gmail.com",
         "email_verified": True, "name": "Pat Doe", "given_name": "Pat", "iat": now, "exp": now + 3600}
    for k, v in over.items():
        if v is DROP:
            c.pop(k, None)
        else:
            c[k] = v
    return c


DROP = object()


def tok(key=K1, kid="k1", alg="RS256", headers=None, **over):
    h = {"kid": kid} if kid is not None else {}
    h.update(headers or {})
    return jwt.encode(claims(**over), key, algorithm=alg, headers=h)


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def raw_token(header, payload, sig=b""):
    return f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(payload).encode())}.{_b64(sig)}"


def post(client, token=None, **kw):
    if "json" not in kw and "data" not in kw:
        kw["json"] = {"id_token": token}
    return client.post(URL, **kw)


def err(r, status, code):
    assert r.status_code == status, (r.status_code, r.get_data(as_text=True))
    body = r.get_json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"code", "message"}, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body


def n(sql, table, where="true", **p):
    return sql(f"SELECT count(*) AS n FROM {table} WHERE {where}", **p)[0]["n"]


# --------------------------------------------------------------------------------------------- happy paths

def test_new_user_created_201_null_password(client, sql, jwks):
    r = post(client, tok())
    assert r.status_code == 201, r.get_data(as_text=True)
    b = r.get_json()
    assert set(b) == {"token", "user", "created"} and b["created"] is True
    u = b["user"]
    assert set(u) == {"id", "email", "display_name", "created_at"}
    assert u["email"] == "pat@gmail.com" and u["display_name"] == "Pat Doe" and u["created_at"].endswith("Z")
    row = sql("SELECT password_hash FROM users WHERE id=:i", i=u["id"])
    assert row == [{"password_hash": None}]
    ids = sql("SELECT provider, subject, user_id::text AS uid, email::text AS email FROM user_identities")
    assert ids == [{"provider": "google", "subject": "10769150350006150715", "uid": u["id"], "email": "pat@gmail.com"}]
    # the BiteDown token works on protected endpoints
    assert client.get("/items", headers={"Authorization": f"Bearer {b['token']}"}).status_code == 200


def test_existing_identity_signs_in_200(client, sql, jwks):
    first = post(client, tok()).get_json()
    r = post(client, tok())
    assert r.status_code == 200 and r.get_json()["created"] is False
    assert r.get_json()["user"] == first["user"]
    assert n(sql, "users") == 1 and n(sql, "user_identities") == 1


def test_response_shape_matches_email_login(client, jwks):
    s = _signup(client, email="shape@x.com")
    login = client.post("/auth/login", json={"email": "shape@x.com", "password": s["password"]}).get_json()
    g = post(client, tok(email="other@x.com", sub="s-shape")).get_json()
    assert set(login) == {"token", "user"}
    assert set(g) == {"token", "user", "created"}  # login's shape plus the documented created flag
    assert set(g["user"]) == set(login["user"]) and "password_hash" not in g["user"]


def test_link_by_email_case_insensitive_keeps_password(client, sql, jwks):
    s = _signup(client, email="Mixed.Case@Gmail.com")
    r = post(client, tok(email="MIXED.case@GMAIL.COM", sub="sub-link"))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["created"] is False
    assert r.get_json()["user"]["id"] == s["user"]["id"]
    assert n(sql, "users") == 1
    assert sql("SELECT user_id::text AS u FROM user_identities WHERE subject='sub-link'") == [{"u": s["user"]["id"]}]
    # password still works after linking
    lr = client.post("/auth/login", json={"email": "mixed.case@gmail.com", "password": s["password"]})
    assert lr.status_code == 200 and lr.get_json()["user"]["id"] == s["user"]["id"]


def test_same_sub_changed_email_signs_in_same_user(client, sql, jwks):
    first = post(client, tok(email="old@gmail.com")).get_json()["user"]
    r = post(client, tok(email="new@gmail.com"))
    assert r.status_code == 200 and r.get_json()["user"]["id"] == first["id"]
    assert n(sql, "users") == 1
    assert sql("SELECT email::text AS e FROM user_identities") == [{"e": "new@gmail.com"}]


def test_identity_wins_over_email_match(client, sql, jwks):
    a = post(client, tok(sub="sub-a", email="a@gmail.com")).get_json()["user"]
    b = _signup(client, email="b@x.com")
    # Google now reports sub-a with b's email: the identity decides, b is untouched
    r = post(client, tok(sub="sub-a", email="b@x.com"))
    assert r.status_code == 200 and r.get_json()["user"]["id"] == a["id"]
    assert n(sql, "user_identities", "user_id=:u", u=b["user"]["id"]) == 0


def test_second_sub_same_email_identity_conflict(client, sql, jwks):
    """Ruling: one Google identity per user. A second sub for the same email is 409, nothing written."""
    a = post(client, tok(sub="sub-1", email="shared@gmail.com"))
    assert a.status_code == 201
    before = sql("SELECT * FROM user_identities ORDER BY subject")
    for email, extra in [("Shared@Gmail.com", {}), ("shared@gmail.com", {"hd": "corp.com"})]:
        err(post(client, tok(sub="sub-2", email=email, **extra)), 409, "identity_conflict")
    assert n(sql, "users") == 1 and sql("SELECT * FROM user_identities ORDER BY subject") == before
    # the original sub still signs in
    r = post(client, tok(sub="sub-1", email="shared@gmail.com"))
    assert r.status_code == 200 and r.get_json()["user"]["id"] == a.get_json()["user"]["id"]


def test_identity_conflict_checked_before_domain_rule(client, sql, jwks):
    """A non-linkable domain whose user already has a google identity: identity_conflict, not use_password."""
    post(client, tok(sub="corp-1", email="me@corp.example", hd="corp.example"))
    err(post(client, tok(sub="corp-2", email="me@corp.example")), 409, "identity_conflict")
    assert n(sql, "user_identities") == 1


@pytest.mark.parametrize("email, extra", [
    ("link@gmail.com", {}),
    ("Link@GMAIL.COM", {}),
    ("link@googlemail.com", {}),
    ("link@GoogleMail.Com", {}),
    ("link@corp.example", {"hd": "corp.example"}),
    ("link@corp.example", {"hd": "CORP.EXAMPLE"}),      # hd matches the email domain case-insensitively
    ("link@Corp.Example", {"hd": "corp.example"}),
    ("link@corp.example", {"hd": " corp.example "}),     # API.md: hd compared trimmed
    ("link@gmail.com", {"hd": "corp.example"}),          # gmail is linkable whatever hd says
    ("link@googlemail.com", {"hd": "other.example"}),
])
def test_link_allowed_branches(client, sql, jwks, email, extra):
    s = _signup(client, email=email.lower())
    r = post(client, tok(sub="link-sub", email=email, **extra))
    assert r.status_code == 200, r.get_data(as_text=True)
    b = r.get_json()
    assert b["created"] is False and b["user"]["id"] == s["user"]["id"]
    assert n(sql, "user_identities", "user_id=:u AND subject='link-sub'", u=s["user"]["id"]) == 1
    assert client.post("/auth/login", json={"email": email.lower(), "password": s["password"]}).status_code == 200


@pytest.mark.parametrize("email, extra", [
    ("link@example.com", {}),
    ("link@corp.example", {"hd": ""}),
    ("link@corp.example", {"hd": "   "}),
    ("link@corp.example", {"hd": None}),
    ("link@corp.example", {"hd": 5}),
    ("link@corp.example", {"hd": ["corp.example"]}),
    ("link@corp.example", {"hd": True}),
    # hd counts only when it equals the email domain (nit on PR 3, feat/requests-audiences)
    ("link@corp.example", {"hd": "anything"}),
    ("link@corp.example", {"hd": "other.example"}),
    ("link@corp.example", {"hd": "example"}),             # suffix of the domain
    ("link@corp.example", {"hd": "evil-corp.example"}),
    ("link@corp.example", {"hd": "corp.example.evil"}),
    ("link@sub.corp.example", {"hd": "corp.example"}),    # parent domain is not equal
    ("link@corp.example", {"hd": "sub.corp.example"}),
    ("link@corp.example", {"hd": "gmail.com"}),           # hd naming a consumer domain does not help
    ("link@gmail.com.evil.example", {}),
    ("link@notgmail.com", {}),
    ("link@mail.gmail.com", {}),
])
def test_link_refused_account_exists_use_password(client, sql, jwks, email, extra):
    s = _signup(client, email=email.lower())
    users_before = sql("SELECT * FROM users")
    e = err(post(client, tok(sub="nolink", email=email, **extra)), 409, "account_exists_use_password")
    assert "password" in e["error"]["message"].lower()
    assert sql("SELECT * FROM users") == users_before and n(sql, "user_identities") == 0
    assert client.post("/auth/login", json={"email": email.lower(), "password": s["password"]}).status_code == 200


@pytest.mark.parametrize("email, extra", [("brand@example.com", {}), ("brand@corp.example", {"hd": "corp.example"}),
                                          ("brand@gmail.com", {}), ("brand@googlemail.com", {}),
                                          ("brand@corp.example", {"hd": "other.example"})])
def test_new_email_any_domain_creates_201(client, jwks, email, extra):
    r = post(client, tok(email=email, **extra))
    assert r.status_code == 201 and r.get_json()["created"] is True


def test_same_sub_non_gmail_without_hd_still_signs_in(client, sql, jwks):
    a = post(client, tok(sub="w", email="w@corp.example", hd="corp.example")).get_json()
    r = post(client, tok(sub="w", email="w@corp.example"))  # no hd, non-gmail: identity path wins
    assert r.status_code == 200 and r.get_json()["user"]["id"] == a["user"]["id"]
    a2 = post(client, tok(sub="x", email="x@example.com")).get_json()  # created as non-gmail
    r = post(client, tok(sub="x", email="x@example.com"))
    assert r.status_code == 200 and r.get_json()["user"]["id"] == a2["user"]["id"]


def test_mismatched_hd_does_not_block_existing_identity(client, sql, jwks):
    """hd only gates *linking by email*: a known (provider, sub) signs in whatever hd says."""
    a = post(client, tok(sub="m", email="m@corp.example", hd="corp.example")).get_json()
    r = post(client, tok(sub="m", email="m@corp.example", hd="other.example"))
    assert r.status_code == 200 and r.get_json()["user"]["id"] == a["user"]["id"]
    assert n(sql, "user_identities") == 1


def test_mismatched_hd_refusal_then_matching_hd_links(client, sql, jwks):
    s = _signup(client, email="pat@corp.example")
    err(post(client, tok(sub="p", email="pat@corp.example", hd="corp.other")), 409, "account_exists_use_password")
    assert n(sql, "user_identities") == 0
    r = post(client, tok(sub="p", email="pat@corp.example", hd="Corp.Example"))
    assert r.status_code == 200 and r.get_json()["user"]["id"] == s["user"]["id"]
    assert n(sql, "user_identities", "user_id=:u", u=s["user"]["id"]) == 1


@pytest.mark.parametrize("ev", ["TRUE", " TRUE ", "tRuE"])
def test_email_verified_upper_true_links_consistently(client, sql, jwks, ev):
    """BE-16 (fixed): any-case/trimmed "true" passes verification, so it must link a gmail account too."""
    s = _signup(client, email="upper@gmail.com")
    r = post(client, tok(sub="up", email="upper@gmail.com", email_verified=ev))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["user"]["id"] == s["user"]["id"]


@pytest.mark.parametrize("over, expected", [
    ({"name": "  Pat   \t Doe  "}, "Pat Doe"),
    ({"name": DROP}, "Pat"),
    ({"name": "", "given_name": "Gee"}, "Gee"),
    ({"name": "   ", "given_name": DROP}, "pat"),
    ({"name": None, "given_name": 5}, "pat"),
    ({"name": "x" * 200}, "x" * 80),
    ({"name": DROP, "given_name": DROP, "email": ("y" * 100) + "@gmail.com"}, "y" * 80),
])
def test_display_name_fallbacks(client, jwks, over, expected):
    r = post(client, tok(**over))
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["user"]["display_name"] == expected


def test_email_lowercased_on_create(client, jwks):
    r = post(client, tok(email="  UPPER@Gmail.COM "))
    assert r.status_code == 201 and r.get_json()["user"]["email"] == "upper@gmail.com"


@pytest.mark.parametrize("ev", [True, "true", "True", "TRUE", " TRUE ", "\ttrue\n"])
def test_email_verified_true_forms(client, jwks, ev):
    assert post(client, tok(email_verified=ev)).status_code == 201


def test_second_allowed_audience(client, jwks):
    assert post(client, tok(aud=CID_B, azp=CID_B)).status_code == 201


@pytest.mark.parametrize("iss", ["accounts.google.com", "https://accounts.google.com"])
def test_both_issuers_pass(client, jwks, iss):
    assert post(client, tok(iss=iss)).status_code == 201


def test_leeway_within_60s_passes(client, jwks):
    now = int(time.time())
    assert post(client, tok(exp=now - 30, iat=now - 3600)).status_code == 201
    assert post(client, tok(iat=now + 30, sub="s2", email="s2@gmail.com")).status_code == 201


def test_whitespace_around_token_is_stripped(client, jwks):
    assert post(client, "  " + tok() + "\n").status_code == 201


# --------------------------------------------------------------------------------------------- rejections

def _no_rows(sql):
    assert n(sql, "users") == 0 and n(sql, "user_identities") == 0


def test_bad_signature(client, sql, jwks):
    err(post(client, tok(key=K_ROGUE, kid="k1")), 401, "invalid_token")
    t = tok()
    h, p, s = t.split(".")
    err(post(client, f"{h}.{p}.{s[:-4]}AAAA"), 401, "invalid_token")
    # payload swapped under a valid signature
    other = tok(sub="attacker").split(".")[1]
    err(post(client, f"{h}.{other}.{s}"), 401, "invalid_token")
    _no_rows(sql)


@pytest.mark.parametrize("kid", ["nope", "", None, 5, ["k1"]])
def test_wrong_or_missing_kid(client, sql, jwks, kid):
    if kid is None:
        t = jwt.encode(claims(), K1, algorithm="RS256")
    elif not isinstance(kid, str):  # PyJWT refuses to encode a non-string kid: sign it by hand
        signing = f"{_b64(json.dumps({'alg': 'RS256', 'typ': 'JWT', 'kid': kid}).encode())}.{_b64(json.dumps(claims()).encode())}"
        sig = K1.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
        t = f"{signing}.{_b64(sig)}"
    else:
        t = tok(kid=kid)
    err(post(client, t), 401, "invalid_token")
    _no_rows(sql)


def test_alg_none(client, sql, jwks):
    t = jwt.encode(claims(), None, algorithm="none", headers={"kid": "k1"})
    err(post(client, t), 401, "invalid_token")
    err(post(client, raw_token({"alg": "none", "kid": "k1", "typ": "JWT"}, claims())), 401, "invalid_token")
    err(post(client, raw_token({"alg": "None", "kid": "k1"}, claims())), 401, "invalid_token")
    _no_rows(sql)


def test_hs256_key_confusion(client, sql, jwks):
    pem = K1.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    for secret in (pem, json.dumps(_jwk(K1, "k1")).encode()):
        h = {"alg": "HS256", "kid": "k1", "typ": "JWT"}
        signing = f"{_b64(json.dumps(h).encode())}.{_b64(json.dumps(claims()).encode())}"
        sig = hmac.new(secret, signing.encode(), hashlib.sha256).digest()
        err(post(client, f"{signing}.{_b64(sig)}"), 401, "invalid_token")
    _no_rows(sql)


@pytest.mark.parametrize("alg", ["RS512", "PS256"])
def test_other_rsa_algs_rejected(client, jwks, alg):
    err(post(client, tok(alg=alg)), 401, "invalid_token")


@pytest.mark.parametrize("aud", ["wrong.apps.googleusercontent.com", "", CID_A.upper(), CID_A + " ", [], ["nope"]])
def test_wrong_aud(client, sql, jwks, aud):
    err(post(client, tok(aud=aud)), 401, "invalid_token")
    _no_rows(sql)


@pytest.mark.parametrize("iss", ["https://evil.example.com", "accounts.google.com.evil.com", "http://accounts.google.com",
                                 "https://accounts.google.com/", "ACCOUNTS.GOOGLE.COM", ""])
def test_wrong_iss(client, sql, jwks, iss):
    err(post(client, tok(iss=iss)), 401, "invalid_token")
    _no_rows(sql)


def test_expired_beyond_leeway(client, sql, jwks):
    now = int(time.time())
    err(post(client, tok(exp=now - 120, iat=now - 4000)), 401, "invalid_token")
    _no_rows(sql)


def test_issued_in_future_beyond_leeway(client, sql, jwks):
    now = int(time.time())
    err(post(client, tok(iat=now + 300, exp=now + 4000)), 401, "invalid_token")
    _no_rows(sql)


@pytest.mark.parametrize("missing", ["sub", "email", "exp", "iat", "iss", "aud"])
def test_missing_claims(client, sql, jwks, missing):
    err(post(client, tok(**{missing: DROP})), 401, "invalid_token")
    _no_rows(sql)


@pytest.mark.parametrize("over", [{"sub": ""}, {"sub": 123}, {"sub": None}, {"email": ""}, {"email": "no-at-sign"},
                                  {"email": 5}, {"email": None}, {"exp": "tomorrow"}, {"iat": "now"}])
def test_bad_claim_values(client, sql, jwks, over):
    err(post(client, tok(**over)), 401, "invalid_token")
    _no_rows(sql)


@pytest.mark.parametrize("ev", [False, "false", "False", "FALSE", 0, 1, None, "yes", "", DROP])
def test_email_not_verified(client, sql, jwks, ev):
    err(post(client, tok(email_verified=ev)), 403, "email_not_verified")
    _no_rows(sql)


def test_unverified_email_does_not_link_existing_account(client, sql, jwks):
    s = _signup(client, email="victim@x.com")
    err(post(client, tok(email="victim@x.com", email_verified="false")), 403, "email_not_verified")
    assert n(sql, "user_identities") == 0
    assert n(sql, "users") == 1 and s


@pytest.mark.parametrize("bad", ["abc", "a.b.c", "....", "a.b", "...", "eyJhbGciOiJSUzI1NiJ9", "x" * 20_000,
                                 "not a token at all", "Bearer " + "x.y.z", "éé.é.é"])
def test_malformed_tokens(client, sql, jwks, bad):
    err(post(client, bad), 401, "invalid_token")
    _no_rows(sql)


def test_header_not_an_object(client, jwks):
    t = f"{_b64(b'[1,2]')}.{_b64(json.dumps(claims()).encode())}.{_b64(b'sig')}"
    err(post(client, t), 401, "invalid_token")
    t = f"{_b64(b'not json')}.{_b64(json.dumps(claims()).encode())}.{_b64(b'sig')}"
    err(post(client, t), 401, "invalid_token")


def test_oversized_valid_token_rejected(client, jwks):
    t = tok(padding="p" * 17_000)
    err(post(client, t), 401, "invalid_token")


@pytest.mark.parametrize("kw", [
    {"data": ""},
    {"data": "not json", "content_type": "application/json"},
    {"data": "id_token=abc", "content_type": "application/x-www-form-urlencoded"},
    {"json": []},
    {"json": "a.b.c"},
    {"json": None},
    {"json": {}},
    {"json": {"token": "a.b.c"}},
    {"json": {"id_token": None}},
    {"json": {"id_token": 123}},
    {"json": {"id_token": ["a.b.c"]}},
    {"json": {"id_token": {"t": 1}}},
    {"json": {"id_token": True}},
    {"json": {"id_token": ""}},
    {"json": {"id_token": "   "}},
])
def test_bad_body_400(client, jwks, kw):
    err(client.post(URL, **kw), 400, "validation_error")
    assert jwks.calls == 0


def test_wrong_method(client, jwks):
    err(client.get(URL), 405, "method_not_allowed")


# --------------------------------------------------------------------------------------------- configuration

@pytest.mark.parametrize("value", ["", "  ", ",", " , , ", None])
def test_not_configured_503(app, client, monkeypatch, value):
    monkeypatch.setitem(app.config, "GOOGLE_IOS_CLIENT_IDS", value)
    fake = FakeJWKS()
    google_auth.set_fetcher(fake)
    # checked before the token is looked at: even a perfectly valid token or junk gives 503
    err(post(client, tok()), 503, "oauth_not_configured")
    err(post(client, "junk"), 503, "oauth_not_configured")
    assert fake.calls == 0


def test_config_list_form_and_single_id(app, client, monkeypatch, jwks):
    monkeypatch.setitem(app.config, "GOOGLE_IOS_CLIENT_IDS", CID_B)
    err(post(client, tok(aud=CID_A)), 401, "invalid_token")
    assert post(client, tok(aud=CID_B)).status_code == 201


# --------------------------------------------------------------------------------------------- JWKS cache

def test_jwks_fetched_once_and_cached(client, jwks):
    for i in range(6):
        assert post(client, tok(sub=f"s{i}", email=f"s{i}@gmail.com")).status_code == 201
    assert jwks.calls == 1


def test_cache_expires_after_max_age(client, jwks, clock):
    jwks.max_age = 100
    assert post(client, tok()).status_code == 201
    clock.t += 99
    assert post(client, tok()).status_code == 200 and jwks.calls == 1
    clock.t += 2
    assert post(client, tok()).status_code == 200 and jwks.calls == 2


def test_key_rotation_unknown_kid_refetches(client, jwks, clock):
    assert post(client, tok()).status_code == 201 and jwks.calls == 1
    jwks.keys = [_jwk(K1, "k1"), _jwk(K2, "k2")]
    clock.t += 31  # cache still fresh (max-age 3600), past the 30 s refetch floor
    r = post(client, tok(key=K2, kid="k2"))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert jwks.calls == 2
    # k2 now cached: no more fetches
    assert post(client, tok(key=K2, kid="k2")).status_code == 200 and jwks.calls == 2


def test_unknown_kid_refetch_rate_limited_30s(client, jwks, clock):
    """Contract: an unknown kid refetches at most once per 30 s, so junk kids cannot hammer Google."""
    assert post(client, tok()).status_code == 201
    jwks.keys = [_jwk(K1, "k1"), _jwk(K2, "k2")]
    clock.t += 5
    err(post(client, tok(key=K2, kid="k2")), 401, "invalid_token")  # inside the 30 s floor: no refetch
    assert jwks.calls == 1
    for i in range(20):
        err(post(client, tok(kid=f"junk{i}")), 401, "invalid_token")
    assert jwks.calls == 1
    clock.t += 30
    assert post(client, tok(key=K2, kid="k2")).status_code == 200 and jwks.calls == 2
    for i in range(20):
        err(post(client, tok(kid=f"junk{i}")), 401, "invalid_token")
    assert jwks.calls == 2


def test_rotated_out_key_rejected_after_refresh(client, jwks, clock):
    jwks.max_age = 60
    assert post(client, tok()).status_code == 201
    jwks.keys = [_jwk(K2, "k2")]
    clock.t += 61
    err(post(client, tok()), 401, "invalid_token")
    assert jwks.calls == 2


@pytest.mark.parametrize("exc", [requests.ConnectionError("down"), requests.Timeout("slow"),
                                 requests.HTTPError("500"), ValueError("bad json")])
def test_jwks_down_empty_cache_502(client, sql, jwks, exc):
    jwks.fail = exc
    err(post(client, tok()), 502, "upstream_unavailable")
    _no_rows(sql)


@pytest.mark.parametrize("payload", [{"keys": []}, {}, {"keys": [{"kty": "EC", "kid": "k1"}]},
                                     {"keys": [{"kty": "RSA", "kid": "k1", "n": "@@", "e": "AQAB"}]},
                                     {"keys": [{"kty": "RSA", "kid": "k1"}]}, {"keys": ["str", 5, None]},
                                     {"keys": "nope"}, [], "x", None])
def test_jwks_unusable_payload_502(client, jwks, payload):
    jwks.payload = payload if payload is not None else {}
    if payload is None:
        jwks.payload = None
        jwks.keys = []
    err(post(client, tok()), 502, "upstream_unavailable")


@pytest.mark.parametrize("payload", [{"keys": None}, {"keys": 5}])
def test_jwks_keys_not_a_list_is_clean_502(client, jwks, payload):
    """BE-15 (fixed): a JWKS body whose `keys` is null or a number must be a clean 502, not a 500."""
    jwks.payload = payload
    err(post(client, tok()), 502, "upstream_unavailable")


@pytest.mark.parametrize("kid", [5, None, ["k1"], {"k": 1}, 1.5, True])
def test_jwks_key_with_non_string_kid_is_unusable(client, jwks, kid):
    """BE-15 (fixed): a JWK whose kid is not a non-empty string is skipped; with nothing else usable -> 502."""
    jwks.keys = [dict(_jwk(K1, "k1"), kid=kid)]
    err(post(client, tok()), 502, "upstream_unavailable")


def test_jwks_non_string_kid_skipped_but_good_key_used(client, jwks):
    jwks.keys = [dict(_jwk(K2, "x"), kid=7), _jwk(K1, "k1")]
    assert post(client, tok()).status_code == 201


def test_jwks_no_usable_keys_with_stale_cache_keeps_cached(client, jwks, clock):
    jwks.max_age = 60
    assert post(client, tok()).status_code == 201
    jwks.payload = {"keys": None}
    clock.t += 120
    assert post(client, tok()).status_code == 200 and jwks.calls == 2


def test_jwks_keys_with_wrong_alg_or_use_ignored(client, jwks):
    jwks.keys = [dict(_jwk(K1, "k1"), alg="RS512"), dict(_jwk(K2, "k2"), use="enc")]
    err(post(client, tok()), 502, "upstream_unavailable")


def test_jwks_down_with_stale_cache_uses_cached_keys(client, jwks, clock):
    jwks.max_age = 60
    assert post(client, tok()).status_code == 201
    jwks.fail = requests.ConnectionError("down")
    clock.t += 120  # stale
    assert post(client, tok()).status_code == 200
    assert jwks.calls == 2  # it did try


def test_jwks_recovers_after_outage(client, jwks):
    jwks.fail = requests.ConnectionError("down")
    err(post(client, tok()), 502, "upstream_unavailable")
    jwks.fail = None
    assert post(client, tok()).status_code == 201


class _Resp:
    def __init__(self, status=200, body=None, headers=None, json_exc=None):
        self.status_code, self._body, self.headers, self._exc = status, body, headers or {}, json_exc

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        if self._exc:
            raise self._exc
        return self._body


@pytest.mark.parametrize("headers, expected", [
    ({"Cache-Control": "public, max-age=19800, must-revalidate, no-transform"}, 19800),
    ({"Cache-Control": "max-age=7"}, 7),
    ({}, 300),
    ({"Cache-Control": "no-store"}, 0),
    ({"Cache-Control": "no-cache, max-age=50"}, 0),
    ({"Cache-Control": "s-maxage=99"}, 300),
])
def test_real_fetcher_parses_cache_control(monkeypatch, headers, expected):
    seen = {}

    def fake_get(url, timeout=None, **kw):
        seen.update(url=url, timeout=timeout)
        return _Resp(body={"keys": [_jwk(K1, "k1")]}, headers=headers)

    monkeypatch.setattr(google_auth.requests, "get", fake_get)
    body, max_age = google_auth._http_fetch()
    assert max_age == expected and body["keys"][0]["kid"] == "k1"
    assert seen["url"] == "https://www.googleapis.com/oauth2/v3/certs" and seen["timeout"]


@pytest.mark.parametrize("resp", [
    _Resp(status=500, body={}),
    _Resp(status=404, body={}),
    _Resp(body=None, json_exc=requests.JSONDecodeError("x", "doc", 0)),
    _Resp(body=["not", "a", "dict"]),
])
def test_real_fetcher_failures_map_to_502(client, app, monkeypatch, resp):
    monkeypatch.setitem(app.config, "GOOGLE_IOS_CLIENT_IDS", CID_A)
    monkeypatch.setattr(google_auth.requests, "get", lambda *a, **k: resp)
    google_auth.set_fetcher(None)  # the real fetcher, with requests.get stubbed
    try:
        err(post(client, tok()), 502, "upstream_unavailable")
    finally:
        google_auth.clear_cache()


def test_real_fetcher_timeout_maps_to_502(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "GOOGLE_IOS_CLIENT_IDS", CID_A)

    def boom(*a, **k):
        raise requests.Timeout("slow")

    monkeypatch.setattr(google_auth.requests, "get", boom)
    google_auth.set_fetcher(None)
    try:
        err(post(client, tok()), 502, "upstream_unavailable")
    finally:
        google_auth.clear_cache()


# --------------------------------------------------------------------------------------------- uniqueness

def test_provider_subject_unique_in_db(app, client, sql, jwks):
    uid = post(client, tok(sub="dup")).get_json()["user"]["id"]
    other = _signup(client)["user"]["id"]
    with pytest.raises(IntegrityError):
        sql("INSERT INTO user_identities (provider, subject, user_id) VALUES ('google','dup',:u)", u=other)
    # same subject under another provider is fine (generic table)
    sql("INSERT INTO user_identities (provider, subject, user_id) VALUES ('other','dup',:u)", u=other)
    assert n(sql, "user_identities", "subject='dup'") == 2 and uid


def test_identity_cascades_with_user_fk(client, sql, jwks):
    uid = post(client, tok()).get_json()["user"]["id"]
    sql("DELETE FROM users WHERE id=:u", u=uid)
    assert n(sql, "user_identities") == 0


def _race(app, tokens, gate):
    """Run one POST per token in parallel threads, all held at the first statement matching `gate`."""
    k = len(tokens)
    barrier = threading.Barrier(k, timeout=10)
    hits = {"n": 0}
    lock = threading.Lock()

    def hold(conn, cur, stmt, params, ctx, many):
        if gate(stmt.lstrip().upper()):
            with lock:
                hits["n"] += 1
                mine = hits["n"] <= k
            if mine:
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass

    out = []

    def run(t):
        r = app.test_client().post(URL, json={"id_token": t})
        out.append((r.status_code, r.get_json()))

    with app.app_context():
        assert post(app.test_client(), tok(sub="warm", email="warm@gmail.com")).status_code == 201  # JWKS cached
        sa_event.listen(db.engine, "before_cursor_execute", hold)
    try:
        ts = [threading.Thread(target=run, args=(t,)) for t in tokens]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
    finally:
        with app.app_context():
            sa_event.remove(db.engine, "before_cursor_execute", hold)
    assert len(out) == k, out
    return out


@pytest.mark.parametrize("threads", [2, 4])
def test_concurrent_first_sign_in_resolves_to_one_user(app, sql, jwks, threads):
    """Simultaneous first sign-ins for one Google account: exactly one 201, the rest 200, one user, one identity."""
    out = _race(app, [tok(sub="race", email="race@gmail.com")] * threads,
                lambda st: st.startswith("INSERT INTO USERS"))
    codes = sorted(c for c, _ in out)
    assert codes == [200] * (threads - 1) + [201], out
    assert len({b["user"]["id"] for _, b in out}) == 1
    assert sorted(b["created"] for _, b in out) == [False] * (threads - 1) + [True]
    assert n(sql, "users", "email='race@gmail.com'") == 1
    assert n(sql, "user_identities", "subject='race'") == 1


def test_concurrent_link_different_subs_one_wins(app, client, sql, jwks):
    """4 different Google subs race to link one gmail password account: one 200, three identity_conflict."""
    s = _signup(client, email="target@gmail.com")
    out = _race(app, [tok(sub=f"racer{i}", email="target@gmail.com") for i in range(4)],
                lambda st: st.startswith("SELECT") and "FOR UPDATE" in st and "FROM USERS" in st)
    codes = sorted(c for c, _ in out)
    assert codes == [200, 409, 409, 409], out
    assert sorted(b["error"]["code"] for c, b in out if c == 409) == ["identity_conflict"] * 3
    assert [b["user"]["id"] for c, b in out if c == 200] == [s["user"]["id"]]
    assert n(sql, "user_identities", "user_id=:u", u=s["user"]["id"]) == 1
    assert n(sql, "users") == 2  # target + warm-up user


def test_concurrent_first_sign_in_different_subs_same_new_email(app, sql, jwks):
    """Two subs, same brand-new gmail address, at once: one creates (201), the other gets identity_conflict."""
    out = _race(app, [tok(sub="na", email="new@gmail.com"), tok(sub="nb", email="new@gmail.com")],
                lambda st: st.startswith("INSERT INTO USERS"))
    codes = sorted(c for c, _ in out)
    assert codes == [201, 409], out
    assert [b["error"]["code"] for c, b in out if c == 409] == ["identity_conflict"]
    assert n(sql, "users", "email='new@gmail.com'") == 1
    assert n(sql, "user_identities", "email='new@gmail.com'") == 1


# --------------------------------------------------------------------------------------------- email login / signup

def test_email_login_for_passwordless_user_401(client, jwks):
    post(client, tok(email="nopw@gmail.com"))
    wrong = client.post("/auth/login", json={"email": "nopw@x.com", "password": "whatever1"})
    for pw in ("", "whatever1", "!", None, "x" * 100):
        r = client.post("/auth/login", json={"email": "nopw@gmail.com", "password": pw})
        e = err(r, 401, "invalid_credentials")
        assert e["error"]["message"] == wrong.get_json()["error"]["message"]


def test_signup_with_oauth_email_is_409_not_500(client, jwks):
    post(client, tok(email="taken@gmail.com"))
    r = client.post("/auth/signup", json={"email": "TAKEN@gmail.com", "password": "pw12345678", "display_name": "X"})
    err(r, 409, "email_taken")


# --------------------------------------------------------------------------------------------- DELETE /auth/me

def test_delete_me_removes_identities_and_user(client, sql, jwks):
    a = post(client, tok(sub="del-1", email="del@gmail.com")).get_json()
    other = _signup(client, email="del2@gmail.com")
    post(client, tok(sub="del-2", email="del2@gmail.com"))  # another user's identity, must survive
    keep = post(client, tok(sub="keep", email="keep@gmail.com")).get_json()
    assert n(sql, "user_identities", "user_id=:u", u=a["user"]["id"]) == 1
    h = {"Authorization": f"Bearer {a['token']}"}
    assert client.delete("/auth/me", headers=h).status_code == 204
    assert n(sql, "users", "id=:u", u=a["user"]["id"]) == 0
    assert n(sql, "user_identities", "user_id=:u", u=a["user"]["id"]) == 0
    assert n(sql, "user_identities", "subject='del-1'") == 0
    assert n(sql, "user_identities", "user_id=:u", u=other["user"]["id"]) == 1
    assert n(sql, "user_identities", "user_id=:u", u=keep["user"]["id"]) == 1
    # old JWT is dead; Google sign-in again creates a fresh account
    err(client.get("/items", headers=h), 401, "unauthorized")
    r = post(client, tok(sub="del-1", email="del@gmail.com"))
    assert r.status_code == 201 and r.get_json()["created"] is True
    assert r.get_json()["user"]["id"] != a["user"]["id"]


def test_delete_me_linked_password_account(client, sql, jwks):
    s = _signup(client, email="both@gmail.com")
    assert post(client, tok(sub="both", email="both@gmail.com")).status_code == 200
    assert client.delete("/auth/me", headers=s["headers"]).status_code == 204
    assert n(sql, "user_identities") == 0 and n(sql, "users") == 0
    err(client.post("/auth/login", json={"email": "both@gmail.com", "password": s["password"]}), 401, "invalid_credentials")


@pytest.mark.parametrize("stmt_prefix", ["DELETE FROM USERS", "DELETE FROM USER_IDENTITIES"])
def test_delete_me_rolls_back_fully_on_failure(app, client, sql, jwks, make_item, stmt_prefix):
    a = post(client, tok(sub="atomic", email="atomic@gmail.com")).get_json()
    u = {"headers": {"Authorization": f"Bearer {a['token']}"}}
    make_item(u)
    uid = a["user"]["id"]

    def boom(conn, cur, stmt, params, ctx, many):
        if stmt.lstrip().upper().startswith(stmt_prefix):
            raise RuntimeError("boom")

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", boom)
        try:
            app.config["PROPAGATE_EXCEPTIONS"] = False
            r = app.test_client().delete("/auth/me", headers=u["headers"])
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", boom)
    err(r, 500, "internal_error")
    assert n(sql, "users", "id=:u", u=uid) == 1
    assert n(sql, "user_identities", "user_id=:u", u=uid) == 1
    assert n(sql, "items", "owner_id=:u", u=uid) == 1
    assert n(sql, "food_events", "user_id=:u", u=uid) >= 1
    assert post(client, tok(sub="atomic", email="atomic@gmail.com")).status_code == 200


# --------------------------------------------------------------------------------------------- N+1

def _count_queries(app, fn):
    seen = []

    def hook(conn, cur, stmt, params, ctx, many):
        seen.append(stmt)

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", hook)
    try:
        r = fn()
    finally:
        with app.app_context():
            sa_event.remove(db.engine, "before_cursor_execute", hook)
    return r, seen


def test_query_count_constant(app, client, jwks):
    post(client, tok(sub="q", email="q@gmail.com"))
    r, small = _count_queries(app, lambda: post(client, tok(sub="q", email="q@gmail.com")))
    assert r.status_code == 200
    # grow the tables and give this user many identities
    for i in range(30):
        post(client, tok(sub=f"bulk{i}", email=f"bulk{i}@gmail.com"))
    for i in range(10):  # rejected second identities must not make the happy path grow
        assert post(client, tok(sub=f"q-alt{i}", email="q@gmail.com")).status_code == 409
    r, big = _count_queries(app, lambda: post(client, tok(sub="q", email="q@gmail.com")))
    assert r.status_code == 200
    assert len(big) == len(small) <= 4, big
    # create and link paths are constant too
    _, c1 = _count_queries(app, lambda: post(client, tok(sub="new1", email="new1@gmail.com")))
    _, c2 = _count_queries(app, lambda: post(client, tok(sub="new2", email="new2@gmail.com")))
    assert len(c1) == len(c2) <= 6, c1
    s1, s2 = _signup(client, email="l1@gmail.com"), _signup(client, email="l2@gmail.com")
    r1, l1 = _count_queries(app, lambda: post(client, tok(sub="l1", email=s1["email"])))
    r2, l2 = _count_queries(app, lambda: post(client, tok(sub="l2", email=s2["email"])))
    assert r1.status_code == r2.status_code == 200
    assert len(l1) == len(l2) <= 6, l1
    assert uuid  # keep import
