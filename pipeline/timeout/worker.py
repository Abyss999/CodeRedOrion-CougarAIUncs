"""Per-item deadline for OCR engines that cannot be interrupted (GLM-OCR generate() on CPU/GPU).

OcrWorker keeps ONE child process alive with the engine loaded (model load is the slow part), sends
it one image path at a time, and waits up to `timeout_s`. On a hang it kills the child and starts a
fresh one, so one bad receipt costs one timeout, not the whole batch.

The engine is built inside the child from an importable factory string ("module:callable"), so
nothing heavy is imported in the parent.
"""
from __future__ import annotations
import importlib
import multiprocessing as mp
import time


class OcrTimeout(RuntimeError):
    pass


class OcrFailed(RuntimeError):
    pass


def _build(factory: str, kwargs: dict):
    mod, fn = factory.split(":")
    return getattr(importlib.import_module(mod), fn)(**kwargs)


def _serve(factory: str, kwargs: dict, conn):
    try:
        engine = _build(factory, kwargs)
    except Exception as e:  # report load failures on the first request
        engine, load_err = None, f"{e.__class__.__name__}: {e}"
    else:
        load_err = None
    while True:
        try:
            path = conn.recv()
        except EOFError:
            return
        if path is None:
            return
        if load_err:
            conn.send(("err", f"engine load failed: {load_err}"))
            continue
        try:
            conn.send(("ok", engine(path)))
        except Exception as e:
            conn.send(("err", f"{e.__class__.__name__}: {e}"))


class OcrWorker:
    def __init__(self, factory: str, timeout_s: float, load_grace_s: float = 600.0, **kwargs):
        """timeout_s: per-image deadline. load_grace_s: extra time allowed on the first image after a
        (re)start, because the engine (e.g. a 0.9B-param model) loads lazily inside the child."""
        self.factory, self.kwargs, self.timeout_s = factory, kwargs, timeout_s
        self.load_grace_s = load_grace_s
        self._ctx = mp.get_context("spawn")  # never fork a process that may hold CUDA/torch state
        self._proc = self._conn = None
        self.restarts = 0

    def _start(self):
        parent, child = self._ctx.Pipe()
        self._proc = self._ctx.Process(target=_serve, args=(self.factory, self.kwargs, child), daemon=True)
        self._proc.start()
        self._conn = parent

    def _kill(self):
        if self._proc is not None:
            self._proc.kill()
            self._proc.join(5)
        self._proc = self._conn = None

    def run(self, path: str) -> str:
        """Return OCR text for the image at `path`, or raise OcrTimeout / OcrFailed."""
        grace = 0.0
        if self._proc is None or not self._proc.is_alive():
            self._start()
            grace = self.load_grace_s
        try:
            self._conn.send(path)
            ready = self._conn.poll(self.timeout_s + grace)
        except (EOFError, OSError):  # child died before or while receiving
            ready = None
        if ready is False:
            self._kill()
            self.restarts += 1
            raise OcrTimeout(f"no result within {self.timeout_s:.0f}s")
        try:
            if ready is None:
                raise EOFError
            status, payload = self._conn.recv()
        except (EOFError, OSError):
            code = self._proc.exitcode if self._proc is not None else None
            self._kill()
            self.restarts += 1
            raise OcrFailed(f"OCR worker died (exit code {code})")
        if status != "ok":
            raise OcrFailed(payload)
        return payload

    def close(self):
        if self._conn is not None:
            try:
                self._conn.send(None)
                self._proc.join(5)
            except (BrokenPipeError, OSError):
                pass
        self._kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ----------------------------------------------------------------- engine factories (run in child)
def glm_engine(model_id: str | None = None):
    """GLM-OCR (zai-org/GLM-OCR) via ml/ocr/receipt_pipeline.GlmOcrEngine. GPU-side; heavy imports
    happen here, inside the worker process."""
    from pipeline import config  # noqa: F401  (sys.path)
    from PIL import Image
    from ocr.receipt_pipeline import GlmOcrEngine
    eng = GlmOcrEngine(model_id).load()
    return lambda path: eng.image_to_text(Image.open(path))


def sidecar_engine(delay_s: float = 0.0):
    """Test/CPU engine: returns the text of <image>.txt next to the image (raises if missing)."""
    from pathlib import Path

    def run(path):
        if delay_s:
            time.sleep(delay_s)
        p = Path(path).with_suffix(".txt")
        if not p.exists():
            raise FileNotFoundError(f"no sidecar text {p.name}")
        return p.read_text()
    return run
