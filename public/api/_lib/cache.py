"""Best-effort TTL cache, serverless-safe.

Adapted from bpc/cache.py. Two layers:
  1. in-process dict (fast; survives WARM invocations on the same instance),
  2. best-effort JSON files under the system temp dir (survives across warm invocations
     sharing /tmp; write failures are swallowed -- the serverless FS is read-only except
     /tmp, and even /tmp is not guaranteed).

Cross-REQUEST caching for the public function is handled by the CDN (Cache-Control
s-maxage) and, later, a Workers-KV layer (B-001) -- not by this module. This just avoids
re-fetching within a process and never crashes on a read-only filesystem.
"""
import hashlib
import json
import os
import tempfile
import time
from typing import Any, Callable, Optional

CACHE_DIR = os.path.join(tempfile.gettempdir(), "bpc_public_cache")

_mem: dict = {}          # key -> (ts, value)
_reads_enabled = True


def disable_reads() -> None:
    global _reads_enabled
    _reads_enabled = False


def _key_to_path(key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h + ".json")


def get(key: str, ttl_seconds: float) -> Optional[Any]:
    if not _reads_enabled:
        return None
    hit = _mem.get(key)
    if hit is not None and time.time() - hit[0] <= ttl_seconds:
        return hit[1]
    path = _key_to_path(key)
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(blob, dict):
        return None
    if time.time() - blob.get("_ts", 0) > ttl_seconds:
        return None
    val = blob.get("value")
    _mem[key] = (blob.get("_ts", time.time()), val)
    return val


def peek(key: str) -> Optional[Any]:
    hit = _mem.get(key)
    if hit is not None:
        return hit[1]
    path = _key_to_path(key)
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return None
    return blob.get("value") if isinstance(blob, dict) else None


def put(key: str, value: Any) -> None:
    _mem[key] = (time.time(), value)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = _key_to_path(key)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"_ts": time.time(), "key": key, "value": value}, f)
        os.replace(tmp, path)
    except OSError:
        pass                                  # read-only FS: in-memory layer still holds it


def cached(key: str, ttl_seconds: float, producer: Callable[[], Any]) -> Any:
    hit = get(key, ttl_seconds)
    if hit is not None:
        return hit
    value = producer()
    put(key, value)
    return value
