"""Harvest the AUTHORITATIVE variant-unique list from poe.ninja (Path of Exile 1).

Pulls every PoE1 ``Unique*`` stash item-overview for the current league, dumps the
raw JSON to ``research/data/ninja_uniques_<type>.json``, and enumerates every item
NAME whose price depends on a poe.ninja ``variant`` string (a *mod-variant*), a
``baseType`` (a *base-variant*), and/or a ``links`` count (a *links-variant*).
Writes the findings to ``docs/research/variant-ninja.md`` (regenerable), sorted by
price-spread ratio.

This feeds decision D-0019 (the variant-unique registry): the spread PROVES which
uniques are price-variant-sensitive -- i.e. which ones the pricer MUST search with
the build's own defining mod instead of by name alone.

KEY FINDING (see the doc's sec 5): a non-null ``variant`` is SUFFICIENT to flag a
variant-unique but NOT NECESSARY. The costliest-to-misprice uniques -- Watcher's Eye,
Forbidden Flame/Flesh, the timeless jewels -- carry a NULL ``variant`` (their value is
a rolled mod/seed poe.ninja cannot enumerate) and appear as a single floor line with a
huge ``listingCount``. So the registry cannot be built from this harvest's variant
enumeration alone; those items are curated (KNOWN_MOD_DEFINED) and priced via trade.

poe.ninja ONLY -- this script NEVER touches the pathofexile.com trade API. The
overview endpoint is cheap; we are still polite (real UA + small inter-request
delay), and raw dumps are cached to disk so re-analysis needs no network.

    python research/probe_variants.py             # fetch (disk-cached), analyze, write doc
    python research/probe_variants.py --refresh    # force re-fetch from poe.ninja
    python research/probe_variants.py --league Allflame
    python research/probe_variants.py --no-doc      # analyze + print summary only

Endpoint (docs/research/economy.md):
    GET https://poe.ninja/poe1/api/economy/stash/current/item/overview
        ?league=<Name>&type=<UniqueWeapon|UniqueArmour|...>
    -> {"lines":[ {name, variant, links, baseType, itemType, itemClass,
                   chaosValue, divineValue, exaltedValue, count, listingCount,
                   explicitModifiers, implicitModifiers, ...}, ... ]}
    `variant` = the mod-variant label (or null); `links` = 5/6/... (or null,
    present only on weapons + body armour). Both verified live 2026-07-27.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 buildpricechecker/0.1")
POE1 = "https://poe.ninja/poe1"
INDEX_STATE = POE1 + "/api/data/index-state"
STASH = POE1 + "/api/economy/stash/current/item/overview"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
DOC_PATH = os.path.normpath(os.path.join(HERE, "..", "docs", "research", "variant-ninja.md"))

# Superset of Unique* overview categories to probe. Discovery keeps whichever
# return >0 lines this league; 404 / empty ones are skipped (and reported), so a
# future league that adds e.g. UniqueContract is caught automatically.
CANDIDATE_TYPES = [
    "UniqueWeapon", "UniqueArmour", "UniqueAccessory", "UniqueFlask",
    "UniqueJewel", "UniqueMap", "UniqueRelic", "UniqueTincture",
    "UniqueContract", "UniqueLogbook", "UniqueIncubator",
]

# Curated [INFERRED - domain knowledge, cross-checked vs the OBSERVED dumps] list of
# uniques whose real value is set by a MOD/SEED the item rolls -- NOT by an enumerable
# `variant`. poe.ninja therefore lists each as a single null-`variant` floor line, so
# the harvest's variant-field enumeration CANNOT surface them: they must be curated and
# priced via trade using the build-copy's own defining mod (D-0019). Membership is the
# inference (flagged); every NUMBER shown for them in the doc is [OBSERVED] from the dump.
KNOWN_MOD_DEFINED = {
    "Watcher's Eye": "which per-aura mod combo (2-3 rolled mods) it has",
    "Forbidden Flame": "which ascendancy notable it Allocates (must pair-match the Flesh)",
    "Forbidden Flesh": "which ascendancy notable it Allocates (must pair-match the Flame)",
    "Glorious Vanity": "seed (Vaal era) -> exact keystone/notable transforms in radius",
    "Lethal Pride": "seed (Karui) -> added notables + attributes in radius",
    "Brutal Restraint": "seed (Maraketh) -> added notables + dexterity in radius",
    "Militant Faith": "seed (Templar) -> keystone granted + notable transforms",
    "Elegant Hubris": "seed (Eternal) -> added notables + small-passive effects",
    "Thread of Hope": "ring size (Small..Massive) = which distant passives it can allocate",
    "Impossible Escape": "which keystone it lets you reach past unallocated passives",
    "Sublime Vision": "which single aura's empowering mod it grants",
    "Split Personality": "the two random attribute/defence mods it gains as it levels",
}


# ---- fetch ---------------------------------------------------------------
def session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json",
                      "Referer": "https://poe.ninja/poe1/economy"})
    return s


def resolve_league(s, prefer=None):
    """Return the poe.ninja league *name* to query overviews with.

    index-state.economyLeagues = [{name,url,displayName}]. Default: the first
    entry that is not Standard/Hardcore (the current challenge league); override
    with --league. The `name` field ("Allflame") is what ?league= wants."""
    idx = s.get(INDEX_STATE, timeout=30).json()
    econ = idx.get("economyLeagues", []) or []
    names = [e.get("name", "") for e in econ]
    if prefer:
        for e in econ:
            if e.get("name") == prefer or e.get("url") == prefer:
                return e.get("name"), names
        return prefer, names          # trust the override even if not listed
    for e in econ:
        nm = e.get("name", "")
        if nm and "Standard" not in nm and "Hardcore" not in nm:
            return nm, names
    return (econ[0].get("name") if econ else "Standard"), names


def load_type(s, league, t, refresh):
    """Return (lines, dump_path, status). status in {'fetched','cached','empty','http404'}.
    Dumps raw JSON to research/data/ninja_uniques_<type>.json on a live fetch."""
    path = os.path.join(DATA_DIR, "ninja_uniques_%s.json" % t.lower())
    if os.path.exists(path) and not refresh:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("lines", []) or [], path, "cached"
    try:
        r = s.get(STASH, params={"league": league, "type": t}, timeout=60)
    except requests.RequestException as e:
        print("  %s: network error %s" % (t, e))
        return [], path, "error"
    if r.status_code == 404:
        return [], path, "http404"
    if not r.ok:
        print("  %s: HTTP %s" % (t, r.status_code))
        return [], path, "http%s" % r.status_code
    data = r.json()
    lines = data.get("lines", []) if isinstance(data, dict) else []
    if not lines:
        return [], path, "empty"
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return lines, path, "fetched"


# ---- analysis ------------------------------------------------------------
def _c(ln):
    v = ln.get("chaosValue")
    return v if isinstance(v, (int, float)) and v > 0 else None


def _link(ln):
    L = ln.get("links")
    return int(L) if isinstance(L, (int, float)) and L else 0


def analyze_type(lines, type_label):
    """Group a type's lines by item NAME and compute the variant/links structure
    + isolated spread ratios for each name. Returns {name: record}."""
    by_name = defaultdict(list)
    for ln in lines:
        by_name[ln.get("name", "") or "(unnamed)"].append(ln)

    out = {}
    for name, lns in by_name.items():
        variants = sorted({(ln.get("variant") or "") for ln in lns if ln.get("variant")})
        link_vals = sorted({_link(ln) for ln in lns})
        chaos_all = [_c(ln) for ln in lns if _c(ln) is not None]
        bases = sorted({(ln.get("baseType") or "") for ln in lns if ln.get("baseType")})
        item_type = next((ln.get("itemType") for ln in lns if ln.get("itemType")), "")

        # per-variant chaos min/max (across whatever links that variant appears at)
        var_detail = {}
        for ln in lns:
            key = ln.get("variant") or "(unspecified)"
            c = _c(ln)
            d = var_detail.setdefault(key, {"cmin": None, "cmax": None, "links": set(),
                                            "listings": 0, "div": None})
            if c is not None:
                d["cmin"] = c if d["cmin"] is None else min(d["cmin"], c)
                d["cmax"] = c if d["cmax"] is None else max(d["cmax"], c)
            d["links"].add(_link(ln))
            d["listings"] += int(ln.get("listingCount") or 0)
            dv = ln.get("divineValue")
            if isinstance(dv, (int, float)):
                d["div"] = dv if d["div"] is None else max(d["div"], dv)

        # VARIANT spread -- hold links FIXED (so a body armour's 5L/6L rows do not
        # masquerade as a variant swing). For each link count present, take each
        # variant's best (max) chaos, ratio the dearest vs cheapest variant; keep
        # the widest such ratio across link counts.
        by_link = defaultdict(dict)   # link -> {variant: max chaos}
        for ln in lns:
            c = _c(ln)
            if c is None:
                continue
            L, v = _link(ln), (ln.get("variant") or "(unspecified)")
            by_link[L][v] = max(by_link[L].get(v, 0), c)
        variant_spread = 1.0
        for reps in by_link.values():
            vals = [c for c in reps.values() if c > 0]
            if len(reps) >= 2 and vals:
                variant_spread = max(variant_spread, max(vals) / min(vals))

        # LINKS spread -- hold the variant FIXED. For each variant, take each link
        # count's best chaos, ratio highest-link vs lowest-link; widest across variants.
        by_variant = defaultdict(dict)  # variant -> {link: max chaos}
        for ln in lns:
            c = _c(ln)
            if c is None:
                continue
            L, v = _link(ln), (ln.get("variant") or "(unspecified)")
            by_variant[v][L] = max(by_variant[v].get(L, 0), c)
        links_spread = 1.0
        for reps in by_variant.values():
            if len(reps) >= 2 and max(reps) >= 5:
                vals = [c for c in reps.values() if c > 0]
                if vals:
                    links_spread = max(links_spread, max(vals) / min(vals))

        # BASE-type variant -- some uniques drop on several bases (Precursor's Emblem
        # -> 5 ring bases; Combat Focus / Grand Spectrum -> 3 jewel colours), a THIRD
        # price axis independent of the `variant` field. Representative = max chaos/base.
        base_detail = {}
        for ln in lns:
            b = ln.get("baseType") or "(?)"
            c = _c(ln)
            d = base_detail.setdefault(b, {"cmin": None, "cmax": None})
            if c is not None:
                d["cmin"] = c if d["cmin"] is None else min(d["cmin"], c)
                d["cmax"] = c if d["cmax"] is None else max(d["cmax"], c)
        base_reps = [d["cmax"] for d in base_detail.values() if d["cmax"]]
        base_spread = (max(base_reps) / min(base_reps)) if len(base_detail) >= 2 and base_reps else 1.0

        # per-LINK chaos min/max over the raw lines (var_detail groups by variant and so
        # loses per-link price granularity -- keep this for the section-4 display).
        link_detail = {}
        for ln in lns:
            c = _c(ln)
            if c is None:
                continue
            Lk = _link(ln)
            d = link_detail.setdefault(Lk, {"cmin": c, "cmax": c})
            d["cmin"] = min(d["cmin"], c)
            d["cmax"] = max(d["cmax"], c)

        listings = [int(ln.get("listingCount") or 0) for ln in lns]

        out[name] = {
            "name": name, "type": type_label, "bases": bases, "item_type": item_type,
            "n_lines": len(lns), "variants": variants, "n_variants": len(variants),
            "link_vals": [L for L in link_vals if L],  # drop the 0 (=unlinked/na)
            "has_unlinked": 0 in link_vals,
            "chaos_min": min(chaos_all) if chaos_all else None,
            "chaos_max": max(chaos_all) if chaos_all else None,
            "var_detail": var_detail,
            "link_detail": link_detail,
            "variant_spread": variant_spread,
            "links_spread": links_spread,
            "base_detail": base_detail, "n_bases": len(base_detail), "base_spread": base_spread,
            "max_listings": max(listings) if listings else 0,
            "total_listings": sum(listings),
            "is_foulborn": name.startswith("Foulborn "),
        }
    return out


# ---- markdown rendering --------------------------------------------------
def fmt_c(c):
    if c is None:
        return "-"
    if c >= 1000:
        return "{:,}".format(int(round(c)))
    if c >= 10:
        return "%.0f" % c
    return "%.2f" % c


def fmt_x(r):
    if r is None or r < 1.0000001:
        return "1x"
    if r >= 100:
        return "{:,}x".format(int(round(r)))
    return "%.1fx" % r


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def variants_inline(rec, cap=40):
    """`variant (chaos)` list for one name, dearest first. min-max shown when a
    variant spans link counts."""
    items = []
    for v, d in rec["var_detail"].items():
        items.append((d["cmax"] if d["cmax"] is not None else -1, v, d))
    items.sort(reverse=True)
    parts = []
    for _, v, d in items[:cap]:
        if d["cmin"] is not None and d["cmax"] is not None and d["cmax"] > d["cmin"] * 1.02:
            price = "%s-%s" % (fmt_c(d["cmin"]), fmt_c(d["cmax"]))
        else:
            price = fmt_c(d["cmax"])
        lk = ""
        links = sorted(x for x in d["links"] if x)
        if links:
            lk = " [%s]" % "/".join("%dL" % x for x in links)
        parts.append("%s: %sc%s" % (esc(v), price, lk))
    extra = len(items) - cap
    tail = "  ... +%d more (see raw dump)" % extra if extra > 0 else ""
    return "; ".join(parts) + tail


def render_doc(league, when, type_status, per_type, all_recs):
    L = []
    W = L.append
    W("# poe.ninja PoE1 variant-unique registry (harvested)")
    W("")
    W("**Generated by `research/probe_variants.py`** from LIVE poe.ninja PoE1 economy")
    W("overviews. Do not hand-edit -- re-run the probe to refresh (raw dumps in")
    W("`research/data/ninja_uniques_*.json` are the primary source of every number here).")
    W("")
    W("- **League:** `%s`  |  **Harvested:** %s" % (league, when))
    W("- **Endpoint:** `GET %s?league=%s&type=<Unique*>`" % (STASH, league))
    W("- **Provenance:** every price / variant string / link count below is")
    W("  **[OBSERVED]** in the dumped poe.ninja response. The *classification* and the")
    W("  *spread ratios* are **[DERIVED]** by this script's method (section 0). The")
    W("  `Foulborn` and timeless-jewel *interpretations* are **[INFERRED]** and flagged.")
    W("  No wiki/community claim is used anywhere in this file.")
    W("")
    W("## 0. What this is + method")
    W("")
    W("poe.ninja lists a unique once per **priced variation**. THREE independent axes drive")
    W("that variation; this file keeps them separate exactly as D-0019 requires (the task")
    W("asked for the first two -- the third, `base`, is the same problem and is included):")
    W("")
    W("- **mod-variant** (sec 2) = a distinct value of the line's `variant` field (Impresence's")
    W("  `Chaos` vs `Fire`; Voices' `3 passives`; Doryani's Invitation's `Physical`). Null")
    W("  `variant` = poe.ninja gives the item only one priced form (see the sec 5 caveat).")
    W("- **base-variant** (sec 3) = the same unique NAME dropping on several `baseType`s")
    W("  (Precursor's Emblem on 5 ring bases; Combat Focus / Grand Spectrum on 3 jewel")
    W("  colours). Each base is effectively a different item; `variant` is usually null.")
    W("- **links-variant** (sec 4) = a distinct value of the `links` field (5L / 6L vs")
    W("  unlinked). Present only on weapons + body armours; null for jewels/rings/amulets/")
    W("  flasks/maps/relics/tinctures.")
    W("")
    W("For each item NAME I group all its lines and compute **isolated** spread ratios")
    W("(dearest priced form / cheapest), so one axis never inflates another:")
    W("")
    W("- **variantx** = spread across `variant` values **at a fixed link count** (widest over")
    W("  the link counts present) -- proves \"pick the wrong variant -> wrong price\".")
    W("- **basex** = spread across `baseType`s (best price per base).")
    W("- **linksx** = spread across `links` values **at a fixed variant** -- the 5L/6L gap.")
    W("")
    W("A name is a **variant-unique** (needs a defining filter, per D-0019) when it has >=1")
    W("non-null `variant`, >=2 bases, or >=2 link counts; it is **price-variant-sensitive**")
    W("when the matching `x` ratio > 1. All chaos values are poe.ninja `chaosValue`")
    W("(already chaos; economy.md).")
    W("")
    W("> **The sec 5 blind spot (most important for D-0019):** a non-null `variant` is")
    W("> SUFFICIENT to flag a variant-unique but NOT NECESSARY. The costliest-to-misprice")
    W("> uniques -- **Watcher's Eye, Forbidden Flame/Flesh, the 5 timeless jewels** -- carry")
    W("> a **null** `variant` because their value is a rolled MOD/SEED poe.ninja cannot")
    W("> enumerate, so it lists ONE floor line (with huge listing counts). The registry can")
    W("> NOT be built from this harvest's variant enumeration alone; those items are curated")
    W("> in sec 5 and must be priced via trade using the build's own copy.")
    W("")

    # ---- section 1: types discovered
    W("## 1. Unique* types discovered this league")
    W("")
    W("| Type | Lines | Names | Multi-variant names | Any-variant names | Links-variant names |")
    W("|---|--:|--:|--:|--:|--:|")
    for t in CANDIDATE_TYPES:
        st = type_status.get(t)
        if st in ("http404", None):
            continue
        recs = per_type.get(t, {})
        if not recs and st not in ("fetched", "cached"):
            W("| %s | 0 | 0 | 0 | 0 | 0 |  _(%s)_" % (t, st))
            continue
        multi = sum(1 for r in recs.values() if r["n_variants"] >= 2)
        anyv = sum(1 for r in recs.values() if r["n_variants"] >= 1)
        lk = sum(1 for r in recs.values() if r["links_spread"] > 1.0)
        nlines = sum(r["n_lines"] for r in recs.values())
        W("| %s | %d | %d | %d | %d | %d |" % (t, nlines, len(recs), multi, anyv, lk))
    skipped = [t for t in CANDIDATE_TYPES if type_status.get(t) == "http404"]
    if skipped:
        W("")
        W("_Probed but absent (HTTP 404) this league: %s._" % ", ".join("`%s`" % x for x in skipped))
    W("")

    # ---- section 2: mod-variant tables (durable registry 2a, then Foulborn 2b)
    multi = [r for r in all_recs if r["n_variants"] >= 2]
    multi.sort(key=lambda r: (r["variant_spread"], r["chaos_max"] or 0), reverse=True)
    durable = [r for r in multi if not r["is_foulborn"]]
    fb_multi = [r for r in multi if r["is_foulborn"]]

    def _mod_rows(rows):
        W("| # | Item | Type | # var | variantx | linksx | chaos min-max | Variants (dearest first) |")
        W("|--:|---|---|--:|--:|--:|---|---|")
        for i, r in enumerate(rows, 1):
            flags = " +L" if r["links_spread"] > 1.0 else ""
            rng = "%sc - %sc" % (fmt_c(r["chaos_min"]), fmt_c(r["chaos_max"]))
            W("| %d | %s%s | %s | %d | **%s** | %s | %s | %s |" % (
                i, esc(r["name"]), flags, r["type"].replace("Unique", "U."),
                r["n_variants"], fmt_x(r["variant_spread"]), fmt_x(r["links_spread"]),
                rng, variants_inline(r)))
        W("")

    W("## 2. Mod-variant uniques -- the registry core (%d names)" % len(multi))
    W("")
    W("Every name with >=2 distinct `variant` values, **sorted by `variantx` (price")
    W("sensitivity = dearest variant / cheapest, links held fixed)**. These are the items")
    W("whose build-copy defining mod MUST drive the search (D-0019). `+L` = links **also**")
    W("vary (see sec 4). Split into the DURABLE registry (2a) and the league-transient")
    W("`Foulborn` copies (2b, see sec 6) so the stable list is not buried by league noise.")
    W("")
    W("### 2a. Durable mod-variant uniques (%d) -- THE registry" % len(durable))
    W("")
    _mod_rows(durable)
    W("### 2b. Foulborn league mod-variants (%d) -- transient [INFERRED]" % len(fb_multi))
    W("")
    W("Same structure, but these are this league's `Foulborn` rolled-mod copies (sec 6);")
    W("their extreme `variantx` (a combined-mod roll priced far above a single-mod roll) is")
    W("a league-mechanic artifact, not a durable unique variant. Listed for completeness.")
    W("")
    _mod_rows(fb_multi)

    # ---- section 3: base-type variant table
    bv = [r for r in all_recs if r["n_bases"] >= 2]
    bv.sort(key=lambda r: (r["base_spread"], r["chaos_max"] or 0), reverse=True)
    W("## 3. Base-type-variant uniques (%d names)" % len(bv))
    W("")
    W("One unique NAME that drops on **multiple `baseType`s** -- a price axis independent of")
    W("the `variant` field (usually null here). The trade search must pin the RIGHT base")
    W("(the build copy's), e.g. Precursor's Emblem's resistances follow its ring base.")
    W("`M` = also mod-variant. `F` = Foulborn.")
    W("")
    W("| # | Item | Type | # base | basex | chaos min-max | Bases (dearest first) |")
    W("|--:|---|---|--:|--:|---|---|")
    for i, r in enumerate(bv, 1):
        detail = sorted(((d["cmax"] if d["cmax"] is not None else -1, b, d)
                         for b, d in r["base_detail"].items()), reverse=True)
        cells = []
        for _, b, d in detail:
            cells.append("%s: %sc" % (esc(b), fmt_c(d["cmax"])))
        flags = ""
        if r["n_variants"] >= 2:
            flags += "M"
        if r["is_foulborn"]:
            flags += "F"
        rng = "%sc - %sc" % (fmt_c(r["chaos_min"]), fmt_c(r["chaos_max"]))
        W("| %d | %s%s | %s | %d | **%s** | %s | %s |" % (
            i, esc(r["name"]), (" " + flags if flags else ""),
            r["type"].replace("Unique", "U."), r["n_bases"],
            fmt_x(r["base_spread"]), rng, "; ".join(cells)))
    W("")

    # ---- section 4: links-variant table
    lk = [r for r in all_recs if r["links_spread"] > 1.0]
    lk.sort(key=lambda r: (r["links_spread"], r["chaos_max"] or 0), reverse=True)
    LK_CAP = 60
    W("## 4. Links-variant uniques (%d names; top %d by linksx shown)" % (len(lk), min(LK_CAP, len(lk))))
    W("")
    W("Names whose price swings with the **`links` count** (5L/6L vs unlinked), variant")
    W("held fixed. `M` = mod-variants **also** apply (also in sec 2). Full set (every 5/6-")
    W("socket unique) is in the raw dumps; the engine already adds a links filter for any")
    W("`max_link >= 5` item (D-0003), so this table is about how MUCH links move the price.")
    W("")
    W("")
    W("| # | Item | Type | linksx | Per-link chaos (best) | chaos min-max |")
    W("|--:|---|---|--:|---|---|")
    for i, r in enumerate(lk[:LK_CAP], 1):
        # per-link BEST (max) chaos, straight from link_detail (real per-link prices)
        ld = r["link_detail"]
        cells = []
        if 0 in ld:
            cells.append("unlinked: %sc" % fmt_c(ld[0]["cmax"]))
        for lk_n in sorted(k for k in ld if k):
            cells.append("%dL: %sc" % (lk_n, fmt_c(ld[lk_n]["cmax"])))
        mark = "M" if r["n_variants"] >= 2 else ""
        rng = "%sc - %sc" % (fmt_c(r["chaos_min"]), fmt_c(r["chaos_max"]))
        W("| %d | %s%s | %s | **%s** | %s | %s |" % (
            i, esc(r["name"]), (" " + mark if mark else ""),
            r["type"].replace("Unique", "U."), fmt_x(r["links_spread"]),
            "; ".join(cells), rng))
    W("")

    # ---- section 5: THE BLIND SPOT -- floor-priced mod/seed-defined uniques
    W("## 5. The blind spot -- floor-priced mod/seed-defined uniques (D-0019 core)")
    W("")
    W("The uniques that are **most dangerous to price by name** carry a **null `variant`**")
    W("on poe.ninja, so sec 2 cannot surface them. Their value is a rolled MOD or SEED that")
    W("poe.ninja does not enumerate -- it lists ONE line, whose price is a **floor over a")
    W("heterogeneous bucket**. The data fingerprint is a **null-variant line with a huge")
    W("`listingCount`** (thousands of different real items dumped into one price).")
    W("")
    W("**5a. Curated known mod/seed-defined uniques** -- membership is **[INFERRED -- domain")
    W("knowledge]**; every number is **[OBSERVED]** in the dump. These MUST be priced via")
    W("trade with the build copy's own defining mod/seed, never from the overview:")
    W("")
    W("| Item | Type | Base | ninja `variant` | ninja floor chaos | listings | Real price driver [INFERRED] |")
    W("|---|---|---|---|--:|--:|---|")
    by_name_all = {r["name"]: r for r in all_recs}
    for nm, why in KNOWN_MOD_DEFINED.items():
        r = by_name_all.get(nm)
        if not r:
            W("| %s | _(not priced this league)_ | | | - | - | %s |" % (esc(nm), esc(why)))
            continue
        vlabel = ", ".join(r["variants"]) if r["variants"] else "null (single line)"
        base = r["bases"][0] if r["bases"] else ""
        W("| %s | %s | %s | %s | %sc | %s | %s |" % (
            esc(nm), r["type"].replace("Unique", "U."), esc(base), esc(vlabel),
            fmt_c(r["chaos_max"]), "{:,}".format(r["max_listings"]), esc(why)))
    W("")
    mf = by_name_all.get("Militant Faith")
    mf_txt = ("~%sc across %s listings" % (fmt_c(mf["chaos_max"]), "{:,}".format(mf["max_listings"]))
              ) if mf else "a single line"
    W("The 5 timeless jewels above make the point sharpest: poe.ninja does not even bucket")
    W("them by conqueror -- **one null-variant line each** (e.g. Militant Faith %s)." % mf_txt)
    W("A timeless jewel's worth is its **seed** (which historic conqueror + which exact")
    W("notable transforms/keystone land in its socket radius); two same-name jewels with")
    W("different seeds are different items. D-0019's plan -- search timeless jewels by")
    W("**exact seed (min=max) + keystone**, and Forbidden Flame/Flesh by the **Allocates")
    W("<notable>** mod, and Watcher's Eye by its **rolled aura mods** -- is the only faithful")
    W("path; the overview supplies only a sanity floor. The build's own copy carries the")
    W("seed/mod, so the registry reads it from the character JSON, never from this table.")
    W("")
    W("**5b. Data-ranked candidates** -- every null-`variant`, single-base name sorted by")
    W("`listingCount` (top 30). High liquidity flags a likely heterogeneous floor bucket;")
    W("`*` = confirmed mod/seed-defined (5a). (High liquidity alone is not proof - a cheap")
    W("fixed unique also trades a lot -- so treat unmarked rows as candidates to verify.)")
    W("")
    W("| Item | Type | Base | floor chaos | listings |")
    W("|---|---|---|--:|--:|")
    floor_cands = [r for r in all_recs if r["n_variants"] == 0 and r["n_bases"] <= 1
                   and not r["is_foulborn"]]
    floor_cands.sort(key=lambda r: r["max_listings"], reverse=True)
    for r in floor_cands[:30]:
        mark = " *" if r["name"] in KNOWN_MOD_DEFINED else ""
        base = r["bases"][0] if r["bases"] else ""
        W("| %s%s | %s | %s | %sc | %s |" % (
            esc(r["name"]), mark, r["type"].replace("Unique", "U."), esc(base),
            fmt_c(r["chaos_max"]), "{:,}".format(r["max_listings"])))
    W("")

    # ---- section 6: Foulborn note
    fb = [r for r in all_recs if r["is_foulborn"]]
    W("## 6. Note: the `Foulborn ` name prefix (%d names) -- league-transient [INFERRED]" % len(fb))
    W("")
    W("%d of this league's priced unique NAMES begin with `Foulborn ` (e.g. `Foulborn" % len(fb))
    W("Reefbane`, `Foulborn Skin of the Loyal`). This is **[OBSERVED]** in the raw data as a")
    W("literal name prefix -- a **league mechanic** that mints a modified copy of a base")
    W("unique with its own `variant` label. It is **[INFERRED -- flagged]** that these are")
    W("**transient to the `%s` league** and are NOT stable variants of the underlying" % league)
    W("unique (they group under a *different* name, so they never merge with the base item")
    W("above). Treat them as league noise for a durable registry: the stable variant-unique")
    W("list is the **non-`Foulborn`** rows. Counts excluding Foulborn:")
    W("")
    W("- Multi-variant names (non-Foulborn): **%d**" % sum(
        1 for r in all_recs if r["n_variants"] >= 2 and not r["is_foulborn"]))
    W("- Any-variant names (non-Foulborn): **%d**" % sum(
        1 for r in all_recs if r["n_variants"] >= 1 and not r["is_foulborn"]))
    W("")

    # ---- section 6: single-variant appendix (compact)
    single = [r for r in all_recs if r["n_variants"] == 1]
    single.sort(key=lambda r: (r["is_foulborn"], r["name"]))
    single_fb = sum(1 for r in single if r["is_foulborn"])
    single_nf = len(single) - single_fb
    W("## 7. Appendix -- single labelled-variant names (%d)" % len(single))
    W("")
    W("Names with exactly ONE non-null `variant` (so `variantx = 1` -- not price-sensitive,")
    W("but poe.ninja still labels the form). **%d of these %d are `Foulborn` league copies**"
      % (single_fb, len(single)))
    W("(non-Foulborn = **%d**); the DURABLE single-variant registry is essentially empty this" % single_nf)
    W("league. Listed for completeness / league reference. `F` marks Foulborn names.")
    W("")
    W("| Item | Type | Variant | chaos |")
    W("|---|---|---|--:|")
    for r in single:
        v = r["variants"][0]
        d = r["var_detail"].get(v, {})
        mark = " `F`" if r["is_foulborn"] else ""
        W("| %s%s | %s | %s | %sc |" % (
            esc(r["name"]), mark, r["type"].replace("Unique", "U."),
            esc(v), fmt_c(d.get("cmax"))))
    W("")

    W("## 8. Reproduce")
    W("")
    W("```")
    W("python research/probe_variants.py --refresh   # re-fetch from poe.ninja + rewrite this doc")
    W("```")
    W("Raw per-type dumps: `research/data/ninja_uniques_<type>.json` (the source of truth).")
    W("")
    return "\n".join(L)


def print_summary(league, type_status, per_type, all_recs):
    print("\n=== SUMMARY (league=%s) ===" % league)
    for t in CANDIDATE_TYPES:
        st = type_status.get(t)
        recs = per_type.get(t, {})
        if st == "http404":
            print("  %-16s 404 (absent)" % t)
        elif recs:
            multi = sum(1 for r in recs.values() if r["n_variants"] >= 2)
            lk = sum(1 for r in recs.values() if r["links_spread"] > 1.0)
            print("  %-16s %4d lines  %4d names  %3d multi-variant  %3d links-variant (%s)"
                  % (t, sum(r["n_lines"] for r in recs.values()), len(recs), multi, lk, st))
        elif st:
            print("  %-16s %s" % (t, st))
    multi = [r for r in all_recs if r["n_variants"] >= 2 and not r["is_foulborn"]]
    multi.sort(key=lambda r: (r["variant_spread"], r["chaos_max"] or 0), reverse=True)
    print("\n  TOP 20 mod-variant (NON-Foulborn) by variantx (links held fixed):")
    for r in multi[:20]:
        print("    %-32s %-14s %2d var  variant=%-9s links=%-7s  %s-%s c"
              % (r["name"][:32], r["type"], r["n_variants"], fmt_x(r["variant_spread"]),
                 fmt_x(r["links_spread"]), fmt_c(r["chaos_min"]), fmt_c(r["chaos_max"])))
    bv = [r for r in all_recs if r["n_bases"] >= 2 and not r["is_foulborn"]]
    bv.sort(key=lambda r: r["base_spread"], reverse=True)
    print("\n  TOP 12 base-variant (NON-Foulborn) by basex:")
    for r in bv[:12]:
        print("    %-32s %-14s %d bases  base=%-8s  %s-%s c"
              % (r["name"][:32], r["type"], r["n_bases"], fmt_x(r["base_spread"]),
                 fmt_c(r["chaos_min"]), fmt_c(r["chaos_max"])))
    print("\n  FLOOR blind-spot (null-variant, top by listingCount, non-Foulborn):")
    fc = [r for r in all_recs if r["n_variants"] == 0 and r["n_bases"] <= 1 and not r["is_foulborn"]]
    fc.sort(key=lambda r: r["max_listings"], reverse=True)
    for r in fc[:18]:
        mark = "MOD-DEF" if r["name"] in KNOWN_MOD_DEFINED else ""
        print("    %-30s %-14s floor=%-8s listings=%-7s %s"
              % (r["name"][:30], r["type"], fmt_c(r["chaos_max"]), r["max_listings"], mark))
    fb = sum(1 for r in all_recs if r["is_foulborn"])
    print("\n  Foulborn-prefixed names: %d of %d total names" % (fb, len(all_recs)))


def main():
    ap = argparse.ArgumentParser(description="Harvest poe.ninja PoE1 variant-unique list")
    ap.add_argument("--league", default=None, help="league name/slug (default: current challenge)")
    ap.add_argument("--refresh", action="store_true", help="force re-fetch (ignore disk cache)")
    ap.add_argument("--no-doc", action="store_true", help="analyze + print summary; do not write the .md")
    args = ap.parse_args()

    s = session()
    league, econ_names = resolve_league(s, args.league)
    print("economyLeagues: %s" % ", ".join(econ_names))
    print("using league: %s\n" % league)

    type_status, per_type, all_recs = {}, {}, []
    for t in CANDIDATE_TYPES:
        lines, path, status = load_type(s, league, t, args.refresh)
        type_status[t] = status
        if lines:
            recs = analyze_type(lines, t)
            per_type[t] = recs
            all_recs.extend(recs.values())
            print("  %-16s %-8s %5d lines -> %d names  (%s)"
                  % (t, status, len(lines), len(recs), os.path.basename(path)))
        else:
            print("  %-16s %-8s (skipped)" % (t, status))
        if status == "fetched":
            time.sleep(0.8)          # polite pacing on live fetches only

    print_summary(league, type_status, per_type, all_recs)

    if not args.no_doc:
        when = time.strftime("%Y-%m-%d %H:%M %Z")
        doc = render_doc(league, when, type_status, per_type, all_recs)
        os.makedirs(os.path.dirname(DOC_PATH), exist_ok=True)
        with open(DOC_PATH, "w", encoding="utf-8") as f:
            f.write(doc)
        print("\nwrote %s (%d bytes)" % (DOC_PATH, len(doc.encode("utf-8"))))


if __name__ == "__main__":
    sys.exit(main())
