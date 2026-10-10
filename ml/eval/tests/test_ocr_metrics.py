import json
import pytest

import ocr_metrics as om
from ocr_metrics import evaluate, normalise, name_ratio, match_lines, cents


def L(name, q=1, price=1.0):
    return {"name": name, "quantity": q, "price": price}


def test_normalise():
    assert normalise("  ORGANIC   Bananas!! ") == "organic bananas"
    assert normalise(None) == ""

def test_name_ratio_values():
    assert name_ratio("Milk 2%", "MILK 2%") == 1.0
    # "bananas" vs "banana": 2*6/13
    assert name_ratio("bananas", "banana") == pytest.approx(12 / 13)
    assert name_ratio("milk", "bread") < 0.5

def test_cents_rounding():
    assert cents(2.10) == 210 and cents(0.1 + 0.2) == 30 and cents(None) is None

def test_perfect_receipt():
    gt = {"r1": {"receipt": "r1", "lines": [L("Milk", 1, 3.49), L("Eggs", 1, 2.99)], "total": 6.48}}
    o = evaluate(gt, gt)["ocr"]
    assert o["line_recall"] == o["price_exact"] == o["total_exact"] == 1.0 and o["line_precision"] == 1.0

def test_fuzzy_matching_threshold_boundary():
    # ratio("bananas","banana") = .923 -> match at 0.8; not at 0.95
    gt = {"r": {"receipt": "r", "lines": [L("bananas")], "total": 1.0}}
    pr = {"r": {"receipt": "r", "lines": [L("banana")], "total": 1.0}}
    assert evaluate(gt, pr, 0.8)["ocr"]["line_recall"] == 1.0
    assert evaluate(gt, pr, 0.95)["ocr"]["line_recall"] == 0.0

def test_case_and_whitespace_insensitive():
    gt = {"r": {"receipt": "r", "lines": [L("Greek  Yogurt")], "total": 1.0}}
    pr = {"r": {"receipt": "r", "lines": [L("GREEK YOGURT ")], "total": 1.0}}
    assert evaluate(gt, pr)["ocr"]["line_recall"] == 1.0

def test_one_to_one_matching_no_double_count():
    # one predicted line cannot satisfy two identical GT lines
    gt = {"r": {"receipt": "r", "lines": [L("apple"), L("apple")], "total": 2.0}}
    pr = {"r": {"receipt": "r", "lines": [L("apple")], "total": 2.0}}
    o = evaluate(gt, pr)["ocr"]
    assert o["line_recall"] == 0.5 and o["line_precision"] == 1.0

def test_best_pairing_is_chosen():
    gt = [L("whole milk"), L("milk")]
    pr = [L("milk")]
    m = match_lines(gt, pr, 0.5)
    assert m == [(1, 0, 1.0)]  # exact beats the partial match

def test_hand_computed_aggregate():
    # r1: 4 GT lines, 3 matched, 2 of those matched prices right; total right
    # r2: 2 GT lines, 2 matched, 2 prices right; total wrong
    # r3: no prediction: 2 GT lines missed; total missed
    gt = {"r1": {"receipt": "r1", "lines": [L("a one", 1, 1.0), L("b two", 1, 2.0), L("c three", 1, 3.0), L("d four", 1, 4.0)], "total": 10.0},
          "r2": {"receipt": "r2", "lines": [L("milk", 1, 3.0), L("bread", 1, 2.0)], "total": 5.0},
          "r3": {"receipt": "r3", "lines": [L("tea", 1, 1.0), L("jam", 1, 2.0)], "total": 3.0}}
    pr = {"r1": {"lines": [L("a one", 1, 1.0), L("b two", 1, 2.5), L("c three", 1, 3.0)], "total": 10.0},
          "r2": {"lines": [L("milk", 1, 3.0), L("bread", 1, 2.0), L("extra junk", 1, 9)], "total": 5.5}}
    o = evaluate(gt, pr)["ocr"]
    assert o["gt_lines"] == 8 and o["matched_lines"] == 5
    assert o["line_recall"] == 5 / 8
    assert o["price_exact"] == 4 / 5
    assert o["total_exact"] == 1 / 3
    assert o["line_precision"] == 5 / 6
    assert o["per_receipt"]["r1"]["missed"] == ["d four"]

def test_null_total_and_null_price_never_match():
    gt = {"r": {"receipt": "r", "lines": [L("milk", 1, 3.0)], "total": 3.0}}
    pr = {"r": {"receipt": "r", "lines": [L("milk", 1, None)], "total": None}}
    o = evaluate(gt, pr)["ocr"]
    assert o["line_recall"] == 1.0 and o["price_exact"] == 0.0 and o["total_exact"] == 0.0

def test_total_compared_to_the_cent():
    gt = {"r": {"receipt": "r", "lines": [], "total": 12.34}}
    assert evaluate(gt, {"r": {"lines": [], "total": 12.340000001}})["ocr"]["total_exact"] == 1.0
    assert evaluate(gt, {"r": {"lines": [], "total": 12.35}})["ocr"]["total_exact"] == 0.0

def test_empty_everything_is_none_not_crash():
    o = evaluate({"r": {"receipt": "r", "lines": [], "total": None}}, {})["ocr"]
    assert o["line_recall"] is None and o["total_exact"] is None

def test_unknown_prediction_receipt_is_error():
    with pytest.raises(ValueError):
        evaluate({"a": {"receipt": "a", "lines": []}}, {"zz": {"lines": []}})

def test_loaders_and_cli(tmp_path, capsys):
    gd = tmp_path / "gt"; gd.mkdir()
    (gd / "r1.json").write_text(json.dumps({"lines": [L("milk", 1, 3.0)], "total": 3.0}))  # id from stem
    p = tmp_path / "p.jsonl"
    p.write_text(json.dumps({"receipt": "r1", "lines": [L("milk", 1, 3.0)], "total": 3.0, "raw_text": "x"}) + "\n")
    out = tmp_path / "o.json"
    assert om.main(["--gt", str(gd), "--pred", str(p), "--json", str(out)]) == 0
    assert json.loads(out.read_text())["ocr"]["line_recall"] == 1.0
