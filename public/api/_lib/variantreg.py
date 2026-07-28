"""Variant-unique registry -> defining trade filters (D-0019).

The registry (`_data/variant_uniques.json`, built offline by `tools/build_variant_registry.py`
from primary poe.ninja + trade-schema data) tells us, for each price-variant-sensitive unique,
how to turn *the build's own copy* into a faithful trade search and how to map it onto
poe.ninja's enumeration. This module is the RUNTIME consumer of that artifact:

  * `lookup(name, base_type)`  -> the registry entry for a unique, or None.
  * `build_variant(item, entry, mapper)` -> a VariantResult: the REQUIRED defining-mod trade
    filters (option-split / exact seed / exact count / aura roll-min / own-rolls), the item
    mod indices that are defining (so the picker can highlight them), a human label, the owned
    count (for socket-count ninja mapping), and the ninja/confidence policy passed through.

D-0015 compliance: every filter here is ADDITIVE. Uniques previously carried an EMPTY stat
group; this only ADDS the variant-defining filters (it never removes a mod the user kept),
making a variant search MORE faithful to the exact item.

No network, no pathofexile.com. The option-child index and every stat id are resolved against
the same bundled `trade_stats.json` the StatMapper uses (`refdata`), so a filter we emit is
always a real trade stat id. Recipes are grounded in `docs/research/variant-stats.md` (all
[SRC]) and `docs/research/timeless-jewels.md`; see `docs/notes-variant-querybuild.md`.
"""
import re
from typing import Dict, List, Optional, Tuple

from . import refdata, util

# ---- registry load / lookup -----------------------------------------------------------
_registry: Optional[Dict[str, List[dict]]] = None       # name_lc -> [entry, ...]
_option_axis_cache: Dict[str, Tuple[Dict[int, str], Dict[int, str]]] = {}  # base_id -> (disp, lc)

_WS = re.compile(r"\s+")


def _norm_keepcase(s: str) -> str:
    """Rich markup stripped, whitespace/newlines collapsed, case PRESERVED (for display)."""
    return _WS.sub(" ", util.strip_rich(s or "")).strip()


def _registry_index() -> Dict[str, List[dict]]:
    global _registry
    if _registry is None:
        idx: Dict[str, List[dict]] = {}
        for e in (refdata.variant_data().get("items") or []):
            nm = (e.get("name") or "").strip().lower()
            if nm:
                idx.setdefault(nm, []).append(e)
        _registry = idx
    return _registry


def lookup(name: str, base_type: str = "") -> Optional[dict]:
    """The registry entry for a unique `name` (optionally disambiguated by `base_type` when a
    name has entries on several bases), or None when the unique is not variant-registered."""
    if not name:
        return None
    entries = _registry_index().get(name.strip().lower())
    if not entries:
        return None
    if len(entries) == 1:
        return entries[0]
    bt = (base_type or "").strip().lower()
    if bt:
        for e in entries:
            if bt in [(b or "").strip().lower() for b in (e.get("base") or [])]:
                return e
    return entries[0]


# ---- option-stat child index (base|opt -> axis name) ----------------------------------
def _option_axes(base_id: str) -> Tuple[Dict[int, str], Dict[int, str]]:
    """For a pre-flattened OPTION base id (`explicit.stat_X`), map each option int -> its
    DISTINGUISHING axis name, by stripping the boilerplate shared across all its `base|opt`
    children. Returns (display_case, lowercase) maps. The lowercase map is matched against the
    item's mod text; the display map supplies the human label. Robust to the item's own mod
    text diverging from the schema text (the 'if you have the matching modifier on ...' clause
    or 'Passive Skills'/'Passives'/'Passage' wording): only the axis name has to be a substring
    of the item line. Cached per base id."""
    if base_id in _option_axis_cache:
        return _option_axis_cache[base_id]
    kids: Dict[int, str] = {}
    prefix = base_id + "|"
    for grp in refdata.stats_data().get("result", []):
        for e in grp.get("entries", []):
            sid = e.get("id", "")
            if sid.startswith(prefix):
                try:
                    opt = int(sid.split("|", 1)[1])
                except (ValueError, IndexError):
                    continue
                kids[opt] = _norm_keepcase(e.get("text", ""))
    disp: Dict[int, str] = {}
    lc: Dict[int, str] = {}
    texts = list(kids.values())
    if texts:
        pre = _common_prefix(texts)
        suf = _common_suffix(texts)
        for opt, t in kids.items():
            core = t[len(pre): len(t) - len(suf)] if (len(pre) + len(suf)) < len(t) else t
            core = core.strip()
            if core:
                disp[opt] = core
                lc[opt] = core.lower()
    _option_axis_cache[base_id] = (disp, lc)
    return disp, lc


def _common_prefix(texts: List[str]) -> str:
    pre = texts[0]
    for t in texts[1:]:
        i = 0
        while i < len(pre) and i < len(t) and pre[i] == t[i]:
            i += 1
        pre = pre[:i]
        if not pre:
            break
    return pre


def _common_suffix(texts: List[str]) -> str:
    suf = texts[0]
    for t in texts[1:]:
        i = 0
        while i < len(suf) and i < len(t) and suf[-1 - i] == t[-1 - i]:
            i += 1
        suf = suf[len(suf) - i:] if i else ""
        if not suf:
            break
    return suf


def _resolve_option(item, base_id: str) -> Optional[Tuple[int, str, int]]:
    """Find the (option_int, display_axis, item_mod_index) for the item's copy of an OPTION
    variant. Scans the item's mods; the winning axis is the LONGEST axis-name substring found
    (disambiguates e.g. Thread of Hope 'Large' vs 'Very Large')."""
    disp, lc = _option_axes(base_id)
    if not lc:
        return None
    best: Optional[Tuple[int, str, int]] = None
    best_len = -1
    for idx, mod in enumerate(item.explicit_mods):
        line = _norm_keepcase(mod).lower()
        if not line:
            continue
        for opt, ax in lc.items():
            if ax and ax in line and len(ax) > best_len:
                best = (opt, disp.get(opt, ax), idx)
                best_len = len(ax)
    return best


# ---- per-mod matching helpers ---------------------------------------------------------
def _mod_group(item, idx: int) -> Optional[str]:
    """The StatMapper group to scope mod `idx` in (enchant mods must not fall back to explicit)."""
    src = item.mod_src[idx] if idx < len(item.mod_src) else None
    return "enchant" if src == "enchant" else None


def _match_id(mapper, text: str, group: Optional[str]):
    return mapper.match(text, group=group)


def _sublines(mod: str) -> List[str]:
    """Timeless jewels bundle the seed line and the 'Conquered by ...' line into ONE explicit
    mod joined by a newline; split so each is matched on its own."""
    return [s.strip() for s in str(mod).split("\n") if s.strip()]


# ---- the builder ----------------------------------------------------------------------
class VariantResult(dict):
    """Thin dict wrapper (JSON-friendly): keys class, label, locked_stats, locked_idx,
    filters, owned_count, ninja_rule, cap, defining_rule."""


def build_variant(item, entry: dict, mapper) -> VariantResult:
    """Turn the build's own copy of a registry unique into its REQUIRED defining trade filters
    plus the metadata the pricer/response/ picker need. Never raises; a copy whose defining mod
    can't be resolved degrades to filters=[] (name+base search) with a class-appropriate label."""
    cls = entry.get("class", "")
    defining = entry.get("defining", []) or []
    rule = entry.get("defining_rule")
    filters: List[dict] = []
    locked_idx: set = set()
    locked_stats: List[dict] = []
    locked_by_idx: Dict[int, dict] = {}
    label = ""
    owned_count: Optional[int] = None
    seen_ids: set = set()

    def add(sid, value, text, idx):
        if not sid or sid in seen_ids:
            return
        seen_ids.add(sid)
        f = {"id": sid}
        if value:
            f["value"] = value
        filters.append(f)
        locked_stats.append({"stat_id": sid, "value": value or None, "text": text})
        if idx is not None:
            locked_idx.add(idx)
            locked_by_idx[idx] = {"stat_id": sid, "value": value or None}

    if cls == "notable-jewel":
        parts = []
        for d in defining:
            if d.get("kind") != "option":
                continue
            base = d.get("stat_id")
            got = _resolve_option(item, base)
            if got:
                opt, axis, idx = got
                add(base, {"option": opt}, "Allocates " + axis, idx)
                parts.append(axis)
        label = " + ".join(parts) if parts else "variant"

    elif cls == "seed-jewel":
        seed_map = {d.get("stat_id"): d for d in defining if d.get("kind") == "seed"}
        done = False
        for idx, mod in enumerate(item.explicit_mods):
            if done:
                break
            for sub in _sublines(mod):
                sid, _neg = _match_id(mapper, sub, "explicit")
                if sid in seed_map:
                    n = util.first_number(sub)
                    if n is not None:
                        N = int(n)
                        add(sid, {"min": N, "max": N}, _norm_keepcase(sub), idx)
                        conq = seed_map[sid].get("conqueror") or ""
                        label = (conq + " seed " if conq else "seed ") + str(N)
                        owned_count = N
                        done = True
                        break
        if not label:
            label = "seed variant"

    elif cls == "socket-defined":
        parts = []
        for d in defining:
            target = d.get("stat_id")
            found = None
            for idx, mod in enumerate(item.explicit_mods):
                for sub in _sublines(mod):
                    sid, _neg = _match_id(mapper, sub, _mod_group(item, idx))
                    if sid == target:
                        n = util.first_number(sub)
                        if n is not None:
                            found = (int(n), idx)
                            break
                if found:
                    break
            if found:
                N, idx = found
                axis = (d.get("axis") or "").replace("-", " ").title()
                add(target, {"min": N, "max": N}, "%d %s" % (N, axis) if axis else str(N), idx)
                owned_count = N if owned_count is None else owned_count
                parts.append("%d %s" % (N, axis) if axis else str(N))
        label = " + ".join(parts) if parts else "count variant"

    elif cls in ("roll-defined", "mod-variant"):
        # def_ids = each defining entry's representative stat_id PLUS any serialised family_ids
        # (build_variant_registry serialise_family_ids=True). A mod-variant family whose copy
        # names a SPECIFIC member -- The Light of Meaning's "Passive Skills in Radius also grant
        # X" -- is matched by that member's own id, which the rep id alone would miss (D-0019
        # MAJOR r1-1). Entries without family_ids are unchanged (def_ids == the stat_ids set).
        def_ids: set = set()
        for d in defining:
            sid = d.get("stat_id")
            if sid:
                def_ids.add(sid)
            def_ids.update((d.get("from") or {}).get("family_ids") or [])
        is_presence = any((d.get("from") or {}).get("emit") == "presence" for d in defining)
        # resolve every searchable explicit mod once
        resolved = []       # (idx, sid, roll, text, neg)
        for idx, mod in enumerate(item.explicit_mods):
            grp = _mod_group(item, idx)
            sid, neg = _match_id(mapper, mod, grp)
            if not sid:
                continue
            roll = util.first_number(mod)
            if neg and roll is not None:
                roll = -abs(roll)
            resolved.append((idx, sid, roll, _norm_keepcase(mod), neg))

        # Dispatch by the family's emit + the copy's actual mods, NOT by a blanket
        # "family-all" flag: EVERY roll-defined/mod-variant family carries
        # from.match == "family-all", so testing that first shadowed the presence and def-id
        # branches (dead code) and forced non-aura families (Megalomaniac, Aul's Uprising, The
        # Light of Meaning, Vessel of Vinktar) into the aura branch -- dropping their defining
        # filters and mislabelling them "aura variant" (D-0019 MAJOR-1). Correct order:
        #   * emit == presence          -> the '1 Added Passive Skill is <Notable>' flags
        #   * a real 'while affected by' aura mod IS on the copy -> the aura branch (Watcher's
        #     Eye / Sublime Vision / Circle-of-X heralds / Doryani's Delusion element pen)
        #   * else the copy's mods that resolve to a DEFINING id (The Light of Meaning; a
        #     reservation/lightning copy that names the representative mod)
        #   * else (roll-defined) the copy's own rolls -- never a name-only unique search.
        aura_mods = [r for r in resolved if "while affected by" in r[3].lower()]
        picked = []
        if is_presence:
            picked = [r for r in resolved if "added passive skill is" in r[3].lower()]
            names = [_after(r[3], "Added Passive Skill is") for r in picked]
            names = [n for n in names if n]
            label = ", ".join(names) if names else "notable variant"
        elif aura_mods:
            picked = aura_mods
            auras = [_aura_name(r[3]) for r in picked]
            auras = [a for a in auras if a]
            label = ("affected by " + ", ".join(dict.fromkeys(auras))) if auras else "aura variant"
        elif def_ids:
            picked = [r for r in resolved if r[1] in def_ids]
            label = picked[0][3] if picked else ""

        if not picked and rule in ("own-explicit-rolls", None) and cls == "roll-defined":
            # fall back to the copy's OWN searchable rolls -- never a name-only search for a
            # roll-defined unique (Split Personality / That Which Was Taken; Aul's Uprising and
            # any other family whose copy doesn't name the representative defining id)
            picked = resolved
            if not label:
                label = "rolled variant"

        for idx, sid, roll, text, neg in picked:
            val = {}
            if roll is not None:
                if neg:
                    val = {"max": int(roll)} if float(roll).is_integer() else {"max": roll}
                else:
                    val = {"min": int(roll)} if float(roll).is_integer() else {"min": roll}
            add(sid, val, text, idx)

        if not label:
            # pure ninja mod-variant (Impresence/Mageblood/base-line): priced by the ninja
            # variant LINE, not a fixed filter; the ninja match fills the label.
            label = ""

    _rule = entry.get("ninja_variant_rule") or {}
    return VariantResult(
        cls=cls, label=label, locked_stats=locked_stats, locked_idx=sorted(locked_idx),
        locked_by_idx=locked_by_idx, filters=filters, owned_count=owned_count,
        ninja_rule=_rule, cap=(entry.get("confidence_policy") or {}).get("cap"),
        defining_rule=rule, name=entry.get("name", ""),
    )


def _aura_name(text: str) -> str:
    m = re.search(r"while affected by (.+)$", text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _after(text: str, marker: str) -> str:
    i = text.lower().find(marker.lower())
    return text[i + len(marker):].strip() if i >= 0 else ""
