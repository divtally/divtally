"""Bundled trade reference data (loaded from disk, NEVER fetched from pathofexile.com).

The query-building layer needs two pieces of GGG trade reference data:
  * `/api/trade/data/stats` -> the stat dictionary (mod text -> stat id) for StatMapper.
  * `/api/trade/data/items` -> base-type list per category for resolve_type / PoB parsing.

In the LOCAL app these come from live `TradeClient.static/stats/items` calls. The PUBLIC
function is forbidden to call pathofexile.com (D-0008 / B-001), so both are shipped as
SLIMMED static JSON in `api/_data/` and read here. They are cut to exactly the fields the
consumers read (StatMapper: group `label` + entries' `id`/`text`, and only the 9 groups it
stores from; load_item_types: `label` + entries' `type`) -- producing identical output to
the full live responses. Regenerate from `research/data/trade_stats.json` + `trade_items.json`
when a new league changes the stat dictionary (rare; the stat ids are stable across leagues).
"""
import json
import os
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
# _lib/ and _data/ are siblings under api/. Try a few roots so this works both in the
# Vercel bundle and from local test runners regardless of how the tree is laid out.
_CANDIDATE_DIRS = [
    os.path.join(os.path.dirname(_HERE), "_data"),   # api/_data  (normal layout)
    os.path.join(_HERE, "_data"),                    # _lib/_data (flattened bundle)
    os.path.join(_HERE, "..", "_data"),
]

_stats_cache: Optional[dict] = None
_items_cache: Optional[dict] = None


def _find(filename: str) -> str:
    for d in _CANDIDATE_DIRS:
        p = os.path.join(d, filename)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(
        f"bundled reference data {filename!r} not found under {_CANDIDATE_DIRS}. "
        "Ensure api/_data/*.json ships with the function (vercel.json includeFiles).")


def stats_data() -> dict:
    """The `/api/trade/data/stats`-shaped dict, from the bundled slim file."""
    global _stats_cache
    if _stats_cache is None:
        with open(_find("trade_stats.json"), encoding="utf-8") as f:
            _stats_cache = json.load(f)
    return _stats_cache


def _items_data() -> dict:
    global _items_cache
    if _items_cache is None:
        with open(_find("trade_items.json"), encoding="utf-8") as f:
            _items_cache = json.load(f)
    return _items_cache


def item_types() -> dict:
    """Trade base types grouped by category: {'all': set, 'by_group': {label: set}}.
    Mirrors bpc.pricing.load_item_types but reads the bundled file (no trade call)."""
    data = _items_data()
    by_group, allt = {}, set()
    for grp in data.get("result", []):
        s = set()
        for e in grp.get("entries", []):
            if e.get("type"):
                s.add(e["type"])
                allt.add(e["type"])
        by_group[grp.get("label", "")] = s
    return {"all": allt, "by_group": by_group}
