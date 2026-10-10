import os
import sys

EVAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(EVAL_DIR))
for p in (EVAL_DIR,):
    if p not in sys.path:
        sys.path.insert(0, p)
