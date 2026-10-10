import json
import check_thresholds as ct


def good_det():
    return {"detection": {"map50": 0.7,
            "freshness": {"fresh": {"precision": 0.9, "recall": 0.9}, "spoiled": {"precision": 0.85, "recall": 0.9}},
            "recall_drop_points": {"low": {"overall": 5.0, "spoiled": 8.0}, "warm": {"overall": 0.0, "spoiled": 10.0}}}}

def good_ocr():
    return {"ocr": {"n_receipts": 20, "line_recall": 0.9, "price_exact": 0.95, "total_exact": 0.9}}

def status(m, name):
    return {n: s for n, s, _ in ct.run_checks(m)}[name]

def test_all_pass_at_boundaries():
    m = {**good_det(), **good_ocr()}
    m["detection"]["map50"] = 0.60
    m["detection"]["freshness"]["fresh"]["precision"] = 0.80
    m["detection"]["freshness"]["spoiled"]["recall"] = 0.85
    assert all(s == "PASS" for _, s, _ in ct.run_checks(m))

def test_each_threshold_can_fail():
    cases = [
        (lambda m: m["detection"].__setitem__("map50", 0.599), "YOLO mAP@0.5"),
        (lambda m: m["detection"]["freshness"]["fresh"].__setitem__("precision", 0.79), "YOLO precision [fresh]"),
        (lambda m: m["detection"]["freshness"]["spoiled"].__setitem__("precision", 0.79), "YOLO precision [spoiled]"),
        (lambda m: m["detection"]["freshness"]["spoiled"].__setitem__("recall", 0.849), "YOLO recall [spoiled]"),
        (lambda m: m["detection"]["recall_drop_points"]["low"].__setitem__("overall", 10.1), "YOLO recall drop low vs normal (overall)"),
        (lambda m: m["detection"]["recall_drop_points"]["warm"].__setitem__("spoiled", 10.5), "YOLO recall drop warm vs normal (spoiled)"),
        (lambda m: m["ocr"].__setitem__("line_recall", 0.84), "OCR line-item recall"),
        (lambda m: m["ocr"].__setitem__("price_exact", 0.89), "OCR price exact"),
        (lambda m: m["ocr"].__setitem__("total_exact", 0.89), "OCR total exact"),
        (lambda m: m["ocr"].__setitem__("n_receipts", 19), "OCR sample size"),
    ]
    for mutate, name in cases:
        m = {**good_det(), **good_ocr()}
        mutate(m)
        assert status(m, name) == "FAIL", name

def test_none_metric_fails_not_passes():
    m = {**good_det(), **good_ocr()}
    m["detection"]["freshness"]["spoiled"]["precision"] = None
    assert status(m, "YOLO precision [spoiled]") == "FAIL"

def test_missing_section_fails_unless_allowed():
    assert any(s == "FAIL" for _, s, _ in ct.run_checks(good_ocr()))

def test_cli_exit_codes(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({**good_det(), **good_ocr()}))
    assert ct.main([str(p)]) == 0
    bad = {**good_det(), **good_ocr()}; bad["ocr"]["total_exact"] = 0.1
    p.write_text(json.dumps(bad))
    assert ct.main([str(p)]) == 1
    p.write_text(json.dumps(good_ocr()))
    assert ct.main([str(p)]) == 1
    assert ct.main([str(p), "--allow-missing-section", "det"]) == 0


def test_end_to_end_cli_on_fixtures(tmp_path):
    import os, detection_metrics as dm
    from conftest import EVAL_DIR
    d = os.path.join(EVAL_DIR, "fixtures", "detection")
    out = tmp_path / "det.json"
    assert dm.main(["--gt", os.path.join(d, "gt.jsonl"), "--pred", os.path.join(d, "pred_perfect.jsonl"), "--json", str(out)]) == 0
    m = json.loads(out.read_text())
    assert m["detection"]["map50"] == 1.0
    # no OCR section supplied -> OCR fails unless explicitly allowed
    assert ct.main([str(out)]) == 1
    assert ct.main([str(out), "--allow-missing-section", "ocr"]) == 0


def test_semi_fresh_is_reported_not_gated():
    m = good_det()
    names = [n for n, _, _ in ct.run_checks(m)]
    assert not any("semi" in n for n in names)
    # terrible / missing semi_fresh numbers never change any status
    base = ct.run_checks(m)
    m["detection"]["freshness"]["semi_fresh"] = {"precision": 0.0, "recall": 0.0}
    m["detection"]["recall_drop_points"]["low"]["semi_fresh"] = 99.0
    assert ct.run_checks(m) == base
    m["detection"]["freshness"]["semi_fresh"] = {"precision": None, "recall": None}
    assert ct.run_checks(m) == base
