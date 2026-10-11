"""Independent QA: POST /items/from-receipt fallback, `source` field and wall-clock budget. No real upstream call.

Claims under test (routes/items.py `_read_receipt`, `from_receipt`, `RECEIPT_CATEGORIZE_BUDGET_S`;
services/gemini.py `receipt_from_image`, `categorize_receipt_lines`, `_default_timeout`, `_generate`;
services/ml.py TIMEOUT; backend/entrypoint.sh gunicorn --timeout):
  1. ML unset / MLUnavailable -> Gemini vision, `source: "gemini"`; ML ok -> `source: "ocr"` and the Gemini reader is
     never called; both down -> 502 naming both reasons.
  2. `source` is on every 200 and no other response key was removed.
  3. One request stays under gunicorn's 120 s: a slow read skips categorization, a quick read keeps it, the SDK
     timeouts are 45 s (reader) and `_default_timeout()` (categorize), a hung call is a 502 / heuristic 200, never a 500.

Time is simulated: `items.time` and `gemini.time` are replaced by a fake clock whose `sleep` and whose stubbed
transport calls advance it. Nothing sleeps. Two layers, as in test_receipt_gemini_fallback.py (copied, not imported):
module-level Mock stubs for the route, and the real google-genai SDK + real services/ml.py over a stubbed
`requests.sessions.Session.request`. All cases inherit conftest's Postgres-backed `app` / `_clean` fixtures.
"""
import io
import json
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from app.routes import items as items_route
from app.services import gemini, ml

IMAGE = b"\xff\xd8receipt-timeout-sentinel-55102"
FAKE_KEY = "AIzaSy-FAKE-KEY-timeouts-sentinel"
MODEL = "gemini-test-model"
ML_URL = "http://ml.invalid"
GEMINI_HOST = "generativelanguage.googleapis.com"
RECEIPT = {"lines": [{"name": "GV WHL MILK GAL", "quantity": 2, "price": 3.48}], "total": 6.96}
ENRICHED = [{"display_name": "Whole milk", "category": "dairy", "food_group": "dairy", "storage": "fridge"}]
GUNICORN_TIMEOUT_S = 120
READER_TIMEOUT_S = 45.0
BACKEND = Path(__file__).resolve().parents[1]


def _img(data=IMAGE):
    return {"image": (io.BytesIO(data), "receipt.jpg", "image/jpeg")}


def _assert_error(response, status, code):
    assert response.status_code == status, response.get_data(as_text=True)
    error = response.get_json()["error"]
    assert error["code"] == code and error["message"]
    return error["message"]


class FakeClock:
    """Stands in for the `time` module inside routes/items.py and services/gemini.py."""

    def __init__(self):
        self.now = 1000.0
        self.start = self.now
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds):
        self.now += seconds

    @property
    def elapsed(self):
        return self.now - self.start


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network access: tests must stub every upstream")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def clock(monkeypatch):
    c = FakeClock()
    ns = SimpleNamespace(monotonic=c.monotonic, sleep=c.sleep)
    monkeypatch.setattr(items_route, "time", ns)
    monkeypatch.setattr(gemini, "time", ns)
    return c


# ---------------------------------------------------------------------------------------------
# Layer 1: module-level stubs (decision table, `source`, budget boundary)
# ---------------------------------------------------------------------------------------------
@pytest.fixture
def route(app, client, user, clock, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "")
    ocr = Mock(side_effect=AssertionError("ML must not run when unconfigured"))
    vision = Mock(return_value=RECEIPT)
    categorize = Mock(return_value=ENRICHED)
    configured = Mock(return_value=True)
    monkeypatch.setattr(ml, "ocr", ocr)
    monkeypatch.setattr(gemini, "is_configured", configured)
    monkeypatch.setattr(gemini, "receipt_from_image", vision)
    monkeypatch.setattr(gemini, "categorize_receipt_lines", categorize)
    monkeypatch.setattr(gemini, "_generate", Mock(side_effect=AssertionError("unstubbed Gemini call")))

    def post():
        return client.post("/items/from-receipt", data=_img(), headers=user["headers"],
                           content_type="multipart/form-data")

    def enable_ml(seconds=0.0, fails=False, reason="test ML unavailable"):
        monkeypatch.setitem(app.config, "ML_SERVICE_URL", ML_URL)

        def run(*a, **k):
            clock.advance(seconds)
            if fails:
                raise ml.MLUnavailable(reason)
            return RECEIPT

        ocr.side_effect = run

    def slow(mock, seconds, result=None, exc=None):
        """Make a stub take `seconds` of simulated time, then return or raise."""
        def run(*a, **k):
            clock.advance(seconds)
            if exc is not None:
                raise exc
            return result if result is not None else mock.return_value

        mock.side_effect = run

    return SimpleNamespace(post=post, enable_ml=enable_ml, slow=slow, ocr=ocr, vision=vision, categorize=categorize,
                           configured=configured)


# ---- (1) decision table -------------------------------------------------------------------------
def test_ml_unset_uses_gemini_reader_and_source_gemini(route):
    body = route.post().get_json()
    assert body["source"] == "gemini"
    route.ocr.assert_not_called()
    route.vision.assert_called_once_with(IMAGE, "image/jpeg", retry=True)


def test_ml_unavailable_falls_back_to_gemini_reader(route):
    route.enable_ml(fails=True)
    response = route.post()
    assert response.status_code == 200 and response.get_json()["source"] == "gemini"
    route.ocr.assert_called_once()
    route.vision.assert_called_once()


def test_ml_success_is_source_ocr_and_never_calls_the_gemini_reader(route):
    route.vision.side_effect = AssertionError("the Gemini reader must not run when ML answered")
    route.enable_ml()
    response = route.post()
    assert response.status_code == 200 and response.get_json()["source"] == "ocr"
    route.vision.assert_not_called()


@pytest.mark.parametrize("ml_configured", [False, True], ids=["ml-unset", "ml-down"])
def test_both_unavailable_is_502_naming_both_reasons(route, ml_configured):
    if ml_configured:
        route.enable_ml(fails=True, reason="ML-REASON-xyz")
    route.vision.side_effect = gemini.UpstreamError("GEMINI-REASON-xyz")
    message = _assert_error(route.post(), 502, "upstream_unavailable")
    assert "GEMINI-REASON-xyz" in message
    assert ("ML-REASON-xyz" in message) if ml_configured else ("ML service is not configured" in message)


def test_both_unavailable_gemini_unconfigured_names_both(route):
    route.configured.return_value = False
    route.enable_ml(fails=True, reason="ML-REASON-abc")
    message = _assert_error(route.post(), 502, "upstream_unavailable")
    assert "ML-REASON-abc" in message and "Gemini is not configured" in message
    route.vision.assert_not_called()


# ---- (2) `source` on every 200, no key removed ---------------------------------------------------
KEYS = {"candidates", "total", "categorized_by", "source"}


@pytest.mark.parametrize("scenario", [
    "gemini-categorized", "ocr-categorized", "empty-lines", "noise-only", "categorize-fails", "categorize-skipped-slow",
    "ml-down-gemini"])
def test_every_200_has_source_and_the_documented_keys(route, scenario):
    expected = "gemini"
    if scenario == "ocr-categorized":
        route.enable_ml()
        expected = "ocr"
    elif scenario == "empty-lines":
        route.vision.return_value = {"lines": [], "total": None}
    elif scenario == "noise-only":
        route.vision.return_value = {"lines": [{"name": "TOTAL", "price": 1.0}], "total": 1.0}
    elif scenario == "categorize-fails":
        route.categorize.side_effect = gemini.UpstreamError("x")
    elif scenario == "categorize-skipped-slow":
        route.slow(route.vision, 91.0, RECEIPT)
    elif scenario == "ml-down-gemini":
        route.enable_ml(fails=True)
    response = route.post()
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == KEYS, f"keys changed: {set(body) ^ KEYS}"
    assert body["source"] == expected
    assert body["categorized_by"] in ("gemini", "heuristic")
    assert isinstance(body["candidates"], list)


def test_documented_response_keys_in_api_md_match_the_route():
    api = (BACKEND.parent / "docs" / "API.md").read_text(encoding="utf-8")
    section = api[api.index("POST /items/from-receipt"):][:600]
    for key in ("candidates", "total", "categorized_by", "source"):
        assert key in section


# ---- (3) budget: fake clock, module stubs --------------------------------------------------------
def test_budget_constant_and_arithmetic_with_the_real_constants():
    assert items_route.RECEIPT_CATEGORIZE_BUDGET_S == 40
    assert ml.TIMEOUT == 60
    assert gemini.RETRY_DELAYS_S == (1.5,)
    retry_gap = sum(gemini.RETRY_DELAYS_S)
    worst_read = 2 * READER_TIMEOUT_S + retry_gap  # two 45 s attempts and the pause
    assert worst_read == 91.5
    worst_categorize = 2 * 30.0 + retry_gap  # default GEMINI_TIMEOUT_S
    assert worst_categorize == 61.5
    # the route's own invariant: categorize only starts when the read finished within the budget
    assert items_route.RECEIPT_CATEGORIZE_BUDGET_S + worst_categorize < GUNICORN_TIMEOUT_S  # 101.5
    assert worst_read < GUNICORN_TIMEOUT_S  # Gemini-only path, ML unset


def test_gunicorn_timeout_is_120_in_entrypoint():
    text = (BACKEND / "entrypoint.sh").read_text(encoding="utf-8")
    assert "--timeout 120" in text


def test_ml_timeout_plus_single_gemini_read_fits_under_gunicorn():
    """BE-31 fix: after a failed ML call the reader runs once (retry=False): 60 + 45 s < 120 s."""
    assert ml.TIMEOUT + READER_TIMEOUT_S < GUNICORN_TIMEOUT_S


def test_ml_down_after_60s_then_plain_gemini_read_timeout_fits(route, clock):
    """The non-retried failure (a plain read timeout) after an ML timeout: 60 + 45 = 105 s < 120."""
    route.enable_ml(seconds=ml.TIMEOUT, fails=True)
    route.slow(route.vision, READER_TIMEOUT_S, exc=gemini.UpstreamError("Gemini request failed: Timeout"))
    _assert_error(route.post(), 502, "upstream_unavailable")
    assert clock.elapsed == 105.0 < GUNICORN_TIMEOUT_S
    route.categorize.assert_not_called()


@pytest.mark.parametrize("read_s,called", [(0, True), (10, True), (39.999, True), (40.0, True), (40.001, False),
                                            (45.0, False), (91.0, False), (91.5, False)])
def test_categorize_runs_only_if_read_finished_within_budget(route, clock, read_s, called):
    route.slow(route.vision, read_s, RECEIPT)
    response = route.post()
    assert response.status_code == 200
    body = response.get_json()
    assert route.categorize.called is called
    assert body["categorized_by"] == ("gemini" if called else "heuristic")
    assert body["source"] == "gemini" and len(body["candidates"]) == 1
    if not called:  # heuristic keeps the printed name and still classifies
        c = body["candidates"][0]
        assert c["name"] == "GV WHL MILK GAL" and c["food_group"] == "dairy" and c["predicted_expiry"]


def test_slow_91s_read_skips_categorize_and_returns_heuristic_200(route, clock):
    route.slow(route.vision, 91.0, RECEIPT)
    response = route.post()
    assert response.status_code == 200
    assert response.get_json()["categorized_by"] == "heuristic"
    route.categorize.assert_not_called()
    assert clock.elapsed == 91.0 < GUNICORN_TIMEOUT_S


def test_10s_read_still_calls_categorize(route, clock):
    route.slow(route.vision, 10.0, RECEIPT)
    response = route.post()
    assert response.get_json()["categorized_by"] == "gemini"
    route.categorize.assert_called_once_with(["GV WHL MILK GAL"])


def test_ml_time_counts_toward_the_budget(route, clock):
    """`started` is taken before the ML call, so a slow ML + quick Gemini read also skips categorize."""
    route.enable_ml(seconds=35.0, fails=True)
    route.slow(route.vision, 6.0, RECEIPT)  # 35 + 6 = 41 > 40
    body = route.post().get_json()
    assert body["categorized_by"] == "heuristic" and body["source"] == "gemini"
    route.categorize.assert_not_called()


def test_slow_ml_success_over_budget_skips_categorize_with_source_ocr(route, clock):
    route.enable_ml(seconds=41.0)
    body = route.post().get_json()
    assert body["source"] == "ocr" and body["categorized_by"] == "heuristic"
    route.categorize.assert_not_called()


def test_categorize_hang_is_heuristic_200_never_500(route, clock):
    route.slow(route.categorize, 30.0, exc=gemini.UpstreamError("Gemini request failed: Timeout"))
    response = route.post()
    assert response.status_code == 200
    assert response.get_json()["categorized_by"] == "heuristic"


# ---------------------------------------------------------------------------------------------
# Layer 2: real SDK + real services/ml.py over a fake transport; fake clock advanced by the transport
# ---------------------------------------------------------------------------------------------
def _response(status=200, body=None, reason="OK"):
    r = requests.Response()
    r.status_code, r.reason, r.url = status, reason, "http://stub.invalid"
    r._content = json.dumps(body).encode()
    r.headers["Content-Type"] = "application/json"
    return r


def _reply(payload):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(payload)}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2}}


@pytest.fixture
def net(app, client, user, clock, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setitem(app.config, "GEMINI_MODEL", MODEL)
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "")
    n = SimpleNamespace(calls=[], queue=[], ml_calls=[], ml_queue=[])

    def request(self, method=None, url=None, **kw):
        if GEMINI_HOST in url:
            body = json.loads(kw["data"])
            is_read = any("inlineData" in p for c in body["contents"] for p in c["parts"])
            n.calls.append(SimpleNamespace(kind="read" if is_read else "categorize", timeout=kw.get("timeout"),
                                           at=clock.elapsed))
            queue = n.queue
        elif url.startswith(ML_URL):
            n.ml_calls.append(SimpleNamespace(timeout=kw.get("timeout"), at=clock.elapsed))
            queue = n.ml_queue
        else:
            pytest.fail(f"unexpected HTTP call to {url}")
        if not queue:
            pytest.fail(f"unexpected upstream call to {url}: no reply queued")
        return queue.pop(0)()

    monkeypatch.setattr(requests.sessions.Session, "request", request)

    def step(seconds, payload=None, status=None, exc=None):
        def run():
            clock.advance(seconds)
            if exc is not None:
                raise exc
            if status:
                return _response(status, {"error": {"code": status, "status": {429: "RESOURCE_EXHAUSTED",
                                                                                503: "UNAVAILABLE",
                                                                                504: "DEADLINE_EXCEEDED"}.get(status, "BAD"),
                                                    "message": "stub"}}, reason="stub")
            return _response(body=_reply(payload))

        return run

    n.step = step
    n.gemini = lambda *a, **k: n.queue.append(step(*a, **k))
    n.ml = lambda *a, **k: n.ml_queue.append(step(*a, **k))
    n.ml_ok = lambda seconds, payload: n.ml_queue.append(
        lambda: (clock.advance(seconds), _response(body=payload))[1])
    n.enable_ml = lambda: monkeypatch.setitem(app.config, "ML_SERVICE_URL", ML_URL)
    n.post = lambda: client.post("/items/from-receipt", data=_img(), headers=user["headers"],
                                 content_type="multipart/form-data")
    return n


def test_sdk_reader_timeout_is_45s_and_categorize_uses_default_timeout(net):
    net.gemini(2.0, RECEIPT)
    net.gemini(2.0, ENRICHED)
    body = net.post().get_json()
    assert body["categorized_by"] == "gemini"
    assert [(c.kind, c.timeout) for c in net.calls] == [("read", 45.0), ("categorize", 30.0)]


def test_categorize_timeout_follows_gemini_timeout_s_reader_stays_45(net, app, monkeypatch):
    monkeypatch.setitem(app.config, "GEMINI_TIMEOUT_S", 12)
    net.gemini(1.0, RECEIPT)
    net.gemini(1.0, ENRICHED)
    net.post()
    assert [(c.kind, c.timeout) for c in net.calls] == [("read", 45.0), ("categorize", 12.0)]
    with app.app_context():
        assert gemini._default_timeout() == 12.0


@pytest.mark.parametrize("value", [None, "", "abc", 0, -5, float("inf"), float("nan")])
def test_default_timeout_falls_back_to_30(app, monkeypatch, value):
    monkeypatch.setitem(app.config, "GEMINI_TIMEOUT_S", value)
    with app.app_context():
        assert gemini._default_timeout() == 30.0


def test_ml_request_timeout_is_60(net):
    net.enable_ml()
    net.ml_ok(1.0, RECEIPT)
    net.gemini(1.0, ENRICHED)
    body = net.post().get_json()
    assert body["source"] == "ocr"
    assert net.ml_calls[0].timeout == 60 == ml.TIMEOUT
    assert [c.kind for c in net.calls] == ["categorize"]  # no reader call after an ML success


@pytest.mark.parametrize("status", [429, 503])
def test_transient_reader_retries_once_after_1_5s(net, clock, status):
    net.gemini(0.5, status=status)
    net.gemini(3.0, RECEIPT)
    net.gemini(2.0, ENRICHED)
    body = net.post().get_json()
    assert body["source"] == "gemini" and body["categorized_by"] == "gemini"
    assert [c.kind for c in net.calls] == ["read", "read", "categorize"]
    assert clock.sleeps == [1.5]
    assert all(c.timeout == 45.0 for c in net.calls[:2])


def test_worst_case_reader_two_45s_attempts_then_success_is_91_5s_and_skips_categorize(net, clock):
    net.gemini(45.0, status=504)
    net.gemini(45.0, RECEIPT)
    response = net.post()
    assert response.status_code == 200
    body = response.get_json()
    assert body["source"] == "gemini" and body["categorized_by"] == "heuristic"
    assert [c.kind for c in net.calls] == ["read", "read"]  # no categorize call
    assert clock.elapsed == 91.5 < GUNICORN_TIMEOUT_S


def test_reader_504_twice_is_502_after_91_5s(net, clock):
    net.gemini(45.0, status=504)
    net.gemini(45.0, status=504)
    message = _assert_error(net.post(), 502, "upstream_unavailable")
    assert "ML service is not configured" in message and "Gemini request failed" in message
    assert clock.elapsed == 91.5


def test_worst_case_quick_read_then_slow_categorize_stays_under_120(net, clock):
    """Read just inside the budget (40 s), categorize 504 twice (2 x 30 s + 1.5 s): 101.5 s total."""
    net.gemini(40.0, RECEIPT)
    net.gemini(30.0, status=504)
    net.gemini(30.0, status=504)
    response = net.post()
    assert response.status_code == 200
    assert response.get_json()["categorized_by"] == "heuristic"
    assert [c.kind for c in net.calls] == ["read", "categorize", "categorize"]
    assert [c.timeout for c in net.calls] == [45.0, 30.0, 30.0]
    assert clock.elapsed == 101.5 < GUNICORN_TIMEOUT_S


def test_read_just_over_budget_skips_categorize_through_the_real_sdk(net, clock):
    net.gemini(40.5, RECEIPT)
    body = net.post().get_json()
    assert body["categorized_by"] == "heuristic"
    assert [c.kind for c in net.calls] == ["read"]


TIMEOUT_EXCEPTIONS = [requests.Timeout("t"), requests.ReadTimeout("t"), requests.ConnectTimeout("t"),
                      TimeoutError("t")]
TIMEOUT_IDS = ["Timeout", "ReadTimeout", "ConnectTimeout", "TimeoutError"]


@pytest.mark.parametrize("exc", TIMEOUT_EXCEPTIONS, ids=TIMEOUT_IDS)
def test_hanging_reader_ml_unset_is_502_never_500_and_not_retried(net, clock, exc):
    net.gemini(45.0, exc=exc)
    message = _assert_error(net.post(), 502, "upstream_unavailable")
    assert "Gemini request failed" in message
    assert [c.kind for c in net.calls] == ["read"]
    assert clock.elapsed == 45.0


@pytest.mark.parametrize("exc", TIMEOUT_EXCEPTIONS, ids=TIMEOUT_IDS)
def test_hanging_reader_after_ml_timeout_is_502_in_105s(net, clock, exc):
    net.enable_ml()
    net.ml(60.0, exc=requests.ReadTimeout("ml hung"))
    net.gemini(45.0, exc=exc)
    message = _assert_error(net.post(), 502, "upstream_unavailable")
    assert "ML service request failed: ReadTimeout" in message and "Gemini request failed" in message
    assert clock.elapsed == 105.0 < GUNICORN_TIMEOUT_S


@pytest.mark.parametrize("exc", TIMEOUT_EXCEPTIONS, ids=TIMEOUT_IDS)
def test_hanging_categorize_is_heuristic_200_never_500(net, clock, exc):
    net.gemini(3.0, RECEIPT)
    net.gemini(30.0, exc=exc)
    response = net.post()
    assert response.status_code == 200
    assert response.get_json()["categorized_by"] == "heuristic"
    assert [c.kind for c in net.calls] == ["read", "categorize"]  # a timeout is not retried
    assert clock.elapsed == 33.0


def test_ml_down_60s_then_slow_gemini_read_total_stays_under_120(net, clock):
    """BE-31 fix: no retry after a failed ML call, so 60 + 45 = 105 s and the answer is a 502."""
    net.enable_ml()
    net.ml(60.0, exc=requests.ReadTimeout("ml hung"))
    net.gemini(45.0, status=504)
    net.gemini(45.0, RECEIPT)
    response = net.post()
    assert response.status_code == 502
    assert clock.elapsed < GUNICORN_TIMEOUT_S, f"{clock.elapsed} s"
