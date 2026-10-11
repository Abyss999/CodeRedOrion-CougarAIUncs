"""Held-out leakage by PARENT image (ML-50): Roboflow exports carry their own rotations / flips / noise / crops of one
source photo ('rotated_by_15_X', 'vertical_flip_X', 'X-jpg_0_1234'). The identity pHash cannot see rotations, so this
check strips the augmentation prefix and the crop suffix and lists parents whose files sit in more than one split.

  python ml/eval/parent_sibling_check.py /path/to/fwr_data [source_prefix|all]

Exit code 1 if any held-out original has a train/val sibling of the same parent (use as a gate; `all` checks every
source in leakage_check.SOURCES that has held-out files).
"""
import os, re, sys, collections

AUG = re.compile(r"^(rotated_by_-?\d+|translation|(?:vertical|horizontal)_flip|saltandpepper|gaussian_noise|blur)_")


def parent(name: str, src: str) -> str:
    n = name[len(src) + 1:] if name.startswith(src + "_") else name
    n = re.sub(r"_(png|jpg|jpeg)_rf_.*$", "", n)
    n = re.sub(r"-(png|jpg|jpeg)_\d+_\d+$", "", n)
    n = re.sub(r"_(png|jpg|jpeg)$", "", n)
    return AUG.sub("", n)


def main(root, src):
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for sp in ("train", "val", "heldout"):
        for f in os.listdir(f"{root}/images/{sp}"):
            if f.startswith(src + "_") and "__low" not in f and "__warm" not in f:
                by[parent(f, src)][sp].append(f)
    bad = {p: {k: len(v) for k, v in d.items()} for p, d in by.items() if len(d) > 1}
    held = sum(d["heldout"].__len__() for d in by.values() if "heldout" in d)
    held_bad = sum(len(d["heldout"]) for p, d in by.items() if p in bad and "heldout" in d)
    for p, d in sorted(bad.items()):
        print(p, d)
    print(f"{src}: {len(bad)} parents straddle splits; {held_bad} of {held} held-out originals have a train/val sibling")
    return held_bad


if __name__ == "__main__":
    which = sys.argv[2] if len(sys.argv) > 2 else "food_spoilage_status"
    if which == "all":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from leakage_check import SOURCES
        sys.exit(1 if sum(main(sys.argv[1], s) for s in SOURCES) else 0)
    sys.exit(1 if main(sys.argv[1], which) else 0)
