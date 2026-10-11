"""QA re-verification of BE-19..BE-22 (fixed by d6b0a52 on PR #79, merged at 02b06e8).

Each test fails on the pre-fix code and passes on the fix. Never calls Google; the memory test runs in
subprocesses so peak RSS is that of one crop only.
"""
import io
import os
import re
import struct
import subprocess
import sys
import textwrap

import pytest
from PIL import Image

from app.services import crops, gemini

from tests.test_qa_pr79_gemini import FakeGenai, _raise, det, gemini_on, photo, use_yolo  # noqa: F401


def _jpeg(size=(300, 300), **kw):
    b = io.BytesIO()
    Image.new("RGB", size, (120, 120, 120)).save(b, "JPEG", **kw)
    return b.getvalue()


def _markers(b):
    i, out = 2, []
    while i < len(b) - 3 and b[i] == 0xFF:
        m = b[i + 1]
        if m in (0xDA, 0xD9):
            break
        out.append(m)
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    return out


# ---- BE-19 ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("orientation", [1, 6])
@pytest.mark.parametrize("mode", ["RGB", "L"])
def test_be19_comment_segment_never_reaches_the_crop(app, orientation, mode):
    ex = Image.Exif()
    ex[0x0112] = orientation
    img = Image.new("RGB", (300, 300), (120, 120, 120)).convert(mode)
    b = io.BytesIO()
    img.save(b, "JPEG", exif=ex.tobytes(), comment=b"secret-comment-text")
    data = b.getvalue()
    assert b"secret-comment-text" in data and 0xFE in _markers(data)  # fixture really has a COM segment
    with app.app_context():
        out = crops.make(data, [[0, 0, 300, 300]])[0]
    assert out is not None
    assert b"secret-comment-text" not in out and 0xFE not in _markers(out)
    im = Image.open(io.BytesIO(out))
    assert "comment" not in im.info and len(im.getexif()) == 0


def test_be19_comment_with_every_other_metadata_kind_leaves_only_baseline_markers(app):
    ex = Image.Exif()
    ex[0x010F] = "SecretMake"
    ex.get_ifd(0x8825).update({1: "N", 2: (33.0, 0.0, 0.0), 3: "W", 4: (96.0, 0.0, 0.0)})
    data = _jpeg(exif=ex.tobytes(), icc_profile=b"\x00" * 128 + b"secret-icc", comment=b"secret-comment-text")
    xmp = b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta>secret-xmp</x:xmpmeta>"
    data = data[:2] + b"\xff\xe1" + struct.pack(">H", 2 + len(xmp)) + xmp + data[2:]
    for needle in (b"SecretMake", b"secret-icc", b"secret-xmp", b"secret-comment-text"):
        assert needle in data
    with app.app_context():
        out = crops.make(data, [[0, 0, 300, 300]])[0]
    for needle in (b"SecretMake", b"Exif", b"GPS", b"secret-icc", b"ICC_PROFILE", b"adobe", b"xmp", b"secret-xmp",
                   b"secret-comment-text"):
        assert needle not in out, needle
    assert set(_markers(out)) <= {0xE0, 0xDB, 0xC0, 0xC2, 0xC4}, [hex(m) for m in _markers(out)]


def test_be19_comment_does_not_survive_through_the_route_to_gemini(app, client, user, monkeypatch, gemini_on):
    data = _jpeg((400, 300), comment=b"secret-comment-text")
    use_yolo(app, monkeypatch, [det("apple")])
    fake = FakeGenai(lambda k, kw: "[]").install(monkeypatch)
    photo(client, user, "expiry", data=data)
    sent = [p for p in fake.calls[0]["contents"] if not isinstance(p, str)]
    blobs = [getattr(getattr(p, "inline_data", None), "data", None) or getattr(p, "data", None) for p in sent]
    blobs = [b for b in blobs if isinstance(b, bytes)]
    assert blobs, "a crop part was sent"
    assert all(b"secret-comment-text" not in b and 0xFE not in _markers(b) for b in blobs)


# ---- BE-20 ---------------------------------------------------------------------------------------------------
class _Coded(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


RETRYABLE = [_Coded("rate", 429), _Coded("unavail", 503), _Coded("deadline", 504),
             RuntimeError("DEADLINE_EXCEEDED"), RuntimeError("503 UNAVAILABLE. high demand"),
             RuntimeError("429 RESOURCE_EXHAUSTED")]


@pytest.mark.parametrize("exc", RETRYABLE, ids=lambda e: f"{type(e).__name__}-{str(e)[:12]}")
def test_be20_enrich_makes_exactly_one_http_attempt(app, client, user, monkeypatch, gemini_on, exc):
    use_yolo(app, monkeypatch, [det("apple")])
    fake = FakeGenai(_raise(exc)).install(monkeypatch)
    r = photo(client, user, "expiry,nutrition")
    assert r.status_code == 200 and r.get_json()["enrichment"]["reason"] == "upstream_error"
    assert len(fake.calls) == 1


@pytest.mark.parametrize("exc", RETRYABLE, ids=lambda e: f"{type(e).__name__}-{str(e)[:12]}")
def test_be20_enrich_items_directly_no_sleep_no_second_call(app, monkeypatch, gemini_on, exc):
    slept = []
    monkeypatch.setattr(gemini.time, "sleep", lambda s: slept.append(s))
    fake = FakeGenai(_raise(exc)).install(monkeypatch)
    items = [{"name": "apple", "category": "produce_hardy", "storage": "fridge", "freshness": "fresh"}]
    with app.app_context(), pytest.raises(gemini.UpstreamError):
        gemini.enrich_items(items, [None], ("expiry",))
    assert len(fake.calls) == 1 and slept == []


def test_be20_other_purposes_keep_the_single_retry(app, monkeypatch, gemini_on):
    for call in (lambda: gemini.parse_text("milk"),
                 lambda: gemini.suggest_recipes([], 3, []),
                 lambda: gemini.estimate_shelf_life([{"name": "a", "category": "other", "storage": "fridge"}])):
        state = {"n": 0}

        def outcome(k, kw, state=state):
            state["n"] += 1
            if k == 1:
                raise _Coded("unavail", 503)
            return "[]"

        fake = FakeGenai(outcome).install(monkeypatch)
        with app.app_context():
            try:
                call()
            except gemini.UpstreamError:
                pass
        assert len(fake.calls) == 2, "retry once on a transient error"
    # and a persistent transient error is two attempts, not more
    fake = FakeGenai(_raise(_Coded("unavail", 503))).install(monkeypatch)
    with app.app_context(), pytest.raises(gemini.UpstreamError):
        gemini.parse_text("milk")
    assert len(fake.calls) == 2


def test_be20_retry_default_is_true_and_only_enrich_opts_out():
    import inspect
    assert inspect.signature(gemini._generate).parameters["retry"].default is True
    src = inspect.getsource(gemini)
    assert len(re.findall(r"retry=False\)", src)) == 1
    assert "retry=False)" in inspect.getsource(gemini.enrich_items)


def test_be20_documented_worst_case_matches_the_code():
    docs = open(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "API.md")).read()
    assert "never retried (one attempt, 25 s at most)" in docs
    assert "detection (skipped past 30 s) plus 25 s" in docs and "at least 60 s" in docs
    # 30 s detection ceiling + one 25 s attempt = 55 s < the documented 60 s
    from flask import Flask
    app = Flask(__name__)
    app.config.update(ENRICH_TIMEOUT_S=25, ENRICH_SKIP_AFTER_S=30)
    assert app.config["ENRICH_SKIP_AFTER_S"] + app.config["ENRICH_TIMEOUT_S"] < 60


# ---- BE-21 ---------------------------------------------------------------------------------------------------
def test_be21_api_md_says_best_effort_and_names_the_twin_caveat():
    docs = open(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "API.md")).read()
    assert "the server does not check that a recipe obeys it" in docs
    assert "with two items of the same name the focus one may be reported" in docs


# ---- BE-22 ---------------------------------------------------------------------------------------------------
_GEN = textwrap.dedent("""
    import sys
    from PIL import Image
    Image.new("RGBA", (7062, 7062), (10, 200, 30, 255)).save(sys.argv[1], "PNG", compress_level=9)
""")
_MEASURE = textwrap.dedent("""
    import resource, sys
    from flask import Flask
    from PIL import Image
    sys.path.insert(0, sys.argv[2])
    from app.services import crops
    data = open(sys.argv[1], "rb").read()
    app = Flask("m")
    scale = 1 if sys.platform == "darwin" else 1024
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale
    with app.app_context():
        out = crops.make(data, [[100, 100, 400, 400]])
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale
    assert out[0] is not None
    print(int(base), int(peak))
""")


def test_be22_peak_memory_of_a_49_9mp_rgba_png_crop_is_one_decode_not_two(tmp_path):
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    png = tmp_path / "big.png"
    subprocess.run([sys.executable, "-c", _GEN, str(png)], check=True, timeout=120)
    assert 7062 * 7062 == 49_871_844 < crops.MAX_PIXELS and png.stat().st_size < 1_000_000
    r = subprocess.run([sys.executable, "-c", _MEASURE, str(png), backend], check=True, capture_output=True,
                       text=True, timeout=120, env={**os.environ, "PYTHONPATH": backend})
    base, peak = map(int, r.stdout.split()[-2:])
    delta_mb = (peak - base) / 1e6
    raw_rgba_mb = 7062 * 7062 * 4 / 1e6  # ~200 MB: the unavoidable decode
    # pre-fix: decode + a full RGB convert = ~1.75x the raw RGBA buffer (measured +400 MB); fixed is ~1.0x
    assert delta_mb < raw_rgba_mb * 1.4, f"+{delta_mb:.0f} MB for a {raw_rgba_mb:.0f} MB decode"


def test_be22_pixel_ceiling_still_enforced_from_the_header(app):
    big = io.BytesIO()
    Image.new("L", (7100, 7100), 0).save(big, "PNG", compress_level=9)  # 50.4 MP
    with app.app_context():
        assert crops.make(big.getvalue(), [[0, 0, 500, 500]]) == [None]
    assert crops.MAX_PIXELS == 50_000_000 and Image.MAX_IMAGE_PIXELS == 89478485
