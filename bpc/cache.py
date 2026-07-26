"""Tiny JSON disk cache with TTL.

Used to (a) cache trade2 reference data (data/stats, data/static) for a long time and
(b) cache price-search results briefly so re-running a build, or builds that share an
item, do not re-hit the rate-limited trade API.
"""
import hashlib
import json
import os
import sys
import time
from typing import Any, Callable, Optional


def _base_dir() -> str:
    # When packaged as a one-file .exe, __file__ lives in a temp dir that's wiped on
    # exit, so persist the cache in a stable per-user location instead.
    if getattr(sys, "frozen", False):
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(root, "PoE2BuildPriceChecker")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CACHE_DIR = os.path.join(_base_dir(), "cache")

_reads_enabled = True


def disable_reads() -> None:
    """Make get() always miss (forces a fresh fetch). Writes still happen, so the
    refreshed values are stored for next time. Used by the CLI --refresh flag."""
    global _reads_enabled
    _reads_enabled = False


def _key_to_path(key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h + ".json")


def get(key: str, ttl_seconds: float) -> Optional[Any]:
    """Return the cached value for `key` if present and younger than ttl, else None."""
    if not _reads_enabled:
        return None
    path = _key_to_path(key)
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(blob, dict):  # foreign/corrupt format -> treat as a miss
        return None
    if time.time() - blob.get("_ts", 0) > ttl_seconds:
        return None
    return blob.get("value")


def peek(key: str) -> Optional[Any]:
    """Read a cached value by key ignoring TTL and the read-disable flag. For explicit
    loads (e.g. re-opening a previously searched build) rather than freshness checks."""
    path = _key_to_path(key)
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return None
    return blob.get("value") if isinstance(blob, dict) else None


def put(key: str, value: Any) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _key_to_path(key)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"_ts": time.time(), "key": key, "value": value}, f)
    os.replace(tmp, path)


def cached(key: str, ttl_seconds: float, producer: Callable[[], Any]) -> Any:
    """Return cached value or compute, store and return it."""
    hit = get(key, ttl_seconds)
    if hit is not None:
        return hit
    value = producer()
    put(key, value)
    return value
