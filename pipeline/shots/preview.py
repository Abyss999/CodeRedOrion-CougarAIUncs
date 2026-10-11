"""Contact sheet: one image under every lighting preset (original first), for a quick visual check.

    python -m pipeline preview-lighting --image some.jpg --out sheet.jpg
"""
from __future__ import annotations
from pathlib import Path

from PIL import Image, ImageDraw

from ..transformation.lighting_aug import load_presets, variant


def contact_sheet(image: Path, out: Path, tile: int = 256, seed: int = 0, presets: list[str] | None = None) -> Path:
    specs = load_presets()
    names = presets or list(specs)
    base = Image.open(image).convert("RGB")
    base.thumbnail((tile, tile))
    tiles = [("original", base)] + [(n, variant(base, n, specs[n], seed)[0]) for n in names]
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile, rows * (tile + 22)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, (n, t) in enumerate(tiles):
        x, y = (i % cols) * tile, (i // cols) * (tile + 22)
        sheet.paste(t, (x + (tile - t.width) // 2, y + 22 + (tile - t.height) // 2))
        d.text((x + 6, y + 5), n, fill=(235, 235, 235))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    return out
