#!/usr/bin/env python
"""Train detector (food names) + freshness classifier, then export held-out predictions.
GPU-side only. Equivalent to train_colab.ipynb.

  python train.py --data /content/fwr_data --epochs 80 --project /content/drive/MyDrive/fwr_runs/<RUN_ID> --resume

--resume makes the run restartable (Colab disconnects): each stage (det, cls) is skipped if its
<project>/<stage>/weights/last.pt is already finished, continued with YOLO(last.pt).train(resume=True) if it is
mid-training, and trained from scratch if there is no checkpoint. See docs/ML.md section 5.
"""
import argparse, os, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

DET_MODEL = "yolo26s.pt"      # detector; see docs/ML.md for the size trade-off
CLS_MODEL = "yolo26n-cls.pt"  # fresh/semi_fresh/spoiled crop classifier


def pick_device(requested: str = "auto") -> str:
    """auto -> cuda (device 0) if available, else mps, else cpu. Anything else is passed through."""
    if requested != "auto":
        return requested
    import torch
    if torch.cuda.is_available():
        return "0"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def ckpt_status(last: Path):
    """'none' | 'done' | 'partial' | 'corrupt' for an Ultralytics last.pt (verified on 8.4.175).
    Ultralytics saves last.pt every epoch with epoch=<i> plus optimizer state. After the final epoch,
    trainer.final_eval() calls strip_optimizer(last), which writes epoch=-1 and optimizer=None. resume_training()
    asserts 0 < ckpt.epoch+1 < epochs, so a complete but still UNSTRIPPED checkpoint raises "nothing to resume".
    A stripped (epoch=-1) one is worse: YOLO.train(resume=True) (engine/model.py) only warns "not a resumable training
    checkpoint" and silently starts a NEW training. The skip logic below is what prevents that silent retrain.
    Hence: epoch == -1 -> done. epoch+1 >= epochs while the optimizer is still there means the process died between the
    last epoch and final_eval(): also done; we strip it ourselves. Returns (status, epoch, epochs)."""
    if not last.exists():
        return "none", None, None
    import torch
    try:
        ck = torch.load(last, map_location="cpu", weights_only=False)
        ep, total = int(ck.get("epoch", -1)), int((ck.get("train_args") or {}).get("epochs", 0))
    except Exception as e:       # Drive can hold a half-written file if the VM died mid-save
        print(f"  {last} unreadable ({type(e).__name__}: {e})")
        return "corrupt", None, None
    if ep == -1:
        return "done", ep, total
    if ep + 1 >= total:
        return "finished_unstripped", ep, total
    return "partial", ep, total


def train_stage(name, model, project, resume, device, **kw):
    """Train one stage into <project>/<name>/. Returns (last.pt, best.pt, 'skipped'|'resumed'|'fresh')."""
    from ultralytics import YOLO
    wdir = Path(project) / name / "weights"
    last, best = wdir / "last.pt", wdir / "best.pt"
    if resume:
        st, ep, total = ckpt_status(last)
        if st == "corrupt" and best.exists():       # fall back to best.pt (also a full checkpoint while training)
            print(f"[{name}] last.pt unreadable, trying best.pt")
            st, ep, total = ckpt_status(best)
            if st == "partial":
                shutil.copy(best, last)
        if st == "finished_unstripped":
            from ultralytics.utils.torch_utils import strip_optimizer
            strip_optimizer(last)
            if best.exists():
                strip_optimizer(best)
            st = "done"
        if st == "done":
            print(f"[{name}] already finished ({last}); skipping training")
            if total and kw.get("epochs") and total != kw["epochs"]:
                print(f"[{name}] note: checkpoint was trained for {total} epochs, --epochs asks {kw['epochs']}; start a new RUN_ID to change it")
            return last, best, "skipped"
        if st == "partial":
            print(f"[{name}] resuming {last}: last completed epoch {ep + 1} of {total}")
            m = YOLO(str(last))
            # resume=True reads every hyperparameter from the checkpoint; only data/device/batch/imgsz can be overridden
            m.train(resume=True, data=kw["data"], device=device, batch=kw["batch"], imgsz=kw["imgsz"])
            return Path(m.trainer.last), Path(m.trainer.best), "resumed"
        print(f"[{name}] no usable checkpoint ({st}); training from scratch")
    m = YOLO(model)
    m.train(project=project, name=name, exist_ok=True, device=device, **kw)
    return Path(m.trainer.last), Path(m.trainer.best), "fresh"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--project", default="runs")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--cls-epochs", type=int, default=30)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--det-model", default=DET_MODEL)
    ap.add_argument("--cls-model", default=CLS_MODEL)
    ap.add_argument("--cls-batch", type=int, default=64)
    ap.add_argument("--weights", choices=("last", "best"), default="last",
                    help="checkpoint to export/evaluate. Default last: val has no potato or apple/spoiled "
                         "(ML-28), so val-based best-epoch selection is blind to them; train fixed epochs, use last.pt")
    ap.add_argument("--device", default="auto", help="auto (cuda, then mps, then cpu), or cpu / mps / 0 / 0,1")
    ap.add_argument("--resume", action="store_true",
                    help="restartable run: skip finished stages, resume unfinished ones from <project>/<stage>/weights/last.pt")
    ap.add_argument("--semi-fresh-threshold", type=float, default=float(os.environ.get("SEMI_FRESH_THRESHOLD", "0.5")),
                    help="P(semi_fresh) needed to label a crop semi_fresh in the exported predictions (env SEMI_FRESH_THRESHOLD, default 0.5)")
    ap.add_argument("--skip-cls", action="store_true")
    a = ap.parse_args(argv)
    from ultralytics import YOLO  # heavy, lazy
    data = Path(a.data)
    device = pick_device(a.device)
    print("device:", device)

    project = str(Path(a.project).resolve())     # absolute, so a resumed run finds the same folders
    det_last, det_best, how = train_stage("det", a.det_model, project, a.resume, device, data=str(data / "data.yaml"),
                                          epochs=a.epochs, imgsz=a.imgsz, batch=a.batch)
    det_pt = det_last if a.weights == "last" else det_best
    print(f"det {how}; val on {a.weights}:", YOLO(str(det_pt)).val(data=str(data / "data.yaml"), split="val", device=device).box.map50)
    print("exporting detector", a.weights, det_pt)

    cls_pt = None
    if not a.skip_cls:
        cls_last, cls_best, how = train_stage("cls", a.cls_model, project, a.resume, device, data=str(data / "cls"),
                                              epochs=a.cls_epochs, imgsz=224, batch=a.cls_batch)
        print(f"cls {how}")
        cls_pt = cls_last if a.weights == "last" else cls_best

    out = Path(project) / "export"; out.mkdir(parents=True, exist_ok=True)
    shutil.copy(det_pt, out / "detector.pt")
    if cls_pt:
        shutil.copy(cls_pt, out / "freshness.pt")
    from export_predictions import main as export
    export(["--data", str(data), "--det", str(out / "detector.pt"), "--out", str(out / "predictions.jsonl"),
            "--device", device, "--semi-fresh-threshold", str(a.semi_fresh_threshold)]
           + (["--cls", str(out / "freshness.pt")] if cls_pt else []))
    shutil.copy(data / "heldout_gt.jsonl", out / "heldout_gt.jsonl")
    shutil.copy(data / "heldout_manifest.csv", out / "heldout_manifest.csv")
    for extra in ("class_names.json", "dataset_report.json"):
        if (data / extra).exists():
            shutil.copy(data / extra, out / extra)
    print("artifacts in", out)


if __name__ == "__main__":
    main()
