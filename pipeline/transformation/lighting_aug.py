"""Lighting augmentation: a SEPARATE step that turns prepared/ into augmented/ by adding photometric
variants (dim fridge, tungsten, LED/fluorescent, overexposed, shelf shadow, top spot light, mixed).

    augmented/                      full YOLO dataset; train with `train.py --data augmented`
      images|labels|freshness/{train,val}/<stem>__lt_<preset>.*   new variants (labels copied)
      cls/{train,val}/<freshness>/<stem>__lt_<preset>.jpg         crop variants for the classifier
      augment_manifest.csv          image, split, variant_of, preset, params (json)
      augment_report.json           counts per split/preset

Only train and val are augmented. heldout is linked/copied byte-for-byte so ML QA's normal/low/warm
gates (built with ml/yolo/lighting.synth) stay comparable across runs. The edits are photometric
only, so boxes, freshness sidecars and crop labels are unchanged. numpy + Pillow only.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config

PRESETS_FILE = config.PIPELINE / "shots" / "presets.json"
SPLITS = ("train", "val")
# `low`, `warm` and `mixed` (dim + warm/cool cast) are the same families as the synthetic low/warm
# held-out copies that ml/yolo/lighting.synth builds. Training on them and then scoring on those
# copies is train-on-test-family, so they are OPT-IN (--presets low,warm,mixed or --presets all).
# A model trained on them gets no lighting sign-off from synthetic held-out rows (ML-17, ML-22).
HELDOUT_FAMILY_PRESETS = ("low", "warm", "mixed")


def default_presets(specs: dict) -> list[str]:
    return [k for k in specs if k not in HELDOUT_FAMILY_PRESETS]


def load_presets(path: Path = PRESETS_FILE) -> dict:
    return {k: v for k, v in json.loads(Path(path).read_text()).items() if not k.startswith("_")}


def kelvin_rgb(k: float) -> np.ndarray:
    """Approximate RGB of a black body at k kelvin (Tanner Helland fit), 0-255."""
    t = k / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492
    b = 255.0 if t >= 66 else 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    return np.clip(np.array([r, g, b], dtype=np.float32), 1, 255)


def cast_gains(kelvin: float, strength: float) -> np.ndarray:
    g = kelvin_rgb(kelvin) / kelvin_rgb(6500)
    g = g / g[1]  # keep green (most of the luma) fixed -> brightness roughly unchanged
    return 1.0 + strength * (g - 1.0)


def _u(rng, lo_hi):
    lo, hi = lo_hi
    return float(rng.uniform(lo, hi))


def _sample(rng, spec: dict) -> dict:
    return {k: (rng.choice(v) if isinstance(v[0], str) else round(_u(rng, v), 4)) for k, v in spec.items()}


def apply(img: Image.Image, preset: str, params: dict, seed: int = 0) -> Image.Image:
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w = a.shape[:2]
    rng = np.random.default_rng(seed)
    if preset == "low":
        a = 255.0 * (a / 255.0) ** params["gamma"] * params["gain"]
        a = a + rng.normal(0, params["noise"], a.shape)  # sensor noise; relatively stronger in the dark
    elif preset == "warm":
        a = a * cast_gains(params["kelvin"], params["strength"]) * params["gain"]
    elif preset == "cool":
        a = a * cast_gains(params["kelvin"], params["strength"]) * np.array([1, params["green"], 1], np.float32)
        a = a * params["gain"]
    elif preset == "bright":
        a = a * params["gain"]
    elif preset == "shadow":
        ang = rng.uniform(0, 2 * math.pi)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        proj = (xx / max(w - 1, 1) - 0.5) * math.cos(ang) + (yy / max(h - 1, 1) - 0.5) * math.sin(ang)
        edge = rng.uniform(-0.2, 0.2)
        ramp = np.clip((proj - edge) / max(params["softness"], 1e-3) + 0.5, 0, 1)
        a = a * (1.0 - params["depth"] * ramp)[..., None]
    elif preset == "spot":
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.hypot(xx / w - params["cx"], yy / h - params["cy"]) / math.hypot(1, 1.2)
        a = a * np.clip(1.0 - params["falloff"] * (d / d.max()) ** 2 * 1.6, 0.15, 1.0)[..., None]
    elif preset == "mixed":
        a = a * params["low_gain"]
        k, s = (3000, 0.6) if params["cast"] == "warm" else (8500, 0.6)
        a = a * cast_gains(k, s) + rng.normal(0, 2.5, a.shape)
    else:
        raise ValueError(f"unknown preset {preset!r}")
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def variant(img: Image.Image, preset: str, spec: dict, seed: int) -> tuple[Image.Image, dict]:
    rng = np.random.default_rng(seed)
    params = _sample(rng, spec)
    return apply(img, preset, params, seed), params


def _seed(base: int, *parts: str) -> int:
    return (int(hashlib.sha1(":".join(parts).encode()).hexdigest()[:8], 16) + base) % (2 ** 32)


def _link_tree(src: Path, dst: Path):
    """Mirror src into dst with hardlinks (no extra disk); copy when linking is not possible."""
    for p in src.rglob("*"):
        t = dst / p.relative_to(src)
        if p.is_dir():
            t.mkdir(parents=True, exist_ok=True)
            continue
        t.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(p, t)
        except OSError:
            shutil.copy2(p, t)


def _shrink(img: Image.Image, max_side: int) -> Image.Image:
    if max_side and max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    return img


def augment(src: Path, out: Path, per_image: int = 2, presets: list[str] | None = None, seed: int = 0,
            max_side: int = 1280, replace: bool = False, include_crops: bool = True) -> dict:
    if not (src / "data.yaml").exists():
        raise SystemExit(f"{src} is not a prepared dataset (no data.yaml); run `prepare` first")
    if out.exists() and any(out.iterdir()):
        if not replace:
            raise SystemExit(f"{out} is not empty; pass --replace to rebuild it")
        shutil.rmtree(out)
    specs = load_presets()
    names = list(specs) if presets and list(presets) == ["all"] else (presets or default_presets(specs))
    bad = [n for n in names if n not in specs]
    if bad:
        raise SystemExit(f"unknown presets {bad}; known: {list(specs)}")
    per_image = max(0, min(per_image, len(names)))
    _link_tree(src, out)
    # data.yaml path must point at the new root
    y = (out / "data.yaml")
    txt = y.read_text()
    y.unlink()  # break the hardlink before rewriting
    y.write_text("\n".join(f"path: {out.resolve()}" if l.startswith("path:") else l for l in txt.splitlines()) + "\n")

    counts: Counter = Counter()
    rows = []
    for split in SPLITS:
        idir = src / "images" / split
        if not idir.is_dir():
            continue
        for ip in sorted(idir.iterdir()):
            if "__lt_" in ip.stem:
                continue
            chosen = np.random.default_rng(_seed(seed, "pick", ip.name)).choice(names, per_image, replace=False)
            img = None
            for preset in chosen:
                if img is None:
                    img = _shrink(Image.open(ip).convert("RGB"), max_side)
                v, params = variant(img, preset, specs[preset], _seed(seed, preset, ip.name))
                stem = f"{ip.stem}__lt_{preset}"
                v.save(out / "images" / split / f"{stem}.jpg", quality=92)
                for sub in ("labels", "freshness"):
                    s = src / sub / split / f"{ip.stem}.txt"
                    if s.exists():
                        shutil.copyfile(s, out / sub / split / f"{stem}.txt")
                rows.append({"image": f"images/{split}/{stem}.jpg", "split": split, "kind": "detector",
                             "variant_of": f"images/{split}/{ip.name}", "preset": preset,
                             "params": json.dumps(params, sort_keys=True)})
                counts[f"{split}:{preset}"] += 1
                counts[f"{split}:images"] += 1
        cdir = src / "cls" / split
        if include_crops and cdir.is_dir():
            for cp in sorted(cdir.rglob("*.jpg")):
                if "__lt_" in cp.stem:
                    continue
                chosen = np.random.default_rng(_seed(seed, "pick", "cls", cp.name)).choice(names, per_image, replace=False)
                crop = Image.open(cp).convert("RGB")
                for preset in chosen:
                    v, params = variant(crop, preset, specs[preset], _seed(seed, preset, "cls", cp.name))
                    rel = cp.relative_to(src).with_name(f"{cp.stem}__lt_{preset}.jpg")
                    v.save(out / rel, quality=92)
                    rows.append({"image": str(rel), "split": split, "kind": "crop",
                                 "variant_of": str(cp.relative_to(src)), "preset": preset,
                                 "params": json.dumps(params, sort_keys=True)})
                    counts[f"{split}:crops"] += 1
    with open(out / "augment_manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image", "split", "kind", "variant_of", "preset", "params"])
        w.writeheader()
        w.writerows(rows)
    report = {"source": str(src), "per_image": per_image, "presets": names, "seed": seed,
              "max_side": max_side, "counts": dict(sorted(counts.items())), "heldout": "unchanged (linked)",
              "heldout_family_presets_used": [n for n in names if n in HELDOUT_FAMILY_PRESETS],
              "lighting_signoff": ("none from synthetic held-out rows: low/warm/mixed were used in training "
                                   "(only real low/warm images count, ML-17/ML-22)"
                                   if any(n in HELDOUT_FAMILY_PRESETS for n in names) else
                                   "n/a: no held-out-family preset used; synthetic low/warm held-out stays independent")}
    (out / "augment_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
