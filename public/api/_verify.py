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
    rares = doc.get("rares") or {}
    for k, v in rares.items():
        for f in ("status", "name", "kind", "scope", "scope_q", "affixes", "pseudo"):
            check(f"rares[{k}].{f} present", f in v)
        check(f"rares[{k}].kind valid", v.get("kind") in ("rare", "unique", "magic"),
              str(v.get("kind")))
        for a in v.get("affixes") or []:
            # picker-ready affix payload: every entry self-describes for the client picker
            for f in ("kind", "text", "stat_id", "value", "default_min", "default_max",
                      "searchable", "negated", "group"):
                check(f"rares[{k}] affix.{f} present", f in a, f"{a.get('text')!r} missing {f}")
            # a searchable affix prefills exactly one of min/max; unsearchable prefills neither
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
                want_stat = sum(1 for a in ent["affixes"] if a["kind"] == "stat" and a["searchable"])
                want_arm = sum(1 for a in ent["affixes"] if a["kind"] == "equip" and a.get("value"))
                check(f"[ascii] rare[{k}] default query requires all searchable affixes",
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
