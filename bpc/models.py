"""Normalised data models shared across the pipeline."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# frameType -> rarity label (GGG standard item frame ids)
FRAME_RARITY = {0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique", 4: "Gem",
                5: "Currency", 6: "Divination", 9: "Foil", 10: "Foil"}

# Pricing categories we route items into.
CAT_UNIQUE = "unique"
CAT_RARE = "rare"
CAT_MAGIC = "magic"      # magic flasks / charms
CAT_RUNE = "rune"        # runes / soul cores (frameType Currency, socketed)
CAT_GEM = "gem"          # skill / support gems
CAT_NORMAL = "normal"


@dataclass
class Item:
    name: str                       # unique name, or "" for non-uniques
    base_type: str                  # e.g. "Utility Belt"
    type_line: str                  # full type incl. magic affixes
    frame_type: int                 # GGG frameType
    rarity: str                     # label from FRAME_RARITY
    category: str                   # one of CAT_*
    group: str                      # "equipment" | "flask" | "jewel" | "rune" | "gem"
    slot: str                       # display slot name (Ring, Body Armour, ...)
    explicit_mods: List[str] = field(default_factory=list)
    mod_src: List[str] = field(default_factory=list)   # trade group per explicit mod (enchant/explicit/...)
    implicit_mods: List[str] = field(default_factory=list)
    rune_mods: List[str] = field(default_factory=list)
    mods_explicit: List[dict] = field(default_factory=list)  # {id, stats}
    corrupted: bool = False
    ilvl: int = 0
    support: bool = False           # gems only
    icon: str = ""
    count: int = 1                  # how many copies (runes dedupe into one line)
    defences: Dict[str, int] = field(default_factory=dict)  # ar/ev/es/ward totals (armour)
    raw: Dict[str, Any] = field(default_factory=dict)
    # gems: an active skill carries its level, its used support-socket count, and the
    # list of its support gems [{name, lineage}]. is_lineage marks a lineage support gem.
    gem_level: int = 0
    gem_sockets: int = 0
    supports: List[dict] = field(default_factory=list)
    is_lineage: bool = False

    @property
    def display_name(self) -> str:
        if self.name and self.base_type and self.name != self.base_type:
            return f"{self.name}, {self.base_type}"
        return self.name or self.type_line or self.base_type


@dataclass
class PriceTier:
    minimum: Optional[float] = None   # exalted
    median: Optional[float] = None
    high: Optional[float] = None


@dataclass
class PriceResult:
    item: Item
    tier: PriceTier = field(default_factory=PriceTier)
    sample_size: int = 0            # listings used after trimming
    total_found: int = 0            # total listings the search reported
    method: str = ""                # "unique-name", "rare-mods", "exchange", ...
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
