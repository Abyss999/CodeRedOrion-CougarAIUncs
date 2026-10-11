"""Per-user recipe suggestion cache (in-process, per gunicorn worker).

One entry per user: {key, stored_at, recipes}. `key` is a SHA-256 of the user's active items plus
the request options, so any add / edit / remove / restore changes the key and the next call misses.
Entries expire after `RECIPE_CACHE_TTL_SECONDS` (default 6 h; 0 disables the cache). Bounded LRU so
memory stays small. Hits and misses are logged on `app.recipes.cache` (no user data in the line).
"""
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict

from flask import current_app

DEFAULT_TTL_SECONDS = 6 * 60 * 60
MAX_USERS = 1000

log = logging.getLogger("app.recipes.cache")
if not log.handlers:  # same pattern as app.gemini.usage: visible in `docker compose logs api`
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False

_lock = threading.Lock()


def _store() -> OrderedDict:
    return current_app.extensions.setdefault("recipe_cache", OrderedDict())


def ttl_seconds() -> int:
    return int(current_app.config.get("RECIPE_CACHE_TTL_SECONDS", DEFAULT_TTL_SECONDS))


def make_key(items, max_results: int, dietary: list) -> str:
    """Hash of every active item (id, name, category, quantity, unit, expiry) + the options."""
    rows = sorted([str(i.id), i.name, i.category, str(i.quantity), i.unit,
                   i.predicted_expiry.isoformat()] for i in items)
    blob = json.dumps({"items": rows, "n": max_results, "dietary": sorted(dietary)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def get(user_id, key):
    ttl = ttl_seconds()
    if ttl <= 0:
        return None
    with _lock:
        store = _store()
        entry = store.get(user_id)
        if entry is None or entry["key"] != key:
            log.info("recipes_cache status=miss reason=%s", "empty" if entry is None else "items_changed")
            return None
        age = time.monotonic() - entry["stored_at"]
        if age > ttl:
            store.pop(user_id, None)
            log.info("recipes_cache status=miss reason=expired")
            return None
        store.move_to_end(user_id)
        log.info("recipes_cache status=hit age_s=%d", int(age))
        return entry["recipes"]


def put(user_id, key, recipes) -> None:
    if ttl_seconds() <= 0:
        return
    with _lock:
        store = _store()
        store[user_id] = {"key": key, "stored_at": time.monotonic(), "recipes": recipes}
        store.move_to_end(user_id)
        while len(store) > MAX_USERS:
            store.popitem(last=False)


def clear() -> None:
    with _lock:
        _store().clear()
