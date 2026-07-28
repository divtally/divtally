"""Build DivTally's OWN variant-unique database (D-0019).

Owner requirement: the runtime must NOT rely on any internet source at appraisal time.
This tool compiles a committed, regenerable artifact --
``public/api/_data/variant_uniques.json`` -- that tells the pricer, for every
price-variant-sensitive PoE1 unique, exactly how to turn the build's OWN copy into a
faithful trade search (the defining mod / seed / socket-count filter) and how to map it
onto poe.ninja's variant enumeration. At runtime only this JSON is read; no network.

WHAT IT MERGES (source tiers, per D-0019's owner EVIDENCE RULE):
  1. PRIMARY  - poe.ninja Unique* economy overviews (the harvested variant/base/links
     enumeration + floor prices + listing counts; cached raw dumps in
     ``research/data/ninja_uniques_*.json``, refreshable live), AND the bundled trade
     stat schema ``public/api/_data/trade_stats.json`` (every defining stat id / option /
     pseudo-seed id is resolved and VALIDATED against it), AND the bundled item list
     ``research/data/trade_items.json`` (name -> base grounding).
  2. CROSS-CHECK - community-rostered variant items (docs/research/variant-crosscheck.md).
     Each is emitted ONLY IF its defining stat id / family RESOLVES in the primary schema
     (the D-0019 gate: "merge cross-check additions ONLY where a primary-data recipe
     exists"). Cross-check-sourced rows carry their ``[NOT FROM SOURCE - <where>]`` tag.

The recipes themselves come from the primary-source research notes, all [SRC]-graded:
  - docs/research/variant-stats.md  (per-class defining-stat recipes from trade_stats.json)
  - docs/research/timeless-jewels.md (the seed + conqueror recipe; the Elegant Hubris x20)
  - docs/research/variant-ninja.md   (the harvested durable variant/base enumeration)

DETERMINISTIC: fixed class + name ordering, sorted inner lists, stable JSON. Re-running
against the same dumps + schema yields byte-identical ``items`` (only the _meta timestamp
moves). Run it for real to produce the artifact; validation FAILS LOUD (non-zero exit) if
any defining stat id does not resolve or any durable ninja variant name is missing.

USAGE
  python tools/build_variant_registry.py            # offline: use cached ninja dumps (default)
  python tools/build_variant_registry.py --refresh  # re-fetch ninja Unique* overviews (polite)
  python tools/build_variant_registry.py --league Allflame
  python tools/build_variant_registry.py --check    # build in memory + validate, do NOT write

poe.ninja ONLY (never pathofexile.com/trade, per CLAUDE.md RULE 4). The overview endpoint
is cheap; live fetches are paced politely and cached to disk. All stat-id validation and
item grounding are offline against the bundled schema/dumps.
"""
import argparse
import json
import os
import sys
import time
from collections import OrderedDict, defaultdict

# --- paths ---------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
DATA_DIR = os.path.join(ROOT, "research", "data")
STATS_SCHEMA = os.path.join(ROOT, "public", "api", "_data", "trade_stats.json")
ITEMS_DUMP = os.path.join(DATA_DIR, "trade_items.json")          # full dump: carries unique names
OUT_PATH = os.path.join(ROOT, "public", "api", "_data", "variant_uniques.json")
LIB_DIR = os.path.join(ROOT, "public", "api", "_lib")

# Use the RUNTIME normaliser so our resolution matches StatMapper exactly (no drift).
sys.path.insert(0, LIB_DIR)
import util  # noqa: E402  (public/api/_lib/util.py -- pure, no relative imports)

SCHEMA_VERSION = "divtally.variant_uniques/1"
DEFAULT_LEAGUE = "Allflame"     # the league the committed dumps were harvested for
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 buildpricechecker/0.1")
POE1 = "https://poe.ninja/poe1"
INDEX_STATE = POE1 + "/api/data/index-state"
STASH = POE1 + "/api/economy/stash/current/item/overview"
NINJA_TYPES = ["UniqueWeapon", "UniqueArmour", "UniqueAccessory", "UniqueFlask",
               "UniqueJewel", "UniqueMap", "UniqueRelic", "UniqueTincture"]

# Deterministic class ordering for the emitted registry.
CLASS_ORDER = ["seed-jewel", "notable-jewel", "socket-defined", "roll-defined",
               "mod-variant", "links"]


# =========================================================================
# 1. SCHEMA INDEX  (validate every defining stat id against the SHIPPED bundle)
# =========================================================================
class Schema:
    """Index of public/api/_data/trade_stats.json -- the exact file the runtime reads.

    Exposes the three lookups the resolver needs:
      * has_id(sid)           -> a BARE id exists (value/seed/flag stats)
      * pipe_children(base)   -> list of (full_id, opt_int, text) for a pre-flattened
                                 option stat 'base|opt' (Forbidden, Impossible Escape,
                                 Thread of Hope, cluster small-grant) -- PoE1 ships these
                                 with the option baked into the id after a '|'.
      * family(group, pred)   -> [(id, text)] whose text matches a predicate, within a
                                 group -- for roll/flag families (Watcher aura mods,
                                 Megalomaniac notables) whose exact id is per-copy.
      * pattern_id(group,pat) -> the id a normalised mod pattern maps to (mirrors
                                 StatMapper), proving an item mod line will resolve.
    """

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.path = path
        self._by_id = {}                       # full id (may contain '|') -> (group, text)
        self._bare = set()                     # ids with no '|'
        self._pipe = defaultdict(list)         # base id -> [(full_id, opt_int, text)]
        self._group_entries = defaultdict(list)  # group label lower -> [(id, text)]
        self._group_pat = defaultdict(dict)    # group -> {normalised pattern -> id}
        for grp in data.get("result", []):
            glabel = (grp.get("label") or "").lower()
            for e in grp.get("entries", []):
                sid = e.get("id", "")
                text = e.get("text", "")
                if not sid:
                    continue
                self._by_id[sid] = (glabel, text)
                self._group_entries[glabel].append((sid, text))
                base = sid.split("|", 1)[0]
                if "|" in sid:
                    try:
                        opt = int(sid.split("|", 1)[1])
                    except ValueError:
                        opt = None
                    self._pipe[base].append((sid, opt, text))
                else:
                    self._bare.add(sid)
                # group index by prefix (explicit/enchant/...) mirrors StatMapper._groups
                prefix = base.split(".", 1)[0]
                self._group_pat[prefix].setdefault(util.mod_to_pattern(text), base if "|" not in sid else sid)

    def has_id(self, sid):
        return sid in self._bare or sid in self._by_id

    def pipe_children(self, base):
        return list(self._pipe.get(base, []))

    def family(self, group, predicate):
        return [(i, t) for (i, t) in self._group_entries.get(group.lower(), []) if predicate(t)]

    def text_of(self, sid):
        return self._by_id.get(sid, (None, None))[1]

    # -- timeless pseudo-seed ids, grouped by flavour template ------------
    def timeless_conquerors(self):
        """{template_key -> [(conqueror, stat_id, text), ...]} for pseudo_timeless_jewel_*."""
        out = defaultdict(list)
        for sid, (g, text) in self._by_id.items():
            base = sid.split("|", 1)[0]
            if not base.startswith("explicit.pseudo_timeless_jewel_"):
                continue
            conq = base.rsplit("_", 1)[-1].capitalize()
            # template key = the text with the trailing conqueror name stripped
            key = text.rsplit(conq, 1)[0].strip() if conq.lower() in text.lower() else text
            out[key].append((conq, base, text))
        return out


# =========================================================================
# 2. NINJA HARVEST  (offline-first; --refresh re-fetches politely)
# =========================================================================
def _requests():
    import requests
    return requests


def resolve_league(prefer, offline):
    if prefer:
        return prefer, "cli"
    if offline:
        return DEFAULT_LEAGUE, "default(offline)"
    try:
        req = _requests()
        s = req.Session()
        s.headers.update({"User-Agent": UA, "Accept": "application/json",
                          "Referer": "https://poe.ninja/poe1/economy"})
        idx = s.get(INDEX_STATE, timeout=20).json()
        for e in idx.get("economyLeagues", []) or []:
            nm = e.get("name", "")
            if nm and "Standard" not in nm and "Hardcore" not in nm:
                return nm, "live(index-state)"
    except Exception as e:  # noqa: BLE001 -- offline / transient: fall back, do not fail the build
        sys.stderr.write("  (league resolve failed: %s; using default)\n" % e)
    return DEFAULT_LEAGUE, "default(fallback)"


def load_ninja_type(league, t, refresh):
    """Return (lines, status). Cached raw dump is the primary source; --refresh re-fetches."""
    path = os.path.join(DATA_DIR, "ninja_uniques_%s.json" % t.lower())
    if os.path.exists(path) and not refresh:
        with open(path, encoding="utf-8") as f:
            return (json.load(f).get("lines", []) or []), "cached"
    try:
        req = _requests()
        s = req.Session()
        s.headers.update({"User-Agent": UA, "Accept": "application/json",
                          "Referer": "https://poe.ninja/poe1/economy"})
        r = s.get(STASH, params={"league": league, "type": t}, timeout=60)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("  %s: fetch error %s\n" % (t, e))
        return [], "error"
    if r.status_code == 404:
        return [], "http404"
    if not r.ok:
        return [], "http%s" % r.status_code
    data = r.json()
    lines = data.get("lines", []) if isinstance(data, dict) else []
    if lines:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    time.sleep(0.8)
    return lines, "fetched"


def _num(v):
    return v if isinstance(v, (int, float)) and v > 0 else None


def _abyssal_count(line):
    """Read 'Has # Abyssal Socket(s)' from a ninja line's explicitModifiers, if present."""
    for m in (line.get("explicitModifiers") or []):
        t = (m.get("text") or "")
        if "Abyssal Socket" in t:
            n = util.first_number(t)
            if n is not None:
                return int(n)
    return None


def harvest_ninja(league, refresh):
    """name -> record: variant lines (label, chaos, listings, links, abyssal_count),
    bases, floor price/listings, ninja type, whether links vary. OBSERVED from the dumps.
    Data-driven so the abyssal/passive COUNT is read from each line (not label-parsed),
    which is robust to poe.ninja's non-literal labels (e.g. Shroud '1 Jewel' = 3 sockets)."""
    rec = {}
    status = {}
    for t in NINJA_TYPES:
        lines, st = load_ninja_type(league, t, refresh)
        status[t] = st
        for ln in lines:
            nm = ln.get("name") or ""
            if not nm:
                continue
            r = rec.setdefault(nm, {"type": t, "variant_lines": [], "bases": set(),
                                    "floor_chaos": None, "floor_listings": 0,
                                    "links_present": False})
            c = _num(ln.get("chaosValue"))
            lc = int(ln.get("listingCount") or 0)
            L = ln.get("links")
            L = int(L) if isinstance(L, (int, float)) and L else 0
            if L:
                r["links_present"] = True
            if ln.get("baseType"):
                r["bases"].add(ln.get("baseType"))
            v = ln.get("variant")
            if v:
                r["variant_lines"].append({"variant": v, "chaos": c, "listings": lc,
                                           "links": L, "abyssal": _abyssal_count(ln),
                                           "base": ln.get("baseType")})
            # floor = the cheapest priced line for the name (used only as a sanity floor)
            if c is not None and (r["floor_chaos"] is None or c < r["floor_chaos"]):
                r["floor_chaos"] = c
                r["floor_listings"] = lc
    return rec, status


def detect_folded_gem_variants(league):
    """HARVEST-GAP GUARD (D-0022). poe.ninja FOLDS a gem-level-defined unique -- Replica
    Dragonfang's Flight carries ~280 *optional* '+# to Level of all <Gem> Gems' modifiers on
    ONE line whose `variant` is null -- so `durable_ninja_names` (which keys on >=2 distinct
    variant LABELS) never surfaces it for the roster, and the whole CLASS of gem/option-defined
    uniques poe.ninja folds into one line is silently skipped by the auto-harvest.

    Scan the CACHED dumps for that FOLD SIGNATURE (a line whose explicitModifiers carry >=3
    optional 'to Level of all ... Gems' entries) and return the names, so `assemble` can WARN
    when such a name is absent from the hand-authored roster. Detection ONLY -- the gem axis is
    priced by a StatMapper-matched defining filter (`defining_gem_level`), not a ninja variant
    line, so recipes stay hand-authored (do NOT auto-add). Reads cached files only (the harvest
    already refreshed them), so it never issues a network call of its own."""
    names = set()
    for t in NINJA_TYPES:
        lines, _ = load_ninja_type(league, t, False)
        for ln in lines:
            nm = ln.get("name") or ""
            hits = sum(1 for m in (ln.get("explicitModifiers") or [])
                       if m.get("optional") and "to Level of all" in (m.get("text") or "")
                       and (m.get("text") or "").rstrip().endswith("Gems"))
            if nm and hits >= 3:
                names.add(nm)
    return names


# =========================================================================
# 3. RECIPE BUILDERS  (resolve + validate defining filters against the schema)
# =========================================================================
class BuildError(Exception):
    pass


def _mkfrom(group, match, pattern, emit, **extra):
    d = OrderedDict([("group", group), ("match", match), ("pattern", pattern), ("emit", emit)])
    for k, v in extra.items():
        d[k] = v
    return d


def defining_option(schema, base_id, group, pattern, axis):
    """OPTION stat (pre-flattened base|opt). Validate the base has pipe children.
    Runtime: StatMapper.match(line, group) -> 'base|opt' -> split to {id:base, value:{option:opt}}."""
    kids = schema.pipe_children(base_id)
    if not kids:
        raise BuildError("option base %s has no pipe children in schema" % base_id)
    return OrderedDict([
        ("stat_id", base_id), ("kind", "option"), ("axis", axis),
        ("option_count", len(kids)),
        ("from", _mkfrom(group, "option-by-name", pattern, "option-split",
                         note="find the item's explicit mod containing the axis name; "
                              "StatMapper returns the pre-split id 'base|opt'; emit "
                              "{id: base, value:{option: opt}}")),
    ])


def defining_seed(conqueror, stat_id, text, live, x20):
    return OrderedDict([
        ("stat_id", stat_id), ("kind", "seed"), ("conqueror", conqueror), ("live", live),
        ("from", _mkfrom("explicit", "seed-line", text, "seed-exact",
                         x20=x20,
                         note=("parse the DISPLAYED seed integer from the item's seed line "
                               "(split combined mod on newline; drop the 'Conquered by' line); "
                               "emit {id, value:{min:seed, max:seed}}. "
                               + ("Elegant Hubris DISPLAYS internal_seed*20 -- the trade stat "
                                  "matches the displayed value, so use the displayed number as-is."
                                  if x20 else "Displayed value == filter value (no transform).")))),
    ])


def defining_value(schema, stat_id, group, pattern, emit, axis, note):
    if not schema.has_id(stat_id):
        raise BuildError("value stat %s not in schema" % stat_id)
    return OrderedDict([
        ("stat_id", stat_id), ("kind", "value"), ("axis", axis),
        ("from", _mkfrom(group, "value", pattern, emit, note=note)),
    ])


def defining_family(schema, group, predicate, pred_label, samples, emit, axis, note,
                    rep_id=None, serialise_family_ids=False):
    """A per-copy FAMILY (roll/flag) recipe: the exact id varies with the copy, so record a
    representative id + verified samples + the predicate. Runtime matches ALL of the item's
    mods whose text satisfies the predicate (via StatMapper) and AND-groups them. RAISES
    BuildError if the family resolves to 0 stats (the D-0019 gate for cross-check items) or a
    sample is missing. `rep_id` defaults to the deterministic first resolved family id (never
    a fabricated id); pass one explicitly only to pin a canonical, verified example.

    `serialise_family_ids=True` also writes the WHOLE sorted family id list into
    `from.family_ids`, so the runtime can match ANY member the copy carries by its OWN id --
    not just `rep_id`. Use it for a mod-variant family the runtime prices by def-id matching
    (NOT the "while affected by" aura branch, NOT emit=presence): The Light of Meaning's
    "Passive Skills in Radius also grant X" set, whose copy names a specific member that the
    rep id alone would miss -- the D-0019 MAJOR where rep-only serialisation dropped the
    defining filter for EVERY real copy. Off by default so large aura/presence families
    (Watcher's Eye 144, Megalomaniac 301, Aul's 116), whose branch never consults these ids,
    are not bloated with them."""
    fam = schema.family(group.capitalize() if group != "pseudo" else "Pseudo", predicate)
    if not fam:
        raise BuildError("family %r resolves to 0 stats in group %s" % (pred_label, group))
    if rep_id is None:
        rep_id = sorted(i for i, _ in fam)[0]     # deterministic, real, resolved id
    elif not schema.has_id(rep_id):
        raise BuildError("family representative %s not in schema" % rep_id)
    missing = [s for s in samples if not schema.has_id(s)]
    if missing:
        raise BuildError("family samples missing from schema: %s" % missing)
    if serialise_family_ids:
        frm = _mkfrom(group, "family-all", pred_label, emit,
                      family_size=len(fam), samples=sorted(samples), note=note,
                      family_ids=sorted(i for i, _ in fam))
    else:
        frm = _mkfrom(group, "family-all", pred_label, emit,
                      family_size=len(fam), samples=sorted(samples), note=note)
    return OrderedDict([
        ("stat_id", rep_id), ("kind", "value"), ("axis", axis), ("from", frm),
    ])


def defining_gem_level(schema, rep_id, note):
    """GEM-LEVEL variant recipe (Replica Dragonfang's Flight, D-0022). The price axis is WHICH
    specific gem the copy grants ``+# to Level of all <Gem> Gems`` for. Unlike Forbidden's
    OPTION stat, PoE1 ships each of these as an INDIVIDUAL stat id -- one
    ``explicit.indexable_skill_N`` per specific gem -- NOT a ``base|opt`` option (PRIMARY-SOURCED
    live: ``/api/trade/data/stats`` carries ZERO pipe form for gem levels; docs/notes-d0022-api.md).
    ``rep_id`` is a real, verified family member (validated here) that documents the family; the
    RUNTIME matches the copy's OWN mod by TEXT (``from.match == 'gem-level'`` ->
    variantreg._is_gem_level_mod), so it needs no id list. ``family_size`` counts the resolved
    per-gem ids (documentation only). RAISES if the rep id or the family does not resolve in the
    shipped schema (the D-0019 gate).

    NOTE (D-0022): there is intentionally NO per-DAMAGE-TAG entry. The owner-hypothesised base
    "Dragonfang's Flight" (per-tag '+# to Level of all <Tag> Skill Gems') does NOT exist as a
    tradeable PoE1 unique -- LIVE /api/trade/data/items lists only "Replica Dragonfang's Flight",
    and a name search for the base returns HTTP 400 "Unknown item name". A per-tag skill-level mod
    would anyway already be searched by the generic _unique_value_filters path (its text contains
    "Skill"), so it needs no registry recipe; only the Replica's "<Gem> Gems" (no "Skill") form
    was invisible to that path. The runtime _is_gem_level_mod still matches the per-tag form, so a
    future per-tag gem-level unique would only need a one-line roster add here."""
    if not schema.has_id(rep_id):
        raise BuildError("gem-level rep %s not in schema" % rep_id)
    # per-specific-gem (indexable): "... <Gem> Gems", NOT "... Skill Gems" (that is the per-tag
    # / generic form, handled by _unique_value_filters), NOT a conditional "... if ... Equipped".
    fam = schema.family("Explicit",
                        lambda t: t.startswith("+# to Level of all ")
                        and t.rstrip().endswith(" Gems") and "Skill Gems" not in t
                        and " if " not in t)
    if len(fam) < 3:
        raise BuildError("gem-level family resolves to %d stats (<3)" % len(fam))
    return OrderedDict([
        ("stat_id", rep_id), ("kind", "gem-level"), ("axis", "gem"),
        ("family_size", len(fam)),
        ("from", _mkfrom("explicit", "gem-level", "+# to Level of all <Gem> Gems", "roll-min",
                         note=note)),
    ])


# =========================================================================
# 4. THE ROSTER  (curated; every recipe is [SRC]-grounded in the research notes)
# =========================================================================
# Each roster entry is a function of (schema) -> the item's `defining` list + metadata,
# so the schema validates every id at BUILD time. `source` records why it's included:
#   ninja-harvest : poe.ninja enumerates its variant/base lines (primary; sec 2/3 of
#                   variant-ninja.md). Always included; ninja rule is the price handle.
#   primary-stat  : a fixed defining stat id/family resolves in the trade schema
#                   (variant-stats.md [SRC]); included; recipe MUST resolve.
#   crosscheck    : community roster (variant-crosscheck.md, [NOT FROM SOURCE]);
#                   included ONLY IF its recipe resolves (the D-0019 gate).

def build_roster(schema, ninja):
    R = []

    def add(name, klass, source, defining, ninja_axis, conf, *,
            base=None, flags=None, tags=None, notes=None, also_links=None,
            defining_rule=None):
        R.append({
            "name": name, "class": klass, "source": source, "defining": defining,
            "ninja_axis": ninja_axis, "confidence_policy": conf,
            "base": base, "flags": flags or [], "crosscheck_tags": tags or [],
            "notes": notes, "also_links": also_links, "defining_rule": defining_rule,
        })

    def add_gated(name, klass, source, family_kw, ninja_axis, conf, **kw):
        """Add ONLY if the defining family resolves in the primary schema (the D-0019 gate
        for cross-check additions); otherwise record a drop with the reason."""
        try:
            defining = [defining_family(**family_kw)]
        except BuildError as e:
            R.append({"_dropped": name, "_reason": str(e)})
            return
        add(name, klass, source, defining, ninja_axis, conf, **kw)

    # ---- seed-jewel (5) : timeless jewels -- exact seed + conqueror ------
    # variant-stats.md sec5 + timeless-jewels.md. Conqueror ids resolved from schema
    # (pseudo_timeless_jewel_*), grouped by flavour template. Live/legacy per
    # timeless-jewels.md sec4 ([SRC:ninja] EH; [INFERRED] the analogous 4th elsewhere).
    LEGACY = {"Zerphi", "Kiloava", "Deshret", "Venarius", "Chitus"}
    TL_TEMPLATE = {  # jewel -> the flavour-template key (text minus conqueror)
        "Glorious Vanity": "Bathed in the blood of # sacrificed in the name of",
        "Lethal Pride": "Commanded leadership over # warriors under",
        "Brutal Restraint": "Denoted service of # dekhara in the akhara of",
        "Militant Faith": "Carved to glorify # new faithful converted by High Templar",
        "Elegant Hubris": "Commissioned # coins to commemorate",
    }
    tl_groups = schema.timeless_conquerors()

    def _tl_conqs(template_key):
        # match by template prefix (schema text uses '#'); find the group whose key startswith it
        for key, conqs in tl_groups.items():
            if key.startswith(template_key) or template_key.startswith(key):
                return conqs
        return []

    for jewel, tmpl in TL_TEMPLATE.items():
        conqs = _tl_conqs(tmpl)
        if not conqs:
            raise BuildError("no timeless conqueror stats for %s (template %r)" % (jewel, tmpl))
        x20 = (jewel == "Elegant Hubris")
        defining = [defining_seed(c, sid, text, c not in LEGACY, x20)
                    for (c, sid, text) in sorted(conqs)]
        conf = OrderedDict([
            ("ninja", "floor-low"), ("cap", "low"), ("trade", "exact-seed-from-listings"),
            ("unmatchable", "none-link-only"),
            ("note", "poe.ninja lists ONE null-variant line = cheapest of ALL seeds & "
                     "conquerors; hard-cap it to LOW and label it a floor. Price by the "
                     "exact-seed (min=max) trade filter; 0 buyouts is the honest answer.")])
        note = ("Two same-name jewels with different seeds are different items; name-only "
                "pricing is meaningless (timeless-jewels.md).")
        if jewel == "Militant Faith":
            note += (" SECOND axis: Militant Faith also grants Devotion + converts a passive "
                     "to a keystone, with separately-searchable 'per 10 Devotion' explicit "
                     "stats (seed+conqueror pin is primary; keystone/Devotion is an optional "
                     "picker refinement -- timeless-jewels.md sec 6).")
        add(jewel, "seed-jewel", "primary-stat", defining, "seed", conf,
            base=["Timeless Jewel"],
            flags=(["elegant-hubris-displayed-seed-x20"] if x20 else []),
            notes=note)

    # ---- notable-jewel (4) : OPTION stats (Allocates / keystone radius / ring size) ----
    add("Forbidden Flame", "notable-jewel", "primary-stat",
        [defining_option(schema, "explicit.stat_2460506030", "explicit",
                         "Allocates <Notable> if you have the matching modifier on Forbidden Flame",
                         "ascendancy-notable")],
        "floor", _floor_conf("The Allocates-<notable> option IS the price identity; must "
                             "pair-match the Forbidden Flesh's notable. poe.ninja floors it."),
        base=["Crimson Jewel"],
        notes="Buy as a matching pair naming the SAME ascendancy notable (Flame+Flesh).")
    add("Forbidden Flesh", "notable-jewel", "primary-stat",
        [defining_option(schema, "explicit.stat_1190333629", "explicit",
                         "Allocates <Notable> if you have the matching modifier on Forbidden Flesh",
                         "ascendancy-notable")],
        "floor", _floor_conf("As Forbidden Flame; base Cobalt Jewel."),
        base=["Cobalt Jewel"],
        notes="Pair-match the Forbidden Flame's notable.")
    add("Impossible Escape", "notable-jewel", "primary-stat",
        [defining_option(schema, "explicit.stat_2422708892", "explicit",
                         "Passives in Radius of <Keystone> can be Allocated ...", "keystone")],
        "floor", _floor_conf("Variant = which keystone's radius it frees; option-stat."),
        base=["Viridian Jewel"],
        notes="Do NOT confuse with stat_1725885727 (Intuitive Leap) or _1211779989 (generic).")
    add("Thread of Hope", "notable-jewel", "primary-stat",
        [defining_option(schema, "explicit.stat_3642528642", "explicit",
                         "Only affects Passives in <Size> Ring", "ring-size")],
        "floor", _floor_conf("Variant = ring size (Small..Massive); 5 options; drives price."),
        base=["Crimson Jewel"])

    # ---- socket-defined (7) : exact COUNT of abyssal sockets / added passives ----
    for nm, b in [("Bubonic Trail", "Murder Boots"), ("Tombfist", "Steelscale Gauntlets"),
                  ("Lightpoacher", "Great Crown"), ("Shroud of the Lightless", "Carnal Armour"),
                  ("Command of the Pit", "Riveted Gloves"), ("Hale Negator", "Mind Cage")]:
        add(nm, "socket-defined", "primary-stat",
            [defining_value(schema, "explicit.stat_3527617737", "explicit",
                            "Has # Abyssal Sockets", "count-exact", "abyssal-sockets",
                            "emit {id, value:{min:N, max:N}} with N = the item's abyssal "
                            "socket count -- the tier that sets the price.")],
            "abyssal-count",
            _count_conf("poe.ninja enumerates '1 Jewel'/'2 Jewels' lines but the LABEL is "
                        "not always the literal count (Shroud's '1 Jewel' line carries "
                        "'Has 3 Abyssal Sockets'), so map by the observed abyssal_count in "
                        "each variant line, NOT by parsing the label."),
            base=[b])
    add("Voices", "socket-defined", "primary-stat",
        [defining_value(schema, "explicit.stat_1085446536", "explicit",
                        "Adds # Small Passive Skills which grant nothing", "count-exact",
                        "added-small-passives",
                        "emit exact min=max on the count (3/5/7) -- the sub-variant that "
                        "distinguishes 1x7 vs corrupted 2x5 / 3x3.")],
        "passive-count",
        _count_conf("poe.ninja enumerates '3 passives'/'5 passives'/'7 passives'."),
        base=["Large Cluster Jewel"])

    # ---- roll-defined (6) : value = which/what the copy rolled (ninja floors these) ----
    add("Watcher's Eye", "roll-defined", "primary-stat",
        [defining_family(schema, "explicit",
                         lambda t: "while affected by" in t.lower(),
                         "explicit '<stat> while affected by <Aura>'",
                         ["explicit.stat_2255914633", "explicit.stat_1222888897",
                          "explicit.stat_3111519953", "explicit.stat_2643562209",
                          "explicit.stat_3627458291"],
                         "roll-min", "aura-mods",
                         "Match EACH 'while affected by <Aura>' explicit line to its own id "
                         "(value:{min:roll}); AND-group them -- the aura-mod COMBO is the "
                         "price identity. Generic ES/Life/Mana lines are not price-driving.",
                         rep_id="explicit.stat_2255914633")],
        "floor",
        _floor_conf("poe.ninja lists ONE null-variant floor (50c across 11,320 mixed "
                    "listings); the specific aura combo is trade-only."),
        base=["Prismatic Jewel"])
    add("Sublime Vision", "roll-defined", "crosscheck",
        [defining_family(schema, "explicit",
                         lambda t: "while affected by" in t.lower(),
                         "explicit aura-empower mod (which single aura it names)",
                         ["explicit.stat_2255914633"],
                         "roll-min", "aura",
                         "Match the copy's aura-empowering explicit mod(s).",
                         rep_id="explicit.stat_2255914633")],
        "floor",
        _floor_conf("Variant = which single aura it empowers (disables others)."),
        base=["Prismatic Jewel"],
        tags=["[NOT FROM SOURCE - poeprices/poewiki 'Sublime Vision']"])
    add("Megalomaniac", "roll-defined", "primary-stat",
        [defining_family(schema, "explicit",
                         lambda t: t.startswith("1 Added Passive Skill is "),
                         "explicit '1 Added Passive Skill is <Notable>' (x3)",
                         ["explicit.stat_2780712583", "explicit.stat_2342448236",
                          "explicit.stat_3599340381"],
                         "presence", "cluster-notables",
                         "Match the item's THREE '1 Added Passive Skill is <Notable>' flags "
                         "(presence, value:{min:1}); AND-group -- the 3-notable combo is the "
                         "identity poe.ninja cannot price.",
                         rep_id="explicit.stat_2780712583")],
        "floor",
        _floor_conf("Rolls 3 random notables from the whole pool; ninja folds to one line."),
        base=["Medium Cluster Jewel"],
        tags=["[NOT FROM SOURCE - maxroll 'Cluster Jewels Explained' (3-random-notables)]"])
    # Split Personality / That Which Was Taken: no special stat -- the variant IS the item's
    # own rolled explicit mods, priced via the generic (rare-style) StatMapper path. Registry
    # flags them roll-defined (a `defining_rule`, not fixed ids) so they are NOT priced
    # name-only. variant-stats.md sec 13 ([SRC] mechanism; the ids are per-copy).
    add("Split Personality", "roll-defined", "primary-stat", [],
        "floor",
        _floor_conf("Value = which two random attribute/defence mods; ninja shows one line."),
        base=["Crimson Jewel"], defining_rule="own-explicit-rolls",
        tags=["[NOT FROM SOURCE - poewiki 'Split Personality']"],
        notes="Priced via the item's OWN explicit rolls (generic StatMapper path), not a "
              "fixed defining id; the registry entry only prevents a name-only price.")
    add("That Which Was Taken", "roll-defined", "crosscheck", [],
        "floor",
        _floor_conf("Value = which explicit mods rolled."),
        base=["Crimson Jewel"], defining_rule="own-explicit-rolls",
        tags=["[NOT FROM SOURCE - poewiki 'That Which Was Taken']"],
        notes="Priced via the item's own explicit rolls (generic path).")
    add_gated("Aul's Uprising", "roll-defined", "crosscheck",
              dict(schema=schema, group="explicit", predicate=lambda t: "Reservation" in t,
                   pred_label="explicit '<Aura> has no Reservation ...' (which aura)",
                   samples=[], emit="roll-min", axis="reservation-aura",
                   note="Match the copy's reservation-removal explicit mod (the price driver "
                        "-- which aura's reservation it removes)."),
              "floor",
              _floor_conf("Value dominated by which aura's reservation-removal mod rolled."),
              base=["Onyx Amulet"],
              tags=["[NOT FROM SOURCE - poewiki/trade experience 'Aul's Uprising']"])
    # D-0022: Replica Dragonfang's Flight -- a GEM-LEVEL-defined amulet. The price is WHICH
    # specific gem the copy grants "+# to Level of all <Gem> Gems" for; poe.ninja FOLDS all ~280
    # gem versions into ONE aggregate line (variant=None, ~15c across 7,216 mixed listings), so
    # the auto-harvest -- which keys on >=2 distinct ninja variant LABELS -- MISSES it (the CLASS
    # gap detect_folded_gem_variants guards). Recipe (roll-defined: value = which the copy rolled,
    # ninja floors it): match the copy's OWN gem-level mod to its individual indexable_skill id,
    # floor the ninja line. NOT an OPTION stat -- no base|opt form exists (notes-d0022-api.md;
    # live-checked). The owner-hypothesised BASE "Dragonfang's Flight" (per-tag) is deliberately
    # NOT added: it is not a tradeable PoE1 unique (LIVE data/items has only the Replica; a name
    # search 400s "Unknown item name"), and a per-tag "Skill Gems" mod is already covered by the
    # generic _unique_value_filters path anyway (see defining_gem_level's NOTE).
    add("Replica Dragonfang's Flight", "roll-defined", "primary-stat",
        [defining_gem_level(schema, "explicit.indexable_skill_138",
                            "Match the copy's own '+# to Level of all <Gem> Gems' mod via "
                            "StatMapper -> its specific explicit.indexable_skill_N id, emit "
                            "value:{min:roll}. The named GEM is the price identity; poe.ninja "
                            "folds all ~280 gem versions into one line (floor-only). D-0022.")],
        "floor",
        _floor_conf("poe.ninja folds every '+# to Level of all <Gem> Gems' version into ONE "
                    "aggregate line (~15c across 7,216 mixed listings) -- a LOW floor; the "
                    "specific gem's real price is the defining-mod trade search on the copy."),
        base=["Onyx Amulet"],
        notes="Replica grants '+3 to Level of all <specific gem> Gems' (one indexable_skill id "
              "per gem, e.g. Determination=indexable_skill_67). poe.ninja can't split by gem -> "
              "floor-only; price the exact gem via the trade link. LIVE-verified 2026-07-28: the "
              "Determination filter returns 14 listings, all carrying stat.explicit.indexable_"
              "skill_67 (notes-d0022-api.md).")

    # ---- mod-variant : poe.ninja enumerates discrete variant/base lines ---
    # For NINJA-HARVEST items the ninja variant enumeration IS the price recipe (mapped in
    # ninja_variant_rule from the live harvest), so `defining` is [] -- no fixed trade filter
    # is needed to price them; the copy is mapped to its priced variant line. (Their
    # discriminating element/type mod is matched generically by the picker if the user wants
    # to verify on trade.) These are always included (primary: sec 2/3 of variant-ninja.md).
    add("Impresence", "mod-variant", "ninja-harvest", [], "variant-mod",
        _variant_conf("Element (Chaos/Physical/Lightning/Fire/Cold) picks the free-curse + "
                      "damage mods; poe.ninja lists 'Impresence (<element>)'."),
        base=["Onyx Amulet"], defining_rule="ninja-variant-label")
    add("Doryani's Invitation", "mod-variant", "ninja-harvest", [], "variant-mod",
        _variant_conf("Element (Physical/Cold/Lightning/Fire) picks the damage + pen mods; "
                      "poe.ninja lists a row per element."),
        base=["Heavy Belt"], defining_rule="ninja-variant-label")
    add("Volkuur's Guidance", "mod-variant", "ninja-harvest", [], "variant-mod",
        _variant_conf("Element (Lightning/Fire/Cold) picks the curse-on-hit + res mod; "
                      "poe.ninja lists 3 rows."),
        base=["Zealot Gloves"], defining_rule="ninja-variant-label")
    add("Yriel's Fostering", "mod-variant", "ninja-harvest", [], "variant-mod",
        _variant_conf("Bleeding/Poison/Maim picks which animal companion skill is granted; "
                      "poe.ninja lists 3 rows. Also 5L/6L links-sensitive (engine adds links)."),
        base=["Exquisite Leather"], also_links=True, defining_rule="ninja-variant-label",
        tags=["[NOT FROM SOURCE - poewiki 'Yriel's Fostering (Rhoa/Snake/Ursa)']"])
    add("Mageblood", "mod-variant", "ninja-harvest", [], "variant-mod",
        _variant_conf("'2 Flasks'/'3 Flasks'/'4 Flasks' -- how many magic utility flasks it "
                      "applies; poe.ninja enumerates each. The count is intrinsic to the copy."),
        base=["Heavy Belt"], defining_rule="ninja-variant-label")
    add("Atziri's Splendour", "mod-variant", "ninja-harvest", [], "variant-mod",
        _variant_conf("Variant = the defence-stat combo it rolls (Armour/ES, Evasion/ES, ..., "
                      "9 forms); poe.ninja enumerates each. Also 5L/6L links-sensitive."),
        base=["Sacrificial Garb"], also_links=True, defining_rule="ninja-variant-label")
    add("The First Crest", "mod-variant", "ninja-harvest", [], "variant-mod",
        _variant_conf("Relic reward variant (Relics / Tainted Currency / Experience); "
                      "poe.ninja lists 3 rows."),
        base=["Coffer Relic"], defining_rule="ninja-variant-label")
    # base-variant (sec 3): the variant axis IS the base type, already pinned by the query's
    # `type` field; poe.ninja splits by base. defining=[] (base is intrinsic to the copy).
    add("Grand Spectrum", "mod-variant", "ninja-harvest", [], "base",
        _variant_conf("Colour base (Cobalt/Crimson/Viridian Jewel) picks the stacking bonus; "
                      "poe.ninja splits by base. The base is pinned by the query `type`."),
        base=["Cobalt Jewel", "Crimson Jewel", "Viridian Jewel"], defining_rule="ninja-base-line",
        tags=["[NOT FROM SOURCE - poewiki (colour->bonus mapping)]"])
    add("Combat Focus", "mod-variant", "ninja-harvest", [], "base",
        _variant_conf("Colour base picks which element is prevented from igniting; poe.ninja "
                      "splits by base."),
        base=["Cobalt Jewel", "Crimson Jewel", "Viridian Jewel"], defining_rule="ninja-base-line",
        tags=["[NOT FROM SOURCE - poewiki (colour->element mapping)]"])
    add("Precursor's Emblem", "mod-variant", "ninja-harvest", [], "base",
        _variant_conf("Ring base picks which resist/attribute implicit it can roll; poe.ninja "
                      "splits by base. Base pinned by query `type`."),
        base=["Prismatic Ring", "Ruby Ring", "Sapphire Ring", "Topaz Ring", "Two-Stone Ring"],
        defining_rule="ninja-base-line",
        notes="Variant axis is an IMPLICIT that follows the base; base-pin is sufficient.")

    # ---- cross-check additions (community roster) -- included ONLY where the defining
    # family RESOLVES in the primary schema (the D-0019 gate). poe.ninja did NOT enumerate
    # these as multi-variant lines this league, so their actionable recipe IS the resolved
    # defining-mod family (searched on the build's own copy), not a ninja variant line.
    for nm, b, herald in [("Circle of Nostalgia", "Amethyst Ring", None),
                          ("Circle of Guilt", "Iron Ring", None),
                          ("Circle of Anguish", "Ruby Ring", None),
                          ("Circle of Fear", "Sapphire Ring", None),
                          ("Circle of Regret", "Topaz Ring", None)]:
        add_gated(nm, "mod-variant", "crosscheck",
                  dict(schema=schema, group="explicit",
                       predicate=lambda t: "while affected by Herald of" in t,
                       pred_label="explicit '<stat> while affected by Herald of <X>'",
                       samples=[], emit="roll-min", axis="herald",
                       note="Match the copy's 'while affected by Herald of <X>' explicit mod "
                            "-- the named Herald IS the variant."),
                  "variant-mod",
                  _variant_conf("The 'while affected by Herald of <X>' mod names the Herald = "
                                "the variant. (poe.ninja lists per-Herald rows when priced.)"),
                  base=[b], tags=["[NOT FROM SOURCE - poewiki 'Elder Circle rings']"])
    add_gated("Vessel of Vinktar", "mod-variant", "crosscheck",
              dict(schema=schema, group="explicit",
                   predicate=lambda t: ("Lightning Damage to Spells" in t
                                        or "Lightning Damage to Attacks" in t
                                        or ("Penetrates" in t and "Lightning Resistance" in t)),
                   pred_label="the lightning conversion / added-lightning / pen mod",
                   samples=[], emit="roll-min", axis="variant-mod",
                   note="Match the copy's lightning conversion/added/pen mod -- the variant."),
              "variant-mod",
              _variant_conf("4-5 variants (added Lightning to Spells / to Attacks / "
                            "Phys->Lightning / Lightning Pen); poe.ninja lists 'Vessel of "
                            "Vinktar (<X>)' when priced."),
              base=["Topaz Flask"], tags=["[NOT FROM SOURCE - poewiki 'Vessel of Vinktar']"])
    add_gated("Doryani's Delusion", "mod-variant", "crosscheck",
              dict(schema=schema, group="explicit",
                   predicate=lambda t: "affected by" in t and ("Anger" in t or "Hatred" in t
                                                               or "Wrath" in t),
                   pred_label="the aura + element mod (element axis rides on the base axis)",
                   samples=[], emit="roll-min", axis="base+variant-mod",
                   note="Base picks the armour type (base-split in trade); match the element "
                        "aura/pen mod for the element sub-axis. Pin base AND the element mod."),
              "base+variant-mod",
              _variant_conf("Base picks the armour type (Boots x3, base-split in trade); an "
                            "ELEMENT axis (Fire/Cold/Lightning aura+pen) rides on top."),
              base=["Slink Boots", "Sorcerer Boots", "Titan Greaves"], also_links=True,
              tags=["[NOT FROM SOURCE - poewiki 'Doryani's Delusion' (element axis)]"])
    # LoM's variant IS which "Passive Skills in Radius also grant <X>" mod it carries -- a
    # 15-member explicit family (evasion/mana/life/an element/crit/...). The whole family's ids
    # are serialised (serialise_family_ids) so the runtime matches the SPECIFIC member on the
    # copy by its own id; rep_id alone matched 0 of 913 live listings (D-0019 MAJOR r1-1). The
    # old recipe's predicate resolved to `stat_607548408` "increased Effect of non-Keystone
    # Passive Skills in Radius" -- which is Might of the Meek's mod (ninja detailsId
    # "...might-of-the-meek..."), NOT a current Light of Meaning mod. samples = the two
    # live-fetched members (variants-r1.md sec 3). "stat_607548408 was LoM's OLD mod" is
    # [INFERRED - community memory]; the source-confirmed fact is that live copies carry the
    # "also grant X" family and none carry stat_607548408.
    add_gated("The Light of Meaning", "mod-variant", "crosscheck",
              dict(schema=schema, group="explicit",
                   predicate=lambda t: "Passive Skills in Radius also grant" in t,
                   pred_label="the 'Passive Skills in Radius also grant <X>' amplify mod",
                   samples=["explicit.stat_3382199855", "explicit.stat_3761482453"],
                   emit="roll-min", axis="variant-mod", serialise_family_ids=True,
                   note="Match the copy's 'Passive Skills in Radius also grant <X>' mod(s); "
                        "which bonus the radius grant confers is the variant. from.family_ids "
                        "serialises all 15 members so the runtime emits the copy's SPECIFIC "
                        "member by its own id (rep id alone matches 0 real copies)."),
              "variant-mod",
              _variant_conf("Variant = which bonus the 'Passive Skills in Radius also grant "
                            "<X>' mod confers (Evasion / Mana / Life / an element / crit / ...)."),
              base=["Prismatic Jewel"], tags=["[NOT FROM SOURCE - poewiki 'The Light of Meaning']"])

    return R


# -- confidence-policy templates ------------------------------------------
def _floor_conf(note):
    return OrderedDict([
        ("ninja", "floor-low"), ("cap", "low"), ("trade", "defining-filter-from-listings"),
        ("unmatchable", "none-link-only"), ("note", note)])


def _count_conf(note):
    return OrderedDict([
        ("ninja", "variant-from-listing-count"), ("cap", None),
        ("trade", "exact-count-from-listings"), ("unmatchable", "none-link-only"),
        ("note", note)])


def _variant_conf(note):
    return OrderedDict([
        ("ninja", "variant-from-listing-count"), ("cap", None),
        ("trade", "defining-filter-from-listings"), ("unmatchable", "none-link-only"),
        ("note", note)])


# =========================================================================
# 5. NINJA-VARIANT-RULE  (how to map an owned copy -> the overview variant string)
# =========================================================================
def ninja_variant_rule(entry, nrec):
    """Build the runtime instruction that maps the build copy onto poe.ninja's lines,
    from the OBSERVED harvest record for this name (nrec) + the entry's axis."""
    axis = entry["ninja_axis"]
    observed = []
    floor_chaos = floor_listings = None
    if nrec:
        floor_chaos = nrec.get("floor_chaos")
        floor_listings = nrec.get("floor_listings")
        # de-dup variant lines to (variant, links) keeping best info; sort deterministically
        seen = {}
        for vl in nrec.get("variant_lines", []):
            key = (vl["variant"], vl.get("links") or 0)
            cur = seen.get(key)
            if cur is None or (vl.get("chaos") or 0) > (cur.get("chaos") or 0):
                seen[key] = vl
        for (v, L), vl in seen.items():
            row = OrderedDict([("variant", v), ("chaos", vl.get("chaos")),
                               ("listing_count", vl.get("listings"))])
            if L:
                row["links"] = L
            if vl.get("abyssal") is not None:
                row["abyssal_count"] = vl.get("abyssal")
            observed.append(row)
        observed.sort(key=lambda r: (-(r.get("chaos") or 0), r["variant"]))

    if axis == "seed":
        strat, match = "floor-only", (
            "poe.ninja has NO seed/conqueror split -- one aggregate line per NAME. Do NOT "
            "match a variant. Use the name-line only as a low-confidence FLOOR; the real "
            "price is the exact-seed trade search.")
    elif axis == "abyssal-count":
        strat, match = "map-count", (
            "Read the copy's abyssal socket count; pick the ninja variant line whose "
            "OBSERVED abyssal_count equals it (not by parsing the '<N> Jewel(s)' label -- "
            "poe.ninja labels are not always literal). Fall back to the exact-count trade "
            "filter for the price.")
    elif axis == "passive-count":
        strat, match = "map-count", (
            "Read the copy's added-small-passive count (3/5/7); pick the ninja variant line "
            "whose label encodes that count ('<N> passives').")
    elif axis == "base":
        strat, match = "map-base", (
            "poe.ninja splits by baseType; pick the line whose baseType == the copy's base. "
            "The base is already pinned by the query's `type` field.")
    elif axis in ("variant-mod", "base+variant-mod"):
        strat, match = "map-variant", (
            "poe.ninja enumerates a `variant` label per form; pick the line whose label "
            "tokens are covered by the copy's defining mod text (or, for the base axis, its "
            "baseType). That line's chaosValue is the price (confidence from its "
            "listing_count). If none covers >0.6 and beats the runner-up, fall to the "
            "min..p90 range at LOW confidence (existing unique_price behaviour).")
    else:  # floor
        strat, match = "floor-only", (
            "poe.ninja lists ONE null-variant floor line for this name; use it only as a "
            "low-confidence floor. The real price is the defining-mod trade search on the "
            "build's own copy.")

    rule = OrderedDict([
        ("strategy", strat), ("axis", axis), ("match", match),
        ("observed_variants", observed),
        ("ninja_floor_chaos", floor_chaos), ("ninja_floor_listings", floor_listings),
        ("harvested", bool(nrec)),
    ])
    return rule


# =========================================================================
# 6. ASSEMBLE + VALIDATE + EMIT
# =========================================================================
def assemble(schema, ninja, league, harvest_status, refresh):
    roster = build_roster(schema, ninja)
    items, dropped = [], []
    for e in roster:
        if "_dropped" in e:
            dropped.append((e["_dropped"], e["_reason"]))
            continue
        nrec = ninja.get(e["name"])
        rule = ninja_variant_rule(e, nrec)
        item = OrderedDict()
        item["name"] = e["name"]
        item["class"] = e["class"]
        if e.get("base"):
            item["base"] = e["base"]
        item["source"] = e["source"]
        item["variant_sensitive"] = True
        if e.get("also_links"):
            item["also_links"] = True
        item["defining"] = e["defining"]
        if e.get("defining_rule"):
            item["defining_rule"] = e["defining_rule"]
        item["ninja_variant_rule"] = rule
        item["confidence_policy"] = e["confidence_policy"]
        if e.get("flags"):
            item["flags"] = e["flags"]
        if e.get("crosscheck_tags"):
            item["crosscheck_tags"] = e["crosscheck_tags"]
        if e.get("notes"):
            item["notes"] = e["notes"]
        items.append(item)

    # deterministic ordering: class order, then name
    items.sort(key=lambda it: (CLASS_ORDER.index(it["class"]), it["name"]))

    # ---- VALIDATION 1: every defining stat_id resolves in the shipped schema ----
    stat_ids = set()
    unresolved = []
    for it in items:
        for d in it["defining"]:
            sid = d["stat_id"]
            stat_ids.add(sid)
            if d["kind"] == "option":
                if not schema.pipe_children(sid):
                    unresolved.append((it["name"], sid, "option-no-children"))
            else:
                if not schema.has_id(sid):
                    unresolved.append((it["name"], sid, d["kind"]))
            # also validate family samples
            samples = (d.get("from") or {}).get("samples") or []
            for s in samples:
                stat_ids.add(s)
                if not schema.has_id(s):
                    unresolved.append((it["name"], s, "sample"))
    if unresolved:
        raise BuildError("UNRESOLVED defining stat ids (validation 1 failed): %s" % unresolved)

    # ---- VALIDATION 2: every DURABLE ninja variant/base name is present ----
    reg_names = {it["name"] for it in items}
    durable_multi, durable_base = durable_ninja_names(ninja)
    missing_multi = sorted(durable_multi - reg_names)
    missing_base = sorted(durable_base - reg_names)
    if missing_multi or missing_base:
        raise BuildError("MISSING durable ninja variant names (validation 2 failed): "
                         "multi=%s base=%s" % (missing_multi, missing_base))

    # ---- HARVEST-GAP GUARD (D-0022): gem/option-defined uniques poe.ninja folds into ONE
    # line (variant=null + many optional gem-level mods) are invisible to durable_ninja_names.
    # WARN (non-fatal) about any folded-gem name absent from the roster so a future league's new
    # such unique is caught; the recipe itself is authored by hand (defining_gem_level). ----
    folded = detect_folded_gem_variants(league)
    folded_unregistered = sorted(folded - reg_names)
    if folded_unregistered:
        sys.stderr.write(
            "  [D-0022 HARVEST-GAP] poe.ninja folds these gem-level-defined uniques into one "
            "line (variant=null); they need a hand-authored defining_gem_level recipe: %s\n"
            % folded_unregistered)

    # ---- coverage stats ----
    by_class = OrderedDict()
    for c in CLASS_ORDER:
        n = sum(1 for it in items if it["class"] == c)
        if n:
            by_class[c] = n
    by_source = OrderedDict()
    for s in ("ninja-harvest", "primary-stat", "crosscheck"):
        by_source[s] = sum(1 for it in items if it["source"] == s)
    fb = sum(1 for nm in ninja if nm.startswith("Foulborn "))
    links_names = sum(1 for nm, r in ninja.items()
                      if r.get("links_present") and not nm.startswith("Foulborn "))

    coverage = OrderedDict([
        ("registry_items", len(items)),
        ("by_class", by_class),
        ("by_source", by_source),
        ("defining_stat_ids", len(stat_ids)),
        ("defining_stat_ids_all_resolve", True),
        ("durable_ninja_multi_variant", len(durable_multi)),
        ("durable_ninja_base_variant", len(durable_base)),
        ("durable_ninja_all_present", True),
        ("crosscheck_dropped", [OrderedDict([("name", n), ("reason", r)]) for n, r in dropped]),
        ("excluded_foulborn_names", fb),
        ("links_variant_names_handled_by_engine", links_names),
        # D-0022 harvest-gap guard: names poe.ninja FOLDS into one gem-level line (the class the
        # auto-harvest misses); *_unregistered must stay [] (each folded name has a hand recipe).
        ("folded_gem_variant_names", sorted(folded)),
        ("folded_gem_variant_unregistered", folded_unregistered),
        ("ninja_names_harvested", len(ninja)),
    ])

    meta = OrderedDict([
        ("schema", SCHEMA_VERSION),
        ("generated", time.strftime("%Y-%m-%dT%H:%M:%S%z")),
        ("generator", "tools/build_variant_registry.py"),
        ("decision", "D-0019 (variant-unique registry + timeless-jewel handling)"),
        ("ninja_league", league),
        ("ninja_endpoint", STASH),
        ("ninja_types", NINJA_TYPES),
        ("ninja_harvest_mode", "live-refresh" if refresh else "cached-dumps"),
        ("ninja_harvest_status", harvest_status),
        ("stats_schema", "public/api/_data/trade_stats.json"),
        ("items_dump", "research/data/trade_items.json"),
        ("runtime_use", "Runtime reads ONLY this file for variant recipes; no network."),
        ("source_tier_policy",
         "PRIMARY = poe.ninja Unique* API + bundled trade stat schema (every defining "
         "stat_id validated against trade_stats.json). CROSS-CHECK = community roster "
         "(variant-crosscheck.md), merged ONLY where the recipe resolves; such rows carry "
         "a crosscheck_tags [NOT FROM SOURCE - <where>] flag. Wiki/community claims are "
         "never presented as primary."),
        ("classes", CLASS_ORDER),
        ("class_notes", OrderedDict([
            ("seed-jewel", "timeless jewels; exact displayed-seed (min=max) + conqueror id; "
                           "ninja floor-only."),
            ("notable-jewel", "OPTION stat (Allocates / keystone radius / ring size); "
                              "pre-flattened base|opt; ninja floor-only."),
            ("socket-defined", "exact abyssal-socket / added-passive COUNT; ninja enumerates "
                               "count lines (map by observed count, labels not always literal)."),
            ("roll-defined", "value = which/what the copy rolled (aura combo, notables, own "
                             "rolls, or which gem its '+# to Level of all <Gem> Gems' names -- "
                             "Replica Dragonfang, D-0022); ninja floors it; price from the copy's mods."),
            ("mod-variant", "poe.ninja enumerates discrete variant/base lines; map the owned "
                            "copy to the line; that line's chaosValue is the price."),
            ("links", "5L/6L price variance (237 uniques this league) is handled GENERICALLY "
                      "by the engine's max_link>=5 filter (D-0003); NOT enumerated here. Items "
                      "that also vary by links carry also_links:true."),
        ])),
        ("foulborn_note",
         "The %d league-transient 'Foulborn ' rolled-mod copies (variant-ninja.md sec 6, "
         "[INFERRED] league noise, group under a different name) are EXCLUDED from this "
         "durable registry; regenerate per league." % fb),
        ("coverage", coverage),
    ])

    registry = OrderedDict([("_meta", meta), ("items", items)])
    return registry, coverage, dropped


def durable_ninja_names(ninja):
    """The validation targets: non-Foulborn names poe.ninja enumerates with >=2 variant
    strings (multi-variant) or >=2 baseTypes (base-variant)."""
    multi, base = set(), set()
    for nm, r in ninja.items():
        if nm.startswith("Foulborn "):
            continue
        vlabels = {vl["variant"] for vl in r.get("variant_lines", [])}
        if len(vlabels) >= 2:
            multi.add(nm)
        if len(r.get("bases", set())) >= 2:
            base.add(nm)
    return multi, base


def main():
    ap = argparse.ArgumentParser(description="Build DivTally's variant-unique registry (D-0019)")
    ap.add_argument("--league", default=None, help="league name (default: live-resolve / Allflame)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch ninja Unique* overviews live")
    ap.add_argument("--offline", action="store_true", help="never touch the network (use cached dumps + default league)")
    ap.add_argument("--check", action="store_true", help="build + validate in memory; do NOT write the artifact")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    league, how = resolve_league(args.league, args.offline)
    print("league: %s (%s)" % (league, how))

    schema = Schema(STATS_SCHEMA)
    print("schema: %s (%d ids)" % (os.path.relpath(STATS_SCHEMA, ROOT), len(schema._by_id)))

    ninja, harvest_status = harvest_ninja(league, args.refresh and not args.offline)
    print("ninja: %d names harvested (%s)"
          % (len(ninja), ", ".join("%s=%s" % (k, v) for k, v in harvest_status.items())))

    registry, coverage, dropped = assemble(schema, ninja, league, harvest_status, args.refresh)

    print("\n=== COVERAGE ===")
    print(json.dumps(coverage, indent=2))
    if dropped:
        print("dropped (recipe unresolved):", dropped)

    if args.check:
        print("\n--check: validated OK, not written.")
        return 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    # newline="\n": force LF so the committed artifact is byte-identical on any platform
    # (Windows text mode would otherwise emit CRLF and defeat cross-machine determinism).
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("\nwrote %s (%d items, %d bytes)"
          % (os.path.relpath(args.out, ROOT), len(registry["items"]),
             os.path.getsize(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
