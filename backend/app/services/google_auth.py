"""Google ID-token verification (Sign in with Google on iOS).

The token is verified locally against Google's JWKS: RS256 signature, `aud` in the configured iOS
client ids, `iss`, `exp`/`iat` (small leeway) and `email_verified`. Keys are cached in-process for the
`Cache-Control: max-age` Google sends (default 5 min if absent); an unknown `kid` forces one refetch,
rate-limited so a stream of junk tokens can't hammer Google.

Tests stub the network with `set_fetcher(fn)` (fn() -> (jwks_dict, max_age_seconds)) and reset the
cache with `clear_cache()`.
"""
import json
import re
import threading
import time

import jwt
import requests
from flask import current_app

JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
LEEWAY_S = 60
DEFAULT_MAX_AGE_S = 300
MIN_REFETCH_INTERVAL_S = 30
TIMEOUT_S = 5
MAX_TOKEN_LEN = 16_384


class GoogleAuthNotConfigured(Exception):
    """GOOGLE_IOS_CLIENT_IDS is empty."""


class GoogleAuthUnavailable(Exception):
    """Google's JWKS could not be fetched and nothing usable is cached."""


class InvalidGoogleToken(Exception):
    """Malformed, badly signed, expired, wrong audience/issuer, or missing claims."""


class EmailNotVerified(Exception):
    """The token is valid but Google says the email is not verified."""


_lock = threading.Lock()
_cache = {"keys": {}, "expires_at": 0.0, "last_fetch": 0.0}
_MAX_AGE = re.compile(r"(?:^|,)\s*max-age\s*=\s*(\d+)", re.I)


def _http_fetch():
    r = requests.get(JWKS_URL, timeout=TIMEOUT_S)
    r.raise_for_status()
    cc = r.headers.get("Cache-Control", "")
    m = _MAX_AGE.search(cc)
    if "no-store" in cc.lower() or "no-cache" in cc.lower():
        max_age = 0
    else:
        max_age = int(m.group(1)) if m else DEFAULT_MAX_AGE_S
    return r.json(), max_age


_fetcher = _http_fetch


def set_fetcher(fn):
    """Replace the JWKS fetcher (tests). `fn()` returns `(jwks_dict, max_age_seconds)`."""
    global _fetcher
    _fetcher = fn or _http_fetch
    clear_cache()


def clear_cache():
    with _lock:
        _cache.update(keys={}, expires_at=0.0, last_fetch=0.0)


def client_ids() -> list[str]:
    raw = current_app.config.get("GOOGLE_IOS_CLIENT_IDS") or ""
    if isinstance(raw, (list, tuple)):
        parts = raw
    else:
        parts = str(raw).split(",")
    return [p.strip() for p in parts if isinstance(p, str) and p.strip()]


def is_configured() -> bool:
    return bool(client_ids())


def email_verified(claims) -> bool:
    """Google's `email_verified`: bool True, or the string "true" in any case. Anything else is False."""
    v = claims.get("email_verified")
    return v is True or (isinstance(v, str) and v.strip().lower() == "true")


def _parse_jwks(jwks) -> dict:
    """{kid: public key}. A malformed document (non-dict, `keys` not a list, junk entries) yields {}."""
    keys = {}
    entries = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(entries, list):
        return keys
    for jwk in entries:
        if not isinstance(jwk, dict) or jwk.get("kty") != "RSA" or not isinstance(jwk.get("kid"), str):
            continue
        if jwk.get("alg") not in (None, "RS256") or jwk.get("use") not in (None, "sig"):
            continue
        try:
            keys[jwk["kid"]] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        except (ValueError, TypeError, KeyError, jwt.PyJWTError):
            continue
    return keys


def _refresh_locked(now):
    _cache["last_fetch"] = now
    try:
        jwks, max_age = _fetcher()
    except (requests.RequestException, ValueError) as e:
        raise GoogleAuthUnavailable(f"Google JWKS fetch failed: {type(e).__name__}") from e
    keys = _parse_jwks(jwks)
    if not keys:
        raise GoogleAuthUnavailable("Google JWKS contained no usable RSA keys.")
    _cache["keys"] = keys
    _cache["expires_at"] = now + max(0, int(max_age))


def _key_for(kid: str):
    with _lock:
        now = time.monotonic()
        fresh = now < _cache["expires_at"]
        # Stale keys are refetched; after a failed fetch, wait MIN_REFETCH_INTERVAL_S before retrying.
        if not fresh and (not _cache["keys"] or now - _cache["last_fetch"] >= MIN_REFETCH_INTERVAL_S):
            try:
                _refresh_locked(now)
            except GoogleAuthUnavailable:
                if not _cache["keys"]:
                    raise
                # Google unreachable but we still hold keys: keep using them.
        key = _cache["keys"].get(kid)
        if key is None and fresh and now - _cache["last_fetch"] >= MIN_REFETCH_INTERVAL_S:
            # Key rotation: an unseen kid forces one early refetch.
            try:
                _refresh_locked(now)
            except GoogleAuthUnavailable:
                pass
            key = _cache["keys"].get(kid)
        return key


def verify_id_token(id_token: str) -> dict:
    """Return the verified claims (`sub`, `email` lowercased, `name`, `given_name`, ...)."""
    audiences = client_ids()
    if not audiences:
        raise GoogleAuthNotConfigured("GOOGLE_IOS_CLIENT_IDS is not set.")
    if not isinstance(id_token, str) or not id_token or len(id_token) > MAX_TOKEN_LEN:
        raise InvalidGoogleToken("Malformed token.")
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as e:
        raise InvalidGoogleToken("Malformed token.") from e
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise InvalidGoogleToken("Unsupported token header.")
    key = _key_for(header["kid"])
    if key is None:
        raise InvalidGoogleToken("Unknown signing key.")
    try:
        claims = jwt.decode(
            id_token, key, algorithms=["RS256"], audience=audiences, issuer=list(ISSUERS),
            leeway=LEEWAY_S, options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise InvalidGoogleToken(f"Token rejected: {type(e).__name__}") from e
    sub, email = claims.get("sub"), claims.get("email")
    if not isinstance(sub, str) or not sub or not isinstance(email, str) or "@" not in email:
        raise InvalidGoogleToken("Token is missing sub or email.")
    if not email_verified(claims):
        raise EmailNotVerified("Google account email is not verified.")
    claims["email"] = email.strip().lower()
    return claims
