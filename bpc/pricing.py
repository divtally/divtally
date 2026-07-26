"""Price each normalised item via the PoE1 trade API and reduce listings to min/median/high.

Strategy by category (chosen to stay within trade rate limits):
  unique  -> search by name + base type (+ links for 5L/6L)   (1-2 searches)
  rare    -> search by base type + top mods (+ defence totals + links),
             fall back to base type only                       (1-2 searches)
  magic   -> search by base type only                          (1 search)  [flasks/jewels]
  gem     -> poe.ninja SkillGem economy: name+level+quality+corrupt (no search budget)

Tiers (all in Chaos Orbs):
  min    = cheapest realistic listing (after trimming scam-low outliers)
  median = median of the sampled listings
  high   = ~90th percentile of the sample  (a clearly-better-rolled copy)
"""
import json
import re
import urllib.parse
from typing import Dict, List, Optional, Tuple

from . import cache, util
from .currency import CurrencyConverter
from .models import (CAT_GEM, CAT_MAGIC, CAT_NORMAL, CAT_RARE,
                     CAT_UNIQUE, Item, PriceResult, PriceTier)
from .statmap import StatMapper, is_local_defence, _score
from .trade import TradeClient

SAMPLE = 20            # listings to fetch per item for the distribution
HIGH_PCT = 90          # percentile used for the "high budget" tier
SEARCH_BUDGET = 30     # hard cap on searches per run (limiter keeps us under bans)

# Armour pieces: local defence mods on these collide with global trade stats.
_ARMOUR_INV = {"Helm", "BodyArmour", "Gloves", "Boots", "Offhand"}

# Pseudo stats let trade match an item's *combined* resistance regardless of how it's
# split across mods (ids verified identical to PoE2). We offer the combined elemental
# total and the chaos total. "Maximum"/penetration/enemy resistance mods are NOT additive
# resistance and must be excluded from the totals.
_PSEUDO_ELEM_RES = "pseudo.pseudo_total_elemental_resistance"
_PSEUDO_CHAOS_RES = "pseudo.pseudo_total_chaos_resistance"


def load_item_types(client) -> dict:
    """Trade base types grouped by category. Returns {'all': set, 'by_group': {label: set}}.
    Cached on disk for a day (shared with the Pricer). Used by the PoB parser too."""
    data = cache.cached(
        "trade:data:items", 86400,
        lambda: client._request("data", "GET",
                                "https://www.pathofexile.com/api/trade/data/items"))
    by_group, allt = {}, set()
    for grp in data.get("result", []):
        s = set()
        for e in grp.get("entries", []):
            if e.get("type"):
                s.add(e["type"]); allt.add(e["type"])
        by_group[grp.get("label", "")] = s
    return {"all": allt, "by_group": by_group}


def _is_res_affix(text: str) -> bool:
    """True if a mod adds to the player's resistances (so it folds into a pseudo total)."""
    t = util.strip_rich(text).lower()
    if "resist" not in t:
        return False
    return not ("maximum" in t or "penetrat" in t or "enemy" in t)


def _affix_tier(line: str, ok: bool, is_unique: bool) -> str:
    """Default mod-priority-survey tier for an affix: required / nice / notimp / skip.
    Rares use the canonical price-relevance score; uniques default only their build-defining
    skill-level rolls to required (other unique mods are fixed, priced by name)."""
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


def _is_skill_level_mod(text: str) -> bool:
    """True for build-defining '+# to Level of all <X> Skills' rolls -- any element or type
    (Fire/Cold/Lightning/Chaos/Attack/Spell/...), including 'Skill Gems'. On a unique these
    swing the price enormously (e.g. +3 vs +1 gem levels), so we price the build's actual
    roll instead of the cheapest version, and default the affix picker to require it."""
    t = util.strip_rich(text).lower()
    return "to level of all" in t and "skill" in t


def res_contributions(mods: List[str]) -> dict:
    """Sum an item's additive resistance mods into per-element / chaos / combined totals,
    mirroring how the trade pseudo stats aggregate ('to all elemental' feeds every
    element; 'to all resistances' feeds every element and chaos)."""
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

# itemData.inventoryId -> trade category option (fallback when base type is unknown).
# PoE1 category tokens verified against /api/trade/data/filters (docs/research/trade1.md 6).
_INVENTORY_CATEGORY = {
    "Helm": "armour.helmet", "BodyArmour": "armour.chest", "Gloves": "armour.gloves",
    "Boots": "armour.boots", "Belt": "accessory.belt", "Amulet": "accessory.amulet",
    "Ring": "accessory.ring", "Ring2": "accessory.ring", "Offhand": "armour.shield",
    "Offhand2": "armour.shield", "Weapon": "weapon", "Weapon2": "weapon",
    "Jewel": "jewel", "PassiveJewels": "jewel", "Flask": "flask",
}

# Display labels for an item's TOTAL defence values (searched via armour_filters instead of
# the individual armour/evasion/ES affixes, which collide with global stats).
_DEF_LABEL = {"es": "Total Energy Shield", "ev": "Total Evasion Rating",
              "ar": "Total Armour", "ward": "Total Ward"}

# trade stat-group types. The query.stats array holds one or more of these group objects
# (all ANDed together). 'and' = match all; 'not' = exclude; 'if' = enforce only if present;
# 'count' = group value.min/max bounds the NUMBER of contained filters that match; 'weight'/
# 'weight2' = weighted sum of (filter value * filter.value.weight) vs the group's value.min.
_GROUP_TYPES = {"and", "not", "if", "count", "weight", "weight2"}
_WEIGHT_TYPES = {"weight", "weight2"}


def _build_stat_groups(groups: List[dict]) -> List[dict]:
    """Convert the picker's group payload into trade query.stats group objects.

    Each input group: {type, min, max, filters:[{stat_id, min, max, weight, option}]}.
    Per-filter weight is only emitted for weight/weight2 groups (filter.value.weight). The
    group's own min/max becomes the group `value` (count threshold, or weighted-sum min).
    Empty groups (no usable filters) are dropped."""
    out: List[dict] = []
    for g in groups or []:
        gtype = g.get("type", "and")
        if gtype not in _GROUP_TYPES:
            gtype = "and"
        # The SEARCH API rejects weight / weight2 groups outright (they are a UI-only
        # construct). Coerce any weighted group to a COUNT group so the search still runs
        # ("how many of these mods you want"), which is what the survey emits anyway.
        coerced_weight = gtype in _WEIGHT_TYPES
        if coerced_weight:
            gtype = "count"
        is_weight = False        # never emit per-filter weights -- the API would 400
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
            # Collapse duplicate same-id filters in one group (keep tightest min/max + max weight).
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
        # Type-specific safety so a stale/blank UI value can't emit an impossible query.
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


class Pricer:
    STATUS_OPTIONS = ("online", "any", "onlineleague", "available", "securable")

    def __init__(self, client: TradeClient, verbose: bool = True, progress=None,
                 status: str = "online", economy=None):
        self.client = client
        self.economy = economy                       # poeninja.PoeNinjaEconomy (gems + rates)
        self.conv = CurrencyConverter(client, economy)
        self.mapper = StatMapper(client)
        self.verbose = verbose
        self.progress = progress  # optional callable(str) for non-CLI front-ends
        self.status = status if status in self.STATUS_OPTIONS else "online"
        self._valid_types = self._load_types()

    def _status(self) -> dict:
        """Listing-status filter applied to every item search (online / any / league)."""
        return {"option": self.status}

    def _emit(self, msg: str) -> None:
        if self.progress:
            self.progress(msg)
        elif self.verbose:
            print(msg, flush=True)

    def _econ(self):
        return self.economy

    # ---- reference data --------------------------------------------------
    def _load_types(self) -> set:
        try:
            return load_item_types(self.client)["all"]
        except Exception:
            return set()

    def currency_image(self, cid: str) -> str:
        """Full image URL for a currency id (e.g. 'chaos', 'divine'), or ''."""
        try:
            for grp in self.client.static_data().get("result", []):
                for e in grp.get("entries", []):
                    if e.get("id") == cid and e.get("image"):
                        img = e["image"]
                        return img if img.startswith("http") else "https://web.poecdn.com" + img
        except Exception:
            pass
        return ""

    # ---- helpers ---------------------------------------------------------
    def resolve_type(self, base: str) -> Optional[str]:
        """Return a valid trade base type, stripping runic/quality prefixes if needed."""
        if not base:
            return None
        if not self._valid_types or base in self._valid_types:
            return base
        words = base.split()
        for start in range(1, len(words)):
            cand = " ".join(words[start:])
            if cand in self._valid_types:
                return cand
        return None  # unknown base; caller decides fallback

    def _links_filter(self, item: Item) -> dict:
        """socket_filters for a 5L/6L item (body armour / two-handed weapon). PoE1-only; a
        6-link is often the single largest cost on a budget build, so a like-for-like search
        must pin the link count. Below 5 links, links don't move price -> no filter."""
        ml = int(getattr(item, "max_link", 0) or 0)
        if ml >= 5:
            return {"socket_filters": {"filters": {"links": {"min": ml}}}}
        return {}

    def _trade_url(self, query_id: Optional[str]) -> str:
        if not query_id:
            return ""
        return (f"https://www.pathofexile.com/trade/search/"
                f"{urllib.parse.quote(self.client.league)}/{query_id}")

    def _q_url(self, query: dict) -> str:
        """A clickable trade URL that pre-fills the EXACT query via ?q= (built locally, no API
        call). Unlike a server query-id link it never expires (so saved results stay clickable)
        and it opens even when the search found nothing -- letting the user see WHY an item
        wasn't matched. Used for every rare/unique result, found or not."""
        if not query:
            return ""
        try:
            payload = {"query": query, "sort": {"price": "asc"}}
            q = urllib.parse.quote(json.dumps(payload, separators=(",", ":")), safe="")
            return (f"https://www.pathofexile.com/trade/search/"
                    f"{urllib.parse.quote(self.client.league)}?q={q}")
        except Exception:
            return ""

    @staticmethod
    def _mod_text(m) -> str:
        """A fetched listing's explicitMods are OBJECTS in PoE1 ({description, hash, mods}),
        not strings -- read the display text off `description` (guard against a bare string)."""
        if isinstance(m, dict):
            return m.get("description", "") or ""
        return str(m or "")

    def _listings_prices(self, listings: List[dict]) -> List[float]:
        out = []
        for res in listings:
            price = (res.get("listing", {}) or {}).get("price") or {}
            amt, cur = price.get("amount"), price.get("currency")
            if amt is None or not cur:
                continue
            ch = self.conv.to_chaos(amt, cur)
            if ch is not None and ch > 0:
                out.append(ch)
        return out

    @staticmethod
    def _spread(ids: List[str], k: int) -> List[str]:
        """Pick up to k ids evenly spaced by rank. Trade returns hashes sorted by
        price ascending, so rank-uniform sampling approximates the true distribution
        (correct percentiles) instead of only seeing the cheapest listings."""
        n = len(ids)
        if k <= 1:
            return ids[:1]
        if n <= k:
            return ids
        idxs = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
        return [ids[i] for i in idxs]

    def _search_listings(self, query: dict) -> Tuple[List[list], int, Optional[str]]:
        """Search + fetch a rank-spread sample. Returns ([[price_chaos, [mod_patterns]], ...],
        total, qid). Cached 30 min per (league, query) so re-runs don't re-spend the
        search budget. The per-listing mod patterns let us detect 'version' uniques."""
        ckey = "search:" + self.client.league + ":" + json.dumps(query, sort_keys=True)
        hit = cache.get(ckey, 1800)
        if hit is not None:
            return hit[0], hit[1], hit[2]
        sr = self.client.search(query)
        qid = sr.get("id")
        ids = sr.get("result", []) or []
        total = sr.get("total", len(ids))
        listings: List[list] = []
        sample_ids = self._spread(ids, SAMPLE)
        for i in range(0, len(sample_ids), 10):
            chunk = sample_ids[i:i + 10]
            for res in self.client.fetch(chunk, qid):
                price = (res.get("listing", {}) or {}).get("price") or {}
                amt, cur = price.get("amount"), price.get("currency")
                if amt is None or not cur:
                    continue
                ch = self.conv.to_chaos(amt, cur)
                if ch is None or ch <= 0:
                    continue
                mods = (res.get("item", {}) or {}).get("explicitMods", []) or []
                pats = set()
                for m in mods:
                    txt = self._mod_text(m)
                    if txt:
                        pats.add(util.mod_to_pattern(txt))
                listings.append([ch, sorted(pats)])
        cache.put(ckey, [listings, total, qid])
        return listings, total, qid

    def _search_collect(self, query: dict) -> Tuple[List[float], int, Optional[str]]:
        listings, total, qid = self._search_listings(query)
        return [l[0] for l in listings], total, qid

    def _tiers(self, prices: List[float]) -> Tuple[PriceTier, int]:
        kept = util.trim_outliers(prices)
        if not kept:
            return PriceTier(), 0
        return PriceTier(minimum=kept[0],
                         median=util.median(kept),
                         high=util.percentile(kept, HIGH_PCT)), len(kept)

    @staticmethod
    def _confidence(sample: int, total: int) -> str:
        if total == 0 or sample == 0:
            return "none"
        if sample >= 6 and total >= 8:
            return "high"
        if sample >= 3:
            return "medium"
        return "low"

    def _variant_affixes(self, item: Item, listings: List[list]) -> dict:
        """Most uniques have fixed affixes (only rolls vary) -> price by name. Some
        ('version' uniques like Loreweave, Watcher's Eye) carry affixes that differ
        between copies. We detect these: a build mod whose PATTERN (numbers blanked) is
        shared by fewer than half the listings is version-specific, not a roll. Returns
        {'mappable': [trade stat filters], 'unmappable': [mod texts]}."""
        out = {"mappable": [], "unmappable": []}
        n = len(listings)
        if n < 4 or not item.explicit_mods:
            return out
        freq: Dict[str, int] = {}
        for _ch, pats in listings:
            for p in pats:
                freq[p] = freq.get(p, 0) + 1
        for mod in item.explicit_mods:
            pat = util.mod_to_pattern(mod)
            if freq.get(pat, 0) / n >= 0.5:
                continue                       # shared by most listings -> fixed mod (roll)
            sid = self.mapper.match_line(mod)
            if sid:
                out["mappable"].append({"id": sid})
            else:
                out["unmappable"].append(mod)
        return out

    # ---- per-category pricing -------------------------------------------
    def _unique_value_filters(self, item: Item) -> List[dict]:
        """Stat filters for a unique's build-defining skill-level rolls, each pinned to the
        build's actual value (min). These swing price hugely, so the default unique price
        targets the build's roll rather than the cheapest copy."""
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

    def price_unique(self, item: Item) -> PriceResult:
        r = PriceResult(item=item, method="unique-name")
        links = self._links_filter(item)
        query = {"status": self._status(), "name": item.name,
                 "type": item.base_type, "stats": [{"type": "and", "filters": []}]}
        if links:
            query["filters"] = dict(links)
        listings, total, qid = self._search_listings(query)
        r.tier, r.sample_size = self._tiers([l[0] for l in listings])
        r.total_found = total
        r.trade_url = self._q_url(query)
        r.confidence = self._confidence(r.sample_size, total)
        if total == 0:
            r.note = "no online listings (may be self-found / dropped-only)"
            return r
        # Refine to the build's actual copy: skill-level rolls pinned to the build's value
        # (priced even when few copies are listed -- the roll dominates the price) PLUS any
        # 'version' affixes that distinguish this copy from other versions of the unique.
        variant = self._variant_affixes(item, listings)
        value_filters = self._unique_value_filters(item)
        refine, seen = [], set()
        for f in value_filters + variant["mappable"]:
            if f["id"] in seen:
                continue
            seen.add(f["id"]); refine.append(f)
        if refine:
            rq = {"status": self._status(), "name": item.name, "type": item.base_type,
                  "stats": [{"type": "and", "filters": refine}]}
            if links:
                rq["filters"] = dict(links)
            rl, rtot, rqid = self._search_listings(rq)
            rtier, rsamp = self._tiers([l[0] for l in rl])
            # a skill-level roll matters even when few copies are listed -> accept any sample;
            # a pure 'version' refinement still needs >=3 listings to trust over the broad price.
            min_samp = 1 if value_filters else 3
            if rsamp >= min_samp:
                r.tier, r.sample_size, r.total_found = rtier, rsamp, rtot
                r.trade_url = self._q_url(rq)
                r.method = "unique-roll" if value_filters else "unique-variant"
                r.confidence = "high" if rsamp >= 5 else ("medium" if rsamp >= 3 else "low")
                bits = []
                if value_filters:
                    bits.append(f"{len(value_filters)} skill-level roll(s) at the build's value")
                if variant["mappable"]:
                    bits.append(f"{len(variant['mappable'])} version affix(es)")
                r.note = "priced the build's copy (" + ", ".join(bits) + ")"
            else:                                # too few of this exact copy listed -> flag
                r.trade_url = self._q_url(rq) or r.trade_url
                r.note = ("few/no copies of the build's exact roll listed; price shown spans "
                          "versions/rolls -- use 'edit affixes' to set an affordable roll")
                if r.confidence == "high":
                    r.confidence = "medium"
        elif variant["unmappable"]:
            r.note = ("variable unique - price spans different versions "
                      f"({len(variant['unmappable'])} version affix(es) not searchable)")
            if r.confidence == "high":
                r.confidence = "medium"
        return r

    def _rare_scopes(self, item: Item) -> List[Tuple[dict, str]]:
        """Ordered query scopes to try: exact base type first (best comparables), then
        the item category (broader pool, rescues narrow/uncommon bases)."""
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
        """The item's mods/defences as selectable search filters (for the advanced UI).

        Returns {"affixes": [...], "pseudo": [...]}. Each entry has a `kind`:
          - "stat":  an explicit mod -> {stat_id, value, searchable, resist}
          - "equip": a total defence value -> {key (ar/ev/es/ward), value}  (searched via
            armour_filters; the individual armour/evasion/ES affixes are dropped because
            we match the item's TOTAL value instead)."""
        is_armour = bool(item.defences) or item.raw.get("inventoryId", "") in _ARMOUR_INV
        is_unique = item.category == CAT_UNIQUE
        affixes = []
        for i, line in enumerate(item.explicit_mods):
            if is_armour and is_local_defence(line):
                continue                # filtered via the defence total below, not as an affix
            src = item.mod_src[i] if i < len(item.mod_src) else None  # enchant/explicit/...
            # Only ENCHANTS need group-scoping (their stat id differs from the same-text explicit
            # and the item has it ONLY as an enchant). crafted/fractured share the explicit stat
            # and search best as explicit -- the broadest pool of comparables.
            grp = "enchant" if src == "enchant" else None
            sid, neg = self.mapper.match(line, group=grp)
            ok = bool(sid)
            v = util.first_number(line)
            if ok and neg and v is not None:
                v = -abs(v)             # 'reduced' roll -> negative on the 'increased' stat
            # `prefer` = ticked by default in the picker. Rares default to every searchable
            # affix; uniques have fixed mods (only rolls vary) so we default ONLY the build-
            # defining skill-level rolls -- the rest are opt-in.
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
        """Assemble a rare trade query for one scope (base type or item category) with the
        given stat groups + defence totals (armour_filters) + a 5L/6L socket-links filter.
        Pure query construction -- runs NO search, so a budget-skipped item can still get a
        clickable URL from the exact query it WOULD have run."""
        query = dict(scope)
        query["status"] = self._status()
        query["stats"] = stat_groups or [{"type": "and", "filters": []}]
        filt = dict(query.get("filters", {}))      # scope may carry type_filters
        if equip_filters:
            filt["armour_filters"] = {"filters": equip_filters}
        filt.update(self._links_filter(item))       # {} for <5 links -> no-op
        if filt:
            query["filters"] = filt
        return query

    def _price_rare_query(self, item: Item, stat_groups: List[dict], equip_filters: dict,
                          method: str, built_for: str) -> PriceResult:
        """Run a rare search (base scope then category) with the given stat groups, defence-
        total filters (armour_filters) and a socket-links filter (for 5L/6L gear), and reduce
        to tiers. `stat_groups` is the trade query.stats array; [] searches by scope alone."""
        r = PriceResult(item=item, method=method)
        scopes = self._rare_scopes(item)
        if not scopes:
            r.note = f"base {item.base_type!r} / category not recognised by trade"
            r.confidence = "none"
            return r
        for scope, scope_label in scopes:
            if self.client.search_count >= SEARCH_BUDGET:
                break
            query = self._rare_query(item, scope, stat_groups, equip_filters)
            prices, total, qid = self._search_collect(query)
            # The clickable link must be the MOST SPECIFIC (base-type) search -- NOT the broad
            # category fallback we try next. Keep the first scope's URL.
            if not r.trade_url:
                r.trade_url = self._q_url(query)
            # require PARSED prices, not just a reported match count -- if the sampled listings
            # are all unpriceable, fall through to the next scope rather than returning blank.
            if total > 0 and prices:
                r.tier, r.sample_size = self._tiers(prices)
                r.total_found = total
                where = "same base" if scope_label == "base" else "same slot"
                r.confidence = ("high" if (scope_label == "base" and r.sample_size >= 4)
                                else "medium" if r.sample_size >= 3 else "low")
                r.method = f"{method}-{scope_label}"
                r.note = f"{built_for} ({where})"
                return r
        r.confidence = "none"
        r.note = (f"no listing matches {built_for.lower()} "
                  "(item may be uniquely rolled) - see trade_url to check manually")
        return r

    def _rare_default_filters(self, item: Item) -> Tuple[List[dict], dict, int]:
        """The DEFAULT rare search parts (README: "require all of the item's searchable
        affixes"): one AND group of every searchable affix, plus each total-defence value at
        >=85%. Returns (stat_groups, equip_filters, n_unsearchable). Pure -- runs NO search,
        so the same parts drive both live pricing and a budget-skipped item's trade link."""
        opts = self.affix_options(item)["affixes"]
        stat_opts = [o for o in opts if o["kind"] == "stat" and o["searchable"]]
        equip_opts = [o for o in opts if o["kind"] == "equip" and o["value"]]

        def _statf(o):
            f = {"id": o["stat_id"]}
            if o.get("negated") and o.get("value") is not None:
                # negated ('reduced') roll: better = more negative -> constrain as a max
                f["value"] = {"max": int(o["value"])}
            return f
        stat_filters = [_statf(o) for o in stat_opts]
        equip_filters = {o["key"]: {"min": int(o["value"] * 0.85)} for o in equip_opts}
        n_skip = sum(1 for o in opts if o["kind"] == "stat" and not o["searchable"])
        stat_groups = [{"type": "and", "filters": stat_filters}] if stat_filters else []
        return stat_groups, equip_filters, n_skip

    def price_rare(self, item: Item) -> PriceResult:
        """Default rare pricing: require all of the item's searchable affixes AND at least
        ~85% of each of its total defence values (armour/evasion/ES/ward)."""
        stat_groups, equip_filters, n_skip = self._rare_default_filters(item)
        stat_filters = stat_groups[0]["filters"] if stat_groups else []
        if not stat_filters and not equip_filters:
            r = self._price_rare_query(item, [], {}, "rare-base", "base-type ballpark")
            if r.confidence != "none":
                r.confidence = "low"
                r.note = "no searchable affixes; base/category price only (rough)"
            return r
        parts = []
        if stat_filters:
            parts.append(f"{len(stat_filters)} affixes")
        if equip_filters:
            parts.append(f"{len(equip_filters)} defence total"
                         + ("s" if len(equip_filters) > 1 else ""))
        built = "requires " + " + ".join(parts)
        if n_skip:
            built += f" ({n_skip} not searchable)"
        return self._price_rare_query(item, stat_groups, equip_filters, "rare-all", built)

    def _custom_query_parts(self, groups: Optional[List[dict]],
                            selections: Optional[List[dict]],
                            equip: Optional[List[dict]]) -> Tuple[List[dict], dict]:
        """Build (stat_groups, equip_filters) from a picker submission. Accepts the new
        multi-group `groups` payload, or the legacy flat `selections` (wrapped in one AND
        group) for older front-ends. `equip` (defence totals) is always a flat list."""
        if groups:
            stat_groups = _build_stat_groups(groups)
        else:
            flat = []
            for s in selections or []:
                sid = s.get("stat_id")
                if not sid:
                    continue
                val = {}
                if s.get("min") is not None:
                    val["min"] = s["min"]
                if s.get("max") is not None:
                    val["max"] = s["max"]
                ff = {"id": sid}
                if val:
                    ff["value"] = val
                flat.append(ff)
            stat_groups = [{"type": "and", "filters": flat}] if flat else []
        equip_filters = {}
        for e in equip or []:
            key = e.get("key")
            if not key:
                continue
            val = {}
            if e.get("min") is not None:
                val["min"] = e["min"]
            if e.get("max") is not None:
                val["max"] = e["max"]
            if val:
                equip_filters[key] = val
        return stat_groups, equip_filters

    @staticmethod
    def _count_filters(stat_groups: List[dict], equip_filters: dict) -> int:
        return sum(len(g.get("filters", [])) for g in stat_groups) + len(equip_filters)

    def price_rare_custom(self, item: Item, selections: Optional[List[dict]] = None,
                          equip: Optional[List[dict]] = None,
                          groups: Optional[List[dict]] = None) -> PriceResult:
        """Advanced rare pricing from user-chosen stat groups (or legacy flat filters)."""
        stat_groups, equip_filters = self._custom_query_parts(groups, selections, equip)
        if not stat_groups and not equip_filters:
            r = self._price_rare_query(item, [], {}, "rare-base", "base-type ballpark")
            if r.confidence != "none":
                r.confidence = "low"
                r.note = "no filters selected; base/category price only (rough)"
            return r
        n = self._count_filters(stat_groups, equip_filters)
        return self._price_rare_query(item, stat_groups, equip_filters, "rare-custom",
                                      f"your {n} filter" + ("s" if n != 1 else ""))

    def price_unique_custom(self, item: Item, selections: Optional[List[dict]] = None,
                            equip: Optional[List[dict]] = None,
                            groups: Optional[List[dict]] = None) -> PriceResult:
        """Advanced unique pricing: search by name+base + user-chosen stat groups (e.g. lower
        a skill-level roll to an affordable value, or a count group of nice-to-haves)."""
        stat_groups, equip_filters = self._custom_query_parts(groups, selections, equip)
        r = PriceResult(item=item, method="unique-custom")
        query = {"status": self._status(), "name": item.name, "type": item.base_type,
                 "stats": stat_groups or [{"type": "and", "filters": []}]}
        filt = {}
        if equip_filters:
            filt["armour_filters"] = {"filters": equip_filters}
        filt.update(self._links_filter(item))
        if filt:
            query["filters"] = filt
        prices, total, qid = self._search_collect(query)
        r.tier, r.sample_size = self._tiers(prices)
        r.total_found = total
        r.trade_url = self._q_url(query)
        r.confidence = self._confidence(r.sample_size, total)
        n = self._count_filters(stat_groups, equip_filters)
        r.note = (f"your {n} filter" + ("s" if n != 1 else "")) if n else "priced by name (no filters)"
        if total == 0:
            r.note = "no listings match your filters (try a lower roll or fewer mods)"
        return r

    def price_magic(self, item: Item) -> PriceResult:
        r = PriceResult(item=item, method="magic-base")
        btype = self.resolve_type(item.base_type)
        if not btype:
            r.note = f"base {item.base_type!r} not recognised"
            r.confidence = "none"
            return r
        query = {"status": self._status(), "type": btype,
                 "stats": [{"type": "and", "filters": []}]}
        prices, total, qid = self._search_collect(query)
        r.tier, r.sample_size = self._tiers(prices)
        r.total_found = total
        r.trade_url = self._q_url(query)
        r.confidence = "low"  # magic items are not mod-matched
        r.note = "priced by base only; magic flasks/jewels are typically cheap"
        return r

    # ---- gem / skill pricing (poe.ninja SkillGem economy; NO trade API -> no ban risk) ----
    def _gem_search_url(self, name, *, support: bool = False, level=None,
                        quality=None, corrupted: bool = False) -> str:
        """A clickable trade search URL that pre-fills the query via ?q= -- built locally,
        with NO API request (the browser POSTs it on click). PoE1 has NO gem_sockets filter
        (gems have no support sockets); we use gem_level / quality / corrupted."""
        if not name:
            return ""
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
        query = {"status": self._status(), "type": name, "filters": filters,
                 "stats": [{"type": "and", "filters": []}]}
        payload = {"query": query, "sort": {"price": "asc"}}
        q = urllib.parse.quote(json.dumps(payload, separators=(",", ":")), safe="")
        league = urllib.parse.quote(self.client.league)
        return f"https://www.pathofexile.com/trade/search/{league}?q={q}"

    def price_skill(self, item: Item) -> PriceResult:
        """Price one gem GROUP (an active skill + its support gems) from poe.ninja's SkillGem
        economy (no trade search). PoE1 gems are real, tradeable items priced by
        name + level + quality + corruption -- so the group cost = the active gem + EVERY
        support gem (Awakened/Empower/Enlighten supports can be the biggest cost). Contrast
        the PoE2 parent's uncut-gem + Jeweller's-Orb synthesis, which is deleted."""
        econ = self._econ()
        r = PriceResult(item=item, method="skill")
        name = item.base_type or item.type_line
        r.trade_url = self._gem_search_url(name, support=bool(item.support),
                                           level=item.gem_level, quality=item.gem_quality,
                                           corrupted=bool(item.corrupted))
        if not econ:
            r.confidence = "none"
            r.note = "couldn't price (poe.ninja economy unavailable)"
            r.extra = {"kind": "skill", "level": item.gem_level, "quality": item.gem_quality,
                       "corrupted": bool(item.corrupted), "source": "poe.ninja",
                       "total_chaos": None, "gems": []}
            return r
        breakdown: List[dict] = []
        total = 0.0
        priced_any = False
        min_lc: Optional[int] = None

        def _one(nm, lvl, qual, corr, is_support):
            nonlocal total, priced_any, min_lc
            m = econ.gem_price(nm, int(lvl or 0) or 20, int(qual or 0), bool(corr))
            chaos = (m or {}).get("chaos")
            breakdown.append({
                "name": nm, "support": bool(is_support), "level": int(lvl or 0),
                "quality": int(qual or 0), "corrupted": bool(corr),
                "chaos": chaos, "variant": (m or {}).get("variant", ""),
                "trade_url": self._gem_search_url(nm, support=bool(is_support), level=lvl,
                                                  quality=qual, corrupted=bool(corr))})
            if chaos is not None:
                total += chaos
                priced_any = True
                lc = (m or {}).get("listing_count") or 0
                min_lc = lc if min_lc is None else min(min_lc, lc)

        _one(name, item.gem_level, item.gem_quality, item.corrupted, item.support)
        for s in (item.supports or []):
            if s.get("name"):
                _one(s["name"], s.get("level"), s.get("quality"), s.get("corrupted"), True)

        if not priced_any:
            r.confidence = "none"
            r.note = "no poe.ninja gem price for this skill setup"
        else:
            r.tier = PriceTier(minimum=total, median=total, high=total)  # point estimate
            r.sample_size = 1
            r.total_found = 1
            lc = min_lc or 0
            r.confidence = "high" if lc >= 5 else ("medium" if lc >= 2 else "low")
            nsup = len(item.supports or [])
            r.note = ("poe.ninja gem prices: active"
                      + (f" + {nsup} support" + ("s" if nsup != 1 else "") if nsup else ""))
        r.extra = {"kind": "skill", "level": item.gem_level, "quality": item.gem_quality,
                   "corrupted": bool(item.corrupted), "source": "poe.ninja",
                   "total_chaos": total if priced_any else None, "gems": breakdown}
        return r

    def _skip_trade_url(self, item: Item) -> str:
        """A clickable trade URL for an item left UNPRICED because the per-run search budget
        was already spent. Mirrors the query its category WOULD have run, built locally with NO
        API call (the browser POSTs it on click), so a skipped row still carries a trade link
        and no number -- the same 'unpriceable => trade link, never a misleading price'
        guardrail every other unpriceable row honours (README/CLAUDE.md)."""
        if item.category == CAT_UNIQUE:
            query = {"status": self._status(), "name": item.name, "type": item.base_type,
                     "stats": [{"type": "and", "filters": []}]}
            links = self._links_filter(item)
            if links:
                query["filters"] = dict(links)
            return self._q_url(query)
        if item.category == CAT_RARE:
            scopes = self._rare_scopes(item)
            if not scopes:
                return ""
            stat_groups, equip_filters, _ = self._rare_default_filters(item)
            return self._q_url(self._rare_query(item, scopes[0][0], stat_groups, equip_filters))
        if item.category == CAT_MAGIC:
            btype = self.resolve_type(item.base_type)
            if not btype:
                return ""
            return self._q_url({"status": self._status(), "type": btype,
                                "stats": [{"type": "and", "filters": []}]})
        return ""

    # ---- orchestration ---------------------------------------------------
    def price_build(self, items: List[Item]) -> List[PriceResult]:
        results: List[PriceResult] = []
        gems = [it for it in items if it.category == CAT_GEM]
        non_gems = [it for it in items if it.category != CAT_GEM]
        # Spend the limited search budget on the most valuable items first.
        prio = {CAT_UNIQUE: 0, CAT_RARE: 1, CAT_MAGIC: 2}
        non_gems.sort(key=lambda it: prio.get(it.category, 3))
        n = len(non_gems)
        for idx, it in enumerate(non_gems, 1):
            self._emit(f"[{idx}/{n}] pricing {it.display_name} ({it.category})...")
            if self.client.search_count >= SEARCH_BUDGET:
                results.append(PriceResult(
                    item=it, method="skipped", confidence="none",
                    note="skipped to stay within trade rate limits",
                    trade_url=self._skip_trade_url(it)))
                continue
            if it.category == CAT_UNIQUE:
                results.append(self.price_unique(it))
            elif it.category == CAT_RARE:
                results.append(self.price_rare(it))
            elif it.category == CAT_MAGIC:
                results.append(self.price_magic(it))
            else:  # normal / unknown
                results.append(PriceResult(item=it, method="none",
                               note="normal item; not priced", confidence="none"))
        for g in gems:                       # gems price off poe.ninja (no trade search budget)
            results.append(self.price_skill(g))
        return results
