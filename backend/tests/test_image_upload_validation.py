"""from-photo / from-receipt reject non-image uploads with 400 before any paid call; mime comes from the bytes."""
import io

import pytest
from PIL import Image

from app.services import gemini, ml


def encode(fmt, size=(8, 8)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 60, 60)).save(buf, fmt)
    return buf.getvalue()


JPEG, PNG, WEBP = encode("JPEG"), encode("PNG"), encode("WEBP")
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic"
ROUTES = ["/items/from-photo", "/items/from-receipt"]


def post(client, user, route, data, mime="image/jpeg", name="p.jpg"):
    return client.post(route, data={"image": (io.BytesIO(data), name, mime)}, headers=user["headers"],
                       content_type="multipart/form-data")


@pytest.fixture
def no_upstream(app, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    for mod, fn in ((gemini, "detect_from_image"), (ml, "detect"), (ml, "ocr")):
        monkeypatch.setattr(mod, fn, lambda *a, _fn=fn, **k: pytest.fail(f"{_fn} must not be called"))


@pytest.fixture
def seen(app, monkeypatch):
    """Stub the vision backends; records the mime each one receives."""
    got = []
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "")
    monkeypatch.setattr(ml, "is_configured", lambda: True)  # receipts: OCR first, never the Gemini fallback (#95)
    monkeypatch.setattr(gemini, "detect_from_image",
                        lambda data, mime, mode: got.append(("photo", mime)) or [])
    monkeypatch.setattr(ml, "ocr", lambda data, name, mime: got.append(("receipt", mime)) or {"lines": [], "total": None})
    return got


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("data", [b"this is just text, renamed .jpg", b"x", b"%PDF-1.4 not an image",
                                  b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"])
def test_non_image_bytes_are_400_with_no_upstream_call(client, user, no_upstream, route, data):
    r = post(client, user, route, data)
    assert r.status_code == 400
    err = r.get_json()["error"]
    assert err["code"] == "validation_error" and "JPEG, PNG, WEBP or HEIC" in err["message"]


@pytest.mark.parametrize("route", ROUTES)
def test_truncated_jpeg_is_400(client, user, no_upstream, route):
    big = encode("JPEG", (400, 300))
    for cut in (60, len(big) // 2):
        assert post(client, user, route, big[:cut]).status_code == 400


@pytest.mark.parametrize("route", ROUTES)
def test_truncated_png_is_400(client, user, no_upstream, route):
    assert post(client, user, route, PNG[: len(PNG) // 2], "image/png", "p.png").status_code == 400


@pytest.mark.parametrize("route", ROUTES)
def test_decompression_bomb_is_400_not_500(client, user, no_upstream, monkeypatch, route):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)  # 8x8 = 64 > 2 x 10 -> DecompressionBombError
    r = post(client, user, route, PNG, "image/png", "p.png")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("route", ROUTES)
def test_empty_and_missing_still_400(client, user, no_upstream, route):
    assert post(client, user, route, b"").status_code == 400
    assert client.post(route, data={}, headers=user["headers"], content_type="multipart/form-data").status_code == 400


@pytest.mark.parametrize("data,mime", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"),
                                       (HEIC, "image/heic")])
def test_valid_formats_reach_gemini_on_from_photo(client, user, seen, data, mime):
    r = post(client, user, "/items/from-photo", data, mime="application/octet-stream")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert seen == [("photo", mime)]


@pytest.mark.parametrize("data,mime", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"),
                                       (HEIC, "image/heic")])
def test_valid_formats_reach_ocr_on_from_receipt(client, user, seen, data, mime):
    r = post(client, user, "/items/from-receipt", data)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert seen == [("receipt", mime)]


def test_mime_is_derived_from_content_not_the_client_header(client, user, seen):
    assert post(client, user, "/items/from-photo", PNG, mime="image/jpeg", name="a.jpg").status_code == 200
    assert seen == [("photo", "image/png")]


def test_mime_to_ml_detect_is_from_content(app, client, user, monkeypatch):
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    got = []
    monkeypatch.setattr(ml, "detect", lambda data, name, mime, mode: got.append(mime) or [])
    assert post(client, user, "/items/from-photo", WEBP, mime="image/jpeg").status_code == 200
    assert got == ["image/webp"]


# ---- BE-28: JPEG completeness is "EOI after the first SOS", not "EOI in the last 4 KB" ----------------------
@pytest.mark.parametrize("route", ROUTES)
def test_jpeg_with_50kb_trailing_junk_is_accepted(client, user, seen, route):
    assert post(client, user, route, JPEG + b"\x00" * 50_000).status_code == 200
    assert post(client, user, route, JPEG + bytes(range(256)) * 200).status_code == 200


@pytest.mark.parametrize("route", ROUTES)
def test_jpeg_cut_mid_scan_is_still_400(client, user, no_upstream, route):
    big = Image.effect_noise((300, 300), 80).convert("RGB")
    buf = io.BytesIO()
    big.save(buf, "JPEG")
    data = buf.getvalue()
    sos = data.find(b"\xff\xda")
    assert sos != -1 and len(data) > sos + 2000
    for cut in (sos + 20, sos + (len(data) - sos) // 2, len(data) - 3):
        assert post(client, user, route, data[:cut]).status_code == 400, cut


def test_mpo_layout_is_accepted(client, user, seen):
    a = io.BytesIO()
    Image.new("RGB", (16, 16), (10, 200, 10)).save(a, "JPEG")
    b = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 10, 10)).save(b, "JPEG")
    mpo = a.getvalue() + b.getvalue()  # two concatenated JPEGs: primary then secondary, as in an MPO
    r = post(client, user, "/items/from-photo", mpo)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert seen == [("photo", "image/jpeg")]
