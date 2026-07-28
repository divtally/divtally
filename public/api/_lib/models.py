"""Normalised data models shared across the pipeline.

VENDORED VERBATIM from bpc/models.py. Keep in sync.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# frameType -> rarity label (GGG standard item frame ids). PoE1 foil/relic uniques use their
# OWN frame ids -- 9 = Relic, 10 = SupporterFoil -- NOT frameType 3 + a `foil` flag (an earlier
# comment claimed that; live poe.ninja data disproves it: Nimis is frameType 10, rarity
# "Unique"). Both 9 and 10 are uniques for routing (see poeninja._categorise), so both label as
# a unique-tier rarity. Missing 10 previously dropped foil uniques to Normal (R1 build3 blocker).
FRAME_RARITY = {0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique", 4: "Gem",
                5: "Currency", 6: "Divination", 8: "Prophecy", 9: "Relic", 10: "Unique"}

# Pricing categories we route items into. (PoE2's CAT_RUNE is deleted -- PoE1 has no
# runes / soul cores; that frame-5 socketed mechanic does not exist here.)
CAT_UNIQUE = "unique"
CAT_RARE = "rare"
CAT_MAGIC = "magic"      # magic flasks / magic jewels (typically cheap)
CAT_GEM = "gem"          # skill / support gems (real, tradeable items in PoE1)
CAT_NORMAL = "normal"


@dataclass
class Item:
    name: str                       # unique name, or "" for non-uniques
    base_type: str                  # e.g. "Astral Plate"
    type_line: str                  # full type incl. magic affixes
    frame_type: int                 # GGG frameType
    rarity: str                     # label from FRAME_RARITY
    category: str                   # one of CAT_*
    group: str                      # "equipment" | "flask" | "jewel" | "gem"
    slot: str                       # display slot name (Ring, Body Armour, ...)
    explicit_mods: List[str] = field(default_factory=list)
    mod_src: List[str] = field(default_factory=list)   # trade group per explicit mod (enchant/explicit/...)
    implicit_mods: List[str] = field(default_factory=list)
    mods_explicit: List[dict] = field(default_factory=list)  # {id, stats} (best-effort; unused in pricing)
    corrupted: bool = False
    ilvl: int = 0
    support: bool = False           # gems only
    icon: str = ""
    count: int = 1                  # how many copies
    defences: Dict[str, int] = field(default_factory=dict)  # ar/ev/es/ward totals (armour)
    # PoE1 sockets / LINKS (brand new vs PoE2; a 5L/6L is a major price component).
    # sockets: raw [{group, attr, sColour}]; max_link = size of the largest link-group;
    # total_sockets = len(sockets); socket_colours = per-socket display colour (R/G/B/W/A).
    sockets: List[dict] = field(default_factory=list)
    max_link: int = 0
    total_sockets: int = 0
    socket_colours: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    # gems: PoE1 prices each gem as a real item by name + level + quality + corruption.
    # An active-skill gem carries its own level/quality and the list of its support gems
    # (each a priceable item: {name, level, quality, corrupted, icon, support, granted}).
    # No uncut/lineage.
    gem_level: int = 0
    gem_quality: int = 0
    supports: List[dict] = field(default_factory=list)
    # gem provenance (D-0006, feedback round 1). `granted` = the gem is provided by an
    # equipped item (character JSON `itemProvidedGems`) or is a built-in support
    # (`isBuiltInSupport`) -- it is NOT a bought/tradeable gem, so it is EXCLUDED from the
    # trade-price total (its socketed supports, if any, still count). host_* describe the
    # equipment the skill group is socketed into (skills[].itemSlot -> host inventoryId),
    # for grouping gem rows under a host-item header in the UI.
    granted: bool = False
    host_slot: str = ""             # friendly slot label of the host item (e.g. "Body Armour")
    host_name: str = ""             # host item display name (e.g. "Blunderbore")
    host_base: str = ""             # host item base type (e.g. "Astral Plate")
    host_unique: bool = False       # whether the host item is a unique
    host_inventory_id: str = ""     # raw host inventoryId (stable UI grouping key, e.g. "BodyArmour")

    @property
    def display_name(self) -> str:
        if self.name and self.base_type and self.name != self.base_type:
            return f"{self.name}, {self.base_type}"
        return self.name or self.type_line or self.base_type


@dataclass
class PriceTier:
    minimum: Optional[float] = None   # chaos
    median: Optional[float] = None
    high: Optional[float] = None


@dataclass
class PriceResult:
    item: Item
    tier: PriceTier = field(default_factory=PriceTier)
    sample_size: int = 0            # listings used after trimming
    total_found: int = 0            # total listings the search reported
    method: str = ""                # "unique-name", "rare-mods", "skill", ...
    confidence: str = "n/a"         # high / medium / low / none
    note: str = ""
    trade_url: str = ""             # link to reproduce the search in a browser
    extra: Dict[str, Any] = field(default_factory=dict)  # extra serialised fields (e.g. skills)


@dataclass
class BuildMeta:
    account: str
    character: str
    league: str
    char_class: str = ""
    level: int = 0
    pob_export: str = ""
    source_url: str = ""
    cache_key: str = ""             # the poeninja:char:... disk-cache key (for saved results)


@dataclass
class BuildEstimate:
    meta: BuildMeta
    results: List[PriceResult] = field(default_factory=list)
