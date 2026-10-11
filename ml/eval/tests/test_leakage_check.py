"""Pooled-unit assertion of leakage_check.session_audit (ML-21): hand-built file trees, no images needed."""
import leakage_check as L

MS = 1_700_000_000_000  # epoch ms base


def tree(tmp_path, files):
    for sp in L.SPLITS:
        (tmp_path / "images" / sp).mkdir(parents=True)
    for sp, name in files:
        (tmp_path / "images" / sp / name).write_bytes(b"x")
    return tmp_path


def at(sec):
    return f"vegqual_{MS + int(sec * 1000)}_x.jpg"


def test_complete_small_session_far_from_train_passes(tmp_path):
    r = L.session_audit(tree(tmp_path, [("train", at(0)), ("train", at(60)), ("heldout", at(5000))]))
    assert r["_all_ok"] and r["vegqual"]["fragments"] == 0
    assert r["vegqual"]["heldout_small_sessions"] == 1 and r["vegqual"]["min_gap_to_trainval_s"] == 4940.0


def test_fragment_of_a_larger_session_fails(tmp_path):
    # train image 100 s before the held-out one: chained into the same session => held-out is a fragment
    r = L.session_audit(tree(tmp_path, [("train", at(0)), ("heldout", at(100))]))
    assert not r["_all_ok"] and r["vegqual"]["fragments"] == 1


def test_gap_just_over_300_s_passes_and_exactly_at_gap_chains(tmp_path):
    ok = L.session_audit(tree(tmp_path / "a", [("train", at(0)), ("heldout", at(301))]))
    assert ok["_all_ok"] and ok["vegqual"]["min_gap_to_trainval_s"] == 301.0   # > 300 s: separate sessions
    bad = L.session_audit(tree(tmp_path / "b", [("train", at(0)), ("heldout", at(300))]))
    assert not bad["_all_ok"]                                                   # <= 300 s chains into one session


def test_synthetic_copies_and_other_sources_are_ignored(tmp_path):
    r = L.session_audit(tree(tmp_path, [("train", "fridge_objects_" + at(0)[8:]), ("heldout", at(10)),
                                        ("train", at(10_000).replace(".jpg", "__low.jpg"))]))
    assert r["_all_ok"]
