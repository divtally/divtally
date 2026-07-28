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
                 trade_query (scoped to the item CATEGORY by default per D-0016, exact base
                 available; require every searchable affix + defence totals + links) and its
                 clickable trade_url, for the extension to execute client-side.
  * magic     -> NOT priced (cheap); carries a category-scoped trade_query + trade_url
                 (exact base available), no affix filters.

The pure query-construction methods are ported verbatim from bpc/pricing.py, with
`self.client.league` -> `self.league` (there is no TradeClient). Trade-search methods
(`_search_listings`, `price_unique`, `price_rare`, `price_magic`, ...) are intentionally
NOT ported -- they would call the trade API.
"""
import json
import urllib.parse
from typing import Dict, List, Optional, Tuple

from . import util, variantreg
from .models import (CAT_GEM, CAT_MAGIC, CAT_RARE, CAT_UNIQUE, Item,
                     PriceResult, PriceTier)
from .statmap import StatMapper, is_local_defence, _score

# ---- module-level constants / helpers (VERBATIM from bpc/pricing.py) -------------------
_ARMOUR_INV = {"Helm", "BodyArmour", "Gloves", "Boots", "Offhand"}

_PSEUDO_ELEM_RES = "pseudo.pseudo_total_elemental_resistance"
_PSEUDO_CHAOS_RES = "pseudo.pseudo_total_chaos_resistance"

# itemData.inventoryId -> trade `type_filters.category` option id. D-0016: this is now the
# DEFAULT search scope for rares/magic (generic "Item Category"), with the exact base type as
# the user-selectable alternative -- it used to be only a fallback when the base was unknown.
# Every id here is present in the trade data/filters "Item Category" option list (source of
# truth research/data/trade_data_filters.json; _verify.py asserts it). None invented.
_INVENTORY_CATEGORY = {
    "Helm": "armour.helmet", "BodyArmour": "armour.chest", "Gloves": "armour.gloves",
    "Boots": "armour.boots", "Belt": "accessory.belt", "Amulet": "accessory.amulet",
    "Ring": "accessory.ring", "Ring2": "accessory.ring", "Offhand": "armour.shield",
    "Offhand2": "armour.shield", "Weapon": "weapon", "Weapon2": "weapon",
    "Jewel": "jewel", "PassiveJewels": "jewel", "Flask": "flask",
}

# D-0016 refinements that narrow the generic slot->category WITHOUT inventing an id (every id
# below is in the source filters list; _verify.py asserts it):
#
#  * Weapons: the inventory slot only says "Weapon", so the specific class is [INFERRED] from
#    the base type's last word. GGG's items endpoint groups every weapon under one "Weapons"
#    label, so the base name is the only weapon-class signal in bundled data. ONLY suffixes
#    that are unambiguously one trade category are mapped (verified against the full base
#    list: every "* Wand"/"* Bow"/"* Sceptre"/"* Claw" base is that class and nothing else
#    is). Ambiguous classes stay generic "weapon" -- sword/axe/mace/staff/maul/dagger et al.
#    can't be told one- vs two-handed (or base vs rune/war variant) from the base name; and
#    "* Rod" is mixed (fishing rods AND non-rods), so it is not mapped. Unmapped list ->
#    docs/notes-v2-api.md. Generic "weapon" is always a CORRECT (broader) scope for a weapon.
_WEAPON_SUFFIX_CATEGORY = {
    "Wand": "weapon.wand", "Bow": "weapon.bow",
    "Sceptre": "weapon.sceptre", "Claw": "weapon.claw",
}

# id -> the "Item Category" option display text, VERBATIM from research/data/
# trade_data_filters.json (source of truth; _verify.py asserts every label matches). Covers
# exactly the ids _category_option can emit; used only for the `scopes` picker labels.
_CATEGORY_LABEL = {
    "weapon": "Any Weapon", "weapon.wand": "Wand", "weapon.bow": "Bow",
    "weapon.sceptre": "Sceptre", "weapon.claw": "Claw",
    "armour.helmet": "Helmet", "armour.chest": "Body Armour", "armour.gloves": "Gloves",
    "armour.boots": "Boots", "armour.shield": "Shield", "armour.quiver": "Quiver",
    "accessory.belt": "Belt", "accessory.amulet": "Amulet", "accessory.ring": "Ring",
    "jewel": "Any Jewel", "flask": "Flask",
}


def _weapon_subcategory(base_type: str) -> Optional[str]:
    """A specific weapon.* category for a weapon base, or None to keep the generic 'weapon'.
    [INFERRED] from the base name's last word (see _WEAPON_SUFFIX_CATEGORY)."""
    if not base_type:
        return None
    return _WEAPON_SUFFIX_CATEGORY.get(base_type.split()[-1])


def _is_quiver(base_type: str) -> bool:
    """Whether an Offhand base is a quiver (vs a shield): every quiver base ends in 'Quiver'
    and nothing else does, so slot->armour.shield must be redirected to armour.quiver."""
    return bool(base_type) and base_type.split()[-1] == "Quiver"

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


def _affix_defaults(value, negated: bool) -> Tuple[Optional[float], Optional[float]]:
    """The picker's prefilled (min, max) for one affix -- mirrors bpc/web.py affixRow():
    a normal roll prefills MIN = the item's value; a negated ('reduced') roll carries a
    NEGATIVE value on the opposite-polarity stat and prefills MAX instead (better = more
    negative, so a min filter would be a near no-op). Returns (default_min, default_max),
    at most one of which is set. The picker consumes these directly; the raw `value` (the
    item's roll, signed) is still carried alongside."""
    if value is None:
        return None, None
    neg = bool(negated) or (isinstance(value, (int, float)) and value < 0)
    return (None, value) if neg else (value, None)


def _res_fold_members(affixes: List[dict]) -> Tuple[List[dict], List[dict]]:
    """Which of an item's built affixes fold into the elemental- vs chaos-resistance pseudo
    totals -- the SAME bucketing res_contributions() sums (an 'all Elemental' mod feeds the
    elemental total; an 'all Resistances' mod feeds BOTH elemental and chaos; a single-element
    mod feeds elemental; a chaos mod feeds chaos). Each member = {index (position in `affixes`),
    text, stat_id, value}; `index` lets a picker grey out exactly the individual resistance
    rows it folded into the total. Returns (elemental_members, chaos_members)."""
    import re
    elem: List[dict] = []
    chaos: List[dict] = []
    for idx, a in enumerate(affixes):
        if not a.get("resist"):
            continue
        t = (a.get("text") or "").lower()
        member = {"index": idx, "text": a.get("text"), "stat_id": a.get("stat_id"),
                  "value": a.get("value")}
        if "all elemental resist" in t:
            elem.append(member)
        elif re.search(r"\ball resistances?\b", t) and "elemental" not in t:
            elem.append(member)
            chaos.append(member)
        else:
            if "fire" in t or "cold" in t or "lightning" in t:
                elem.append(member)
            if "chaos" in t:
                chaos.append(member)
    return elem, chaos


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
        self.status = status if status in self.STATUS_OPTIONS else "available"

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

    # ---- rare scopes / affixes -------------------------------------------
    def _category_option(self, item: Item) -> Optional[str]:
        """The trade `type_filters.category` option id for this item's inventory slot, refined
        to a specific weapon class / to armour.quiver where derivable (see the module notes).
        None when the slot maps to no category (then the exact base type is the only scope)."""
        cat = _INVENTORY_CATEGORY.get(item.raw.get("inventoryId", ""))
        if not cat:
            return None
        if cat == "weapon":
            return _weapon_subcategory(item.base_type) or cat
        if cat == "armour.shield" and _is_quiver(item.base_type):
            return "armour.quiver"
        return cat

    def _rare_scopes(self, item: Item) -> List[Tuple[dict, str]]:
        """Both search scopes for a rare/magic item, DEFAULT FIRST. D-0016: the default is the
        generic item CATEGORY (type_filters.category.option) whenever the slot maps to one; the
        exact base `type` is the fallback default (when no category maps) AND the user-
        selectable alternative. Order is [category, base] when both exist, else whichever
        resolves. Consumers use scopes[0] as the default query/url scope."""
        scopes: List[Tuple[dict, str]] = []
        cat = self._category_option(item)
        if cat:
            scopes.append(({"filters": {"type_filters": {"filters":
                           {"category": {"option": cat}}}}}, "category"))
        btype = self.resolve_type(item.base_type)
        if btype:
            scopes.append(({"type": btype}, "base"))
        return scopes

    def scope_choices(self, item: Item) -> dict:
        """The rares[].scopes payload (docs/public-contract.md 2.6.1): BOTH search scopes so a
        picker can offer the choice. `category` = the D-0016 default (generic, e.g. weapon.wand),
        null when the slot maps to no category; `base` = the exact-base alternative, null only
        when the base isn't a recognised trade type. Labels are the source filters' display
        text (category) / the base type itself (base)."""
        cat = self._category_option(item)
        btype = self.resolve_type(item.base_type)
        category = {"id": cat, "label": _CATEGORY_LABEL.get(cat, cat)} if cat else None
        base = {"type": btype, "label": btype} if btype else None
        return {"category": category, "base": base}

    @staticmethod
    def _apply_defining(row: dict, locked: dict) -> None:
        """Overlay a variant-DEFINING mod's exact search value onto its picker row: the base
        stat id, an `option` for OPTION stats (Allocates X / ring size / keystone radius), or
        an EXACT prefill for seed/socket-count stats -- signalled by `exact:true` (search
        min==max=default_min), the min=max mode the base picker lacked (audit sec 3). Keeps the
        '<=1 prefilled bound' contract invariant intact (default_max stays null)."""
        sid = locked.get("stat_id")
        if sid:
            row["stat_id"] = sid
            row["searchable"] = True
            row["prefer"] = True     # a defining mod is ticked + required by default
            row["reason"] = ""       # it IS searchable (via the resolved base/option/exact id)
        val = locked.get("value") or {}
        if "option" in val:
            row["option"] = val["option"]
            row["default_min"] = row["default_max"] = None
        elif "min" in val and val.get("min") == val.get("max"):
            row["default_min"] = val["min"]
            row["default_max"] = None
            row["exact"] = True
        elif "min" in val:
            row["default_min"] = val["min"]
            row["default_max"] = None
        elif "max" in val:
            row["default_max"] = val["max"]
            row["default_min"] = None

    def affix_options(self, item: Item) -> dict:
        """The item's mods/defences as picker-ready search options (docs/public-contract.md
        `rares[].affixes` / `.pseudo`). Each entry carries `group` (the mod's trade stat group:
        explicit/crafted/fractured/enchant/...) and `default_min`/`default_max` (the value the
        picker prefills, mirroring bpc/web.py affixRow) in addition to the raw signed `value`.
        Unsearchable mods are INCLUDED with searchable:false (D-0015: the user sees every affix;
        the tool hides nothing)."""
        is_armour = bool(item.defences) or item.raw.get("inventoryId", "") in _ARMOUR_INV
        is_unique = item.category == CAT_UNIQUE
        # D-0019: for a variant-registered unique, the copy's variant-DEFINING mods are marked
        # required + prefilled with the exact search value (option / exact seed-count / roll),
        # so the picker highlights them instead of blanket-skipping every unique mod.
        var = self._variant_for(item) if is_unique else None
        locked = (var.get("locked_by_idx") if var else None) or {}
        affixes = []
        for i, line in enumerate(item.explicit_mods):
            is_def = i in locked
            if is_armour and is_local_defence(line) and not is_def:
                continue
            src = item.mod_src[i] if i < len(item.mod_src) else None
            grp = "enchant" if src == "enchant" else None
            sid, neg = self.mapper.match(line, group=grp)
            ok = bool(sid)
            v = util.first_number(line)
            if ok and neg and v is not None:
                v = -abs(v)
            prefer = ok and ((not is_unique) or _is_skill_level_mod(line) or is_def)
            label = util.strip_rich(line).strip()
            if src == "enchant":
                label += " (enchant)"
            # prefill (min/max) only for searchable affixes -- an unsearchable mod has no
            # filter to prefill (the picker greys it out); `value` still carries its roll.
            dmin, dmax = _affix_defaults(v, bool(ok and neg)) if ok else (None, None)
            row = {
                "kind": "stat", "text": label,
                "stat_id": sid if ok else None, "value": v,
                "default_min": dmin, "default_max": dmax,
                "searchable": ok, "resist": _is_res_affix(line), "negated": bool(ok and neg),
                "group": src or "explicit",
                "prefer": prefer,
                "priority": "required" if is_def else _affix_tier(line, ok, is_unique),
                "defining": bool(is_def),
                "reason": "" if ok else "no trade filter matches this mod",
            }
            if is_def:
                self._apply_defining(row, locked[i])
            affixes.append(row)
        for key, val in item.defences.items():
            if val and val > 0:
                affixes.append({"kind": "equip", "key": key, "stat_id": None,
                                "text": _DEF_LABEL.get(key, key), "value": int(val),
                                "default_min": int(val), "default_max": None,
                                "searchable": True, "resist": False, "negated": False,
                                "group": "equip", "prefer": not is_unique, "defining": False,
                                "priority": "skip" if is_unique else "required", "reason": ""})
        c = res_contributions(item.explicit_mods)
        elem_members, chaos_members = _res_fold_members(affixes)
        pseudo = []
        if c["elemental"] > 0:
            tot = round(c["elemental"])
            pseudo.append({"kind": "stat", "text": "+#% total Elemental Resistance",
                           "stat_id": _PSEUDO_ELEM_RES, "value": tot,
                           "default_min": tot, "default_max": None,
                           "searchable": True, "resist": True, "negated": False,
                           "group": "pseudo", "folds": elem_members, "prefer": not is_unique,
                           "defining": False,
                           "priority": "skip" if is_unique else "required", "reason": ""})
        if c["chaos"] > 0:
            tot = round(c["chaos"])
            pseudo.append({"kind": "stat", "text": "+#% total to Chaos Resistance",
                           "stat_id": _PSEUDO_CHAOS_RES, "value": tot,
                           "default_min": tot, "default_max": None,
                           "searchable": True, "resist": True, "negated": False,
                           "group": "pseudo", "folds": chaos_members, "prefer": not is_unique,
                           "defining": False,
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
        # D-0015 (supersedes D-0014's auto-relax, owner veto): the default requires ALL of the
        # item's affixes - the tool NEVER silently excludes an affix the user didn't exclude.
        # Affix selection belongs to the USER via the per-rare picker (advanced mode).
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

    def _variant_for(self, item: Item):
        """The VariantResult for a registry unique (D-0019), or None. Recomputed on demand
        (cheap, stateless); price_unique_ninja + affix_options both call it so the picker's
        defining flags and the built query always agree."""
        if item.category != CAT_UNIQUE or not item.name:
            return None
        entry = variantreg.lookup(item.name, item.base_type)
        if not entry:
            return None
        return variantreg.build_variant(item, entry, self.mapper)

    # ---- trade query builders (built, never executed) --------------------
    def _unique_query(self, item: Item, var=None) -> dict:
        """Name + base (+ links) (+ build's skill-level rolls) (+ D-0019 variant-defining
        filters) -- the query the extension runs to price/verify this unique on the user's
        machine. `var` (a VariantResult) ADDS the REQUIRED defining-mod filters for a
        variant-registered unique (option-split / exact seed / exact count / aura roll-min /
        own-rolls); D-0015: purely additive over the previous name+base+skill-level query."""
        vfilters = self._unique_value_filters(item)
        if var:
            have = {f.get("id") for f in vfilters}
            for f in var.get("filters", []):
                if f.get("id") and f["id"] not in have:
                    have.add(f["id"])
                    vfilters.append(f)
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
        """Magic items: the D-0016 DEFAULT category scope (base type as fallback), no affix
        filters (magic items are cheap - the scope alone is the search). Same scope selection
        as the rare default so the trade link / autoscan agree."""
        scopes = self._rare_scopes(item)
        if not scopes:
            return None
        return self._rare_query(item, scopes[0][0], [], {})

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

    # ---- unique pricing (poe.ninja by name; registry-aware per D-0019) ---
    def price_unique_ninja(self, item: Item) -> PriceResult:
        r = PriceResult(item=item, method="unique-ninja")
        econ = self._econ()
        var = self._variant_for(item)
        query = self._unique_query(item, var) if item.name else None
        self._attach_query(r, query)
        if var:
            # additive item-row variant block (docs/public-contract.md 2.8): what makes this a
            # variant, a human label, and the locked defining stats (the required trade filters).
            r.extra["variant_info"] = {"class": var["cls"], "label": var["label"],
                                       "locked_stats": var["locked_stats"]}
        if not item.name or not econ:
            r.method = "unique-unpriced"
            r.confidence = "none"
            r.note = ("no poe.ninja economy available; price via the trade link"
                      if item.name else "unnamed unique; price via the trade link")
            r.extra["source"] = "none"
            return r
        mod_text = " ".join(item.explicit_mods or [])
        reg_rule = var["ninja_rule"] if var else None
        owned_count = var["owned_count"] if var else None
        m = econ.unique_price(item.name, mod_text=mod_text, base_type=item.base_type,
                              reg_rule=reg_rule, owned_count=owned_count)
        if not m:
            r.method = "unique-unpriced"
            r.confidence = "none"
            # D-0019: a registry variant whose exact owned variant isn't on poe.ninja is
            # UNPRICED + link -- never a cheapest-any-variant number.
            r.note = ("couldn't match your exact variant on poe.ninja; price it on your "
                      "machine via the trade link" if var else
                      "not listed on poe.ninja; price it on your machine via the trade link")
            r.extra["source"] = "none"
            return r
        r.tier = PriceTier(minimum=m["chaos_min"], median=m["chaos_median"], high=m["chaos_high"])
        r.total_found = m.get("count") or 0
        r.sample_size = 1
        r.extra["source"] = "poe.ninja"
        r.extra["listing_count"] = m.get("listing_count") or 0
        r.extra["n_variants"] = m.get("n_variants") or 1
        r.extra["variant"] = m.get("variant") or ""
        cap = var["cap"] if var else None
        matched = m.get("matched")
        if matched == "floor":
            # registry floor-only class (timeless seed / Allocates notable / roll-defined):
            # poe.ninja can't split the variant, so its one aggregate line is a LOW-confidence
            # floor; the exact-variant trade search (this row's trade_query) is the real price.
            r.method = "unique-ninja-floor"
            r.confidence = cap or "low"
            r.note = ("poe.ninja lists one aggregate line for this name -- a low-confidence "
                      "FLOOR across all variants (min of the range); price your exact variant "
                      "via the trade link")
        elif matched == "variant":
            r.method = "unique-ninja-variant"
            lc = m.get("listing_count") or 0
            r.confidence = cap or ("high" if lc >= 5 else "medium")
            r.note = f"poe.ninja price for variant '{m.get('variant')}'"
            if var and not var["label"] and m.get("variant"):
                r.extra["variant_info"]["label"] = m.get("variant")
        elif matched == "range":
            r.method = "unique-ninja-range"
            r.confidence = "low"
            r.note = (f"{m.get('n_variants')} variants on poe.ninja; showing the price "
                      "range (min..high) - exact roll unclear, verify via the trade link")
        else:  # "name"
            r.method = "unique-ninja"
            r.confidence = cap or self._confidence_from_lc(m.get("listing_count") or 0)
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
