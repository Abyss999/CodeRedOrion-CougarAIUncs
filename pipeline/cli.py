"""python -m pipeline <command> [...]   (run from the repo root with the project venv)

  fetch-dafif       --out DIR [--fresh-days 1,2,3] [--spoiled-days 9,10,11] [--max-per-cell 300] [--max-side 1280]
  fetch-meatscan    --out DIR [--per-class 450] [--max-side 1280] [--workers 8]   (range reads; needs pip unrar-cffi)
  ingest-dataset    --zip FILE | --dir DIR  --name NAME  [--adapter agrifreshnet|folders|meatscan|dafif]
  prepare           [--extra-sources ml/yolo/sources.json] [--replace] [-- prepare_dataset args]
  augment-lighting  [--per-image 2] [--presets cool,bright,...|all] [--seed 0] [--max-side 1280] [--replace]
  ingest-receipts   [--engine fake|glm|service] [--timeout S] [--service-url URL] [--watch SECONDS]
  preview-lighting  --image FILE --out FILE.jpg
  run-all           --zip FILE --name NAME [--adapter ...] [--per-image 2] [--replace]

All data lives under pipeline/data/ (or --data-root / $PIPELINE_DATA). See docs/PIPELINE.md.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from . import config


def _p(x):
    print(json.dumps(x, indent=2, default=str))


def _curation(a) -> dict:
    return dict(specimen_groups=True if a.specimen_groups else None, exclude_source_augs=a.exclude_source_augs,
                max_per_cell=a.max_per_cell)


def _ingest(a, dirs):
    from .ingestion import datasets
    if bool(a.zip) == bool(a.dir):
        sys.exit("pass exactly one of --zip or --dir")
    if a.zip:
        return datasets.ingest_zip(Path(a.zip), a.name, a.adapter, dirs, keep_raw=not a.drop_raw, **_curation(a))
    from .ingestion.ledger import Ledger
    led = Ledger(dirs["staged"] / "ledger.sqlite")
    try:
        return datasets.ingest(Path(a.dir), a.name, a.adapter, dirs["staged"], led, **_curation(a))
    finally:
        led.close()


def _prepare(a, dirs):
    from .transformation.stage import prepare
    return prepare(dirs["staged"], Path(a.out) if a.out else dirs["prepared"],
                   [Path(e) for e in a.extra_sources], a.replace, a.prepare_args)


def _augment(a, dirs):
    from .transformation.lighting_aug import augment
    return augment(Path(a.src) if a.src else dirs["prepared"], Path(a.out) if a.out else dirs["augmented"],
                   a.per_image, a.presets.split(",") if a.presets else None, a.seed, a.max_side, a.replace,
                   not a.no_crops)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", help="default pipeline/data or $PIPELINE_DATA")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("fetch-dafif", help="download the DaFiF fish images for the kept days (Mendeley, CC BY 4.0)")
    s.add_argument("--out", required=True)
    s.add_argument("--fresh-days", default="1,2,3"); s.add_argument("--spoiled-days", default="9,10,11")
    s.add_argument("--max-per-cell", type=int, default=300); s.add_argument("--max-side", type=int, default=1280)
    s.add_argument("--workers", type=int, default=6)

    s = sub.add_parser("fetch-meatscan", help="fetch MeatScan originals by HTTP range reads (Zenodo, CC BY 4.0; never the 25 GB RAR)")
    s.add_argument("--out", required=True)
    s.add_argument("--per-class", type=int, default=450, help="originals fetched per class (ingest then caps per cell)")
    s.add_argument("--max-side", type=int, default=1280)
    s.add_argument("--workers", type=int, default=8)

    s = sub.add_parser("ingest-dataset", help="extract + stage a dataset drop")
    s.add_argument("--zip"); s.add_argument("--dir"); s.add_argument("--name", required=True)
    s.add_argument("--adapter", default="folders", choices=["agrifreshnet", "folders", "meatscan", "dafif"])
    s.add_argument("--drop-raw", action="store_true", help="delete the extracted copy after staging")
    s.add_argument("--specimen-groups", action="store_true",
                   help="group by specimen (cross-stage pHash) / capture session in the staged names (agrifreshnet); same as PIPELINE_SPECIMEN_GROUPS=1")
    s.add_argument("--exclude-source-augs", action="store_true", help="skip the dataset's own aug_<n>_<original> files")
    s.add_argument("--max-per-cell", type=int, default=None,
                   help="keep at most N images per class x freshness, round-robin over split units")

    s = sub.add_parser("prepare", help="merge staged datasets with ml/yolo/prepare_dataset.py")
    s.add_argument("--out"); s.add_argument("--extra-sources", action="append", default=[])
    s.add_argument("--replace", action="store_true")
    s.add_argument("prepare_args", nargs=argparse.REMAINDER, help="after --, passed to prepare_dataset.py")

    s = sub.add_parser("augment-lighting", help="add lighting variants to train/val (separate step)")
    s.add_argument("--src"); s.add_argument("--out")
    s.add_argument("--per-image", type=int, default=2)
    s.add_argument("--presets", help="default: cool,bright,shadow,spot. low/warm/mixed are opt-in; 'all' = every preset")
    s.add_argument("--seed", type=int, default=0); s.add_argument("--max-side", type=int, default=1280)
    s.add_argument("--no-crops", action="store_true"); s.add_argument("--replace", action="store_true")

    s = sub.add_parser("ingest-receipts", help="process incoming/receipts with OCR")
    s.add_argument("--engine", default="fake", choices=["fake", "glm", "service"])
    s.add_argument("--timeout", type=float, default=config.OCR_TIMEOUT_S)
    s.add_argument("--service-url", default=config.ML_SERVICE_URL)
    s.add_argument("--watch", type=float, default=0, help="poll every N seconds (default: one pass)")

    s = sub.add_parser("preview-lighting", help="contact sheet of every preset")
    s.add_argument("--image", required=True); s.add_argument("--out", required=True)
    s.add_argument("--seed", type=int, default=0)

    s = sub.add_parser("run-all", help="ingest-dataset + prepare + augment-lighting")
    s.add_argument("--zip", required=True); s.add_argument("--name", required=True)
    s.add_argument("--adapter", default="folders", choices=["agrifreshnet", "folders", "meatscan", "dafif"])
    s.add_argument("--per-image", type=int, default=2); s.add_argument("--replace", action="store_true")

    a = ap.parse_args(argv)
    dirs = config.data_dirs(Path(a.data_root) if a.data_root else None)
    if getattr(a, "prepare_args", None) and a.prepare_args[0] == "--":
        a.prepare_args = a.prepare_args[1:]

    if a.cmd == "fetch-dafif":
        from .ingestion.fetch import fetch_dafif
        days = lambda v: tuple(int(x) for x in v.split(",") if x)  # noqa: E731
        _p(fetch_dafif(Path(a.out), days(a.fresh_days), days(a.spoiled_days), a.max_per_cell, a.max_side, a.workers))
        return
    if a.cmd == "fetch-meatscan":
        from .ingestion.fetch import fetch_meatscan
        _p(fetch_meatscan(Path(a.out), a.per_class, a.max_side, a.workers))
        return
    if a.cmd == "ingest-dataset":
        _p(_ingest(a, dirs))
    elif a.cmd == "prepare":
        _p(_prepare(a, dirs))
    elif a.cmd == "augment-lighting":
        _p(_augment(a, dirs))
    elif a.cmd == "ingest-receipts":
        from .ingestion import receipts
        kw = dict(engine=a.engine, timeout_s=a.timeout, service_url=a.service_url)
        if a.watch:
            receipts.watch(dirs, a.watch, **kw)
        else:
            _p(receipts.process_inbox(dirs, **kw))
    elif a.cmd == "preview-lighting":
        from .shots.preview import contact_sheet
        print(contact_sheet(Path(a.image), Path(a.out), seed=a.seed))
    elif a.cmd == "run-all":
        from .ingestion import datasets
        from .transformation.lighting_aug import augment
        from .transformation.stage import prepare
        _p({"ingest": datasets.ingest_zip(Path(a.zip), a.name, a.adapter, dirs),
            "prepare": {k: v for k, v in prepare(dirs["staged"], dirs["prepared"], replace=a.replace).items()
                        if k != "classes_unmapped_skipped"},
            "augment": augment(dirs["prepared"], dirs["augmented"], a.per_image, replace=a.replace)})


if __name__ == "__main__":
    main()
