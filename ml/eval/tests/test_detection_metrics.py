"""Hand-computed checks for detection_metrics. Every expected number is derived in a comment."""
import json
import pytest

import detection_metrics as dm
from detection_metrics import evaluate, iou, average_precision


def box(i):  # non-overlapping 10x10 boxes along x
    return [10 * i, 0, 10 * i + 10, 10]


def lab(name, fresh, i):
    return {"name": name, "category": "produce_hardy", "freshness": fresh, "bbox": box(i)}


def pred(name, fresh, i, conf=0.9, bbox=None):
    return {"name": name, "category": "produce_hardy", "freshness": fresh, "confidence": conf, "bbox": bbox or box(i)}


def row(img, key, items, lighting="normal"):
    return {"image": img, "lighting": lighting, key: items}


# ---------- IoU ----------
def test_iou_identical_is_one():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0

def test_iou_disjoint_and_touching_are_zero():
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    assert iou([0, 0, 10, 10], [10, 0, 20, 10]) == 0.0  # shared edge only

def test_iou_half_overlap_is_one_third():
    # inter 5*10=50, union 100+100-50=150
    assert iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)

def test_iou_containment():
    # inner 5x5=25 inside 10x10=100 -> 25/100
    assert iou([0, 0, 10, 10], [2, 2, 7, 7]) == pytest.approx(0.25)

def test_iou_degenerate_zero_area_boxes():
    assert iou([5, 5, 5, 5], [5, 5, 5, 5]) == 0.0

def test_iou_exactly_half_matches_and_just_below_does_not():
    gt = [row("a", "labels", [lab("apple", "fresh", 0)])]
    exact = [row("a", "predictions", [pred("apple", "fresh", 0, bbox=[0, 0, 10, 5])])]   # IoU 50/100 = 0.5
    below = [row("a", "predictions", [pred("apple", "fresh", 0, bbox=[0, 0, 10, 4.9])])]  # 49/100
    assert evaluate(gt, exact)["detection"]["freshness"]["fresh"]["tp"] == 1
    r = evaluate(gt, below)["detection"]["freshness"]["fresh"]
    assert (r["tp"], r["fp"], r["fn"]) == (0, 1, 1)


# ---------- AP ----------
def test_average_precision_known_curve():
    # TP, FP, TP over 2 GT: points (R,P) = (.5,1), (.5,.5), (1,2/3) -> AP = .5*1 + .5*(2/3)
    assert average_precision([0.5, 0.5, 1.0], [1.0, 0.5, 2 / 3]) == pytest.approx(5 / 6)

def test_perfect_predictions_give_all_ones():
    gt = [row("i1", "labels", [lab("apple", "fresh", 0), lab("milk", "spoiled", 1)]),
          row("i2", "labels", [lab("apple", "spoiled", 0)], "low")]
    pr = [row("i1", "predictions", [pred("apple", "fresh", 0), pred("milk", "spoiled", 1)]),
          row("i2", "predictions", [pred("apple", "spoiled", 0)], "low")]
    d = evaluate(gt, pr)["detection"]
    assert d["map50"] == 1.0
    for c in ("fresh", "spoiled", "overall"):
        assert d["freshness"][c]["precision"] == 1.0 and d["freshness"][c]["recall"] == 1.0

def test_map_two_classes_hand_computed():
    # apple: 2 GT, preds TP(.9) FP(.8, empty space) TP(.7) -> AP 5/6. banana: perfect -> 1.0. mAP = (5/6+1)/2 = 11/12
    gt = [row("i", "labels", [lab("apple", "fresh", 0), lab("apple", "fresh", 1), lab("banana", "fresh", 5)])]
    pr = [row("i", "predictions", [pred("apple", "fresh", 0, 0.9), pred("apple", "fresh", 9, 0.8),
                                   pred("apple", "fresh", 1, 0.7), pred("banana", "fresh", 5, 0.6)])]
    d = evaluate(gt, pr)["detection"]
    assert d["ap_per_class"]["apple"] == pytest.approx(5 / 6)
    assert d["ap_per_class"]["banana"] == 1.0
    assert d["map50"] == pytest.approx(11 / 12)

def test_ap_wrong_name_is_not_a_hit():
    gt = [row("i", "labels", [lab("apple", "fresh", 0)])]
    pr = [row("i", "predictions", [pred("pear", "fresh", 0)])]
    d = evaluate(gt, pr)["detection"]
    assert d["ap_per_class"] == {"apple": 0.0}
    assert d["map50"] == 0.0

def test_class_with_gt_but_no_predictions_counts_zero_in_map():
    gt = [row("i", "labels", [lab("apple", "fresh", 0), lab("milk", "fresh", 1)])]
    pr = [row("i", "predictions", [pred("apple", "fresh", 0)])]
    assert evaluate(gt, pr)["detection"]["map50"] == pytest.approx(0.5)

def test_duplicate_detection_of_one_gt_is_a_false_positive():
    # GT 1; preds .9 TP, .8 duplicate FP -> PR (1,1),(1,.5) -> AP 1.0, precision 1/2
    gt = [row("i", "labels", [lab("apple", "fresh", 0)])]
    pr = [row("i", "predictions", [pred("apple", "fresh", 0, 0.9), pred("apple", "fresh", 0, 0.8)])]
    d = evaluate(gt, pr)["detection"]
    assert d["ap_per_class"]["apple"] == 1.0
    f = d["freshness"]["fresh"]
    assert (f["tp"], f["fp"], f["fn"]) == (1, 1, 0) and f["precision"] == 0.5

def test_greedy_by_confidence_not_file_order():
    # Two preds overlap the single GT; the higher-confidence one (listed second) must win.
    gt = [row("i", "labels", [lab("apple", "fresh", 0)])]
    good = pred("apple", "fresh", 0, 0.9)
    lowc = pred("apple", "fresh", 0, 0.5, bbox=[0, 0, 10, 6])  # IoU .6
    pr = [row("i", "predictions", [lowc, good])]
    # TP is the .9 one first -> curve (1,1),(1,.5): AP=1.0 ; if file order were used it would still be 1, so check AP via FP first:
    d = evaluate(gt, pr)["detection"]
    assert d["ap_per_class"]["apple"] == 1.0
    # confidence ordering matters when the first-ranked pred is the wrong one:
    bad_hi = pred("apple", "fresh", 9, 0.95)  # empty space
    pr2 = [row("i", "predictions", [good, bad_hi])]
    # ranking: bad(FP) then good(TP): (0,0),(1,.5) -> envelope .5 -> AP .5
    assert evaluate(gt, pr2)["detection"]["ap_per_class"]["apple"] == pytest.approx(0.5)


# ---------- fresh / spoiled precision & recall ----------
def test_known_fp_fn_counts():
    # fresh GT: 3 (boxes 0,1,2). spoiled GT: 2 (boxes 3,4).
    # preds fresh: box0 ok, box1 ok, box8 spurious (FP) -> fresh tp2 fp1 fn1 -> P 2/3, R 2/3
    # preds spoiled: box3 ok -> spoiled tp1 fp0 fn1 -> P 1, R 1/2
    gt = [row("i", "labels", [lab("a", "fresh", 0), lab("a", "fresh", 1), lab("a", "fresh", 2),
                              lab("b", "spoiled", 3), lab("b", "spoiled", 4)])]
    pr = [row("i", "predictions", [pred("a", "fresh", 0), pred("a", "fresh", 1), pred("a", "fresh", 8),
                                   pred("b", "spoiled", 3)])]
    f = evaluate(gt, pr)["detection"]["freshness"]
    assert (f["fresh"]["tp"], f["fresh"]["fp"], f["fresh"]["fn"]) == (2, 1, 1)
    assert f["fresh"]["precision"] == pytest.approx(2 / 3) and f["fresh"]["recall"] == pytest.approx(2 / 3)
    assert (f["spoiled"]["tp"], f["spoiled"]["fp"], f["spoiled"]["fn"]) == (1, 0, 1)
    assert f["spoiled"]["precision"] == 1.0 and f["spoiled"]["recall"] == 0.5
    # overall: tp3 fp1 fn2 -> P .75, R .6
    assert f["overall"]["precision"] == 0.75 and f["overall"]["recall"] == pytest.approx(0.6)

def test_wrong_freshness_label_is_fp_for_predicted_class_and_fn_for_true_class():
    gt = [row("i", "labels", [lab("a", "spoiled", 0)])]
    pr = [row("i", "predictions", [pred("a", "fresh", 0)])]
    f = evaluate(gt, pr)["detection"]["freshness"]
    assert (f["fresh"]["tp"], f["fresh"]["fp"], f["fresh"]["fn"]) == (0, 1, 0)
    assert (f["spoiled"]["tp"], f["spoiled"]["fp"], f["spoiled"]["fn"]) == (0, 0, 1)
    assert f["spoiled"]["recall"] == 0.0
    assert f["fresh"]["precision"] == 0.0
    assert f["fresh"]["recall"] is None  # no fresh GT at all -> undefined, not 0 or 1

def test_empty_predictions():
    gt = [row("i", "labels", [lab("a", "fresh", 0), lab("b", "spoiled", 1)])]
    pr = [row("i", "predictions", [])]
    d = evaluate(gt, pr)["detection"]
    assert d["map50"] == 0.0
    assert d["freshness"]["fresh"]["recall"] == 0.0 and d["freshness"]["fresh"]["precision"] is None
    assert d["freshness"]["spoiled"]["recall"] == 0.0

def test_missing_prediction_row_is_all_misses():
    gt = [row("i", "labels", [lab("a", "fresh", 0)]), row("j", "labels", [lab("a", "fresh", 0)])]
    pr = [row("i", "predictions", [pred("a", "fresh", 0)])]
    f = evaluate(gt, pr)["detection"]["freshness"]["fresh"]
    assert (f["tp"], f["fn"]) == (1, 1)

def test_empty_gt_image_with_preds_are_false_positives():
    gt = [row("i", "labels", [lab("a", "fresh", 0)]), row("empty", "labels", [])]
    pr = [row("i", "predictions", [pred("a", "fresh", 0)]), row("empty", "predictions", [pred("a", "fresh", 0)])]
    f = evaluate(gt, pr)["detection"]["freshness"]["fresh"]
    assert (f["tp"], f["fp"], f["fn"]) == (1, 1, 0)

def test_preds_do_not_cross_images():
    gt = [row("i", "labels", [lab("a", "fresh", 0)]), row("j", "labels", [])]
    pr = [row("i", "predictions", []), row("j", "predictions", [pred("a", "fresh", 0)])]
    f = evaluate(gt, pr)["detection"]["freshness"]["fresh"]
    assert (f["tp"], f["fp"], f["fn"]) == (0, 1, 1)

def test_conf_threshold_applies_to_pr_but_not_map():
    gt = [row("i", "labels", [lab("a", "fresh", 0)])]
    pr = [row("i", "predictions", [pred("a", "fresh", 0, 0.9), pred("a", "fresh", 9, 0.1)])]
    lo = evaluate(gt, pr, conf=0.0)["detection"]
    hi = evaluate(gt, pr, conf=0.25)["detection"]
    assert lo["freshness"]["fresh"]["precision"] == 0.5
    assert hi["freshness"]["fresh"]["precision"] == 1.0
    assert lo["map50"] == hi["map50"] == 1.0

def test_match_name_flag():
    gt = [row("i", "labels", [lab("apple", "spoiled", 0)])]
    pr = [row("i", "predictions", [pred("pear", "spoiled", 0)])]
    assert evaluate(gt, pr)["detection"]["freshness"]["spoiled"]["recall"] == 1.0
    assert evaluate(gt, pr, match_name=True)["detection"]["freshness"]["spoiled"]["recall"] == 0.0


# ---------- lighting split ----------
def test_lighting_split_and_recall_drop():
    # normal: 4 GT all found -> recall 1.0. low: 4 GT, 3 found -> .75 (drop 25). warm: 4 GT, 4 found but
    # 1 spoiled of 2 missed? -> make warm: 2 spoiled GT, 1 found; 2 fresh GT both found -> overall 3/4 = .75
    def gts(img, lt):
        return row(img, "labels", [lab("a", "fresh", 0), lab("a", "fresh", 1), lab("b", "spoiled", 2), lab("b", "spoiled", 3)], lt)
    gt = [gts("n", "normal"), gts("l", "low"), gts("w", "warm")]
    full = [pred("a", "fresh", 0), pred("a", "fresh", 1), pred("b", "spoiled", 2), pred("b", "spoiled", 3)]
    pr = [row("n", "predictions", full, "normal"),
          row("l", "predictions", full[:3], "low"),                       # misses one spoiled
          row("w", "predictions", [full[0], full[1], full[2]], "warm")]   # same
    d = evaluate(gt, pr)["detection"]
    assert d["by_lighting"]["normal"]["freshness"]["overall"]["recall"] == 1.0
    assert d["by_lighting"]["low"]["freshness"]["overall"]["recall"] == 0.75
    assert d["by_lighting"]["low"]["freshness"]["spoiled"]["recall"] == 0.5
    dr = d["recall_drop_points"]
    assert dr["low"]["overall"] == pytest.approx(25.0)
    assert dr["low"]["spoiled"] == pytest.approx(50.0)
    assert dr["warm"]["fresh"] == pytest.approx(0.0)
    # pooled over all three groups: 11 of 12 found
    assert d["freshness"]["overall"]["recall"] == pytest.approx(10 / 12)

def test_lighting_groups_are_independent_in_map():
    gt = [row("n", "labels", [lab("a", "fresh", 0)], "normal"), row("l", "labels", [lab("a", "fresh", 0)], "low")]
    pr = [row("n", "predictions", [pred("a", "fresh", 0)], "normal"), row("l", "predictions", [], "low")]
    d = evaluate(gt, pr)["detection"]
    assert d["by_lighting"]["normal"]["map50"] == 1.0 and d["by_lighting"]["low"]["map50"] == 0.0
    assert d["recall_drop_points"]["low"]["overall"] == pytest.approx(100.0)

def test_negative_drop_when_group_is_better():
    gt = [row("n", "labels", [lab("a", "fresh", 0), lab("a", "fresh", 1)], "normal"),
          row("w", "labels", [lab("a", "fresh", 0), lab("a", "fresh", 1)], "warm")]
    pr = [row("n", "predictions", [pred("a", "fresh", 0)], "normal"),
          row("w", "predictions", [pred("a", "fresh", 0), pred("a", "fresh", 1)], "warm")]
    assert evaluate(gt, pr)["detection"]["recall_drop_points"]["warm"]["overall"] == pytest.approx(-50.0)

def test_unknown_prediction_image_is_an_error():
    with pytest.raises(ValueError):
        evaluate([row("a", "labels", [])], [row("zzz", "predictions", [])])

def test_duplicate_image_rows_rejected():
    with pytest.raises(ValueError):
        evaluate([row("a", "labels", []), row("a", "labels", [])], [])


# ---------- CLI ----------
def test_cli_writes_json(tmp_path, capsys):
    g = tmp_path / "gt.jsonl"; p = tmp_path / "p.jsonl"; o = tmp_path / "o.json"
    g.write_text(json.dumps(row("i", "labels", [lab("a", "spoiled", 0)])) + "\n")
    p.write_text(json.dumps(row("i", "predictions", [pred("a", "spoiled", 0)])) + "\n")
    assert dm.main(["--gt", str(g), "--pred", str(p), "--json", str(o)]) == 0
    assert json.loads(o.read_text())["detection"]["map50"] == 1.0
    assert "mAP@0.5" in capsys.readouterr().out


def test_lighting_sources_real_vs_synthetic():
    # real normal n1 (2 GT, 2 found); real low l1 (2 GT, 1 found) -> real drop 50.
    # synthetic low s1 derived from n1 (2 GT, 2 found) -> synthetic drop 0.
    gts = lambda i, lt: row(i, "labels", [lab("a", "fresh", 0), lab("a", "fresh", 1)], lt)
    gt = [gts("n1", "normal"), gts("l1", "low"), gts("s1", "low")]
    two = [pred("a", "fresh", 0), pred("a", "fresh", 1)]
    pr = [row("n1", "predictions", two), row("l1", "predictions", two[:1], "low"), row("s1", "predictions", two, "low")]
    man = {"n1": {"lighting_method": "auto", "variant_of": ""}, "l1": {"lighting_method": "auto", "variant_of": ""},
           "s1": {"lighting_method": "synthetic", "variant_of": "n1"}}
    ls = dm.evaluate_lighting_sources(gt, pr, man)
    assert ls["n_real"] == 2 and ls["n_synthetic"] == 1
    assert ls["real"]["recall_drop_points"]["low"]["overall"] == pytest.approx(50.0)
    assert ls["synthetic"]["recall_drop_points"]["low"]["overall"] == pytest.approx(0.0)
