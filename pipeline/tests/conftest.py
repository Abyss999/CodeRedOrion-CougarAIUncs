"""Shared helpers. All data lives under pytest tmp_path - never pipeline/data."""
from __future__ import annotations
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def make_jpeg(path: Path, seed: int, size=(48, 48), base=(120, 110, 100)) -> Path:
    """Unique noisy image (different seed -> different bytes)."""
    rng = np.random.default_rng(seed)
    a = np.clip(np.array(base, np.float32) + rng.normal(0, 40, (size[1], size[0], 3)), 0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(path, "JPEG", quality=92)
    return path


def jpeg_bytes(seed: int, size=(48, 48)) -> bytes:
    b = io.BytesIO()
    Image.fromarray(np.random.default_rng(seed).integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)).save(b, "JPEG")
    return b.getvalue()


def zip_dir(src: Path, dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w") as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src).as_posix())
    return dest


@pytest.fixture
def root(tmp_path):
    return tmp_path / "data"


def build_drop(drop: Path, per_class: int = 30, with_aug=True) -> Path:
    """Synthetic AgriFreshNET-like drop."""
    seed = 0
    classes = {"Fresh Banana(1-4)": 0, "Semi fresh Pineapple (15-25)": 1, "Semi_Fresh eggplant(4-8)": 2,
               "Rotten Orange(20-35)": 3, "Semi Fresh Bittermelon ( 3-5)": 4}
    for cname, k in classes.items():
        for i in range(per_class):
            seed += 1
            make_jpeg(drop / cname / f"IMG_{i:04d}.jpg", seed, base=(60 + 30 * k, 120, 90))
            if with_aug and i % 3 == 0:
                seed += 1
                make_jpeg(drop / cname / f"aug_{i}_IMG_{i:04d}.jpg", seed, base=(60 + 30 * k, 120, 90))
    return drop
