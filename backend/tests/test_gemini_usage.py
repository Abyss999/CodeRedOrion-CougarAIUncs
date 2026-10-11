"""BE-3: one INFO usage line per Gemini call, no prompt/response/user data/key; scripts/gemini_cost.py."""
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import gemini

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gemini_cost.py"
FAKE_KEY = "AIzaSy-FAKE-KEY-0123456789-sentinel"
SENTINEL = "SENTINEL-USER-STRING-xyzzy-4242"
RESP_SENTINEL = "RESPONSE-SENTINEL-plugh-777"
LOGGER = "app.gemini.usage"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def usage_records():
    """The logger sets propagate=False, so caplog cannot see it: attach our own handler."""
    lg = logging.getLogger(LOGGER)
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


def _install_fake(monkeypatch, *, text='[{"name": "Milk"}]', usage="default", raises=None):
    import google.genai as genai

    if usage == "default":
        usage = SimpleNamespace(prompt_token_count=120, candidates_token_count=45, total_token_count=165)

    class Models:
        def generate_content(self, **kw):
            if raises:
                raise raises
            return SimpleNamespace(text=text, usage_metadata=usage)

    class Client:
        def __init__(self, api_key=None, **kw):
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)


def _kv(record):
    return dict(re.findall(r"(\w+)=(\S+)", record.getMessage()))


def test_one_info_record_per_call_with_fields(gem, monkeypatch, usage_records):
    _install_fake(monkeypatch)
    assert gemini.parse_text(f"2 cartons of milk {SENTINEL}") == [{"name": "Milk"}]
    assert len(usage_records) == 1
    rec = usage_records[0]
    assert rec.name == LOGGER and rec.levelno == logging.INFO
    kv = _kv(rec)
    assert kv["model"] == "gemini-test-model"
    assert kv["input_tokens"] == "120" and kv["output_tokens"] == "45" and kv["total_tokens"] == "165"
    assert kv["status"] == "ok" and kv["latency_ms"].isdigit() and int(kv["latency_ms"]) >= 0
    assert kv["purpose"] == "parse_text"  # endpoint/purpose field


def test_record_is_leak_free(gem, monkeypatch, usage_records):
    _install_fake(monkeypatch, text=json.dumps([{"name": RESP_SENTINEL}]))
    gemini.parse_text(f"my private note {SENTINEL}")
    assert len(usage_records) == 1
    rec = usage_records[0]
    text = rec.getMessage() + " " + str(rec.args) + " " + str(rec.msg) + " " + json.dumps(rec.__dict__, default=str)
    for secret in (SENTINEL, RESP_SENTINEL, FAKE_KEY, "my private note", "Extract the grocery",
                   "Return JSON", "AIzaSy"):
        assert secret not in text, secret


def test_every_helper_logs_exactly_once_and_leak_free(gem, monkeypatch, usage_records):
    _install_fake(monkeypatch, text="[]")
    gemini.parse_text(SENTINEL)
    gemini.suggest_recipes([{"name": SENTINEL, "category": "dairy"}], 2, [SENTINEL])
    gemini.estimate_shelf_life([{"name": SENTINEL, "category": "dairy", "storage": "fridge"}])
    gemini.detect_from_image(b"\xff\xd8\xff" + SENTINEL.encode(), "image/jpeg", "single")
    assert len(usage_records) == 4
    purposes = [_kv(r)["purpose"] for r in usage_records]
    assert len(set(purposes)) == 4, purposes
    for r in usage_records:
        assert r.levelno == logging.INFO and r.name == LOGGER
        blob = r.getMessage() + json.dumps(r.__dict__, default=str)
        assert SENTINEL not in blob and FAKE_KEY not in blob


@pytest.mark.parametrize("usage", [None, SimpleNamespace(), SimpleNamespace(prompt_token_count=None,
                                   candidates_token_count=None, total_token_count=None)])
def test_missing_usage_metadata_gives_null_fields(gem, monkeypatch, usage_records, usage):
    _install_fake(monkeypatch, usage=usage)
    assert gemini.parse_text("milk") == [{"name": "Milk"}]  # no exception, result intact
    assert len(usage_records) == 1
    kv = _kv(usage_records[0])
    assert kv["input_tokens"] == kv["output_tokens"] == kv["total_tokens"] == "null"
    assert kv["status"] == "ok"


def test_response_object_without_usage_attribute(gem, monkeypatch, usage_records):
    import google.genai as genai

    class Models:
        def generate_content(self, **kw):
            return SimpleNamespace(text="[]")  # no usage_metadata attribute at all

    monkeypatch.setattr(genai, "Client", lambda api_key=None, **k: SimpleNamespace(models=Models()))
    assert gemini.parse_text("x") == []
    assert len(usage_records) == 1 and _kv(usage_records[0])["input_tokens"] == "null"


def test_error_path_logs_status_error(gem, monkeypatch, usage_records):
    _install_fake(monkeypatch, raises=RuntimeError(f"boom {SENTINEL} {FAKE_KEY}"))
    with pytest.raises(gemini.UpstreamError) as ei:
        gemini.parse_text("milk")
    assert FAKE_KEY not in str(ei.value) and SENTINEL not in str(ei.value)
    assert len(usage_records) == 1
    rec = usage_records[0]
    kv = _kv(rec)
    assert rec.levelno == logging.INFO and kv["status"] == "error"
    assert kv["input_tokens"] == "null" and kv["model"] == "gemini-test-model"
    assert SENTINEL not in rec.getMessage() and FAKE_KEY not in rec.getMessage()
    assert rec.exc_info is None  # no traceback (it could carry the key / prompt)


def test_bad_json_response_logs_error_but_keeps_tokens(gem, monkeypatch, usage_records):
    _install_fake(monkeypatch, text="not json {{")
    with pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert len(usage_records) == 1
    kv = _kv(usage_records[0])
    assert kv["status"] == "error" and kv["input_tokens"] == "120"  # the call was billed
    assert "not json" not in usage_records[0].getMessage()


def test_unconfigured_makes_no_call_and_logs_nothing(app, monkeypatch, usage_records):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", "")
    with app.app_context(), pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert usage_records == []


def test_logging_failure_never_breaks_the_call(gem, monkeypatch):
    _install_fake(monkeypatch)
    lg = logging.getLogger(LOGGER)

    def bad(*a, **k):
        raise RuntimeError("logging down")

    monkeypatch.setattr(lg, "info", bad)
    assert gemini.parse_text("milk") == [{"name": "Milk"}]


def test_endpoint_logs_once_through_route(client, user, app, monkeypatch, usage_records):
    monkeypatch.setitem(app.config, "GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setitem(app.config, "GEMINI_MODEL", "gemini-test-model")
    _install_fake(monkeypatch, text='[{"name": "Milk", "category": "dairy", "quantity": 1, "unit": "l", "storage": "fridge"}]')
    r = client.post("/items/parse-text", json={"text": f"milk {SENTINEL}"}, headers=user["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    assert len(usage_records) == 1
    blob = usage_records[0].getMessage()
    assert SENTINEL not in blob and FAKE_KEY not in blob and "status=ok" in blob


# ---------- scripts/gemini_cost.py -----------------------------------------------------------
def _line(model="gemini-3.8-flash", purpose="parse_text", i="100", o="50", t="150", status="ok", ms=900):
    return (f"2026-10-10 12:00:00,000 app.gemini.usage gemini_usage model={model} purpose={purpose} "
            f"input_tokens={i} output_tokens={o} total_tokens={t} latency_ms={ms} status={status}")


def _run(lines, *args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, timeout=30)
    return p


def test_cost_script_totals_and_cost_math():
    lines = [
        "api-1  | some unrelated log line",
        _line(i="1000000", o="1000000", t="2000000"),                       # 0.75 + 3.75 = 4.50
        _line(purpose="detect", i="2000000", o="0", t="2000000"),            # 1.50
        _line(model="gemini-3.5-flash-lite", purpose="recipes", i="1000000", o="100000", t="1100000"),  # 0.30+0.25
        _line(status="error", i="null", o="null", t="null"),
        "garbage gemini_usage nonsense",
    ]
    p = _run(lines)
    assert p.returncode == 0, p.stderr
    out = p.stdout
    total = next(l for l in out.splitlines() if l.startswith("TOTAL"))
    nums = re.findall(r"[\d,]+\.?\d*", total)
    assert nums[0] == "4" and nums[1] == "1"                        # calls, errors
    assert "4,000,000" in total and "1,100,000" in total and "5,100,000" in total
    assert float(nums[-1]) == pytest.approx(4.50 + 1.50 + 0.55, abs=1e-4)
    assert "without usage" in out  # the null-usage error call is flagged


def test_cost_script_price_override_and_default_model():
    p = _run([_line(model="mystery-model", i="1000000", o="1000000", t="2000000")], "--price", "mystery-model=1,2")
    total = next(l for l in p.stdout.splitlines() if l.startswith("TOTAL"))
    assert float(total.split()[-1]) == pytest.approx(3.0)
    p = _run([_line(model="mystery-model", i="1000000", o="1000000", t="2000000")], "--default-price", "4,6")
    assert float(next(l for l in p.stdout.splitlines() if l.startswith("TOTAL")).split()[-1]) == pytest.approx(10.0)
    assert "default price" in p.stdout


def test_cost_script_file_arg_and_empty_input(tmp_path):
    f = tmp_path / "api.log"
    f.write_text(_line(i="10", o="5", t="15") + "\n")
    p = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and "TOTAL" in p.stdout
    p = _run(["nothing here", ""])
    assert p.returncode == 0 and "No gemini_usage lines" in p.stdout


def test_cost_script_parses_real_logger_output(gem, monkeypatch, usage_records):
    """Round trip: the line the backend actually emits is understood by the script."""
    _install_fake(monkeypatch)
    gemini.parse_text("milk")
    formatted = "2026-10-10 app.gemini.usage " + usage_records[0].getMessage()
    p = _run([formatted])
    total = next(l for l in p.stdout.splitlines() if l.startswith("TOTAL"))
    assert "120" in total and "45" in total and "165" in total


def test_cost_script_default_table_prices():
    """The shipped table: gemini-3.8-flash is 0.75 in / 3.75 out per 1M tokens; unknown models use that too."""
    p = _run([_line(i="1000000", o="1000000", t="2000000")])
    assert float(next(l for l in p.stdout.splitlines() if l.startswith("TOTAL")).split()[-1]) == pytest.approx(4.50)
    p = _run([_line(model="gemini-3.1-flash-lite", i="1000000", o="1000000", t="2000000")])
    assert float(next(l for l in p.stdout.splitlines() if l.startswith("TOTAL")).split()[-1]) == pytest.approx(1.75)
    p = _run([_line(model="never-heard-of-it", i="1000000", o="1000000", t="2000000")])
    assert float(next(l for l in p.stdout.splitlines() if l.startswith("TOTAL")).split()[-1]) == pytest.approx(4.50)
    assert "default price" in p.stdout
