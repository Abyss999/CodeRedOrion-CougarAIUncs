#!/usr/bin/env python
"""Run the trained two-stage model over heldout_gt.jsonl images and write predictions JSONL
(one line per image) in the ML QA eval format:

  {"image": str, "lighting": "normal"|"low"|"warm",
   "predictions": [{"name","category","freshness","confidence","bbox":[x1,y1,x2,y2]}]}

Usage: python export_predictions.py --data /content/fwr_data --det runs/det/weights/best.pt \
           --cls runs/cls/weights/best.pt --out predictions.jsonl
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from infer import TwoStage  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="dataset dir produced by prepare_dataset.py")
    ap.add_argument("--det", required=True)
    ap.add_argument("--cls", default=None)
    ap.add_argument("--out", default="predictions.jsonl")
    ap.add_argument("--conf", type=float, default=0.10, help="low conf so QA can sweep thresholds")
    ap.add_argument("--spoiled-threshold", type=float, default=0.5)
    ap.add_argument("--semi-fresh-threshold", type=float, default=0.5)
    ap.add_argument("--device", default=None, help="e.g. mps, cpu, 0 (default: ultralytics picks)")
    a = ap.parse_args(argv)
    from PIL import Image
    ts = TwoStage(a.det, a.cls, conf=a.conf, spoiled_threshold=a.spoiled_threshold,
                  semi_fresh_threshold=a.semi_fresh_threshold, device=a.device).load()
    data = Path(a.data)
    n = 0
    with open(a.out, "w") as f:
        for line in open(data / "heldout_gt.jsonl"):
            g = json.loads(line)
            preds = ts.predict(Image.open(data / g["image"]))
            f.write(json.dumps({"image": g["image"], "lighting": g["lighting"], "predictions": preds}) + "\n")
            n += 1
    print(f"wrote {n} lines to {a.out}")


if __name__ == "__main__":
    main()
