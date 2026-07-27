"""Trade-free pricing for the PUBLIC serverless function.

This is the query-building slice of bpc/pricing.py (the parts that construct trade queries
and clickable trade URLs WITHOUT running a search) plus the poe.ninja pricing paths
(gems + uniques-by-name), assembled into one `PublicPricer`. It NEVER calls
pathofexile.com.

What it produces per item:
  * gems      -> priced from poe.ninja SkillGem economy (active + supports); trade_query
                 for the active gem attached for extension refinement.
  * uniques   -> priced BY NAME from poe.ninja unique overviews (best-effort for variants);
                 ALSO carries the exact trade_query (name+base+links+skill-level rolls) so
                 the extension can verify / refine on the user's machine.
  * rares     -> NOT priced here (no honest poe.ninja source). Carries the exact default
                 trade_query (require every searchable affix + defence totals + links) and
                 its clickable trade_url, for the extension to execute client-side.
  * magic     -> NOT priced (cheap); carries a base-type trade_query + trade_url.

The pure query-construction methods are ported verbatim from bpc/pricing.py, with
`self.client.league` -> `self.league` (there is no TradeClient). Trade-search methods
(`_search_listings`, `price_unique`, `price_rare`, `price_magic`, ...) are intentionally
NOT ported -- they would call the trade API.
"""
import json
import urllib.parse
from typing import Dict, List, Optional, Tuple

from . import util
from .models import (CAT_GEM, CAT_MAGIC, CAT_RARE, CAT_UNIQUE, Item,
                     PriceResult, PriceTier)
from .statmap import StatMapper, is_local_defence, _score

# ---- module-level constants / helpers (VERBATIM from bpc/pricing.py) -------------------
_ARMOUR_INV = {"Helm", "BodyArmour", "Gloves", "Boots", "Offhand"}

_PSEUDO_ELEM_RES = "pseudo.pseudo_total_elemental_resistance"
_PSEUDO_CHAOS_RES = "pseudo.pseudo_total_chaos_resistance"

# itemData.inventoryId -> trade category option (fallback when base type is unknown).
_INVENTORY_CATEGORY = {
    "Helm": "armour.helmet", "BodyArmour": "armour.chest", "Gloves": "armour.gloves",
    "Boots": "armour.boots", "Belt": "accessory.belt", "Amulet": "accessory.amulet",
    "Ring": "accessory.ring", "Ring2": "accessory.ring", "Offhand": "armour.shield",
    "Offhand2": "armour.shield", "Weapon": "weapon", "Weapon2": "weapon",
    "Jewel": "jewel", "PassiveJewels": "jewel", "Flask": "flask",
}

_DEF_LABEL = {"es": "Total Energy Shield", "ev": "Total Evasion Rating",
              "ar": "Total Armour", "ward": "Total Ward"}

_GROUP_TYPES = {"and", "not", "if", "count", "weight", "weight2"}
_WEIGHT_TYPES = {"weight", "weight2"}


def _is_res_affix(text: str) -> bool:
    t = util.strip_rich(text).lower()
    if "resist" not in t:
        return False
    return not ("maximum" in t or "penetrat" in t or "enemy" in t)


def _is_skill_level_mod(text: str) -> bool:
    t = util.strip_rich(text).lower()
    return "to level of all" in t and "skill" in t


def _affix_tier(line: str, ok: bool, is_unique: bool) -> str:
    if not ok:
        return "skip"
    if is_unique:
        return "required" if _is_skill_level_mod(line) else "skip"
    sc = _score(util.mod_to_pattern(line))
    if sc >= 70:
        return "required"
    if sc >= 40:
        return "nice"
    return "notimp"


def res_contributions(mods: List[str]) -> dict:
    import re
    fire = cold = light = all_elem = chaos = all_res = 0.0
    for line in mods:
        if not _is_res_affix(line):
            continue
        t = util.strip_rich(line).lower()
        v = util.first_number(line)
        if v is None:
            continue
        if "all elemental resist" in t:
            all_elem += v
        elif re.search(r"\ball resistances?\b", t) and "elemental" not in t:
            all_res += v
        else:
            if "fire" in t:
                fire += v
            if "cold" in t:
                cold += v
            if "lightning" in t:
                light += v
            if "chaos" in t:
                chaos += v
    fire_t, cold_t, light_t = (fire + all_elem + all_res, cold + all_elem + all_res,
                               light + all_elem + all_res)
    chaos_t = chaos + all_res
    return {"fire": fire_t, "cold": cold_t, "lightning": light_t, "chaos": chaos_t,
            "elemental": fire_t + cold_t + light_t}


def _build_stat_groups(groups: List[dict]) -> List[dict]:
    """Convert a picker group payload into trade query.stats group objects (VERBATIM)."""
    out: List[dict] = []
    for g in groups or []:
        gtype = g.get("type", "and")
        if gtype not in _GROUP_TYPES:
            gtype = "and"
        coerced_weight = gtype in _WEIGHT_TYPES
        if coerced_weight:
            gtype = "count"
        is_weight = False
        filters = []
        by_id: Dict[str, dict] = {}
        for f in g.get("filters", []):
            sid = f.get("stat_id") or f.get("id")
            if not sid:
                continue
            val = {}
            if f.get("min") is not None:
                val["min"] = f["min"]
            if f.get("max") is not None:
                val["max"] = f["max"]
            if is_weight and f.get("weight") is not None:
                val["weight"] = f["weight"]
            if f.get("option") is not None:
                val["option"] = f["option"]
            if sid in by_id:
                prev = by_id[sid].setdefault("value", {})
                if "min" in val:
                    prev["min"] = max(prev.get("min", val["min"]), val["min"])
                if "max" in val:
                    prev["max"] = min(prev.get("max", val["max"]), val["max"])
                if "weight" in val:
                    prev["weight"] = max(prev.get("weight", val["weight"]), val["weight"])
                if "option" in val:
                    prev["option"] = val["option"]
                if not prev:
                    by_id[sid].pop("value", None)
                continue
            ff = {"id": sid}
            if val:
                ff["value"] = val
            by_id[sid] = ff
            filters.append(ff)
        if not filters:
            continue
        grp = {"type": gtype, "filters": filters}
        gval = {}
        if g.get("min") is not None:
            gval["min"] = g["min"]
        if g.get("max") is not None:
            gval["max"] = g["max"]
        n = len(filters)
        if gtype == "count":
            mn = gval.get("min")
            if coerced_weight:
                mn = max(1, (n + 1) // 2)
                gval.pop("max", None)
            gval["min"] = n if mn is None else max(1, min(int(mn), n))
            if gval.get("max") is not None:
                gval["max"] = max(gval["min"], min(int(gval["max"]), n))
        if gval:
            grp["value"] = gval
        out.append(grp)
    return out


class PublicPricer:
    """Query-builder + poe.ninja pricer. No TradeClient, no trade calls."""

    STATUS_OPTIONS = ("online", "any", "onlineleague", "available", "securable")

    def __init__(self, league: str, economy, mapper: StatMapper,
                 valid_types: set, status: str = "online"):
        self.league = league or "Standard"
        self.economy = economy                        # poeninja.PoeNinjaEconomy
        self.mapper = mapper                           # statmap.StatMapper (bundled stats)
        self._valid_types = valid_types or set()
        self.status = status if status in self.STATUS_OPTIONS else "online"

    # ---- small helpers (ported; league is now a plain string) ------------
    def _status(self) -> dict:
        return {"option": self.status}

    def _econ(self):
        return self.economy

    def resolve_type(self, base: str) -> Optional[str]:
        if not base:
            return None
        if not self._valid_types or base in self._valid_types:
            return base
        words = base.split()
        for start in range(1, len(words)):
            cand = " ".join(words[start:])
            if cand in self._valid_types:
                return cand
        return None

    def _links_filter(self, item: Item) -> dict:
        ml = int(getattr(item, "max_link", 0) or 0)
        if ml >= 5:
            return {"socket_filters": {"filters": {"links": {"min": ml}}}}
        return {}

    @staticmethod
    def _payload(query: dict) -> dict:
        """The exact body an extension POSTs to /api/trade/search/<league>."""
        return {"query": query, "sort": {"price": "asc"}}

    def _q_url(self, query: dict) -> str:
        """A clickable trade URL that pre-fills the EXACT query via ?q= (built locally)."""
        if not query:
            return ""
        try:
            q = urllib.parse.quote(json.dumps(self._payload(query), separators=(",", ":")),
                                   safe="")
            return (f"https://www.pathofexile.com/trade/search/"
                    f"{urllib.parse.quote(self.league)}?q={q}")
        except Exception:
            return ""

    # ---- rare scopes / affixes (VERBATIM logic) --------------------------
    def _rare_scopes(self, item: Item) -> List[Tuple[dict, str]]:
        scopes: List[Tuple[dict, str]] = []
        btype = self.resolve_type(item.base_type)
        if btype:
            scopes.append(({"type": btype}, "base"))
        cat = _INVENTORY_CATEGORY.get(item.raw.get("inventoryId", ""))
        if cat:
            scopes.append(({"filters": {"type_filters": {"filters":
                           {"category": {"option": cat}}}}}, "category"))
        return scopes

    def affix_options(self, item: Item) -> dict:
        is_armour = bool(item.defences) or item.raw.get("inventoryId", "") in _ARMOUR_INV
        is_unique = item.category == CAT_UNIQUE
        affixes = []
        for i, line in enumerate(item.explicit_mods):
            if is_armour and is_local_defence(line):
                continue
            src = item.mod_src[i] if i < len(item.mod_src) else None
            grp = "enchant" if src == "enchant" else None
            sid, neg = self.mapper.match(line, group=grp)
            ok = bool(sid)
            v = util.first_number(line)
            if ok and neg and v is not None:
                v = -abs(v)
            prefer = ok and ((not is_unique) or _is_skill_level_mod(line))
            label = util.strip_rich(line).strip()
            if src == "enchant":
                label += " (enchant)"
            affixes.append({
                "kind": "stat", "text": label,
                "stat_id": sid if ok else None, "value": v,
                "searchable": ok, "resist": _is_res_affix(line), "negated": bool(ok and neg),
                "prefer": prefer, "priority": _affix_tier(line, ok, is_unique),
                "reason": "" if ok else "no trade filter matches this mod",
            })
        for key, val in item.defences.items():
            if val and val > 0:
                affixes.append({"kind": "equip", "key": key, "stat_id": None,
                                "text": _DEF_LABEL.get(key, key), "value": int(val),
                                "searchable": True, "resist": False, "prefer": not is_unique,
                                "priority": "skip" if is_unique else "required", "reason": ""})
        c = res_contributions(item.explicit_mods)
        pseudo = []
        if c["elemental"] > 0:
            pseudo.append({"kind": "stat", "text": "+#% total Elemental Resistance",
                           "stat_id": _PSEUDO_ELEM_RES, "value": round(c["elemental"]),
                           "searchable": True, "resist": True, "prefer": not is_unique,
                           "priority": "skip" if is_unique else "required", "reason": ""})
        if c["chaos"] > 0:
            pseudo.append({"kind": "stat", "text": "+#% total to Chaos Resistance",
                           "stat_id": _PSEUDO_CHAOS_RES, "value": round(c["chaos"]),
                           "searchable": True, "resist": True, "prefer": not is_unique,
                           "priority": "skip" if is_unique else "required", "reason": ""})
        return {"affixes": affixes, "pseudo": pseudo}

    def _rare_query(self, item: Item, scope: dict, stat_groups: List[dict],
                    equip_filters: dict) -> dict:
        query = dict(scope)
        query["status"] = self._status()
        query["stats"] = stat_groups or [{"type": "and", "filters": []}]
        filt = dict(query.get("filters", {}))
        if equip_filters:
            filt["armour_filters"] = {"filters": equip_filters}
        filt.update(self._links_filter(item))
        if filt:
            query["filters"] = filt
        return query

    def _rare_default_filters(self, item: Item) -> Tuple[List[dict], dict, int]:
        opts = self.affix_options(item)["affixes"]
        stat_opts = [o for o in opts if o["kind"] == "stat" and o["searchable"]]
        equip_opts = [o for o in opts if o["kind"] == "equip" and o["value"]]

        def _statf(o):
            f = {"id": o["stat_id"]}
            if o.get("negated") and o.get("value") is not None:
                f["value"] = {"max": int(o["value"])}
            return f
        stat_filters = [_statf(o) for o in stat_opts]
        equip_filters = {o["key"]: {"min": int(o["value"] * 0.85)} for o in equip_opts}
        n_skip = sum(1 for o in opts if o["kind"] == "stat" and not o["searchable"])
        stat_groups = [{"type": "and", "filters": stat_filters}] if stat_filters else []
        return stat_groups, equip_filters, n_skip

    def _unique_value_filters(self, item: Item) -> List[dict]:
        out, seen = [], set()
        for mod in item.explicit_mods:
            if not _is_skill_level_mod(mod):
                continue
            sid, neg = self.mapper.match(mod)
            v = util.first_number(mod)
            if sid and v is not None and not neg and sid not in seen:
                seen.add(sid)
                out.append({"id": sid, "value": {"min": int(v)}})
        return out

    # ---- trade query builders (built, never executed) --------------------
    def _unique_query(self, item: Item) -> dict:
        """Name + base (+ links) (+ build's skill-level rolls) -- the query the extension
        runs to price/verify this unique on the user's machine."""
        vfilters = self._unique_value_filters(item)
        query = {"status": self._status(), "name": item.name, "type": item.base_type,
                 "stats": [{"type": "and", "filters": vfilters}]}
        links = self._links_filter(item)
        if links:
            query["filters"] = dict(links)
        return query

    def _rare_query_default(self, item: Item) -> Optional[dict]:
        scopes = self._rare_scopes(item)
        if not scopes:
            return None
        stat_groups, equip_filters, _ = self._rare_default_filters(item)
        return self._rare_query(item, scopes[0][0], stat_groups, equip_filters)

    def _magic_query(self, item: Item) -> Optional[dict]:
        btype = self.resolve_type(item.base_type)
        if not btype:
            return None
        return {"status": self._status(), "type": btype,
                "stats": [{"type": "and", "filters": []}]}

    def _gem_query(self, name, *, support: bool = False, level=None,
                   quality=None, corrupted: bool = False) -> dict:
        cat = "gem.supportgem" if support else "gem.activegem"
        filters = {"type_filters": {"filters": {"category": {"option": cat}}}}
        misc = {}
        if level:
            misc["gem_level"] = {"min": int(level)}
        if quality:
            misc["quality"] = {"min": int(quality)}
        if corrupted:
            misc["corrupted"] = {"option": "true"}
        if misc:
            filters["misc_filters"] = {"filters": misc}
        return {"status": self._status(), "type": name, "filters": filters,
                "stats": [{"type": "and", "filters": []}]}

    def _gem_search_url(self, name, *, support: bool = False, level=None,
                        quality=None, corrupted: bool = False) -> str:
        if not name:
            return ""
        return self._q_url(self._gem_query(name, support=support, level=level,
                                           quality=quality, corrupted=corrupted))

    @staticmethod
    def _confidence_from_lc(lc: int) -> str:
        return "high" if lc >= 5 else ("medium" if lc >= 2 else "low")

    def _attach_query(self, r: PriceResult, query: Optional[dict]) -> None:
        """Set both the clickable trade_url and the raw trade_query payload from one query."""
        if not query:
            return
        r.trade_url = self._q_url(query)
        r.extra["trade_query"] = self._payload(query)

    # ---- gem pricing (poe.ninja; VERBATIM logic from bpc.pricing.price_skill) ----
    def price_skill(self, item: Item) -> PriceResult:
        econ = self._econ()
        r = PriceResult(item=item, method="skill")
        name = item.base_type or item.type_line
        active_granted = bool(getattr(item, "granted", False))
        r.trade_url = self._gem_search_url(name, support=bool(item.support),
                                           level=item.gem_level, quality=item.gem_quality,
                                           corrupted=bool(item.corrupted))
        host_extra = {
            "granted": active_granted,
            "host_slot": getattr(item, "host_slot", "") or "",
            "host_name": getattr(item, "host_name", "") or "",
            "host_base": getattr(item, "host_base", "") or "",
            "host_unique": bool(getattr(item, "host_unique", False)),
            "host_inventory_id": getattr(item, "host_inventory_id", "") or "",
        }
        # the active gem's trade search payload (for extension refinement / verification)
        active_query = self._gem_query(name, support=bool(item.support), level=item.gem_level,
                                       quality=item.gem_quality, corrupted=bool(item.corrupted))
        if not econ:
            r.confidence = "none"
            r.note = "couldn't price (poe.ninja economy unavailable)"
            r.extra = {"kind": "skill", "level": item.gem_level, "quality": item.gem_quality,
                       "corrupted": bool(item.corrupted), "source": "poe.ninja",
                       "total_chaos": None, "gems": [],
                       "trade_query": self._payload(active_query), **host_extra}
            return r
        breakdown: List[dict] = []
        total = 0.0
        priced_any = False
        min_lc: Optional[int] = None

        def _one(nm, lvl, qual, corr, is_support, is_granted):
            nonlocal total, priced_any, min_lc
            m = None if is_granted else econ.gem_price(nm, int(lvl or 0) or 20,
                                                       int(qual or 0), bool(corr))
            chaos = (m or {}).get("chaos")
            if is_granted:
                where = f" by {host_extra['host_name']}" if host_extra["host_name"] else " (item-provided)"
                note = "granted" + where + " - not counted"
            elif chaos is None:
                note = "no poe.ninja price for this gem"
            else:
                note = ""
            breakdown.append({
                "name": nm, "support": bool(is_support), "granted": bool(is_granted),
                "level": int(lvl or 0), "quality": int(qual or 0), "corrupted": bool(corr),
                "chaos": chaos, "variant": (m or {}).get("variant", ""), "note": note,
                "trade_url": self._gem_search_url(nm, support=bool(is_support), level=lvl,
                                                  quality=qual, corrupted=bool(corr))})
            if chaos is not None:
                total += chaos
                priced_any = True
                lc = (m or {}).get("listing_count") or 0
                min_lc = lc if min_lc is None else min(min_lc, lc)

        _one(name, item.gem_level, item.gem_quality, item.corrupted, item.support, active_granted)
        for s in (item.supports or []):
            if s.get("name"):
                _one(s["name"], s.get("level"), s.get("quality"), s.get("corrupted"),
                     s.get("support", True), bool(s.get("granted")))

        if not priced_any:
            r.confidence = "none"
            r.note = ("item-granted skill (comes free with the host item)" if active_granted
                      else "no poe.ninja gem price for this skill setup")
        else:
            r.tier = PriceTier(minimum=total, median=total, high=total)
            r.sample_size = 1
            r.total_found = 1
            lc = min_lc or 0
            r.confidence = self._confidence_from_lc(lc)
            nsup = sum(1 for g in breakdown if g["support"] and g["chaos"] is not None)
            lead = "supports only (active is item-granted)" if active_granted else "active"
            r.note = ("poe.ninja gem prices: " + lead
                      + (f" + {nsup} support" + ("s" if nsup != 1 else "") if nsup else ""))
        r.extra = {"kind": "skill", "level": item.gem_level, "quality": item.gem_quality,
                   "corrupted": bool(item.corrupted), "source": "poe.ninja",
                   "total_chaos": total if priced_any else None, "gems": breakdown,
                   "trade_query": self._payload(active_query), **host_extra}
        return r

    # ---- unique pricing (poe.ninja by name; NEW) -------------------------
    def price_unique_ninja(self, item: Item) -> PriceResult:
        r = PriceResult(item=item, method="unique-ninja")
        econ = self._econ()
        query = self._unique_query(item) if item.name else None
        self._attach_query(r, query)
        if not item.name or not econ:
            r.method = "unique-unpriced"
            r.confidence = "none"
            r.note = ("no poe.ninja economy available; price via the trade link"
                      if item.name else "unnamed unique; price via the trade link")
            r.extra["source"] = "none"
            return r
        mod_text = " ".join(item.explicit_mods or [])
        m = econ.unique_price(item.name, mod_text=mod_text, base_type=item.base_type)
        if not m:
            r.method = "unique-unpriced"
            r.confidence = "none"
            r.note = "not listed on poe.ninja; price it on your machine via the trade link"
            r.extra["source"] = "none"
            return r
        r.tier = PriceTier(minimum=m["chaos_min"], median=m["chaos_median"], high=m["chaos_high"])
        r.total_found = m.get("count") or 0
        r.sample_size = 1
        r.extra["source"] = "poe.ninja"
        r.extra["listing_count"] = m.get("listing_count") or 0
        r.extra["n_variants"] = m.get("n_variants") or 1
        r.extra["variant"] = m.get("variant") or ""
        matched = m.get("matched")
        if matched == "range":
            r.method = "unique-ninja-range"
            r.confidence = "low"
            r.note = (f"{m.get('n_variants')} variants on poe.ninja; showing the price "
                      "range (min..high) - exact roll unclear, verify via the trade link")
        elif matched == "variant":
            r.method = "unique-ninja-variant"
            r.confidence = "high" if (m.get("listing_count") or 0) >= 5 else "medium"
            r.note = f"poe.ninja price for variant '{m.get('variant')}'"
        else:  # "name"
            r.method = "unique-ninja"
            r.confidence = self._confidence_from_lc(m.get("listing_count") or 0)
            r.note = "poe.ninja price by name"
        return r

    # ---- rare / magic: not priced here; carry the exact trade query ------
    def price_rare_unpriced(self, item: Item) -> PriceResult:
        r = PriceResult(item=item, method="rare-unpriced")
        query = self._rare_query_default(item)
        self._attach_query(r, query)
        r.confidence = "none"
        r.extra["source"] = "trade"
        if query is None:
            r.note = f"base {item.base_type!r} / category not recognised by trade"
        else:
            r.note = ("rares are priced on your machine via the trade link / extension "
                      "(this server never calls the trade API)")
        return r

    def price_magic_unpriced(self, item: Item) -> PriceResult:
        r = PriceResult(item=item, method="magic-unpriced")
        query = self._magic_query(item)
        self._attach_query(r, query)
        r.confidence = "none"
        r.extra["source"] = "trade"
        if query is None:
            r.note = f"base {item.base_type!r} not recognised by trade"
        else:
            r.note = "magic items are usually cheap; check via the trade link"
        return r

    # ---- orchestration ---------------------------------------------------
    def price_build(self, items: List[Item]) -> List[PriceResult]:
        """Price every item, ninja where possible, else attach a trade query. Results are
        returned in the build's original order (belt order for flasks, skills[] order for
        gems, items[] order for gear) -- matching bpc.Pricer.price_build's contract."""
        results: List[PriceResult] = []
        for it in items:
            if it.category == CAT_GEM:
                results.append(self.price_skill(it))
            elif it.category == CAT_UNIQUE:
                results.append(self.price_unique_ninja(it))
            elif it.category == CAT_RARE:
                results.append(self.price_rare_unpriced(it))
            elif it.category == CAT_MAGIC:
                results.append(self.price_magic_unpriced(it))
            else:
                results.append(PriceResult(item=it, method="none",
                               note="normal item; not priced", confidence="none"))
        return results
