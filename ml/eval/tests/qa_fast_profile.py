"""ML QA (2026-10-11): Colab FAST profile (branch feat/fast-train).

Covers ml/yolo/cap_detector.py (capped detector train view), the notebook wiring (cells 1, 5, 6) and the
train.py speed flags (--cache, --no-epoch-val). Unit level only: tiny fixtures, no ultralytics, no training.
A real-data check runs only when the local rebuilt dataset exists (FWR_QA_DATA, default ../mldata/verify_main/fwr_data).

Run: python -m pytest ml/eval/tests/qa_fast_profile.py -q   (CI's ml/eval job collects test_*.py only)
"""
import filecmp
import json
import os
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
YOLO = REPO / "ml" / "yolo"
NB = YOLO / "train_colab.ipynb"
if str(YOLO) not in sys.path:
    sys.path.insert(0, str(YOLO))

import cap_detector as CD  # noqa: E402
from make_subset import make_subset  # noqa: E402
from taxonomy import FRESHNESS_CODE  # noqa: E402

_CAND = [REPO.parent / "mldata" / "verify_main" / "fwr_data", REPO.parent.parent / "mldata" / "verify_main" / "fwr_data"]
REAL = Path(os.environ.get("FWR_QA_DATA") or next((c for c in _CAND if c.is_dir()), _CAND[0]))   # repo or a worktree
FR = {"fresh": FRESHNESS_CODE["fresh"], "spoiled": FRESHNESS_CODE["spoiled"], "semi": FRESHNESS_CODE["semi_fresh"]}


# ----------------------------------------------------------------------------------------------------------- fixture
NAMES = {"0": "big", "1": "rare", "2": "rot", "3": "milk", "4": "egg"}
SOURCES = ["fresh", "fresh_stale_fruits_veg", "fridge_objects"]


def _img(root, sp, stem, labels, fresh, sidecar=True, label_file=True):
    Image.new("RGB", (8, 8), (len(stem) * 7 % 255, 0, 0)).save(root / "images" / sp / f"{stem}.jpg")
    if label_file:
        (root / "labels" / sp / f"{stem}.txt").write_text("".join(f"{c} .5 .5 .1 .1\n" for c in labels))
    if sidecar:
        (root / "freshness" / sp / f"{stem}.txt").write_text("".join(f"{f}\n" for f in fresh))


def build_fixture(root):
    """big: 40 single images (fresh/semi_fresh/spoiled, two sources); rot: 30 spoiled-only images (big, spoiled-only);
    rare: 3 images; 4 fridge multi-object images (milk+egg, 2 with rare); 2 background images (empty label, no label)."""
    for sp in ("train", "val", "heldout"):
        for sub in ("images", "labels", "freshness"):
            (root / sub / sp).mkdir(parents=True)
    for i in range(40):
        src = "fresh_stale_fruits_veg" if i % 2 else "fresh"
        _img(root, "train", f"{src}_big{i:02d}", [0], [(FR["fresh"], FR["spoiled"], FR["semi"])[i % 3]])
    for i in range(30):
        _img(root, "train", f"fresh_rot{i:02d}", [2], [FR["spoiled"]])
    for i in range(3):
        _img(root, "train", f"fresh_rare{i}", [1], [FR["fresh"]])
    for i in range(4):
        labels = [3, 3, 4] + ([1] if i < 2 else [])
        _img(root, "train", f"fridge_objects_m{i}", labels, [FR["fresh"]] * len(labels))
    for i in range(16):
        _img(root, "train", f"fridge_objects_milk{i:02d}", [3], [FR["fresh"]])
    _img(root, "train", "fresh_bg0", [], [])                            # empty label file = background
    _img(root, "train", "fresh_bg1", [], [], sidecar=False, label_file=False)   # no label at all = background
    for sp in ("val", "heldout"):
        for i in range(3):
            _img(root, sp, f"fresh_{sp}{i}", [i % 3], [FR["fresh"]])
    for sp in ("train", "val"):
        for fr in ("fresh", "semi_fresh", "spoiled"):
            d = root / "cls" / sp / fr
            d.mkdir(parents=True)
            for i in range(3):
                Image.new("RGB", (4, 4)).save(d / f"c{i}.jpg")
    (root / "class_names.json").write_text(json.dumps(NAMES))
    (root / "dataset_report.json").write_text(json.dumps({"source_by_split": {s: {} for s in SOURCES}}))
    (root / "data.yaml").write_text(f"path: {root}\ntrain: images/train\nval: images/val\ntest: images/heldout\nnames:\n"
                                    + "".join(f"  {k}: {v}\n" for k, v in NAMES.items()))
    (root / "heldout_gt.jsonl").write_text("".join(json.dumps({"image": f"images/heldout/fresh_heldout{i}.jpg"}) + "\n" for i in range(3)))
    (root / "heldout_manifest.csv").write_text("image,lighting\n" + "".join(f"images/heldout/fresh_heldout{i}.jpg,normal\n" for i in range(3)))
    return root


def same_tree(a, b):
    c = filecmp.dircmp(a, b)
    if c.left_only or c.right_only or c.funny_files:
        return False
    if filecmp.cmpfiles(a, b, c.common_files, shallow=False)[1:] != ([], []):
        return False
    return all(same_tree(os.path.join(a, d), os.path.join(b, d)) for d in c.common_dirs)


def train_boxes(data, stems):
    names = {str(k): v for k, v in json.loads((Path(data) / "class_names.json").read_text()).items()}
    return {s: (CD._boxes(Path(data), s, names) if (Path(data) / "labels" / "train" / f"{s}.txt").exists() else []) for s in stems}


def check_view(src, out, cap):
    """Integrity + cap invariants of a built view against its source. Returns (kept stems, per-food kept/total, overshoot)."""
    src, out = Path(src), Path(out)
    # 1. everything except the train split is the source, byte for byte
    for sub in ("images", "labels", "freshness"):
        for sp in ("val", "heldout"):
            if (src / sub / sp).exists():
                assert same_tree(src / sub / sp, out / sub / sp), f"{sub}/{sp} differs from the source"
    assert same_tree(src / "cls", out / "cls")
    for f in ("heldout_gt.jsonl", "heldout_manifest.csv", "class_names.json", "dataset_report.json"):
        assert (src / f).read_bytes() == (out / f).read_bytes(), f
    sy, oy = (src / "data.yaml").read_text().splitlines(), (out / "data.yaml").read_text().splitlines()
    assert [l for l in sy if not l.startswith("path:")] == [l for l in oy if not l.startswith("path:")]
    assert f"path: {out.resolve()}" in oy
    # 2. train: a subset of the source train split, each kept image with its own label + freshness sidecar
    full = {p.stem for p in (src / "images" / "train").iterdir() if p.is_file()}
    kept = {p.stem for p in (out / "images" / "train").iterdir()}
    assert kept <= full
    for s in kept:
        img = next((out / "images" / "train").glob(f"{s}.*"))
        assert img.resolve().parent == (src / "images" / "train").resolve()
        for sub in ("labels", "freshness"):
            o, i = out / sub / "train" / f"{s}.txt", src / sub / "train" / f"{s}.txt"
            assert o.exists() == i.exists(), (sub, s)
            if i.exists():
                assert o.read_bytes() == i.read_bytes()
        # Ultralytics img2label_paths: /images/ -> /labels/ on the (unresolved) image path
        lab = Path(str(img).replace(f"{os.sep}images{os.sep}", f"{os.sep}labels{os.sep}")).with_suffix(".txt")
        assert lab.exists() == (src / "labels" / "train" / f"{s}.txt").exists()
    for sub in ("labels", "freshness"):
        assert {p.stem for p in (out / sub / "train").iterdir()} <= kept, f"orphan {sub} in the view"
    # 3. cap semantics
    bx = train_boxes(src, full)
    total = Counter(f for b in bx.values() for f, _ in b)
    got = Counter(f for s in kept for f, _ in bx[s])
    for f, n in total.items():
        if n <= cap:
            assert got[f] == n, f"{f}: total {n} <= cap but only {got[f]} kept"
        else:
            assert got[f] >= cap, f"{f}: {got[f]} < cap {cap} although {n} available"
    for s in full - kept:                                   # maximality: a dropped image adds nothing under cap
        assert bx[s] and all(got[f] >= cap for f, _ in bx[s]), f"dropped {s} would have added a box to an under-cap food"
    for s in full:
        if not bx[s]:
            assert s in kept, "background image dropped"
    # overshoot over cap is only allowed from forced images (they hold a rare food), multi-food images (taken for
    # another food), or the last image that crossed the cap (an image with k boxes of f can overshoot by k - 1)
    forced = {s for s in kept if not bx[s] or any(total[f] <= cap for f, _ in bx[s])}
    over = {f: got[f] - cap for f in got if got[f] > cap}
    for f, o in over.items():
        n = lambda s: sum(g == f for g, _ in bx[s])  # noqa: E731
        explained = sum(n(s) for s in kept if s in forced or len({g for g, _ in bx[s]}) > 1)
        assert o <= explained + max(n(s) for s in kept) - 1, (f, o, explained)
    return kept, {f: (got[f], total[f]) for f in total}, over


# -------------------------------------------------------------------------------------------------- cap_detector
def test_view_integrity_and_cap_semantics(tmp_path):
    src = build_fixture(tmp_path / "d")
    r = CD.cap_detector(src, tmp_path / "o", cap=10)
    kept, per_food, over = check_view(src, tmp_path / "o", 10)
    assert per_food["rare"] == (5, 5) and per_food["egg"] == (4, 4)          # <= cap: all
    assert per_food["big"] == (10, 40) and per_food["rot"] == (10, 30)
    assert per_food["milk"][1] == 24 and per_food["milk"][0] >= 10
    assert r["train_images"] == len(kept) and r["train_images_full"] == 95
    assert {"fresh_bg0", "fresh_bg1"} <= kept
    assert all(f"fridge_objects_m{i}" in kept for i in range(4))              # rare / egg are forced keeps
    assert over.get("milk", 0) == per_food["milk"][0] - 10
    # the report's food counts equal what is on disk
    assert r["boxes_by_food"] == {f: f"{g}/{t}" for f, (g, t) in per_food.items()}


def test_freshness_codes_decoded(tmp_path):
    src = build_fixture(tmp_path / "d")
    names = {k: v for k, v in NAMES.items()}
    assert CD.CODE_TO_FRESHNESS == {"0": "fresh", "1": "spoiled", "2": "semi_fresh"}
    assert CD._boxes(src, "fresh_big02", names) == [("big", "semi_fresh")]     # code 2
    assert CD._boxes(src, "fresh_stale_fruits_veg_big01", names) == [("big", "spoiled")]
    assert CD._boxes(src, "fresh_rot00", names) == [("rot", "spoiled")]
    (src / "freshness" / "train" / "fresh_big00.txt").unlink()                  # no sidecar -> fresh
    assert CD._boxes(src, "fresh_big00", names) == [("big", "fresh")]
    r = CD.cap_detector(src, tmp_path / "o", cap=10)
    # rot is spoiled-only: its 10 kept boxes are all spoiled; big keeps all three freshness values
    kept = {p.stem for p in (tmp_path / "o" / "images" / "train").iterdir()}
    bx = train_boxes(src, kept)
    assert Counter(fr for s in kept for f, fr in bx[s] if f == "rot") == Counter({"spoiled": 10})
    assert set(fr for s in kept for f, fr in bx[s] if f == "big") == {"fresh", "semi_fresh", "spoiled"}
    assert sum(r["boxes_by_freshness"].values()) == sum(len(b) for b in bx.values())
    assert r["boxes_by_freshness"]["semi_fresh"] >= 3


def test_source_prefix_longest_match(tmp_path, monkeypatch):
    srcs = sorted(SOURCES, key=len, reverse=True)
    assert CD._source("fresh_stale_fruits_veg_big01", srcs) == "fresh_stale_fruits_veg"
    assert CD._source("fresh_big00", srcs) == "fresh"
    assert CD._source("nosuch_x", srcs) == "unknown"
    # and select() itself passes the longest-first order (spy on _source)
    src = build_fixture(tmp_path / "d")
    seen = {}
    real = CD._source
    monkeypatch.setattr(CD, "_source", lambda stem, sources: seen.setdefault(stem, real(stem, sources)))
    CD.select(src, 10)
    assert seen and all(v == "fresh_stale_fruits_veg" for k, v in seen.items() if k.startswith("fresh_stale_fruits_veg_"))
    assert seen["fresh_big00"] == "fresh"


def test_deterministic_and_path_independent(tmp_path):
    import shutil
    a = build_fixture(tmp_path / "d1")
    shutil.copytree(a, tmp_path / "elsewhere" / "d2")
    r1 = CD.cap_detector(a, tmp_path / "o1", cap=7)
    r2 = CD.cap_detector(a, tmp_path / "o2", cap=7)
    r3 = CD.cap_detector(tmp_path / "elsewhere" / "d2", tmp_path / "o3", cap=7)
    names = lambda o: sorted(p.name for p in (tmp_path / o / "images" / "train").iterdir())  # noqa: E731
    assert r1 == r2 == r3 and names("o1") == names("o2") == names("o3")
    assert CD.cap_detector(a, tmp_path / "o4", cap=10_000)["train_images"] == 95      # cap above every total: all kept


def test_rebuild_into_same_out_never_touches_source(tmp_path):
    src = build_fixture(tmp_path / "d")
    import hashlib
    def digest(root):
        h = hashlib.sha256()
        for p in sorted(Path(root).rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(root)).encode()); h.update(p.read_bytes())
        return h.hexdigest()
    before = digest(src)
    CD.cap_detector(src, tmp_path / "o", cap=10)
    (tmp_path / "o" / "labels" / "train.cache").write_text("ultralytics cache")    # what a training run leaves behind
    CD.cap_detector(src, tmp_path / "o", cap=10)                                    # cell 5 re-run on resume
    assert digest(src) == before
    assert not (tmp_path / "o" / "labels" / "train.cache").exists()
    check_view(src, tmp_path / "o", 10)


def test_make_subset_on_fast_view_is_a_valid_dry_run(tmp_path):
    src = build_fixture(tmp_path / "d")
    CD.cap_detector(src, tmp_path / "fast", cap=10)
    stats = make_subset(tmp_path / "fast", tmp_path / "dry", stride=4)
    dry = tmp_path / "dry"
    assert stats["train"] >= 1 and stats["val"] >= 1 and stats["heldout"] >= 1
    for sp in ("train", "val", "heldout"):
        imgs = list((dry / "images" / sp).iterdir())
        assert imgs and all(p.exists() for p in imgs)                        # symlink chains resolve
        for p in imgs:
            lab = dry / "labels" / sp / f"{p.stem}.txt"
            assert lab.exists() == (src / "labels" / sp / f"{p.stem}.txt").exists(), (sp, p.name)
    train = {p.stem for p in (dry / "images" / "train").iterdir()}
    assert train <= {p.stem for p in (tmp_path / "fast" / "images" / "train").iterdir()}   # subset of the CAPPED train
    for sp in ("train", "val"):
        assert sorted(os.listdir(dry / "cls" / sp)) == ["fresh", "semi_fresh", "spoiled"]
        assert all(os.listdir(dry / "cls" / sp / c) for c in os.listdir(dry / "cls" / sp))
    gt = [json.loads(l)["image"] for l in (dry / "heldout_gt.jsonl").read_text().splitlines()]
    assert gt and set(gt) == {f"images/heldout/{p.name}" for p in (dry / "images" / "heldout").iterdir()}
    assert f"path: {dry.resolve()}" in (dry / "data.yaml").read_text()


@pytest.mark.skipif(not (REAL / "images" / "train").is_dir(), reason="local rebuilt dataset not present")
def test_real_dataset_view(tmp_path):
    r = CD.cap_detector(REAL, tmp_path / "fast", cap=400)
    kept, per_food, over = check_view(REAL, tmp_path / "fast", 400)
    assert r["train_images"] == len(kept) and r["train_images_full"] == 11777
    assert all(min(400, t) <= g for g, t in per_food.values())
    assert set(r["boxes_by_freshness"]) == {"fresh", "semi_fresh", "spoiled"}
    print("kept", len(kept), "overshoot", over, "freshness", r["boxes_by_freshness"])


# -------------------------------------------------------------------------------------------------------- notebook
def code_cells():
    return ["".join(c["source"]) for c in json.loads(NB.read_text())["cells"] if c["cell_type"] == "code"]


def cell(prefix):
    hits = [s for s in code_cells() if s.lstrip().startswith(prefix)]
    assert len(hits) == 1, prefix
    return hits[0]


def py(src):
    return "\n".join("" if l.lstrip().startswith(("!", "%")) else l for l in src.splitlines())


def test_every_code_cell_parses_and_params_present():
    for i, s in enumerate(code_cells()):
        compile(py(s), f"cell{i}", "exec")
    c1, c5 = cell("# 1."), cell("# 5.")
    assert "FAST = True  #@param {type:\"boolean\"}" in c1
    assert "DET_CAP = 400  #@param {type:\"integer\"}" in c5
    assert "*PROFILE]" in c5


def test_cap_rep_does_not_clobber_cell4_rep():
    import ast
    assigned = {t.id for n in ast.walk(ast.parse(py(cell("# 5.")))) if isinstance(n, (ast.Assign, ast.AugAssign))
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    assert "rep" not in assigned and "cap_rep" in assigned
    for later in ("# 6.",):
        assert "rep[" not in cell(later) and "rep." not in cell(later)


@pytest.mark.parametrize("fast,dry", [(True, True), (True, False), (False, True), (False, False)])
def test_run_dir_suffixes_isolate_profiles(fast, dry):
    line = next(l for l in cell("# 1.").splitlines() if l.startswith("RUN_DIR ="))
    ns = {"CACHE_DIR": "/d/RUN/data_ab12cd34", "FAST": fast, "DRY_RUN": dry}
    exec(line, ns)
    assert ns["RUN_DIR"] == "/d/RUN/data_ab12cd34" + ("_fast" if fast else "") + ("_dry" if dry else "")


def test_run_dirs_all_distinct():
    line = next(l for l in cell("# 1.").splitlines() if l.startswith("RUN_DIR ="))
    out = set()
    for fast in (True, False):
        for dry in (True, False):
            ns = {"CACHE_DIR": "/c", "FAST": fast, "DRY_RUN": dry}
            exec(line, ns)
            out.add(ns["RUN_DIR"])
    assert len(out) == 4 and "/c" in out        # full real run keeps the pre-FAST folder (old checkpoints still resume)


STUB = """import json, os, sys
open(os.environ["ARGV_LOG"], "w").write(json.dumps(sys.argv[1:]))
"""


@pytest.mark.parametrize("fast,dry", [(True, True), (True, False), (False, True), (False, False)])
def test_cell5_profile_reaches_train_py(tmp_path, monkeypatch, fast, dry):
    work = tmp_path / "yolo"; work.mkdir()
    (work / "train.py").write_text(STUB)
    run_dir = tmp_path / "run"; run_dir.mkdir()
    log = tmp_path / "argv.json"
    monkeypatch.setenv("ARGV_LOG", str(log)); monkeypatch.chdir(work)
    caps, subs = [], []
    monkeypatch.setitem(sys.modules, "cap_detector", types.SimpleNamespace(
        cap_detector=lambda *a, **k: caps.append((a, k)) or {"train_images": 1, "train_images_full": 2, "boxes_by_freshness": {}}))
    monkeypatch.setitem(sys.modules, "make_subset", types.SimpleNamespace(make_subset=lambda *a, **k: subs.append((a, k)) or {}))
    import shutil
    sentinel = {"cell4": "report"}
    ns = {"os": os, "shutil": shutil, "subprocess": subprocess, "sys": sys, "RUN_DIR": str(run_dir),
          "DRY_RUN": dry, "FAST": fast, "rep": sentinel}
    exec(compile(cell("# 5."), "cell5", "exec"), ns)
    argv = json.loads(log.read_text())
    assert ns["rep"] is sentinel
    assert bool(caps) == fast
    if fast:
        assert caps == [(("/content/fwr_data", "/content/fwr_data_fast"), {"cap": 400})]
    data = "/content/fwr_data_fast" if fast else "/content/fwr_data"
    if dry:
        assert subs == [((data, "/content/fwr_data_dry"), {"stride": 20})]
    else:
        assert not subs
    i = argv.index("--data")
    assert argv[i + 1] == ("/content/fwr_data_dry" if dry else data)
    ep, cls_ep = argv[argv.index("--epochs") + 1], argv[argv.index("--cls-epochs") + 1]
    assert (ep, cls_ep) == (("1", "1") if dry else (("30", "10") if fast else ("80", "30")))
    assert argv[argv.index("--project") + 1] == str(run_dir) and "--resume" in argv
    prof = ["--det-model", "yolo26n.pt", "--imgsz", "512", "--batch", "32", "--cls-batch", "128", "--cache", "ram", "--no-epoch-val"]
    if fast:
        assert argv[-len(prof):] == prof
    else:
        assert not set(prof) & set(argv) - {"--batch"} and "--cache" not in argv and "--det-model" not in argv


def test_cell6_messages():
    c6 = cell("# 6.")
    assert "~30 min with FAST, ~4-5 h without" in c6
    assert 'm.val(data="/content/fwr_data/data.yaml", split="test")' in c6          # full held-out, not the view


# ------------------------------------------------------------------------------------------------------- train.py
class _FakeYOLO:
    calls = []

    def __init__(self, path):
        self.path = path
        self.trainer = types.SimpleNamespace(last="L", best="B")

    def train(self, **kw):
        _FakeYOLO.calls.append((self.path, kw))

    def val(self, **kw):
        return types.SimpleNamespace(box=types.SimpleNamespace(map50=0.0))


@pytest.fixture
def fake_ultra(monkeypatch, tmp_path):
    _FakeYOLO.calls = []
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=_FakeYOLO))
    monkeypatch.setitem(sys.modules, "export_predictions", types.SimpleNamespace(main=lambda argv: None))
    import train
    monkeypatch.setattr(train, "pick_device", lambda d: "cpu")
    return train


def _main(train, tmp_path, monkeypatch, *extra):
    data = build_fixture(tmp_path / "d")
    stages = []
    def ts(name, model, project, resume, device, **kw):
        stages.append((name, model, kw))
        p = tmp_path / f"{name}.pt"; p.write_text("x")
        return p, p, "fresh"
    monkeypatch.setattr(train, "train_stage", ts)
    train.main(["--data", str(data), "--project", str(tmp_path / "proj"), *extra])
    return stages


@pytest.mark.parametrize("extra,cache,val", [
    ((), False, True),
    (("--cache", "ram", "--no-epoch-val"), "ram", False),
    (("--cache", "disk"), "disk", True),
    (("--cache", "none", "--no-epoch-val"), False, False),
])
def test_speed_kwargs_reach_both_stages(fake_ultra, tmp_path, monkeypatch, extra, cache, val):
    """--cache is for the DETECTOR only; the classifier never caches, for every --cache value (ML-69: Ultralytics'
    ClassificationDataset.cache_images decodes crops at full resolution, 9.4 GB for 14k crops, OOM on Colab).
    --no-epoch-val still reaches both stages."""
    stages = _main(fake_ultra, tmp_path, monkeypatch, *extra)
    assert [s[0] for s in stages] == ["det", "cls"]
    (_, _, det), (_, _, cls) = stages
    assert det["cache"] == cache and det["val"] is val
    assert cls["cache"] is False and cls["val"] is val


def test_fast_profile_flags_parse(fake_ultra, tmp_path, monkeypatch):
    prof = ["--det-model", "yolo26n.pt", "--imgsz", "512", "--batch", "32", "--cls-batch", "128", "--cache", "ram", "--no-epoch-val"]
    stages = _main(fake_ultra, tmp_path, monkeypatch, "--epochs", "30", "--cls-epochs", "10", "--resume", *prof)
    (n1, m1, k1), (n2, m2, k2) = stages
    assert m1 == "yolo26n.pt" and k1["imgsz"] == 512 and k1["batch"] == 32 and k1["epochs"] == 30
    assert k2["imgsz"] == 224 and k2["batch"] == 128 and k2["epochs"] == 10


def test_bad_cache_value_rejected(fake_ultra):
    with pytest.raises(SystemExit):
        fake_ultra.main(["--data", "x", "--cache", "true"])


# Ultralytics 8.4.175 engine/trainer.py check_resume (L1039-1062): keys a resume may override, and keys it never
# reports as ignored. Anything else passed on resume is silently replaced by the checkpoint value (with a warning).
UL_RESUME_ALLOWED = {"imgsz", "batch", "device", "close_mosaic", "augmentations", "save_period", "workers", "cache",
                     "patience", "time", "freeze", "val", "plots", "channels_last", "distill_model", "save_dir"}
UL_RESUME_EXEMPT = {"model", "data", "mode", "resume", "pretrained"}


def _ul_allowed_from_source():
    """The real allowed set, if an ultralytics install is around (e.g. ../mldata/.venv-train); else None."""
    import glob, re
    tail = Path("lib") / "python3*" / "site-packages" / "ultralytics" / "engine" / "trainer.py"
    roots = (REPO.parent / "mldata", REPO.parent.parent / "mldata")
    for f in sorted({f for r in roots for pat in ("*", ".*") for f in glob.glob(str(r / pat / tail))}):   # venvs are dot-dirs
        m = re.search(r"allowed = \{[^}]*\}", Path(f).read_text())
        if m:
            return set(re.findall(r'"(\w+)"', m.group(0)))
    return None


def test_pinned_allowed_set_matches_installed_ultralytics():
    real = _ul_allowed_from_source()
    if real is None:
        pytest.skip("no local ultralytics install to read")
    assert real == UL_RESUME_ALLOWED


@pytest.mark.parametrize("cache,val", [("ram", False), ("disk", True), (False, True), (False, False)])
def test_resume_branch_overrides_cache_and_val(fake_ultra, tmp_path, monkeypatch, cache, val):
    """ML-69: resume passes cache/val so a checkpoint saved with cache=ram can't bring the RAM cache back; every key it
    passes is one Ultralytics' check_resume accepts (allowed or exempt), so none is silently ignored."""
    train = fake_ultra
    w = tmp_path / "proj" / "det" / "weights"; w.mkdir(parents=True); (w / "last.pt").write_text("x")
    monkeypatch.setattr(train, "ckpt_status", lambda p: ("partial", 3, 30))
    kw = dict(data="d.yaml", epochs=30, imgsz=512, batch=32, cache=cache, val=val)
    last, best, how = train.train_stage("det", "yolo26n.pt", str(tmp_path / "proj"), True, "cpu", **kw)
    assert how == "resumed"
    (path, call), = _FakeYOLO.calls
    assert path == str(w / "last.pt")
    assert call == {"resume": True, "data": "d.yaml", "device": "cpu", "batch": 32, "imgsz": 512, "cache": cache, "val": val}
    assert set(call) <= UL_RESUME_ALLOWED | UL_RESUME_EXEMPT
    assert "epochs" not in call                                   # epochs come from the checkpoint (not overridable)


def test_resume_branch_defaults_without_speed_kwargs(fake_ultra, tmp_path, monkeypatch):
    """A caller that passes no cache/val (pre-FAST signature) resumes with no cache and per-epoch val."""
    train = fake_ultra
    (tmp_path / "proj" / "cls" / "weights").mkdir(parents=True)
    monkeypatch.setattr(train, "ckpt_status", lambda p: ("partial", 1, 10))
    train.train_stage("cls", "m", str(tmp_path / "proj"), True, "cpu", data="cls", epochs=10, imgsz=224, batch=128)
    (_, call), = _FakeYOLO.calls
    assert call["cache"] is False and call["val"] is True


def test_resumed_classifier_never_gets_ram_cache_end_to_end(fake_ultra, tmp_path, monkeypatch):
    """main() --resume --cache ram with both stages mid-training: the detector resumes with cache=ram, the classifier
    with cache=False (its checkpoint from the OOM'd run says cache=ram; the override must win)."""
    train = fake_ultra
    data = build_fixture(tmp_path / "d")
    for st in ("det", "cls"):
        (tmp_path / "proj" / st / "weights").mkdir(parents=True)
    monkeypatch.setattr(train, "ckpt_status", lambda p: ("partial", 2, 30))
    monkeypatch.chdir(tmp_path)                                   # _FakeYOLO.trainer.last/best are "L"/"B"
    (tmp_path / "L").write_text("pt"); (tmp_path / "B").write_text("pt")
    train.main(["--data", str(data), "--project", str(tmp_path / "proj"), "--resume", "--cache", "ram", "--no-epoch-val",
                "--epochs", "30", "--cls-epochs", "10"])
    resumes = [(p, c) for p, c in _FakeYOLO.calls if c.get("resume")]
    assert len(resumes) == 2
    (dp, det), (cp, cls) = resumes
    assert "/det/" in dp and det["cache"] == "ram" and det["val"] is False
    assert "/cls/" in cp and cls["cache"] is False and cls["val"] is False and cls["imgsz"] == 224


def test_resume_branch_skip_and_fresh_paths(fake_ultra, tmp_path, monkeypatch):
    train = fake_ultra
    kw = dict(data="d.yaml", epochs=30, imgsz=512, batch=32, cache="ram", val=False)
    # done checkpoint: skipped, extra kwargs harmless
    _FakeYOLO.calls = []
    monkeypatch.setattr(train, "ckpt_status", lambda p: ("done", -1, 30))
    assert train.train_stage("det", "m", str(tmp_path / "proj"), True, "cpu", **kw)[2] == "skipped" and not _FakeYOLO.calls
    # fresh: speed kwargs go to YOLO.train
    monkeypatch.setattr(train, "ckpt_status", lambda p: ("none", None, None))
    train.train_stage("det", "m", str(tmp_path / "proj"), True, "cpu", **kw)
    (_, call), = _FakeYOLO.calls
    assert call["cache"] == "ram" and call["val"] is False and call["imgsz"] == 512
