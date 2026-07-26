"""Lightweight self-tests for the pure logic (no network). Run: python tests.py

Tests derive from the DOCUMENTED PoE1 behaviour (RULE 8): input auto-detection, category
routing, statmap group-scoping, sockets/links, gem name+bucket pricing, chaos/divine
formatting, and the engine->UI JSON contract. Offline: no live trade calls; the real
poe.ninja character dump in research/data/ is used as a fixture where present.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from bpc import util
from bpc.poeninja import parse_build_url, PoeNinjaError, dash_account

_fails = []


def check(name, got, want):
    if got != want:
        _fails.append(f"{name}: got {got!r}, want {want!r}")


def approx(name, got, want, tol=1e-6):
    if got is None or abs(got - want) > tol:
        _fails.append(f"{name}: got {got!r}, want ~{want!r}")


# ---- util.strip_rich / mod_to_pattern (game-agnostic) ----
check("strip_rich pipe", util.strip_rich("+10% to all [Resistances]"),
      "+10% to all Resistances")
check("strip_rich named", util.strip_rich("[Evasion|Evasion Rating] boost"),
      "Evasion Rating boost")
check("pattern life", util.mod_to_pattern("+90 to maximum Life"), "# to maximum Life")
check("pattern range", util.mod_to_pattern("Adds 13 to 16 [Fire|Fire] Damage"),
      "Adds # to # Fire Damage")
check("pattern pct", util.mod_to_pattern("111% increased [Evasion] and [EnergyShield|Energy Shield]"),
      "#% increased Evasion and Energy Shield")
check("first_number", util.first_number("+71 to [Evasion] Rating"), 71.0)
check("first_number neg", util.first_number("-5% reduced"), -5.0)

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

# ---- statmap group-scoping: enchant searched in its OWN group (PoE1 has enchant/crucible/
#      veiled groups, NOT rune/desecrated); an enchant never falls back to the explicit map ----
class _FakeStats2:
    def stats_data(self):
        return {"result": [
            {"label": "Explicit", "entries": [{"id": "explicit.stat_life", "text": "+# to maximum Life"}]},
            {"label": "Enchant", "entries": [{"id": "enchant.stat_life", "text": "+# to maximum Life"}]},
            {"label": "Crucible", "entries": [{"id": "crucible.mod_x", "text": "Grants Level # Foo Skill"}]}]}
_sm2 = _StatMapper(_FakeStats2())
check("enchant scoped to enchant id", _sm2.match("+50 to maximum Life", group="enchant"),
      ("enchant.stat_life", False))
check("explicit default map", _sm2.match("+50 to maximum Life"), ("explicit.stat_life", False))
check("enchant no explicit fallback", _sm2.match("+50 to Bogus", group="enchant"), (None, False))
check("crucible group built", _sm2.match("Grants Level 3 Foo Skill", group="crucible"),
      ("crucible.mod_x", False))

# ---- gem property parsing (level + quality) ----
from bpc import poeninja as _pn
check("gem level (Max)", _pn._gem_level({"properties": [{"name": "Level", "values": [["20 (Max)"]]}]}), 20)
check("gem level plain", _pn._gem_level({"properties": [{"name": "Level", "values": [["19"]]}]}), 19)
check("gem level missing", _pn._gem_level({"properties": []}), 0)
check("gem quality", _pn._gem_quality({"properties": [{"name": "Quality", "values": [["+20%", 1]]}]}), 20)
check("gem quality missing", _pn._gem_quality({"properties": []}), 0)

# ---- category routing (PoE1: frameType 5 is NOT a rune -- CAT_RUNE was deleted) ----
check("cat unique ft3", _pn._categorise({"frameType": 3}, "equipment"), "unique")
check("cat rare ft2", _pn._categorise({"frameType": 2}, "equipment"), "rare")
check("cat magic ft1", _pn._categorise({"frameType": 1}, "equipment"), "magic")
check("cat gem ft4", _pn._categorise({"frameType": 4}, "equipment"), "gem")
check("cat gem by group", _pn._categorise({}, "gem"), "gem")
check("cat ft5 -> normal (not rune)", _pn._categorise({"frameType": 5}, "equipment"), "normal")
check("cat normal ft0", _pn._categorise({"frameType": 0}, "equipment"), "normal")

# ---- sockets / LINKS (PoE1-only; max_link = largest link-group) ----
_si6 = _pn._sockets_info({"sockets": [{"group": 0, "sColour": "R"}] * 6})
check("6-link max", _si6[1], 6)
check("6-link total", _si6[2], 6)
_si2 = _pn._sockets_info({"sockets": [{"group": 0}, {"group": 0}, {"group": 1},
                                      {"group": 1}, {"group": 2}, {"group": 2}]})
check("3x2-link max_link=2", _si2[1], 2)
check("3x2-link total=6", _si2[2], 6)
_si0 = _pn._sockets_info({})
check("no sockets max_link 0", _si0[1], 0)
check("no sockets total 0", _si0[2], 0)

# ---- dash-account encoder (API 404s on raw '#'; only the final #digits converts) ----
check("dash converts discriminator", dash_account("example#0416"), "example-0416")
check("dash keeps dash form", dash_account("example-0416"), "example-0416")
check("dash no discriminator", dash_account("PlainName"), "PlainName")

# ---- percentile / median ----
check("median empty", util.median([]), None)
check("median single", util.median([5]), 5)
approx("median even", util.median([1, 2, 3, 4]), 2.5)
approx("pct 0", util.percentile([1, 2, 3, 4, 5], 0), 1)
approx("pct 100", util.percentile([1, 2, 3, 4, 5], 100), 5)
approx("pct 90", util.percentile([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100], 90), 90)

# ---- trim_outliers ----
check("trim small kept", util.trim_outliers([1, 2, 3]), [1, 2, 3])
trimmed = util.trim_outliers([0.1, 8, 9, 10, 11, 12, 1000])
check("trim drops low", 0.1 in trimmed, False)
check("trim drops high", 1000 in trimmed, False)
check("trim keeps mid", 10 in trimmed, True)
check("trim never empty", len(util.trim_outliers([1, 100, 10000, 1000000])) > 0, True)

# ---- URL parsing (PoE1 links; PoE2 links now REJECTED) ----
p = parse_build_url("https://poe.ninja/poe1/builds/allflame/character/example-0416/TestCharacter")
check("parse slug", p["slug"], "allflame")
check("parse account", p["account"], "example-0416")
check("parse char", p["character"], "TestCharacter")
p2 = parse_build_url("https://poe.ninja/poe1/builds/hardcore-allflame/character/example%230416/Char")
check("parse #-encoded account -> dash", p2["account"], "example-0416")
p3 = parse_build_url("poe.ninja/poe1/builds/allflamehc/character/Acc-1/Name/")
check("parse trailing slash", p3["character"], "Name")

for bad in ["", "not a url", "https://poe.ninja/poe1/builds",
            "https://example.com/x", "https://poe.ninja/poe2/builds/x/character/a/b"]:
    try:
        parse_build_url(bad)
        _fails.append(f"parse should have rejected {bad!r}")
    except PoeNinjaError:
        pass

# ---- currency: base = CHAOS, display Divine (poe.ninja rates) ----
from bpc.currency import CurrencyConverter
class _FakeEcon:
    def chaos_by_id(self, cat, cid):
        return {"chaos": 1.0, "divine": 102.5, "exalted": 0.72, "mirror": 16787}.get(cid)
conv = CurrencyConverter.__new__(CurrencyConverter)
conv.client = None
conv.economy = _FakeEcon()
conv._rates = {"chaos": 1.0}
approx("chaos base rate", conv.to_chaos(3, "chaos"), 3.0)
approx("divine_rate from economy", conv.divine_rate(), 102.5)
approx("lookup exalted via economy", conv._lookup("exalted"), 0.72)
check("lookup unknown -> None", conv._lookup("bogus_currency"), None)
check("fmt none", conv.fmt(None), "n/a")
check("fmt small chaos", conv.fmt(5), "5.0 chaos")
check("fmt big -> divine form", "div" in conv.fmt(300), True)
check("fmt chaos unit shown", "chaos" in conv.fmt(300), True)

# ---- sign normalization so '+#' dict mods match '+30' item mods ----
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

# ---- socket-links search filter (5L/6L gets a socket_filters.links min; <5 gets none) ----
from bpc.models import Item as _Item
_pnew = Pricer.__new__(Pricer)
_i6 = _Item(name="", base_type="Astral Plate", type_line="", frame_type=2, rarity="Rare",
            category="rare", group="equipment", slot="Body Armour", max_link=6)
check("links filter 6L", _pnew._links_filter(_i6),
      {"socket_filters": {"filters": {"links": {"min": 6}}}})
_i5 = _Item(name="", base_type="Astral Plate", type_line="", frame_type=2, rarity="Rare",
            category="rare", group="equipment", slot="Body Armour", max_link=5)
check("links filter 5L", _pnew._links_filter(_i5),
      {"socket_filters": {"filters": {"links": {"min": 5}}}})
_i4 = _Item(name="", base_type="Leather Cap", type_line="", frame_type=2, rarity="Rare",
            category="rare", group="equipment", slot="Helmet", max_link=4)
check("links filter 4L -> none", _pnew._links_filter(_i4), {})

# ---- Retry-After parsing ----
from bpc.trade import _parse_retry_after
check("retry seconds", _parse_retry_after("30"), 30.0)
check("retry none", _parse_retry_after(None), None)
check("retry garbage", _parse_retry_after("soon"), None)
check("retry httpdate", _parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT"), 0.0)

# ---- trade rate rules seeded from the live PoE1 headers (search adds the 6h window) ----
from bpc.trade import _DEFAULT_RULES
check("search windows include 6h", (600, 21600) in _DEFAULT_RULES["search"], True)
check("fetch windows include 6h", (1000, 21600) in _DEFAULT_RULES["fetch"], True)

# ---- league normalization (HC/SSF) ----
from bpc.engine import _norm_league
check("league ssf==hc", _norm_league("HC SSF Allflame"), _norm_league("Hardcore Allflame"))
check("league plain", _norm_league("Allflame"), "allflame")

# ---- cache tolerates a non-dict file ----
from bpc import cache as _cache
_cache.put("selftest:list", ["x"])  # writes a proper dict wrapper
_bad = _cache._key_to_path("selftest:bad")
os.makedirs(_cache.CACHE_DIR, exist_ok=True)
open(_bad, "w", encoding="utf-8").write("[1, 2, 3]")  # non-dict json
try:
    check("cache non-dict -> miss", _cache.get("selftest:bad", 9999), None)
finally:
    os.remove(_bad)

# ---- pseudo resistance aggregation (res_contributions; ids identical to PoE2) ----
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

# ---- poe.ninja gem economy: name+level+quality+corrupt bucket matching (economy.md 3c) ----
from bpc.poeninja import PoeNinjaEconomy
_econ = PoeNinjaEconomy.__new__(PoeNinjaEconomy)
_econ._gems = {
    "empower support": [
        {"name": "Empower Support", "variant": "3", "gemLevel": 3, "gemQuality": 0,
         "corrupted": None, "chaosValue": 50.0, "divineValue": 0.5, "listingCount": 10},
        {"name": "Empower Support", "variant": "4c", "gemLevel": 4, "gemQuality": 0,
         "corrupted": True, "chaosValue": 780.0, "divineValue": 7.6, "listingCount": 37}],
    "added fire damage support": [
        {"name": "Added Fire Damage Support", "variant": "20/20", "gemLevel": 20,
         "gemQuality": 20, "corrupted": None, "chaosValue": 3.0, "divineValue": None, "listingCount": 100},
        {"name": "Added Fire Damage Support", "variant": "21/20c", "gemLevel": 21,
         "gemQuality": 20, "corrupted": True, "chaosValue": 120.0, "divineValue": 1.2, "listingCount": 20}],
}
check("gem exact corrupted bucket", _econ.gem_price("Empower Support", 4, 0, True)["variant"], "4c")
check("gem uncorrupted bucket", _econ.gem_price("Empower Support", 3, 0, False)["variant"], "3")
check("gem nearest lvl/qual bucket", _econ.gem_price("Added Fire Damage Support", 19, 17, False)["variant"], "20/20")
check("gem 21c corrupted bucket", _econ.gem_price("Added Fire Damage Support", 21, 20, True)["variant"], "21/20c")
check("gem PoB suffix fallback", (_econ.gem_price("Empower", 4, 0, True) or {}).get("variant"), "4c")
check("gem unknown -> None", _econ.gem_price("Nonexistent Gem", 20, 20, False), None)
approx("gem chaos value", _econ.gem_price("Empower Support", 4, 0, True)["chaos"], 780.0)

# ---- engine->UI JSON contract: exalted -> chaos rename (report.build_payload) ----
from bpc.report import build_payload
from bpc.models import BuildMeta as _Meta, PriceResult as _PR, PriceTier as _PT
class _ConvStub:
    def divine_rate(self): return 102.5
_meta = _Meta(account="a", character="C", league="Allflame", char_class="Witch", level=90)
_it = _Item(name="Goldrim", base_type="Leather Cap", type_line="Leather Cap", frame_type=3,
            rarity="Unique", category="unique", group="equipment", slot="Helmet")
_res = _PR(item=_it, tier=_PT(minimum=1.0, median=2.0, high=3.0), confidence="high", trade_url="x")
_payload = build_payload(_meta, [_res], _ConvStub())
check("contract: item uses 'chaos'", "chaos" in _payload["items"][0], True)
check("contract: item drops 'exalted'", "exalted" in _payload["items"][0], False)
check("contract: divine_to_chaos present", "divine_to_chaos" in _payload, True)
check("contract: no divine_to_exalted", "divine_to_exalted" in _payload, False)
check("contract: currency_unit chaos", _payload["currency_unit"], "chaos")
check("contract: totals_chaos present", "totals_chaos" in _payload, True)
check("contract: item chaos tier", _payload["items"][0]["chaos"], {"min": 1.0, "median": 2.0, "high": 3.0})

# ---- Path of Building import (PoE1: count="nil" gems kept; catalyst/percentile lines not leaked) ----
import base64 as _b64, zlib as _zlib
from bpc import pob as _pob, engine as _engine
_xml = ('<?xml version="1.0"?><PathOfBuilding>'
        '<Build level="92" className="Witch" ascendClassName="Elementalist"/>'
        '<Items activeItemSet="1">'
        '<Item id="1">\nRarity: UNIQUE\nThe Gull\nRaven Mask\n'
        'EvasionBasePercentile: 0.6665\nEnergyShieldBasePercentile: 0.7042\n'
        'Item Level: 80\nQuality: 20\nSockets: W-R-B-W\nImplicits: 0\n'
        '131% increased Evasion and Energy Shield\nCorrupted\n</Item>'
        '<Item id="2">\nRarity: UNIQUE\nMarylenes Fallacy\nLapis Amulet\n'
        'Catalyst: Unstable\nCatalystQuality: 20\nItem Level: 83\nImplicits: 2\n'
        '{crafted}Allocates Force of Darkness\n+23 to Intelligence\n</Item>'
        '<ItemSet id="1"><Slot name="Helmet" itemId="1"/><Slot name="Amulet" itemId="2"/></ItemSet>'
        '</Items>'
        '<Skills activeSkillSet="1"><SkillSet id="1">'
        '<Skill><Gem nameSpec="Righteous Fire" skillId="RighteousFire" level="20" quality="20" count="nil" enabled="true"/></Skill>'
        '<Skill><Gem nameSpec="Empower" skillId="SupportEmpower" gemId="Metadata/Items/Gems/SupportGemAdditionalLevel" level="3" quality="0" count="nil" enabled="true"/></Skill>'
        '</SkillSet></Skills>'
        '</PathOfBuilding>')
_code = _b64.urlsafe_b64encode(_zlib.compress(_xml.encode())).decode()
check("pob decode PoE1 root", "<PathOfBuilding>" in _pob.decode(_code), True)
check("pob looks_like_code", _pob.looks_like_code(_code), True)
check("pob not code (url)", _pob.looks_like_code("https://pobb.in/x"), False)
_m, _items = _pob.parse(_code, {"all": {"Raven Mask", "Lapis Amulet"}, "by_group": {}})
_gems = [i for i in _items if i.category == "gem"]
check("pob count=nil gems NOT dropped", len(_gems), 2)
_rf = next((g for g in _gems if g.base_type == "Righteous Fire"), None)
check("pob gem level captured", _rf.gem_level if _rf else None, 20)
check("pob gem quality captured", _rf.gem_quality if _rf else None, 20)
check("pob active not support", _rf.support if _rf else None, False)
_emp = next((g for g in _gems if g.base_type == "Empower"), None)
check("pob support detected", _emp.support if _emp else None, True)
_gull = next((i for i in _items if i.name == "The Gull"), None)
check("pob unique parsed", _gull is not None, True)
if _gull:
    check("pob no BasePercentile leak",
          any("BasePercentile" in m for m in _gull.explicit_mods), False)
    check("pob unique mod kept",
          "131% increased Evasion and Energy Shield" in _gull.explicit_mods, True)
    check("pob unique corrupted", _gull.corrupted, True)
_mar = next((i for i in _items if i.name == "Marylenes Fallacy"), None)
check("pob catalyst unique parsed", _mar is not None, True)
if _mar:
    check("pob no Catalyst leak",
          any("Catalyst" in m for m in (_mar.implicit_mods + _mar.explicit_mods)), False)
    check("pob catalyst implicit boundary kept",
          "Allocates Force of Darkness" in _mar.implicit_mods, True)
check("pobb.in raw url", _engine._pob_raw_candidates("https://pobb.in/abc")[0],
      "https://pobb.in/abc/raw")
check("pastebin raw url", _engine._pob_raw_candidates("https://pastebin.com/Xy")[0],
      "https://pastebin.com/raw/Xy")

# ---- poeninja defences from item properties ----
_njdef = _pn._defences({"properties": [
    {"name": "[EnergyShield|Energy Shield]", "values": [["477", 0]]},
    {"name": "[Evasion|Evasion Rating]", "values": [["1560", 0]]},
    {"name": "Armour", "values": [["1958", 0]]},
    {"name": "[Quality]", "values": [["+20%", 1]]}]})
check("poeninja defences from properties", _njdef, {"es": 477, "ev": 1560, "ar": 1958})

# ---- normalize integration on the real poe.ninja PoE1 character fixture (offline) ----
import json as _json2
_fix = os.path.join(_HERE, "research", "data", "char_poe1.json")
if os.path.exists(_fix):
    with open(_fix, encoding="utf-8") as _fh:
        _char = _json2.load(_fh)
    _meta_c, _items_c = _pn.normalize(_char)
    _groups = {}
    for _it in _items_c:
        _groups[_it.group] = _groups.get(_it.group, 0) + 1
    check("normalize has equipment", _groups.get("equipment", 0) > 0, True)
    check("normalize has flask", _groups.get("flask", 0) > 0, True)
    check("normalize has jewel", _groups.get("jewel", 0) > 0, True)
    check("normalize has gem", _groups.get("gem", 0) > 0, True)
    check("normalize NO rune group", "rune" in _groups, False)
    check("normalize no CAT_RUNE items", any(i.category == "rune" for i in _items_c), False)
    _body = next((i for i in _items_c if i.raw.get("inventoryId") == "BodyArmour"), None)
    check("normalize body armour found", _body is not None, True)
    if _body:
        check("normalize 6-link body armour", _body.max_link, 6)
        check("normalize body total_sockets 6", _body.total_sockets, 6)
    _gem = next((i for i in _items_c if i.group == "gem" and i.supports), None)
    check("normalize gem group has supports", _gem is not None, True)
    if _gem:
        _s0 = _gem.supports[0]
        check("normalize support has level/quality/corrupted",
              all(k in _s0 for k in ("name", "level", "quality", "corrupted")), True)
        check("normalize support drops lineage", "lineage" in _s0, False)
else:
    print("(skipped char_poe1.json fixture tests: dump not present)")

if _fails:
    print("FAILED:")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("All self-tests passed.")
