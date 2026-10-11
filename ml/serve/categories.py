"""Class-name -> backend category. Single source of truth is ml/yolo/taxonomy.py."""
import sys
from pathlib import Path

_ML = str(Path(__file__).resolve().parents[1])   # ml/  (in Docker: /app)
if _ML not in sys.path:
    sys.path.insert(0, _ML)
from yolo.taxonomy import CATEGORIES, CLASS_CATEGORY, CLASS_FOOD_GROUP, FOOD_GROUPS, FRESHNESS, SEMI_WORDS, SPOILED_WORDS, category_for, food_group_for  # noqa: E402,F401
