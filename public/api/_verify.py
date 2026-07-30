"""Local verifier for the PoE1 public serverless function (no Vercel account needed).

Underscore-prefixed => Vercel never routes it, and it is never import-traced into the
build/health function bundles (they don't import it), so shipping it is harmless. It is a
DEV tool: it reads offline fixtures from `research/data/` (not present in the deployed
bundle) and, in phase B, makes a handful of live poe.ninja calls.

Phase A (OFFLINE, hermetic): monkeypatch poeninja.get_json to serve research/data fixtures,
then exercise the REAL vendored code paths (normalize -> PublicPricer.price_build ->
response.build_response) plus contract assertions, a PoeNinjaEconomy.unique_price unit test
(name/variant/range), and a slim-vs-full StatMapper equality check.

Phase B (LIVE, one character): restores real networking, boots the actual Vercel `handler`
on 127.0.0.1:8951, GETs /api/build for a live poe.ninja PoE1 character, and validates the
response against the same contract. A handful of poe.ninja calls only; NEVER pathofexile.com
(enforced by _http._guard_host and asserted here).

Run:  python public/api/_verify.py
Env:  BPC_SKIP_LIVE=1 to skip phase B; BPC_LIVE_CHAR_URL to override the live character;
      BPC_TEST_OUT to choose where sample_response_*.json are written (default: temp dir).
"""
import json, os, sys, tempfile, threading, time, urllib.request

API = os.path.dirname(os.path.abspath(__file__))          # .../public/api
REPO = os.path.dirname(os.path.dirname(API))              # repo root
DATA = os.path.join(REPO, "research", "data")
sys.path.insert(0, API)

from _lib import cache, engine, poeninja, refdata, response, statmap   # noqa: E402
from _lib._http import _guard_host, HttpError                          # noqa: E402

FAILS = []
def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name + (f" :: {detail}" if detail else ""))
    print(f"  [{tag}] {name}" + (f" :: {detail}" if (detail and not cond) else ""))


def load(fn):
    with open(os.path.join(DATA, fn), encoding="utf-8") as f:
        return json.load(f)


# ---------- contract validator ----------
def validate_contract(doc, *, source):
    check("top.ok true", doc.get("ok") is True)
    check("schema_version present", bool(doc.get("schema_version")))
    m = doc.get("meta", {})
    for k in ("character", "class", "level", "league", "ninja_league", "source",
              "currency_unit", "divine_to_chaos", "generated_at", "pricing_note"):
        check(f"meta.{k} present", k in m, f"missing {k}")
    check("meta.currency_unit==chaos", m.get("currency_unit") == "chaos")
    check("meta.source matches", m.get("source") == source, f"{m.get('source')} != {source}")
    t = doc.get("totals", {})
    for k in ("chaos", "divine", "priced_items", "unpriced_items"):
        check(f"totals.{k} present", k in t)
    for k in ("min", "median", "high"):
        check(f"totals.chaos.{k} present", k in t.get("chaos", {}))
    items = doc.get("items")
    check("items is list", isinstance(items, list) and len(items) > 0, f"n={len(items or [])}")
    byidx = {str(it.get("index")): it for it in (items or [])}   # for the scope cross-checks
    for it in items or []:
        idx = it.get("index")
        for k in ("index", "name", "group", "category", "slot", "rarity", "price",
                  "trade_url", "trade_query"):
            check(f"item[{idx}].{k} present", k in it, f"missing {k}")
        p = it.get("price", {})
        for k in ("chaos", "divine", "confidence", "method", "source"):
            check(f"item[{idx}].price.{k}", k in p, f"missing {k}")
        for k in ("min", "median", "high"):
            check(f"item[{idx}].price.chaos.{k}", k in p.get("chaos", {}))
        cat = it.get("category")
        if cat in ("rare", "magic"):
            check(f"item[{idx}] rare/magic has trade_query", it.get("trade_query") is not None)
            check(f"item[{idx}] rare/magic not ninja-priced", p.get("source") != "poe.ninja")
        if cat == "gem":
            check(f"item[{idx}] gem kind=skill", p.get("kind") == "skill")
            check(f"item[{idx}] gem has gems[]", isinstance(p.get("gems"), list))
            gems = p.get("gems") or []
            tot = p.get("total_chaos")
            if tot is not None:
                s = sum(g["chaos"] for g in gems if g.get("chaos") is not None)
                check(f"item[{idx}] total_chaos==sum(priced gems)", abs(s - tot) < 1e-6, f"{s}!={tot}")
        if it.get("trade_query"):
            tq = it["trade_query"]
            check(f"item[{idx}].trade_query.query dict", isinstance(tq.get("query"), dict))
            check(f"item[{idx}].trade_query sort asc", tq.get("sort", {}).get("price") == "asc")
        u = it.get("trade_url") or ""
        if u:
            check(f"item[{idx}] trade_url is /trade/search", "/trade/search/" in u and "/api/" not in u, u[:80])
        # D-0019 (contract 2.8): a variant-registered unique carries a `variant` block.
        if "variant" in it:
            vb = it["variant"]
            check(f"item[{idx}].variant shape",
                  isinstance(vb, dict) and "class" in vb and "label" in vb
                  and isinstance(vb.get("locked_stats"), list), str(vb)[:90])
            check(f"item[{idx}].variant only on uniques", it.get("category") == "unique")
    rares = doc.get("rares") or {}
    for k, v in rares.items():
        for f in ("status", "name", "kind", "scope", "scope_q", "affixes", "pseudo"):
            check(f"rares[{k}].{f} present", f in v)
        check(f"rares[{k}].kind valid", v.get("kind") in ("rare", "unique", "magic"),
              str(v.get("kind")))
        # D-0016: rare/magic entries expose BOTH search scopes, and the DEFAULT trade_query is
        # the generic category when the slot maps to one, else the exact base type. Uniques keep
        # their name+type scope and carry no `scopes` payload (unchanged by D-0016).
        if v.get("kind") in ("rare", "magic"):
            sc = v.get("scopes")
            check(f"rares[{k}] scopes present (rare/magic)",
                  isinstance(sc, dict) and "category" in sc and "base" in sc, str(sc))
            cat, base = (sc or {}).get("category"), (sc or {}).get("base")
            q = ((byidx.get(k) or {}).get("trade_query") or {}).get("query") or {}
            opt = ((((q.get("filters") or {}).get("type_filters") or {}).get("filters") or {})
                   .get("category") or {}).get("option")
            if cat:
                check(f"rares[{k}] scopes.category has id+label",
                      isinstance(cat, dict) and bool(cat.get("id")) and bool(cat.get("label")),
                      str(cat))
                check(f"rares[{k}] default query scoped to category (D-0016)",
                      opt == cat.get("id"), f"query {opt!r} != {cat.get('id')!r}")
            elif base:
                check(f"rares[{k}] no-category default falls back to base type",
                      q.get("type") == base.get("type") and not opt,
                      f"type {q.get('type')!r} opt {opt!r}")
        else:
            check(f"rares[{k}] unique carries no scopes payload (D-0016 unchanged)",
                  "scopes" not in v)
        for a in v.get("affixes") or []:
            # picker-ready affix payload: every entry self-describes for the client picker
            for f in ("kind", "text", "stat_id", "value", "default_min", "default_max",
                      "searchable", "negated", "group", "defining"):
                check(f"rares[{k}] affix.{f} present", f in a, f"{a.get('text')!r} missing {f}")
            # a searchable affix prefills exactly one of min/max; unsearchable prefills neither.
            # A defining EXACT row (seed/socket count) carries `exact:true` = search min==max at
            # default_min, so it still prefills a single bound (D-0019).
            if a.get("searchable"):
                nn = (a.get("default_min") is not None) + (a.get("default_max") is not None)
                check(f"rares[{k}] affix prefills <=1 bound", nn <= 1, f"{a.get('text')!r}")
        for p in v.get("pseudo") or []:
            for f in ("kind", "text", "stat_id", "value", "default_min", "group", "folds"):
                check(f"rares[{k}] pseudo.{f} present", f in p, f"missing {f}")
            check(f"rares[{k}] pseudo.folds is list", isinstance(p.get("folds"), list))
            # every folded member points at a real resist affix on the same item
            for m in p.get("folds") or []:
                check(f"rares[{k}] fold member has index/text", "index" in m and "text" in m)
                aff = (v.get("affixes") or [])[m["index"]] if isinstance(m.get("index"), int) \
                    and 0 <= m["index"] < len(v.get("affixes") or []) else None
                check(f"rares[{k}] fold index -> resist affix",
                      bool(aff) and aff.get("resist") is True, str(m))
    # every trade-queryable non-gem item (rare/unique/magic) gets an affix-picker entry
    want = {str(it["index"]) for it in (items or [])
            if it.get("category") in ("rare", "unique", "magic")}
    check("every rare/unique/magic item has a rares entry", want <= set(rares.keys()),
          f"missing {sorted(want - set(rares.keys()))}")
    return {it.get("category") for it in items or []}


# ---------- fixture-backed get_json ----------
_CHAR = {"file": "char_poe1.json"}
def fake_get_json(url, params=None, timeout=30, headers=None):
    _guard_host(url)
    p = params or {}
    typ = p.get("type", "")
    if "data/index-state" in url:
        return load("ninja_econ_index_state.json")
    if "/builds/" in url and "/character" in url:
        return load(_CHAR["file"])
    if "economy/exchange" in url and typ == "Currency":
        return load("ninja_econ_currency.json")
    if "economy/stash" in url and typ == "SkillGem":
        return load("ninja_econ_skillgem.json")
    if "economy/stash" in url and typ.startswith("Unique"):
        return {"lines": []}
    raise HttpError(f"fixture miss: {url} {p}")


def fresh_cache():
    cache._mem.clear()
    cache.CACHE_DIR = tempfile.mkdtemp(prefix="bpc_test_")


def phase_a():
    print("\n== PHASE A: offline (fixtures) ==")
    fresh_cache()
    full = statmap.StatMapper(load("trade_stats.json"))
    slim = statmap.StatMapper(refdata.stats_data())
    check("slim stats _map == full _map", slim._map == full._map, f"slim={len(slim._map)} full={len(full._map)}")
    check("slim stats _groups == full _groups", slim._groups == full._groups)

    # ---- D-0016: default rare/magic scope = item CATEGORY (source-of-truth + scope logic) ----
    from _lib import querybuild as qb
    from _lib.models import Item as _Item, CAT_RARE as _CAT_RARE
    # (A) every category option id the query-builder can emit is a REAL trade category, and
    # every `scopes` label matches the source filters' display text VERBATIM (no invented ids).
    _filt = load("trade_data_filters.json")
    _cat_src = {}
    for _grp in _filt.get("result", []):
        if _grp.get("id") == "type_filters":
            for _f in _grp.get("filters", []):
                if _f.get("id") == "category":
                    for _o in _f.get("option", {}).get("options", []):
                        if _o.get("id"):
                            _cat_src[_o["id"]] = _o.get("text", "")
    check("source filters carry the category options", len(_cat_src) > 20, str(len(_cat_src)))
    _emitted = (set(qb._INVENTORY_CATEGORY.values())
                | set(qb._WEAPON_SUFFIX_CATEGORY.values()) | {"armour.quiver"})
    for _cid in sorted(_emitted):
        check(f"category id {_cid!r} present in source filters", _cid in _cat_src, "invented id")
    for _cid, _lbl in qb._CATEGORY_LABEL.items():
        check(f"category label {_cid!r} matches source", _cat_src.get(_cid) == _lbl,
              f"{_lbl!r} != {_cat_src.get(_cid)!r}")
    # (B) scope selection: category default (+ weapon subcat), quiver correctness fix,
    # ambiguous-weapon -> generic, exact-base alternative, and base fallback (no category).
    _p = qb.PublicPricer("TestLeague", None, statmap.StatMapper(refdata.stats_data()),
                         {"Opal Wand", "Thicket Bow", "Astral Plate", "Ornate Quiver"})

    def _mk(base, inv):
        return _Item(name="", base_type=base, type_line=base, frame_type=2, rarity="Rare",
                     category=_CAT_RARE, group="equipment", slot=inv, raw={"inventoryId": inv})
    _wsc = _p._rare_scopes(_mk("Opal Wand", "Weapon"))
    check("scope[wand] default is category weapon.wand (D-0016)",
          bool(_wsc) and _wsc[0][1] == "category"
          and _wsc[0][0]["filters"]["type_filters"]["filters"]["category"]["option"] == "weapon.wand",
          str(_wsc))
    check("scope[wand] exact base is the alternative", _wsc[-1] == ({"type": "Opal Wand"}, "base"))
    _wch = _p.scope_choices(_mk("Opal Wand", "Weapon"))
    check("scope[wand] scopes payload has category+base",
          _wch["category"] == {"id": "weapon.wand", "label": "Wand"}
          and _wch["base"] == {"type": "Opal Wand", "label": "Opal Wand"}, str(_wch))
    check("scope[quiver] Offhand quiver -> armour.quiver (not shield)",
          _p._category_option(_mk("Ornate Quiver", "Offhand2")) == "armour.quiver")
    check("scope[ambiguous weapon] stays generic 'weapon'",
          _p._category_option(_mk("Vaal Blade", "Weapon")) == "weapon")
    _osc = _p._rare_scopes(_mk("Astral Plate", ""))         # slot maps to no category
    check("scope[no-category] default falls back to exact base",
          bool(_osc) and _osc[0] == ({"type": "Astral Plate"}, "base"), str(_osc))
    check("scope[no-category] scopes.category is null",
          _p.scope_choices(_mk("Astral Plate", ""))["category"] is None)

    # ---- cluster-jewel resistance-fold regression ("Blight Joy" 0-result bug) ----
    # "Added Small Passive Skills also grant: +N% to X Resistance" is a PER-PASSIVE grant, not the
    # character's own resistance -> it must NOT fold into pseudo.pseudo_total_elemental_resistance
    # (which matches 0 cluster jewels), and the picker must search it by PRESENCE, not the roll.
    _grant = "Added Small Passive Skills also grant: +5% to Cold Resistance"
    _gear = "+45% to Cold Resistance"
    check("clusterjewel: 'also grant' res is NOT a foldable resist", qb._is_res_affix(_grant) is False)
    check("clusterjewel: gear res IS still a foldable resist (control)", qb._is_res_affix(_gear) is True)
    check("clusterjewel: 'also grant' res contributes 0 to elemental total",
          qb.res_contributions([_grant])["elemental"] == 0, str(qb.res_contributions([_grant])))
    check("clusterjewel: gear res still contributes to elemental total (control)",
          qb.res_contributions([_gear])["elemental"] == 45)
    _cj = _Item(name="", base_type="Large Cluster Jewel", type_line="Large Cluster Jewel",
                frame_type=2, rarity="Rare", category=_CAT_RARE, group="jewel", slot="Jewel",
                explicit_mods=["Adds 8 Passive Skills",
                               "2 Added Passive Skills are Jewel Sockets",
                               "Added Small Passive Skills grant: 10% increased Spell Damage",
                               _grant,
                               "1 Added Passive Skill is Conjured Wall",
                               "1 Added Passive Skill is Mage Hunter",
                               "1 Added Passive Skill is Thaumophage"],
                mod_src=["enchant", "enchant", "enchant", "explicit", "explicit", "explicit", "explicit"],
                raw={"inventoryId": "Jewel"})
    _opts = _p.affix_options(_cj)
    check("clusterjewel: NO elemental/chaos pseudo synthesised", _opts["pseudo"] == [],
          str([p.get("text") for p in _opts["pseudo"]]))
    _ca = next((a for a in _opts["affixes"] if "Cold Resistance" in (a.get("text") or "")), None)
    check("clusterjewel: cold-res-grant affix present", _ca is not None)
    if _ca:
        check("clusterjewel: cold-res-grant resist=False", _ca.get("resist") is False)
        check("clusterjewel: cold-res-grant searchable", _ca.get("searchable") is True)
        check("clusterjewel: cold-res-grant presence-only (default_min None)", _ca.get("default_min") is None)
        _sg, _eq, _ = _p._rare_default_filters(_cj)
        _flat = [f for g in _sg for f in g.get("filters", [])]
        _cf = next((f for f in _flat if f.get("id") == _ca.get("stat_id")), None)
        check("clusterjewel: default query grant filter is presence-only (no min)",
              _cf is not None and "value" not in _cf, str(_cf))

    # ---- Watcher's Eye: generic max Life/Mana/ES default to NOT-NEEDED (registry default_off) ----
    # Owner 2026-07-29: only the "while affected by <Aura>" combo drives Watcher's Eye price; the
    # generic max Life/Mana/ES base roll defaults to not-needed (priority "exclude") yet stays
    # searchable/selectable. The client maps priority "exclude" -> the not-needed tier.
    _we = _Item(name="Watcher's Eye", base_type="Prismatic Jewel", type_line="Prismatic Jewel",
                frame_type=3, rarity="Unique", category="unique", group="jewel", slot="Jewel",
                explicit_mods=["6% increased maximum Energy Shield",
                               "5% increased maximum Life",
                               "6% increased maximum Mana",
                               "+7% Chance to Block Attack Damage while affected by Determination",
                               "51% increased Cold Damage while affected by Hatred"],
                mod_src=["explicit"] * 5, raw={"inventoryId": "Jewel"})
    _weopts = _p.affix_options(_we)
    def _wefind(txt):
        return next((a for a in _weopts["affixes"] if txt in (a.get("text") or "")), None)
    for _t in ("increased maximum Energy Shield", "increased maximum Life", "increased maximum Mana"):
        _a = _wefind(_t)
        check(f"watcherseye: '{_t}' present", _a is not None)
        if _a:
            check(f"watcherseye: '{_t}' default-off (priority=exclude)",
                  _a.get("priority") == "exclude", str(_a.get("priority")))
            check(f"watcherseye: '{_t}' still searchable (user can re-select)", _a.get("searchable") is True)
    _aura = _wefind("while affected by Hatred")
    check("watcherseye: aura mod is NOT default-off",
          _aura is None or _aura.get("priority") != "exclude", str(_aura and _aura.get("priority")))

    # ---- magic JEWELS scanned like rares (owner: magic jewels weren't getting scanned) ----
    # A magic abyss/cluster jewel can carry price-defining rolls -> route it through the RARE path
    # (affix-filtered query = a real autoscan price), NOT the scope-only "magic is cheap" path.
    # Other magic items (flasks) stay cheap.
    _mj = _Item(name="", base_type="Cobalt Jewel", type_line="Vivid Crimson Jewel of Zealousness",
                frame_type=1, rarity="Magic", category="magic", group="jewel", slot="Jewel",
                explicit_mods=["7% increased maximum Life",
                               "8% increased Fire Damage over Time Multiplier"],
                mod_src=["explicit", "explicit"], raw={"inventoryId": "Jewel"})
    _mf = _Item(name="", base_type="Quicksilver Flask", type_line="Quicksilver Flask",
                frame_type=1, rarity="Magic", category="magic", group="flask", slot="Flask",
                explicit_mods=["25% increased Movement Speed"], mod_src=["explicit"],
                raw={"inventoryId": "Flask"})
    _pb = _p.price_build([_mj, _mf])
    check("magicjewel: priced like a rare (method=rare-unpriced)", _pb[0].method == "rare-unpriced", _pb[0].method)
    check("magicflask: stays cheap (method=magic-unpriced)", _pb[1].method == "magic-unpriced", _pb[1].method)
    _mjq = (_pb[0].extra.get("trade_query") or {}).get("query") or {}
    _mjfilters = [f for g in (_mjq.get("stats") or []) for f in (g.get("filters") or [])]
    check("magicjewel: query is affix-filtered (a real search, not scope-only)", len(_mjfilters) >= 1, str(len(_mjfilters)))

    # ---- Heist trinket: only "drop as" is required, the rest default-off (owner) ----
    # "Carrion Creed, Thief's Trinket" from the owner's screenshot. The 3 additional-items /
    # increased-Rarity mods over-constrain the search; only the currency-conversion mod prices it.
    _tk = _Item(name="Carrion Creed", base_type="Thief's Trinket", type_line="Thief's Trinket",
                frame_type=2, rarity="Rare", category="rare", group="trinket", slot="Trinket",
                explicit_mods=[
                    "2% chance to receive additional Blight items when opening a Reward Chest in a Heist",
                    "8% chance to receive additional Divination Card items when opening a Reward Chest in a Heist",
                    "5% chance in Heists for Orbs of Augmentation to drop as Chaos Orbs instead",
                    "19% increased Rarity of Items dropped in Heists"],
                mod_src=["explicit", "explicit", "explicit", "explicit"], raw={"inventoryId": "Trinket"})
    _tko = _p.affix_options(_tk)["affixes"]
    _tk_conv = [o for o in _tko if "to drop as" in o["text"].lower()]
    _tk_other = [o for o in _tko if o["kind"] == "stat" and "to drop as" not in o["text"].lower()]
    check("heisttrinket: every non-'drop as' mod is default-off (exclude)",
          all(o["priority"] == "exclude" for o in _tk_other), str([o["priority"] for o in _tk_other]))
    check("heisttrinket: the conversion mod is required (searchable)",
          bool(_tk_conv) and all(o["priority"] == "required" for o in _tk_conv), str([o["priority"] for o in _tk_conv]))
    # the auto-scan required set is ONLY the conversion mod (not the 3 others). Asserted on
    # _rare_default_filters directly -- scope-independent, so it doesn't need the trinket base in
    # this harness's tiny valid-types whitelist (prod resolves it: refdata.item_types has it).
    _tk_sg, _, _ = _p._rare_default_filters(_tk)
    _tkf = [f for g in _tk_sg for f in (g.get("filters") or [])]
    check("heisttrinket: auto-scan requires exactly 1 filter (the conversion mod)", len(_tkf) == 1, str(len(_tkf)))
    # a trinket with NO conversion mod is left alone (still requires all its mods)
    _tk2 = _Item(name="Plain Trinket", base_type="Thief's Trinket", type_line="Thief's Trinket",
                 frame_type=2, rarity="Rare", category="rare", group="trinket", slot="Trinket",
                 explicit_mods=["19% increased Rarity of Items dropped in Heists",
                                "12% increased Quantity of Items dropped in Heists"],
                 mod_src=["explicit", "explicit"], raw={"inventoryId": "Trinket"})
    _tk2o = [o for o in _p.affix_options(_tk2)["affixes"] if o["kind"] == "stat"]
    check("heisttrinket: no conversion mod -> curation is inert (nothing forced off)",
          all(o["priority"] != "exclude" for o in _tk2o), str([o["priority"] for o in _tk2o]))

    # ---- corruption default: the search matches the build item's OWN corruption state (owner) ----
    def _corrupt_opt(q):
        return ((((q or {}).get("filters") or {}).get("misc_filters") or {}).get("filters", {})
                .get("corrupted", {}).get("option"))
    _rr_nc = _Item(name="", base_type="Coral Ring", type_line="Coral Ring", frame_type=2, rarity="Rare",
                   category="rare", group="equipment", slot="Ring", explicit_mods=["+45 to maximum Life"],
                   mod_src=["explicit"], raw={"inventoryId": "Ring"}, corrupted=False)
    _rr_c = _Item(name="", base_type="Coral Ring", type_line="Coral Ring", frame_type=2, rarity="Rare",
                  category="rare", group="equipment", slot="Ring", explicit_mods=["+45 to maximum Life"],
                  mod_src=["explicit"], raw={"inventoryId": "Ring"}, corrupted=True)
    check("corruption: non-corrupted rare search excludes corrupted (option=false)",
          _corrupt_opt(_p._rare_query(_rr_nc, {"type": "Coral Ring"}, [], {})) == "false",
          str(_corrupt_opt(_p._rare_query(_rr_nc, {"type": "Coral Ring"}, [], {}))))
    check("corruption: corrupted rare search matches corrupted (option=true)",
          _corrupt_opt(_p._rare_query(_rr_c, {"type": "Coral Ring"}, [], {})) == "true",
          str(_corrupt_opt(_p._rare_query(_rr_c, {"type": "Coral Ring"}, [], {}))))
    # the amulet from the owner's screenshot: a non-corrupted unique whose search returned corrupted comps
    _uq_nc = _Item(name="Whispers of Infinity", base_type="Seaglass Amulet", type_line="Seaglass Amulet",
                   frame_type=3, rarity="Unique", category="unique", group="equipment", slot="Amulet",
                   explicit_mods=[], mod_src=[], raw={"inventoryId": "Amulet"}, corrupted=False)
    check("corruption: non-corrupted unique search excludes corrupted (option=false)",
          _corrupt_opt(_p._unique_query(_uq_nc)) == "false", str(_corrupt_opt(_p._unique_query(_uq_nc))))

    econ = poeninja.PoeNinjaEconomy("TestLeague")
    econ._uniques = {
        "mageblood": [{"name": "Mageblood", "baseType": "Heavy Belt", "variant": "5 Flasks",
                       "chaosValue": 5800000, "divineValue": 4900, "listingCount": 74, "count": 74}],
        "impresence": [
            {"name": "Impresence", "baseType": "Onyx Amulet", "variant": "Lightning",
             "chaosValue": 900, "listingCount": 8, "count": 10},
            {"name": "Impresence", "baseType": "Onyx Amulet", "variant": "Cold",
             "chaosValue": 700, "listingCount": 6, "count": 9},
            {"name": "Impresence", "baseType": "Onyx Amulet", "variant": "Fire",
             "chaosValue": 500, "listingCount": 5, "count": 7}]}
    mb = econ.unique_price("Mageblood", mod_text="", base_type="Heavy Belt")
    check("unique name-match single line", mb and mb["matched"] == "name" and mb["chaos_median"] == 5800000, str(mb))
    imp_l = econ.unique_price("Impresence", mod_text="Adds Lightning Damage; Auras from your Skills", base_type="Onyx Amulet")
    check("unique variant-match by mod text", imp_l and imp_l["matched"] == "variant"
          and imp_l["variant"] == "Lightning" and imp_l["chaos_median"] == 900, str(imp_l))
    imp_amb = econ.unique_price("Impresence", mod_text="some unrelated text", base_type="Onyx Amulet")
    check("unique ambiguous -> range", imp_amb and imp_amb["matched"] == "range"
          and imp_amb["chaos_min"] == 500 and imp_amb["chaos_median"] == 700
          and 700 <= imp_amb["chaos_high"] <= 900, str(imp_amb))
    check("unique not listed -> None", econ.unique_price("Nonexistent Item") is None)
    # ---- R1 M1/M3: link-split uniques priced at the copy's LINK TIER (not a min..high range) ----
    econ._uniques["inpulsa's broken heart"] = [
        {"name": "Inpulsa's Broken Heart", "baseType": "Sadist Garb", "variant": None,
         "links": 6, "chaosValue": 344.5, "listingCount": 30, "count": 30},
        {"name": "Inpulsa's Broken Heart", "baseType": "Sadist Garb", "variant": None,
         "links": 5, "chaosValue": 81.0, "listingCount": 40, "count": 40},
        {"name": "Inpulsa's Broken Heart", "baseType": "Sadist Garb", "variant": None,
         "links": None, "chaosValue": 10.0, "listingCount": 500, "count": 500}]
    inp6 = econ.unique_price("Inpulsa's Broken Heart", base_type="Sadist Garb", max_link=6)
    check("link-split: 6L item -> the 6L line as a POINT (344.5), not a 10..291 range",
          inp6 and inp6["matched"] == "variant"
          and inp6["chaos_min"] == inp6["chaos_median"] == inp6["chaos_high"] == 344.5, str(inp6))
    inp5 = econ.unique_price("Inpulsa's Broken Heart", base_type="Sadist Garb", max_link=5)
    check("link-split: 5L item -> the 5L line (81), not the 6L", inp5 and inp5["chaos_median"] == 81.0, str(inp5))
    inp3 = econ.unique_price("Inpulsa's Broken Heart", base_type="Sadist Garb", max_link=3)
    check("link-split: <5L item -> the unlinked base line (10), not the 5L median",
          inp3 and inp3["matched"] == "variant" and inp3["chaos_median"] == 10.0, str(inp3))
    inp0 = econ.unique_price("Inpulsa's Broken Heart", base_type="Sadist Garb")
    check("link-split: unknown link count -> range fallback (never guesses a tier)",
          inp0 and inp0["matched"] == "range", str(inp0))
    # non-monotonic tiers: match the link COUNT, not the price (a 5L can out-price the 6L)
    econ._uniques["replica farrul's fur"] = [
        {"name": "Replica Farrul's Fur", "baseType": "Triumphant Lamellar", "variant": None,
         "links": 5, "chaosValue": 3609.0, "listingCount": 5, "count": 5},
        {"name": "Replica Farrul's Fur", "baseType": "Triumphant Lamellar", "variant": None,
         "links": 6, "chaosValue": 1768.0, "listingCount": 9, "count": 9},
        {"name": "Replica Farrul's Fur", "baseType": "Triumphant Lamellar", "variant": None,
         "links": None, "chaosValue": 1323.0, "listingCount": 20, "count": 20}]
    rff6 = econ.unique_price("Replica Farrul's Fur", base_type="Triumphant Lamellar", max_link=6)
    check("link-split non-monotonic: 6L item -> the 6L line (1768), not the pricier 5L (3609)",
          rff6 and rff6["chaos_median"] == 1768.0, str(rff6))

    poeninja.get_json = fake_get_json
    engine._mapper_singleton = None; engine._types_singleton = None
    for fixture, label in (("char_poe1.json", "ascii"), ("char_poe1_unicode.json", "unicode")):
        _CHAR["file"] = fixture
        fresh_cache()
        url = "https://poe.ninja/poe1/builds/allflame/character/acc/char"
        meta, results, pricer, league = engine.run_estimate(url, status="online")
        doc = response.build_response(meta, results, pricer, league, "poe.ninja")
        print(f"  -- {label}: {len(doc['items'])} items, league={league!r}, "
              f"priced={doc['totals']['priced_items']}, unpriced={doc['totals']['unpriced_items']}")
        cats = validate_contract(doc, source="poe.ninja")
        check(f"[{label}] has gem items", "gem" in cats)
        check(f"[{label}] a gem priced from poe.ninja",
              any(it["category"] == "gem" and it["price"].get("total_chaos") is not None for it in doc["items"]))
        if label == "ascii":
            check("[ascii] a granted gem exists (Herald of the Hive)",
                  any(it["category"] == "gem" and it.get("granted") for it in doc["items"]))
            rr = doc.get("rares") or {}
            check("[ascii] magic item present in rares (kind=magic)",
                  any(v.get("kind") == "magic" for v in rr.values()))
            check("[ascii] a rare/unique carries pseudo resist totals",
                  any(v.get("pseudo") for v in rr.values()))
            check("[ascii] a pseudo total lists the affixes folded into it",
                  any(p.get("folds") for v in rr.values() for p in (v.get("pseudo") or [])))
            check("[ascii] every affix carries a group",
                  all(a.get("group") for v in rr.values() for a in (v.get("affixes") or [])))
            # D-0015 invariant preserved through the enriched payload: the DEFAULT rare query
            # still requires EVERY searchable affix (one stats filter per searchable stat affix,
            # one armour_filter per defence total). Ties the picker payload to the built query so
            # a future affix_options change can't silently drop an affix from the default search.
            byidx = {str(it["index"]): it for it in doc["items"]}
            for k, ent in rr.items():
                if ent.get("kind") != "rare":
                    continue
                q = ((byidx.get(k) or {}).get("trade_query") or {}).get("query") or {}
                n_stat_filt = sum(len(g.get("filters", [])) for g in (q.get("stats") or []))
                n_arm = len((((q.get("filters") or {}).get("armour_filters") or {}).get("filters") or {}))
                # IMPLICIT affixes are opt-in picker rows (D-0015), NOT part of the default rare
                # query, so they don't count toward the "requires all searchable EXPLICIT affixes"
                # invariant (base implicits come with the base; user opts in via the picker).
                want_stat = sum(1 for a in ent["affixes"] if a["kind"] == "stat"
                                and a["searchable"] and a.get("group") != "implicit")
                want_arm = sum(1 for a in ent["affixes"] if a["kind"] == "equip" and a.get("value"))
                check(f"[ascii] rare[{k}] default query requires all searchable explicit affixes",
                      n_stat_filt == want_stat and n_arm == want_arm,
                      f"stats {n_stat_filt}/{want_stat} armour {n_arm}/{want_arm}")
            globals()["_SAMPLE_DOC"] = doc
        try:
            json.dumps(doc, allow_nan=False); check(f"[{label}] strict-JSON", True)
        except ValueError as e:
            check(f"[{label}] strict-JSON", False, str(e))

    import base64, zlib
    fresh_cache()
    with open(os.path.join(DATA, "pob_sample.xml"), encoding="utf-8") as f:
        xml = f.read()
    code = base64.urlsafe_b64encode(zlib.compress(xml.encode("utf-8"))).decode("ascii")
    meta, results, pricer, league = engine.run_estimate(code, league="Standard", status="online")
    doc = response.build_response(meta, results, pricer, league, "pob")
    print(f"  -- PoB import: {len(doc['items'])} items, league={league!r}")
    validate_contract(doc, source="pob")
    check("PoB league honoured override", league == "Standard")
    linked = [it for it in doc["items"] if int(it.get("max_link", 0) or 0) >= 5]
    if linked:
        check("PoB 5L/6L item carries a links filter in trade_query",
              '"links"' in json.dumps(linked[0].get("trade_query") or {}))

    import build as buildmod
    code, body = buildmod._run("not a url or code", "", "online")
    check("bad input -> ok false", body.get("ok") is False and code >= 400, str(code))
    check("bad input -> error_type", bool(body.get("error_type")))
    # R1: a build-overview link and a PoE2 link are USER URL mistakes -> 400 bad_input (contract
    # sec.4 lists a build-overview link there), NOT 502 ninja_error (upstream failure). Parse
    # fails before any fetch, so these are hermetic.
    ov_code, ov_body = buildmod._run("https://poe.ninja/poe1/builds/allflame", "", "online")
    check("overview link -> 400 bad_input (was 502 ninja_error)",
          ov_code == 400 and ov_body.get("error_type") == "bad_input",
          f"{ov_code}/{ov_body.get('error_type')}")
    p2_code, p2_body = buildmod._run(
        "https://poe.ninja/poe2/builds/allflame/character/Foo-1234/Bar", "", "online")
    check("PoE2 link -> 400 bad_input (was 502 ninja_error)",
          p2_code == 400 and p2_body.get("error_type") == "bad_input",
          f"{p2_code}/{p2_body.get('error_type')}")


def phase_variant():
    """D-0019 variant-unique registry, hermetic (no network): the copy's variant-DEFINING
    trade filters, the registry-driven poe.ninja match (floor-cap / map-count / map-variant /
    unmatched->link), the picker's defining flags, and the item-row variant block. Fixtures
    are synthetic uniques + a mock poe.ninja unique overview (offline)."""
    print("\n== PHASE VARIANT: D-0019 registry wiring (offline) ==")
    from _lib import querybuild as qb
    from _lib.models import Item as I, CAT_UNIQUE, BuildMeta
    mapper = statmap.StatMapper(refdata.stats_data())

    def mk(name, base, mods, group="jewel"):
        return I(name=name, base_type=base, type_line=base, frame_type=3, rarity="Unique",
                 category=CAT_UNIQUE, group=group, slot="Jewel",
                 explicit_mods=mods, mod_src=["explicit"] * len(mods), raw={})

    econ = poeninja.PoeNinjaEconomy("TestLeague")
    econ._uniques = {
        "forbidden flesh": [{"name": "Forbidden Flesh", "baseType": "Cobalt Jewel",
                             "variant": None, "chaosValue": 30.0, "listingCount": 863, "count": 863}],
        "watcher's eye": [{"name": "Watcher's Eye", "baseType": "Prismatic Jewel",
                           "variant": None, "chaosValue": 50.0, "listingCount": 11320, "count": 11320}],
        "lethal pride": [{"name": "Lethal Pride", "baseType": "Timeless Jewel", "variant": None,
                          "chaosValue": 67.5, "listingCount": 6189, "count": 6189}],
        "voices": [
            {"name": "Voices", "baseType": "Large Cluster Jewel", "variant": "3 passives",
             "chaosValue": 7030, "listingCount": 15, "count": 15},
            {"name": "Voices", "baseType": "Large Cluster Jewel", "variant": "5 passives",
             "chaosValue": 507.0, "listingCount": 84, "count": 84},
            {"name": "Voices", "baseType": "Large Cluster Jewel", "variant": "7 passives",
             "chaosValue": 5.0, "listingCount": 312, "count": 312}],
        "shroud of the lightless": [   # NOTE: "1 Jewel" LABEL carries 3 abyssal sockets (non-literal)
            {"name": "Shroud of the Lightless", "baseType": "Carnal Armour", "variant": "1 Jewel",
             "chaosValue": 360.9, "listingCount": 13, "count": 13},
            {"name": "Shroud of the Lightless", "baseType": "Carnal Armour", "variant": "2 Jewels",
             "chaosValue": 3.0, "listingCount": 346, "count": 346}],
        "impresence": [
            {"name": "Impresence", "baseType": "Onyx Amulet", "variant": "Chaos",
             "chaosValue": 90.0, "listingCount": 493, "count": 493},
            {"name": "Impresence", "baseType": "Onyx Amulet", "variant": "Lightning",
             "chaosValue": 2.0, "listingCount": 323, "count": 323}],
        "bubonic trail": [   # R1 build4 M2: the 1-socket variant renders the SINGULAR mod text
            {"name": "Bubonic Trail", "baseType": "Murder Boots", "variant": "1 Jewel",
             "chaosValue": 1.0, "listingCount": 2564, "count": 2564},
            {"name": "Bubonic Trail", "baseType": "Murder Boots", "variant": "2 Jewels",
             "chaosValue": 10.0, "listingCount": 161, "count": 161}],
    }
    types = {"Cobalt Jewel", "Prismatic Jewel", "Timeless Jewel", "Large Cluster Jewel",
             "Carnal Armour", "Onyx Amulet", "Murder Boots"}
    P = qb.PublicPricer("TestLeague", econ, mapper, types, status="available")

    def stats_of(r):
        return (r.extra.get("trade_query") or {}).get("query", {}).get("stats", [{}])[0].get("filters", [])

    # ---- Forbidden Flesh: Allocates OPTION filter present + exact-variant ninja match ----
    ff = mk("Forbidden Flesh", "Cobalt Jewel",
            ["Allocates Berserker if you have the matching modifier on Forbidden Flame"])
    r = P.price_unique_ninja(ff)
    ffilt = stats_of(r)
    check("Forbidden Flesh: Allocates option filter present (split base|option form)",
          any(f.get("id") == "explicit.stat_1190333629"
              and (f.get("value") or {}).get("option") == 4194 for f in ffilt), str(ffilt))
    check("Forbidden Flesh: ninja floor matched + capped LOW (not high @863 listings)",
          r.method == "unique-ninja-floor" and r.confidence == "low" and r.extra["source"] == "poe.ninja",
          f"{r.method}/{r.confidence}/{r.extra.get('source')}")
    check("Forbidden Flesh: variant block class+label",
          r.extra["variant_info"]["class"] == "notable-jewel"
          and r.extra["variant_info"]["label"] == "Berserker", str(r.extra.get("variant_info")))

    # ---- Watcher's Eye 2-mod: both aura filters present, generic ES mod not required ----
    we = mk("Watcher's Eye", "Prismatic Jewel", [
        "+35 to maximum Energy Shield",
        "Damage Penetrates 10% Cold Resistance while affected by Hatred",
        "+30% to Critical Strike Multiplier while affected by Anger"])
    r = P.price_unique_ninja(we)
    wids = [f["id"] for f in stats_of(r)]
    check("Watcher's Eye 2-mod: both aura filters present",
          "explicit.stat_1222888897" in wids and "explicit.stat_3627458291" in wids, str(wids))
    check("Watcher's Eye 2-mod: exactly the 2 aura mods locked (generic ES not required)",
          len(wids) == 2, str(wids))
    check("Watcher's Eye: floor-capped LOW", r.method == "unique-ninja-floor" and r.confidence == "low")

    # ---- Lethal Pride: seed min==max + keystone(conqueror) id ----
    lp = mk("Lethal Pride", "Timeless Jewel",
            ["Commanded leadership over 15000 warriors under Kaom\nPassives in radius are Conquered by the Karui"])
    r = P.price_unique_ninja(lp)
    sf = stats_of(r)
    check("Lethal Pride: exact seed filter (min==max) on the conqueror id",
          len(sf) == 1 and sf[0]["id"] == "explicit.pseudo_timeless_jewel_kaom"
          and sf[0]["value"] == {"min": 15000, "max": 15000}, str(sf))
    check("Lethal Pride: floor-capped LOW (no per-seed ninja price)",
          r.method == "unique-ninja-floor" and r.confidence == "low")
    check("Lethal Pride: variant label carries conqueror + seed",
          r.extra["variant_info"]["label"] == "Kaom seed 15000", str(r.extra["variant_info"]["label"]))

    # ---- Voices: exact COUNT filter + map-count ninja match (7 passives -> its line) ----
    vo = mk("Voices", "Large Cluster Jewel", ["Adds 7 Small Passive Skills which grant nothing"])
    r = P.price_unique_ninja(vo)
    vf = stats_of(r)
    check("Voices: exact count filter min==max==7",
          len(vf) == 1 and vf[0]["id"] == "explicit.stat_1085446536"
          and vf[0]["value"] == {"min": 7, "max": 7}, str(vf))
    check("Voices: map-count picked the '7 passives' ninja line",
          r.method == "unique-ninja-variant" and abs((r.tier.median or 0) - 5.0) < 1e-6,
          f"{r.method}/{r.tier.median}")

    # ---- Shroud: map-count via OBSERVED abyssal_count (label '1 Jewel' is non-literal) ----
    sh = mk("Shroud of the Lightless", "Carnal Armour",
            ["Has 3 Abyssal Sockets", "+20 to maximum Energy Shield"], group="equipment")
    r = P.price_unique_ninja(sh)
    check("Shroud: 3 abyssal sockets -> '1 Jewel' line via observed abyssal_count (non-literal label)",
          r.method == "unique-ninja-variant" and abs((r.tier.median or 0) - 360.9) < 1e-6,
          f"{r.method}/{r.tier.median}")

    # ---- Bubonic Trail: exactly 1 abyssal socket renders the SINGULAR "Has 1 Abyssal Socket",
    # which the plural-only stat pattern can't match. The count MUST come from the socket array
    # (attr/sColour == 'A') so the copy is priced (map-count -> '1 Jewel' 1c), carries a non-empty
    # defining filter (D-0019), and gets a real label -- not unpriced/'count variant' (R1 M2). ----
    bt = I(name="Bubonic Trail", base_type="Murder Boots", type_line="Murder Boots",
           frame_type=3, rarity="Unique", category=CAT_UNIQUE, group="equipment", slot="Boots",
           explicit_mods=["Has 1 Abyssal Socket", "+20 to maximum Life"],
           mod_src=["explicit", "explicit"], raw={},
           sockets=[{"group": 0, "attr": "A", "sColour": "A"},
                    {"group": 0, "attr": "S", "sColour": "R"}])
    r = P.price_unique_ninja(bt)
    check("Bubonic Trail: singular 1-socket copy priced via socket-array count (map-count '1 Jewel' 1c)",
          r.method == "unique-ninja-variant" and abs((r.tier.median or 0) - 1.0) < 1e-6,
          f"{r.method}/{r.tier.median}")
    _bt_vi = r.extra.get("variant_info") or {}
    check("Bubonic Trail: defining abyssal filter locked (not empty) + real label (D-0019 / contract 2.8)",
          bool(_bt_vi.get("locked_stats")) and _bt_vi.get("label") not in ("count variant", "", None),
          str(_bt_vi))
    _bt_q = (r.extra.get("trade_query") or {}).get("query", {}).get("stats", [{}])[0].get("filters", [])
    check("Bubonic Trail: trade_query carries the exact abyssal-count filter (min==max==1)",
          any(f.get("id") == "explicit.stat_3527617737"
              and f.get("value") == {"min": 1, "max": 1} for f in _bt_q), str(_bt_q))

    # ---- Impresence: map-variant by mod text; unmatchable -> unpriced + link ----
    im = P.price_unique_ninja(mk("Impresence", "Onyx Amulet",
                                 ["Adds 20 to 40 Lightning Damage", "Grants Level 20 Conductivity"]))
    check("Impresence: map-variant picked 'Lightning' line",
          im.method == "unique-ninja-variant" and abs((im.tier.median or 0) - 2.0) < 1e-6,
          f"{im.method}/{im.tier.median}")
    imu = P.price_unique_ninja(mk("Impresence", "Onyx Amulet", ["some unrelated text"]))
    check("Impresence unmatchable -> unpriced + link (never cheapest-any-variant)",
          imu.method == "unique-unpriced" and imu.extra["source"] == "none" and bool(imu.trade_url),
          f"{imu.method}/{imu.extra.get('source')}/url={bool(imu.trade_url)}")

    # ---- non-registry unique still uses the legacy path (name/variant/range) ----
    econ._uniques["nonvariant belt"] = [{"name": "Nonvariant Belt", "baseType": "Heavy Belt",
                                         "variant": None, "chaosValue": 12.0, "listingCount": 7, "count": 7}]
    nv = P.price_unique_ninja(mk("Nonvariant Belt", "Heavy Belt", ["+40 to maximum Life"], group="equipment"))
    check("non-registry unique keeps legacy name-match (not floor)",
          nv.method == "unique-ninja" and nv.confidence == "high", f"{nv.method}/{nv.confidence}")

    # ---- D-0022: Dragonfang's Flight family -- GEM-LEVEL variant. poe.ninja FOLDS every
    # "+# to Level of all <X> Gems" version into ONE line, so the price identity is WHICH gem/tag
    # the copy grants -- matched from the copy's OWN mod to its individual indexable_skill /
    # per-tag stat id (NOT an option stat; live-verified no base|opt form -- notes-d0022-api.md).
    # The query must carry EXACTLY that one gem-level filter, never the copy's fixed
    # resistance / reservation-efficiency / reduced-attribute-requirement mods. ----
    econ._uniques["replica dragonfang's flight"] = [
        {"name": "Replica Dragonfang's Flight", "baseType": "Onyx Amulet", "variant": None,
         "chaosValue": 15.0, "listingCount": 7216, "count": 399}]
    rep_dd = mk("Replica Dragonfang's Flight", "Onyx Amulet", [
        "+3 to Level of all Determination Gems",
        "+7% to all Elemental Resistances",
        "8% increased Reservation Efficiency of Skills",
        "Items and Gems have 6% reduced Attribute Requirements"], group="equipment")
    r = P.price_unique_ninja(rep_dd)
    rf = stats_of(r)
    check("Replica Dragonfang: exactly ONE defining filter = the Determination gem-level id (min=3)",
          rf == [{"id": "explicit.indexable_skill_67", "value": {"min": 3}}], str(rf))
    check("Replica Dragonfang: floor-capped LOW (ninja folds all gems into one 15c line)",
          r.method == "unique-ninja-floor" and r.confidence == "low"
          and abs((r.tier.median or 0) - 15.0) < 1e-6, f"{r.method}/{r.confidence}/{r.tier.median}")
    check("Replica Dragonfang: variant label names the specific gem mod",
          (r.extra.get("variant_info") or {}).get("label") == "+3 to Level of all Determination Gems",
          str((r.extra.get("variant_info") or {}).get("label")))
    # copy-specific: a DIFFERENT gem (Spark) must emit Spark's id, proving the filter is read off
    # the COPY's own mod, not a fixed id baked into the recipe.
    rep_spark = P.price_unique_ninja(mk("Replica Dragonfang's Flight", "Onyx Amulet",
                   ["+3 to Level of all Spark Gems", "+7% to all Elemental Resistances"], group="equipment"))
    check("Replica Dragonfang: a Spark copy emits Spark's id, not Determination's (copy-specific)",
          stats_of(rep_spark) == [{"id": "explicit.indexable_skill_27", "value": {"min": 3}}],
          str(stats_of(rep_spark)))
    # base "Dragonfang's Flight" is DELIBERATELY not a shipped registry item: it does NOT exist
    # as a tradeable PoE1 unique (LIVE /api/trade/data/items lists only the Replica; a base name
    # search returns 400 "Unknown item name" -- notes-d0022-api.md). Instead lock the gem-level
    # MATCHER contract directly: it recognises BOTH the per-gem ("<Gem> Gems") and the per-tag
    # ("<Tag> Skill Gems") forms and rejects the item's fixed non-gem mods, so a future per-tag
    # gem-level unique would be matched without shipping a phantom entry today.
    from _lib import variantreg as _vr
    check("gem-level matcher: recognises the per-specific-gem form (Replica, no 'Skill')",
          _vr._is_gem_level_mod("+3 to Level of all Determination Gems") is True)
    check("gem-level matcher: recognises the per-tag 'Skill Gems' form (future-proofing)",
          _vr._is_gem_level_mod("+1 to Level of all Fire Skill Gems") is True)
    check("gem-level matcher: rejects the copy's fixed res / reservation / attr-req mods",
          not _vr._is_gem_level_mod("+7% to all Elemental Resistances")
          and not _vr._is_gem_level_mod("Items and Gems have 6% reduced Attribute Requirements")
          and not _vr._is_gem_level_mod("8% increased Reservation Efficiency of Skills"))

    # ---- picker payload + item-row variant block via the FULL response ----
    from _lib import response as resp
    items = [ff, we, lp, vo, sh, rep_dd]
    results = P.price_build(items)
    meta = BuildMeta(account="t", character="t", league="TestLeague")
    doc = resp.build_response(meta, results, P, "TestLeague", "poe.ninja")
    cats = validate_contract(doc, source="poe.ninja")   # reuse the full contract validator
    check("variant fixtures are uniques", cats == {"unique"}, str(cats))
    rows = {it["name"].split(",")[0]: it for it in doc["items"]}
    check("every variant row carries a variant block",
          all("variant" in rows[n] for n in ("Forbidden Flesh", "Watcher's Eye", "Lethal Pride",
                                              "Voices", "Replica Dragonfang's Flight")),
          str([n for n in rows if "variant" not in rows[n]]))
    # the picker marks defining mods (Forbidden option row, Voices exact-count row)
    rr = doc["rares"]
    ff_idx = str(rows["Forbidden Flesh"]["index"])
    ff_def = [a for a in rr[ff_idx]["affixes"] if a.get("defining")]
    check("picker: Forbidden defining affix flagged required+prefer+option",
          len(ff_def) == 1 and ff_def[0]["priority"] == "required" and ff_def[0]["prefer"] is True
          and ff_def[0].get("option") == 4194, str(ff_def))
    vo_idx = str(rows["Voices"]["index"])
    vo_def = [a for a in rr[vo_idx]["affixes"] if a.get("defining")]
    check("picker: Voices defining affix flagged exact (min==max prefill)",
          len(vo_def) == 1 and vo_def[0].get("exact") is True and vo_def[0]["default_min"] == 7,
          str(vo_def))
    lp_idx = str(rows["Lethal Pride"]["index"])
    lp_def = [a for a in rr[lp_idx]["affixes"] if a.get("defining")]
    check("picker: Lethal Pride seed row is searchable + exact (was unmatched full-line)",
          len(lp_def) == 1 and lp_def[0]["searchable"] is True and lp_def[0].get("exact") is True
          and lp_def[0]["reason"] == "", str(lp_def))
    # D-0022: the Replica Dragonfang gem-level mod is the sole defining picker row -- required,
    # searchable via its specific indexable_skill id, prefilled min=3; the copy's fixed
    # res/reservation/attr mods are NOT flagged defining.
    dd_idx = str(rows["Replica Dragonfang's Flight"]["index"])
    dd_def = [a for a in rr[dd_idx]["affixes"] if a.get("defining")]
    check("picker: Replica Dragonfang gem row is the sole defining row (required+searchable, min=3)",
          len(dd_def) == 1 and dd_def[0]["priority"] == "required" and dd_def[0]["prefer"] is True
          and dd_def[0]["searchable"] is True and dd_def[0]["default_min"] == 3
          and dd_def[0]["stat_id"] == "explicit.indexable_skill_67", str(dd_def))

    # ---- D-0019 MAJOR-1 regression: the non-aura roll/mod-variant families. EVERY family
    # carries from.match=="family-all", so the old blanket `if family_all` forced these into
    # the aura branch -- dropping their defining filters and stamping label="aura variant".
    # Each must now emit its INTENDED defining filter + a correct label. (Closes MINOR-1: the
    # missing presence/reservation/non-"while affected by" coverage that let MAJOR-1 ship green.)
    from _lib import variantreg

    def variant_of(name, base, mods):
        return variantreg.build_variant(mk(name, base, mods), variantreg.lookup(name, base), mapper)

    # Megalomaniac (emit=presence): AND the three '1 Added Passive Skill is <Notable>' flags --
    # NOT the base 'Adds N Passive Skills' grant, and never 'aura variant'.
    mega = variant_of("Megalomaniac", "Medium Cluster Jewel", [
        "Adds 5 Passive Skills",
        "1 Added Passive Skill is Touch of Cruelty",
        "1 Added Passive Skill is Prismatic Heart",
        "1 Added Passive Skill is Fuel the Fight"])
    check("Megalomaniac: exactly the 3 notable presence filters (min=1), base grant excluded",
          {f["id"] for f in mega["filters"]} == {"explicit.stat_2780712583",
              "explicit.stat_2342448236", "explicit.stat_3599340381"}
          and all(f.get("value") == {"min": 1} for f in mega["filters"]), str(mega["filters"]))
    check("Megalomaniac: label names the notables, NOT 'aura variant'",
          mega["label"] != "aura variant" and "Touch of Cruelty" in mega["label"], mega["label"])

    # Aul's Uprising (reservation family; the registry rep id is a DIFFERENT reservation mod, so
    # def_ids misses and it falls to own-rolls) -- which STILL captures the '<Aura> has no
    # Reservation' mod as a filter, and must not be mislabelled 'aura variant'.
    auls = variant_of("Aul's Uprising", "Onyx Amulet", ["Grace has no Reservation",
                                                        "+40 to maximum Life"])
    check("Aul's Uprising: '<Aura> has no Reservation' captured + not 'aura variant'",
          any(f["id"] == "explicit.stat_2930404958" for f in auls["filters"])
          and auls["label"] != "aura variant", f"{auls['label']!r} {auls['filters']}")

    # The Light of Meaning (mod-variant): REAL copies carry the "Passive Skills in Radius also
    # grant <X>" family (15 members, serialised as from.family_ids), NOT the fictional "increased
    # Effect ... in Radius" the old test fed -- that string resolves to the wrong legacy id
    # stat_607548408 (which is Might of the Meek's mod; 0 of 913 live Light-of-Meaning listings
    # carry it -- docs/verify/variants-r1.md sec 3). The copy's SPECIFIC family member must be
    # emitted by its OWN id: the real defining filter and LoM's only price handle (it has no ninja
    # variant lines). These real strings FAIL if the registry regresses to stat_607548408 (the old
    # fixture passed on both the wrong AND the right registry -- coverage of a fiction).
    lom = variant_of("The Light of Meaning", "Prismatic Jewel", [
        "Passive Skills in Radius also grant 7% increased Evasion Rating"])
    check("The Light of Meaning: real 'grant <X>' member emitted by its own id (min-roll), not legacy",
          lom["filters"] == [{"id": "explicit.stat_3761482453", "value": {"min": 7}}]
          and all(f["id"] != "explicit.stat_607548408" for f in lom["filters"])
          and lom["label"] not in ("aura variant", ""), str(lom["filters"]) + " / " + lom["label"])
    lom2 = variant_of("The Light of Meaning", "Prismatic Jewel", [
        "Passive Skills in Radius also grant +6 to maximum Mana"])
    check("The Light of Meaning: a different family member (mana) emits ITS own id, never the legacy",
          lom2["filters"] == [{"id": "explicit.stat_3382199855", "value": {"min": 6}}],
          str(lom2["filters"]))

    # Vessel of Vinktar (mod-variant, rep is 1-of-18; the copy names a different lightning mod):
    # no defining filter is derivable from the rep, so ninja map-variant prices it -- the only
    # requirement is that it is no longer mislabelled 'aura variant'.
    vov = variant_of("Vessel of Vinktar", "Topaz Flask", [
        "Adds 30 to 90 Lightning Damage to Spells", "25% increased Lightning Damage"])
    check("Vessel of Vinktar: no bogus 'aura variant' label (ninja map-variant prices it)",
          vov["label"] != "aura variant", repr(vov["label"]))

    # end-to-end: the presence label survives to the item-row variant block via
    # price_unique_ninja's floor path (the ninja-variant label overwrite must NOT fire on floor).
    econ._uniques["megalomaniac"] = [{"name": "Megalomaniac", "baseType": "Medium Cluster Jewel",
                                     "variant": None, "chaosValue": 25.5, "listingCount": 9641,
                                     "count": 9641}]
    rm = P.price_unique_ninja(mk("Megalomaniac", "Medium Cluster Jewel", [
        "1 Added Passive Skill is Touch of Cruelty",
        "1 Added Passive Skill is Prismatic Heart",
        "1 Added Passive Skill is Fuel the Fight"]))
    check("Megalomaniac: floor-capped LOW + presence label reaches variant_info (not overwritten)",
          rm.method == "unique-ninja-floor" and rm.confidence == "low"
          and "Touch of Cruelty" in rm.extra["variant_info"]["label"]
          and rm.extra["variant_info"]["label"] != "aura variant",
          f"{rm.method}/{rm.confidence}/{rm.extra.get('variant_info', {}).get('label')!r}")


def phase_b():
    if os.environ.get("BPC_SKIP_LIVE") == "1":
        print("\n== PHASE B: SKIPPED (BPC_SKIP_LIVE=1) =="); return
    print("\n== PHASE B: live (one poe.ninja character, via the real handler on :8951) ==")
    from _lib import _http
    poeninja.get_json = _http.get_json
    engine._mapper_singleton = None; engine._types_singleton = None
    fresh_cache()
    import build as buildmod
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", 8951), buildmod.handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        default_url = ("https://poe.ninja/poe1/builds/allflame/character/"
                       "example-0416/TestCharacter")
        char_url = os.environ.get("BPC_LIVE_CHAR_URL", default_url)
        import urllib.parse
        q = urllib.parse.urlencode({"url": char_url})
        t0 = time.time()
        with urllib.request.urlopen(f"http://127.0.0.1:8951/api/build?{q}", timeout=90) as r:
            hdrs = dict(r.headers); doc = json.loads(r.read().decode("utf-8"))
        dt = time.time() - t0
        print(f"  live /api/build -> {dt:.1f}s; CORS={hdrs.get('Access-Control-Allow-Origin')!r}; "
              f"Cache-Control={hdrs.get('Cache-Control')!r}")
        check("live CORS allow-origin *", hdrs.get("Access-Control-Allow-Origin") == "*")
        check("live Cache-Control has s-maxage", "s-maxage" in (hdrs.get("Cache-Control") or ""))
        if not doc.get("ok"):
            check("live request ok", False, f"{doc.get('error_type')}: {doc.get('error')}")
            print("  (live character may have rotated out; set BPC_LIVE_CHAR_URL to a current one)")
        else:
            validate_contract(doc, source="poe.ninja")
            print(f"  live: {len(doc['items'])} items; priced={doc['totals']['priced_items']} "
                  f"unpriced={doc['totals']['unpriced_items']}; "
                  f"totals.chaos.median={doc['totals']['chaos']['median']}; div/chaos={doc['meta']['divine_to_chaos']}")
            check("live: >=1 unique priced by name",
                  any(it["category"] == "unique" and it["price"].get("source") == "poe.ninja" for it in doc["items"]))
            check("live: gems priced from poe.ninja",
                  any(it["category"] == "gem" and it["price"].get("total_chaos") is not None for it in doc["items"]))
            check("live: divine_to_chaos > 0", (doc["meta"]["divine_to_chaos"] or 0) > 0)
            blob = json.dumps(doc)
            check("live: no /api/trade in document", "/api/trade" not in blob)
            globals()["_LIVE_DOC"] = doc
    finally:
        srv.shutdown()
    import health as healthmod
    hp = healthmod._payload()
    check("health ok", hp.get("ok") is True, str(hp))
    check("health says never calls pathofexile", hp.get("calls_pathofexile_com") is False)


def main():
    phase_a()
    phase_variant()
    phase_b()
    out = os.environ.get("BPC_TEST_OUT", tempfile.gettempdir())
    for name, key in (("sample_response_offline.json", "_SAMPLE_DOC"),
                      ("sample_response_live.json", "_LIVE_DOC")):
        d = globals().get(key)
        if d:
            with open(os.path.join(out, name), "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2, ensure_ascii=False)
            print(f"wrote {os.path.join(out, name)}")
    print("\n==== SUMMARY ====")
    if FAILS:
        print(f"{len(FAILS)} FAILURES:")
        for f in FAILS:
            print("  -", f)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
