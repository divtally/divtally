"""Turn a poe.ninja PoE2 build/character URL into a normalised item list.

URL shape (what the user pastes):
    https://poe.ninja/poe2/builds/<slug>/character/<account>/<charName>?i=N

Flow:
    /poe2/api/data/index-state                      -> snapshot version + name for slug
    /poe2/api/builds/<version>/character?account=.. -> full character JSON
"""
import re
import urllib.parse
from typing import List, Optional, Tuple

import requests

from . import cache, util
from .models import (CAT_GEM, CAT_MAGIC, CAT_NORMAL, CAT_RARE, CAT_RUNE,
                     CAT_UNIQUE, FRAME_RARITY, BuildMeta, Item)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 buildpricechecker/0.1")
INDEX_STATE = "https://poe.ninja/poe2/api/data/index-state"

# itemSlot int -> friendly name (best effort; inventoryId is preferred when present)
_INVENTORY_NAMES = {
    "Weapon": "Weapon", "Offhand": "Off-hand", "Weapon2": "Weapon (swap)",
    "Offhand2": "Off-hand (swap)", "Helm": "Helmet", "BodyArmour": "Body Armour",
    "Gloves": "Gloves", "Boots": "Boots", "Belt": "Belt", "Amulet": "Amulet",
    "Ring": "Ring", "Ring2": "Ring", "Flask": "Flask",
}


class PoeNinjaError(RuntimeError):
    pass


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
            "like https://poe.ninja/poe2/builds/<league>/character/<account>/<name>")
    parts = [p for p in parsed.path.split("/") if p]
    if "poe2" not in parts:
        raise PoeNinjaError(
            "this looks like a Path of Exile 1 link; this tool only prices PoE2 builds "
            "(URL should contain '/poe2/').")
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
    account = urllib.parse.unquote(parts[bi + 3])
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
    return (f"https://poe.ninja/poe2/builds/{slug}/character/"
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
        longer snapshots cannot be priced and raise a clear error.
        """
        idx = self.index_state()
        for sv in idx.get("snapshotVersions", []):
            if sv.get("url") == slug:
                league = next((b["name"] for b in idx.get("buildLeagues", [])
                               if b.get("url") == slug), sv.get("name", slug))
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
        url = f"https://poe.ninja/poe2/api/builds/{version}/character"
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
    """poe.ninja PoE2 economy prices (no pathofexile trade API -> no ban risk). All prices
    returned in Exalted. One GET per category (cached 30 min):
      /poe2/api/economy/exchange/current/overview?league=<DISPLAY NAME>&type=<Category>
    A line's primaryValue is in Divine; Exalted = primaryValue * core.rates.exalted.
    """
    _OVERVIEW = "https://poe.ninja/poe2/api/economy/exchange/current/overview"

    def __init__(self, league_name: str, client: Optional["PoeNinjaClient"] = None):
        self.league = (league_name or "").strip()
        self._client = client or PoeNinjaClient()
        self._cache: dict = {}    # category -> {by_id:{id:ex}, by_name:{name_lc:id}, ex_per_div}

    def _load(self, category: str) -> dict:
        if category in self._cache:
            return self._cache[category]
        out = {"by_id": {}, "by_name": {}, "ex_per_div": None}
        if self.league:
            try:
                data = cache.cached(
                    f"poeninja:econ:{self.league}:{category}", 1800,
                    lambda: self._client._get(self._OVERVIEW,
                                              {"league": self.league, "type": category}))
            except Exception:
                data = None
            if isinstance(data, dict):
                core = data.get("core", {}) or {}
                out["ex_per_div"] = (core.get("rates", {}) or {}).get("exalted")
                id_name = {}
                for it in (data.get("items", []) or []) + (core.get("items", []) or []):
                    if it.get("id"):
                        id_name[it["id"]] = it.get("name", "")
                for ln in (data.get("lines", []) or []):
                    cid, pv = ln.get("id"), ln.get("primaryValue")
                    if cid is None or pv is None:
                        continue
                    out["by_id"][cid] = (pv * out["ex_per_div"]) if out["ex_per_div"] else None
                    nm = id_name.get(cid, "")
                    if nm:
                        out["by_name"][nm.lower()] = cid
        self._cache[category] = out
        return out

    def ex_by_id(self, category: str, cid: str) -> Optional[float]:
        return self._load(category)["by_id"].get(cid)

    def ex_by_name(self, category: str, name: str) -> Optional[float]:
        c = self._load(category)
        cid = c["by_name"].get((name or "").lower())
        return c["by_id"].get(cid) if cid else None


# ---- normalisation -------------------------------------------------------
def _categorise(d: dict, group: str) -> str:
    ft = d.get("frameType")
    if group == "gem" or ft == 4:
        return CAT_GEM
    if ft == 5:                       # currency frame -> rune / soul core
        return CAT_RUNE
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
    """Active gem level from its 'Level' property ('20 (Max)' / '19' / '1' -> int)."""
    for p in d.get("properties", []) or []:
        if (p.get("name") or "").strip().lower() == "level":
            vals = p.get("values") or []
            if vals and vals[0]:
                m = re.match(r"\s*(\d+)", str(vals[0][0]))
                if m:
                    return int(m.group(1))
    return 0


def _is_lineage(d: dict) -> bool:
    """A lineage support gem is tagged '[LineageSupports|Lineage]' in its properties."""
    for p in d.get("properties", []) or []:
        if "LineageSupports" in (p.get("name") or ""):
            return True
    return False


# Mod buckets that are all "explicit-style" on-item modifiers and searchable as such on
# trade. poe.ninja splits them into separate arrays; the trade stat dict matches their text
# to the explicit/fractured groups, so we fold them together. Without this, corrupted/
# desecrated Time-Lost jewels (whose affixes live entirely in desecratedMods) and any
# fractured/crafted rolls would be invisible to the pricer ("no trade filter matches").
# (bucket key -> trade2 stat-group prefix). The group matters: an enchant and an explicit can
# share IDENTICAL display text but map to DIFFERENT stat ids (enchant.stat_X vs explicit.stat_X),
# so each mod must be searched in its OWN group or the search returns nothing.
_EXPLICIT_MOD_KEYS = (("explicitMods", "explicit"), ("craftedMods", "crafted"),
                      ("desecratedMods", "desecrated"), ("fracturedMods", "fractured"),
                      ("enchantMods", "enchant"))


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
        rune_mods=d.get("runeMods", []) or [],
        mods_explicit=(d.get("mods", {}) or {}).get("explicit", []) or [],
        corrupted=bool(d.get("corrupted")),
        ilvl=int(d.get("ilvl", 0) or 0),
        support=bool(d.get("support")),
        icon=d.get("icon", "") or "",
        defences=_defences(d),
        gem_level=_gem_level(d),
        is_lineage=_is_lineage(d),
        raw=d,
    )


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
        # runes / soul cores live INSIDE equipment as socketed frame-5 items (poe.ninja does
        # NOT list them top-level), so extract them here or their cost is dropped from the build.
        for si in (d.get("socketedItems") or []):
            if isinstance(si, dict) and (si.get("frameType") == 5 or _categorise(si, "rune") == CAT_RUNE):
                items.append(_make_item(si, "rune"))
    for entry in data.get("flasks", []):
        d = entry.get("itemData")
        if d:
            items.append(_make_item(d, "flask"))
    for entry in data.get("jewels", []):
        d = entry.get("itemData")
        if d:
            items.append(_make_item(d, "jewel"))
    # gems: each skills[] entry is a GROUP — allGems[0] is the active skill, the rest are
    # its support gems. Build ONE active-skill Item per group (sockets == #supports), and
    # attach the support list (name + lineage flag) so the UI can show it + price lineages.
    seen_skill = set()
    for sk in data.get("skills", []):
        allg = sk.get("allGems", []) or []
        if not allg:
            continue
        active_d = allg[0].get("itemData", allg[0])
        if active_d.get("support"):              # safety: the first gem should be the skill
            continue
        active = _make_item(active_d, "gem")
        sups = []
        for g in allg[1:]:
            gd = g.get("itemData", g)
            sups.append({"name": gd.get("baseType") or gd.get("typeLine") or "",
                         "lineage": _is_lineage(gd), "icon": gd.get("icon") or ""})
        active.supports = sups
        active.gem_sockets = min(len(sups), 5)
        sig = (active.base_type, active.gem_level, tuple(s["name"] for s in sups))
        if sig in seen_skill:                    # collapse duplicate setups (e.g. weapon swap)
            continue
        seen_skill.add(sig)
        items.append(active)

    # runes inside equipment are returned as their own frame-5 items already; but
    # equipment lines with frameType 5 ARE the runes. Re-tag group for clarity.
    for it in items:
        if it.category == CAT_RUNE and it.group == "equipment":
            it.group = "rune"
    return meta, items


def dedupe_runes(items: List[Item]) -> List[Item]:
    """Collapse identical runes into a single line with count. (Skill gems are already
    grouped one-per-skill in normalize and must NOT be merged.)"""
    out: List[Item] = []
    index = {}
    for it in items:
        if it.category == CAT_RUNE:
            key = (it.category, it.base_type, it.support)
            if key in index:
                index[key].count += 1
                continue
            index[key] = it
        out.append(it)
    return out
