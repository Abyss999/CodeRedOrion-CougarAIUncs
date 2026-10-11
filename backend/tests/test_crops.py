"""services/crops: cutting detections out of the uploaded photo for the Gemini call."""
import io

import pytest
from PIL import Image

from app.services import crops

W, H = 400, 300
RED, BLUE = (200, 30, 30), (30, 30, 200)


def photo(size=(W, H), orientation=None, fmt="JPEG", mode="RGB", tags=None):
    """Left half red, right half blue (so a crop's colour says where it came from)."""
    img = Image.new("RGB", size, RED)
    img.paste(BLUE, (size[0] // 2, 0, size[0], size[1]))
    if mode != "RGB":
        img = img.convert(mode)
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    for tag, value in (tags or {}).items():
        exif[tag] = value
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.save(buf, fmt, exif=exif)
    else:
        img.save(buf, fmt)
    return buf.getvalue()


def open_(data):
    return Image.open(io.BytesIO(data))


def is_red(p):
    return p[0] > 150 and p[2] < 100


def is_blue(p):
    return p[2] > 150 and p[0] < 100


def make(app, image, boxes):
    with app.app_context():
        return crops.make(image, boxes)


def test_one_jpeg_per_box_in_order_and_none_for_unusable_boxes(app):
    out = make(app, photo(), [[0, 0, 150, 300], None, [250, 0, 400, 300]])
    assert len(out) == 3 and out[1] is None
    left, right = open_(out[0]), open_(out[2])
    assert left.format == "JPEG" and right.format == "JPEG"
    assert is_red(left.getpixel((left.width // 2, left.height // 2)))
    assert is_blue(right.getpixel((right.width // 2, right.height // 2)))


def test_crop_is_grown_by_the_pad_and_clamped_to_the_image(app):
    out = make(app, photo(), [[100, 100, 200, 180], [0, 0, 200, 150]])
    assert open_(out[0]).size == (116, 94)   # 100 x 80 box + 8 % per side
    assert open_(out[1]).size == (216, 162)  # the left and top edges are the image edge: no padding there


def test_long_side_is_capped_and_the_aspect_ratio_kept(app, monkeypatch):
    out = make(app, photo((2000, 1500)), [[0, 0, 2000, 1500]])
    assert open_(out[0]).size == (512, 384)
    monkeypatch.setitem(app.config, "ENRICH_CROP_MAX_PX", 128)
    out = make(app, photo((2000, 1500)), [[0, 0, 2000, 1500]])
    assert open_(out[0]).size == (128, 96)


def test_small_crops_are_never_upscaled(app):
    assert open_(make(app, photo(), [[100, 100, 200, 180]])[0]).size == (116, 94)


def test_metadata_is_dropped(app):
    data = photo(tags={0x010F: "SecretCam", 0x0131: "secret-software"})
    assert b"SecretCam" in data, "the fixture really carries EXIF"
    out = make(app, data, [[0, 0, 200, 150]])[0]
    assert len(open_(out).getexif()) == 0
    assert b"SecretCam" not in out and b"secret-software" not in out


@pytest.mark.parametrize("orientation,size,red_at,blue_at", [
    (None, (200, 100), "left", "right"),
    (1, (200, 100), "left", "right"),
    (3, (200, 100), "right", "left"),      # upside down: left and right swap
    (6, (100, 200), "top", "bottom"),      # shown rotated 90 degrees clockwise: the left half is now the top
    (8, (100, 200), "bottom", "top"),      # rotated 90 degrees counter-clockwise
])
def test_crop_is_rotated_upright_by_exif_orientation(app, orientation, size, red_at, blue_at):
    out = open_(make(app, photo((200, 100), orientation=orientation), [[0, 0, 200, 100]])[0])
    assert out.size == size
    w, h = out.size
    spot = {"left": (w // 4, h // 2), "right": (3 * w // 4, h // 2), "top": (w // 2, h // 4),
            "bottom": (w // 2, 3 * h // 4)}
    assert is_red(out.getpixel(spot[red_at])), (orientation, red_at)
    assert is_blue(out.getpixel(spot[blue_at])), (orientation, blue_at)


def test_boxes_are_in_the_raw_pixel_frame_by_default(app):
    """ml/serve decodes without EXIF transpose. A box in the *upright* frame is mostly outside the raw image."""
    sideways = photo((200, 100), orientation=6)  # upright it is 100 x 200
    assert make(app, sideways, [[0, 100, 100, 200]]) == [None]


def test_upright_frame_config_transposes_the_whole_photo_before_cutting(app, monkeypatch):
    monkeypatch.setitem(app.config, "ML_BBOX_FRAME", "upright")
    out = open_(make(app, photo((200, 100), orientation=6), [[0, 100, 100, 200]])[0])
    assert is_blue(out.getpixel((out.width // 2, out.height // 2 + 20))), "bottom half upright is the blue half"
    assert out.size[0] == 100


@pytest.mark.parametrize("bad", [
    None, [], [1, 2, 3], [1, 2, 3, 4, 5], "abc", 5, {"x": 1},
    [0, 0, 0, 0], [50, 50, 50, 90],                      # no area
    [float("nan"), 0, 100, 100], [0, 0, float("inf"), 100], ["a", 0, 100, 100], [None, 0, 100, 100],
    [1000, 1000, 1100, 1100],                            # entirely outside
    [-500, -500, 10, 10],                                # mostly outside
    [10, 10, 20, 20],                                    # too small to carry detail
])
def test_unusable_boxes_give_none(app, bad):
    assert make(app, photo(), [bad]) == [None]


def test_a_reversed_box_is_normalised(app):
    assert make(app, photo(), [[210, 160, 10, 10]])[0] is not None


@pytest.mark.parametrize("data", [b"", b"\xff\xd8fakejpeg", b"not an image at all", b"\x89PNG\r\n\x1a\n"])
def test_undecodable_bytes_give_all_none_without_raising(app, data):
    assert make(app, data, [[0, 0, 100, 100], [10, 10, 200, 200]]) == [None, None]


def test_too_many_pixels_is_all_none(app, monkeypatch):
    monkeypatch.setitem(app.config, "ENRICH_MAX_PIXELS", 1000)
    assert make(app, photo(), [[0, 0, 200, 150]]) == [None]


def test_png_and_alpha_input_work_and_come_out_as_jpeg(app):
    for data in (photo(fmt="PNG"), photo(fmt="PNG", mode="RGBA")):
        out = make(app, data, [[0, 0, 150, 300]])[0]
        assert out[:2] == b"\xff\xd8" and open_(out).mode == "RGB"


def test_no_decode_when_no_box_is_usable(app, monkeypatch):
    def boom(_):
        raise AssertionError("decoded for nothing")
    monkeypatch.setattr(crops, "_decode", boom)
    assert make(app, b"x", [None, [], "bad"]) == [None, None, None]
    assert make(app, b"x", []) == []


def test_one_failing_box_does_not_cost_the_others(app, monkeypatch):
    real, calls = crops._cut, []

    def flaky(*a):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(*a)
    monkeypatch.setattr(crops, "_cut", flaky)
    out = make(app, photo(), [[0, 0, 150, 300], [0, 0, 160, 300], [250, 0, 400, 300]])
    assert out[0] is not None and out[1] is None and out[2] is not None
