"""chore/gunicorn-gthread: module-level state shared by request threads under `--worker-class gthread`.

- recipe_cache: get/put/invalidate/clear from many threads; no exceptions, no cross-user leaks, LRU bound
  held, and exactly one hit/miss log line per get that agrees with what get returned.
- google_auth JWKS cache: concurrent verifies during cold / stale / rotation refetches do one fetch per
  throttle window (stubbed fetcher, frozen clock).
- gemini._generate: concurrent calls with a stubbed genai client log exactly one intact usage line each.
"""
import io
import json
import logging
import random
import re
import sys
import threading
import time
from collections import Counter
from types import SimpleNamespace

import jwt
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services import gemini, google_auth, recipe_cache


@pytest.fixture(autouse=True)
def _tight_switching():
    """Switch threads far more often than the default 5 ms so races get a chance to show."""
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    yield
    sys.setswitchinterval(old)


def run_threads(n, target, *args):
    """Run target(i, *args) on n threads released together; re-raise the first exception."""
    barrier = threading.Barrier(n)
    errors = []

    def wrap(i):
        try:
            barrier.wait(timeout=10)
            target(i, *args)
        except BaseException as e:  # noqa: BLE001  (surfaced below)
            errors.append(e)

    ts = [threading.Thread(target=wrap, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in ts), "thread hung"
    if errors:
        raise errors[0]


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


# ============================================================================================ recipe cache
CACHE_LINE = re.compile(r"^recipes_cache status=(hit age_s=\d+|miss reason=(empty|items_changed|expired))$")


@pytest.fixture
def cache_log(app, monkeypatch):
    monkeypatch.setitem(app.config, "RECIPE_CACHE_TTL_SECONDS", 3600)
    h = ListHandler()
    monkeypatch.setattr(recipe_cache.log, "handlers", [h])  # propagate=False: caplog can't see it
    return h.messages


def _recipes(uid, v):
    return [{"title": f"r-{uid}-{v}", "owner": uid, "v": v}]


def _key(uid, v):
    return f"key-{uid}-{v}"


def test_recipe_cache_contention_no_leaks_and_logs_agree(app, cache_log):
    """16 threads x 3 own users each; MAX_USERS (1000) never reached, so behaviour is exact."""
    n_threads, per_thread, ops = 16, 3, 300
    gets = Counter()

    def worker(i):
        rnd = random.Random(i)
        mine = [f"u{i}-{j}" for j in range(per_thread)]
        version = {u: 0 for u in mine}
        stored = {u: None for u in mine}  # version currently cached, None = nothing
        local = Counter()
        with app.app_context():
            for _ in range(ops):
                u = rnd.choice(mine)
                op = rnd.random()
                if op < 0.35:
                    recipe_cache.put(u, _key(u, version[u]), _recipes(u, version[u]))
                    stored[u] = version[u]
                    got = recipe_cache.get(u, _key(u, version[u]))  # put-then-get: must hit
                    local["get"] += 1
                    assert got == _recipes(u, version[u]), (u, got)
                    local["hit"] += 1
                elif op < 0.5:  # invalidate: items changed -> new key, old entry must not be served
                    version[u] += 1
                    got = recipe_cache.get(u, _key(u, version[u]))
                    local["get"] += 1
                    assert got is None, (u, got)
                    local["miss"] += 1
                else:
                    got = recipe_cache.get(u, _key(u, version[u]))
                    local["get"] += 1
                    if stored[u] == version[u]:
                        assert got == _recipes(u, version[u]), (u, got)
                        local["hit"] += 1
                    else:
                        assert got is None, (u, got)
                        local["miss"] += 1
        with lock:
            gets.update(local)

    lock = threading.Lock()
    run_threads(n_threads, worker)

    assert all(CACHE_LINE.match(m) for m in cache_log), [m for m in cache_log if not CACHE_LINE.match(m)][:5]
    logged = Counter("hit" if "status=hit" in m else "miss" for m in cache_log)
    assert len(cache_log) == gets["get"] == n_threads * ops
    assert logged["hit"] == gets["hit"] and logged["miss"] == gets["miss"], (logged, gets)
    with app.app_context():
        assert len(recipe_cache._store()) <= n_threads * per_thread


def test_recipe_cache_lru_bound_and_concurrent_clear(app, cache_log, monkeypatch):
    """MAX_USERS=8 with 64 users plus a thread calling clear(): misses are allowed, wrong data is not."""
    monkeypatch.setattr(recipe_cache, "MAX_USERS", 8)
    stop = threading.Event()
    sizes, gets = [], Counter()
    lock = threading.Lock()

    def worker(i):
        if i == 0:  # clearer
            with app.app_context():
                while not stop.is_set():
                    recipe_cache.clear()
                    time.sleep(0.001)
            return
        if i == 1:  # observer: the bound holds at every lock-protected point we can see
            with app.app_context():
                while not stop.is_set():
                    with recipe_cache._lock:
                        sizes.append(len(recipe_cache._store()))
                    time.sleep(0.0005)
            return
        rnd = random.Random(i)
        mine = [f"w{i}-{j}" for j in range(4)]
        version = {u: 0 for u in mine}
        local = Counter()
        try:
            with app.app_context():
                for _ in range(400):
                    u = rnd.choice(mine)
                    if rnd.random() < 0.4:
                        recipe_cache.put(u, _key(u, version[u]), _recipes(u, version[u]))
                    elif rnd.random() < 0.2:
                        version[u] += 1
                    got = recipe_cache.get(u, _key(u, version[u]))
                    local["get"] += 1
                    if got is not None:  # evicted / cleared -> None is fine; anything else must be exact
                        assert got == _recipes(u, version[u]), (u, version[u], got)
                        local["hit"] += 1
        finally:
            with lock:
                gets.update(local)

    workers = 2 + 16

    def driver(i):
        try:
            worker(i)
        finally:
            if i >= 2:
                with lock:
                    driver.done += 1
                    if driver.done == workers - 2:
                        stop.set()

    driver.done = 0
    run_threads(workers, driver)

    assert sizes and max(sizes) <= 8, max(sizes or [None])
    with app.app_context():
        assert len(recipe_cache._store()) <= 8
    assert len(cache_log) == gets["get"]
    assert sum("status=hit" in m for m in cache_log) == gets["hit"]
    assert all(CACHE_LINE.match(m) for m in cache_log)


# ============================================================================================ JWKS cache
CID = "111-ios-a.apps.googleusercontent.com"
K1, K2 = (rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))


def _jwk(priv, kid):
    d = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    d.update(kid=kid, alg="RS256", use="sig")
    return d


def _tok(key, kid, sub="10769150350006150715"):
    now = int(time.time())
    c = {"iss": "https://accounts.google.com", "aud": CID, "sub": sub, "email": "pat@gmail.com",
         "email_verified": True, "iat": now, "exp": now + 3600}
    return jwt.encode(c, key, algorithm="RS256", headers={"kid": kid})


class SlowFetcher:
    """Counts calls; sleeps so concurrent callers overlap the fetch."""

    def __init__(self):
        self.keys = [_jwk(K1, "k1")]
        self.max_age = 3600
        self.fail = False
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.calls += 1
        time.sleep(0.15)
        if self.fail:
            raise requests.ConnectionError("down")
        return {"keys": list(self.keys)}, self.max_age


@pytest.fixture
def jw(app, monkeypatch):
    monkeypatch.setitem(app.config, "GOOGLE_IOS_CLIENT_IDS", CID)
    clock = SimpleNamespace(t=1_000_000.0)
    monkeypatch.setattr(google_auth, "time", SimpleNamespace(monotonic=lambda: clock.t))
    f = SlowFetcher()
    google_auth.set_fetcher(f)  # also clears the cache
    yield f, clock
    google_auth.clear_cache()


def _verify_all(app, n, token, expect=None):
    out = [None] * n

    def worker(i):
        with app.app_context():
            try:
                out[i] = google_auth.verify_id_token(token)["sub"]
            except google_auth.InvalidGoogleToken as e:
                out[i] = e
    run_threads(n, worker)
    if expect is not None:
        assert out == [expect] * n, out
    return out


def test_jwks_cold_concurrent_lookups_fetch_once(app, jw):
    f, _ = jw
    _verify_all(app, 8, _tok(K1, "k1"), expect="10769150350006150715")
    assert f.calls == 1


def test_jwks_stale_concurrent_refetch_once(app, jw):
    f, clock = jw
    _verify_all(app, 1, _tok(K1, "k1"), expect="10769150350006150715")
    clock.t += 3601  # past max-age
    _verify_all(app, 8, _tok(K1, "k1"), expect="10769150350006150715")
    assert f.calls == 2


def test_jwks_stale_and_google_down_uses_stale_keys_one_attempt(app, jw):
    f, clock = jw
    _verify_all(app, 1, _tok(K1, "k1"), expect="10769150350006150715")
    clock.t += 3601
    f.fail = True
    _verify_all(app, 8, _tok(K1, "k1"), expect="10769150350006150715")
    assert f.calls == 2  # one failed attempt; the rest wait out MIN_REFETCH_INTERVAL_S


def test_jwks_concurrent_unknown_kids_refetch_at_most_once_per_window(app, jw):
    f, clock = jw
    _verify_all(app, 1, _tok(K1, "k1"), expect="10769150350006150715")
    assert f.calls == 1

    # Rotation: k2 appears at Google; 8 concurrent k2 tokens -> exactly one early refetch, all verify.
    clock.t += google_auth.MIN_REFETCH_INTERVAL_S
    f.keys.append(_jwk(K2, "k2"))
    _verify_all(app, 8, _tok(K2, "k2"), expect="10769150350006150715")
    assert f.calls == 2

    # Junk kids within the same window: no refetch at all.
    out = _verify_all(app, 8, _tok(K2, "junk"))
    assert all(isinstance(o, google_auth.InvalidGoogleToken) for o in out), out
    assert f.calls == 2

    # Next window: a junk storm costs at most one refetch.
    clock.t += google_auth.MIN_REFETCH_INTERVAL_S
    out = _verify_all(app, 8, _tok(K2, "junk"))
    assert all(isinstance(o, google_auth.InvalidGoogleToken) for o in out), out
    assert f.calls == 3


# ============================================================================================ Gemini usage
USAGE_LINE = re.compile(
    r"^app\.gemini\.usage gemini_usage model=gemini-test-model purpose=t\d+ "
    r"(input_tokens=120 output_tokens=45 total_tokens=165 latency_ms=\d+ status=ok code=200"
    r"|input_tokens=null output_tokens=null total_tokens=null latency_ms=\d+ status=error code=null)$")


def test_concurrent_generate_one_intact_usage_line_per_call(app, monkeypatch):
    import google.genai as genai

    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "fake-key-for-tests")
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    usage = SimpleNamespace(prompt_token_count=120, candidates_token_count=45, total_token_count=165)

    class Models:
        def generate_content(self, *, model, contents, config):
            time.sleep(random.random() * 0.01)
            if "FAIL" in contents:
                raise ValueError("bad request")  # not transient: no retry, one error line
            return SimpleNamespace(text='[{"name": "Milk"}]', usage_metadata=usage)

    class Client:
        def __init__(self, api_key=None, **kw):
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)
    buf = io.StringIO()
    stream = logging.StreamHandler(buf)
    stream.setFormatter(logging.Formatter("%(name)s %(message)s"))
    monkeypatch.setattr(gemini.usage_log, "handlers", [stream])

    n_threads, calls = 16, 6
    results = Counter()
    lock = threading.Lock()

    def worker(i):
        local = Counter()
        with app.app_context():
            for k in range(calls):
                fail = (i + k) % 3 == 0
                try:
                    out = gemini._generate("FAIL" if fail else "ok", "hint", purpose=f"t{i}")
                    assert out == [{"name": "Milk"}]
                    local["ok", i] += 1
                except gemini.UpstreamError:
                    assert fail
                    local["error", i] += 1
        with lock:
            results.update(local)

    run_threads(n_threads, worker)

    lines = buf.getvalue().splitlines()
    assert len(lines) == n_threads * calls, len(lines)
    bad = [l for l in lines if not USAGE_LINE.match(l)]
    assert not bad, bad[:3]
    logged = Counter((re.search(r"status=(\w+)", l).group(1), int(re.search(r"purpose=t(\d+)", l).group(1)))
                     for l in lines)
    assert logged == results
