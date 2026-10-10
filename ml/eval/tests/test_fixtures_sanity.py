import glob, json, os
from conftest import EVAL_DIR

FIX = os.path.join(EVAL_DIR, "fixtures", "receipts")

def test_every_receipt_text_has_ground_truth_and_balances():
    txts = sorted(glob.glob(os.path.join(FIX, "*.txt")))
    assert len(txts) >= 20
    for t in txts:
        j = json.load(open(t[:-4] + ".json"))
        assert j["receipt"] == os.path.basename(t)[:-4]
        assert j["lines"] and j["total"] > 0
        text = open(t).read()
        assert ("%.2f" % j["total"]) in text or ("%.2f" % j["total"]).replace(".", ",") in text, t
        for l in j["lines"]:
            assert l["quantity"] > 0 and l["price"] is not None
