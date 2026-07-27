"""Turn a poe.ninja PoE1 build/character URL into a normalised item list.

URL shape (what the user pastes):
    https://poe.ninja/poe1/builds/<slug>/character/<account>/<charName>

Flow:
    /poe1/api/data/index-state                      -> snapshot version + name for slug
    /poe1/api/builds/<version>/character?account=.. -> full character JSON

See docs/research/poeninja-poe1.md for the live-verified shapes this depends on.
"""
import re
import urllib.parse
from collections import Counter
from typing import List, Optional, Tuple

import requests

from . import cache, util
from .models import (CAT_GEM, CAT_MAGIC, CAT_NORMAL, CAT_RARE,
                     CAT_UNIQUE, FRAME_RARITY, BuildMeta, Item)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 buildpricechecker/0.1")
INDEX_STATE = "https://poe.ninja/poe1/api/data/index-state"

# itemSlot int -> friendly name (best effort; inventoryId is preferred when present)
_INVENTORY_NAMES = {
    "Weapon": "Weapon", "Offhand": "Off-hand", "Weapon2": "Weapon (swap)",
    "Offhand2": "Off-hand (swap)", "Helm": "Helmet", "BodyArmour": "Body Armour",
    "Gloves": "Gloves", "Boots": "Boots", "Belt": "Belt", "Amulet": "Amulet",
    "Ring": "Ring", "Ring2": "Ring", "Flask": "Flask", "PassiveJewels": "Jewel",
}


class PoeNinjaError(RuntimeError):
    pass


def dash_account(a: str) -> str:
    """Convert a hand-typed `account#1234` discriminator to the dash form `account-1234`
    that the poe.ninja API requires (it 404s on the raw `#`). Only the final `#<digits>`
    discriminator is converted; any other `#` is left alone. Ports poe.ninja's own
    front-end encoder (docs/research/poeninja-poe1.md section 8)."""
    if not a:
        return a
    for i in range(len(a) - 1, -1, -1):
        if a[i].isdigit():
            continue
        return a[:i] + "-" + a[i + 1:] if a[i] == "#" else a
    return a


def parse_build_url(url: str) -> dict:
    """Extract {slug, account, character} from a poe.ninja build URL.

    Accepts full URLs with or without scheme. Raises PoeNinjaError with guidance
    if the link is a build *overview* (no character) or otherwise unrecognised.
    """
    u = url.strip().strip('"').strip("'")
    if not u:
        raise PoeNinjaError("empty URL")
    if not u.startswith("http"):
        u = "https://" + u
    parsed = urllib.parse.urlparse(u)
    host = (parsed.hostname or "").lower()
    if host != "poe.ninja" and not host.endswith(".poe.ninja"):
        raise PoeNinjaError(
            f"not a poe.ninja link: {parsed.netloc or url!r}. Paste a character link "
            "like https://poe.ninja/poe1/builds/<league>/character/<account>/<name>")
    parts = [p for p in parsed.path.split("/") if p]
    if "poe1" not in parts:
        raise PoeNinjaError(
            "this looks like a Path of Exile 2 link; this tool only prices PoE1 builds "
            "(URL should contain '/poe1/').")
    # The path is positional: .../builds/<slug>/character/<account>/<char>.
    # Anchor on 'builds' (not the first 'character' token) so it parses unambiguously.
    try:
        bi = parts.index("builds")
    except ValueError:
        raise PoeNinjaError(f"unrecognised poe.ninja URL (no '/builds/'): {parsed.path}")
    if len(parts) < bi + 5 or parts[bi + 2] != "character":
        raise PoeNinjaError(
            "that looks like a build *overview* link, not a specific character. Open a "
            "character on poe.ninja and copy that page's URL (it contains '/character/').")
    slug = parts[bi + 1]
    account = dash_account(urllib.parse.unquote(parts[bi + 3]))
    character = urllib.parse.unquote(parts[bi + 4])
    return {"slug": slug, "account": account, "character": character}


def build_url_from_cache_key(cache_key: str) -> str:
    """Reconstruct the public poe.ninja character URL from a cache key
    (`poeninja:char:<version>:<account>:<character>`), so a build loaded from disk can
    still link back to its source page. Maps the snapshot version back to its league slug
    via index-state (cached). Best-effort: returns "" if the slug can't be resolved."""
    prefix = "poeninja:char:"
    if not (cache_key or "").startswith(prefix):
        return ""
    parts = cache_key[len(prefix):].split(":")
    if len(parts) < 3:
        return ""
    version, account, character = parts[0], parts[1], ":".join(parts[2:])
    try:
        idx = PoeNinjaClient().index_state()
    except Exception:
        return ""
    slug = next((sv.get("url") for sv in idx.get("snapshotVersions", [])
                 if sv.get("version") == version), "")
    if not slug:
        return ""
    return (f"https://poe.ninja/poe1/builds/{slug}/character/"
            f"{urllib.parse.quote(account)}/{urllib.parse.quote(character)}")


class PoeNinjaClient:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept": "application/json"})

    def index_state(self) -> dict:
        def producer():
            data = self._get(INDEX_STATE)
            if not isinstance(data, dict) or not data.get("snapshotVersions"):
                raise PoeNinjaError("poe.ninja returned an empty index (the site may be "
                                    "deploying); try again in a minute.")
            return data
        return cache.cached("poeninja:index-state", 600, producer)

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        try:
            r = self.s.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            raise PoeNinjaError(f"could not reach poe.ninja: {e}")
        if not r.ok:
            raise PoeNinjaError(f"HTTP {r.status_code} from {r.url}")
        try:
            return r.json()
        except ValueError:
            raise PoeNinjaError(
                f"poe.ninja did not return JSON from {r.url} "
                f"(content-type {r.headers.get('content-type', '?')}); the character "
                "may be private/unindexed, or the site is rate-limiting. Try again.")

    def resolve_snapshot(self, slug: str) -> Tuple[str, str, str]:
        """slug -> (version, snapshotName, leagueDisplayName).

        Looks in snapshotVersions (current leagues). Old leagues that poe.ninja no
        longer snapshots cannot be priced and raise a clear error. PoE1 lists TWO rows
        per league url (type 'exp' and 'depthsolo', sharing version/snapshotName); we
        prefer the 'exp' row for determinism.
        """
        idx = self.index_state()
        matches = [sv for sv in idx.get("snapshotVersions", []) if sv.get("url") == slug]
        sv = next((m for m in matches if m.get("type") == "exp"), matches[0] if matches else None)
        if sv is not None:
            league = next((b.get("displayName") or b.get("name")
                           for b in idx.get("buildLeagues", []) if b.get("url") == slug),
                          sv.get("name", slug))
            version, snapname = sv.get("version"), sv.get("snapshotName")
            if not version or not snapname:
                raise PoeNinjaError(
                    f"poe.ninja snapshot for {slug!r} is missing version/snapshot "
                    "fields (the site's data format may have changed).")
            return version, snapname, league
        known = ", ".join(sorted({sv.get("url", "") for sv in idx.get("snapshotVersions", [])}))
        raise PoeNinjaError(
            f"league slug {slug!r} is not in poe.ninja's current snapshots. "
            f"Known: {known}")

    def fetch_character(self, slug: str, account: str, character: str) -> dict:
        version, snapname, league = self.resolve_snapshot(slug)
        url = f"https://poe.ninja/poe1/api/builds/{version}/character"
        params = {"account": account, "name": character,
                  "overview": snapname, "timeMachine": ""}
        ckey = f"poeninja:char:{version}:{account}:{character}"
        def producer():
            d = self._get(url, params)
            if not isinstance(d, dict) or "items" not in d:
                raise PoeNinjaError(
                    f"poe.ninja returned no item data for {account}/{character}. "
                    "Double-check the link, or the character may be private/unindexed.")
            d["_league"] = league       # persist INSIDE the blob so cache loads keep the
            d["_cache_key"] = ckey      # resolved (display-name) league, not the raw field
            return d
        # cache per character for 30 min (poe.ninja snapshots are not realtime anyway);
        # validation lives in the producer so error/empty responses are never cached.
        data = cache.cached(ckey, 1800, producer)
        data["_league"] = league        # also set on cache hits (older blobs lack the keys)
        data["_cache_key"] = ckey
        return data


class PoeNinjaEconomy:
    """poe.ninja PoE1 economy prices (no pathofexile trade API -> no ban risk). All prices
    returned in CHAOS. TWO endpoints (docs/research/economy.md):
      * bulk / fungible currency:
        /poe1/api/economy/exchange/current/overview?league=<Name>&type=Currency
        -> {core, items, lines}; a line's `primaryValue` is already the price in chaos.
      * variant-bearing items (gems, uniques, cluster jewels, bases):
        /poe1/api/economy/stash/current/item/overview?league=<Name>&type=SkillGem
        -> {lines:[{name, variant, gemLevel, gemQuality, corrupted, chaosValue, ...}]}.
    """
    _EXCHANGE = "https://poe.ninja/poe1/api/economy/exchange/current/overview"
    _STASH = "https://poe.ninja/poe1/api/economy/stash/current/item/overview"

    def __init__(self, league_name: str, client: Optional["PoeNinjaClient"] = None):
        self.league = (league_name or "").strip()
        self._client = client or PoeNinjaClient()
        self._exchange: dict = {}     # category -> {by_id:{id:chaos}, by_name:{name_lc:id}}
        self._gems: Optional[dict] = None   # name_lc -> [line, ...]

    # ---- fungible currency (exchange endpoint) ----
    def _load_exchange(self, category: str) -> dict:
        if category in self._exchange:
            return self._exchange[category]
        out = {"by_id": {}, "by_name": {}}
        if self.league:
            try:
                data = cache.cached(
                    f"poeninja:econ1x:{self.league}:{category}", 1800,
                    lambda: self._client._get(self._EXCHANGE,
                                              {"league": self.league, "type": category}))
            except Exception:
                data = None
            if isinstance(data, dict):
                core = data.get("core", {}) or {}
                id_name = {}
                for it in (data.get("items", []) or []) + (core.get("items", []) or []):
                    if it.get("id"):
                        id_name[it["id"]] = it.get("name", "")
                for ln in (data.get("lines", []) or []):
                    cid, pv = ln.get("id"), ln.get("primaryValue")
                    if cid is None or pv is None:
                        continue
                    out["by_id"][cid] = pv          # already CHAOS (no rate multiply)
                    nm = id_name.get(cid, "")
                    if nm:
                        out["by_name"][nm.lower()] = cid
        self._exchange[category] = out
        return out

    def chaos_by_id(self, category: str, cid: str) -> Optional[float]:
        return self._load_exchange(category)["by_id"].get(cid)

    def chaos_by_name(self, category: str, name: str) -> Optional[float]:
        c = self._load_exchange(category)
        cid = c["by_name"].get((name or "").lower())
        return c["by_id"].get(cid) if cid else None

    # ---- gems (stash item-overview endpoint) ----
    def _load_gems(self) -> dict:
        if self._gems is not None:
            return self._gems
        out: dict = {}
        if self.league:
            try:
                data = cache.cached(
                    f"poeninja:econ1i:{self.league}:SkillGem", 1800,
                    lambda: self._client._get(self._STASH,
                                              {"league": self.league, "type": "SkillGem"}))
            except Exception:
                data = None
            if isinstance(data, dict):
                for ln in (data.get("lines", []) or []):
                    nm = (ln.get("name") or "").lower()
                    if nm:
                        out.setdefault(nm, []).append(ln)
        self._gems = out
        return out

    def gem_price(self, name: str, level: int = 20, quality: int = 0,
                  corrupted: bool = False) -> Optional[dict]:
        """Best-matching SkillGem bucket for a socketed gem. Returns
        {chaos, divine, listing_count, variant, level, quality, corrupted} or None.

        Match rule (docs/research/economy.md 3c): exact `name` (case-insensitive), then
        the nearest level/quality bucket with a corrupted-match preference. PoB exports a
        support's `nameSpec` WITHOUT the 'Support' suffix, so we retry with it appended."""
        gems = self._load_gems()
        lines = gems.get((name or "").lower())
        if not lines and name and not name.lower().endswith("support"):
            lines = gems.get((name + " Support").lower())
        if not lines:
            return None
        best, best_score = None, None
        for ln in lines:
            gl = ln.get("gemLevel") or 0
            gq = ln.get("gemQuality") or 0          # absent (None) means 0 quality
            gc = bool(ln.get("corrupted"))          # absent (None) means not corrupted
            score = abs(gl - level) + 0.3 * abs(gq - quality) + (100 if gc != corrupted else 0)
            if best_score is None or score < best_score:
                best_score, best = score, ln
        return {"chaos": best.get("chaosValue"), "divine": best.get("divineValue"),
                "listing_count": best.get("listingCount") or 0,
                "variant": best.get("variant", ""), "level": best.get("gemLevel"),
                "quality": best.get("gemQuality") or 0, "corrupted": bool(best.get("corrupted"))}


# ---- normalisation -------------------------------------------------------
def _categorise(d: dict, group: str) -> str:
    ft = d.get("frameType")
    if group == "gem" or ft == 4:
        return CAT_GEM
    if ft == 3:
        return CAT_UNIQUE
    if ft == 2:
        return CAT_RARE
    if ft == 1:
        return CAT_MAGIC
    return CAT_NORMAL


def _slot_name(d: dict) -> str:
    inv = d.get("inventoryId", "")
    return _INVENTORY_NAMES.get(inv, inv or "?")


def _sockets_info(d: dict) -> Tuple[list, int, int, list]:
    """Return (sockets, max_link, total_sockets, colours) from an item's `sockets` array.
    Links = sockets sharing a `group`; max_link = size of the largest group. PoE1-only
    (PoE2 has no linked sockets) and a major price component for 5L/6L gear."""
    socks = d.get("sockets") or []
    if not socks:
        return [], 0, 0, []
    groups = Counter(s.get("group") for s in socks)
    max_link = max(groups.values()) if groups else 0
    colours = [s.get("sColour", "") for s in socks]
    return list(socks), max_link, len(socks), colours


def _defences(d: dict) -> dict:
    """The item's total Armour/Evasion/Energy Shield/Ward (the searchable value totals,
    incl. affix + quality), read from its display properties."""
    out = {}
    for p in d.get("properties", []) or []:
        nm = util.strip_rich(p.get("name", "")).strip().lower()
        vals = p.get("values") or []
        if not vals or not vals[0]:
            continue
        digits = re.sub(r"[^\d]", "", str(vals[0][0]))
        if not digits:
            continue
        v = int(digits)
        if v <= 0:
            continue
        if nm == "armour":
            out["ar"] = v
        elif nm in ("evasion rating", "evasion"):
            out["ev"] = v
        elif nm == "energy shield":
            out["es"] = v
        elif "ward" in nm:
            out["ward"] = v
    return out


def _gem_level(d: dict) -> int:
    """Gem level from its 'Level' property ('20 (Max)' / '19' / '1' -> int)."""
    for p in d.get("properties", []) or []:
        if (p.get("name") or "").strip().lower() == "level":
            vals = p.get("values") or []
            if vals and vals[0]:
                m = re.match(r"\s*(\d+)", str(vals[0][0]))
                if m:
                    return int(m.group(1))
    return 0


def _gem_quality(d: dict) -> int:
    """Gem quality from its 'Quality' property ('+20%' -> 20)."""
    for p in d.get("properties", []) or []:
        if (p.get("name") or "").strip().lower() == "quality":
            vals = p.get("values") or []
            if vals and vals[0]:
                m = re.search(r"(\d+)", str(vals[0][0]))
                if m:
                    return int(m.group(1))
    return 0


# Mod buckets that are all "explicit-style" on-item modifiers and searchable as such on
# trade. poe.ninja splits them into separate arrays; the trade stat dict matches their text
# to the right stat group, so we fold them together (with the group tag per mod). Without
# this, a fractured/crafted/enchant roll would be invisible to the pricer. `utilityMods`
# is the flask's utility line (PoE1-only; missing on gear) -- added so a unique/enchanted
# flask's defining line is visible. PoE2's `desecratedMods` bucket is DROPPED (no Desecrated
# stat group in PoE1). (bucket key -> trade stat-group prefix). An enchant and an explicit
# can share IDENTICAL text but map to DIFFERENT ids (enchant.stat_X vs explicit.stat_X), so
# each is searched in its OWN group.
_EXPLICIT_MOD_KEYS = (("explicitMods", "explicit"), ("craftedMods", "crafted"),
                      ("fracturedMods", "fractured"), ("enchantMods", "enchant"),
                      ("utilityMods", "explicit"), ("scourgeMods", "scourge"),
                      ("crucibleMods", "crucible"), ("veiledMods", "veiled"))


def _all_explicit_mods(d: dict):
    """Return (mods, sources) parallel lists. Deduped per (text, group) so the same text in two
    buckets (e.g. an explicit roll AND an enchant) is kept as two distinct, separately-scoped rows."""
    out: List[str] = []
    src: List[str] = []
    seen = set()
    for key, grp in _EXPLICIT_MOD_KEYS:
        for line in (d.get(key) or []):
            if line and (line, grp) not in seen:
                seen.add((line, grp))
                out.append(line)
                src.append(grp)
    return out, src


def _make_item(d: dict, group: str) -> Item:
    ft = d.get("frameType", 0)
    mods, mod_src = _all_explicit_mods(d)
    socks, max_link, total_sockets, colours = _sockets_info(d)
    return Item(
        name=d.get("name", "") or "",
        base_type=d.get("baseType", "") or d.get("typeLine", "") or "",
        type_line=d.get("typeLine", "") or "",
        frame_type=ft,
        rarity=FRAME_RARITY.get(ft, "Unknown"),
        category=_categorise(d, group),
        group=group,
        slot=_slot_name(d),
        explicit_mods=mods,
        mod_src=mod_src,
        implicit_mods=d.get("implicitMods", []) or [],
        mods_explicit=(d.get("mods", {}) or {}).get("explicit", []) or [],
        corrupted=bool(d.get("corrupted")),
        ilvl=int(d.get("ilvl", 0) or 0),
        support=bool(d.get("support")),
        icon=d.get("icon", "") or "",
        defences=_defences(d),
        sockets=socks,
        max_link=max_link,
        total_sockets=total_sockets,
        socket_colours=colours,
        gem_level=_gem_level(d),
        gem_quality=_gem_quality(d),
        raw=d,
    )


def _host_index(data: dict) -> dict:
    """Map each equipment itemSlot -> host-item info, so a skill group (skills[].itemSlot)
    can be grouped under the gear it is socketed into (D-0006). Returns
    {itemSlot -> {inventory_id, slot_label, name, base, unique}}."""
    out: dict = {}
    for entry in data.get("items", []) or []:
        d = entry.get("itemData")
        if not d:
            continue
        inv = d.get("inventoryId", "") or ""
        base = d.get("baseType", "") or d.get("typeLine", "") or ""
        nm = d.get("name", "") or ""
        out[entry.get("itemSlot")] = {
            "inventory_id": inv,
            "slot_label": _INVENTORY_NAMES.get(inv, inv or "?"),
            "name": nm or base,           # unique/rare name, else the base type
            "base": base,
            "unique": d.get("frameType") == 3,
        }
    return out


def _provided_gem_index(data: dict) -> Tuple[set, set]:
    """Read the character JSON's `itemProvidedGems` (gems granted by equipped items) into
    two lookup sets used to flag genuinely item-provided gems (D-0006):
      * pairs        = {(slot, name_lc)}  -- precise slot+name match (preferred)
      * names_noslot = {name_lc}          -- entries whose slot is absent (name-only fallback)
    Each entry is `{slot, gems:[{name, level, quality, isBuiltInSupport}]}`. Verified live in
    `research/data/char_poe1.json`: `[{slot:9, gems:[{name:"Herald of the Hive", ...}]}]`."""
    pairs, names_noslot = set(), set()
    for entry in data.get("itemProvidedGems", []) or []:
        slot = entry.get("slot")
        for g in entry.get("gems", []) or []:
            nm = (g.get("name") or "").strip().lower()
            if not nm:
                continue
            if slot is None:
                names_noslot.add(nm)
            else:
                pairs.add((slot, nm))
    return pairs, names_noslot


def _gem_is_granted(entry: dict, item_data: dict, slot,
                    provided_pairs: set, provided_names: set) -> bool:
    """True if a `skills[]` gem is item-provided (granted) -- so it is EXCLUDED from the
    trade-price total (D-0006). Authoritative signals: the gem's `isBuiltInSupport` flag, or
    a match in the item's `itemProvidedGems` (by slot+name). A gem whose itemData is EMPTY
    (no baseType / typeLine / frameType) cannot be a real socketed tradeable gem -- it exists
    only because an item grants it -- so that is treated as granted too ([INFERRED], but
    strictly safe: every real socketed gem carries a baseType, so this never mis-flags the
    socketed Heralds / Leap Slam the owner reported as wrongly "granted").

    ROOT CAUSE of the owner's bug: the granted flag was NOT computed here at all -- the web
    layer inferred it from `itemData.inventoryId`, which is ALWAYS None for PoE1 skills[]
    gems, so `not "".startswith("SkillSlot")` flagged EVERY gem granted. The engine now owns
    this decision from the character JSON; the UI must read `it.granted` (see feedback1-spec)."""
    if entry.get("isBuiltInSupport"):
        return True
    nm = (entry.get("name") or item_data.get("baseType")
          or item_data.get("typeLine") or "").strip().lower()
    if nm and ((slot, nm) in provided_pairs or nm in provided_names):
        return True
    if not (item_data.get("baseType") or item_data.get("typeLine")
            or item_data.get("frameType")):
        return True
    return False


def normalize(data: dict) -> Tuple[BuildMeta, List[Item]]:
    meta = BuildMeta(
        account=data.get("account", ""),
        character=data.get("name", ""),
        league=data.get("_league", data.get("league", "")),
        char_class=data.get("class", ""),
        level=int(data.get("level", 0) or 0),
        pob_export=data.get("pathOfBuildingExport", "") or "",
        cache_key=data.get("_cache_key", "") or "",
    )
    items: List[Item] = []
    for entry in data.get("items", []):
        d = entry.get("itemData")
        if not d:                                   # skip empty/odd slots (don't crash)
            continue
        items.append(_make_item(d, "equipment"))
        # NOTE (PoE1): equipment `socketedItems` are the GEMS, not runes -- those gems are
        # ALSO enumerated in skills[] and priced there, so we do NOT extract them here (that
        # would double-count). PoE2's frame-5 rune extraction is deleted: PoE1 has no runes.
    for entry in data.get("flasks", []):
        d = entry.get("itemData")
        if d:
            items.append(_make_item(d, "flask"))
    for entry in data.get("jewels", []):
        d = entry.get("itemData")
        if d:
            items.append(_make_item(d, "jewel"))
    # gems: each skills[] entry is a GROUP -- allGems[0] is the active skill, the rest are
    # its support gems. Build ONE active-skill Item per group and attach the support list,
    # each carrying its own level/quality/corruption (PoE1 prices every gem as a real item).
    # D-0006: also attach host-item info (which gear the group is socketed in) + a `granted`
    # flag (item-provided gems, excluded from the trade total) per gem.
    host_by_slot = _host_index(data)
    provided_pairs, provided_names = _provided_gem_index(data)
    seen_skill = set()
    for sk in data.get("skills", []):
        allg = sk.get("allGems", []) or []
        if not allg:
            continue
        slot = sk.get("itemSlot")
        active_entry = allg[0]
        active_d = active_entry.get("itemData", active_entry) or {}
        if active_d.get("support"):              # safety: the first gem should be the skill
            continue
        active = _make_item(active_d, "gem")
        # A genuinely item-provided active (e.g. a Herald granted by a unique ring) has an
        # EMPTY itemData -- its real name lives only on the entry. Recover it so the row is
        # not blank (verified: skills[5] "Herald of the Hive", lvl 30, from Lost Unity).
        if not active.base_type:
            active.base_type = active.type_line = active_entry.get("name", "") or ""
        # allGems entries carry clean top-level level/quality ints; prefer them over props.
        active.gem_level = int(active_entry.get("level", active.gem_level) or 0)
        active.gem_quality = int(active_entry.get("quality", active.gem_quality) or 0)
        active.granted = _gem_is_granted(active_entry, active_d, slot,
                                         provided_pairs, provided_names)
        host = host_by_slot.get(slot)
        if host:
            active.host_slot = host["slot_label"]
            active.host_name = host["name"]
            active.host_base = host["base"]
            active.host_unique = host["unique"]
            active.host_inventory_id = host["inventory_id"]
        sups = []
        for g in allg[1:]:
            gd = g.get("itemData", g) or {}
            s_name = gd.get("baseType") or gd.get("typeLine") or g.get("name") or ""
            sups.append({"name": s_name,
                         "level": int(g.get("level", 0) or 0),
                         "quality": int(g.get("quality", 0) or 0),
                         "corrupted": bool(gd.get("corrupted")),
                         "icon": gd.get("icon") or "",
                         # `support` is the gem's REAL support-ness (a group can hold >1 active,
                         # e.g. two Heralds linked together); `granted` marks a built-in/item-
                         # provided support (excluded from the total, its siblings still count).
                         "support": bool(gd.get("support")),
                         "granted": _gem_is_granted(g, gd, slot, provided_pairs, provided_names)})
        active.supports = sups
        sig = (active.base_type, active.gem_level, tuple(s["name"] for s in sups))
        if sig in seen_skill:                    # collapse duplicate setups (e.g. weapon swap)
            continue
        seen_skill.add(sig)
        items.append(active)
    return meta, items
