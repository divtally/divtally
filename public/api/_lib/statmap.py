"""Map an item's human-readable mods to trade stat-filter ids, so rare items can be
priced by searching for similar items.

This is necessarily approximate: we match explicit mod text against the trade "stats"
dictionary, pick the few most price-relevant ones, and search with min thresholds.

VENDORED from bpc/statmap.py. ONLY CHANGE vs the original: `StatMapper.__init__` takes
the stats-data DICT directly (from refdata.stats_data(), the bundled file) instead of a
TradeClient -- the public build has no trade client. All matching logic is verbatim.
"""
import re
from typing import Dict, List, Optional, Tuple

from . import util

# Some count-of-N mods render SINGULAR at count 1 ("1 Added Passive Skill is a Jewel Socket") but
# the trade schema carries ONLY the PLURAL stat text ("# Added Passive Skills are Jewel Sockets" =
# enchant.stat_4079888060). The singular pattern never equals the plural, and because the mod is an
# ENCHANT the mapper never falls back -> a Medium Cluster Jewel's single jewel socket was silently
# DROPPED from the query (D-0020 R3 F2; same singular/plural class as the R1 Bubonic Trail
# abyssal-socket fix). Normalise the known singular PATTERN(s) to their plural schema form before
# the id lookup in `match()`. The count is preserved (the leading '#' is untouched), so
# util.first_number still reads the item's count for the picker prefill. Done in `match()` (not
# `_build`) so the pattern maps themselves are unchanged (slim == full mapper equality holds).
_SINGULAR_TO_PLURAL = [
    (re.compile(r"# Added Passive Skill is a Jewel Socket\b"),
     "# Added Passive Skills are Jewel Sockets"),
]


def _normalise_pattern(pat: str) -> str:
    for rx, repl in _SINGULAR_TO_PLURAL:
        pat = rx.sub(repl, pat)
    return pat

# Keyword priority for choosing which matched mods to constrain on (higher = keep).
# These are the affixes that actually drive a PoE1 rare's price.
_PRIORITY = [
    ("maximum life", 100), ("maximum energy shield", 95), ("maximum mana", 40),
    ("resistance", 70), ("to all", 75),
    ("increased energy shield", 60), ("increased evasion", 45),
    ("increased armour", 45), ("increased physical damage", 80),
    ("increased spell damage", 80), ("increased attack speed", 85),
    ("increased cast speed", 85), ("critical", 70), ("adds", 65),
    ("increased damage", 70), ("to strength", 35), ("to dexterity", 35),
    ("to intelligence", 35), ("attributes", 50), ("movement speed", 80),
    ("increased rarity", 55), ("level of all", 88), ("to level of", 88),
    ("accuracy", 25), ("life regenerat", 30), ("mana regenerat", 25),
    ("chance to", 40), ("increased mana", 30),
]


# On armour pieces (helmet/chest/gloves/boots/shield) these defence affixes are LOCAL
# mods whose display text collides with a different GLOBAL trade stat id, so matching
# them by text yields the wrong filter and zero results. Demote them on armour so we
# search by unambiguous global mods (resistances, life, attributes) instead. (Defence
# TOTALS are searched via armour_filters, not these affixes.)
_LOCAL_DEFENCE = [
    "to maximum energy shield", "to evasion rating", "to armour",
    "increased energy shield", "increased evasion rating", "increased armour",
    "increased evasion and energy shield", "increased armour and energy shield",
    "increased armour and evasion", "increased armour, evasion and energy shield",
]


def is_local_defence(text: str) -> bool:
    """True if a mod's display text collides with a local-vs-global trade stat (flat/
    %-increased armour/evasion/ES). These can't be reliably filtered on trade by text."""
    p = util.mod_to_pattern(text).lower()
    return any(kw in p for kw in _LOCAL_DEFENCE)


def _score(pattern: str, demote_local: bool = False) -> int:
    p = pattern.lower()
    best = 10
    for kw, sc in _PRIORITY:
        if kw in p:
            best = max(best, sc)
    if demote_local and any(kw in p for kw in _LOCAL_DEFENCE):
        best = 3
    return best


class StatMapper:
    def __init__(self, stats_data: dict):
        # pattern -> stat id (global, explicit-preferred) for the default/unscoped path
        self._map: Dict[str, str] = {}
        # per-group pattern -> stat id, so a mod can be matched within its OWN stat group
        # (an enchant and an explicit can share text but map to different ids)
        self._groups: Dict[str, Dict[str, str]] = {}
        self._build(stats_data)

    def _build(self, stats_data: dict) -> None:
        # PoE1 stat groups (from /api/trade/data/stats): Pseudo, Explicit, Implicit, Imbued,
        # Fractured, Enchant, Scourge, Crafted, Mercenary, Veiled, Delve, Ultimatum, Sanctum,
        # Crucible. There is NO rune / desecrated group (those were PoE2).
        wanted = {"explicit", "implicit", "pseudo", "fractured"}
        grouped = wanted | {"enchant", "crafted", "veiled", "crucible", "scourge"}
        for grp in stats_data.get("result", []):
            label = (grp.get("label") or "").lower()
            for e in grp.get("entries", []):
                sid = e.get("id", "")
                prefix = sid.split(".", 1)[0]
                text = e.get("text", "")
                pat = util.mod_to_pattern(text)
                if prefix in grouped or label in grouped:
                    self._groups.setdefault(prefix, {}).setdefault(pat, sid)
                if prefix in wanted or label in wanted:
                    # prefer explicit over other groups if duplicate pattern
                    if pat not in self._map or prefix == "explicit":
                        self._map[pat] = sid

    @staticmethod
    def _swap(table: Dict[str, str], pat: str):
        if "reduced" in pat:
            sid = table.get(pat.replace("reduced", "increased"))
            if sid:
                return sid, True
        elif "increased" in pat:
            sid = table.get(pat.replace("increased", "reduced"))
            if sid:
                return sid, True
        return None, False

    def match(self, mod_text: str, group: Optional[str] = None) -> Tuple[Optional[str], bool]:
        """Return (stat_id, negate). When `group` (the mod's stat group, e.g. 'enchant') is
        given, match within THAT group first so a mod is searched as the correct stat type
        (enchant.stat_X, not explicit.stat_X). Falls back to the OPPOSITE polarity
        (reduced<->increased, negate=True) so a 'reduced' roll matches its 'increased' stat.
        Enchants never fall back to the explicit map -- searching an enchant as an explicit
        returns nothing and hangs the appraisal."""
        pat = _normalise_pattern(util.mod_to_pattern(mod_text))
        if group:
            gm = self._groups.get(group)
            if gm:
                sid = gm.get(pat)
                if sid:
                    return sid, False
                sw = self._swap(gm, pat)
                if sw[0]:
                    return sw
            if group == "enchant":      # don't let an enchant masquerade as an explicit search
                return None, False
        sid = self._map.get(pat)
        if sid:
            return sid, False
        return self._swap(self._map, pat)

    def match_line(self, mod_text: str) -> Optional[str]:
        return self.match(mod_text)[0]

    def top_filters(self, explicit_mods: List[str], limit: int = 4,
                    demote_local: bool = False
                    ) -> List[Tuple[str, str, Optional[float]]]:
        """Return up to `limit` (stat_id, original_text, min_value) for the most
        price-relevant explicit mods that we can map to trade stats.

        Set demote_local=True for armour pieces so local defence mods (whose text
        collides with a different global stat id) are pushed below global mods.
        """
        scored = []
        for line in explicit_mods:
            sid = self.match_line(line)
            if not sid:
                continue
            pat = util.mod_to_pattern(line)
            val = util.first_number(line)
            scored.append((_score(pat, demote_local), sid, line, val))
        # de-dup by stat id keeping the highest score
        best: Dict[str, Tuple[int, str, str, Optional[float]]] = {}
        for sc, sid, line, val in scored:
            if sid not in best or sc > best[sid][0]:
                best[sid] = (sc, sid, line, val)
        ranked = sorted(best.values(), key=lambda t: t[0], reverse=True)
        return [(sid, line, val) for _, sid, line, val in ranked[:limit]]
