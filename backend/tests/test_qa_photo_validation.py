"""Independent QA for fix/photo-image-validation (BE-26/BE-27/BE-28). Stubs only: no Gemini or ML call."""
import io
import struct

import pytest
from PIL import Image

from app.services import gemini, ml


def enc(fmt, size=(8, 8), **kw):
    b = io.BytesIO()
    Image.new("RGB", size, (200, 60, 60)).save(b, fmt, **kw)
    return b.getvalue()


JPEG = enc("JPEG")


def post(client, user, route, data, mime="image/jpeg", name="p.jpg", headers=True):
    return client.post(route, data={"image": (io.BytesIO(data), name, mime)},
                       headers=user["headers"] if headers else {}, content_type="multipart/form-data")


@pytest.fixture
def stubs(app, monkeypatch):
    got = []
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "")
    monkeypatch.setattr(gemini, "detect_from_image", lambda d, m, mode: got.append((len(d), m)) or [])
    monkeypatch.setattr(ml, "ocr", lambda d, n, m: got.append((len(d), m)) or {"lines": [], "total": None})
    return got


def with_trailer(jpeg, n):
    """A valid JPEG with n bytes after EOI (MPF second image / Ultra HDR gain map / depth data)."""
    assert jpeg.endswith(b"\xff\xd9")
    return jpeg + b"\x00" * n


def mpo_like(n):
    """Primary JPEG followed by a complete second JPEG (what a camera MPO / Ultra HDR file is)."""
    return JPEG + enc("JPEG", size=(max(8, n), 8))


# ---- BE-26 false-reject risk: valid JPEGs with data after EOI --------------------------------------

@pytest.mark.parametrize("trailer", [100, 3000])
def test_small_trailer_after_eoi_accepted(client, user, stubs, trailer):
    assert post(client, user, "/items/from-photo", with_trailer(JPEG, trailer)).status_code == 200


def test_real_second_jpeg_after_primary_accepted(client, user, stubs):
    """MPO / Ultra HDR layout: primary image then a full second JPEG. The second JPEG ends in FFD9 so this passes."""
    assert post(client, user, "/items/from-photo", mpo_like(400)).status_code == 200


def test_valid_jpeg_with_50kb_nonmarker_trailer_is_wrongly_rejected(client, user, stubs):
    """BE-28 (fixed): valid JPEG + 50 KB trailer without a final FFD9 (padding, depth payload) must be accepted."""
    data = with_trailer(JPEG, 50_000)
    Image.open(io.BytesIO(data)).load()  # proves it is a good image
    assert post(client, user, "/items/from-photo", data).status_code == 200


def test_pillow_loads_jpeg_with_big_trailer():
    Image.open(io.BytesIO(with_trailer(JPEG, 50_000))).load()


def test_truncated_jpeg_without_trailer_still_400(client, user, stubs):
    big = enc("JPEG", size=(300, 300), quality=95)
    assert post(client, user, "/items/from-photo", big[: len(big) // 2]).status_code == 400


def test_jpeg_cut_in_the_last_bytes_is_400(client, user, stubs):
    big = enc("JPEG", size=(300, 300))
    assert post(client, user, "/items/from-photo", big[:-2]).status_code == 400


# ---- ordering / limits -----------------------------------------------------------------------------

@pytest.mark.parametrize("route", ["/items/from-photo", "/items/from-receipt"])
def test_401_before_400_for_garbage_unauthenticated(client, user, stubs, route):
    assert post(client, user, route, b"not an image", headers=False).status_code == 401


def test_413_for_oversize_even_if_garbage(client, user, stubs):
    r = post(client, user, "/items/from-photo", b"x" * (11 * 1024 * 1024))
    assert r.status_code == 413


def test_bad_mode_is_400_before_image_check(client, user, stubs):
    r = client.post("/items/from-photo", data={"mode": "nope", "image": (io.BytesIO(b"garbage"), "a.jpg")},
                    headers=user["headers"], content_type="multipart/form-data")
    assert r.status_code == 400 and "mode" in r.get_json()["error"]["message"]


def test_bytes_forwarded_intact_after_verify(client, user, stubs):
    png = enc("PNG", size=(40, 30))
    assert post(client, user, "/items/from-photo", png).status_code == 200
    assert stubs == [(len(png), "image/png")]


def test_heic_forwarded_as_image_heic_to_gemini_and_ml(app, client, user, monkeypatch):
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
    got = []
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "http://ml.invalid")
    monkeypatch.setattr(ml, "detect", lambda d, n, m, mode: got.append(("ml", m)) or [])
    assert post(client, user, "/items/from-photo", heic, mime="image/jpeg", name="a.heic").status_code == 200
    monkeypatch.setitem(app.config, "ML_SERVICE_URL", "")
    monkeypatch.setattr(gemini, "detect_from_image", lambda d, m, mode: got.append(("gem", m)) or [])
    assert post(client, user, "/items/from-photo", heic, name="a.heic").status_code == 200
    assert got == [("ml", "image/heic"), ("gem", "image/heic")]


def test_ftyp_but_not_heic_brand_is_400(client, user, stubs):
    mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    assert post(client, user, "/items/from-photo", mp4).status_code == 400


def test_ftyp_heic_header_with_no_body_is_accepted_documented(client, user, stubs):
    """HEIC is only brand-sniffed (no structure check): a 12-byte stub passes. Documented limitation, not a bug."""
    assert post(client, user, "/items/from-photo", b"\x00\x00\x00\x0cftypheic").status_code == 200


def test_bomb_error_is_400(client, user, stubs, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    r = post(client, user, "/items/from-photo", enc("PNG", size=(100, 100)))
    assert r.status_code == 400


def test_no_full_decode_on_png_verify(client, user, stubs, monkeypatch):
    """verify() must not call load() (memory): patch ImageFile.load to explode."""
    from PIL import ImageFile
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: pytest.fail("full decode"))
    assert post(client, user, "/items/from-photo", enc("PNG", size=(50, 50))).status_code == 200


def exif_thumb_jpeg(main_cut):
    """JPEG whose EXIF APP1 embeds a thumbnail JPEG (own SOS+EOI); optionally cut off the main scan."""
    exif = Image.Exif()
    thumb = enc("JPEG", size=(16, 16))
    big = Image.new("RGB", (400, 400))
    import random
    random.seed(1)
    big.putdata([(random.randrange(256),) * 3 for _ in range(400 * 400)])
    b = io.BytesIO()
    big.save(b, "JPEG", exif=exif.tobytes())
    data = b.getvalue()
    # splice a thumbnail JPEG into the APP1 payload region by building the segment by hand
    seg_body = b"Exif\x00\x00" + thumb
    app1 = b"\xff\xe1" + struct.pack(">H", len(seg_body) + 2) + seg_body
    soi, rest = data[:2], data[2:]
    out = soi + app1 + rest
    return out[: len(out) // 2] if main_cut else out


def test_residual_exif_thumbnail_eoi_lets_cut_main_scan_through(client, user, stubs):
    """Named residual (documented, not a bug): the thumbnail's SOS/EOI satisfies the marker check, so a JPEG whose
    MAIN scan is cut off still reaches Gemini. The app re-encodes, and Gemini fails soft (502), so impact is low."""
    r = post(client, user, "/items/from-photo", exif_thumb_jpeg(True))
    assert r.status_code == 200  # pins current behaviour; flip to 400 if the check is ever tightened


def test_intact_jpeg_with_thumbnail_accepted(client, user, stubs):
    assert post(client, user, "/items/from-photo", exif_thumb_jpeg(False)).status_code == 200
