"""Independent QA (food-main-mac) for PR #62: is PL-5 fixed on the REAL MeatScan data?

PL-5: MeatScan's CSV gives minute-resolution capture times (every Time_Captured ends in ':00'), so the 300 s
chained-session rule collapses the sampled 600 images into a handful of split units. The author's strict xfail in
qa_new_sources.py looks for the CSV at <repo>/../mldata, which does not exist from a worktree (wt/<name>/), so there
it silently SKIPS. These tests find mldata in any ancestor directory instead.

  <pipeline venv>/bin/python -m pytest pipeline/tests/qa_pr62_pl5.py -q
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pipeline.ingestion import fetch, meatscan


def _find(rel: str) -> Path | None:
    for p in Path(__file__).resolve().parents:
        c = p / "mldata" / rel
        if c.exists():
            return c
    return None


CSV = _find("raw/meatscan/MeatScan_Metadata.csv")
STAGED = _find("pipeline_data/staged/meatscan") or _find("qa62/pipeline_data/staged/meatscan")   # notebook-equivalent staging
GAP = 300


def _units(ts):
    ts = sorted(ts)
    return 1 + sum(1 for a, b in zip(ts, ts[1:]) if b - a > GAP)


def _t(r):
    return datetime.strptime(f"{r['Date_Captured']} {r['Time_Captured']}", "%Y-%m-%d %H:%M:%S").timestamp()


@pytest.mark.skipif(CSV is None, reason="real MeatScan CSV not downloaded")
def test_real_csv_is_minute_resolution():
    rows = meatscan.load_metadata(CSV)
    assert len(rows) == 6995
    assert {r["Time_Captured"][-3:] for r in rows.values()} == {":00"}


@pytest.mark.skipif(CSV is None, reason="real MeatScan CSV not downloaded")
def test_all_originals_chain_into_one_unit_per_day():
    rows = meatscan.load_metadata(CSV)
    assert _units([_t(r) for r in rows.values()]) == 3


@pytest.mark.xfail(strict=True, reason="PL-5 accepted (won't fix): minute-resolution, continuous per-day stream; beef train-only (ML-52)")
@pytest.mark.skipif(CSV is None, reason="real MeatScan CSV not downloaded")
def test_sampled_plan_has_enough_split_units():
    rows = meatscan.load_metadata(CSV)
    ents = [{"name": f"M/{k[0].title()}_CowMeat/{k[0].title()} ({k[1]}).jpg"} for k in rows]
    plan = fetch.meatscan_plan(ents, dict(rows), 450)
    ts = [_t(rows[(c, i["n"])]) for c in ("fresh", "spoiled") for i in [x for x in plan["items"] if x["cls"] == c][:300]]
    assert _units(ts) >= 12


@pytest.mark.xfail(strict=True, reason="PL-5 accepted (won't fix): minute-resolution, continuous per-day stream; beef train-only (ML-52)")
@pytest.mark.skipif(STAGED is None or not (STAGED / "ingest_report.json").exists(), reason="MeatScan not (fully) staged under mldata")
def test_staged_meatscan_has_enough_split_units():
    import re
    ts = []
    for p in STAGED.rglob("*.jpg"):
        m = re.search(r"IMG_(\d{8})_(\d{6})", p.name)
        assert m, f"staged name without capture time: {p.name}"
        ts.append(datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp())
    assert len(ts) == 600
    assert _units(ts) >= 12, f"{_units(ts)} units"
