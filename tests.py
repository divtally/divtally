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
# foil/relic uniques carry their OWN frame id (9=Relic, 10=SupporterFoil), NOT frameType 3 + a
# flag -- they must route to unique, else high-value foils (e.g. Nimis) are dropped to normal.
check("cat relic ft9 -> unique", _pn._categorise({"frameType": 9}, "equipment"), "unique")
check("cat foil ft10 -> unique", _pn._categorise({"frameType": 10}, "equipment"), "unique")
check("cat rarity=Unique fallback (unknown frame)",
      _pn._categorise({"frameType": 99, "rarity": "Unique"}, "equipment"), "unique")

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

# FIX (MINOR-2): the poe.ninja economy must be fed the NORMALISED trade league, not the raw
# SSF build league (poe.ninja publishes no SSF economy). resolve_trade_league maps an SSF league
# to its tradeable parent; engine.prepare* now builds PoeNinjaEconomy(trade_league). Verify the
# mapping offline (stub the live league list) + that the resolved economy league carries no 'ssf'.
from bpc.engine import resolve_trade_league as _rtl
from bpc.trade import TradeClient as _TC
from bpc.poeninja import PoeNinjaEconomy as _PNE
_orig_ll = _TC.__dict__["list_leagues"]
_TC.list_leagues = staticmethod(lambda: [{"id": "Allflame"}, {"id": "Hardcore Allflame"},
                                         {"id": "Standard"}, {"id": "Hardcore"}])
try:
    check("resolve SSF -> tradeable parent", _rtl("SSF Allflame"), "Allflame")
    check("resolve HC SSF -> hardcore parent", _rtl("HC SSF Allflame"), "Hardcore Allflame")
    check("resolve plain league unchanged", _rtl("Allflame"), "Allflame")
    check("economy league (from resolved) has no ssf",
          "ssf" in _PNE(_rtl("SSF Allflame")).league.lower(), False)
    check("economy league == tradeable parent", _PNE(_rtl("SSF Allflame")).league, "Allflame")
finally:
    _TC.list_leagues = _orig_ll

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

# ================= fix-minors coverage (all offline; RULE 8 documented promises) =================

# ---- FIX (MINOR-1): PoB import now populates sockets/links, so a 5/6-link PoB item yields the
#      SAME links filter the poe.ninja path yields (was dropped -> PoB gear underpriced) ----
_pob6_xml = ('<?xml version="1.0"?><PathOfBuilding>'
             '<Build level="90" className="Witch"/>'
             '<Items activeItemSet="1">'
             '<Item id="1">\nRarity: UNIQUE\nBlunderbore\nAstral Plate\n'
             'Armour: 1958\nItem Level: 83\nQuality: 20\nSockets: W-G-R-W-G-G\n'
             'LevelReq: 62\nImplicits: 1\n+2 to Level of Socketed Projectile Gems\n'
             '113% increased Armour\nCorrupted\n</Item>'
             '<ItemSet id="1"><Slot name="Body Armour" itemId="1"/></ItemSet>'
             '</Items></PathOfBuilding>')
_pob6_code = _b64.urlsafe_b64encode(_zlib.compress(_pob6_xml.encode())).decode()
_m6, _items6 = _pob.parse(_pob6_code, {"all": {"Astral Plate"}, "by_group": {}})
_body6 = next((i for i in _items6 if i.base_type == "Astral Plate"), None)
check("pob 6-link body parsed", _body6 is not None, True)
if _body6:
    check("pob 6-link max_link=6", _body6.max_link, 6)
    check("pob 6-link total_sockets=6", _body6.total_sockets, 6)
    check("pob 6-link socket_colours len", len(_body6.socket_colours), 6)
    # poe.ninja derives max_link via _sockets_info; both input paths must pin the SAME links
    _nj_ml = _pn._sockets_info({"sockets": [{"group": 0, "sColour": c} for c in "WGRWGG"]})[1]
    _nj_body = _Item(name="Blunderbore", base_type="Astral Plate", type_line="", frame_type=3,
                     rarity="Unique", category="unique", group="equipment",
                     slot="Body Armour", max_link=_nj_ml)
    check("pob links filter == poe.ninja links filter",
          _pnew._links_filter(_body6), _pnew._links_filter(_nj_body))
    check("pob 6-link filter is min-6 socket-links filter",
          _pnew._links_filter(_body6), {"socket_filters": {"filters": {"links": {"min": 6}}}})
# unlinked groups (space-separated): max_link = size of the largest hyphen-run, not total
_unlinked = _pob._parse_sockets("R-G B W")
check("pob unlinked groups max_link=2", _unlinked[1], 2)
check("pob unlinked groups total=4", _unlinked[2], 4)

# ---- R4-1 / R4-2: PoB gem CORRUPTION inference + weapon-SWAP flagging (parse layer) ----
# PoB encodes gem corruption implicitly (level>20 or quality>20, no explicit attr) and sockets
# swap skills in "Weapon 1/2 Swap" slots. Both must reach the same swap-exclusion + corrupted
# economy line the poe.ninja path uses. raw.inventoryId in (Weapon2, Offhand2) == swap (mirrors
# response._is_swap); corrupted picks the dearer poe.ninja corrupted line.
_pobsc_xml = ('<?xml version="1.0"?><PathOfBuilding>'
              '<Build level="95" className="Witch"/>'
              '<Items activeItemSet="1">'
              '<Item id="1">\nRarity: RARE\nMain Wand\nProphecy Wand\nItem Level: 80\nImplicits: 0\n</Item>'
              '<Item id="2">\nRarity: RARE\nSwap Bow\nThicket Bow\nItem Level: 80\nImplicits: 0\n</Item>'
              '<Item id="3">\nRarity: RARE\nSwap Ward\nPlank Kite Shield\nItem Level: 80\nImplicits: 0\n</Item>'
              '<ItemSet id="1">'
              '<Slot name="Weapon 1" itemId="1"/>'
              '<Slot name="Weapon 1 Swap" itemId="2"/>'
              '<Slot name="Weapon 2 Swap" itemId="3"/>'
              '</ItemSet></Items>'
              '<Skills activeSkillSet="1"><SkillSet id="1">'
              '<Skill slot="Body Armour" enabled="true">'
              '<Gem nameSpec="Vortex" skillId="Vortex" level="21" quality="20" enabled="true"/>'
              '<Gem nameSpec="Hypothermia Support" skillId="SupportHypothermia" level="20" quality="23" enabled="true"/>'
              '<Gem nameSpec="Controlled Destruction Support" skillId="SupportControlledDestruction" level="20" quality="20" enabled="true"/>'
              '</Skill>'
              '<Skill slot="Weapon 1 Swap" enabled="true">'
              '<Gem nameSpec="Eclipse" skillId="Eclipse" level="20" quality="0" enabled="true"/>'
              '</Skill>'
              '</SkillSet></Skills></PathOfBuilding>')
_pobsc_code = _b64.urlsafe_b64encode(_zlib.compress(_pobsc_xml.encode())).decode()
_m_sc, _it_sc = _pob.parse(_pobsc_code, {"all": {"Prophecy Wand", "Thicket Bow", "Plank Kite Shield"},
                                         "by_group": {"Armour": {"Plank Kite Shield"}}})
def _byname_sc(nm):
    return next((i for i in _it_sc if (i.name or i.base_type) == nm), None)
def _inv_sc(it):
    return (it.raw or {}).get("inventoryId") if it else None
_main_w = next((i for i in _it_sc if i.name == "Main Wand"), None)
_swap_bow = next((i for i in _it_sc if i.name == "Swap Bow"), None)
_swap_wd = next((i for i in _it_sc if i.name == "Swap Ward"), None)
check("R4-2 main-hand NOT swap-flagged", _inv_sc(_main_w), "Weapon")
check("R4-2 swap main-hand -> Weapon2 (swap)", _inv_sc(_swap_bow), "Weapon2")
check("R4-2 swap off-hand (armour base) -> Offhand2 (swap, not downgraded)", _inv_sc(_swap_wd), "Offhand2")
_gems_sc = [i for i in _it_sc if i.category == "gem"]
_vortex = next((g for g in _gems_sc if g.base_type == "Vortex"), None)
_hypo = next((g for g in _gems_sc if g.base_type == "Hypothermia Support"), None)
_cd = next((g for g in _gems_sc if g.base_type == "Controlled Destruction Support"), None)
_eclipse = next((g for g in _gems_sc if g.base_type == "Eclipse"), None)
check("R4-1 level-21 gem inferred corrupted", _vortex.corrupted if _vortex else None, True)
check("R4-1 quality-23 gem inferred corrupted", _hypo.corrupted if _hypo else None, True)
check("R4-1 L20/Q20 gem NOT corrupted", _cd.corrupted if _cd else None, False)
check("R4-2 swap-socketed gem is swap-flagged (Weapon 1 Swap -> Weapon2)", _inv_sc(_eclipse), "Weapon2")
check("R4-2 main-skill gem NOT swap-flagged", _inv_sc(_vortex), None)
# swap gems are still EMITTED (excluded-by-default + toggle-able), not dropped
check("R4-2 swap gem still present in items (toggle-able, not dropped)", _eclipse is not None, True)
# an explicit corrupted="true" marker is honoured even at level/quality <= 20 (defensive)
_pobcx = ('<?xml version="1.0"?><PathOfBuilding><Build level="1"/><Items activeItemSet="1">'
          '<ItemSet id="1"/></Items><Skills activeSkillSet="1"><SkillSet id="1">'
          '<Skill slot="Helmet" enabled="true">'
          '<Gem nameSpec="Anger" skillId="Anger" level="20" quality="0" corrupted="true" enabled="true"/>'
          '</Skill></SkillSet></Skills></PathOfBuilding>')
_cx_code = _b64.urlsafe_b64encode(_zlib.compress(_pobcx.encode())).decode()
_cx_gems = [i for i in _pob.parse(_cx_code, {"all": set(), "by_group": {}})[1] if i.category == "gem"]
check("R4-1 explicit corrupted attr honoured at L20/Q0 (defensive)",
      (_cx_gems[0].corrupted if _cx_gems else None), True)

# ---- shared Pricer with offline fakes (no trade calls) for query-assembly + guardrail tests ----
from bpc.pricing import SEARCH_BUDGET as _BUDGET
class _FakeStatsRare:
    def stats_data(self):
        return {"result": [{"label": "Explicit", "entries": [
            {"id": "explicit.stat_life", "text": "+# to maximum Life"},
            {"id": "explicit.stat_fireres", "text": "+#% to Fire Resistance"}]}]}
class _FakeSearchClient:
    def __init__(self):
        self.league = "SelfTestPricerLeague"
        self.search_count = 0
    def search(self, query):
        self.search_count += 1
        return {"id": "QID0", "result": [], "total": 0}      # deterministic no-match
    def fetch(self, ids, qid):
        return []
_pr = Pricer.__new__(Pricer)
_pr.client = _FakeSearchClient()
_pr.status = "online"
_pr.mapper = _StatMapper(_FakeStatsRare())
_pr._valid_types = {"Vaal Regalia", "Testonium Plate"}
_pr.economy = None
_pr.verbose = False
_pr.progress = None
_pr.conv = CurrencyConverter.__new__(CurrencyConverter)
_pr.conv.client = None
_pr.conv.economy = None
_pr.conv._rates = {"chaos": 1.0}

# ---- (5b) rare default query requires ALL of the item's searchable affixes (extras allowed) ----
_rare_b = _Item(name="", base_type="Vaal Regalia", type_line="Vaal Regalia", frame_type=2,
                rarity="Rare", category="rare", group="equipment", slot="Body Armour",
                explicit_mods=["+90 to maximum Life", "+40% to Fire Resistance",
                               "12% increased Banana"],
                mod_src=["explicit", "explicit", "explicit"], raw={"inventoryId": "BodyArmour"})
_sg_b, _ef_b, _nskip_b = _pr._rare_default_filters(_rare_b)
check("rare default: single AND group", len(_sg_b) == 1 and _sg_b[0]["type"] == "and", True)
check("rare default requires ALL searchable affixes", len(_sg_b[0]["filters"]), 2)
check("rare default filter ids are the mapped mods",
      sorted(f["id"] for f in _sg_b[0]["filters"]),
      ["explicit.stat_fireres", "explicit.stat_life"])
check("rare default counts the unsearchable mod", _nskip_b, 1)

# ---- (5c) armour_filters total-defence construction (>=85% of each total) from Item.defences ----
_rare_c = _Item(name="", base_type="Testonium Plate", type_line="Testonium Plate", frame_type=2,
                rarity="Rare", category="rare", group="equipment", slot="Body Armour",
                defences={"ar": 1000, "es": 200}, raw={"inventoryId": "BodyArmour"})
_sg_c, _ef_c, _ = _pr._rare_default_filters(_rare_c)
check("armour totals built at 85%", _ef_c, {"ar": {"min": 850}, "es": {"min": 170}})
_q_c = _pr._rare_query(_rare_c, {"type": "Testonium Plate"}, _sg_c, _ef_c)
check("armour_filters embedded in query",
      _q_c["filters"]["armour_filters"], {"filters": {"ar": {"min": 850}, "es": {"min": 170}}})

# ---- (5d) no-match => confidence 'none', no numeric tier, but trade_url STILL present ----
_rare_d = _Item(name="", base_type="Testonium Plate", type_line="Testonium Plate", frame_type=2,
                rarity="Rare", category="rare", group="equipment", slot="Body Armour",
                raw={"inventoryId": "BodyArmour"})
_pr.client.search_count = 0
_res_d = _pr.price_rare(_rare_d)
check("no-match confidence none", _res_d.confidence, "none")
check("no-match has NO median number", _res_d.tier.median, None)
check("no-match has NO min number", _res_d.tier.minimum, None)
check("no-match STILL emits a trade_url",
      _res_d.trade_url.startswith("https://www.pathofexile.com/trade/search/"), True)

# ---- FIX (MINOR-3): a budget-SKIPPED row also carries a trade link + no number (was blank) ----
_uniq_skip = _Item(name="Headhunter", base_type="Leather Belt", type_line="Leather Belt",
                   frame_type=3, rarity="Unique", category="unique", group="equipment", slot="Belt")
_pr.client.search_count = _BUDGET             # force the per-run search-budget cap
_skips = _pr.price_build([_uniq_skip])
check("skipped: one result", len(_skips), 1)
check("skipped: method 'skipped'", _skips[0].method, "skipped")
check("skipped: confidence none", _skips[0].confidence, "none")
check("skipped: NO number", _skips[0].tier.median, None)
check("skipped: HAS a trade link (unpriceable guardrail)",
      _skips[0].trade_url.startswith("https://www.pathofexile.com/trade/search/"), True)
# a skipped RARE also gets a link, built from its default query WITHOUT executing a search
_rare_skip = _Item(name="", base_type="Testonium Plate", type_line="Testonium Plate", frame_type=2,
                   rarity="Rare", category="rare", group="equipment", slot="Body Armour",
                   defences={"ar": 1000}, raw={"inventoryId": "BodyArmour"})
_pr.client.search_count = _BUDGET
check("skipped rare: trade link present (no search run)",
      _pr.price_build([_rare_skip])[0].trade_url.startswith(
          "https://www.pathofexile.com/trade/search/"), True)

# ---- (5a) --status mapping: 5 documented options pass through; bogus/empty fall back to online ----
_orig_lt = Pricer._load_types
Pricer._load_types = lambda self: set()
class _StatusClient:
    league = "SelfTestStatusLeague"
    search_count = 0
    def stats_data(self):
        return {"result": []}
try:
    def _mk(st):
        return Pricer(_StatusClient(), verbose=False, status=st, economy=None)
    check("status options are the 5 documented", set(Pricer.STATUS_OPTIONS),
          {"online", "any", "onlineleague", "available", "securable"})
    for _s in Pricer.STATUS_OPTIONS:
        check("status " + _s + " -> option", _mk(_s)._status(), {"option": _s})
    check("status bogus -> online fallback", _mk("bananas")._status(), {"option": "online"})
    check("status empty -> online fallback", _mk("")._status(), {"option": "online"})
finally:
    Pricer._load_types = _orig_lt

# ---- (5e) CurrencyConverter.to_chaos for non-chaos currencies (divine/mirror), stubbed economy ----
class _StubEcon:
    def chaos_by_id(self, cat, cid):
        return {"divine": 102.5, "mirror": 16787.0}.get(cid)
_conve = CurrencyConverter.__new__(CurrencyConverter)
_conve.client = None
_conve.economy = _StubEcon()
_conve._rates = {"chaos": 1.0, "divine": 102.5, "mirror": 16787.0}
approx("to_chaos divine multiply", _conve.to_chaos(2, "divine"), 205.0)
approx("to_chaos mirror multiply", _conve.to_chaos(3, "mirror"), 50361.0)
approx("to_chaos chaos identity", _conve.to_chaos(7, "chaos"), 7.0)
approx("_lookup divine from stubbed economy", _conve._lookup("divine"), 102.5)
approx("_lookup mirror from stubbed economy", _conve._lookup("mirror"), 16787.0)
check("_lookup unknown currency -> None", _conve._lookup("unobtaniumorb"), None)

# ---- (5f) version-unique auto-detection: a build affix NOT shared by most listings is flagged
#      version-specific; a widely-shared affix is treated as a fixed roll (not flagged) ----
_lifep = util.mod_to_pattern("+90 to maximum Life")
_firep = util.mod_to_pattern("+40% to Fire Resistance")
_vu_item = _Item(name="Loreweave", base_type="Prismatic Ring", type_line="", frame_type=3,
                 rarity="Unique", category="unique", group="equipment", slot="Ring",
                 explicit_mods=["+90 to maximum Life", "+40% to Fire Resistance"])
# life shared by all 4 listings (fixed roll); fire res in only 1/4 (version-specific)
_vu_rare = [[10, [_lifep]], [12, [_lifep]], [15, [_lifep]], [20, [_lifep, _firep]]]
_va = _pr._variant_affixes(_vu_item, _vu_rare)
check("version-unique: rare affix flagged version-specific (mappable)",
      _va["mappable"], [{"id": "explicit.stat_fireres"}])
check("version-unique: shared affix not left unmappable", _va["unmappable"], [])
# the same affix shared by most listings -> fixed roll, NOT flagged
_vu_common = [[10, [_lifep, _firep]], [12, [_lifep, _firep]], [15, [_lifep, _firep]], [20, [_lifep]]]
check("version-unique: widely-shared affix treated as fixed roll",
      _pr._variant_affixes(_vu_item, _vu_common)["mappable"], [])
check("version-unique: <4 listings -> detection disabled",
      _pr._variant_affixes(_vu_item, [[10, [_firep]]])["mappable"], [])

# ================= D-0006 feedback round 1: gem host-grouping, GRANTED, flasks =================

# ---- host-item index: skills[].itemSlot -> host gear (slot label + name + unique flag) ----
_hchar = {"items": [
    {"itemSlot": 3, "itemData": {"inventoryId": "BodyArmour", "name": "Blunderbore",
                                 "baseType": "Astral Plate", "frameType": 3}},
    {"itemSlot": 9, "itemData": {"inventoryId": "Ring2", "name": "Lost Unity",
                                 "baseType": "Formless Ring", "frameType": 3}},
    {"itemSlot": 2, "itemData": {"inventoryId": "Gloves", "name": "",
                                 "baseType": "Sorcerer Gloves", "frameType": 2}}]}
_hidx = _pn._host_index(_hchar)
check("host index slot->label", _hidx[3]["slot_label"], "Body Armour")
check("host index unique name", _hidx[9]["name"], "Lost Unity")
check("host index unique flag", _hidx[9]["unique"], True)
check("host index rare uses base as name", _hidx[2]["name"], "Sorcerer Gloves")
check("host index rare not unique", _hidx[2]["unique"], False)

# ---- itemProvidedGems index (the granted authority) ----
_ppairs, _pnoslot = _pn._provided_gem_index(
    {"itemProvidedGems": [{"slot": 9, "gems": [
        {"name": "Herald of the Hive", "isBuiltInSupport": False}]}]})
check("provided pairs slot+name", (9, "herald of the hive") in _ppairs, True)
check("provided names_noslot empty", _pnoslot, set())

# ---- _gem_is_granted: the signals + the NON-granted socketed case (the owner's bug) ----
check("granted via itemProvidedGems",
      _pn._gem_is_granted({"name": "Herald of the Hive"}, {}, 9,
                          {(9, "herald of the hive")}, set()), True)
check("granted via isBuiltInSupport",
      _pn._gem_is_granted({"name": "X", "isBuiltInSupport": True}, {"baseType": "X"},
                          3, set(), set()), True)
check("granted via empty itemData",
      _pn._gem_is_granted({"name": "Herald of the Hive"}, {}, None, set(), set()), True)
check("SOCKETED herald NOT granted (owner's mis-flag bug)",
      _pn._gem_is_granted({"name": "Herald of Ice"},
                          {"baseType": "Herald of Ice", "frameType": 4},
                          7, {(9, "herald of the hive")}, set()), False)
check("granted via name-only fallback (slotless provided entry)",
      _pn._gem_is_granted({"name": "Portal"}, {"baseType": "Portal", "frameType": 4},
                          3, set(), {"portal"}), True)

# ---- D-0006 on the real fixture: ONLY item-provided gems flagged granted; host info present ----
if os.path.exists(_fix):
    _gems_c = [i for i in _items_c if i.group == "gem"]
    _granted_c = [i.display_name for i in _gems_c if i.granted]
    check("fixture: only the item-provided gem is granted", _granted_c, ["Herald of the Hive"])
    for _nm in ("Herald of Ice", "Herald of Ash", "Herald of Purity", "Leap Slam"):
        _g = next((x for x in _gems_c if x.display_name == _nm), None)
        check("fixture: socketed " + _nm + " NOT granted", (_g.granted if _g else None), False)
    _hoth = next((x for x in _gems_c if x.display_name == "Herald of the Hive"), None)
    check("fixture: granted active name recovered from entry",
          (_hoth.display_name if _hoth else None), "Herald of the Hive")
    check("fixture: granted active host is the granting item",
          (_hoth.host_name if _hoth else None), "Lost Unity")
    _ek = next((x for x in _gems_c if x.display_name == "Ethereal Knives of the Massacre"), None)
    check("fixture: main skill host slot", (_ek.host_slot if _ek else None), "Body Armour")
    check("fixture: main skill host name", (_ek.host_name if _ek else None), "Blunderbore")
    check("fixture: main skill host unique", (_ek.host_unique if _ek else None), True)
    _hice = next((x for x in _gems_c if x.display_name == "Herald of Ice"), None)
    check("fixture: a linked second active reads support=False",
          (_hice.supports[0]["support"] if _hice and _hice.supports else None), False)
    check("fixture: each support carries support+granted keys",
          (all(("support" in s and "granted" in s) for s in _ek.supports) if _ek else False), True)
    _flasks_c = [i for i in _items_c if i.group == "flask"]
    check("fixture: 5 flasks emitted", len(_flasks_c), 5)
    check("fixture: flask belt order preserved",
          [f.name for f in _flasks_c][:4],
          ["Wine of the Prophet", "The Overflowing Chalice", "Cinderswallow Urn", "Atziri's Promise"])

# ---- D-0006 price_skill: total == sum of PRICED gems (supports INCLUDED); granted EXCLUDED ----
class _GemEconD6:
    def gem_price(self, name, level=20, quality=0, corrupted=False):
        _t = {"active skill": 10.0, "support a": 3.0, "support b": 5.0}
        v = _t.get((name or "").lower())
        return None if v is None else {"chaos": v, "listing_count": 9, "variant": "",
                                       "divine": None, "level": level, "quality": quality}
_prg = Pricer.__new__(Pricer)
class _GClient:
    league = "SelfTestGemLeague"
    search_count = 0
_prg.client = _GClient()
_prg.status = "online"
_prg.economy = _GemEconD6()
_prg.conv = CurrencyConverter.__new__(CurrencyConverter)
_prg.conv.client = None
_prg.conv.economy = None
_prg.conv._rates = {"chaos": 1.0}

# (a) active + 2 supports, all priced -> total = 10+3+5; supports are INCLUDED in the total
_gd6 = _Item(name="", base_type="Active Skill", type_line="Active Skill", frame_type=4,
             rarity="Gem", category="gem", group="gem", slot="", gem_level=20, gem_quality=20,
             supports=[{"name": "Support A", "level": 20, "quality": 20, "corrupted": False,
                        "icon": "", "support": True, "granted": False},
                       {"name": "Support B", "level": 20, "quality": 0, "corrupted": False,
                        "icon": "", "support": True, "granted": False}],
             host_slot="Body Armour", host_name="Blunderbore", host_unique=True,
             host_inventory_id="BodyArmour")
_rg6 = _prg.price_skill(_gd6)
approx("gem total = active + every support", _rg6.extra["total_chaos"], 18.0)
check("gem total == sum of priced gems (SUPPORTS INCLUDED)",
      abs(_rg6.extra["total_chaos"]
          - sum(x["chaos"] for x in _rg6.extra["gems"] if x["chaos"] is not None)) < 1e-9, True)
check("gem breakdown = active + 2 supports", len(_rg6.extra["gems"]), 3)
check("gem breakdown[0] is the active (support False)", _rg6.extra["gems"][0]["support"], False)
check("gem extra carries host info",
      (_rg6.extra["host_slot"], _rg6.extra["host_name"], _rg6.extra["host_unique"]),
      ("Body Armour", "Blunderbore", True))
check("gem support entries both priced",
      sum(1 for x in _rg6.extra["gems"] if x["support"] and x["chaos"] is not None), 2)

# (b) granted ACTIVE with a real socketed support: active EXCLUDED, support STILL counts
_gd6g = _Item(name="", base_type="Active Skill", type_line="Active Skill", frame_type=4,
              rarity="Gem", category="gem", group="gem", slot="", gem_level=30, granted=True,
              host_name="Lost Unity",
              supports=[{"name": "Support A", "level": 20, "quality": 0, "corrupted": False,
                         "icon": "", "support": True, "granted": False}])
_rg6g = _prg.price_skill(_gd6g)
approx("granted active excluded; socketed support still counts", _rg6g.extra["total_chaos"], 3.0)
check("granted active has NO price in breakdown", _rg6g.extra["gems"][0]["chaos"], None)
check("granted active flagged granted in breakdown", _rg6g.extra["gems"][0]["granted"], True)
check("granted extra top-level flag set", _rg6g.extra["granted"], True)
check("granted total still == sum of priced gems",
      abs(_rg6g.extra["total_chaos"]
          - sum(x["chaos"] for x in _rg6g.extra["gems"] if x["chaos"] is not None)) < 1e-9, True)

# (c) fully-granted active, no supports -> total None (nothing to buy), NO misleading number
_gd6f = _Item(name="", base_type="Herald of the Hive", type_line="Herald of the Hive",
              frame_type=4, rarity="Gem", category="gem", group="gem", slot="",
              gem_level=30, granted=True, host_name="Lost Unity")
_rg6f = _prg.price_skill(_gd6f)
check("fully-granted skill total None", _rg6f.extra["total_chaos"], None)
check("fully-granted skill tier median None", _rg6f.tier.median, None)
check("fully-granted skill confidence none", _rg6f.confidence, "none")

# ---- D-0006 normalize emits ALL flasks in belt order (synthetic 5-utility-flask belt) ----
def _fl_entry(nm, base, frame, util_line):
    return {"itemSlot": 14, "itemData": {"name": nm, "baseType": base, "typeLine": base,
            "frameType": frame, "utilityMods": [util_line]}}
_char5 = {"account": "a", "name": "C", "level": 90, "class": "Witch", "items": [],
          "skills": [], "jewels": [], "flasks": [
    _fl_entry("Wise Oak", "Bismuth Flask", 3, "immune to elemental ailments"),
    _fl_entry("", "Quicksilver Flask", 1, "40% increased Movement Speed"),
    _fl_entry("Rumi's Concoction", "Granite Flask", 3, "+3000 to Armour"),
    _fl_entry("", "Quartz Flask", 1, "10% chance to Dodge"),
    _fl_entry("", "Basalt Flask", 1, "15% additional Physical Damage Reduction")]}
_m5, _items5 = _pn.normalize(_char5)
_fl5 = [i for i in _items5 if i.group == "flask"]
check("normalize: 5 utility flasks all emitted (none dropped)", len(_fl5), 5)
check("normalize: flask belt order preserved",
      [i.base_type for i in _fl5],
      ["Bismuth Flask", "Quicksilver Flask", "Granite Flask", "Quartz Flask", "Basalt Flask"])

# ---- D-0006 price_build RETURNS the flask group in belt order despite the category sort ----
def _flaskI(nm, base, frame, cat):
    return _Item(name=(nm if cat == "unique" else ""), base_type=base, type_line=base,
                 frame_type=frame, rarity=("Unique" if cat == "unique" else "Magic"),
                 category=cat, group="flask", slot="Flask", raw={"inventoryId": "Flask"})
# belt order interleaves magic + unique so the priority sort WOULD scramble it without the fix
_belt = [_flaskI("F0", "Quicksilver Flask", 1, "magic"),
         _flaskI("Atziri's Promise", "Amethyst Flask", 3, "unique"),
         _flaskI("F2", "Sulphur Flask", 1, "magic"),
         _flaskI("Cinderswallow Urn", "Silver Flask", 3, "unique"),
         _flaskI("F4", "Granite Flask", 1, "magic")]
_pr.client.search_count = 0
_res_belt = [r.item for r in _pr.price_build(list(_belt)) if r.item.group == "flask"]
check("price_build: all 5 flasks returned (none dropped)", len(_res_belt), 5)
check("price_build: flask belt order preserved (mixed unique/magic, not category-sorted)",
      [i.base_type for i in _res_belt],
      ["Quicksilver Flask", "Amethyst Flask", "Sulphur Flask", "Silver Flask", "Granite Flask"])

if _fails:
    print("FAILED:")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("All self-tests passed.")
