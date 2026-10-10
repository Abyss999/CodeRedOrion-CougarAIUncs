import csv
import http.server
import json
import socket
import threading
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from pipeline import config
from pipeline.ingestion import receipts
from pipeline.timeout.worker import OcrFailed, OcrTimeout, OcrWorker
from .conftest import REPO, make_jpeg

FIX = REPO / "ml" / "eval" / "fixtures" / "receipts"
FACTORY = "pipeline.tests.ocr_engines:behave"


def drop(dirs, name, text=None, seed=1):
    inbox = dirs["incoming"] / "receipts"
    p = make_jpeg(inbox / name, seed, size=(40, 40))
    if text is not None:
        p.with_suffix(".txt").write_text(text)
    return p


@pytest.fixture
def dirs(root):
    return config.data_dirs(root)


def worker(t=1.0, grace=3.0):
    return OcrWorker(FACTORY, t, load_grace_s=grace)


SIMPLE = "MILK 2% GAL     4.29\nCHKN BRST       8.00\nTOTAL          12.29\n"


# ------------------------------------------------------------------ fake engine, outputs
def test_fake_engine_outputs(dirs):
    p = drop(dirs, "r1.jpg", SIMPLE)
    c = receipts.process_inbox(dirs, engine="fake", timeout_s=5, load_grace_s=30)
    assert c["processed"] == 1 and c["lines"] == 2
    pd = dirs["processed"]
    recs = [json.loads(l) for l in (pd / "receipts.jsonl").read_text().splitlines()]
    assert len(recs) == 1
    rid = recs[0]["receipt_id"]
    assert json.loads((pd / "receipts" / f"{rid}.json").read_text()) == recs[0]
    rows = list(csv.DictReader(open(pd / "receipt_lines.csv")))
    assert list(rows[0]) == receipts.LINE_COLS
    assert [(r["canonical"], r["category"]) for r in rows] == [("milk", "dairy"), ("chicken", "meat")]
    assert rows[0]["receipt_id"] == rid and rows[0]["source_file"] == "r1.jpg"
    assert recs[0]["total"] == 12.29
    assert not p.exists() and not p.with_suffix(".txt").exists()
    assert (pd / "archive" / f"{rid}.jpg").exists() and (pd / "archive" / f"{rid}.txt").exists()
    assert list((dirs["incoming"] / "receipts").iterdir()) == []


def test_duplicate_content_goes_to_duplicates(dirs):
    drop(dirs, "a.jpg", SIMPLE)
    receipts.process_inbox(dirs, engine_obj=worker(), engine="fake")
    drop(dirs, "b.jpg", SIMPLE)  # same seed -> same bytes
    c = receipts.process_inbox(dirs, engine="fake", engine_obj=worker())
    assert c == {"duplicates": 1}
    assert len(list((dirs["processed"] / "duplicates").glob("*.jpg"))) == 1
    assert len((dirs["processed"] / "receipts.jsonl").read_text().splitlines()) == 1


# ------------------------------------------------------------------ quarantine
def q(dirs, name):
    p = dirs["quarantine"] / name
    assert p.exists(), list(dirs["quarantine"].iterdir())
    return json.loads(p.with_name(p.name + ".error.json").read_text())


@pytest.mark.parametrize("name", ["scan.pdf", "photo.heic", "x.heif", "weird.xyz", "noext", "UPPER.PDF"])
def test_unsupported_format(dirs, name):
    inbox = dirs["incoming"] / "receipts"
    inbox.mkdir(parents=True)
    (inbox / name).write_bytes(b"data")
    c = receipts.process_inbox(dirs, engine_obj=object())
    assert c == {"quarantined": 1}
    assert q(dirs, name)["code"] == "unsupported_format"
    assert not (inbox / name).exists()


def test_invalid_image(dirs):
    inbox = dirs["incoming"] / "receipts"
    inbox.mkdir(parents=True)
    (inbox / "bad.jpg").write_bytes(b"this is not a jpeg")
    (inbox / "empty.png").write_bytes(b"")
    c = receipts.process_inbox(dirs, engine_obj=object())
    assert c == {"quarantined": 2}
    assert q(dirs, "bad.jpg")["code"] == "invalid_image" and q(dirs, "empty.png")["code"] == "invalid_image"


def test_ocr_failed_then_next_file_ok(dirs):
    drop(dirs, "a_bad.jpg", "BOOM", seed=1)
    drop(dirs, "b_ok.jpg", SIMPLE, seed=2)
    c = receipts.process_inbox(dirs, engine="fake", engine_obj=worker(5, 30))
    assert c["quarantined"] == 1 and c["processed"] == 1
    assert q(dirs, "a_bad.jpg")["code"] == "ocr_failed"


def test_missing_sidecar_is_ocr_failed(dirs):
    drop(dirs, "nosidecar.jpg", None)
    receipts.process_inbox(dirs, engine="fake", engine_obj=worker(5, 30))
    assert q(dirs, "nosidecar.jpg")["code"] == "ocr_failed"


def test_timeout_kills_worker_and_continues(dirs):
    drop(dirs, "a_hang.jpg", "HANG", seed=1)
    drop(dirs, "b_ok.jpg", SIMPLE, seed=2)
    w = worker(1.0, 3.0)
    try:
        c = receipts.process_inbox(dirs, engine="fake", engine_obj=w)
    finally:
        w.close()
    assert c["quarantined"] == 1 and c["processed"] == 1
    assert q(dirs, "a_hang.jpg")["code"] == "ocr_timeout"
    assert w.restarts == 1


def test_quarantined_is_retried_when_redropped(dirs):
    drop(dirs, "a.jpg", "BOOM", seed=1)
    receipts.process_inbox(dirs, engine="fake", engine_obj=worker(5, 30))
    assert q(dirs, "a.jpg")["code"] == "ocr_failed"
    drop(dirs, "a.jpg", SIMPLE, seed=1)  # same image bytes, now readable
    c = receipts.process_inbox(dirs, engine="fake", engine_obj=worker(5, 30))
    assert c.get("processed") == 1 and not c.get("duplicates")


def test_worker_direct_timeout_and_recovery(tmp_path):
    a, b = make_jpeg(tmp_path / "a.jpg", 1), make_jpeg(tmp_path / "b.jpg", 2)
    a.with_suffix(".txt").write_text("HANG")
    b.with_suffix(".txt").write_text("hello")
    with worker(1.0, 3.0) as w:
        with pytest.raises(OcrTimeout):
            w.run(str(a))
        assert w.run(str(b)) == "hello"
        assert w.restarts == 1


def test_worker_crash_is_ocr_failed_and_recovers(tmp_path):
    b = make_jpeg(tmp_path / "b.jpg", 2)
    b.with_suffix(".txt").write_text("hello")
    with worker(2.0, 8.0) as w:
        assert w.run(str(b)) == "hello"
        w._proc.kill(); w._proc.join()
        try:
            w.run(str(b))  # may succeed via restart or raise OcrFailed; must not hang
        except OcrFailed:
            pass
        assert w.run(str(b)) == "hello"


# ------------------------------------------------------------------ service engine
class _H(http.server.BaseHTTPRequestHandler):
    mode = "ok"
    seen = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        type(self).seen.append((self.path, self.headers.get("Content-Type", ""), len(body)))
        if self.path != "/ocr":
            self.send_response(404); self.end_headers(); return
        if type(self).mode == "slow":
            import time; time.sleep(3)
        if b"fail" in body[:400] or type(self).mode == "500":
            self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"boom"}'); return
        out = json.dumps({"lines": [{"name": "MILK 2% GAL", "quantity": 1, "price": 4.29}], "total": 4.29,
                          "raw_text": "MILK 2% GAL 4.29"}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    _H.mode, _H.seen = "ok", []
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{s.server_address[1]}", _H
    s.shutdown(); s.server_close()


def test_service_engine_ok(dirs, server):
    url, h = server
    drop(dirs, "r.jpg")
    c = receipts.process_inbox(dirs, engine="service", service_url=url, timeout_s=5)
    assert c["processed"] == 1
    assert h.seen[0][0] == "/ocr" and h.seen[0][1].startswith("multipart/form-data")
    row = next(csv.DictReader(open(dirs["processed"] / "receipt_lines.csv")))
    assert (row["canonical"], row["category"], row["price"]) == ("milk", "dairy", "4.29")


def test_service_http_error_quarantines_one_file(dirs, server):
    url, h = server
    h.mode = "500"
    drop(dirs, "r.jpg", seed=1)
    drop(dirs, "s.jpg", seed=2)
    c = receipts.process_inbox(dirs, engine="service", service_url=url + "/", timeout_s=5)
    assert c == {"quarantined": 2}
    assert q(dirs, "r.jpg")["code"] == "ocr_failed"


def test_service_unreachable_stops_and_keeps_files(dirs):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    drop(dirs, "a.jpg", seed=1)
    drop(dirs, "b.jpg", seed=2)
    c = receipts.process_inbox(dirs, engine="service", service_url=f"http://127.0.0.1:{port}", timeout_s=2)
    assert "stopped" in c and "processed" not in c and "quarantined" not in c
    assert sorted(p.name for p in (dirs["incoming"] / "receipts").iterdir()) == ["a.jpg", "b.jpg"]
    assert not dirs["quarantine"].exists() or not list(dirs["quarantine"].iterdir())


def test_service_requires_url(dirs):
    drop(dirs, "a.jpg")
    with pytest.raises(ValueError):
        receipts.process_inbox(dirs, engine="service", service_url="")


def test_service_against_ml_serve_app(dirs):
    pytest.importorskip("flask")
    from werkzeug.serving import make_server
    from serve.app import create_app
    from serve.backends import FakeOCR, FakeDetector
    app = create_app(detector=FakeDetector(), ocr=FakeOCR(SIMPLE), structure_with_gemini=False)
    srv = make_server("127.0.0.1", 0, app)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        drop(dirs, "r.jpg")
        c = receipts.process_inbox(dirs, engine="service", service_url=f"http://127.0.0.1:{srv.server_port}",
                                   timeout_s=10)
    finally:
        srv.shutdown()
    assert c["processed"] == 1 and c["lines"] == 2


# ------------------------------------------------------------------ parser accuracy via the inbox
def _render(txt: str, path: Path):
    im = Image.new("RGB", (400, 20 + 14 * len(txt.splitlines())), "white")
    d = ImageDraw.Draw(im)
    for i, l in enumerate(txt.splitlines()):
        d.text((5, 5 + 14 * i), l, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


CASES = sorted(p.stem for p in FIX.glob("*.json"))
PARSER_KNOWN_DIFF = set()  # fixtures where the ML parser itself differs from ground truth (ML QA owns those)


def test_inbox_matches_parser_and_ground_truth(dirs):
    from ocr.receipt_pipeline import parse_receipt_text
    inbox = dirs["incoming"] / "receipts"
    chosen = CASES
    for n in chosen:
        _render((FIX / f"{n}.txt").read_text(), inbox / f"{n}.png")
        (inbox / f"{n}.txt").write_text((FIX / f"{n}.txt").read_text())
    c = receipts.process_inbox(dirs, engine="fake", timeout_s=10, load_grace_s=30)
    assert c["processed"] == len(chosen)
    recs = {json.loads(l)["source_file"]: json.loads(l) for l in (dirs["processed"] / "receipts.jsonl").read_text().splitlines()}
    for n in chosen:
        rec, gt = recs[f"{n}.png"], json.loads((FIX / f"{n}.json").read_text())
        parsed = parse_receipt_text((FIX / f"{n}.txt").read_text())
        got = [(l["name"], l["quantity"], l["price"]) for l in rec["lines"]]
        assert got == [(l["name"], l["quantity"], l["price"]) for l in parsed["lines"]], n
        assert rec["total"] == parsed["total"] == gt["total"], n
        assert [l["price"] for l in rec["lines"]] == [l["price"] for l in gt["lines"]] or n in PARSER_KNOWN_DIFF, n


def test_service_timeout_is_ocr_timeout(dirs, server):
    url, h = server
    h.mode = "slow"
    drop(dirs, "r.jpg")
    c = receipts.process_inbox(dirs, engine="service", service_url=url, timeout_s=1)
    assert c == {"quarantined": 1}
    assert q(dirs, "r.jpg")["code"] == "ocr_timeout"


def test_same_content_twice_in_one_pass(dirs):
    drop(dirs, "a.jpg", SIMPLE, seed=1)
    drop(dirs, "b.jpg", SIMPLE, seed=1)
    c = receipts.process_inbox(dirs, engine="fake", engine_obj=worker(5, 30))
    assert c["processed"] == 1 and c["duplicates"] == 1


def test_timeout_moves_sidecar_with_file(dirs):
    drop(dirs, "h.jpg", "HANG")
    w = worker(1.0, 3.0)
    try:
        receipts.process_inbox(dirs, engine="fake", engine_obj=w)
    finally:
        w.close()
    assert (dirs["quarantine"] / "h.txt").exists()
