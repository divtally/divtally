"""Parse a Path of Building (PoE1 community) import code / XML into priceable items.

A PoB code is URL-safe base64 of zlib-compressed XML rooted at <PathOfBuilding>. Each
<Item> holds the in-game item text (Rarity / name / base / Item Level / Implicits:N /
mods, with {enchant}{fractured}{crafted} prefixes / Corrupted). Equipment/flask slots
come from <ItemSet><Slot>, jewels from <Spec><Sockets><Socket>, gems from the active
<SkillSet>'s <Gem> nodes. (PoE1 has no runes / soul cores / charms.)
"""
import base64
import re
import xml.etree.ElementTree as ET
import zlib
from typing import List, Optional, Tuple

from .models import (CAT_GEM, CAT_NORMAL, FRAME_RARITY, BuildMeta, Item,
                     CAT_MAGIC, CAT_RARE, CAT_UNIQUE)


class PobError(RuntimeError):
    pass


_RARITY_FRAME = {"NORMAL": 0, "MAGIC": 1, "RARE": 2, "UNIQUE": 3, "RELIC": 3}
_CAT_BY_FRAME = {0: CAT_NORMAL, 1: CAT_MAGIC, 2: CAT_RARE, 3: CAT_UNIQUE}

# header/property lines that appear before the mod block (not mods themselves). PoE1 adds
# the *BasePercentile / Catalyst lines PoB emits for uniques (docs/research/pob1.md 5.2);
# without them they leak into the mod block and corrupt the Implicits boundary.
_PROP_PREFIXES = ("Armour:", "Evasion:", "Energy Shield:", "Ward:", "Requires",
                  "Quality", "Sockets:", "LevelReq:", "Unique ID:", "Item Level:",
                  "Stack Size:", "Radius:", "Limited to:",
                  "ArmourBasePercentile", "EvasionBasePercentile",
                  "EnergyShieldBasePercentile", "WardBasePercentile",
                  "Catalyst:", "CatalystQuality:")

# PoB slot name -> (group, inventoryId, display). 'Weapon 2*' resolved dynamically (shield).
_SLOT_MAP = {
    "Helmet": ("equipment", "Helm", "Helmet"),
    "Body Armour": ("equipment", "BodyArmour", "Body Armour"),
    "Gloves": ("equipment", "Gloves", "Gloves"),
    "Boots": ("equipment", "Boots", "Boots"),
    "Belt": ("equipment", "Belt", "Belt"),
    "Amulet": ("equipment", "Amulet", "Amulet"),
    "Ring 1": ("equipment", "Ring", "Ring"),
    "Ring 2": ("equipment", "Ring", "Ring"),
    "Ring 3": ("equipment", "Ring", "Ring"),
    "Weapon 1": ("equipment", "Weapon", "Weapon"),
    "Weapon 2": ("equipment", "Weapon", "Off-hand"),
    "Weapon 1 Swap": ("equipment", "Weapon", "Weapon (swap)"),
    "Weapon 2 Swap": ("equipment", "Weapon", "Off-hand (swap)"),
}
for _i in range(1, 6):
    _SLOT_MAP[f"Flask {_i}"] = ("flask", "Flask", "Flask")


def decode(code: str) -> str:
    """PoB import code -> XML string."""
    code = re.sub(r"\s+", "", code or "")
    if code.lower().startswith("pob://"):
        code = code[6:]
    pad = "=" * (-len(code) % 4)
    last = None
    for fn in (base64.urlsafe_b64decode, base64.standard_b64decode):
        try:
            return zlib.decompress(fn(code + pad)).decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
    raise PobError(f"not a valid Path of Building code ({last})")


def looks_like_code(text: str) -> bool:
    """Cheap check that a blob is a PoB code (decodes to a PathOfBuilding doc).
    Tolerates whitespace-wrapped codes (decode() ignores whitespace anyway)."""
    t = re.sub(r"\s+", "", (text or "").strip())
    if len(t) < 40 or t.lower().startswith("http"):
        return False
    try:
        return "<PathOfBuilding" in decode(t)[:200]
    except PobError:
        return False


def _derive_base(type_line: str, all_types) -> str:
    """For magic/unknown items with no explicit base line, find the longest known base
    type contained in the affixed type line. Falls back to the full type line.

    Uses a fast `in` pre-filter so we only run the word-boundary regex on the few base
    types that are actually substrings (not all ~3000)."""
    best = ""
    for t in all_types:
        if len(t) > len(best) and t in type_line and \
                re.search(r"\b" + re.escape(t) + r"\b", type_line):
            best = t
    return best or type_line


def _split_tags(line: str) -> Tuple[str, set]:
    """Strip a mod's leading {tag} markers, returning (text, set_of_tags)."""
    m = re.match(r"^((?:\{[^}]*\})+)", line)
    if not m:
        return line.strip(), set()
    return line[m.end():].strip(), set(re.findall(r"\{([^}]*)\}", m.group(1)))


def _is_property(ln: str) -> bool:
    return any(ln.startswith(p) for p in _PROP_PREFIXES)


def _parse_item_text(text: str, all_types) -> Optional[dict]:
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("<")]
    if not lines or not lines[0].lower().startswith("rarity:"):
        return None
    rarity = lines[0].split(":", 1)[1].strip().upper()
    frame = _RARITY_FRAME.get(rarity, 0)

    if frame in (2, 3):                         # RARE / UNIQUE: name + base lines
        name = lines[1] if len(lines) > 1 else ""
        base = lines[2] if len(lines) > 2 else ""
        type_line = base
        body = lines[3:]
    else:                                       # MAGIC / NORMAL: one combined line
        type_line = lines[1] if len(lines) > 1 else ""
        name = ""
        base = type_line if frame == 0 else _derive_base(type_line, all_types)
        body = lines[2:]

    ilvl = 0
    corrupted = False
    defences: dict = {}
    impl_count = 0
    impl_seen = False
    mods: List[dict] = []                       # {text, tags}
    for ln in body:
        if ln.startswith("Item Level:"):
            m = re.search(r"\d+", ln)
            ilvl = int(m.group()) if m else 0
            continue
        if ln == "Corrupted":
            corrupted = True
            continue
        dm = re.match(r"^(Armour|Evasion|Energy Shield|Ward):\s*(\d+)", ln)
        if dm and not impl_seen:                # item's total defence value (searchable)
            defences[{"Armour": "ar", "Evasion": "ev",
                      "Energy Shield": "es", "Ward": "ward"}[dm.group(1)]] = int(dm.group(2))
            continue
        if ln.startswith("Implicits:"):
            m = re.search(r"\d+", ln)
            impl_count = int(m.group()) if m else 0
            impl_seen = True
            continue
        if not impl_seen and _is_property(ln):
            continue                            # header property before the mod block
        text_, tags = _split_tags(ln)
        if not text_:
            continue
        # join a wrapped continuation line (starts lower-case, no tags) onto the prev mod
        if mods and not tags and text_[:1].islower():
            mods[-1]["text"] += " " + text_
        else:
            mods.append({"text": text_, "tags": tags})

    implicit_mods = [m["text"] for m in mods[:impl_count]]
    # explicit affixes exclude enchant-granted lines (not base item affixes)
    explicit_mods = [m["text"] for m in mods[impl_count:] if "enchant" not in m["tags"]]
    return {"frame": frame, "name": name, "base": base, "type_line": type_line,
            "ilvl": ilvl, "corrupted": corrupted, "defences": defences,
            "implicit_mods": implicit_mods, "explicit_mods": explicit_mods}


def parse(code_or_xml: str, types: dict) -> Tuple[BuildMeta, List[Item]]:
    """Parse a PoB code (or already-decoded XML) into (BuildMeta, [Item])."""
    xml = code_or_xml if code_or_xml.lstrip().startswith("<") else decode(code_or_xml)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise PobError(f"could not read the Path of Building data ({e})")
    if "PathOfBuilding" not in root.tag:
        raise PobError("this doesn't look like a Path of Building build.")

    all_types = types.get("all", set())
    armour_types = types.get("by_group", {}).get("Armour", set())
    jewel_types = types.get("by_group", {}).get("Jewels", set())
    flask_types = types.get("by_group", {}).get("Flasks", set())

    build = root.find("Build")
    klass = ""
    level = 0
    if build is not None:
        klass = build.get("ascendClassName") or build.get("className") or ""
        if klass in ("None", "nil", ""):
            klass = build.get("className", "")
        try:
            level = int(build.get("level", 0))
        except (TypeError, ValueError):
            level = 0

    items_el = root.find("Items")
    if items_el is None:
        raise PobError("the build has no items.")

    # active item-set slot map (skip weapon-swap alternates): itemId -> slotName
    sets = items_el.findall("ItemSet")
    active = next((s for s in sets if s.get("id") == items_el.get("activeItemSet")),
                  sets[0] if sets else None)
    slot_of = {}
    if active is not None:
        for sl in active.findall("Slot"):
            iid, nm = sl.get("itemId"), sl.get("name", "")
            if iid and iid != "0":
                slot_of[iid] = nm
    jewel_ids = {s.get("itemId") for s in root.iter("Socket")
                 if s.get("itemId") and s.get("itemId") != "0"}

    items: List[Item] = []
    for el in items_el.findall("Item"):
        iid = el.get("id")
        slot = slot_of.get(iid)
        is_jewel = iid in jewel_ids
        if not slot and not is_jewel:
            continue                            # spare / unequipped item
        parsed = _parse_item_text("".join(el.itertext()), all_types)
        if not parsed:
            continue
        base = parsed["base"]
        if slot and slot in _SLOT_MAP:
            group, inv, disp = _SLOT_MAP[slot]
            if slot.startswith("Weapon 2") and base in armour_types:
                inv, disp = "Offhand", "Off-hand"     # shield / focus, not a weapon
        elif is_jewel or base in jewel_types:
            group, inv, disp = "jewel", "PassiveJewels", "Jewel"
        elif base in flask_types:
            group, inv, disp = "flask", "Flask", "Flask"
        else:
            group, inv, disp = "equipment", "", slot or "?"
        frame = parsed["frame"]
        items.append(Item(
            name=parsed["name"], base_type=base, type_line=parsed["type_line"],
            frame_type=frame, rarity=FRAME_RARITY.get(frame, "Normal"),
            category=_CAT_BY_FRAME.get(frame, CAT_NORMAL), group=group, slot=disp,
            explicit_mods=parsed["explicit_mods"], implicit_mods=parsed["implicit_mods"],
            corrupted=parsed["corrupted"], ilvl=parsed["ilvl"],
            defences=parsed["defences"], raw={"inventoryId": inv}))

    # gems: active skill set only, skipping item-/tree-granted skills. PoB sets count="nil"
    # for normal single gems, so gate on enabled (+ a non-empty name), NOT count -- otherwise
    # every gem is dropped (docs/research/pob1.md 4/5). Level/quality drive PoE1 gem pricing.
    skills_el = root.find("Skills")
    gem_scope = skills_el
    if skills_el is not None:
        ss = skills_el.findall("SkillSet")
        if ss:
            gem_scope = next((s for s in ss if s.get("id") == skills_el.get("activeSkillSet")),
                             ss[0])
    if gem_scope is not None:
        for sk in gem_scope.findall("Skill"):
            if sk.get("source"):                # granted by an item or the tree
                continue
            for gem in sk.findall("Gem"):
                if (gem.get("enabled") or "").lower() == "false":
                    continue
                name = gem.get("nameSpec") or ""
                if not name:
                    continue
                sid, gid = (gem.get("skillId") or "").lower(), (gem.get("gemId") or "").lower()
                support = sid.startswith("support") or "supportgem" in gid
                try:
                    lvl = int(gem.get("level") or 0)
                except (TypeError, ValueError):
                    lvl = 0
                try:
                    qual = int(gem.get("quality") or 0)
                except (TypeError, ValueError):
                    qual = 0
                items.append(Item(name="", base_type=name, type_line=name, frame_type=4,
                                  rarity="Gem", category=CAT_GEM, group="gem", slot="",
                                  support=support, gem_level=lvl, gem_quality=qual, raw={}))

    meta = BuildMeta(account="", character="Path of Building import",
                     league="", char_class=klass, level=level, pob_export="")
    return meta, items
