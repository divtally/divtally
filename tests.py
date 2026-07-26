"""Lightweight self-tests for the pure logic (no network). Run: python tests.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bpc import util
from bpc.poeninja import parse_build_url, PoeNinjaError

_fails = []


def check(name, got, want):
    if got != want:
        _fails.append(f"{name}: got {got!r}, want {want!r}")


def approx(name, got, want, tol=1e-6):
    if got is None or abs(got - want) > tol:
        _fails.append(f"{name}: got {got!r}, want ~{want!r}")


# ---- util.strip_rich / mod_to_pattern ----
check("strip_rich pipe", util.strip_rich("+10% to all [Resistances]"),
      "+10% to all Resistances")
check("strip_rich named", util.strip_rich("[Wind|Wind Skills] deal more"),
      "Wind Skills deal more")
check("pattern life", util.mod_to_pattern("+90 to maximum Life"), "# to maximum Life")
check("pattern range", util.mod_to_pattern("Adds 13 to 16 [Fire|Fire] Damage"),
      "Adds # to # Fire Damage")
check("pattern pct", util.mod_to_pattern("111% increased [Evasion] and [EnergyShield|Energy Shield]"),
      "#% increased Evasion and Energy Shield")
check("first_number", util.first_number("+71 to [Evasion] Rating"), 71.0)
check("first_number neg", util.first_number("-5% reduced"), -5.0)
check("pattern seconds->second", util.mod_to_pattern("Inherent Rage loss starts 4.1 seconds later"),
      "Inherent Rage loss starts # second later")

# ---- statmap polarity swap (reduced <-> increased; value negated) ----
from bpc.statmap import StatMapper as _StatMapper
class _FakeStatsClient:
    def stats_data(self):
        return {"result": [{"label": "Explicit", "entries": [
            {"id": "explicit.stat_incattr", "text": "#% increased Attribute Requirements"},
            {"id": "explicit.stat_redignite", "text": "#% reduced Ignite Duration on you"}]}]}
_sm = _StatMapper(_FakeStatsClient())
check("polarity reduced->increased", _sm.match("35% reduced Attribute Requirements"),
      ("explicit.stat_incattr", True))
check("polarity direct reduced", _sm.match("20% reduced Ignite Duration on you"),
      ("explicit.stat_redignite", False))
check("polarity unmatched", _sm.match("12% increased Banana"), (None, False))

# ---- gem parsing (skill level + lineage detection) ----
from bpc import poeninja as _pn
check("gem level (Max)", _pn._gem_level({"properties": [{"name": "Level", "values": [["20 (Max)"]]}]}), 20)
check("gem level plain", _pn._gem_level({"properties": [{"name": "Level", "values": [["19"]]}]}), 19)
check("gem level missing", _pn._gem_level({"properties": []}), 0)
check("lineage tag", _pn._is_lineage({"properties": [{"name": "[SupportGem|Support], [LineageSupports|Lineage]"}]}), True)
check("not lineage", _pn._is_lineage({"properties": [{"name": "[SupportGem|Support]"}]}), False)

# ---- percentile / median ----
check("median empty", util.median([]), None)
check("median single", util.median([5]), 5)
approx("median even", util.median([1, 2, 3, 4]), 2.5)
approx("pct 0", util.percentile([1, 2, 3, 4, 5], 0), 1)
approx("pct 100", util.percentile([1, 2, 3, 4, 5], 100), 5)
approx("pct 50", util.percentile([1, 2, 3, 4, 5], 50), 3)
approx("pct 90", util.percentile([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100], 90), 90)

# ---- trim_outliers ----
check("trim small kept", util.trim_outliers([1, 2, 3]), [1, 2, 3])
# scam-low (0.1) and absurd-high (1000) trimmed around median ~10
trimmed = util.trim_outliers([0.1, 8, 9, 10, 11, 12, 1000])
check("trim drops low", 0.1 in trimmed, False)
check("trim drops high", 1000 in trimmed, False)
check("trim keeps mid", 10 in trimmed, True)
# never returns empty
check("trim never empty", len(util.trim_outliers([1, 100, 10000, 1000000])) > 0, True)

# ---- URL parsing ----
p = parse_build_url("https://poe.ninja/poe2/builds/runesofaldur/character/example-0416/ResurrectGodAura?i=0")
check("parse slug", p["slug"], "runesofaldur")
check("parse account", p["account"], "example-0416")
check("parse char", p["character"], "ResurrectGodAura")
p2 = parse_build_url("https://poe.ninja/poe2/builds/runesofaldur/character/Sensa%C3%A7%C3%A3oX-1/Char")
check("parse encoded", p2["account"], "SensaçãoX-1")
p3 = parse_build_url("poe.ninja/poe2/builds/hcrunesofaldur/character/Acc-1/Name/")
check("parse trailing slash", p3["character"], "Name")

for bad in ["", "not a url", "https://poe.ninja/poe2/builds",
            "https://example.com/x", "https://poe.ninja/poe1/builds/x/character/a/b"]:
    try:
        parse_build_url(bad)
        _fails.append(f"parse should have rejected {bad!r}")
    except PoeNinjaError:
        pass

# ---- report.fmt via a fake converter ----
from bpc.currency import CurrencyConverter
conv = CurrencyConverter.__new__(CurrencyConverter)
conv._rates = {"exalted": 1.0, "divine": 135.0}
conv.client = None
check("fmt none", conv.fmt(None), "n/a")
check("fmt small ex", conv.fmt(5), "5.0 ex")
check("fmt divine", "div" in conv.fmt(2700), True)

# ---- sign normalization so '+#' dict mods match '+30' item mods ----
check("pattern spirit-per-socket",
      util.mod_to_pattern("+30 to Spirit per Socket filled"),
      util.mod_to_pattern("+# to Spirit per Socket filled"))
check("pattern +level",
      util.mod_to_pattern("+2 to Level of all Fire Skills"),
      util.mod_to_pattern("+# to Level of all Fire Skills"))
check("pattern res sign",
      util.mod_to_pattern("+38% to Cold Resistance"),
      util.mod_to_pattern("+#% to Cold Resistance"))

# ---- Pricer._spread edge cases ----
from bpc.pricing import Pricer
check("spread k=1", Pricer._spread(["a", "b", "c"], 1), ["a"])
check("spread n<=k", Pricer._spread(["a", "b"], 20), ["a", "b"])
check("spread len", len(Pricer._spread([str(i) for i in range(100)], 20)), 20)
sp = Pricer._spread([str(i) for i in range(100)], 20)
check("spread first", sp[0], "0")
check("spread last", sp[-1], "99")

# ---- Retry-After parsing ----
from bpc.trade import _parse_retry_after
check("retry seconds", _parse_retry_after("30"), 30.0)
check("retry none", _parse_retry_after(None), None)
check("retry garbage", _parse_retry_after("soon"), None)
check("retry httpdate", _parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT"), 0.0)

# ---- league normalization (HC/SSF) ----
from bpc.engine import _norm_league
check("league ssf==hc", _norm_league("HC SSF Runes of Aldur"),
      _norm_league("Hardcore Runes of Aldur"))
check("league plain", _norm_league("Runes of Aldur"), "runes of aldur")

# ---- cache tolerates a non-dict file ----
from bpc import cache as _cache
import json as _json
_cache.put("selftest:list", ["x"])  # writes a proper dict wrapper
import os as _os
_bad = _cache._key_to_path("selftest:bad")
_os.makedirs(_cache.CACHE_DIR, exist_ok=True)
open(_bad, "w", encoding="utf-8").write("[1, 2, 3]")  # non-dict json
try:
    check("cache non-dict -> miss", _cache.get("selftest:bad", 9999), None)
finally:
    _os.remove(_bad)

# ---- pseudo resistance aggregation (res_contributions) ----
from bpc.pricing import res_contributions
c = res_contributions(["+22% to all [Elemental|Elemental] Resistances",
                       "+54% to [Lightning|Lightning] Resistance"])
approx("res elemental 120", c["elemental"], 120)
approx("res lightning 76", c["lightning"], 76)
approx("res chaos 0", c["chaos"], 0)
c2 = res_contributions(["+2% to Maximum Fire Resistance",   # max res must NOT count
                        "+22% to Cold Resistance", "+16% to Chaos Resistance"])
approx("res excl maximum (elemental=22)", c2["elemental"], 22)
approx("res chaos 16", c2["chaos"], 16)
c3 = res_contributions(["+10% to all Resistances"])         # feeds elem x3 and chaos
approx("all-res elemental 30", c3["elemental"], 30)
approx("all-res chaos 10", c3["chaos"], 10)

# ---- Path of Building import (decode + parse + link candidates) ----
import base64 as _b64, zlib as _zlib
from bpc import pob as _pob, engine as _engine
_xml = ('<?xml version="1.0"?><PathOfBuilding2>'
        '<Build level="92" className="Ranger" ascendClassName="Deadeye"/>'
        '<Items activeItemSet="1">'
        '<Item id="1">\nRarity: RARE\nFoo Bar\nGold Amulet\nItem Level: 80\nImplicits: 1\n'
        '{enchant}+10 to Dexterity\n+90 to maximum Life\n+30% to Fire Resistance\nCorrupted\n</Item>'
        '<ItemSet id="1"><Slot name="Amulet" itemId="1"/></ItemSet></Items></PathOfBuilding2>')
_code = _b64.urlsafe_b64encode(_zlib.compress(_xml.encode())).decode()
check("pob decode", "<PathOfBuilding2>" in _pob.decode(_code), True)
check("pob looks_like_code", _pob.looks_like_code(_code), True)
check("pob not code (url)", _pob.looks_like_code("https://pobb.in/x"), False)
_m, _items = _pob.parse(_code, {"all": {"Gold Amulet"}, "by_group": {}})
_amu = next((i for i in _items if i.base_type == "Gold Amulet"), None)
check("pob item parsed", _amu is not None, True)
if _amu:
    check("pob name", _amu.name, "Foo Bar")
    check("pob rarity", _amu.category, "rare")
    check("pob corrupted", _amu.corrupted, True)
    check("pob ilvl", _amu.ilvl, 80)
    check("pob implicit strip", _amu.implicit_mods, ["+10 to Dexterity"])
    check("pob explicit life", "+90 to maximum Life" in _amu.explicit_mods, True)
    check("pob slot", _amu.slot, "Amulet")
check("pobb.in raw url", _engine._pob_raw_candidates("https://pobb.in/abc")[0],
      "https://pobb.in/abc/raw")
check("pastebin raw url", _engine._pob_raw_candidates("https://pastebin.com/Xy")[0],
      "https://pastebin.com/raw/Xy")
# review-fix regressions:
_wrapped = "\n".join(_code[i:i + 40] for i in range(0, len(_code), 40))
check("pob wrapped code detected", _pob.looks_like_code(_wrapped), True)
_no_impl = _pob._parse_item_text(
    "Rarity: RARE\nFoo\nGold Amulet\nItem Level: 80\n+90 to maximum Life\n"
    "+30% to Fire Resistance\n", set())
check("pob mods kept w/o Implicits line", _no_impl["explicit_mods"],
      ["+90 to maximum Life", "+30% to Fire Resistance"])
_multi = _pob._parse_item_text(
    "Rarity: UNIQUE\nFoo\nRing\nImplicits: 0\nWind Skills count\n"
    "as being boosted by stuff\n", set())
check("pob multiline mod joined", _multi["explicit_mods"],
      ["Wind Skills count as being boosted by stuff"])
_rune = _pob._parse_item_text(
    "Rarity: RARE\nFoo\nSleek Jacket\nItem Level: 80\nRune: Greater Iron Rune\n"
    "Implicits: 0\n{rune}+18% to Cold Resistance\n+50 to maximum Energy Shield\n", set())
check("pob rune extracted", _rune["runes"], ["Greater Iron Rune"])
check("pob rune mod excluded from explicit", _rune["explicit_mods"],
      ["+50 to maximum Energy Shield"])
# defence totals (searched via equipment_filters instead of the local defence affixes)
_def = _pob._parse_item_text(
    "Rarity: RARE\nFoo\nSleek Jacket\nEvasion: 504\nEnergy Shield: 162\nWard: 38\n"
    "Item Level: 80\nImplicits: 0\n+90 to maximum Life\n", set())
check("pob defences captured", _def["defences"], {"ev": 504, "es": 162, "ward": 38})
from bpc import poeninja as _nj
_njdef = _nj._defences({"properties": [
    {"name": "[EnergyShield|Energy Shield]", "values": [["477", 0]]},
    {"name": "[Evasion|Evasion Rating]", "values": [["1560", 0]]},
    {"name": "[Quality]", "values": [["+20%", 1]]}]})
check("poeninja defences from properties", _njdef, {"es": 477, "ev": 1560})

if _fails:
    print("FAILED:")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("All self-tests passed.")
