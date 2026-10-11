"""variant_dup_check: a flipped / rotated copy of a held-out image must be caught (needs imagehash + numpy)."""
import pytest

imagehash = pytest.importorskip("imagehash")
np = pytest.importorskip("numpy")
from PIL import Image  # noqa: E402

import variant_dup_check as v  # noqa: E402


def _img(seed):
    rng = np.random.default_rng(seed)
    a = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)
    return Image.fromarray(a).resize((128, 128), Image.BICUBIC)


def _make(root, split, name, im):
    d = root / "images" / split
    d.mkdir(parents=True, exist_ok=True)
    im.save(d / name)


@pytest.mark.parametrize("op", ["flip", "rot90", "rot270", "flip_rot90"])
def test_transformed_copy_is_flagged(tmp_path, op):
    base = _img(1)
    T = Image.Transpose
    copy = {"flip": base.transpose(T.FLIP_LEFT_RIGHT), "rot90": base.transpose(T.ROTATE_90),
            "rot270": base.transpose(T.ROTATE_270),
            "flip_rot90": base.transpose(T.FLIP_LEFT_RIGHT).transpose(T.ROTATE_90)}[op]
    _make(tmp_path, "train", "srcA_one.jpg", base)
    _make(tmp_path, "heldout", "srcA_two.jpg", copy)
    _make(tmp_path, "train", "srcA_other.jpg", _img(2))
    r = v.check(tmp_path, sources=["srcA"], workers=1)["srcA"]
    assert r["heldout_vs_trainval"]["variant_near_dup"] == 1
    assert r["heldout_vs_trainval"]["identity_only_near_dup"] == 0
    assert r["criterion_variant_phash_le_1pct_heldout"] is False
    assert r["within_set"]["pairs_straddling_splits"] >= 1


def test_unrelated_images_pass(tmp_path):
    _make(tmp_path, "train", "srcA_one.jpg", _img(3))
    _make(tmp_path, "heldout", "srcA_two.jpg", _img(4))
    r = v.check(tmp_path, sources=["srcA"], workers=1)["srcA"]
    assert r["heldout_vs_trainval"]["variant_near_dup"] == 0
