"""QA for the MeatScan + DaFiF sources (fetch planning, RAR5 range reads, ingest hooks, leakage through the real
ml/yolo/prepare_dataset.py, notebook wiring, sources.json). Offline: network and unrar are injected, all data under
tmp_path. Run: .venv/bin/python -m pytest pipeline/tests/qa_new_sources.py (not collected by the default pattern)."""
from __future__ import annotations
import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline import config  # noqa: F401  (puts ml/yolo on sys.path)
from pipeline.ingestion import dafif, datasets, fetch, meatscan
from pipeline.ingestion.ledger import Ledger
from pipeline.tests.test_new_sources import _quick_open, _rar5_file_header  # builder helpers (read-only use)
import taxonomy as T  # noqa: E402
import prepare_dataset as PD  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SOURCES = REPO / "ml" / "yolo" / "sources.json"
NOTEBOOK = REPO / "ml" / "yolo" / "train_colab.ipynb"
REAL_CSV = REPO.parent / "mldata" / "raw" / "meatscan" / "MeatScan_Metadata.csv"


def _noise(path: Path, seed: int, size=(96, 72)):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)).save(path, "JPEG")


def _jpeg_bytes(size=(1600, 900)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, (90, 40, 40)).save(b, "JPEG")
    return b.getvalue()


# ============================================================================== 1. DaFiF names / plan
REAL_NAMES = [
    ("19-01-2024(Makarel).xlsx", ("2024-01-19", 1, "mackerel", 1)),
    ("19-01-2024(Mujair).xlsx", ("2024-01-19", 1, "tilapia", 1)),
    ("20-01-2024(Muajir).xlsx", ("2024-01-20", 2, "tilapia", 1)),
    ("21-01-2024(MujairSesi2).xlsx", ("2024-01-21", 3, "tilapia", 2)),
    ("21-01-2024(Mujair_Sesi2).xlsx", ("2024-01-21", 3, "tilapia", 2)),
    ("22-01-2024(Mujair sesi 2).xlsx", ("2024-01-22", 4, "tilapia", 2)),
    ("26-01-2024(TongkolSesi1).xlsx", ("2024-01-26", 8, "tuna", 1)),
    ("27-01-2024 (Tongkol Sesi 2).xlsx", ("2024-01-27", 9, "tuna", 2)),
    ("29-01-2024(t(TongkolSesi1).xlsx", ("2024-01-29", 11, "tuna", 1)),
    ("28-01-2024(t(Tongkol_Sesi2).xlsx", ("2024-01-28", 10, "tuna", 2)),
    ("Rekap Makarel 20 Sesi 1.xlsx", ("2024-01-20", 2, "mackerel", 1)),
    ("Rekap Mujair 25 sesi 2.xlsx", ("2024-01-25", 7, "tilapia", 2)),
    ("Rekap Muajir 25 Sesi 1.xlsx", ("2024-01-25", 7, "tilapia", 1)),
    ("rekap tongkol 29 sesi 2.xlsx", ("2024-01-29", 11, "tuna", 2)),
]


@pytest.mark.parametrize("name, want", REAL_NAMES)
def test_workbook_name_variants(name, want):
    got = fetch.parse_workbook_name(name)
    assert got is not None, name
    assert (got["date"], got["day"], got["species"], got["session"]) == want


@pytest.mark.parametrize("name", ["24-01-2024(SalmonSesi1).xlsx", "notes.xlsx", "Rekap Salmon 22 Sesi 1.xlsx", "", "readme.txt"])
def test_workbook_unknown_is_none(name):
    assert fetch.parse_workbook_name(name) is None


@pytest.mark.parametrize("name", ["31-02-2024(Makarel).xlsx", "Rekap Makarel 45 Sesi 1.xlsx"])
def test_workbook_impossible_date_is_none(name):
    assert fetch.parse_workbook_name(name) is None


def _meta_one_per_day(extra=()):
    files = []
    for day in range(1, 12):
        fid = f"f{day}"
        files.append({"filename": f"{18 + day:02d}-01-2024(Makarel).xlsx", "folder_id": fid})
        for k in range(2):
            files.append({"filename": f"d{day}_{k}.jpg", "folder_id": fid, "content_details": {"download_url": f"u/{day}/{k}"}})
    files += list(extra)
    return {"files": files}


def test_dafif_day_rule_exact_boundaries():
    plan = fetch.dafif_plan(_meta_one_per_day(), max_per_cell=None)
    by_day = {}
    for i in plan["items"]:
        by_day.setdefault(i["day"], set()).add(i["freshness"])
    assert by_day == {1: {"fresh"}, 2: {"fresh"}, 3: {"fresh"}, 9: {"spoiled"}, 10: {"spoiled"}, 11: {"spoiled"}}
    assert plan["report"]["skipped_middle_days"] == {d: 2 for d in range(4, 9)}
    assert plan["report"]["rule"]["day1"] == "2024-01-19"


def test_dafif_plan_reports_unparsed_and_orphans():
    extra = [{"filename": "24-01-2024(SalmonSesi1).xlsx", "folder_id": "z"},
             {"filename": "z0.jpg", "folder_id": "z", "content_details": {"download_url": "u/z"}},
             {"filename": "lost.jpg", "folder_id": "nowhere", "content_details": {"download_url": "u/l"}}]
    plan = fetch.dafif_plan(_meta_one_per_day(extra), max_per_cell=None)
    assert plan["report"]["unparsed_workbooks"] == ["24-01-2024(SalmonSesi1).xlsx"]
    assert plan["report"]["images_without_folder"] == 2
    assert not any(i["filename"] in ("z0.jpg", "lost.jpg") for i in plan["items"])


def test_dafif_plan_cap_is_per_freshness_and_spreads_species_sessions():
    files, n = [], 0
    for day in (1, 2, 3, 9, 10, 11):
        for sp in ("Makarel", "Mujair", "Tongkol"):
            for s in (1, 2):
                n += 1
                files.append({"filename": f"{18 + day:02d}-01-2024({sp}Sesi{s}).xlsx", "folder_id": f"f{n}"})
                files += [{"filename": f"{n}_{k}.jpg", "folder_id": f"f{n}", "content_details": {"download_url": f"u/{n}/{k}"}}
                          for k in range(50)]
    plan = fetch.dafif_plan({"files": files}, max_per_cell=36)
    for fr in ("fresh", "spoiled"):
        sel = [i for i in plan["items"] if i["freshness"] == fr]
        assert len(sel) == 36
        cells = Counter((i["species"], i["session"], i["day"]) for i in sel)
        assert len(cells) == 18 and set(cells.values()) == {2}             # even spread over species x session x day (3x2x3)
    assert plan["report"]["candidates"] == {"fresh": 900, "spoiled": 900}


def test_dafif_plan_is_deterministic():
    m = _meta_one_per_day()
    assert fetch.dafif_plan(m, max_per_cell=3)["items"] == fetch.dafif_plan(m, max_per_cell=3)["items"]


def test_fetch_dafif_sha_mismatch_not_written_and_rerun_is_cached(tmp_path):
    good = _jpeg_bytes()
    meta = _meta_one_per_day()
    for f in meta["files"]:
        if f["filename"].endswith(".jpg"):
            f["content_details"]["sha256_hash"] = hashlib.sha256(good).hexdigest()
    bad_f = next(f for f in meta["files"] if f["filename"] == "d1_0.jpg")
    bad_f["content_details"]["sha256_hash"] = "f" * 64
    calls = []

    def get(url):
        calls.append(url)
        return good

    rep = fetch.fetch_dafif(tmp_path / "d", max_per_cell=None, max_side=400, get=get, meta=meta, workers=2)
    assert rep["sha_mismatch"] == ["d1_0.jpg: sha256 mismatch"]
    names = sorted(p.name for p in (tmp_path / "d").rglob("*.jpg"))
    assert "mackerel_s1_d1__d1_0.jpg" not in names and "mackerel_s1_d1__d1_1.jpg" in names
    assert len(names) == 11                                   # 12 selected (6 days x 2) minus the corrupt one
    assert all(max(Image.open(p).size) == 400 for p in (tmp_path / "d").rglob("*.jpg"))
    assert json.loads((tmp_path / "d" / "fetch_report.json").read_text())["sha_mismatch"] == rep["sha_mismatch"]
    calls.clear()
    rep2 = fetch.fetch_dafif(tmp_path / "d", max_per_cell=None, max_side=400, get=get, meta=meta, workers=2)
    assert rep2["cached"] == 11 and rep2["downloaded"] == 0 and calls == ["u/1/0"]     # only the failed one is retried


def test_fetch_dafif_reports_unknown_species_and_writes_nothing_for_it(tmp_path):
    good = _jpeg_bytes((200, 100))
    extra = [{"filename": "24-01-2024(SalmonSesi1).xlsx", "folder_id": "z"},
             {"filename": "s.jpg", "folder_id": "z", "content_details": {"download_url": "u/s"}}]
    rep = fetch.fetch_dafif(tmp_path / "d", max_per_cell=None, get=lambda u: good, meta=_meta_one_per_day(extra))
    assert rep["unparsed_workbooks"] == ["24-01-2024(SalmonSesi1).xlsx"]
    assert not any("salmon" in p.name.lower() or p.name.startswith("s") for p in (tmp_path / "d").rglob("*.jpg"))


def test_fetch_dafif_only_two_class_dirs(tmp_path):
    good = _jpeg_bytes((200, 100))
    fetch.fetch_dafif(tmp_path / "d", max_per_cell=None, get=lambda u: good, meta=_meta_one_per_day())
    assert {p.parent.name for p in (tmp_path / "d").rglob("*.jpg")} == {"fish__fresh", "fish__spoiled"}


# ============================================================================== 2. MeatScan RAR5 / plan
def test_parse_quick_open_empty_index_is_empty():
    assert fetch.parse_quick_open(_quick_open([], 1000), 1000) == []


def _fake_archive(names, payload, qo_prefix=64):
    blob, layout = bytearray(b"\x00" * qo_prefix), []
    for n in names:
        hdr = _rar5_file_header(n, len(payload[n]), len(payload[n]))
        layout.append((n, len(blob), len(payload[n]), len(payload[n])))
        blob += hdr + payload[n]
    qo_abs = len(blob)
    blob += _quick_open(layout, qo_abs)
    return blob, qo_abs


@pytest.fixture
def qo_abs_patch():
    old = fetch.MS_QO_ABS

    def set_(v):
        fetch.MS_QO_ABS = v
    yield set_
    fetch.MS_QO_ABS = old


def test_fetch_meatscan_empty_index_raises(tmp_path, qo_abs_patch):
    blob, qo = _fake_archive([], {})
    qo_abs_patch(qo)
    with pytest.raises(RuntimeError, match="empty"):
        fetch.fetch_meatscan(tmp_path / "m", total_bytes=len(blob), rng=lambda u, s, n: bytes(blob[s:s + n]),
                             decompress=lambda a: b"")


def test_curl_range_truncated_response_raises(monkeypatch):
    class R:
        stdout = b"abc"
    monkeypatch.setattr(fetch.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="got 3 bytes"):
        fetch.curl_range("http://x", 0, 10)


def test_curl_range_requests_exact_inclusive_range(monkeypatch):
    seen = {}

    class R:
        stdout = b"x" * 10

    def run(cmd, **k):
        seen["cmd"] = cmd
        return R()
    monkeypatch.setattr(fetch.subprocess, "run", run)
    assert len(fetch.curl_range("http://x", 100, 10)) == 10
    assert seen["cmd"][seen["cmd"].index("-r") + 1] == "100-109"


def test_fetch_meatscan_truncated_member_header_raises(tmp_path, qo_abs_patch):
    names = ["M/Fresh_CowMeat/Fresh (1).jpg", "M/MeatScan_Metadata.csv"]
    csv_text = b"Image_ID,Filename,Class,Date_Captured,Time_Captured,Location\nIMG_1,fresh_meat_1.jpg,Fresh,2024-02-14,07:30:00,A\n"
    blob, qo = _fake_archive(names, {names[0]: b"jpegbytes", names[1]: csv_text})
    qo_abs_patch(qo)

    def rng(u, s, n):
        d = bytes(blob[s:s + n])
        return d[:5] if s < qo else d          # member reads come back truncated to 5 bytes (the index read is intact)

    with pytest.raises(RuntimeError, match="does not match"):
        fetch.fetch_meatscan(tmp_path / "m", total_bytes=len(blob), rng=rng, decompress=lambda a: b"")


def test_fetch_meatscan_decompress_failure_propagates(tmp_path, qo_abs_patch):
    names = ["M/MeatScan_Metadata.csv"]
    blob, qo = _fake_archive(names, {names[0]: b"x"})
    qo_abs_patch(qo)

    def boom(a):
        raise OSError("CRC mismatch")
    with pytest.raises(OSError):
        fetch.fetch_meatscan(tmp_path / "m", total_bytes=len(blob), rng=lambda u, s, n: bytes(blob[s:s + n]), decompress=boom)


def test_fetch_meatscan_missing_csv_is_a_clear_error(tmp_path, qo_abs_patch):
    names = ["M/Fresh_CowMeat/Fresh (1).jpg"]
    blob, qo = _fake_archive(names, {names[0]: b"x"})
    qo_abs_patch(qo)
    with pytest.raises(RuntimeError, match="no metadata CSV"):
        fetch.fetch_meatscan(tmp_path / "m", total_bytes=len(blob), rng=lambda u, s, n: bytes(blob[s:s + n]),
                             decompress=lambda a: b"")


def test_wrap_single_file_structure_and_crc():
    raw = _rar5_file_header("a.jpg", 4, 4) + b"data"
    w = fetch.wrap_single_file(raw)
    pos = len(fetch.RAR5_SIG)
    for want_type in (1, None, 5):           # main block, [file header+data], end block
        if want_type is None:
            assert w[pos:pos + len(raw)] == raw
            pos += len(raw)
            continue
        crc = int.from_bytes(w[pos:pos + 4], "little")
        size, p = fetch._vint(w, pos + 4)
        assert zlib.crc32(w[pos + 4:p + size]) == crc
        assert fetch._vint(w, p)[0] == want_type
        pos = p + size
    assert pos == len(w)


def test_vint_roundtrip():
    for n in (0, 1, 127, 128, 16383, 2 ** 31, 25416554933):
        assert fetch._vint(fetch._vint_enc(n), 0) == (n, len(fetch._vint_enc(n)))


def test_meatscan_plan_never_picks_augmented_and_spreads_buckets():
    rows = ["Image_ID,Filename,Class,Date_Captured,Time_Captured,Location"]
    for n in range(1, 41):
        rows.append(f"I{n},fresh_meat_{n}.jpg,Fresh,2024-02-1{4 + n % 3},{7 + n % 4:02d}:00:00,{'A' if n % 2 else 'B'}")
    orig = fetch.meatscan_originals("\n".join(rows) + "\n")
    ents = [{"name": f"M/Fresh_CowMeat/Fresh ({n}).jpg"} for n in range(1, 61)]         # 41..60 = augmented
    plan = fetch.meatscan_plan(ents, orig, per_class=24)
    ns = [i["n"] for i in plan["items"]]
    assert max(ns) <= 40 and len(ns) == 24
    nb = len({i["bucket"] for i in plan["items"]})
    assert len({i["bucket"] for i in plan["items"][:nb]}) == nb                             # one per bucket before repeats
    assert plan["report"]["augmented_copies_skipped"] == {"fresh": 20}


def test_meatscan_originals_survives_crlf_and_bom():
    text = "﻿Image_ID,Filename,Class,Date_Captured,Time_Captured,Location\r\nI1,Fresh_Meat_5.JPG,Fresh,2024-02-14,07:30:00,A\r\n"
    assert list(fetch.meatscan_originals(text.lstrip("﻿"))) == [("fresh", 5)]


@pytest.mark.skipif(not REAL_CSV.exists(), reason="real MeatScan CSV not downloaded")
def test_real_csv_parses_all_6995_with_timestamps():
    rows = meatscan.load_metadata(REAL_CSV)
    assert len(rows) == 6995 and Counter(k[0] for k in rows) == {"fresh": 3487, "spoiled": 3508}
    assert all(meatscan.capture_stamp(r) for r in rows.values())
    assert set(fetch.meatscan_originals(REAL_CSV.read_text(encoding="utf-8-sig"))) == set(rows)


@pytest.mark.xfail(strict=True, reason="PL-5: the 300 s chained session rule collapses the sampled MeatScan into ~4-5 split units")
@pytest.mark.skipif(not REAL_CSV.exists(), reason="real MeatScan CSV not downloaded")
def test_real_csv_sampled_set_has_enough_split_units():
    rows = meatscan.load_metadata(REAL_CSV)
    ents = [{"name": f"M/{k[0].title()}_CowMeat/{k[0].title()} ({k[1]}).jpg"} for k in rows]
    plan = fetch.meatscan_plan(ents, dict(rows), 450)
    ts = []
    for cls in ("fresh", "spoiled"):
        for i in [x for x in plan["items"] if x["cls"] == cls][:300]:             # ingest --max-per-cell 300
            r = rows[(cls, i["n"])]
            ts.append(datetime.strptime(f"{r['Date_Captured']} {r['Time_Captured']}", "%Y-%m-%d %H:%M:%S").timestamp())
    ts.sort()
    units = 1 + sum(1 for a, b in zip(ts, ts[1:]) if b - a > 300)
    assert units >= 12, f"only {units} split units for {len(ts)} images"


# ============================================================================== 3. ingest hooks
def _csv_for(rows):
    out = ["Image_ID,Filename,Class,Date_Captured,Time_Captured,Location"]
    for i, (cls, n, d, t) in enumerate(rows):
        out.append(f"I{i},{cls}_meat_{n}.jpg,{cls.title()},{d},{t},Ayigya Market")
    return "\n".join(out) + "\n"


def _ingest(raw, name, adapter, staged, **kw):
    led = Ledger(staged / "ledger.sqlite")
    try:
        return datasets.ingest(raw, name, adapter, staged, led, **kw)
    finally:
        led.close()


def test_hooks_absent_for_old_adapters_and_report_unchanged(tmp_path):
    for ad in (datasets.agrifreshnet, datasets.generic):
        assert not hasattr(ad, "setup") and not hasattr(ad, "include")
    raw = tmp_path / "raw"
    _noise(raw / "Fresh Banana(1-4)" / "IMG_20250101_123456.jpg", 1)
    _noise(raw / "rotten_apple" / "a.jpg", 2)
    rep = _ingest(raw, "g", "folders", tmp_path / "staged")
    assert "adapter_setup" not in rep and rep.get("excluded_by_adapter", 0) == 0
    names = sorted(p.name for p in (tmp_path / "staged" / "g").rglob("*.jpg"))
    assert any(n.startswith("banana__fresh__IMG_20250101_123456.rf.") for n in names)


def test_meatscan_no_csv_keeps_everything_untimestamped(tmp_path):
    raw = tmp_path / "raw"
    for n in (1, 2, 3):
        _noise(raw / "Fresh_CowMeat" / f"Fresh ({n}).jpg", n)
    rep = _ingest(raw, "m", "meatscan", tmp_path / "staged")
    assert rep["staged"] == 3 and rep.get("excluded_by_adapter", 0) == 0
    assert rep["adapter_setup"]["metadata_csv"] is None
    assert not any("IMG_" in p.name for p in (tmp_path / "staged" / "m").rglob("*.jpg"))


def test_meatscan_state_does_not_leak_between_ingests(tmp_path):
    raw1, raw2 = tmp_path / "r1", tmp_path / "r2"
    _noise(raw1 / "Fresh_CowMeat" / "Fresh (1).jpg", 1)
    (raw1 / "MeatScan_Metadata.csv").write_text(_csv_for([("fresh", 1, "2024-02-14", "07:30:00")]))
    _noise(raw2 / "Fresh_CowMeat" / "Fresh (9).jpg", 2)          # no CSV here: must not inherit raw1's rows
    _ingest(raw1, "a", "meatscan", tmp_path / "s")
    rep = _ingest(raw2, "b", "meatscan", tmp_path / "s")
    assert rep["staged"] == 1 and rep["adapter_setup"]["originals_listed"] == 0
    _noise(tmp_path / "r3" / "rotten_apple" / "x.jpg", 3)
    assert _ingest(tmp_path / "r3", "c", "folders", tmp_path / "s")["staged"] == 1


def test_meatscan_reingest_is_idempotent(tmp_path):
    raw = tmp_path / "raw"
    _noise(raw / "Fresh_CowMeat" / "Fresh (1).jpg", 1)
    (raw / "MeatScan_Metadata.csv").write_text(_csv_for([("fresh", 1, "2024-02-14", "07:30:00")]))
    r1 = _ingest(raw, "m", "meatscan", tmp_path / "s")
    r2 = _ingest(raw, "m", "meatscan", tmp_path / "s")
    assert r1["staged"] == 1 and r2.get("staged", 0) == 0 and r2["skipped_seen"] == 1


def test_meatscan_csv_with_crlf_and_bom_is_used(tmp_path):
    raw = tmp_path / "raw"
    _noise(raw / "Fresh_CowMeat" / "Fresh (1).jpg", 1)
    (raw / "MeatScan_Metadata.csv").write_bytes(("﻿" + _csv_for([("fresh", 1, "2024-02-14", "07:30:00")]).replace("\n", "\r\n")).encode())
    rep = _ingest(raw, "m", "meatscan", tmp_path / "s")
    assert rep["adapter_setup"]["timestamped"] == 1
    assert any("IMG_20240214_073000" in p.name for p in (tmp_path / "s" / "m").rglob("*.jpg"))


def test_meatscan_max_per_cell_spreads_over_sessions(tmp_path):
    raw = tmp_path / "raw"
    rows = []
    for h in range(6):                      # 6 sessions of 5 photos
        for k in range(5):
            n = h * 5 + k + 1
            _noise(raw / "Fresh_CowMeat" / f"Fresh ({n}).jpg", n)
            rows.append(("fresh", n, "2024-02-14", f"{8 + h:02d}:{k:02d}:00"))
    (raw / "MeatScan_Metadata.csv").write_text(_csv_for(rows))
    rep = _ingest(raw, "m", "meatscan", tmp_path / "s", max_per_cell=6)
    assert rep["staged"] == 6
    stamps = {re.search(r"IMG_20240214_(\d\d)", p.name).group(1) for p in (tmp_path / "s" / "m").rglob("*.jpg")}
    assert len(stamps) == 6 or len(stamps) >= 3          # spread over sessions, not the first six photos


# ============================================================================== 4. taxonomy
@pytest.mark.parametrize("raw, want", [("cowmeat", "beef"), ("CowMeat", "beef"), ("cow_meat", "beef"), ("mackerel", "fish"),
                                       ("Tilapia", "fish"), ("tuna", "fish"), ("Makarel", "fish"), ("mujair", "fish"),
                                       ("Tongkol", "fish")])
def test_taxonomy_aliases(raw, want):
    assert T.canonical_name(raw) == want


@pytest.mark.parametrize("d, want_cls, fr", [("Fresh_CowMeat", "beef", "fresh"), ("Spoiled_CowMeat", "beef", "spoiled"),
                                             ("fish__fresh", "fish", "fresh"), ("fish__spoiled", "fish", "spoiled")])
def test_adapter_dir_parse(d, want_cls, fr):
    ad = meatscan if want_cls == "beef" else dafif
    p = ad.parse_dir(d)
    assert p and p["freshness"] == fr and T.canonical_name(p["item"]) == want_cls, p


def test_adapter_rejects_non_class_dirs():
    for d in ("MeatScan_Dataset", "images", "Augmented"):
        assert meatscan.parse_dir(d) is None


def test_aliases_have_no_conflicting_duplicate_keys():
    tree = ast.parse((REPO / "ml" / "yolo" / "taxonomy.py").read_text())
    seen = defaultdict(set)
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "ALIASES" and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                seen[ast.literal_eval(k)].add(ast.literal_eval(v))
    assert seen and {k: v for k, v in seen.items() if len(v) > 1} == {}
    assert all(T.ALIASES[k] in T.CLASS_CATEGORY for k in ("cowmeat", "mackerel", "tilapia", "tuna", "makarel", "mujair", "tongkol"))


# ============================================================================== 5. leakage through prepare_dataset
def _build_staged(tmp_path, seed=0):
    """Synthetic raw MeatScan + DaFiF -> real ingest -> sources.json for prepare_dataset."""
    staged = tmp_path / "staged"
    raw = tmp_path / "raw_ms"
    rows, n = [], 0
    base = datetime(2024, 2, 14, 7, 0, 0)
    for cls in ("fresh", "spoiled"):                 # 14 capture sessions per class, 4 photos 60 s apart, sessions >1 h apart
        for s in range(14):
            for k in range(4):
                n += 1
                t = base + timedelta(hours=s + (0 if cls == "fresh" else 40), seconds=60 * k)
                _noise(raw / f"{cls.title()}_CowMeat" / f"{cls.title()} ({n}).jpg", seed * 1000 + n)
                rows.append((cls, n, t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S")))
    (raw / "MeatScan_Metadata.csv").write_text(_csv_for(rows))
    _ingest(raw, "meatscan", "meatscan", staged)
    raw2, n = tmp_path / "raw_df", 0                 # 3 species x 2 sessions, fresh days 1-3, spoiled days 9-11, 3 photos each
    for sp in ("mackerel", "tilapia", "tuna"):
        for s in (1, 2):
            for day, fr in [(1, "fresh"), (2, "fresh"), (3, "fresh"), (9, "spoiled"), (10, "spoiled"), (11, "spoiled")]:
                for k in range(3):
                    n += 1
                    _noise(raw2 / f"fish__{fr}" / f"{sp}_s{s}_d{day}__{n:06d}.jpg", seed * 1000 + 500 + n)
    _ingest(raw2, "dafif", "dafif", staged)
    srcs = [json.loads((staged / d / "source.json").read_text()) for d in ("meatscan", "dafif")]
    sj = tmp_path / "sources.json"
    sj.write_text(json.dumps({"sources": srcs}))
    return sj


@pytest.fixture(scope="module", params=[0, 1, 2])
def prepared(request, tmp_path_factory):
    tmp = tmp_path_factory.mktemp(f"prep{request.param}")
    sj = _build_staged(tmp, request.param)
    out = tmp / "out"
    PD.main(["--sources", str(sj), "--out", str(out), "--seed", str(42 + request.param), "--heldout", "0.25", "--val", "0.25",
             "--no-synth-lighting", "--min-session-images", "1"])
    return out


def _files(out):
    for sp in ("train", "val", "heldout"):
        for p in sorted((out / "images" / sp).glob("*.jpg")):
            yield sp, p


def test_prepare_class_map_and_freshness(prepared):
    names = json.loads((prepared / "class_names.json").read_text())
    assert set(names.values()) == {"beef", "fish"}
    n_checked, fr_count = 0, Counter()
    for sp, p in _files(prepared):
        cid = int((prepared / "labels" / sp / f"{p.stem}.txt").read_text().split()[0])
        code = (prepared / "freshness" / sp / f"{p.stem}.txt").read_text().split()[0]
        is_meat = p.stem.startswith("meatscan_")
        assert names[str(cid)] == ("beef" if is_meat else "fish")
        fr = {"0": "fresh", "1": "spoiled"}[code]
        if is_meat:                                       # meat names carry the class dir; fish names deliberately do not
            assert f"beef__{fr}__" in p.stem, p.stem
        fr_count[(is_meat, fr)] += 1
        n_checked += 1
    assert n_checked == 112 + 108
    assert fr_count == {(True, "fresh"): 56, (True, "spoiled"): 56, (False, "fresh"): 54, (False, "spoiled"): 54}


def test_prepare_dafif_species_session_never_split(prepared):
    where, count = defaultdict(set), Counter()
    for sp, p in _files(prepared):
        m = re.search(r"dafif_(mackerel|tilapia|tuna)_s(\d)", p.stem)
        if m:
            where[m.groups()].add(sp)
            count[m.groups()] += 1
    assert len(where) == 6 and sum(count.values()) == 108
    assert {k: v for k, v in where.items() if len(v) > 1} == {}


def test_prepare_dafif_fresh_and_spoiled_of_a_batch_share_a_split(prepared):
    seen = defaultdict(set)
    for sp, p in _files(prepared):
        m = re.search(r"dafif_(mackerel|tilapia|tuna)_s(\d)", p.stem)
        if m:
            code = (prepared / "freshness" / sp / f"{p.stem}.txt").read_text().split()[0]
            seen[m.groups()].add(({"0": "fresh", "1": "spoiled"}[code], sp))
    assert len(seen) == 6
    for batch, v in seen.items():
        assert len({sp for _, sp in v}) == 1, (batch, v)
        assert {fr for fr, _ in v} == {"fresh", "spoiled"}


def test_prepare_meatscan_300s_sessions_share_split(prepared):
    pts = []
    for sp, p in _files(prepared):
        m = re.search(r"IMG_(\d{8})_(\d{6})", p.stem)
        if m:
            pts.append((datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"), sp, p.stem))
    assert len(pts) == 112
    pts.sort()
    for (t1, s1, n1), (t2, s2, n2) in zip(pts, pts[1:]):
        if (t2 - t1).total_seconds() <= 300:
            assert s1 == s2, (n1, n2)


def test_prepare_all_splits_have_data(prepared):
    c = Counter(sp for sp, _ in _files(prepared))
    assert c["train"] > 0 and c["val"] > 0 and c["heldout"] > 0


# ============================================================================== 6. sources.json, pending, notebook
def _sources():
    return json.loads(SOURCES.read_text())["sources"]


def test_sources_json_new_entries():
    by = {s["name"]: s for s in _sources()}
    assert len(by) == len(_sources())
    for n in ("meatscan", "dafif"):
        s = by[n]
        assert s["license"] == "CC BY 4.0" and s["url"].startswith("http") and s["kind"] == "folders" and not s.get("pending")
    assert by["meatscan"]["class_map"] == {"beef__fresh": "beef:fresh", "beef__spoiled": "beef:spoiled"}
    assert by["dafif"]["class_map"] == {"fish__fresh": "fish:fresh", "fish__spoiled": "fish:spoiled"}
    h = by["food_hvk7g"]
    assert h["pending"] is True and h["license"] and h["url"] and "class_map" in h
    assert h["roboflow"]["version"] is None and h["roboflow"]["workspace"] and h["roboflow"]["project"]
    f = by["food_spoilage_status"]
    assert not f.get("pending") and f["kind"] == "yolo" and f["license"] == "CC BY 4.0" and f["url"].startswith("http")
    assert f["roboflow"]["version"] == 1 and f["roboflow"]["workspace"] and f["roboflow"]["project"]
    assert len(f["class_map"]) == 12
    got = {PD.resolve(k, f["class_map"]) for k in f["class_map"]}
    assert len(got) == 12
    for name, fr in got:
        assert name in T.CLASS_NAMES and fr in ("fresh", "spoiled"), (name, fr)
    assert {fr for _, fr in got} == {"fresh", "spoiled"}
    assert Counter(n for n, _ in got) == {n: 2 for n in ("apple", "banana", "bell_pepper", "orange", "potato", "bitter_melon")}


def test_every_source_has_license_and_url():
    for s in _sources():
        assert s.get("license") and s.get("url"), s["name"]


def test_pending_source_skipped_by_prepare(tmp_path):
    _noise(tmp_path / "rootdir" / "cls" / "a.jpg", 1)
    srcs = [dict(s, root=str(tmp_path / "rootdir")) for s in _sources() if s["name"] == "food_hvk7g"]
    assert len(srcs) == 1
    skipped = Counter()
    assert PD.collect(srcs, skipped) == []
    assert len(skipped) == 1


def test_enabled_yolo_source_without_data_yaml_exits_clearly(tmp_path):
    (tmp_path / "rootdir").mkdir()
    srcs = [dict(s, root=str(tmp_path / "rootdir")) for s in _sources() if s["name"] == "food_spoilage_status"]
    with pytest.raises(SystemExit, match="no data.yaml"):
        PD.collect(srcs, Counter())


def test_prepare_main_with_only_pending_source_does_not_crash(tmp_path):
    srcs = [s for s in _sources() if s["name"] == "food_hvk7g"]
    sj = tmp_path / "s.json"
    sj.write_text(json.dumps({"sources": srcs}))
    try:
        PD.main(["--sources", str(sj), "--out", str(tmp_path / "o")])
    except SystemExit:
        pass                               # an empty dataset may exit; it must not crash on the pending entry
    except Exception as e:                 # noqa: BLE001
        pytest.fail(f"pending-only sources crashed prepare: {e!r}")


def _cells():
    nb = json.loads(NOTEBOOK.read_text())
    return ["".join(c["source"]) for c in nb["cells"]]


def test_notebook_cell_syntax():
    cells = _cells()
    assert len(cells) > 3
    for i in (1, 3):                       # replace IPython magics / shell lines by `pass`; the rest must parse
        lines = [l[:len(l) - len(l.lstrip())] + "pass" if l.lstrip().startswith(("%", "!")) else l for l in cells[i].splitlines()]
        ast.parse("\n".join(lines), filename=f"cell{i}")


def test_notebook_cell1_pins_unrar():
    assert re.search(r"pip install[^\n]*unrar-cffi==0\.2\.2", _cells()[1])


def test_notebook_data_ver_derived_from_sources_and_used_in_cache_dir():
    c = _cells()[1]
    assert re.search(r'DATA_VER\s*=\s*_h\.sha256\(open\("[^"]*ml/yolo/sources\.json", "rb"\)\.read\(\)\)\.hexdigest\(\)\[:8\]', c)
    assert re.search(r'CACHE_DIR\s*=\s*f"[^"]*\{DATA_VER\}"', c)
    assert c.index("DATA_VER =") < c.index("CACHE_DIR =") < c.index("DRIVE_TAR, DRIVE_DATA")


def test_notebook_cell3_new_sources_commands():
    c = _cells()[3]
    for cmd, name in (("fetch-meatscan", "meatscan"), ("fetch-dafif", "dafif")):
        i = c.index(f'"{cmd}"')
        j = c.index('"ingest-dataset"', i)
        tail = c[j:j + 400]
        assert f'"--adapter", "{name}"' in tail and f'"--name", "{name}"' in tail
        assert '"--max-per-cell", "300"' in tail
        assert f'"--out", "/content/raw/{name}"' in c[i:j] and f'"--dir", "/content/raw/{name}"' in tail
    assert '"--per-class", "450"' in c


def test_notebook_roboflow_loop_skips_pending_and_unversioned():
    c = _cells()[3]
    m = re.search(r"rf_names\s*=\s*\[.+\]", c)
    assert m
    srcs = {s["name"]: s for s in _sources()}
    ns = {"srcs": srcs}
    exec(m.group(0), ns)                                                   # noqa: S102 (our own notebook text)
    assert "food_hvk7g" not in ns["rf_names"] and "food_spoilage_status" in ns["rf_names"]
    assert set(ns["rf_names"]) == {n for n, s in srcs.items() if s.get("roboflow") and s["roboflow"].get("version") and not s.get("pending")}
    assert ns["rf_names"], "the pinned Roboflow sources must still be downloaded"
    # the loop must not touch an entry whose version is missing even if "pending" were removed
    srcs2 = {"x": {"roboflow": {"version": None}}, "y": {"roboflow": {"version": 3}, "pending": True}, "z": {"roboflow": {"version": 2}}}
    ns2 = {"srcs": srcs2}
    exec(m.group(0), ns2)                                                  # noqa: S102
    assert ns2["rf_names"] == ["z"]


def test_notebook_final_sources_json_keeps_pending_entries():
    assert 'json.dump({"sources": list(srcs.values())}' in _cells()[3]


# ============================================================================== 7. CLI
@pytest.mark.parametrize("cmd, flags", [("fetch-dafif", ["--out", "--fresh-days", "--spoiled-days", "--max-per-cell", "--max-side"]),
                                        ("fetch-meatscan", ["--out", "--per-class", "--max-side", "--workers"])])
def test_cli_help(cmd, flags):
    r = subprocess.run([sys.executable, "-m", "pipeline", cmd, "--help"], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert all(f in r.stdout for f in flags)


def test_cli_ingest_adapter_choices_and_bad_adapter():
    r = subprocess.run([sys.executable, "-m", "pipeline", "ingest-dataset", "--help"], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert "meatscan" in r.stdout and "dafif" in r.stdout and "agrifreshnet" in r.stdout
    r = subprocess.run([sys.executable, "-m", "pipeline", "ingest-dataset", "--dir", "x", "--name", "n", "--adapter", "nope"],
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2


def test_cli_fetch_requires_out():
    r = subprocess.run([sys.executable, "-m", "pipeline", "fetch-dafif"], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "--out" in r.stderr


def test_cli_dafif_days_parse_and_pass_through(tmp_path, monkeypatch):
    from pipeline import cli
    got = {}

    def fake(*a, **k):
        got["a"] = a
        return {}
    monkeypatch.setattr(fetch, "fetch_dafif", fake)
    cli.main(["fetch-dafif", "--out", str(tmp_path / "o"), "--fresh-days", "1,2", "--spoiled-days", "10", "--max-per-cell", "5"])
    assert got["a"][1:] == ((1, 2), (10,), 5, 1280, 6)


# ---- PL-6/PL-7 fixes and atomic write / failed list
def test_save_downscaled_is_atomic(tmp_path, monkeypatch):
    dst = tmp_path / "x" / "a.jpg"
    real_save = Image.Image.save

    def boom(self, fp, *a, **k):
        real_save(self, fp, *a, **k)
        raise OSError("disk full")
    monkeypatch.setattr(Image.Image, "save", boom)
    with pytest.raises(OSError):
        fetch.save_downscaled(_jpeg_bytes((300, 200)), dst, 100)
    assert not dst.exists()                                   # a failed write never looks cached
    monkeypatch.undo()
    assert fetch.save_downscaled(_jpeg_bytes((300, 200)), dst, 100) == (100, 67) and dst.exists()
    assert not list(dst.parent.glob("*.part"))


def test_fetch_dafif_undecodable_image_goes_to_failed_not_abort(tmp_path):
    good = _jpeg_bytes((200, 100))
    meta = _meta_one_per_day()
    rep = fetch.fetch_dafif(tmp_path / "d", max_per_cell=None, meta=meta,
                            get=lambda u: b"not a jpeg" if u == "u/1/0" else good)
    assert rep["failed"] and "d1_0.jpg" in rep["failed"][0] and rep["sha_mismatch"] == []
    assert rep["downloaded"] == 11
    assert not list((tmp_path / "d").rglob("*.part"))
    assert json.loads((tmp_path / "d" / "fetch_report.json").read_text())["failed"] == rep["failed"]


def test_fetch_dafif_sha_and_failed_lists_are_separate(tmp_path):
    good = _jpeg_bytes((200, 100))
    meta = _meta_one_per_day()
    for f in meta["files"]:
        if f["filename"] == "d1_1.jpg":
            f["content_details"]["sha256_hash"] = "0" * 64
    rep = fetch.fetch_dafif(tmp_path / "d", max_per_cell=None, meta=meta,
                            get=lambda u: b"junk" if u == "u/1/0" else good)
    assert len(rep["sha_mismatch"]) == 1 and "d1_1.jpg" in rep["sha_mismatch"][0]
    assert len(rep["failed"]) == 1 and "d1_0.jpg" in rep["failed"][0]
