"""Lighting tagging + synthetic lighting variants. Light deps only (Pillow, numpy)."""
from __future__ import annotations
import numpy as np
from PIL import Image

LOW_LUMA = 70.0      # mean luma (0-255) below this -> "low"
WARM_RB = 1.35       # mean(R)/mean(B) above this -> "warm"


def measure(img: Image.Image) -> tuple[float, float]:
    a = np.asarray(img.convert("RGB").resize((96, 96)), dtype=np.float32)
    r, g, b = a[..., 0].mean(), a[..., 1].mean(), a[..., 2].mean()
    return float(0.299 * r + 0.587 * g + 0.114 * b), float(r / max(b, 1.0))


def tag(img: Image.Image) -> str:
    luma, rb = measure(img)
    if luma < LOW_LUMA:
        return "low"
    if rb > WARM_RB:
        return "warm"
    return "normal"


def synth(img: Image.Image, kind: str, seed: int = 0) -> Image.Image:
    """kind: 'low' (dim + sensor noise) or 'warm' (tungsten-like cast)."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    if kind == "low":
        a = a * 0.35
        a = a + np.random.default_rng(seed).normal(0, 3.0, a.shape)
    elif kind == "warm":
        a = a * np.array([1.25, 1.0, 0.7], dtype=np.float32)
    else:
        raise ValueError(kind)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
