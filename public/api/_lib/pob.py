"""Parse a Path of Building (PoE1 community) import code / XML into priceable items.

VENDORED VERBATIM from bpc/pob.py (imports only `.models`; no trade). `parse` takes the
base-type `types` dict, which the public build sources from refdata.item_types() (bundled)
instead of a live trade `data/items` call.
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

# header/property lines that appear before the mod block (not mods themselves).
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
    "Weapon 1 Swap": ("equipment", "Weapon2", "Weapon (swap)"),
    "Weapon 2 Swap": ("equipment", "Offhand2", "Off-hand (swap)"),
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
    """Cheap check that a blob is a PoB code (decodes to a PathOfBuilding doc)."""
    t = re.sub(r"\s+", "", (text or "").strip())
    if len(t) < 40 or t.lower().startswith("http"):
        return False
    try:
        return "<PathOfBuilding" in decode(t)[:200]
    except PobError:
        return False


def _derive_base(type_line: str, all_types) -> str:
    """For magic/unknown items with no explicit base line, find the longest known base
    type contained in the affixed type line. Falls back to the full type line."""
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


# Socket colour -> GGG attribute letter (R=Str, G=Dex, B=Int, W=generic/white, A=abyss).
_SOCKET_ATTR = {"R": "S", "G": "D", "B": "I", "W": "G", "A": "A"}


def _parse_sockets(spec: str) -> Tuple[list, int, int, list]:
    """Parse a PoB `Sockets:` value into the SAME four socket fields the poe.ninja path
    builds, so a PoB-imported item's LINKS drive pricing identically."""
    spec = (spec or "").strip()
    if not spec:
        return [], 0, 0, []
    sockets: List[dict] = []
    colours: List[str] = []
    max_link = 0
    for gidx, grp in enumerate(spec.split()):
        cols = [c for c in grp.split("-") if c]
        if not cols:
            continue
        if len(cols) > max_link:
            max_link = len(cols)
        for c in cols:
            sockets.append({"group": gidx, "attr": _SOCKET_ATTR.get(c, ""), "sColour": c})
            colours.append(c)
    return sockets, max_link, len(sockets), colours


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
    sockets_spec = ""
    impl_count = 0
    impl_seen = False
    mods: List[dict] = []                       # {text, tags}
    for ln in body:
        if ln.startswith("Item Level:"):
            m = re.search(r"\d+", ln)
            ilvl = int(m.group()) if m else 0
            continue
        if ln.startswith("Sockets:"):           # capture links BEFORE the header-property skip
            sockets_spec = ln.split(":", 1)[1]
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
    sockets, max_link, total_sockets, socket_colours = _parse_sockets(sockets_spec)
    return {"frame": frame, "name": name, "base": base, "type_line": type_line,
            "ilvl": ilvl, "corrupted": corrupted, "defences": defences,
            "sockets": sockets, "max_link": max_link, "total_sockets": total_sockets,
            "socket_colours": socket_colours,
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
            # Only the MAIN-set off-hand remaps a shield/focus to "Offhand"; the swap off-hand
            # ("Weapon 2 Swap") keeps its "Offhand2" swap id so D-0018 exclusion still applies (R4-2).
            if slot == "Weapon 2" and base in armour_types:
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
            defences=parsed["defences"], sockets=parsed["sockets"],
            max_link=parsed["max_link"], total_sockets=parsed["total_sockets"],
            socket_colours=parsed["socket_colours"], raw={"inventoryId": inv}))

    # gems: active skill set only, skipping item-/tree-granted skills.
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
            # D-0018: skills socketed in the weapon-SWAP set are excluded from totals by default
            # (mirrors the poe.ninja path, whose character doc omits swap-set skills). Flag each
            # such gem `swap` via a Weapon2/Offhand2 inventoryId so response._is_swap + the site's
            # weapon-swap toggle both apply, exactly like swap gear does (R4-2).
            sk_slot = sk.get("slot") or ""
            swap_inv = ("Weapon2" if sk_slot.startswith("Weapon 1") else "Offhand2") \
                if "Swap" in sk_slot else None
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
                # PoB encodes gem corruption IMPLICITLY: a corrupted gem is level 21 or quality 23
                # (no explicit attribute -- verified across a real export's 35 gems, incl. L20/Q23
                # and L21/Q20, none carrying a corrupt attr). Infer it so the gem matches the
                # correct (dearer) poe.ninja corrupted economy line, not the cheap uncorrupted one
                # -- parity with the poe.ninja path, which reads corruption from socket data (R4-1).
                # Honour an explicit marker too, should a future/variant export ever add one.
                gc = (gem.get("corrupted") or "").strip().lower()
                corrupted = (lvl > 20 or qual > 20 or gc in ("true", "1", "yes"))
                items.append(Item(name="", base_type=name, type_line=name, frame_type=4,
                                  rarity="Gem", category=CAT_GEM, group="gem", slot="",
                                  support=support, gem_level=lvl, gem_quality=qual,
                                  corrupted=corrupted,
                                  raw=({"inventoryId": swap_inv} if swap_inv else {})))

    meta = BuildMeta(account="", character="Path of Building import",
                     league="", char_class=klass, level=level, pob_export="")
    return meta, items
