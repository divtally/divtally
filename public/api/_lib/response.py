"""Shape (meta, results, pricer, league) into the ONE public JSON document.

Kept separate from the Vercel handler so the local test runner produces byte-identical
output. The per-item `price` object mirrors bpc/web.py `_result_dict` (chaos tier +
confidence/note/method/sample/total + merged `extra`); `trade_url` + `trade_query` are
promoted to the item top level because they are the primary deliverable for the
client-side extension. See docs/public-contract.md for the authoritative schema.
"""
import math
import time
from typing import List, Optional

from .currency import CurrencyConverter
from .models import CAT_RARE, CAT_UNIQUE, CAT_GEM, BuildMeta, PriceResult
from .querybuild import PublicPricer

SCHEMA_VERSION = "1.0"


def _finite(x):
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _chaos_tier(r: PriceResult) -> dict:
    return {"min": _finite(r.tier.minimum), "median": _finite(r.tier.median),
            "high": _finite(r.tier.high)}


def _divine_tier(chaos: dict, div_rate: Optional[float]) -> dict:
    if not div_rate:
        return {"min": None, "median": None, "high": None}
    out = {}
    for k in ("min", "median", "high"):
        v = chaos.get(k)
        out[k] = round(v / div_rate, 3) if isinstance(v, (int, float)) else None
    return out


def _price_obj(r: PriceResult, div_rate: Optional[float]) -> dict:
    chaos = _chaos_tier(r)
    price = {
        "chaos": chaos,
        "divine": _divine_tier(chaos, div_rate),
        "confidence": r.confidence, "note": r.note, "method": r.method,
        "source": (r.extra or {}).get("source", "none"),
        "sample_size": r.sample_size, "total_found": r.total_found,
    }
    # merge the category-specific extra (gem breakdown, unique variant info, ...) EXCEPT
    # trade_query (promoted to the item level) and host_* (already on the gem row).
    for k, v in (r.extra or {}).items():
        if k in ("trade_query", "source", "host_slot", "host_name", "host_base",
                 "host_unique", "host_inventory_id"):
            continue
        price[k] = v
    return price


def _item_row(i: int, r: PriceResult, div_rate: Optional[float]) -> dict:
    it = r.item
    row = {"index": i, "name": it.display_name, "group": it.group,
           "category": it.category, "slot": it.slot, "rarity": it.rarity,
           "count": it.count, "icon": it.icon}
    if int(getattr(it, "max_link", 0) or 0) > 0:
        row["max_link"] = it.max_link
        row["total_sockets"] = it.total_sockets
        row["socket_colours"] = it.socket_colours
    if it.category == CAT_GEM:
        row["level"] = it.gem_level
        row["quality"] = it.gem_quality
        row["corrupted"] = it.corrupted
        row["granted"] = bool(it.granted)
        row["supports"] = it.supports
        row["host_slot"] = it.host_slot
        row["host_name"] = it.host_name
        row["host_base"] = it.host_base
        row["host_unique"] = it.host_unique
        row["host_inventory_id"] = it.host_inventory_id
    else:
        from . import util
        mods = {"implicit": [util.strip_rich(m).strip() for m in (it.implicit_mods or [])],
                "explicit": [util.strip_rich(m).strip() for m in (it.explicit_mods or [])]}
        if any(mods.values()):
            row["mods"] = mods
    row["price"] = _price_obj(r, div_rate)
    row["trade_url"] = r.trade_url or ""
    row["trade_query"] = (r.extra or {}).get("trade_query")
    return row


def _sum_tier(results: List[PriceResult], key: str) -> Optional[float]:
    """Sum a tier across ninja-priced items (source == 'poe.ninja'). None if none priced."""
    total, any_v = 0.0, False
    for r in results:
        if (r.extra or {}).get("source") != "poe.ninja":
            continue
        v = getattr(r.tier, key)
        if isinstance(v, (int, float)) and math.isfinite(v):
            total += v
            any_v = True
    return total if any_v else None


def _priced_ninja(r: PriceResult) -> bool:
    """A row counts toward `priced_items` only if it is poe.ninja-sourced AND carries at least
    one finite chaos tier -- matching the contract's "items with a poe.ninja number". Excludes a
    granted-only gem group (source 'poe.ninja' but every tier null), which the totals already
    skip via `_sum_tier`."""
    if (r.extra or {}).get("source") != "poe.ninja":
        return False
    return any(isinstance(v, (int, float)) and math.isfinite(v)
               for v in (r.tier.minimum, r.tier.median, r.tier.high))


def build_response(meta: BuildMeta, results: List[PriceResult], pricer: PublicPricer,
                   trade_league: str, source_kind: str) -> dict:
    conv = CurrencyConverter(pricer.economy)
    try:
        div_rate = conv.divine_rate()
    except Exception:
        div_rate = None
    try:
        chaos_img = pricer.economy.currency_image("chaos")
        divine_img = pricer.economy.currency_image("divine")
    except Exception:
        chaos_img = divine_img = ""

    items = [_item_row(i, r, div_rate) for i, r in enumerate(results)]

    # affix-picker payload per rare/unique index (mirrors bpc/web.py rares_meta), so the
    # site/extension can offer manual refinement of the trade query.
    rares = {}
    for i, r in enumerate(results):
        it = r.item
        if it.category not in (CAT_RARE, CAT_UNIQUE):
            continue
        is_uni = it.category == CAT_UNIQUE
        spec = pricer.affix_options(it)
        if is_uni:
            scope = "unique: " + it.name
            scope_q = {"name": it.name, "type": it.base_type}
        else:
            btype = pricer.resolve_type(it.base_type)
            scope = ("base: " + btype) if btype else "category"
            sc = pricer._rare_scopes(it)
            scope_q = dict(sc[0][0]) if sc else {}
        rares[str(i)] = {
            "status": "priced" if (r.extra or {}).get("source") == "poe.ninja" else "unpriced",
            "name": it.display_name, "kind": "unique" if is_uni else "rare",
            "scope": scope, "scope_q": scope_q,
            "affixes": spec["affixes"], "pseudo": spec["pseudo"]}

    chaos_totals = {"min": _finite(_sum_tier(results, "minimum")),
                    "median": _finite(_sum_tier(results, "median")),
                    "high": _finite(_sum_tier(results, "high"))}
    priced_n = sum(1 for r in results if _priced_ninja(r))
    # "unpriced" = has a trade query to run but no server-side number (rares, uniques not on
    # ninja, magic). Normal/none items are neither priced nor trade-queryable.
    unpriced_n = sum(1 for r in results if (r.extra or {}).get("trade_query")
                     and (r.extra or {}).get("source") != "poe.ninja")

    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "character": meta.character, "account": meta.account,
            "class": meta.char_class, "level": meta.level,
            "league": trade_league,                     # the trade league used in URLs/queries
            "ninja_league": meta.league,                # poe.ninja league display name
            "source": source_kind,                      # "poe.ninja" | "pob"
            "source_url": getattr(meta, "source_url", "") or "",
            "pob_code": getattr(meta, "pob_export", "") or "",
            "cache_key": getattr(meta, "cache_key", "") or "",
            "currency_unit": "chaos",
            "divine_to_chaos": _finite(div_rate),
            "chaos_img": chaos_img, "divine_img": divine_img,
            "generated_at": int(time.time()),
            "pricing_note": ("Item prices are from the poe.ninja economy only (gems, "
                             "currency, uniques by name). Rare and unpriced items include a "
                             "prebuilt trade_url and the exact trade_query JSON for a "
                             "client-side extension to run on your own machine. This service "
                             "never calls pathofexile.com."),
        },
        "totals": {
            "currency": "chaos",
            "chaos": chaos_totals,
            "divine": _divine_tier(chaos_totals, div_rate),
            "priced_items": priced_n,
            "unpriced_items": unpriced_n,
            "note": "Totals sum poe.ninja-priced items only (gems + uniques). Rares are "
                    "excluded until priced client-side.",
        },
        "items": items,
        "rares": rares,
        "warnings": [],
    }
