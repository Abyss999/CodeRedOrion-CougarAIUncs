"""Black-box test of the builder's deterministic receipt text parser (ml/ocr) against the
>=20 hand-written fixtures in fixtures/receipts/ (NN_x.txt text + NN_x.json ground truth).

Discovery: the first callable named parse_receipt_text / parse_receipt / parse_text / parse in any
module under ml/ocr, or override with env ML_PARSER="module_path_or_dotted:function".
Skips (does not fail) if ml/ocr has no parser yet.
Results are written to ml/eval/results/ocr_parser_metrics.json and checked against QA.md thresholds
by test_parser_meets_thresholds (a real FAIL if the builder's parser is below threshold).
"""
import glob
import importlib.util
import json
import os

import pytest

import check_thresholds
import ocr_metrics
from conftest import EVAL_DIR, REPO_ROOT

FIX = os.path.join(EVAL_DIR, "fixtures", "receipts")
RESULTS = os.path.join(EVAL_DIR, "results")
NAMES = ("parse_receipt_text", "parse_receipt", "parse_text", "parse")


def _load_file(path):
    spec = importlib.util.spec_from_file_location("builder_" + os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_parser():
    env = os.environ.get("ML_PARSER")
    if env:
        path, fn = env.split(":")
        return getattr(_load_file(path), fn)
    import sys
    ocr_dir = os.path.join(REPO_ROOT, "ml", "ocr")
    if ocr_dir not in sys.path:
        sys.path.insert(0, ocr_dir)
    for path in sorted(glob.glob(os.path.join(ocr_dir, "*.py"))):
        if os.path.basename(path).startswith("test_"):
            continue
        try:
            mod = _load_file(path)
        except Exception:
            continue  # heavy deps (torch etc.) not installed here; try the next module
        for n in NAMES:
            if callable(getattr(mod, n, None)):
                return getattr(mod, n)
    return None


@pytest.fixture(scope="module")
def parser():
    p = find_parser()
    if p is None:
        pytest.skip("no receipt text parser found in ml/ocr yet")
    return p


def _norm(out):
    if isinstance(out, dict):
        return {"lines": out.get("lines") or out.get("items") or [], "total": out.get("total")}
    if isinstance(out, (tuple, list)) and len(out) == 2 and isinstance(out[0], list):
        return {"lines": out[0], "total": out[1]}
    raise AssertionError(f"unrecognised parser output type: {type(out)}")


HOLDOUT = os.path.join(EVAL_DIR, "fixtures", "receipts_holdout")
SETS = {"original": FIX, "holdout": HOLDOUT}


def receipts(d=FIX):
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(d, "*.txt")))


def test_fixture_count_meets_qa_minimum():
    assert len(receipts()) >= 20


def run_set(parser, name):
    d = SETS[name]
    gt, pred, crashes = {}, {}, {}
    for rid in receipts(d):
        gt[rid] = json.load(open(os.path.join(d, rid + ".json")))
        text = open(os.path.join(d, rid + ".txt")).read()
        try:
            pred[rid] = {"receipt": rid, **_norm(parser(text))}
        except Exception as e:  # a crash is a result, not a harness error
            crashes[rid] = repr(e)
            pred[rid] = {"receipt": rid, "lines": [], "total": None}
    res = ocr_metrics.evaluate(gt, pred)
    res["ocr"]["crashes"] = crashes
    os.makedirs(RESULTS, exist_ok=True)
    json.dump(res, open(os.path.join(RESULTS, f"ocr_parser_metrics_{name}.json"), "w"), indent=2)
    print(f"[{name}]"); ocr_metrics.print_report(res)
    return res


@pytest.fixture(scope="module", params=sorted(SETS))
def evaluation(request, parser):
    return run_set(parser, request.param)


def test_holdout_has_at_least_12_receipts():
    assert len(receipts(HOLDOUT)) >= 12


def test_parser_never_crashes(evaluation):
    assert evaluation["ocr"]["crashes"] == {}


def test_parser_meets_thresholds(evaluation):
    """Separate gate per set (original 24 / blind holdout 12). Holdout skips the >=20 sample-size rule."""
    ocr = dict(evaluation["ocr"])
    if ocr["n_receipts"] < 20:
        ocr["n_receipts"] = 20  # size rule applies to the QA set only; the holdout is a generalisation check
    results = check_thresholds.run_checks({"ocr": ocr}, skip=("det",))
    failing = [f"{n}: {d}" for n, s, d in results if s == "FAIL"]
    assert not failing, "; ".join(failing)


def test_parser_output_types(parser):
    for rid in receipts()[:5]:
        out = _norm(parser(open(os.path.join(FIX, rid + ".txt")).read()))
        for l in out["lines"]:
            assert isinstance(l["name"], str) and l["name"].strip()
            assert isinstance(l["quantity"], (int, float)) and l["quantity"] > 0
            assert l["price"] is None or isinstance(l["price"], (int, float))
        assert out["total"] is None or isinstance(out["total"], (int, float))


def test_parser_empty_and_garbage_input_do_not_crash(parser):
    for t in ("", "   \n\n", "!!! ??? ###", "TOTAL", "SUBTOTAL 5.00\nTAX 0.40"):
        out = _norm(parser(t))
        assert isinstance(out["lines"], list)
