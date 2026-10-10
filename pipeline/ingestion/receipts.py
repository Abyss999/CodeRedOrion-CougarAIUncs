"""Receipt inbox: incoming/receipts/* -> OCR (GLM-OCR / ML service / sidecar fake) -> deterministic
parser (ml/ocr/receipt_pipeline.parse_receipt_text) -> category cleanup -> processed outputs.

    processed/receipts/<id>.json     one receipt (lines + canonical/category per line, total, raw_text)
    processed/receipts.jsonl         same records, appended
    processed/receipt_lines.csv      one row per line item, appended (easy to load into a DB/sheet)
    processed/archive/<id><ext>      the original image (and its .txt sidecar, if any)
    processed/duplicates/            files whose content was already processed
    quarantine/<file> + .error.json  timeout / invalid image / OCR failure / unsupported format

A quarantined file is retried if it is dropped into the inbox again; a processed one is not.
If the ML service is unreachable the pass stops and leaves files in the inbox (the next pass retries).
"""
from __future__ import annotations
import csv
import json
import shutil
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .. import config
from ..category_cleanup.names import clean
from ..timeout.worker import OcrFailed, OcrTimeout, OcrWorker
from .ledger import Ledger, sha1_file
from ocr.receipt_pipeline import parse_receipt_text  # noqa: E402  (ml/ on sys.path via config)

KIND = "receipt"
UNSUPPORTED = {".heic", ".heif", ".pdf"}
LINE_COLS = ["receipt_id", "line_no", "name", "quantity", "price", "canonical", "category", "match", "source_file"]
ENGINES = {"fake": "pipeline.timeout.worker:sidecar_engine", "glm": "pipeline.timeout.worker:glm_engine"}
MODEL_IDS = {"fake": "sidecar-text", "glm": "zai-org/GLM-OCR"}


class ServiceUnavailable(RuntimeError):
    """The ML service can't be reached: not the file's fault, so the pass stops and files stay in the inbox."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ServiceEngine:
    """POST the image to the ML service (ml/serve) /ocr; it runs GLM-OCR + the parser on the GPU box."""

    def __init__(self, url: str, timeout_s: float):
        if not url:
            raise ValueError("--engine service needs ML_SERVICE_URL (or --service-url)")
        self.url, self.timeout_s = url.rstrip("/") + "/ocr", timeout_s

    def run(self, path: Path) -> dict:
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{path.name}\"\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n").encode() + path.read_bytes() + \
            f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return json.load(r)
        except TimeoutError as e:
            raise OcrTimeout(f"ML service did not answer within {self.timeout_s:.0f}s") from e
        except urllib.error.HTTPError as e:
            raise OcrFailed(f"ML service HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from e
        except (urllib.error.URLError, OSError) as e:
            if "timed out" in str(e):
                raise OcrTimeout(f"ML service did not answer within {self.timeout_s:.0f}s") from e
            raise ServiceUnavailable(f"ML service unreachable at {self.url}: {e}") from e

    def close(self):
        pass


def _quarantine(path: Path, qdir: Path, code: str, message: str) -> Path:
    qdir.mkdir(parents=True, exist_ok=True)
    dst = qdir / path.name
    if dst.exists():
        dst = qdir / f"{path.stem}.{int(time.time())}{path.suffix}"
    shutil.move(str(path), dst)
    side = path.with_suffix(".txt")
    if side.exists():
        shutil.move(str(side), dst.with_suffix(".txt"))
    dst.with_name(dst.name + ".error.json").write_text(
        json.dumps({"file": path.name, "code": code, "message": message, "at": _now()}, indent=2) + "\n")
    return dst


def _record(rid: str, src: Path, engine: str, model: str, raw_text: str, parsed: dict) -> dict:
    lines = []
    for i, l in enumerate(parsed.get("lines", [])):
        name = str(l.get("name", ""))
        lines.append({"line_no": i, "name": name, "quantity": l.get("quantity"), "price": l.get("price"),
                      **clean(name)})
    return {"receipt_id": rid, "source_file": src.name, "processed_at": _now(), "engine": engine,
            "model": model, "total": parsed.get("total"), "n_lines": len(lines), "lines": lines,
            "raw_text": raw_text}


def _write_outputs(rec: dict, pdir: Path):
    (pdir / "receipts").mkdir(parents=True, exist_ok=True)
    (pdir / "receipts" / f"{rec['receipt_id']}.json").write_text(json.dumps(rec, indent=2) + "\n")
    with open(pdir / "receipts.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    lpath = pdir / "receipt_lines.csv"
    new = not lpath.exists()
    with open(lpath, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LINE_COLS)
        if new:
            w.writeheader()
        for l in rec["lines"]:
            w.writerow({"receipt_id": rec["receipt_id"], "source_file": rec["source_file"],
                        **{k: l.get(k) for k in LINE_COLS if k not in ("receipt_id", "source_file")}})


def _archive(path: Path, dst_dir: Path, stem: str):
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), dst_dir / f"{stem}{path.suffix.lower()}")
    side = path.with_suffix(".txt")
    if side.exists():
        shutil.move(str(side), dst_dir / f"{stem}.txt")


def make_engine(engine: str, timeout_s: float, service_url: str = "", load_grace_s: float = 600.0, **kw):
    if engine == "service":
        return ServiceEngine(service_url or config.ML_SERVICE_URL, timeout_s)
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}; choose fake|glm|service")
    return OcrWorker(ENGINES[engine], timeout_s, load_grace_s=load_grace_s, **kw)


def process_inbox(dirs: dict[str, Path], engine: str = "fake", timeout_s: float | None = None,
                  service_url: str = "", engine_obj=None, load_grace_s: float = 600.0) -> dict:
    """One pass over incoming/receipts. Returns counts. `engine_obj` lets tests inject an engine."""
    inbox = dirs["incoming"] / "receipts"
    inbox.mkdir(parents=True, exist_ok=True)
    pdir, qdir = dirs["processed"], dirs["quarantine"]
    timeout_s = timeout_s if timeout_s is not None else config.OCR_TIMEOUT_S
    files = sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() != ".txt"
                   and not p.name.startswith("."))
    counts: Counter = Counter()
    if not files:
        return dict(counts)
    ledger = Ledger(pdir / "ledger.sqlite")
    eng = engine_obj
    try:
        for p in files:
            ext = p.suffix.lower()
            if ext in UNSUPPORTED or ext not in config.IMG_EXT:
                _quarantine(p, qdir, "unsupported_format", f"{ext or 'no extension'} is not a supported image type "
                            f"({', '.join(sorted(config.IMG_EXT))}); convert it to JPEG/PNG first")
                counts["quarantined"] += 1
                continue
            sha = sha1_file(p)
            rid = sha[:16]
            if ledger.status(KIND, sha) == "done":
                _archive(p, pdir / "duplicates", f"{rid}.{int(time.time())}")
                counts["duplicates"] += 1
                continue
            try:
                with Image.open(p) as im:
                    im.verify()
            except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as e:
                _quarantine(p, qdir, "invalid_image", f"{e.__class__.__name__}: {e}")
                ledger.mark(KIND, sha, "quarantined", "invalid_image")
                counts["quarantined"] += 1
                continue
            if eng is None:
                eng = make_engine(engine, timeout_s, service_url, load_grace_s)
            try:
                if isinstance(eng, ServiceEngine):
                    resp = eng.run(p)
                    raw = resp.get("raw_text", "")
                    parsed = {"lines": resp.get("lines", []), "total": resp.get("total")}
                    model = "ml-service:/ocr"
                else:
                    raw = eng.run(str(p))
                    parsed = parse_receipt_text(raw)
                    model = MODEL_IDS.get(engine, engine)
            except OcrTimeout as e:
                _quarantine(p, qdir, "ocr_timeout", str(e))
                ledger.mark(KIND, sha, "quarantined", "ocr_timeout")
                counts["quarantined"] += 1
                continue
            except ServiceUnavailable as e:
                counts["stopped"] = str(e)  # leave this and the remaining files in the inbox
                break
            except OcrFailed as e:
                _quarantine(p, qdir, "ocr_failed", str(e))
                ledger.mark(KIND, sha, "quarantined", "ocr_failed")
                counts["quarantined"] += 1
                continue
            rec = _record(rid, p, engine, model, raw, parsed)
            _write_outputs(rec, pdir)
            _archive(p, pdir / "archive", rid)
            ledger.mark(KIND, sha, "done", rid)
            counts["processed"] += 1
            counts["lines"] += rec["n_lines"]
    finally:
        if eng is not None and engine_obj is None:
            eng.close()
        ledger.close()
    return dict(counts)


def watch(dirs: dict[str, Path], every_s: float, **kw):
    """Poll the inbox forever (Ctrl-C to stop). Each pass prints its counts as one JSON line."""
    while True:
        c = process_inbox(dirs, **kw)
        if c:
            print(json.dumps({"at": _now(), **c}), flush=True)
        time.sleep(every_s)
