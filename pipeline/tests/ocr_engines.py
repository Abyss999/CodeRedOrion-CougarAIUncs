"""Test OCR engine factory run inside the spawned worker (must be importable)."""
import time
from pathlib import Path


def behave():
    def run(path):
        txt = Path(path).with_suffix(".txt").read_text()
        if "HANG" in txt:
            time.sleep(60)
        if "BOOM" in txt:
            raise RuntimeError("engine exploded")
        return txt
    return run
