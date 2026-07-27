"""Turn a poe.ninja PoE1 build/character URL into a normalised item list, and read the
poe.ninja PoE1 economy (currency rates + gem prices + UNIQUE prices by name).

VENDORED + ADAPTED from bpc/poeninja.py:
  * HTTP goes through the stdlib `_http` helper (no `requests`).
  * `PoeNinjaEconomy` gains UNIQUE-overview pricing (UniqueWeapon/Armour/Accessory/Flask/
    Jewel) so the public build can price uniques BY NAME off poe.ninja -- the local build
    priced uniques via a trade search (forbidden server-side here).
  * Adds `current_challenge_league()` (index-state economyLeagues) so a PoB import with no
    league can pick a sensible default without a trade `data/leagues` call.
The character-fetch + normalize logic (frameType routing, sockets/links, gem grouping,
GRANTED detection, host-item index) is verbatim -- it is pure poe.ninja, never trade.
"""
import re
import urllib.parse
from collections import Counter
from typing import List, Optional, Tuple

from . import cache, util
from ._http import HttpError, get_json
from .models import (CAT_GEM, CAT_MAGIC, CAT_NORMAL, CAT_RARE,
                     CAT_UNIQUE, FRAME_RARITY, BuildMeta, Item)

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
    discriminator is converted; any other `#` is left alone."""
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


class PoeNinjaClient:
    def __init__(self):
        pass

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        try:
            return get_json(url, params=params, timeout=30,
                            headers={"Referer": "https://poe.ninja/poe1/economy"})
        except HttpError as e:
            raise PoeNinjaError(str(e))

    def index_state(self) -> dict:
        def producer():
            data = self._get(INDEX_STATE)
            if not isinstance(data, dict) or not data.get("snapshotVersions"):
                raise PoeNinjaError("poe.ninja returned an empty index (the site may be "
                                    "deploying); try again in a minute.")
            return data
        return cache.cached("poeninja:index-state", 600, producer)

    def economy_leagues(self) -> List[dict]:
        """[{name, url, displayName}] of leagues poe.ninja tracks economy for."""
        try:
            return self.index_state().get("economyLeagues", []) or []
        except Exception:
            return []

    def current_challenge_league(self) -> str:
        """First non-perma economy league name (the current challenge league), for PoB
        imports which carry no league. Falls back to 'Standard'."""
        for l in self.economy_leagues():
            nm = l.get("name") or ""
            if nm and nm not in ("Standard", "Hardcore", "Ruthless", "Hardcore Ruthless"):
                return nm
        return "Standard"

    def resolve_snapshot(self, slug: str) -> Tuple[str, str, str]:
        """slug -> (version, snapshotName, leagueDisplayName)."""
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

    def _snapshot_candidates(self, slug: str):
        """The snapshots to try for a character link, in order. Special overview slugs
        ("streamers" etc. - website-only views whose character API 404s) fall back through
        the REAL leagues' exp snapshots: a streamer's character lives in its home league."""
        idx = self.index_state()
        svs = idx.get("snapshotVersions", [])
        leagues = idx.get("buildLeagues", [])

        def league_name(url):
            return next((b.get("displayName") or b.get("name")
                         for b in leagues if b.get("url") == url), url)

        out = []
        matches = [sv for sv in svs if sv.get("url") == slug]
        primary = next((m for m in matches if m.get("type") == "exp"),
                       matches[0] if matches else None)
        if primary is not None and primary.get("version") and primary.get("snapshotName"):
            out.append((primary["version"], primary["snapshotName"], league_name(slug)))
        # fallbacks: every build league's exp snapshot, current-league order, no duplicates
        seen = {(v, s) for v, s, _ in out}
        for b in leagues:
            sv = next((m for m in svs if m.get("url") == b.get("url")
                       and m.get("type") == "exp"), None)
            if sv and sv.get("version") and sv.get("snapshotName"):
                key = (sv["version"], sv["snapshotName"])
                if key not in seen:
                    seen.add(key)
                    out.append((sv["version"], sv["snapshotName"],
                                b.get("displayName") or b.get("name") or b.get("url")))
        if not out:
            known = ", ".join(sorted({sv.get("url", "") for sv in svs}))
            raise PoeNinjaError(
                f"league slug {slug!r} is not in poe.ninja's current snapshots. Known: {known}")
        return out

    def fetch_character(self, slug: str, account: str, character: str) -> dict:
        last_err = None
        for version, snapname, league in self._snapshot_candidates(slug)[:8]:
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
                d["_league"] = league
                d["_cache_key"] = ckey
                return d
            try:
                data = cache.cached(ckey, 1800, producer)
                data["_league"] = league
                data["_cache_key"] = ckey
                return data
            except Exception as e:                      # 404 under this overview -> next league
                last_err = e
                continue
        raise last_err if last_err else PoeNinjaError(
            f"could not locate {account}/{character} in any current poe.ninja snapshot.")


class PoeNinjaEconomy:
    """poe.ninja PoE1 economy prices (no pathofexile trade API -> no ban risk). All prices
    returned in CHAOS. Endpoints (docs/research/economy.md):
      * fungible currency: /poe1/api/economy/exchange/current/overview?type=Currency
        -> {core, items, lines}; a line's `primaryValue` is already the price in chaos.
      * variant-bearing items: /poe1/api/economy/stash/current/item/overview?type=SkillGem
        (and Unique* / Jewel) -> {lines:[{name, baseType, variant, chaosValue, ...}]}.
    """
    _EXCHANGE = "https://poe.ninja/poe1/api/economy/exchange/current/overview"
    _STASH = "https://poe.ninja/poe1/api/economy/stash/current/item/overview"
    # Unique overviews merged into one name index (a build's unique is matched by name).
    _UNIQUE_TYPES = ("UniqueWeapon", "UniqueArmour", "UniqueAccessory",
                     "UniqueFlask", "UniqueJewel")

    def __init__(self, league_name: str, client: Optional["PoeNinjaClient"] = None):
        self.league = (league_name or "").strip()
        self._client = client or PoeNinjaClient()
        self._exchange: dict = {}     # category -> {by_id:{id:chaos}, by_name:{name_lc:id}, images:{id:img}}
        self._gems: Optional[dict] = None    # name_lc -> [line, ...]
        self._uniques: Optional[dict] = None  # name_lc -> [line, ...]

    # ---- fungible currency (exchange endpoint) ----
    def _load_exchange(self, category: str) -> dict:
        if category in self._exchange:
            return self._exchange[category]
        out = {"by_id": {}, "by_name": {}, "images": {}}
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
                id_name, id_img = {}, {}
                for it in (data.get("items", []) or []) + (core.get("items", []) or []):
                    if it.get("id"):
                        id_name[it["id"]] = it.get("name", "")
                        if it.get("image"):
                            id_img[it["id"]] = it["image"]
                out["images"] = id_img
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

    def currency_image(self, cid: str) -> str:
        """poe.ninja image URL for a currency id ('chaos'/'divine'), or ''. poe.ninja
        serves these off web.poecdn.com; the path may be absolute or need the CDN prefix."""
        img = self._load_exchange("Currency")["images"].get(cid, "")
        if not img:
            return ""
        return img if img.startswith("http") else "https://web.poecdn.com" + img

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
        {chaos, divine, listing_count, variant, level, quality, corrupted} or None."""
        gems = self._load_gems()
        lines = gems.get((name or "").lower())
        if not lines and name and not name.lower().endswith("support"):
            lines = gems.get((name + " Support").lower())
        if not lines:
            return None
        best, best_score = None, None
        for ln in lines:
            gl = ln.get("gemLevel") or 0
            gq = ln.get("gemQuality") or 0
            gc = bool(ln.get("corrupted"))
            score = abs(gl - level) + 0.3 * abs(gq - quality) + (100 if gc != corrupted else 0)
            if best_score is None or score < best_score:
                best_score, best = score, ln
        return {"chaos": best.get("chaosValue"), "divine": best.get("divineValue"),
                "listing_count": best.get("listingCount") or 0,
                "variant": best.get("variant", ""), "level": best.get("gemLevel"),
                "quality": best.get("gemQuality") or 0, "corrupted": bool(best.get("corrupted"))}

    # ---- uniques (stash item-overview endpoint, merged across Unique* types) ----
    def _load_uniques(self) -> dict:
        if self._uniques is not None:
            return self._uniques
        out: dict = {}
        if self.league:
            for t in self._UNIQUE_TYPES:
                try:
                    data = cache.cached(
                        f"poeninja:econ1i:{self.league}:{t}", 1800,
                        lambda t=t: self._client._get(self._STASH,
                                                      {"league": self.league, "type": t}))
                except Exception:
                    data = None
                if isinstance(data, dict):
                    for ln in (data.get("lines", []) or []):
                        nm = (ln.get("name") or "").lower()
                        if nm:
                            out.setdefault(nm, []).append(ln)
        self._uniques = out
        return out

    @staticmethod
    def _variant_tokens(s: str) -> set:
        return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 3}

    def unique_price(self, name: str, mod_text: str = "", base_type: str = "") -> Optional[dict]:
        """Price a unique BY NAME off the merged poe.ninja unique overviews. Best-effort for
        variant uniques (Watcher's Eye, Impresence, Mageblood, ...):

          * exactly one line for the name          -> point estimate (matched='name').
          * several lines but one clearly matches   -> that variant (matched='variant'):
            picked when its `variant` string tokens are contained in the item's mod text and
            it is the sole strong match (e.g. Impresence 'Lightning', Mageblood '5 Flasks').
          * several lines, ambiguous                -> a RANGE across variants (matched='range',
            min..high of the variant chaos values) with a low-confidence note -- never a
            fabricated point estimate (the 'no misleading number' guardrail).

        Returns {matched, variant, chaos_min, chaos_median, chaos_high, listing_count,
        n_variants, count} in CHAOS, or None if the name is not listed on poe.ninja."""
        lines = self._load_uniques().get((name or "").lower())
        if not lines:
            return None
        # If a base type is known, keep only lines on that base (disambiguates same-name
        # uniques across bases; harmless when all lines share the base).
        if base_type:
            bt = base_type.lower()
            same_base = [ln for ln in lines if (ln.get("baseType") or "").lower() == bt]
            if same_base:
                lines = same_base
        vals = sorted(float(ln["chaosValue"]) for ln in lines
                      if isinstance(ln.get("chaosValue"), (int, float)))
        if not vals:
            return None
        n = len(lines)
        if n == 1:
            ln = lines[0]
            return {"matched": "name", "variant": ln.get("variant") or "",
                    "chaos_min": vals[0], "chaos_median": vals[0], "chaos_high": vals[0],
                    "listing_count": ln.get("listingCount") or 0, "n_variants": 1,
                    "count": ln.get("count") or 0}
        # Try to disambiguate variants against the item's mod text.
        item_tokens = self._variant_tokens(mod_text)
        scored = []
        for ln in lines:
            vt = self._variant_tokens(ln.get("variant") or "")
            if vt and item_tokens:
                cover = len(vt & item_tokens) / len(vt)
            else:
                cover = 0.0
            scored.append((cover, ln))
        scored.sort(key=lambda t: t[0], reverse=True)
        top_cover, top_ln = scored[0]
        second_cover = scored[1][0] if len(scored) > 1 else 0.0
        if top_cover >= 0.6 and top_cover > second_cover and isinstance(top_ln.get("chaosValue"), (int, float)):
            c = float(top_ln["chaosValue"])
            return {"matched": "variant", "variant": top_ln.get("variant") or "",
                    "chaos_min": c, "chaos_median": c, "chaos_high": c,
                    "listing_count": top_ln.get("listingCount") or 0, "n_variants": n,
                    "count": top_ln.get("count") or 0}
        return {"matched": "range", "variant": "",
                "chaos_min": vals[0], "chaos_median": util.median(vals),
                "chaos_high": util.percentile(vals, 90), "listing_count": 0,
                "n_variants": n, "count": sum(ln.get("count") or 0 for ln in lines)}


# ---- normalisation (VERBATIM from bpc/poeninja.py; pure poe.ninja transform) ----------
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
    Links = sockets sharing a `group`; max_link = size of the largest group."""
    socks = d.get("sockets") or []
    if not socks:
        return [], 0, 0, []
    groups = Counter(s.get("group") for s in socks)
    max_link = max(groups.values()) if groups else 0
    colours = [s.get("sColour", "") for s in socks]
    return list(socks), max_link, len(socks), colours


def _defences(d: dict) -> dict:
    """The item's total Armour/Evasion/Energy Shield/Ward (searchable value totals)."""
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
    for p in d.get("properties", []) or []:
        if (p.get("name") or "").strip().lower() == "level":
            vals = p.get("values") or []
            if vals and vals[0]:
                m = re.match(r"\s*(\d+)", str(vals[0][0]))
                if m:
                    return int(m.group(1))
    return 0


def _gem_quality(d: dict) -> int:
    for p in d.get("properties", []) or []:
        if (p.get("name") or "").strip().lower() == "quality":
            vals = p.get("values") or []
            if vals and vals[0]:
                m = re.search(r"(\d+)", str(vals[0][0]))
                if m:
                    return int(m.group(1))
    return 0


# Mod buckets that are all "explicit-style" on-item modifiers and searchable as such.
_EXPLICIT_MOD_KEYS = (("explicitMods", "explicit"), ("craftedMods", "crafted"),
                      ("fracturedMods", "fractured"), ("enchantMods", "enchant"),
                      ("utilityMods", "explicit"), ("scourgeMods", "scourge"),
                      ("crucibleMods", "crucible"), ("veiledMods", "veiled"))


def _all_explicit_mods(d: dict):
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
    """Map each equipment itemSlot -> host-item info (for grouping gem rows under gear)."""
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
            "name": nm or base,
            "base": base,
            "unique": d.get("frameType") == 3,
        }
    return out


def _provided_gem_index(data: dict) -> Tuple[set, set]:
    """Read `itemProvidedGems` into lookup sets used to flag item-provided gems (D-0006)."""
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
    """True if a `skills[]` gem is item-provided (granted) -- excluded from the trade total."""
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
        if not d:
            continue
        items.append(_make_item(d, "equipment"))
    for entry in data.get("flasks", []):
        d = entry.get("itemData")
        if d:
            items.append(_make_item(d, "flask"))
    for entry in data.get("jewels", []):
        d = entry.get("itemData")
        if d:
            items.append(_make_item(d, "jewel"))
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
        if active_d.get("support"):
            continue
        active = _make_item(active_d, "gem")
        if not active.base_type:
            active.base_type = active.type_line = active_entry.get("name", "") or ""
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
                         "support": bool(gd.get("support")),
                         "granted": _gem_is_granted(g, gd, slot, provided_pairs, provided_names)})
        active.supports = sups
        sig = (active.base_type, active.gem_level, tuple(s["name"] for s in sups))
        if sig in seen_skill:
            continue
        seen_skill.add(sig)
        items.append(active)
    return meta, items
