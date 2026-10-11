"""variant_dup_check (report only, ML-40): same-class only, padding masked, central crop, noise floor shown.
Needs imagehash + numpy (skipped in venv-ml)."""
import subprocess
import sys
from pathlib import Path

import pytest

imagehash = pytest.importorskip("imagehash")
np = pytest.importorskip("numpy")
from PIL import Image  # noqa: E402

import variant_dup_check as v  # noqa: E402

T = Image.Transpose


def _img(seed):
    rng = np.random.default_rng(seed)
    a = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)
    return Image.fromarray(a).resize((128, 128), Image.BICUBIC)


def _make(root, split, name, im, cls=None):
    d = root / "images" / split
    d.mkdir(parents=True, exist_ok=True)
    im.save(d / name, quality=98)
    if cls is not None:
        ld = root / "labels" / split
        ld.mkdir(parents=True, exist_ok=True)
        (ld / (Path(name).stem + ".txt")).write_text(f"{cls} 0.5 0.5 0.5 0.5\n")


@pytest.mark.parametrize("op", ["flip", "rot90", "rot270", "flip_rot90"])
def test_transformed_copy_is_flagged(tmp_path, op):
    base = _img(1)
    copy = {"flip": base.transpose(T.FLIP_LEFT_RIGHT), "rot90": base.transpose(T.ROTATE_90),
            "rot270": base.transpose(T.ROTATE_270),
            "flip_rot90": base.transpose(T.FLIP_LEFT_RIGHT).transpose(T.ROTATE_90)}[op]
    _make(tmp_path, "train", "srcA_one.jpg", base, 3)
    _make(tmp_path, "heldout", "srcA_two.jpg", copy, 3)
    _make(tmp_path, "train", "srcA_other.jpg", _img(2), 3)
    r = v.check(tmp_path, sources=["srcA"], workers=1)["srcA"]
    t = r["heldout_vs_trainval"]
    assert t["same_class_near_dup"] == 1 and t["same_class_pct"] == 100.0
    assert t["same_class_identity_only_pct"] == 0.0
    assert r["within_set_same_class"]["pairs_straddling_splits"] >= 1
    assert "criterion_variant_phash_le_1pct_heldout" not in r      # reported only, no gate field


def test_unrelated_images_not_flagged(tmp_path):
    _make(tmp_path, "train", "srcA_one.jpg", _img(3), 1)
    _make(tmp_path, "heldout", "srcA_two.jpg", _img(4), 1)
    t = v.check(tmp_path, sources=["srcA"], workers=1)["srcA"]["heldout_vs_trainval"]
    assert t["same_class_near_dup"] == 0


def test_different_class_copy_is_not_same_class_but_shows_in_floor(tmp_path):
    base = _img(5)
    _make(tmp_path, "train", "srcA_one.jpg", base, 1)            # class 1 reference: the rotated copy
    _make(tmp_path, "train", "srcA_far.jpg", _img(6), 2)         # class 2 reference: unrelated
    _make(tmp_path, "heldout", "srcA_q.jpg", base.transpose(T.ROTATE_90), 2)
    t = v.check(tmp_path, sources=["srcA"], workers=1)["srcA"]["heldout_vs_trainval"]
    assert t["same_class_near_dup"] == 0                         # the look-alike is a different class: not counted
    assert t["diff_class_floor_all_pct"] == 100.0                # but it is the noise floor
    assert t["excess_over_floor_points"] <= 0


def test_black_rotation_padding_is_masked(tmp_path):
    """Two different pictures rotated 45 degrees with black corners look alike through the padding; masking removes that."""
    a = _img(7).resize((200, 200)).rotate(45, expand=True, fillcolor=(0, 0, 0))
    b = _img(8).resize((200, 200)).rotate(45, expand=True, fillcolor=(0, 0, 0))
    for mask in (False, True):
        d = tmp_path / f"m{int(mask)}"
        _make(d, "train", "srcA_one.jpg", a, 1)
        _make(d, "heldout", "srcA_two.jpg", b, 1)
        r = v.check(d, sources=["srcA"], workers=1, crop=1.0, mask=mask)["srcA"]
        if mask:
            assert r["padding_masked_images"] == 2
        else:
            assert r["padding_masked_images"] == 0
    im, masked = v.mask_padding(a)
    assert masked and np.asarray(im).max(axis=2).min() > v.BLACK       # no black left
    plain, m2 = v.mask_padding(_img(9))
    assert not m2                                                     # an ordinary image is untouched


def test_central_crop_size():
    im = Image.new("RGB", (100, 50))
    assert v.central_crop(im, 0.8).size == (80, 40)
    assert v.central_crop(im, 1.0).size == (100, 50)


def test_cli_is_report_only_exit_zero(tmp_path):
    base = _img(10)
    _make(tmp_path, "train", "srcA_one.jpg", base, 1)
    _make(tmp_path, "heldout", "srcA_two.jpg", base.transpose(T.FLIP_LEFT_RIGHT), 1)   # a duplicate, 100% > 1%
    script = Path(v.__file__)
    p = subprocess.run([sys.executable, str(script), str(tmp_path), "--sources", "srcA", "--workers", "1",
                        "--component-t", "0"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "not a gate" in p.stdout
