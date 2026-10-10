"""Two-stage inference: item detector (food NAME) -> per-crop fresh/spoiled classifier.

GPU-side. `ultralytics` is imported lazily inside TwoStage.load(), so importing this module is cheap
and safe on the VPS. Used by ml/serve (YoloDetector) and by export_predictions.py.
"""
from __future__ import annotations
import os
from pathlib import Path

try:
    from yolo import taxonomy as T  # when ml/ is on sys.path (serve, tests)
except ImportError:  # run as a script from ml/yolo
    import taxonomy as T  # type: ignore


class TwoStage:
    def __init__(self, det_weights: str, cls_weights: str | None = None, conf: float = 0.25,
                 imgsz: int = 640, spoiled_threshold: float = 0.5, device: str | None = None):
        self.det_weights, self.cls_weights = det_weights, cls_weights
        self.conf, self.imgsz, self.spoiled_threshold = conf, imgsz, spoiled_threshold
        self.device = device
        self._det = self._cls = None

    @property
    def model_id(self) -> str:
        d = Path(self.det_weights).name
        return f"yolo:{d}" + (f"+{Path(self.cls_weights).name}" if self.cls_weights else "")

    def load(self):
        if self._det is None:
            from ultralytics import YOLO  # lazy: heavy
            self._det = YOLO(self.det_weights)
            if self.cls_weights:
                self._cls = YOLO(self.cls_weights)
        return self

    def _spoiled_prob(self, crop) -> float:
        r = self._cls.predict(crop, imgsz=224, verbose=False, device=self.device)[0]
        names = {int(k): v for k, v in r.names.items()}
        idx = next((k for k, v in names.items() if v == "spoiled"), None)
        return float(r.probs.data[idx]) if idx is not None else 0.0

    def predict(self, image) -> list[dict]:
        """image: PIL.Image. Returns [{name, category, freshness, confidence, bbox:[x1,y1,x2,y2]}]."""
        from PIL import Image  # noqa
        self.load()
        image = image.convert("RGB")
        r = self._det.predict(image, conf=self.conf, imgsz=self.imgsz, verbose=False, device=self.device)[0]
        out = []
        for xyxy, c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
            name = r.names[int(k)]
            fresh = "fresh"
            if self._cls is not None:
                x1, y1, x2, y2 = [int(v) for v in xyxy]
                crop = image.crop((x1, y1, max(x2, x1 + 2), max(y2, y1 + 2)))
                fresh = "spoiled" if self._spoiled_prob(crop) >= self.spoiled_threshold else "fresh"
            out.append({"name": name, "category": T.category_for(name), "freshness": fresh,
                        "confidence": round(float(c), 4), "bbox": [round(v, 1) for v in xyxy]})
        out.sort(key=lambda d: -d["confidence"])
        return out

    @classmethod
    def from_env(cls):
        w = os.environ.get("YOLO_WEIGHTS")
        if not w:
            raise RuntimeError("YOLO_WEIGHTS is not set")
        return cls(w, os.environ.get("FRESHNESS_WEIGHTS") or None,
                   conf=float(os.environ.get("YOLO_CONF", "0.25")),
                   spoiled_threshold=float(os.environ.get("SPOILED_THRESHOLD", "0.5")),
                   device=os.environ.get("YOLO_DEVICE") or None)
