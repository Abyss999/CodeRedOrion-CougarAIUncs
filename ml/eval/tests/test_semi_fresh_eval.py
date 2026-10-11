"""Binary-gated, 3-class-reported freshness (docs/QA.md "Freshness gates"). Hand-computed numbers.

Gates: spoiled vs not-spoiled, semi_fresh folded into not_spoiled in GT AND predictions.
Info only: 3x3 confusion + semi_fresh P/R (never gated). Ported from LemurTech22's 7843e06 where it fits.
"""
import json
import pytest

import check_thresholds as ct
import detection_metrics as dm
from detection_metrics import evaluate


def box(i):
    return [10 * i, 0, 10 * i + 10, 10]


def lab(fresh, i, name="banana"):
    return {"name": name, "category": "produce_hardy", "freshness": fresh, "bbox": box(i)}


def pred(fresh, i, conf=0.9, name="banana"):
    return {"name": name, "category": "produce_hardy", "freshness": fresh, "confidence": conf, "bbox": box(i)}


def row(img, key, items, lighting="normal"):
    return {"image": img, "lighting": lighting, key: items}


def mixed():
    # a: GT fresh@0 semi@1 spoiled@2; preds fresh@0 semi@1 spoiled@2 (all right)
    # b: GT semi@0 spoiled@1; preds fresh@0 (semi called fresh), spoiled@1, semi@5 (no GT -> FP)
    gt = [row("a", "labels", [lab("fresh", 0), lab("semi_fresh", 1), lab("spoiled", 2)]),
          row("b", "labels", [lab("semi_fresh", 0), lab("spoiled", 1)])]
    pr = [row("a", "predictions", [pred("fresh", 0), pred("semi_fresh", 1), pred("spoiled", 2)]),
          row("b", "predictions", [pred("fresh", 0), pred("spoiled", 1), pred("semi_fresh", 5)])]
    return gt, pr


def test_constants():
    assert dm.FRESHNESS3 == ("fresh", "semi_fresh", "spoiled")
    assert dm.FRESHNESS == ("not_spoiled", "spoiled")


def test_fold():
    assert [dm.fold(x) for x in ("fresh", "semi_fresh", "spoiled")] == ["not_spoiled", "not_spoiled", "spoiled"]
    for bad in ("rotten", "", None, "Semi_Fresh"):
        with pytest.raises(ValueError):
            dm.fold(bad)


def test_binary_folding_hand_computed():
    gt, pr = mixed()
    f = evaluate(gt, pr)["detection"]["freshness"]
    # not_spoiled GT: a0,a1,b0 = 3. preds not_spoiled: a0,a1,b0,b5(FP) -> tp3 fp1 fn0
    assert (f["not_spoiled"]["tp"], f["not_spoiled"]["fp"], f["not_spoiled"]["fn"]) == (3, 1, 0)
    assert f["not_spoiled"]["precision"] == pytest.approx(3 / 4) and f["not_spoiled"]["recall"] == 1.0
    # spoiled perfect
    assert f["spoiled"]["precision"] == 1.0 and f["spoiled"]["recall"] == 1.0
    o = f["overall"]
    assert (o["tp"], o["fp"], o["fn"], o["n_gt"]) == (5, 1, 0, 5)
    assert f["fresh"] == f["not_spoiled"]  # legacy alias


def test_fresh_semi_confusion_costs_nothing_in_gates():
    # every semi_fresh GT predicted as fresh and vice versa: binary metrics are perfect
    gt = [row("a", "labels", [lab("fresh", 0), lab("semi_fresh", 1), lab("spoiled", 2)])]
    pr = [row("a", "predictions", [pred("semi_fresh", 0), pred("fresh", 1), pred("spoiled", 2)])]
    d = evaluate(gt, pr)["detection"]
    f = d["freshness"]
    assert f["not_spoiled"]["precision"] == 1.0 and f["not_spoiled"]["recall"] == 1.0
    assert f["spoiled"]["recall"] == 1.0
    # ...but the information-only 3-way view sees it
    t = d["freshness_3way"]
    assert t["confusion"]["fresh"]["semi_fresh"] == 1 and t["confusion"]["semi_fresh"]["fresh"] == 1
    assert t["fresh"]["precision"] == 0.0 and t["semi_fresh"]["recall"] == 0.0


def test_spoiled_called_semi_is_a_gated_miss_and_semi_called_spoiled_is_gated_fp():
    gt = [row("a", "labels", [lab("spoiled", 0), lab("semi_fresh", 1)])]
    pr = [row("a", "predictions", [pred("semi_fresh", 0), pred("spoiled", 1)])]
    f = evaluate(gt, pr)["detection"]["freshness"]
    assert f["spoiled"]["recall"] == 0.0 and f["spoiled"]["precision"] == 0.0
    assert f["not_spoiled"]["recall"] == 0.0 and f["not_spoiled"]["precision"] == 0.0


def test_3x3_confusion_hand_computed():
    gt, pr = mixed()
    t = evaluate(gt, pr)["detection"]["freshness_3way"]
    assert t["gated"] is False and t["labels"] == ["fresh", "semi_fresh", "spoiled"]
    c = t["confusion"]
    assert c["fresh"] == {"fresh": 1, "semi_fresh": 0, "spoiled": 0, "missed": 0}
    assert c["semi_fresh"] == {"fresh": 1, "semi_fresh": 1, "spoiled": 0, "missed": 0}
    assert c["spoiled"] == {"fresh": 0, "semi_fresh": 0, "spoiled": 2, "missed": 0}
    assert t["false_positive"] == {"fresh": 0, "semi_fresh": 1, "spoiled": 0}
    # semi: tp1, preds-as-semi = 1 (a1) + 1 FP (b5) = 2 -> P .5; GT semi = 2 -> R .5
    assert (t["semi_fresh"]["precision"], t["semi_fresh"]["recall"]) == (0.5, 0.5)
    # fresh: tp1, preds-as-fresh = a0 + b0 = 2 -> P .5; GT fresh 1 -> R 1
    assert (t["fresh"]["precision"], t["fresh"]["recall"]) == (0.5, 1.0)
    assert (t["spoiled"]["precision"], t["spoiled"]["recall"]) == (1.0, 1.0)


def test_3x3_missed_and_conf_cutoff_and_name():
    gt = [row("a", "labels", [lab("semi_fresh", 0), lab("fresh", 1, "apple")])]
    pr = [row("a", "predictions", [pred("semi_fresh", 0, 0.1), pred("fresh", 1, 0.9, "pear")])]
    t = evaluate(gt, pr, conf=0.25)["detection"]["freshness_3way"]
    assert t["confusion"]["semi_fresh"]["missed"] == 1  # below conf
    assert t["confusion"]["fresh"]["fresh"] == 1        # name ignored by default
    t = evaluate(gt, pr, conf=0.25, match_name=True)["detection"]["freshness_3way"]
    assert t["confusion"]["fresh"]["missed"] == 1 and t["false_positive"]["fresh"] == 1


def test_semi_absent_gives_none_not_crash():
    gt = [row("a", "labels", [lab("fresh", 0)])]
    pr = [row("a", "predictions", [pred("fresh", 0)])]
    t = evaluate(gt, pr)["detection"]["freshness_3way"]
    assert t["semi_fresh"]["precision"] is None and t["semi_fresh"]["recall"] is None and t["semi_fresh"]["n_gt"] == 0


def test_two_class_files_unchanged():
    gt = [row("a", "labels", [lab("fresh", 0), lab("spoiled", 1)])]
    pr = [row("a", "predictions", [pred("fresh", 0), pred("spoiled", 1)])]
    d = evaluate(gt, pr)["detection"]
    assert d["freshness"]["not_spoiled"]["recall"] == 1.0 and d["freshness"]["spoiled"]["recall"] == 1.0
    assert d["freshness_3way"]["semi_fresh"]["recall"] is None
    # 2-class predictions against 3-class GT: semi_fresh GT predicted "fresh" still counts as right for the gates
    gt = [row("a", "labels", [lab("semi_fresh", 0)])]
    pr = [row("a", "predictions", [pred("fresh", 0)])]
    assert evaluate(gt, pr)["detection"]["freshness"]["not_spoiled"]["recall"] == 1.0


def test_unknown_freshness_rejected():
    gt = [row("a", "labels", [lab("fresh", 0)])]
    with pytest.raises(ValueError):
        evaluate(gt, [row("a", "predictions", [pred("rotten", 0)])])
    with pytest.raises(ValueError):
        evaluate([row("a", "labels", [lab("ripe", 0)])], [row("a", "predictions", [])])


def test_lighting_drop_gated_keys_fold_semi_and_semi_is_info():
    gt, pr = mixed()
    # low image: semi missed entirely, spoiled found. normal: not-spoiled recall 1.0, semi recall .5
    gt.append(row("c", "labels", [lab("semi_fresh", 0), lab("spoiled", 1)], "low"))
    pr.append(row("c", "predictions", [pred("spoiled", 1)], "low"))
    res = evaluate(gt, pr)
    d = res["detection"]["recall_drop_points"]["low"]
    assert set(d) == {"overall", "spoiled", "not_spoiled", "fresh", "semi_fresh"}
    assert d["not_spoiled"] == pytest.approx(100.0)  # 1.0 -> 0 (the only not-spoiled GT in low is the semi)
    assert d["spoiled"] == pytest.approx(0.0)
    assert d["semi_fresh"] == pytest.approx(50.0)    # .5 -> 0
    dm.print_report(res)


def test_report_prints_matrix(capsys):
    gt, pr = mixed()
    dm.print_report(evaluate(gt, pr))
    out = capsys.readouterr().out
    assert "NOT gated" in out and "semi_fresh" in out and "false_pos" in out and "not_spoiled" in out


def test_lighting_sources_semi_info(tmp_path):
    gt = [row("n", "labels", [lab("semi_fresh", 0)], "normal"), row("l", "labels", [lab("semi_fresh", 0)], "low")]
    pr = [row("n", "predictions", [pred("semi_fresh", 0)], "normal"), row("l", "predictions", [], "low")]
    man = {"n": {"lighting_method": "auto", "variant_of": ""}, "l": {"lighting_method": "manual", "variant_of": ""}}
    ls = dm.evaluate_lighting_sources(gt, pr, man)
    assert ls["real"]["recall_drop_points"]["low"]["not_spoiled"] == pytest.approx(100.0)
    assert ls["real"]["recall_drop_points"]["low"]["semi_fresh"] == pytest.approx(100.0)


# ---------- check_thresholds: gates are binary; semi_fresh never gated ----------
def good_det():
    return {"detection": {"map50": 0.7,
            "freshness": {"not_spoiled": {"precision": 0.9, "recall": 0.9}, "spoiled": {"precision": 0.85, "recall": 0.9}},
            "recall_drop_points": {"low": {"overall": 5.0, "spoiled": 8.0}, "warm": {"overall": 0.0, "spoiled": 10.0}}}}


def test_semi_fresh_is_reported_not_gated():
    m = good_det()
    base = ct.run_checks(m)
    assert not any("semi" in n.lower() for n, _, _ in base)
    m["detection"]["freshness_3way"] = {"semi_fresh": {"precision": 0.0, "recall": 0.0}, "gated": False}
    m["detection"]["recall_drop_points"]["low"]["semi_fresh"] = 99.0
    assert ct.run_checks(m) == base
    m["detection"]["freshness_3way"]["semi_fresh"] = {"precision": None, "recall": None}
    m["detection"]["recall_drop_points"]["low"]["semi_fresh"] = None
    assert ct.run_checks(m) == base


def test_precision_gate_reads_not_spoiled_and_ignores_legacy_fresh_when_present():
    m = good_det()
    m["detection"]["freshness"]["fresh"] = {"precision": 0.1, "recall": 0.1}  # must be ignored
    assert {n: s for n, s, _ in ct.run_checks(m)}["YOLO precision [not-spoiled]"] == "PASS"
    m["detection"]["freshness"]["not_spoiled"]["precision"] = 0.79
    assert {n: s for n, s, _ in ct.run_checks(m)}["YOLO precision [not-spoiled]"] == "FAIL"


def test_legacy_fresh_key_still_gated_for_old_metric_files():
    m = good_det()
    m["detection"]["freshness"]["fresh"] = m["detection"]["freshness"].pop("not_spoiled")
    m["detection"]["freshness"]["fresh"]["precision"] = 0.5
    assert {n: s for n, s, _ in ct.run_checks(m)}["YOLO precision [not-spoiled]"] == "FAIL"
    del m["detection"]["freshness"]["fresh"]
    assert {n: s for n, s, _ in ct.run_checks(m)}["YOLO precision [not-spoiled]"] == "FAIL"  # missing = not evaluable


def test_end_to_end_semi_passes_gates_with_fresh_semi_confusion(tmp_path):
    # many fresh<->semi swaps, spoiled/not-spoiled perfect: every gate passes via the JSON round trip
    n = 6
    gt = [row(lt, "labels", [lab("fresh" if i % 2 else "semi_fresh", i) for i in range(n)] + [lab("spoiled", n)], lt)
          for lt in ("normal", "low", "warm")]
    pr = [row(lt, "predictions", [pred("semi_fresh" if i % 2 else "fresh", i) for i in range(n)] + [pred("spoiled", n)], lt)
          for lt in ("normal", "low", "warm")]
    g = tmp_path / "g.jsonl"; p = tmp_path / "p.jsonl"; o = tmp_path / "o.json"
    g.write_text("\n".join(json.dumps(r) for r in gt)); p.write_text("\n".join(json.dumps(r) for r in pr))
    assert dm.main(["--gt", str(g), "--pred", str(p), "--json", str(o)]) == 0
    assert ct.main([str(o), "--allow-missing-section", "ocr"]) == 0


# ---------- semi_fresh P/R with Wilson 95% CIs (information only) ----------
def test_semi_fresh_pr_has_wilson_ci_hand_computed():
    gt, pr = mixed()
    t = evaluate(gt, pr)["detection"]["freshness_3way"]["semi_fresh"]
    # tp 1, n_pred 2 (a1 + FP b5), n_gt 2 -> P = R = 0.5 with the n=2 Wilson interval
    assert (t["tp"], t["n_pred"], t["n_gt"]) == (1, 2, 2)
    assert t["precision_ci95"] == pytest.approx(list(dm.wilson_ci(1, 2)))
    assert t["recall_ci95"] == pytest.approx(list(dm.wilson_ci(1, 2)))
    lo, hi = t["recall_ci95"]
    assert lo == pytest.approx(0.0945, abs=1e-3) and hi == pytest.approx(0.9055, abs=1e-3)
    assert lo < t["recall"] < hi and hi - lo > 0.5          # n=2: the interval is wide, which is the point


def test_semi_fresh_ci_none_when_no_denominator():
    gt = [row("a", "labels", [lab("fresh", 0)])]
    pr = [row("a", "predictions", [pred("fresh", 0)])]
    t = evaluate(gt, pr)["detection"]["freshness_3way"]
    assert t["semi_fresh"]["precision"] is None and t["semi_fresh"]["precision_ci95"] == [None, None]
    assert t["semi_fresh"]["recall"] is None and t["semi_fresh"]["recall_ci95"] == [None, None]
    assert all(0 <= t["fresh"][k][0] <= t["fresh"][k][1] <= 1 for k in ("precision_ci95", "recall_ci95"))


def test_ci_present_for_every_class_and_json_serialisable():
    gt, pr = mixed()
    t = evaluate(gt, pr)["detection"]["freshness_3way"]
    for c in dm.FRESHNESS3:
        assert set(("precision_ci95", "recall_ci95")) <= set(t[c])
    json.dumps(t)
    assert t["gated"] is False


def test_semi_fresh_by_source_real_only_and_per_source():
    # source A: 2 semi GT, 1 found, 1 FP; source B: 1 semi GT found. A synthetic copy of A must not add a sample.
    gt = [row("a1", "labels", [lab("semi_fresh", 0), lab("semi_fresh", 1)]),
          row("b1", "labels", [lab("semi_fresh", 0)]),
          row("a1__low", "labels", [lab("semi_fresh", 0), lab("semi_fresh", 1)], "low")]
    pr = [row("a1", "predictions", [pred("semi_fresh", 0), pred("semi_fresh", 7)]),
          row("b1", "predictions", [pred("semi_fresh", 0)]),
          row("a1__low", "predictions", [pred("semi_fresh", 0), pred("semi_fresh", 1)], "low")]
    man = {"a1": {"lighting_method": "auto", "source": "A"}, "b1": {"lighting_method": "auto", "source": "B"},
           "a1__low": {"lighting_method": "synthetic", "source": "A"}}
    r = dm.semi_fresh_by_source(gt, pr, man)
    a = r["by_source"]["A"]
    assert (a["tp"], a["n_gt"], a["n_pred"]) == (1, 2, 2) and a["recall"] == 0.5 and a["precision"] == 0.5
    assert a["recall_ci95"] == pytest.approx(list(dm.wilson_ci(1, 2)))
    b = r["by_source"]["B"]
    assert (b["recall"], b["precision"], b["n_gt"]) == (1.0, 1.0, 1)
    assert r["all"]["n_gt"] == 3 and r["all"]["tp"] == 2
    assert dm.semi_fresh_by_source(gt, pr, man, real_only=False)["all"]["n_gt"] == 5


def test_main_reports_semi_fresh_by_source_and_never_gates_on_it(tmp_path, capsys):
    gt = [row("a", "labels", [lab("semi_fresh", 0), lab("spoiled", 1)])]
    pr = [row("a", "predictions", [pred("fresh", 0), pred("spoiled", 1)])]       # semi_fresh recall 0, still passes the gates
    g = tmp_path / "g.jsonl"; p = tmp_path / "p.jsonl"; o = tmp_path / "o.json"; m = tmp_path / "m.csv"
    g.write_text(json.dumps(gt[0])); p.write_text(json.dumps(pr[0]))
    m.write_text("image,lighting_method,variant_of,source\na,auto,,S\n")
    assert dm.main(["--gt", str(g), "--pred", str(p), "--json", str(o), "--manifest", str(m)]) == 0
    out = capsys.readouterr().out
    assert "semi_fresh precision / recall with 95% Wilson CI" in out and "NOT a gate" in out
    res = json.loads(o.read_text())["detection"]
    assert res["semi_fresh_by_source"]["by_source"]["S"]["recall"] == 0.0
    names = {n for n, _, _ in ct.run_checks(json.loads(o.read_text()))}
    assert not any("semi" in n.lower() for n in names)                          # check_thresholds has no semi_fresh gate
