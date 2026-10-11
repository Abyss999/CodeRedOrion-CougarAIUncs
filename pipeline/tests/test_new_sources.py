"""Builder tests for the MeatScan and DaFiF sources (fetch planning, RAR5 range extraction, adapters).
Offline: network, 7z/unrar and HTTP ranges are injected. All data lives under tmp_path."""
from __future__ import annotations
import csv
import json
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline.ingestion import dafif, datasets, fetch, meatscan
from pipeline.ingestion.ledger import Ledger


def _jpg(path: Path, seed: int, size=(640, 480)):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)).save(path, "JPEG")


# ------------------------------------------------------------------------------------------- DaFiF
@pytest.mark.parametrize("name, want", [
    ("24-01-2024(MakarelSesi1).xlsx", ("2024-01-24", 6, "mackerel", 1)),
    ("19-01-2024(Mujair).xlsx", ("2024-01-19", 1, "tilapia", 1)),
    ("23-01-2024(MuajirSesi1).xlsx", ("2024-01-23", 5, "tilapia", 1)),        # upstream typo
    ("29-01-2024(t(TongkolSesi1).xlsx", ("2024-01-29", 11, "tuna", 1)),       # upstream typo
    ("29-01-2024(Tongkol_Sesi2).xlsx", ("2024-01-29", 11, "tuna", 2)),
    ("Rekap Tongkol 28 Sesi 2.xlsx", ("2024-01-28", 10, "tuna", 2)),
    ("Rekap Makarel 22 sesi 1.xlsx", ("2024-01-22", 4, "mackerel", 1)),
])
def test_workbook_names(name, want):
    got = fetch.parse_workbook_name(name)
    assert (got["date"], got["day"], got["species"], got["session"]) == want


def test_workbook_name_unknown_species_is_none():
    assert fetch.parse_workbook_name("24-01-2024(SalmonSesi1).xlsx") is None
    assert fetch.parse_workbook_name("notes.xlsx") is None


def _fish_meta():
    files, fid = [], 0
    for day in range(1, 12):
        for sp in ("Makarel", "Mujair", "Tongkol"):
            for s in (1, 2):
                fid += 1
                d = f"{18 + day:02d}-01-2024"
                files.append({"filename": f"{d}({sp}Sesi{s}).xlsx", "folder_id": f"f{fid}"})
                for k in range(4):
                    files.append({"filename": f"{fid}{k}.jpg", "folder_id": f"f{fid}", "size": 10,
                                  "content_details": {"download_url": f"u/{fid}{k}", "sha256_hash": None}})
    return {"files": files}


def test_dafif_plan_days_rule_and_balance():
    plan = fetch.dafif_plan(_fish_meta(), (1, 2, 3), (9, 10, 11), max_per_cell=30)
    items = plan["items"]
    assert {i["freshness"] for i in items} == {"fresh", "spoiled"}
    assert all((i["day"] <= 3) == (i["freshness"] == "fresh") for i in items)
    assert not any(4 <= i["day"] <= 8 for i in items)
    assert plan["report"]["selected"] == {"fresh": 30, "spoiled": 30}
    # round-robin: every species x session appears in each class
    for fr in ("fresh", "spoiled"):
        assert len({(i["species"], i["session"]) for i in items if i["freshness"] == fr}) == 6
    assert plan["report"]["skipped_middle_days"] == {d: 24 for d in range(4, 9)}


def test_fetch_dafif_writes_named_files_and_checks_sha(tmp_path):
    import io
    import hashlib
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1000), (120, 30, 30)).save(buf, "JPEG")
    good = buf.getvalue()
    meta = _fish_meta()
    for f in meta["files"]:
        if f["filename"].endswith(".jpg"):
            f["content_details"]["sha256_hash"] = hashlib.sha256(good).hexdigest()
    meta["files"][1]["content_details"]["sha256_hash"] = "0" * 64     # one corrupt file (day 1)
    rep = fetch.fetch_dafif(tmp_path / "dafif", max_per_cell=8, max_side=500, get=lambda url: good, meta=meta, workers=2)
    outs = sorted((tmp_path / "dafif").rglob("*.jpg"))
    assert rep["downloaded"] == len(outs) == 16 - len(rep["sha_mismatch"])
    assert all(o.parent.name in ("fish__fresh", "fish__spoiled") for o in outs)
    assert all(max(Image.open(o).size) == 500 for o in outs)
    assert all(dafif._BATCH.match(o.stem) for o in outs)


def test_dafif_groups_same_batch_across_days():
    a = dafif.group_of("fish__fresh", "mackerel_s1_d2__1000212414")[0]
    b = dafif.group_of("fish__spoiled", "mackerel_s1_d10__1000219999")[0]
    c = dafif.group_of("fish__spoiled", "mackerel_s2_d10__1000219999")[0]
    assert a == b != c


# ---------------------------------------------------------------------------------------- MeatScan
def _rar5_file_header(name: str, packed: int, unpacked: int) -> bytes:
    """A RAR5 file header (type 2) with a data area, like the ones cached in QuickOpen."""
    body = (fetch._vint_enc(2) + fetch._vint_enc(2) + fetch._vint_enc(packed)     # type, flags (data area), data size
            + fetch._vint_enc(0) + fetch._vint_enc(unpacked) + fetch._vint_enc(0x20)  # file flags, unpacked, attrs
            + fetch._vint_enc(0) + fetch._vint_enc(0)                                 # compression info, host os
            + fetch._vint_enc(len(name.encode())) + name.encode())
    return fetch._rar_block(body)


def _quick_open(entries: list[tuple[str, int, int, int]], qo_abs: int) -> bytes:
    """entries: (name, header_abs, packed, unpacked) -> a QuickOpen service block."""
    data = b""
    for name, habs, packed, unpacked in entries:
        hdr = _rar5_file_header(name, packed, unpacked)
        rec = fetch._vint_enc(0) + fetch._vint_enc(qo_abs - habs) + fetch._vint_enc(len(hdr)) + hdr
        data += zlib.crc32(rec).to_bytes(4, "little") + fetch._vint_enc(len(rec)) + rec
    body = fetch._vint_enc(3) + fetch._vint_enc(2) + fetch._vint_enc(len(data)) + b"\x02QO"
    return fetch._rar_block(body) + data


def test_parse_quick_open_roundtrip():
    qo_abs = 10_000_000
    ents = [("MeatScan_Dataset/Fresh_CowMeat/Fresh (1).jpg", 29, 5000, 5100),
            ("MeatScan_Dataset/MeatScan_Metadata.csv", 9000, 300, 1200)]
    got = fetch.parse_quick_open(_quick_open(ents, qo_abs), qo_abs)
    assert [(g["name"], g["abs"], g["packed"], g["unpacked"]) for g in got] == ents
    assert got[0]["header"] == _rar5_file_header(ents[0][0], 5000, 5100)


def test_wrap_single_file_is_a_rar5_archive():
    raw = _rar5_file_header("x.csv", 3, 3) + b"abc"
    w = fetch.wrap_single_file(raw)
    assert w.startswith(fetch.RAR5_SIG) and raw in w
    # main and end blocks carry a valid CRC32 over size+body
    main = w[len(fetch.RAR5_SIG):len(fetch.RAR5_SIG) + 8]
    assert int.from_bytes(main[:4], "little") == zlib.crc32(main[4:])


_CSV = ("Image_ID,Filename,Class,Date_Captured,Time_Captured,Location\n"
        "IMG_1,fresh_meat_1.jpg,Fresh,2024-02-14,07:30:00,Ayigya Market\n"
        "IMG_2,fresh_meat_2.jpg,Fresh,2024-02-14,07:31:00,Ayigya Market\n"
        "IMG_3,fresh_meat_3.jpg,Fresh,2024-02-15,09:00:00,Ayeduase Market\n"
        "IMG_4,spoiled_meat_1.jpg,Spoiled,2024-02-16,10:10:00,Ayigya Market\n"
        "IMG_5,spoiled_meat_2.jpg,Spoiled,bad-date,10:10:00,Ayigya Market\n")


def test_meatscan_plan_originals_only_and_spread():
    originals = fetch.meatscan_originals(_CSV)
    entries = [{"name": f"MeatScan_Dataset/Fresh_CowMeat/Fresh ({n}).jpg", "abs": n, "hdr_len": 1, "packed": 1,
                "unpacked": 1, "header": b"x"} for n in (1, 2, 3, 4, 5)]
    entries += [{"name": f"MeatScan_Dataset/Spoiled_CowMeat/Spoiled ({n}).jpg", "abs": n, "hdr_len": 1, "packed": 1,
                 "unpacked": 1, "header": b"x"} for n in (1, 2, 9)]
    plan = fetch.meatscan_plan(entries, originals, per_class=2)
    names = [Path(i["name"]).name for i in plan["items"]]
    assert "Fresh (4).jpg" not in names and "Spoiled (9).jpg" not in names       # not in the CSV = augmented copy
    assert plan["report"]["augmented_copies_skipped"] == {"fresh": 2, "spoiled": 1}
    fresh = [i for i in plan["items"] if i["cls"] == "fresh"]
    assert len(fresh) == 2 and len({i["bucket"] for i in fresh}) == 2           # spread over capture buckets


def test_fetch_meatscan_end_to_end_with_injected_ranges(tmp_path):
    import io
    buf = io.BytesIO()
    Image.new("RGB", (1920, 1080), (150, 40, 40)).save(buf, "JPEG")
    jpeg = buf.getvalue()
    names = ["MeatScan_Dataset/Fresh_CowMeat/Fresh (1).jpg", "MeatScan_Dataset/Fresh_CowMeat/Fresh (7).jpg",
             "MeatScan_Dataset/Spoiled_CowMeat/Spoiled (1).jpg", "MeatScan_Dataset/MeatScan_Metadata.csv"]
    payload = {n: (_CSV.encode() if n.endswith(".csv") else jpeg) for n in names}
    blob, layout = bytearray(b"\x00" * 64), []
    for n in names:                                      # stored ("packed") bytes = payload, for the fake decompressor
        hdr = _rar5_file_header(n, len(payload[n]), len(payload[n]))
        layout.append((n, len(blob), len(payload[n]), len(payload[n])))
        blob += hdr + payload[n]
    qo_abs = len(blob)
    blob += _quick_open(layout, qo_abs)
    total = len(blob)

    def rng(url, start, length):
        return bytes(blob[start:start + length])

    def decompress(archive: bytes) -> bytes:
        for n, p in payload.items():
            if archive.endswith(p + fetch._rar_block(b"\x05\x00\x00")):
                return p
        raise AssertionError("unexpected member")

    old = fetch.MS_QO_ABS
    fetch.MS_QO_ABS = qo_abs
    try:
        rep = fetch.fetch_meatscan(tmp_path / "ms", per_class=5, max_side=640, total_bytes=total, rng=rng,
                                   decompress=decompress, workers=2)
    finally:
        fetch.MS_QO_ABS = old
    got = sorted(p.relative_to(tmp_path / "ms").as_posix() for p in (tmp_path / "ms").rglob("*.jpg"))
    assert got == ["Fresh_CowMeat/Fresh (1).jpg", "Spoiled_CowMeat/Spoiled (1).jpg"]   # (7) is not in the CSV
    assert (tmp_path / "ms" / "MeatScan_Metadata.csv").read_text() == _CSV
    assert max(Image.open(tmp_path / "ms" / "Fresh_CowMeat" / "Fresh (1).jpg").size) == 640
    assert rep["index_entries"] == 4 and rep["augmented_copies_skipped"] == {"fresh": 1}


def test_fetch_meatscan_rejects_shifted_offsets(tmp_path):
    names = ["MeatScan_Dataset/MeatScan_Metadata.csv"]
    hdr = _rar5_file_header(names[0], 5, 5)
    blob = bytearray(b"\x00" * 10) + hdr + b"hello"
    qo_abs = len(blob)
    blob += _quick_open([(names[0], 11, 5, 5)], qo_abs)        # off by one
    old = fetch.MS_QO_ABS
    fetch.MS_QO_ABS = qo_abs
    try:
        with pytest.raises(RuntimeError, match="does not match"):
            fetch.fetch_meatscan(tmp_path / "ms", total_bytes=len(blob), rng=lambda u, s, n: bytes(blob[s:s + n]),
                                 decompress=lambda a: b"")
    finally:
        fetch.MS_QO_ABS = old


def test_meatscan_adapter_ingest_originals_timestamps(tmp_path):
    raw = tmp_path / "raw" / "meatscan"
    for i, n in enumerate((1, 2, 3, 8)):
        _jpg(raw / "Fresh_CowMeat" / f"Fresh ({n}).jpg", seed=i)
    _jpg(raw / "Spoiled_CowMeat" / "Spoiled (1).jpg", seed=10)
    _jpg(raw / "Spoiled_CowMeat" / "Spoiled (2).jpg", seed=11)
    (raw / "MeatScan_Metadata.csv").write_text(_CSV)
    led = Ledger(tmp_path / "staged" / "ledger.sqlite")
    rep = datasets.ingest(raw, "meatscan", "meatscan", tmp_path / "staged", led)
    led.close()
    assert rep["staged"] == 5 and rep["excluded_by_adapter"] == 1                   # Fresh (8) is not an original
    assert rep["adapter_setup"] == {"metadata_csv": "MeatScan_Metadata.csv", "originals_listed": 5, "timestamped": 4}
    rows = list(csv.DictReader(open(tmp_path / "staged" / "meatscan" / "manifest.csv")))
    g = {r["source_file"]: r["image"] for r in rows}
    assert "IMG_20240214_073000" in g["Fresh (1).jpg"] and "IMG_20240216_101000" in g["Spoiled (1).jpg"]
    assert "IMG_" not in g["Spoiled (2).jpg"].split("__", 2)[-1].split(".rf.")[0].replace("Spoiled_2", "")  # bad date: no stamp
    src = json.loads((tmp_path / "staged" / "meatscan" / "source.json").read_text())
    assert src["class_map"] == {"beef__fresh": "beef:fresh", "beef__spoiled": "beef:spoiled"}
    assert src["license"] == "CC BY 4.0"


def test_dafif_adapter_ingest(tmp_path):
    raw = tmp_path / "raw" / "dafif"
    _jpg(raw / "fish__fresh" / "tuna_s1_d1__100.jpg", 1)
    _jpg(raw / "fish__spoiled" / "tuna_s1_d10__200.jpg", 2)
    _jpg(raw / "fish__spoiled" / "tuna_s2_d10__300.jpg", 3)
    led = Ledger(tmp_path / "staged" / "ledger.sqlite")
    rep = datasets.ingest(raw, "dafif", "dafif", tmp_path / "staged", led)
    led.close()
    rows = list(csv.DictReader(open(tmp_path / "staged" / "dafif" / "manifest.csv")))
    groups = {r["source_file"]: Path(r["image"]).name.split(".rf.")[0] for r in rows}
    assert rep["staged"] == 3
    assert groups["tuna_s1_d1__100.jpg"] == groups["tuna_s1_d10__200.jpg"] != groups["tuna_s2_d10__300.jpg"]
    assert {r["canonical"] for r in rows} == {"fish"}
