"""Paths and env knobs. Importing this puts ml/ and ml/yolo on sys.path so the pipeline reuses
taxonomy, lighting, prepare_dataset and the receipt parser instead of copying them."""
from __future__ import annotations
import os
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
REPO = PIPELINE.parent
ML = REPO / "ml"
for _p in (ML, ML / "yolo"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

DATA = Path(os.environ.get("PIPELINE_DATA", PIPELINE / "data"))


def data_dirs(root: Path | None = None) -> dict[str, Path]:
    r = Path(root) if root else DATA
    return {k: r / k for k in ("raw", "staged", "prepared", "augmented", "incoming", "processed", "quarantine")}


OCR_TIMEOUT_S = float(os.environ.get("OCR_TIMEOUT_S", "180"))
ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "")
MAX_EXTRACT_GB = float(os.environ.get("PIPELINE_MAX_EXTRACT_GB", "20"))
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
