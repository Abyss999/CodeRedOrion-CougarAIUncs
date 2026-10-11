"""Perceptual hashing for near-duplicate detection (ML-21). numpy + Pillow only (no imagehash dependency).

phash64: 32x32 grey -> 2-D DCT -> top-left 8x8 block -> bit = coeff > median (DC excluded from the median).
dhash64: 9x8 grey, bit = left pixel > right pixel (a different signal, used as an independent check).
Hamming distance <= 6 on 64 bits is the conventional "same picture" threshold.
"""
from __future__ import annotations
import numpy as np
from PIL import Image

_N = 32
_DCT = np.cos(np.pi / _N * (np.arange(_N)[None, :] + 0.5) * np.arange(_N)[:, None]).astype(np.float64)
_POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def _grey(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    try:
        img.draft("L", (size[0] * 4, size[1] * 4))      # cheap JPEG downscale
    except Exception:
        pass
    return np.asarray(img.convert("L").resize(size, Image.LANCZOS), dtype=np.float64)


def _pack(bits: np.ndarray) -> int:
    v = 0
    for b in bits.ravel():
        v = (v << 1) | int(b)
    return v


def phash64(img: Image.Image) -> int:
    a = _grey(img, (_N, _N))
    d = _DCT @ a @ _DCT.T
    blk = d[:8, :8]
    med = np.median(blk.ravel()[1:])
    return _pack(blk > med)


def dhash64(img: Image.Image) -> int:
    a = _grey(img, (9, 8))
    return _pack(a[:, 1:] > a[:, :-1])


def near_pairs(hashes: list[int], thresh: int = 6, chunk: int = 256):
    """Yield (i, j) i<j with Hamming distance <= thresh."""
    h = np.array(hashes, dtype=np.uint64)
    n = len(h)
    for s in range(0, n, chunk):
        x = h[s:s + chunk, None] ^ h[None, :]
        d = _POP[x.view(np.uint8).reshape(x.shape[0], n, 8)].sum(axis=2)
        ii, jj = np.nonzero(d <= thresh)
        for i, j in zip(ii, jj):
            if s + i < j:
                yield int(s + i), int(j)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
