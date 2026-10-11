"""DaFiF: Dataset for Fish's Freshness Problems (Mendeley Data v1, doi:10.17632/vx4ptwk3pb.1). CC BY 4.0.
Prasetyo et al., "DaFiF: A complete dataset for fish's freshness problems", Data in Brief 57 (2024) 111016.

Mackerel (Makarel), tilapia (Mujair) and tuna (Tongkol), 10 fish per species kept on ice for 11 days
(19-29 Jan 2024), photographed on both sides in two daily sessions. The release has no freshness labels
for images, only the storage day, so `pipeline fetch-dafif` (see fetch.py) labels by day:
days 1-3 = fresh, days 9-11 = spoiled, days 4-8 dropped as ambiguous (data owner's rule, 2026-10-10).

`fetch-dafif` writes raw/<name>/fish__<freshness>/<species>_s<session>_d<day>__<original>.jpg. The same ten fish
of a species appear on every day, so `group_of` groups by species + session ONLY (not day): every photo of
one batch of fish, fresh or spoiled, lands in one split.
"""
from __future__ import annotations
import re

from .generic import parse_dir as _parse_generic

LICENCE = "CC BY 4.0"
VERSION = "v1"
URL = "https://data.mendeley.com/datasets/vx4ptwk3pb/1"
DOI = "10.17632/vx4ptwk3pb.1"
CITATION = ("Prasetyo, Suciati, Sutramiani, Adiananda, Dewi. Dataset for Fish's Freshness Problems. Mendeley Data, v1, "
            "doi:10.17632/vx4ptwk3pb.1. CC BY 4.0. Article: Data in Brief 57 (2024) 111016.")
_BATCH = re.compile(r"^(?P<species>[a-z]+)_s(?P<session>\d)_d\d+__", re.I)


def parse_dir(dirname: str) -> dict | None:
    d = _parse_generic(dirname)
    if d and d["source_freshness"] is None:
        return None
    return d


def group_of(cls_dir: str, stem: str) -> tuple[str, bool]:
    m = _BATCH.match(stem)
    batch = f"{m.group('species').lower()}_s{m.group('session')}" if m else stem
    return f"fish__dafif_{batch}", False
