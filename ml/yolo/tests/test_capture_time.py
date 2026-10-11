"""parse_capture_time (prepare_dataset) must read every filename format ml/eval/leakage_check.py reads, and the
two parsers must agree (ML-21: the split groups by sessions the QA check later measures)."""
import sys
from pathlib import Path

import pytest

import prepare_dataset as P

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import leakage_check as L  # noqa: E402  (read-only import of ML QA's parser)

# (name, kind in prepare_dataset, kind in leakage_check)
PARSED = [
    ("IMG_20251102_075610.jpg", "compact", "compact"),
    ("IMG_20251102_075610660_HDR_AE.jpg", "compact", "compact"),          # AgriFreshNET: milliseconds
    ("aug_3_IMG_20251102_075610660_HDR.jpg", "compact", "compact"),
    ("IMG20250926100615.jpg", "compact", "compact"),
    ("20250101_123456.jpg", "compact", "compact"),
    ("PXL_20250101_123456789.jpg", "compact", "compact"),
    ("IMG-20250101-123456.jpg", "compact", "compact"),                    # hyphen between date and time
    ("banana__semi_fresh__IMG_20250101_123456.rf.0a1b2c3d.jpg", "compact", "compact"),
    ("banana__spec_ab12cd34.rf.0123456789abcdef_IMG_20251102_075610660_HDR.jpg", "compact", "compact"),
    ("1758873619153.jpg", "epoch_ms", "epoch"),
    ("photo_1600000000000_x.jpg", "epoch_ms", "epoch"),
    ("Screen_Shot_2018-06-08_at_4.59.36_PM.png", "screenshot", "shot"),
    ("Screen_Shot_2020-07-29_at_8_31_22_AM.png", "screenshot", "shot"),
    ("WhatsApp_Image_2020-11-07_at_11.35.36_PM.jpg", "screenshot", "shot"),
]
NOT_PARSED = ["IMG_0042.jpg", "Banana (3).jpeg", "IMG-20251122-WA0003.jpg", "fresh_apple_1.jpg", "rotated_by_15_x_3.jpg"]


@pytest.mark.parametrize("name,kp,kl", PARSED)
def test_every_format_is_parsed_by_both(name, kp, kl):
    a, b = P.parse_capture_time(Path(name)), L.stamp(name)
    assert a is not None and b is not None, (a, b)
    assert a[0] == kp and b[0] == kl


@pytest.mark.parametrize("name", NOT_PARSED)
def test_names_without_a_time_are_ignored_by_both(name):
    assert P.parse_capture_time(Path(name)) is None and L.stamp(name) is None


def test_parsers_agree_on_time_differences():
    """Absolute values differ by the timezone each uses, so compare gaps between names."""
    base_p, base_l = P.parse_capture_time(Path(PARSED[0][0]))[1], L.stamp(PARSED[0][0])[1]
    for name, kp, kl in PARSED[:9]:
        if "20250101" in name or "20250926" in name:
            continue
        dp = P.parse_capture_time(Path(name))[1] - base_p
        dl = L.stamp(name)[1] - base_l
        assert abs(dp - dl) < 1.0 + 1e-6 or abs(dp - dl) % 3600 < 1e-6, (name, dp, dl)   # at most a DST hour apart
    # same-minute-plus-gap: both see 200 s
    a = P.parse_capture_time(Path("IMG_20251201_190640848.jpg"))[1]
    b = P.parse_capture_time(Path("IMG_20251201_191000111.jpg"))[1]
    la, lb = L.stamp("IMG_20251201_190640848.jpg")[1], L.stamp("IMG_20251201_191000111.jpg")[1]
    assert b - a == lb - la == 200


def test_milliseconds_are_not_taken_for_seconds():
    t = P.parse_capture_time(Path("IMG_20251102_075610660.jpg"))[1]
    assert t == P.parse_capture_time(Path("IMG_20251102_075610.jpg"))[1]
