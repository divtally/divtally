/* bpc core.js — PUBLIC edition (static site engine for B-001 / D-0008).
 *
 * Same event/method surface the stash VIEW already consumes, but rewired for the
 * public architecture (docs/public-contract.md, docs/notes-public-worker.md,
 * docs/notes-public-ext.md):
 *
 *   • The build is ONE SHOT — GET/POST {API_BASE}/api/build returns the whole
 *     document (meta + items[] each with an embedded price + rares{}). No job,
 *     no polling. (Local app used /api/price + /api/job.)
 *   • Item numbers come ONLY from poe.ninja (server-side, in the document),
 *     the community cache ({WORKER_BASE}/cache, seeded by real machines), a human
 *     pasting a trade whisper, or the browser extension pricing on the user's IP.
 *   • Rares / magic / uniques poe.ninja can't name arrive UNPRICED with a ready
 *     trade_url + trade_query. The site prices them client-side:
 *        1. cache read-through (GET /cache)         — free, shared, opt-out-able
 *        2. whisper-paste / typed price (manual)     — always available
 *        3. the extension bridge (postMessage)       — hands-free, POSTs to cache
 *   • NOTHING here ever calls pathofexile.com. (Trade links open in the user's
 *     own browser tab; the extension runs on the user's own IP.)
 *
 *   bpc.init(opts)                    -> load prefs, restore recent + manual prices, ping the bridge
 *   bpc.startUrl(text)               -> price a poe.ninja link / PoB code / pobb.in link
 *   bpc.startCache(key)              -> reload a recent build (from localStorage)
 *   bpc.setControl(name,val)         -> 'status'|'league'|'tier'|'refresh'
 *   bpc.applyWhisper(key,text)       -> parse a pasted whisper / "35c" / "2 div" and fold it in
 *   bpc.parseWhisper(text,rate)      -> pure parser (unit-tested in node), returns {amount,currency,chaos}
 *   bpc.manualRows()                 -> the unpriced rares/magic that need a client-side price
 *   bpc.autoscan() / priceViaExtension(key)   -> drive the extension bridge
 *   bpc.setCacheOptOut(on) / cacheOptOut()    -> the community-cache opt-out (persisted)
 *   bpc.cacheKey(league,item)/itemIdentity(item)  -> the shared cache-key recipe (unit-tested)
 *   bpc.loadMock(snapshot)           -> render a full build with NO backend (?mock / demo)
 *
 * Events (bpc.on(name, cb); '*' for all):
 *   'phase'(idle|loading|done|error) · 'state' · 'meta' · 'items' · 'priced' ·
 *   'totals' · 'progress' · 'recent' · 'control' · 'bridge'({active,version}) ·
 *   'manual'(rows) · 'done' · 'error'
 */
(function () {
  "use strict";

  // ---- config (window.BPC_CONFIG from config.js, with ?query overrides for testing) ----
  var CFG = (typeof window !== "undefined" && window.BPC_CONFIG) || {};
  function qp(name) {
    try { return new URLSearchParams(window.location.search).get(name); } catch (e) { return null; }
  }
  function trimSlash(s) { return String(s || "").replace(/\/+$/, ""); }
  // R6-S1: the ?api/?stub/?worker overrides repoint the build fetch (and the community cache) at an
  // arbitrary origin, letting a crafted link supply the WHOLE build document from an attacker. Honour
  // them ONLY in a dev context (localhost / 127.0.0.1 / *.local / file: — or an explicit
  // CFG.ALLOW_QUERY_OVERRIDES flag); in production they are ignored, so a shared link can never
  // repoint the data origin. Config values below are always trusted (they ship with the site).
  function devContext() {
    try {
      var loc = (typeof window !== "undefined" && window.location) || {};
      var h = loc.hostname || "", proto = loc.protocol || "";
      return proto === "file:" || h === "localhost" || h === "127.0.0.1" || h === "::1" || h === "[::1]" ||
             /(^|\.)localhost$/i.test(h) || /(^|\.)local$/i.test(h);
    } catch (e) { return false; }
  }
  var ALLOW_OVERRIDES = !!(CFG && CFG.ALLOW_QUERY_OVERRIDES) || devContext();
  function qpOverride(name) { return ALLOW_OVERRIDES ? qp(name) : null; }
  var API_BASE = trimSlash(qpOverride("api") || CFG.API_BASE || "");
  var WORKER_BASE = trimSlash(qpOverride("worker") || (CFG.WORKER_BASE === undefined ? "" : CFG.WORKER_BASE));
  var STUB = qpOverride("stub");          // ?stub[=path] -> local build document instead of the API (dev only)
  var MAX_KEYS = CFG.CACHE_MAX_KEYS || 60;
  // Bound the build fetch so an unresponsive API (accepts the TCP connection but never replies)
  // can't strand the page in 'loading' forever (R4-4). Default 45s: generous enough never to trip
  // a legitimately slow build, short enough to recover a truly hung connection. Overridable via
  // config or ?buildTimeout for tests.
  var BUILD_TIMEOUT_MS = Number(qp("buildTimeout")) || CFG.BUILD_TIMEOUT_MS || 45000;

  var STATUS_LABEL = {
    available: "Instant Buyout and In Person", securable: "Instant Buyout",
    onlineleague: "In Person (Online in League)", online: "In Person (Online)", any: "Any"
  };
  var STATUS_ORDER = ["available", "securable", "onlineleague", "online", "any"];
  var TIER_LABEL = { min: "min (budget)", median: "median (typical)", high: "high (~90th pct)" };
  var TIER_ORDER = ["min", "median", "high"];
  var GROUPS = [["equipment", "Equipment"], ["flask", "Flasks"], ["jewel", "Jewels"], ["gem", "Gems"]];

  function lsget(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsset(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function lsdel(k) { try { localStorage.removeItem(k); } catch (e) {} }

  // ---- event emitter ----
  var L = {};
  function on(ev, cb) { (L[ev] = L[ev] || []).push(cb); return function () { off(ev, cb); }; }
  function off(ev, cb) { var a = L[ev]; if (a) { var i = a.indexOf(cb); if (i >= 0) a.splice(i, 1); } }
  function emit(ev, data) {
    (L[ev] || []).slice().forEach(function (cb) { try { cb(data); } catch (e) { console.error("[bpc]", ev, e); } });
    (L["*"] || []).slice().forEach(function (cb) { try { cb(ev, data); } catch (e) {} });
  }

  // ---- state ----
  var state = {
    phase: "idle", source: null,
    meta: null, items: [], priced: {}, rares: {}, warnings: [],
    progress: "", error: null,
    status: "available", league: "", refresh: false,
    tier: "min",
    enabled: {}, purchased: {}, leagues: [], recent: [],
    bridge: { active: false, version: null },
    _sig: {}, _mock: false,
    gen: 0                          // R6-F1: build "generation" — bumped by reset(); async continuations gate on it
  };
  // R6-F1 (race lens): every reset() stamps a new generation. Any async continuation captured under an
  // OLDER build (its fetch .then/.catch/timeout, its cache read-through, its in-flight extension scan)
  // checks `gen !== state.gen` and drops itself, so a superseded build/scan can never (a) clobber the
  // render with the wrong build, (b) fold its prices onto the current build's same-index items, or
  // (c) POST those cross-build prices into the SHARED community cache. See reset()/start().
  var genSeq = 0;                   // monotonic generation counter
  var curBuildAbort = null;         // the in-flight build fetch's AbortController (aborted when a newer build starts)

  // ---- prefs ----
  function loadPrefs() {
    var s = lsget("bpc_status_v2"); if (s && STATUS_LABEL[s]) state.status = s;
    var l = lsget("bpc_league"); if (l !== null) state.league = l;
    else if (CFG.DEFAULT_LEAGUE) state.league = CFG.DEFAULT_LEAGUE;
    var ti = lsget("bpc_tier"); if (ti && TIER_LABEL[ti]) state.tier = ti;
  }
  function setControl(name, value, opts) {
    opts = opts || {};
    if (name === "status") { state.status = value; lsset("bpc_status_v2", value); }
    else if (name === "league") { state.league = value; lsset("bpc_league", value); }
    else if (name === "refresh") { state.refresh = !!value; }
    else if (name === "tier") { state.tier = TIER_LABEL[value] ? value : "min"; lsset("bpc_tier", state.tier); }
    emit("control", { name: name, value: value });
    // status/league change the query -> re-fetch. tier/refresh are display/one-shot -> no re-fetch.
    if (opts.rerun !== false && (name === "status" || name === "league")) rerun();
  }
  function tierEx(p) { return (p && p.chaos) ? p.chaos[state.tier] : null; }

  // ---- currency formatting (verbatim from the local engine) ----
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function nfmt(n, d) { return Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function divRate() { return (state.meta && state.meta.divine_to_chaos) ? state.meta.divine_to_chaos : 0; }
  function curImg(kind) {
    var m = state.meta || {}, src = kind === "div" ? m.divine_img : m.chaos_img;
    return src ? '<img class="bpc-cur" src="' + esc(src) + '" alt="' + kind + '" title="' +
      (kind === "div" ? "Divine Orb" : "Chaos Orb") + '">' : esc(kind);
  }
  function price(ex) {
    var div = divRate();
    if (ex == null) return { empty: true };
    var exStr = ex >= 10 ? nfmt(Math.round(ex), 0) : nfmt(ex, 1);
    if (div && ex >= div * 0.5) {
      var v = ex / div;
      return { empty: false, ex: ex, exStr: exStr, div: v, divStr: v < 100 ? nfmt(v, 1) : nfmt(Math.round(v), 0) };
    }
    return { empty: false, ex: ex, exStr: exStr, div: null, divStr: null };
  }
  function priceHTML(ex) {
    var p = price(ex);
    if (p.empty) return '<span class="bpc-dash">—</span>';
    var exPart = p.exStr + " " + curImg("chaos");
    if (p.div != null) return p.divStr + " " + curImg("div") + ' <span class="bpc-exsub">(' + exPart + ")</span>";
    return exPart;
  }

  // ---- totals + include/exclude (verbatim) ----
  function isPriced(it) { var p = state.priced[String(it.index)]; return !!(p && p.chaos && p.chaos.median != null); }
  function includeSwap() { return lsget("bpc_include_swap") === "1"; }
  function itemSwap(k) { var it = state.items.find(function (x) { return String(x.index) === String(k); }); return !!(it && it.swap); }
  // D-0021: non-unique (magic) flasks are excluded by default (cheap; not worth scan budget),
  // re-includable via the equipment-header "magic flasks" button. Mirrors the swap pattern.
  function includeMagicFlasks() { return lsget("bpc_include_magicflask") === "1"; }
  function isMagicFlask(it) { return !!(it && it.group === "flask" && it.category === "magic"); }
  function isMagicFlaskK(k) { return isMagicFlask(state.items.find(function (x) { return String(x.index) === String(k); })); }
  // default include-state for a row the first time its price lands (granted, weapon-swap, and
  // magic flasks all start excluded; their header buttons re-include).
  function defaultOn(k) { return !itemGranted(k) && !(itemSwap(k) && !includeSwap()) && !(isMagicFlaskK(k) && !includeMagicFlasks()); }
  function setIncludeSwap(on) {
    lsset("bpc_include_swap", on ? "1" : "0");
    state.items.forEach(function (it) {
      if (!it.swap) return;
      var k = String(it.index);
      if (state.priced[k] && state.priced[k].chaos && state.priced[k].chaos.median != null)
        state.enabled[k] = on ? !itemGranted(k) : false;
    });
    emit("manual", manualRows()); emit("totals", totals()); emit("swap", { on: !!on });
  }
  function setIncludeMagicFlasks(on) {
    lsset("bpc_include_magicflask", on ? "1" : "0");
    state.items.forEach(function (it) {
      if (!isMagicFlask(it)) return;
      var k = String(it.index);
      if (state.priced[k] && state.priced[k].chaos && state.priced[k].chaos.median != null)
        state.enabled[k] = on ? !itemGranted(k) : false;
    });
    emit("manual", manualRows()); emit("totals", totals()); emit("magicflasks", { on: !!on });
  }
  // D-0021: is this jewel currently sitting on a poe.ninja floor (last-chance price)?
  function isJewelFloor(k) { var it = state.items.find(function (x) { return String(x.index) === String(k); }); var p = state.priced[String(k)];
    return !!(it && it.group === "jewel" && p && p.chaos && p.chaos.median != null && /^unique-ninja/.test(p.method || "")); }
  function itemGranted(k) { var it = state.items.find(function (x) { return String(x.index) === String(k); }); return !!(it && it.granted); }
  function totals() {
    var mn = 0, md = 0, hi = 0, sMn = 0, sMd = 0, sHi = 0, inc = 0, tot = 0, bought = 0;
    state.items.forEach(function (it) {
      var k = String(it.index), p = state.priced[k];
      if (!p || !p.chaos || p.chaos.median == null) return;
      tot++;
      if (!state.enabled[k]) return;
      inc++; var c = it.count || 1;
      if (state.purchased[k]) {
        bought++;
        if (p.chaos.min != null) sMn += p.chaos.min * c;
        sMd += p.chaos.median * c;
        if (p.chaos.high != null) sHi += p.chaos.high * c;
      } else {
        if (p.chaos.min != null) mn += p.chaos.min * c;
        md += p.chaos.median * c;
        if (p.chaos.high != null) hi += p.chaos.high * c;
      }
    });
    return { min: mn, median: md, high: hi, included: inc, priced: tot,
             spentMin: sMn, spentMedian: sMd, spentHigh: sHi,
             purchased: bought, remaining: inc - bought };
  }
  function setEnabled(key, on) { state.enabled[String(key)] = !!on; emit("enabled", { key: String(key), on: !!on }); emit("totals", totals()); }
  function purchaseLSKey() {
    var ck = (state.meta && (state.meta.cache_key || state.meta.source_url)) || "";
    if (!ck) return "";
    var m = ck.match(/^poeninja:char:[^:]+:(.+)$/);
    return "bpc_purchased:" + (m ? m[1] : ck);
  }
  function loadPurchased() {
    state.purchased = {};
    var lk = purchaseLSKey(); if (!lk) return;
    try { (JSON.parse(lsget(lk) || "[]") || []).forEach(function (k) { state.purchased[String(k)] = true; }); } catch (e) {}
  }
  function savePurchased() {
    var lk = purchaseLSKey(); if (!lk) return;
    var keys = Object.keys(state.purchased).filter(function (k) { return state.purchased[k]; });
    lsset(lk, JSON.stringify(keys));
  }
  function isPurchased(key) { return !!state.purchased[String(key)]; }
  function setPurchased(key, on) {
    var k = String(key);
    if (on) state.purchased[k] = true; else delete state.purchased[k];
    savePurchased();
    emit("purchased", { key: k, on: !!on }); emit("totals", totals());
  }
  function setGroupEnabled(group, on) {
    state.items.filter(function (it) { return it.group === group; }).forEach(function (it) {
      var k = String(it.index);
      if (state.priced[k] && state.priced[k].chaos && state.priced[k].chaos.median != null) state.enabled[k] = on ? !it.granted : false;
    });
    emit("enabled", { group: group, on: !!on }); emit("totals", totals());
  }
  // D-0021: is a group currently ON (any priced row in it enabled)? drives the gold/black header buttons.
  function groupEnabled(group) {
    return state.items.some(function (it) {
      if (it.group !== group) return false;
      var k = String(it.index);
      return state.enabled[k] && state.priced[k] && state.priced[k].chaos && state.priced[k].chaos.median != null;
    });
  }
  // does a group have any priced row at all (so its button is worth showing)?
  function groupHasPriced(group) {
    return state.items.some(function (it) {
      if (it.group !== group) return false;
      var k = String(it.index);
      return state.priced[k] && state.priced[k].chaos && state.priced[k].chaos.median != null;
    });
  }
  function itemsByGroup() {
    var out = [];
    GROUPS.forEach(function (g) {
      var rows = state.items.filter(function (it) { return it.group === g[0]; });
      if (rows.length) out.push({ group: g[0], title: g[1], items: rows });
    });
    return out;
  }

  // ---- gem host grouping + per-gem breakdown (verbatim from the local engine) ----
  function gemHost(itOrKey) {
    var it = (itOrKey && typeof itOrKey === "object") ? itOrKey
           : state.items.find(function (x) { return String(x.index) === String(itOrKey); });
    var p = it ? state.priced[String(it.index)] : null;
    function f(name) {
      var v = p ? p[name] : undefined;
      if (v !== undefined && v !== null && v !== "") return v;
      v = it ? it[name] : undefined;
      if (v !== undefined && v !== null && v !== "") return v;
      return undefined;
    }
    return { inventory_id: f("host_inventory_id") || "", slot: f("host_slot") || "",
             name: f("host_name") || "", base: f("host_base") || "", unique: !!f("host_unique") };
  }
  function gemGroupHeader(h) {
    var slot = h.slot || "", name = h.name || "";
    if (slot && name) return slot + " — " + name;
    return slot || name || "Gems";
  }
  function gemGroups() {
    var order = [], byKey = {};
    state.items.forEach(function (it) {
      if (it.group !== "gem") return;
      var h = gemHost(it), key = h.inventory_id || h.slot || "";
      var g = byKey[key];
      if (!g) { g = byKey[key] = { key: key, slot: h.slot, name: h.name, base: h.base,
                                   unique: h.unique, header: "", items: [] }; order.push(g); }
      else {
        if (!g.slot && h.slot) g.slot = h.slot;
        if (!g.name && h.name) g.name = h.name;
        if (!g.base && h.base) g.base = h.base;
        if (h.unique) g.unique = true;
      }
      g.items.push(it);
    });
    order.forEach(function (g) { g.header = gemGroupHeader(g); });
    return order;
  }
  function gemBreakdown(key) {
    var k = String(key), p = state.priced[k];
    var it = state.items.find(function (x) { return String(x.index) === k; });
    var sups = (it && it.supports) || [];
    var glist = (p && p.gems && p.gems.length) ? p.gems : null, rows;
    if (glist) {
      rows = glist.map(function (g, i) {
        var sk = i === 0 ? it : sups[i - 1];
        return { name: g.name, support: !!g.support, granted: !!g.granted, active: i === 0,
                 level: g.level, quality: g.quality, corrupted: !!g.corrupted,
                 chaos: (g.chaos == null ? null : g.chaos), variant: g.variant || "",
                 note: g.note || "", trade_url: g.trade_url || (p && p.trade_url) || "",
                 icon: (sk && sk.icon) || "" };
      });
    } else if (it) {
      rows = [{ name: it.name, support: false, granted: !!it.granted, active: true,
                level: it.level, quality: it.quality, corrupted: !!it.corrupted, chaos: null,
                variant: "", note: "", trade_url: (p && p.trade_url) || "", icon: it.icon || "" }];
      sups.forEach(function (s) {
        rows.push({ name: s.name, support: (s.support === undefined ? true : !!s.support),
                    granted: !!s.granted, active: false, level: s.level, quality: s.quality,
                    corrupted: !!s.corrupted, chaos: null, variant: "", note: "",
                    trade_url: (p && p.trade_url) || "", icon: s.icon || "" });
      });
    } else { rows = []; }
    var total = p ? (p.total_chaos != null ? p.total_chaos : (p.chaos ? p.chaos.median : null)) : null;
    return { total: total, granted: !!(p && p.granted), gems: rows };
  }

  function sigOf(p) {
    var c = p.chaos || {};
    return p.method + "|" + c.min + "|" + c.median + "|" + c.high + "|" + p.note + "|" + p.trade_url + "|" + p.source;
  }

  // =====================================================================
  //  THE SHARED CACHE-KEY RECIPE  (docs/notes-public-worker.md §1)
  //  Byte-identical to tools/seed_cache.py and the Worker's expectations.
  // =====================================================================
  var US = "\x1f", RS = "\x1e", GS = "\x1d";
  function canon(s) { return (s || "").normalize("NFC").trim(); }
  function leagueKeyspace(l) { return canon(l).toLowerCase().split(/\s+/).join(" "); }
  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
  function itemIdentity(it) {
    var cat = (it.category || "").toLowerCase();
    var name = canon(it.name || "");
    if (cat === "gem") {
      var sup = (it.supports || []).map(function (s) {
        return canon(s.name || "") + "~L" + parseInt(s.level || 0, 10) + "~Q" + parseInt(s.quality || 0, 10) + "~" + (s.corrupted ? "c" : "n");
      }).sort(cmp);
      return ["gem", name, "L" + parseInt(it.level || 0, 10), "Q" + parseInt(it.quality || 0, 10),
              it.corrupted ? "c" : "n", sup.join("|")].join(US);
    }
    var mods = it.mods || {};
    var impl = (mods.implicit || []).map(canon).sort(cmp);
    var expl = (mods.explicit || []).map(canon).sort(cmp);
    return [cat, name, impl.join(RS), expl.join(RS)].join(US);
  }
  function _hasSubtle() { try { return !!(crypto && crypto.subtle && crypto.subtle.digest); } catch (e) { return false; } }
  function cacheKey(league, it) {
    var material = leagueKeyspace(league) + GS + itemIdentity(it);
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(material)).then(function (buf) {
      var hex = [].slice.call(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
      return "v1_" + hex.slice(0, 32);
    });
  }

  // ---- reset / phase helpers ----
  function reset() {
    // R6-F1: bump the generation FIRST so every still-in-flight continuation from the PRIOR build
    // (build fetch, cache read-through, extension scan foldBatch) sees gen !== state.gen and drops
    // itself instead of folding onto — or poisoning the shared cache of — the build we're loading now.
    state.gen = ++genSeq;
    // Abort the previous build's fetch so it doesn't waste bandwidth or resolve late (its .then/.catch
    // are gen-guarded regardless, so aborting is a clean optimisation, not the correctness mechanism).
    if (curBuildAbort) { try { curBuildAbort.abort(); } catch (e) {} curBuildAbort = null; }
    state.meta = null; state.items = []; state.priced = {}; state.rares = {}; state.warnings = [];
    state.progress = ""; state.error = null; state.enabled = {}; state.purchased = {}; state._sig = {};
    scanReset();     // drop any stale scan session so a new build starts with a clean status map
  }
  function fail(msg) { state.phase = "error"; state.error = msg; emit("error", msg); emit("phase", "error"); emit("state", state); }

  // =====================================================================
  //  BUILD FETCH  — the one-shot public document (never touches GGG)
  // =====================================================================
  function start(source, opts) {
    opts = opts || {};
    if (source && source.url) state.source = source;
    state._mock = false; reset();
    var gen = state.gen;              // R6-F1: this build's generation; every async continuation below gates on it
    state.phase = "loading"; emit("phase", "loading"); emit("state", state);
    var input = (source && source.url) || "";

    var url, init = null;
    if (STUB != null) {
      // dev: serve a local build document as the API (no network to any service)
      url = (STUB && STUB !== "1") ? STUB : "stub-build.json";
    } else if (!API_BASE || /REPLACE_ME/.test(API_BASE)) {
      return fail("This site isn't configured yet — set API_BASE in config.js. (Try ?mock for a demo.)");
    } else {
      // Short poe.ninja/pobb.in links -> GET (CDN-cacheable). Long PoB codes -> POST (avoid URL limits).
      var isUrl = /^https?:\/\//i.test(input);
      var useGet = isUrl && input.length < 1800;
      if (useGet) {
        var qs = "url=" + encodeURIComponent(input);
        if (state.league) qs += "&league=" + encodeURIComponent(state.league);
        if (state.status) qs += "&status=" + encodeURIComponent(state.status);
        if (opts.refresh || state.refresh) qs += "&_=" + Date.now();
        url = API_BASE + "/api/build?" + qs;
      } else {
        url = API_BASE + "/api/build";
        var body = { input: input };
        if (state.league) body.league = state.league;
        if (state.status) body.status = state.status;
        init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
      }
    }
    if (state.refresh) { state.refresh = false; emit("control", { name: "refresh", value: false }); }
    emit("progress", "fetching the build from poe.ninja…");

    // The build fetch must not hang forever: an API that accepts the TCP connection but never
    // sends an HTTP response (firewall DROP, half-open/overloaded server, LB gateway timeout)
    // would otherwise leave the page stuck in 'loading' with the spinner and no recovery. Bound it
    // with an AbortController + timer (mirrors the bridge/chunk timeout discipline, D-0012); on
    // timeout -> fail() with a "took too long" message. `settled` de-dupes so the timeout and a
    // late reply/abort can never both report. (R4-4)
    var ac = (typeof AbortController !== "undefined") ? new AbortController() : null;
    curBuildAbort = ac;                       // R6-F1: expose so a newer build's reset() can abort this fetch
    var settled = false;
    var timer = setTimeout(function () {
      if (gen !== state.gen) return;          // R6-F1: a newer build superseded us -> never report against it
      if (settled) return;
      settled = true;
      if (ac) { try { ac.abort(); } catch (e) {} }
      fail("The pricing service took too long to respond. Check your connection, or try ?mock for a demo.");
    }, BUILD_TIMEOUT_MS);
    if (ac) { init = init || {}; init.signal = ac.signal; }

    fetch(url, init || undefined)
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (gen !== state.gen) return;        // R6-F1: a newer build started -> drop this stale reply (never clobber it)
        if (settled) return;                  // already timed out -> ignore the late reply
        settled = true; clearTimeout(timer);
        if (curBuildAbort === ac) curBuildAbort = null;
        var j = res.j || {};
        if (j.ok === false || (!res.ok && j.ok !== true)) return fail((j && j.error) || "The build could not be loaded.");
        loadBuild(j);
      })
      .catch(function () {
        if (gen !== state.gen) return;        // R6-F1: our own abort() (a newer build started) or a stale error -> drop
        if (settled) return;                  // the timeout (or its abort()) already reported the error
        settled = true; clearTimeout(timer);
        if (curBuildAbort === ac) curBuildAbort = null;
        fail("Could not reach the pricing service. Check your connection, or try ?mock for a demo.");
      });
  }
  function startUrl(url) { if (url && url.trim()) start({ url: url.trim() }); }
  function startCache(key) {
    var b = (state.recent || []).find(function (x) { return x.key === key; });
    if (b && b.url) start({ url: b.url });
  }
  function rerun() { if (!state._mock && state.source && state.source.url) start(state.source, { refresh: true }); }
  function researchAll() { rerun(); }

  // Reshape the public build document (docs/public-contract.md §2) into the state
  // shape the stash VIEW expects: state.items (skeleton) + state.priced[index] (price obj
  // with trade_url copied on), + state.rares. Then paint everything at once.
  function loadBuild(doc) {
    state.meta = normMeta(doc.meta || {});
    state.rares = doc.rares || {};
    state.warnings = doc.warnings || [];
    var items = (doc.items || []).map(normItem);
    state.items = items;
    state.priced = {};
    state._sig = {};
    state.enabled = {};
    items.forEach(function (it) {
      var k = String(it.index);
      var p = normPrice(it);
      state.priced[k] = p;
      state._sig[k] = sigOf(p);
      // auto-include only items that carry a real server-side number; unpriced rares stay OUT
      // of the total until a human/cache/extension prices them.
      if (p.chaos && p.chaos.median != null) state.enabled[k] = defaultOn(k);
    });

    loadPurchased();
    emit("meta", state.meta);
    emit("items", state.items);
    emit("priced", { keys: Object.keys(state.priced), state: state });
    emit("totals", totals());
    state.phase = "done"; emit("state", state);

    pushRecent(state.meta);
    restoreManual();          // re-apply any prices this user pasted for this build before
    cacheReadThrough();       // fill unpriced rows from the shared community cache
    emit("manual", manualRows());
    emit("done", state);
  }

  function normMeta(m) {
    // pass through; guarantee the fields the view + recipe read
    m = Object.assign({}, m);
    if (m.status == null) m.status = state.status;
    return m;
  }
  function normItem(it) {
    it = Object.assign({}, it);
    // the view labels gems "N sup" from it.sockets; the contract carries supports[] instead.
    if (it.group === "gem" && it.sockets == null) it.sockets = (it.supports || []).length;
    return it;
  }
  // the price object the view reads (state.priced[k]); trade_url lives on the ITEM in the
  // contract, so copy it onto the price so p.trade_url keeps working everywhere.
  function normPrice(it) {
    var src = it.price || {};
    var p = Object.assign({}, src);
    if (!p.chaos) p.chaos = { min: null, median: null, high: null };
    if (!p.trade_url) p.trade_url = it.trade_url || "";
    if (p.trade_query == null && it.trade_query) p.trade_query = it.trade_query;
    if (p.method == null) p.method = "none";
    if (p.source == null) p.source = (p.chaos.median != null ? "poe.ninja" : "none");
    if (p.note == null) p.note = "";
    return p;
  }

  // ---- fold a client-side price (whisper / cache / extension) into a row ----
  function applyPrice(key, patch, opts) {
    key = String(key); opts = opts || {};
    var cur = state.priced[key] || { chaos: { min: null, median: null, high: null } };
    var merged = Object.assign({}, cur, patch);
    if (patch.chaos) merged.chaos = patch.chaos;
    if (!merged.chaos) merged.chaos = { min: null, median: null, high: null };
    state.priced[key] = merged;
    state._sig[key] = sigOf(merged);
    if (merged.chaos.median != null) {
      // an explicitly-provided price (paste/extension) is included by default; a passive cache
      // fill only auto-includes if the user hasn't already decided this row.
      if (opts.include) state.enabled[key] = defaultOn(key);
      else if (!(key in state.enabled)) state.enabled[key] = defaultOn(key);
    } else {
      // Invariant (F1/R2): a row with no median carries no number, so it must never stay counted.
      // Clears a stale enable when a price is WITHDRAWN — e.g. a variant unique whose poe.ninja
      // placeholder is dropped once its exact locked-mod search comes back empty (link-only, like
      // a 0-match rare). Every other enable site already guards on median != null; this closes the
      // one path (foldBatch nulling a placeholder) that left an enable behind a null price.
      delete state.enabled[key];
    }
    emit("priced", { keys: [key], state: state });
    emit("totals", totals());
    emit("manual", manualRows());
  }

  // =====================================================================
  //  WHISPER-PASTE  (Rung 1 manual pricing) — backlog B-001
  // =====================================================================
  // Canonical currency aliases -> the tokens the site can convert to chaos.
  var CUR_ALIAS = {
    "chaos orb": "chaos", "chaos": "chaos", "c": "chaos", "ch": "chaos",
    "divine orb": "divine", "divine": "divine", "div": "divine", "d": "divine",
    "exalted orb": "exalted", "exalted": "exalted", "exalt": "exalted", "exa": "exalted", "ex": "exalted",
    "mirror": "mirror", "mir": "mirror"
  };
  // longest-first so "chaos" wins over "c", "divine" over "div"/"d", etc.
  var CUR_RE = "(chaos orb|divine orb|exalted orb|chaos|divine|exalted|exalt|mirror|div|exa|mir|ch|ex|c|d)";
  var AMT_RE = "([0-9]+(?:\\.[0-9]+)?|[0-9]+\\s*/\\s*[0-9]+)";

  function _num(a) {
    a = String(a).replace(/\s+/g, "");
    if (a.indexOf("/") >= 0) { var pp = a.split("/"); var n = parseFloat(pp[0]) / parseFloat(pp[1]); return isFinite(n) ? n : null; }
    var v = parseFloat(a); return isFinite(v) ? v : null;
  }
  // Pure parser — unit-tested in node. Returns {amount, currency, chaos|null, raw} or null.
  // chaos is null when the currency has no known chaos rate on this build (only chaos+divine
  // convert; divine uses meta.divine_to_chaos). We never fabricate a number we can't derive.
  function parseWhisper(text, divineRate) {
    if (text == null) return null;
    var t = String(text).toLowerCase().replace(/[⁄]/g, "/");   // normalise the fraction slash
    var tail = "\\s*" + CUR_RE + "\\b";
    // capture the amount's absolute index in `t` too: the prefixes ("listed for", "~b/o",
    // "~price") carry no digits, so indexOf lands on the amount, not an earlier char.
    function findFirst(re) { var m = t.match(re); return m ? { amount: m[1], cur: m[2], at: m.index + m[0].indexOf(m[1]) } : null; }
    // priority: the machine "listed for" phrase, then a ~b/o / ~price note, then any bare "N cur".
    var hit = findFirst(new RegExp("listed for\\s*" + AMT_RE + tail))
           || findFirst(new RegExp("~\\s*(?:b/?o|price)\\s*" + AMT_RE + tail))
           || findFirst(new RegExp(AMT_RE + tail));
    if (!hit) return null;
    // Reject locale/thousands separators embedded in the number. GGG's own whispers never use
    // them; only manual entry does. When a separator splits the real number the regex captures
    // only a FRAGMENT ("1,000"->"000", "1 000"->"000", "35,5"->"5", "1.000.000"->"000.000"): the
    // matched run is flanked by a grouping separator that itself sits between digits. Rather than
    // silently fold a wrong value into the headline as a confident price, reject -> applyWhisper
    // re-prompts with "couldn't read a price". (R4-5)
    var SEP = ",.'" + "\u2019\u0020\u00A0\u2009\u202F";   // comma dot apostrophes space nbsp thin narrow (grouping seps)
    function _sep(c) { return !!c && SEP.indexOf(c) >= 0; }
    function _dig(c) { return !!c && c >= "0" && c <= "9"; }
    var _s = hit.at, _e = hit.at + String(hit.amount).length;
    if (_sep(t.charAt(_s - 1)) && _dig(t.charAt(_s - 2))) return null;   // digit<sep>[fragment]
    if (_sep(t.charAt(_e)) && _dig(t.charAt(_e + 1))) return null;       // [number]<sep>digit
    var amount = _num(hit.amount);
    if (amount == null || amount < 0) return null;
    var currency = CUR_ALIAS[hit.cur] || hit.cur;
    var chaos = null;
    if (currency === "chaos") chaos = amount;
    else if (currency === "divine") chaos = divineRate ? amount * divineRate : null;
    // exalted/mirror: no rate on the build doc -> chaos stays null (shown raw, kept out of totals)
    return { amount: amount, currency: currency, chaos: (chaos == null ? null : chaos), raw: String(text).trim() };
  }

  function manualLSKey() {
    var ck = (state.meta && (state.meta.cache_key || state.meta.source_url)) || "";
    if (!ck) return "";
    var m = ck.match(/^poeninja:char:[^:]+:(.+)$/);
    return "bpc_manual:" + (m ? m[1] : ck);
  }
  function loadManualStore() { try { return JSON.parse(lsget(manualLSKey()) || "{}") || {}; } catch (e) { return {}; } }
  function saveManualStore(o) { var lk = manualLSKey(); if (lk) lsset(lk, JSON.stringify(o)); }

  // Apply a pasted whisper / typed price to a row. Persists per build+item so it survives reloads.
  function applyWhisper(key, text) {
    key = String(key);
    var parsed = parseWhisper(text, divRate());
    if (!parsed) return { ok: false, error: "Couldn't read a price in there. Try \"35 chaos\", \"2 div\", or paste the whole buyout whisper." };
    var note = parsed.chaos != null
      ? ("you pasted: " + fmtAmt(parsed.amount) + " " + parsed.currency)
      : ("you pasted: " + fmtAmt(parsed.amount) + " " + parsed.currency + " — no chaos rate for " + parsed.currency + ", not added to the total");
    var chaos = parsed.chaos != null ? { min: parsed.chaos, median: parsed.chaos, high: parsed.chaos }
                                     : { min: null, median: null, high: null };
    applyPrice(key, {
      chaos: chaos, confidence: "medium", method: "whisper", source: "manual",
      note: note, sample_size: 1, total_found: 1, manual_currency: parsed.currency, manual_amount: parsed.amount
    }, { include: true });
    var store = loadManualStore();
    store[key] = { amount: parsed.amount, currency: parsed.currency, chaos: parsed.chaos, raw: parsed.raw };
    saveManualStore(store);
    return { ok: true, parsed: parsed };
  }
  function clearManual(key) {
    key = String(key);
    var store = loadManualStore(); delete store[key]; saveManualStore(store);
    // revert to the document's original price for this row (server number or unpriced)
    var it = state.items.find(function (x) { return String(x.index) === key; });
    if (it) { var p = normPrice(it); state.priced[key] = p; state._sig[key] = sigOf(p);
      if (!(p.chaos && p.chaos.median != null)) delete state.enabled[key]; }
    emit("priced", { keys: [key], state: state }); emit("totals", totals()); emit("manual", manualRows());
  }
  function restoreManual() {
    var store = loadManualStore();
    Object.keys(store).forEach(function (k) {
      var it = state.items.find(function (x) { return String(x.index) === k; });
      if (!it) return;                          // this build no longer has that row
      var s = store[k];
      var chaos = s.chaos != null ? { min: s.chaos, median: s.chaos, high: s.chaos } : { min: null, median: null, high: null };
      var note = s.chaos != null ? ("you pasted: " + fmtAmt(s.amount) + " " + s.currency)
                                 : ("you pasted: " + fmtAmt(s.amount) + " " + s.currency + " — no chaos rate, not in the total");
      applyPrice(k, { chaos: chaos, confidence: "medium", method: "whisper", source: "manual",
        note: note, sample_size: 1, total_found: 1, manual_currency: s.currency, manual_amount: s.amount }, { include: true });
    });
  }
  function fmtAmt(n) { return (n % 1 === 0) ? String(n) : String(Math.round(n * 100) / 100); }

  // rows still needing a client-side price: rares / magic / uniques poe.ninja couldn't name,
  // that carry a trade query. Excludes anything already priced (server, cache, whisper, extension).
  function manualRows() {
    return state.items.filter(function (it) {
      var p = state.priced[String(it.index)];
      if (!p) return false;
      var priceable = it.category === "rare" || it.category === "magic" ||
                      (it.category === "unique" && (p.method === "unique-unpriced" || p.source === "trade" ||
                                                    !!it.variant ||
                                                    // D-0021: unique JEWELS priced by poe.ninja are scannable —
                                                    // trade is the real price, ninja is only the last-chance floor.
                                                    (it.group === "jewel" && /^unique-ninja/.test(p.method || ""))));
      if (!priceable) return false;
      if (it.swap && !includeSwap()) return false;   // D-0018: swap gear sits out until re-included
      if (isMagicFlask(it) && !includeMagicFlasks()) return false;   // D-0021: magic flasks sit out unless re-included
      var hasQuery = !!(p.trade_query || p.trade_url || it.trade_query || it.trade_url);
      return hasQuery;
    }).map(function (it) {
      var k = String(it.index), p = state.priced[k];
      return { key: k, item: it, price: p, priced: !!(p.chaos && p.chaos.median != null),
               source: p.source, trade_url: p.trade_url || it.trade_url || "" };
    });
  }

  // =====================================================================
  //  COMMUNITY CACHE  (read-through GET + extension POST-back) — worker.js
  // =====================================================================
  function cacheOptOut() { return lsget("bpc_cache_optout") === "1"; }
  function setCacheOptOut(on) {
    lsset("bpc_cache_optout", on ? "1" : "0");
    emit("control", { name: "cache_optout", value: !!on });
    if (!on && state.meta) cacheReadThrough();      // opting back in -> try a fill now
  }
  function cacheEnabled() { return !!WORKER_BASE && !/REPLACE_ME/.test(WORKER_BASE) && !cacheOptOut(); }
  function cacheEndpoint() { return /\/cache$/.test(WORKER_BASE) ? WORKER_BASE : (WORKER_BASE + "/cache"); }

  // Fill unpriced rows from the shared cache. Reads keys for the manual rows only (the ones
  // that could benefit); server-priced gems/uniques already have numbers.
  function cacheReadThrough() {
    if (!cacheEnabled() || !_hasSubtle() || !state.meta) return;
    var gen = state.gen;             // R6-F1: pin this build's generation for the async cache reply below
    var league = state.meta.league || "";
    var rows = manualRows().filter(function (r) { return !r.priced; });
    if (!rows.length) return;
    Promise.all(rows.map(function (r) {
      return cacheKey(league, r.item).then(function (kk) { return { row: r, key: kk }; });
    })).then(function (pairs) {
      var byCacheKey = {};
      pairs.forEach(function (pr) { byCacheKey[pr.key] = pr.row.key; });
      var keys = pairs.map(function (pr) { return pr.key; });
      // chunk into <=MAX_KEYS batches
      var chunks = [];
      for (var i = 0; i < keys.length; i += MAX_KEYS) chunks.push(keys.slice(i, i + MAX_KEYS));
      chunks.forEach(function (chunk) {
        var url = cacheEndpoint() + "?league=" + encodeURIComponent(league) + "&keys=" + encodeURIComponent(chunk.join(","));
        fetch(url).then(function (r) { return r.ok ? r.json() : {}; }).then(function (found) {
          if (gen !== state.gen) return;   // R6-F1: build changed under us -> don't fold stale cache prices onto the new build
          Object.keys(found || {}).forEach(function (ck) {
            var rowKey = byCacheKey[ck]; if (rowKey == null) return;
            var rec = found[ck]; if (!rec || !rec.chaos) return;
            if (rec.chaos.median == null && rec.chaos.min == null && rec.chaos.high == null) return;
            applyPrice(rowKey, {
              chaos: { min: num(rec.chaos.min), median: num(rec.chaos.median != null ? rec.chaos.median : rec.chaos.min), high: num(rec.chaos.high) },
              confidence: rec.confidence || "low", method: (rec.method || "cache"), source: "cache",
              note: "Community-submitted price — not verified by this site. Confirm via the trade link.",
              // R6-S1: the ?worker override bypasses the worker's write-time sanitiser, so re-validate
              // here too — a poisoned entry must not carry a non-numeric or a non-pathofexile trade_url.
              sample_size: num(rec.sample_size) || 0, total_found: num(rec.total_found) || 0,
              trade_url: (typeof rec.trade_url === "string" && /^https:\/\/www\.pathofexile\.com\//i.test(rec.trade_url)) ? rec.trade_url : undefined
            });   // passive fill: no {include:true} so a user's own decision isn't overridden
          });
        }).catch(function () {});
      });
    }).catch(function () {});
  }
  function num(x) { return (typeof x === "number" && isFinite(x)) ? x : null; }

  // POST prices produced on THIS machine (extension results) back to the shared cache.
  function cachePost(records) {
    if (!cacheEnabled() || !_hasSubtle() || !state.meta || !records.length) return;
    var league = state.meta.league || "";
    Promise.all(records.map(function (rec) {
      return cacheKey(league, rec.item).then(function (kk) { return { key: kk, value: rec.value }; });
    })).then(function (pairs) {
      for (var i = 0; i < pairs.length; i += MAX_KEYS) {
        var slice = pairs.slice(i, i + MAX_KEYS), entries = {};
        slice.forEach(function (pr) { entries[pr.key] = pr.value; });
        fetch(cacheEndpoint(), { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ league: league, entries: entries }) }).catch(function () {});
      }
    }).catch(function () {});
  }

  // =====================================================================
  //  EXTENSION BRIDGE  (postMessage protocol — docs/notes-public-ext.md §1)
  // =====================================================================
  var pending = {};           // reqId -> callback
  var reqSeq = 0;
  function rid() { return "bpc" + (++reqSeq) + "-" + Date.now(); }
  function bridgeSend(type, extra) {
    var msg = Object.assign({ source: "bpc-page", type: type, reqId: rid() }, extra || {});
    try { window.postMessage(msg, window.location.origin); } catch (e) {}
    return msg.reqId;
  }
  function initBridge() {
    if (typeof window === "undefined" || !window.addEventListener) return;
    window.addEventListener("message", function (ev) {
      if (ev.source !== window) return;
      var d = ev.data;
      if (!d || d.source !== "bpc-ext") return;
      if (d.type === "hello" || d.type === "pong") { markBridge(d.version); if (pending[d.reqId]) { pending[d.reqId](); delete pending[d.reqId]; } return; }
      // v1.1 per-item progress (status only — prices still land via price-result below).
      // Route by reqId (must belong to the live scan) + key (must be in its order).
      if (d.type === "price-progress") { if (scan.active && scan.reqIds[d.reqId]) scanSet(d.key, d.stage, d.detail); return; }
      if (d.type === "price-result" && pending[d.reqId]) {
        var cb = pending[d.reqId]; delete pending[d.reqId];
        cb(d.error ? { error: d.error } : { results: d.results || [] });
      }
    });
    // announce-or-ping: content scripts fire an unsolicited "hello"; we also ping in case we
    // loaded after it. No reply within 1.2s -> treat the bridge as absent (Rung-1 fallback).
    var pid = bridgeSend("ping"); pending[pid] = function () {};
    setTimeout(function () { if (!state.bridge.active) emit("bridge", state.bridge); }, 1300);
  }
  function markBridge(version) {
    if (state.bridge.active && state.bridge.version === (version || null)) return;
    state.bridge.active = true; state.bridge.version = version || null;
    emit("bridge", state.bridge);
  }

  // =====================================================================
  //  SCAN STATUS  (v1.1 per-item progress -> per-row chips + progress bar)
  //  Additive to the D-0012 chunked bridge below. Progress events carry
  //  STATUS ONLY; the priced numbers are still applied from the final
  //  price-result reply in foldBatch() (single source of truth). Works with
  //  an OLD extension too: no progress events => rows sit at "scanning" until
  //  the chunk reply resolves them. Emits "scanstatus" with
  //  { active, total, done, current, order, names, status{ key -> {stage,detail,ahead,resolved,waitUntil} } }.
  //  stage: queued | scanning | searching | fetching | waiting | done | nobuyout | error
  // =====================================================================
  var scan = { active: false, order: [], names: {}, status: {}, reqIds: {} };
  var SCAN_TERMINAL = { done: 1, nobuyout: 1, error: 1 };
  var SCAN_ACTIVE = { scanning: 1, searching: 1, fetching: 1, waiting: 1 };
  function scanReset() { scan = { active: false, order: [], names: {}, status: {}, reqIds: {} }; }
  function scanResolved(key) { var s = scan.status[String(key)]; return !!(s && SCAN_TERMINAL[s.stage]); }
  // a self-describing debug tail for a failing item (the owner's "no buyout everywhere" mystery)
  function debugSuffix(dbg) {
    if (!dbg) return "";
    var bits = [];
    if (dbg.searchStatus != null) bits.push("search " + dbg.searchStatus);
    if (dbg.fetchStatus != null) bits.push("fetch " + dbg.fetchStatus);
    if (dbg.fetched != null) bits.push(dbg.fetched + " fetched");
    if (dbg.nulls != null) bits.push(dbg.nulls + " w/o buyout");
    return bits.length ? (" [" + bits.join(", ") + "]") : "";
  }
  function scanSnapshot() {
    var order = scan.order.slice(), status = {}, done = 0, unresolvedBefore = 0, current = null, i;
    order.forEach(function (k) {
      var s = scan.status[k] || { stage: "queued", detail: null };
      var resolved = !!SCAN_TERMINAL[s.stage];
      if (resolved) done++;
      status[k] = { stage: s.stage, detail: s.detail || null, waitUntil: s.waitUntil || null,
                    resolved: resolved, ahead: unresolvedBefore, ms: (s.ms != null ? s.ms : null) };
      if (!resolved) unresolvedBefore++;      // ahead = # of unresolved rows earlier in SEND order
    });
    for (i = 0; i < order.length; i++) { if (SCAN_ACTIVE[status[order[i]].stage]) { current = order[i]; break; } }
    var totalMs = scan.startedAt ? ((scan.finishedAt || Date.now()) - scan.startedAt) : null;
    if (current == null) { for (i = 0; i < order.length; i++) { if (!status[order[i]].resolved) { current = order[i]; break; } } }
    return { totalMs: totalMs, active: scan.active, total: order.length, done: done, current: current,
             order: order, names: Object.assign({}, scan.names), status: status };
  }
  function scanEmit() { emit("scanstatus", scanSnapshot()); }
  function scanBegin(rows) {
    scanReset(); scan.active = true; scan.startedAt = Date.now();
    rows.forEach(function (r) {
      var k = String(r.key); scan.order.push(k);
      scan.names[k] = (r.item && r.item.name) || k;
      scan.status[k] = { stage: "queued", detail: null };
    });
    scanEmit();
  }
  function scanSet(key, stage, detail) {
    key = String(key);
    if (!scan.active || scan.order.indexOf(key) < 0) return;
    if (scanResolved(key) && !SCAN_TERMINAL[stage]) return;      // never regress a resolved row
    var s = scan.status[key] || (scan.status[key] = {});
    // D-0020 timing audit: stamp first activity + terminal per row; ms = row wall-clock
    if (s.t0 == null && stage !== "queued") s.t0 = Date.now();
    if (SCAN_TERMINAL[stage] && s.ms == null) s.ms = s.t0 != null ? (Date.now() - s.t0) : 0;
    s.stage = stage; s.detail = detail || null;
    s.waitUntil = (stage === "waiting" && detail && detail.waitMs) ? (Date.now() + detail.waitMs) : null;
    scanEmit();
  }
  function scanEnd() { if (!scan.active) return; scan.active = false; scan.finishedAt = Date.now(); scanEmit(); }

  // Price one or more rows via the extension. Groups by league (one price message per league,
  // per the protocol — the extension prices the batch serially under its own limiter).
  function priceRowsViaExtension(rows) {
    if (!state.bridge.active) return Promise.resolve({ error: "no bridge" });
    // R6-F3 (race lens): this is the single funnel for EVERY scan entrypoint — autoscan(), the per-row
    // ⚡auto button (priceViaExtension), and the picker Autoscan / re-search (priceRaresCustom /
    // priceRareCustom). If a scan is already live, starting another here would (a) scanBegin()->scanReset()
    // WIPE the running session's order/chips/progress bar (BUG_sessionCollapsed) and (b) re-send rows the
    // live scan already dispatched -> DUPLICATE on-IP trade searches + duplicate community-cache POSTs
    // (rate-limit discipline is load-bearing — CLAUDE.md: violations -> temporary IP bans). Guarding at this
    // one choke point closes all entrypoints at once and can't be forgotten by a present or future UI skin.
    // Callers treat the resolved {busy} exactly like the {error:"no bridge"} above (no-op, fire-and-forget).
    if (scan.active) return Promise.resolve({ error: "scan in progress", busy: true });
    var gen = state.gen;             // R6-F1: pin the build this scan belongs to; late replies gate on it
    var byLeague = {};
    rows.forEach(function (r) {
      var it = r.item, p = r.price;
      var tq = (p && p.trade_query) || it.trade_query;
      // the affix picker passes a client-built REFINED query (r.query); otherwise use the item's
      // own strict trade_query. Either way we pass the INNER query object, not the {query,sort} wrapper.
      var q = r.query || (tq && (tq.query || tq));
      if (!q) return;
      var lg = (state.meta && state.meta.league) || "";
      (byLeague[lg] = byLeague[lg] || []).push({ key: r.key, query: q });
    });
    // Send in SMALL chunks, sequentially. The extension prices serially under its own
    // conservative rate limiter, so a 17-item batch legitimately takes minutes — one big
    // message with a fixed 45s reply timeout dropped the whole answer (the launch-day bug).
    // Chunks keep every reply well inside its own timeout and rows fill progressively.
    var CHUNK = 3;
    var chunks = [];
    Object.keys(byLeague).forEach(function (lg) {
      for (var i = 0; i < byLeague[lg].length; i += CHUNK)
        chunks.push({ league: lg, queries: byLeague[lg].slice(i, i + CHUNK) });
    });
    // Begin a scan session: the flat order is every queued key across chunks, in SEND order,
    // so "N ahead" and the progress bar track exactly how the extension prices them serially.
    var scanRows = [];
    chunks.forEach(function (c) { c.queries.forEach(function (qq) {
      scanRows.push({ key: qq.key, item: state.items.find(function (x) { return String(x.index) === String(qq.key); }) });
    }); });
    if (scanRows.length) scanBegin(scanRows);
    var cachedCount = 0;
    function foldBatch(b) {
      // R6-F1b: if a newer build loaded while this scan was in flight, this reply is a ZOMBIE from the
      // superseded build. Dropping it here prevents (a) folding its prices onto the new build's
      // same-index items (item.index is positional, so index 3's "Headhunter" price would land on
      // whatever sits at index 3 now) and (b) cachePost() below POSTing those cross-build prices into
      // the SHARED community cache under the new build's item identities (cross-user corruption).
      if (gen !== state.gen) return;
      var toCache = [];
      var seen = {};
      if (b.resp && !b.resp.error) {
        (b.resp.results || []).forEach(function (res) {
          var key = String(res.key); seen[key] = true;
          var it = state.items.find(function (x) { return String(x.index) === key; });
          if (!it) return;
          var dbg = res.debug || null;      // v1.1: {searchStatus, fetchStatus, fetched, nulls} (absent on old ext)
          if (res.error) {
            foldFail(key, { confidence: "none", method: "extension", source: "trade",
              note: "extension: " + res.error + debugSuffix(dbg), debug: dbg },
              "error", { message: res.error, status: dbg && dbg.searchStatus });
            return;
          }
          if (res.amount == null) {
            var _tot = res.total || 0;   // 0 = nothing matched the search; >0 = matched but no buyout price
            foldFail(key, { confidence: "none", method: "extension", source: "trade",
              note: (_tot > 0 ? "listings exist but none had a buyout price"
                              : "no listings matched this search") + debugSuffix(dbg),
              total_found: _tot, debug: dbg },
              "nobuyout", { total: _tot, fetched: dbg ? dbg.fetched : null, nulls: dbg ? dbg.nulls : null });
            return;
          }
          // D-0016 item 4: build real {min,median,high} from ALL fetched listings (ext v1.2.0
          // prices[]) with the local app's distribution math. Fallback (old v1.1.0 ext with no
          // prices[], or an all-non-convertible set): the single cheapest, exactly as before.
          var band = rareTiersFromPrices(res.prices, divRate());
          var chaos = toChaos(res.amount, res.currency);   // cheapest (norate guard + fallback)
          if (band == null && chaos == null) {
            foldFail(key, { confidence: "low", method: "extension", source: "trade",
              note: "cheapest: " + fmtAmt(res.amount) + " " + res.currency + " (no chaos rate to convert)" + debugSuffix(dbg),
              total_found: res.total || 0, debug: dbg },
              "nobuyout", { total: res.total || 0, amount: res.amount, currency: res.currency, norate: true });
            return;
          }
          var tierObj = band ? { min: band.min, median: band.median, high: band.high }
                             : { min: chaos, median: chaos, high: chaos };
          var nSamp = band ? band.sample : 1;
          var tierNote = band
            ? ("priced via extension — " + nSamp + " of " + (res.total || 0) + " listings (min · median · high)")
            : ("priced via extension — cheapest buyout of " + (res.total || 0) + " online listings");
          applyPrice(key, {
            chaos: tierObj, confidence: confFromTotal(res.total),
            method: "extension", source: "trade",
            note: tierNote,
            sample_size: nSamp, total_found: res.total || 0, debug: dbg
          }, { include: true });
          scanSet(key, "done", { total: res.total || 0, amount: res.amount, currency: res.currency });
          // POST the real, on-IP tiers to the shared cache (short TTL) for everyone else
          toCache.push({ item: it, value: {
            chaos: tierObj, confidence: confFromTotal(res.total),
            method: "extension", sample_size: nSamp, total_found: res.total || 0,
            note: "", trade_url: (state.priced[key] && state.priced[key].trade_url) || it.trade_url || ""
          } });
        });
      }
      // Any key in this chunk with no usable result (whole-chunk error/timeout, or omitted from
      // the reply) resolves to a self-describing failure so the bar + chips still complete.
      (b.keys || []).forEach(function (key) {
        key = String(key);
        if (seen[key] || scanResolved(key)) return;
        var msg = (b.resp && b.resp.error) ? b.resp.error : "no result returned";
        foldFail(key, { confidence: "none", method: "extension", source: "trade", note: "extension: " + msg },
          "error", { message: msg });
      });
      if (toCache.length) { cachedCount += toCache.length; cachePost(toCache); }
    }
    var idx = 0;
    function nextChunk() {
      // R6-F1b: a newer build superseded this scan -> stop sending further chunks to the extension
      // (wasted trade calls against a build the user has moved on from). No scanEnd(): the global scan
      // object now belongs to the new build, so ending it here would kill the CURRENT build's scan.
      if (gen !== state.gen) return Promise.resolve({ ok: false, superseded: true });
      if (idx >= chunks.length) { scanEnd(); return Promise.resolve({ ok: true, cached: cachedCount }); }
      var c = chunks[idx++];
      var keys = c.queries.map(function (qq) { return qq.key; });
      return new Promise(function (resolve) {
        // protocolVersion 1.1 opts THIS request into per-item progress events; an old extension
        // ignores the field and never emits them (feature-detected page-side => generic chip).
        var id = bridgeSend("price", { league: c.league, queries: c.queries, protocolVersion: 1.1 });
        scan.reqIds[id] = true;
        keys.forEach(function (k) { scanSet(k, "scanning", null); });   // "sent"; v1.1 progress refines it
        // sized to THIS chunk's worst-case limiter pacing, not the whole scan
        var ms = 30000 + 30000 * c.queries.length;
        pending[id] = function (resp) { resolve({ league: c.league, resp: resp, keys: keys }); };
        setTimeout(function () { if (pending[id]) { delete pending[id]; resolve({ league: c.league, resp: { error: "timed out" }, keys: keys }); } }, ms);
      }).then(function (b) { foldBatch(b); return nextChunk(); });   // a failed chunk never blocks the rest
    }
    return nextChunk();
  }
  // A variant unique's poe.ninja floor/range is a PLACEHOLDER, not its price (owner report
  // 2026-07-27: "why did i have to click each unique jewel to price it?") - autoscan treats
  // such rows as unfinished until their exact locked-mod search has run (source becomes 'trade').
  function needsScan(r) {
    if (!r.priced) return true;
    var p = r.price || {};
    // D-0019 variant uniques AND D-0021 unique jewels both load on a poe.ninja floor that autoscan
    // must replace with a real trade price (ninja is last-chance only).
    if (r.item && /^unique-ninja/.test(p.method || "") && (r.item.variant || r.item.group === "jewel")) return true;
    return false;
  }
  // F1 (R2): a variant unique carries a poe.ninja name-level PLACEHOLDER at load (D-0019: "floor
  // is a PLACEHOLDER, not its price"). If its exact locked-mod search then comes back with no real
  // trade price (0 matches / no buyout / no chaos rate / an error), that placeholder is proven NOT
  // to be this variant's price, so it must DROP to link-only — exactly like a 0-match rare
  // ("unmatchable -> link + no number"), never lingering as a counted, misleading number. Given a
  // failure patch, null its chaos iff the row still shows the ninja placeholder (method
  // unique-ninja*). Scoped to the placeholder only: a real whisper / cache / prior-scan price is a
  // different method and is never clobbered by a failed re-scan. Runs BEFORE applyPrice overwrites
  // state.priced, so it reads the pre-scan price. applyPrice's null-median branch then clears the
  // stale enable, and totals() (which skips null medians) drops the row from the headline.
  function dropIfPlaceholder(key, patch) {
    var it = state.items.find(function (x) { return String(x.index) === String(key); });
    var p = state.priced[String(key)];
    if (it && it.variant && p && p.chaos && p.chaos.median != null && /^unique-ninja/.test(p.method || ""))
      patch.chaos = { min: null, median: null, high: null };
    return patch;
  }
  // D-0021: single funnel for a scan row that resolved WITHOUT a real trade price. A JEWEL keeps its
  // poe.ninja floor (last-chance price - priced + included, just annotated); everything else drops the
  // placeholder + excludes, exactly as before.
  function foldFail(key, patch, stage, detail) {
    if (isJewelFloor(key)) applyPrice(key, { note: "no live trade match — poe.ninja estimate (last resort)" });
    else applyPrice(key, dropIfPlaceholder(key, patch), { include: false });
    scanSet(key, stage, detail);
  }
  function autoscan() { return priceRowsViaExtension(manualRows().filter(needsScan)); }
  function priceViaExtension(key) {
    var r = manualRows().find(function (x) { return x.key === String(key); });
    return r ? priceRowsViaExtension([r]) : Promise.resolve({ error: "no such row" });
  }
  // convert an extension/whisper amount+currency to chaos (chaos + divine only; else null)
  function toChaos(amount, currency) {
    if (amount == null) return null;
    var c = CUR_ALIAS[String(currency || "").toLowerCase()] || String(currency || "").toLowerCase();
    if (c === "chaos") return amount;
    var rates = (state.meta && state.meta.rates) || {};
    if (rates[c] > 0) return amount * rates[c];
    if (c === "divine") return divRate() ? amount * divRate() : null;
    return null;
  }
  function confFromTotal(n) { n = n || 0; return n >= 5 ? "high" : n >= 2 ? "medium" : "low"; }

  // =====================================================================
  //  RARE PRICE DISTRIBUTION  (D-0016 item 4)
  // ---------------------------------------------------------------------
  //  Port of the LOCAL app's bpc/pricing.py Pricer._tiers + bpc/util.py
  //  (trim_outliers / median / percentile) — byte-faithful so an
  //  extension-priced rare gets the SAME {min, median, high} the desktop
  //  app would compute from the same listings. Pure + node-testable.
  //  HIGH_PCT=90; trim keeps prices in [0.30, 6.0] × median.
  // =====================================================================
  var HIGH_PCT = 90;
  function _sortNum(a) { return a.slice().sort(function (x, y) { return x - y; }); }
  // linear-interpolation percentile (pct 0..100); null for empty. Mirrors util.percentile.
  function _percentile(values, pct) {
    if (!values || !values.length) return null;
    var xs = _sortNum(values);
    if (xs.length === 1) return xs[0];
    var k = (xs.length - 1) * (pct / 100);
    var lo = Math.floor(k), hi = Math.min(lo + 1, xs.length - 1), frac = k - lo;
    return xs[lo] + (xs[hi] - xs[lo]) * frac;
  }
  function _median(values) { return _percentile(values, 50); }
  // drop scam/typo listings relative to the median: keep [lo,hi]×median. Mirrors util.trim_outliers.
  function _trimOutliers(values, loMult, hiMult) {
    loMult = (loMult == null ? 0.30 : loMult); hiMult = (hiMult == null ? 6.0 : hiMult);
    var vals = _sortNum((values || []).filter(function (v) { return v != null && v > 0; }));
    if (!vals.length) return [];
    var med = _median(vals);
    if (!med) return vals;
    var kept = vals.filter(function (v) { return loMult * med <= v && v <= hiMult * med; });
    return kept.length ? kept : vals;                    // never empty just because it's spread out
  }
  // Pricer._tiers: chaos values -> {min, median, high, sample} (null when nothing kept).
  function tiersFromChaos(chaosVals) {
    var kept = _trimOutliers(chaosVals);
    if (!kept.length) return null;
    return { min: kept[0], median: _median(kept), high: _percentile(kept, HIGH_PCT), sample: kept.length };
  }
  // convert one {amount,currency} to chaos with an EXPLICIT rate (keeps this pure/testable —
  // no state read). chaos+divine convert; anything else has no build rate -> null (never faked).
  function _amtToChaos(amount, currency, rate) {
    if (amount == null) return null;
    var c = CUR_ALIAS[String(currency || "").toLowerCase()] || String(currency || "").toLowerCase();
    if (c === "chaos") return amount;
    if (c === "divine") return rate ? amount * rate : null;
    return null;
  }
  // Convert an extension prices[] array ([{amount,currency}…], fetch = price-ascending order) to
  // chaos and run the distribution. Returns {min,median,high,sample} or null (old ext / nothing
  // convertible). Non-convertible listings are dropped (not fabricated) — D-0015: nothing hidden,
  // the whole convertible set feeds the sheet.
  function rareTiersFromPrices(prices, rate) {
    if (!prices || !prices.length) return null;
    var chaos = [];
    for (var i = 0; i < prices.length; i++) {
      var c = _amtToChaos(prices[i] && prices[i].amount, prices[i] && prices[i].currency, rate);
      if (c != null && c > 0) chaos.push(c);
    }
    return tiersFromChaos(chaos);
  }

  // =====================================================================
  //  PER-RARE AFFIX PICKER  —  client-side query builder (D-0015)
  // ---------------------------------------------------------------------
  //  Pure + node-testable (no DOM/window). The picker UI (index.html) drives
  //  these. D-0015: the default state has EVERY searchable affix ticked with
  //  its roll prefilled — the tool never unticks anything; only the USER
  //  subtracts/edits. "All ticked, unedited" reproduces the item's own strict
  //  query (modulo ordering); scope (status/type/name/type_filters) + the 5/6-
  //  link socket filter are copied VERBATIM from the item's trade_query and
  //  never invented. Faithful to the local app's advanced picker (bpc/web.py
  //  affixRow/submitRare): a normal roll prefills MIN, a negated/'reduced' roll
  //  prefills MAX, and — like that picker — a ticked affix searches "at least
  //  this good" (min = the roll), which is deliberately stricter than the API's
  //  presence-only Autoscan default; the user loosens by clearing a min.
  // =====================================================================
  function _pnum(x) { if (x === "" || x == null) return null; var v = Number(x); return isFinite(v) ? v : null; }
  // An affix's prefilled (min,max): the payload's explicit default_min/default_max when present
  // (public API §2.6), else derived from the signed roll + negated flag (mirrors bpc/web.py affixRow
  // and the API's _affix_defaults). `value` still carries the raw roll for display.
  function affixPrefill(a) {
    if (!a) return { min: null, max: null };
    if (a.default_min !== undefined || a.default_max !== undefined)
      return { min: _pnum(a.default_min), max: _pnum(a.default_max) };
    var v = _pnum(a.value);
    var neg = !!a.negated || (v != null && v < 0);
    return neg ? { min: null, max: v } : { min: v, max: null };
  }
  // D-0015: every searchable stat affix (and every defence total) starts TICKED. `prefer` is only a
  // hint the API carries; the picker never unticks — all searchable default to on. Unsearchable
  // (no stat_id) can never be a filter, so it is never "ticked" (and never emitted).
  function affixDefaultTicked(a) {
    if (!a) return false;
    if (a.kind === "equip") return a.key != null;
    if (a && a.priority === "exclude") return false;   // owner default_off: off by default (still selectable)
    return !!(a.searchable && a.stat_id);
  }
  // D-0016 item 3 — map the API's affix `priority` (contract §3: required·nice·notimp·skip) onto
  // the site's THREE tiers. `notimp` -> nice-to-have (NOT not-needed): D-0015 forbids the tool
  // auto-EXCLUDING on a low score; nice keeps it searched in the count group (whose default
  // threshold is #nice−1 per D-0034 — searched, but not force-required). `skip` -> not-needed
  // ONLY when the row is UNSEARCHABLE (no stat_id — it can never
  // be a filter); a SEARCHABLE `skip` row is treated like `notimp` (still searched). querybuild
  // assigns `skip` to EVERY non-skill-level unique mod AND the unique pseudo total (all
  // searchable) — mapping those to not-needed silently auto-excluded them (D-0020 R3-2, breaching
  // D-0015: 51/53 uniques dropped filters). No hint -> required (strictest; preserves the
  // all-affix default + the offline test fixtures).
  function _siteTierOf(a) {
    var pr = a && a.priority;
    if (pr === "required") return "required";
    if (pr === "nice" || pr === "notimp") return "nice";
    // `exclude` = owner-curated default_off (registry `default_off`, e.g. Watcher's Eye generic max
    // Life/Mana/ES): default to NOT-NEEDED but still searchable + shown, so the user can opt it back in.
    if (pr === "exclude") return "notneeded";
    if (pr === "skip") return (a && a.stat_id) ? "nice" : "notneeded";
    return "required";
  }
  // The default picks for a rare: all searchable affixes ticked with their prefilled min/max, every
  // pseudo row ticked, and the resistance-fold (pseudo) toggle ON when the item has any resistance
  // pseudo total — exactly the local app's default (usePseudo = pseudo.length>0). Each pick also
  // carries a prefilled `tier` (visible suggestion; the user reviews the sheet before searching).
  function rareDefaultPicks(rare) {
    rare = rare || {};
    var picks = { usePseudo: !!(rare.pseudo && rare.pseudo.length), affix: {}, pseudo: {} };
    (rare.affixes || []).forEach(function (a, i) { var pf = affixPrefill(a);
      picks.affix[i] = { ticked: affixDefaultTicked(a), min: pf.min, max: pf.max, tier: _siteTierOf(a) }; });
    (rare.pseudo || []).forEach(function (p, j) { var pf = affixPrefill(p);
      picks.pseudo[j] = { ticked: true, min: pf.min, max: pf.max, tier: _siteTierOf(p) }; });
    return picks;
  }
  function _statFilter(id, min, max) {
    var f = { id: id }, v = {};
    if (min != null) v.min = min;
    if (max != null) v.max = max;
    if (Object.keys(v).length) f.value = v;
    return f;
  }
  // D-0019/D-0022 — a variant-DEFINING mod's filter VALUE, built from the affix's own identity value
  // (never from user picks): an OPTION mod (Allocates-notable / ring-size / keystone-radius) ->
  // {id: base, value:{option:N}}; an EXACT seed/count -> min==max; else the roll min. The VALUE is
  // always the item's identity. D-0022 UNLOCKS the requirement: the picker now chooses WHETHER to
  // emit it (tier required/nice) or drop it (not-needed) — but when emitted it is exactly this
  // value, so all-required reproduces the D-0019 exact-variant query byte-for-byte.
  function _definingFilter(a) {
    if (a.option != null) return { id: a.stat_id, value: { option: a.option } };
    var pf = affixPrefill(a);
    if (a.exact) { var v = (pf.min != null ? pf.min : pf.max); return _statFilter(a.stat_id, v, v); }
    return _statFilter(a.stat_id, pf.min, pf.max);
  }
  function _pickOf(map, i, a) {
    var e = map && map[i];
    if (e) return { ticked: !!e.ticked, min: _pnum(e.min), max: _pnum(e.max), group: (e.group != null ? e.group : null) };
    var pf = affixPrefill(a);                 // no explicit pick -> the all-ticked default (group 0)
    return { ticked: affixDefaultTicked(a), min: pf.min, max: pf.max, group: null };
  }
  // Build a rare trade query (the INNER query object) from the CURRENT picker state.
  //   rare      = state.rares[key]  ({ affixes:[], pseudo:[] })
  //   origQuery = the item's own trade_query.query  OR its scope_q — the ONLY source of scope
  //               (status/type/name/type_filters) and the links socket_filter. Never invented.
  //   picks     = { usePseudo, affix:{i:{ticked,min,max,group}}, pseudo:{j:{ticked,min,max,group}},
  //                 groups:[{type:'and'|'count'|'not', min}] }.
  //               Omit picks (or an entry) to use that affix's all-ticked default, so
  //               buildRareQuery(rare, origQuery) == the all-ticked query.
  //   GROUPS (D-0016 item 3): with NO picks.groups every ticked affix goes into ONE AND group —
  //   byte-identical to the original single-group behaviour. With a picks.groups array each
  //   pick's `.group` index routes it to that group; a `count` group carries the trade API's
  //   group-level value:{min} (clamped to [1, #filters]; default = all ⇒ acts as AND).
  function buildRareQuery(rare, origQuery, picks) {
    rare = rare || {}; picks = picks || {};
    var affixes = rare.affixes || [], pseudos = rare.pseudo || [];
    var usePseudo = picks.usePseudo !== undefined ? !!picks.usePseudo : !!(pseudos && pseudos.length);
    var oq = origQuery || {};
    var q = {};
    if (oq.type != null) q.type = oq.type;               // scope: copied verbatim, never invented
    if (oq.name != null) q.name = oq.name;
    q.status = oq.status ? oq.status : { option: state.status || "online" };
    var groupDefs = (picks.groups && picks.groups.length) ? picks.groups : [{ type: "and" }];
    var stats = [];
    groupDefs.forEach(function (g, gi) {
      var filters = [];
      affixes.forEach(function (a, i) {
        if (a.kind !== "stat") return;
        if (!a.searchable || !a.stat_id) return;          // unsearchable is NEVER emitted
        // D-0019/D-0022 — a variant-DEFINING mod is the item's identity but is now a NORMAL
        // tier-controlled row (required by default, deselectable). Handled BEFORE the resist-fold
        // (D-0020 R3-1) so a defining RESISTANCE (Purity Watcher's Eye, Viridian Grand Spectrum) is
        // never folded into a pseudo total. Emitted when its pick is ticked (tier required/nice),
        // OMITTED when not-needed; its VALUE stays the item's own identity (option / exact seed /
        // count) via _definingFilter, never the picker's min/max.
        if (a.defining) {
          var dpk = _pickOf(picks.affix, i, a);
          if (!dpk.ticked) return;                        // not-needed / unticked -> filter OMITTED
          if ((dpk.group != null ? dpk.group : 0) !== gi) return;   // route to its tier's group (default AND=0)
          filters.push(_definingFilter(a));
          return;
        }
        if (usePseudo && a.resist) return;                // folded into a pseudo total below
        var pk = _pickOf(picks.affix, i, a); if (!pk.ticked) return;
        if ((pk.group != null ? pk.group : 0) !== gi) return;
        // F1 (D-0020 R3) — a non-defining OPTION stat (cluster-jewel "grant: X" / "Allocates X"
        // enchant) emits GGG's wire form {id:base, value:{option}}; it has no magnitude filter, so
        // pk.min/max are ignored (mirrors _definingFilter's option branch).
        if (a.option != null) { filters.push({ id: a.stat_id, value: { option: a.option } }); return; }
        filters.push(_statFilter(a.stat_id, pk.min, pk.max));
      });
      if (usePseudo) pseudos.forEach(function (p, j) {
        if (!p.stat_id) return;
        var pk = _pickOf(picks.pseudo, j, p); if (!pk.ticked) return;
        if ((pk.group != null ? pk.group : 0) !== gi) return;
        filters.push(_statFilter(p.stat_id, pk.min, pk.max));
      });
      if (!filters.length) return;                        // drop empty groups
      var grp = { type: g.type || "and", filters: filters };
      if (grp.type === "count") {                         // count needs a group-level value.min
        var m = (g.min == null || g.min === "") ? filters.length : Number(g.min);
        if (!isFinite(m)) m = filters.length;
        grp.value = { min: Math.max(1, Math.min(Math.round(m), filters.length)) };
      }
      stats.push(grp);
    });
    if (!stats.length) stats = [{ type: "and", filters: [] }];   // scope-only search (nothing ticked)
    q.stats = stats;
    var filt = {};
    if (oq.filters && oq.filters.type_filters) filt.type_filters = oq.filters.type_filters;   // scope
    var armour = {};
    affixes.forEach(function (a, i) {
      if (a.kind !== "equip" || a.key == null) return;
      var pk = _pickOf(picks.affix, i, a); if (!pk.ticked) return;
      if (pk.min != null) armour[a.key] = { min: pk.min };  // defence totals are min-only
    });
    if (Object.keys(armour).length) filt.armour_filters = { filters: armour };
    if (oq.filters && oq.filters.socket_filters) filt.socket_filters = oq.filters.socket_filters;  // links verbatim
    if (Object.keys(filt).length) q.filters = filt;
    return q;
  }
  // D-0016 item 3 — the site's tier model -> stat GROUPS (pure; feeds buildRareQuery). Reads each
  // pick's `tier` ('required'|'nice'|'notneeded'; default = the affix's mapped priority) and returns
  // a NEW picks (usePseudo, affix{i:{ticked,min,max,tier,group}}, pseudo{…}, groups[], countMin):
  //   required  -> the AND group (min/max carried through "as now")
  //   nice      -> ONE count group; threshold = picks.countMin ?? (#nice − 1) = all-but-one (D-0034)
  //   notneeded -> excluded (unticked). Equip (defence totals) is required/not-needed only
  //               (armour_filters can't be count-grouped) and stays out of `groups`.
  function tierGroups(rare, picks) {
    rare = rare || {}; picks = picks || {};
    var affixes = rare.affixes || [], pseudos = rare.pseudo || [];
    var usePseudo = picks.usePseudo !== undefined ? !!picks.usePseudo : !!(pseudos && pseudos.length);
    function tOf(map, i, a) { var e = map && map[i]; return (e && e.tier) || _siteTierOf(a); }
    var req = 0, nice = 0;
    affixes.forEach(function (a, i) {
      if (a.kind !== "stat" || !a.searchable || !a.stat_id) return;
      // D-0022: a defining mod is counted BY ITS TIER (required/nice), like any stat — but a defining
      // RESIST skips the fold (R3-1: never folded), so it still counts and creates its own group.
      if (!a.defining && usePseudo && a.resist) return;
      var t = tOf(picks.affix, i, a); if (t === "required") req++; else if (t === "nice") nice++;
    });
    if (usePseudo) pseudos.forEach(function (p, j) {
      if (!p.stat_id) return;
      var t = tOf(picks.pseudo, j, p); if (t === "required") req++; else if (t === "nice") nice++;
    });
    var groups = [], andGi = -1, cGi = -1;
    if (req) { andGi = groups.length; groups.push({ type: "and" }); }
    if (nice) {
      cGi = groups.length;
      // D-0034 (owner): the untouched default threshold is ALL-BUT-ONE of the nice-to-have mods
      // (#nice − 1, floored at 1), not all of them — requiring every nice-to-have was too strict.
      // An explicit picks.countMin still wins (and clamps to [1, #nice]). The REQUIRED AND-group is
      // untouched, so every required mod still matches; only the nice count loosens by one.
      var cm = (picks.countMin != null ? picks.countMin : Math.max(1, nice - 1));
      groups.push({ type: "count", min: Math.max(1, Math.min(nice, Math.round(cm))) });
    }
    if (!groups.length) groups.push({ type: "and" });
    var out = { usePseudo: usePseudo, affix: {}, pseudo: {}, groups: groups,
                countMin: (cGi >= 0 ? groups[cGi].min : null) };
    function place(map, i, a, dst, isPseudo) {
      var base = _pickOf(map, i, a), t = tOf(map, i, a);
      var e = { ticked: base.ticked, min: base.min, max: base.max, tier: t };
      if (a.kind === "equip") { e.ticked = (t !== "notneeded"); dst[i] = e; return; }
      // D-0022: a defining mod routes by its tier like any stat (required->AND, nice->count,
      // not-needed->unticked) — but is NEVER folded into a pseudo total (R3-1), so it skips the fold.
      if (!isPseudo && !a.defining && usePseudo && a.resist) { dst[i] = e; return; }   // folded away; group irrelevant
      if (t === "required") { e.group = (andGi < 0 ? 0 : andGi); e.ticked = true; }
      else if (t === "nice") { e.group = (cGi < 0 ? 0 : cGi); e.ticked = true; }
      else { e.ticked = false; }                                        // notneeded -> excluded
      dst[i] = e;
    }
    affixes.forEach(function (a, i) { place(picks.affix, i, a, out.affix, false); });
    if (usePseudo) pseudos.forEach(function (p, j) { place(picks.pseudo, j, p, out.pseudo, true); });
    return out;
  }
  // D-0016 item 2 — re-scope a query to the chosen scope ('category'|'base') from rare.scopes.
  // Swaps ONLY the scope fields (type <-> type_filters.category); status, the 5/6-link
  // socket_filters and everything else are preserved. Never invents a scope — an unavailable
  // request returns the query unchanged (the default). Pure (deep-clones origQuery).
  function applyScope(rare, origQuery, which) {
    var oq = origQuery ? JSON.parse(JSON.stringify(origQuery)) : {};
    var scopes = (rare && rare.scopes) || {};
    if (which === "base" && scopes.base && scopes.base.type != null) {
      oq.type = scopes.base.type;
      if (oq.filters && oq.filters.type_filters && oq.filters.type_filters.filters) {
        delete oq.filters.type_filters.filters.category;
        if (!Object.keys(oq.filters.type_filters.filters).length) delete oq.filters.type_filters;
        if (oq.filters && !Object.keys(oq.filters).length) delete oq.filters;
      }
      return oq;
    }
    if (which === "category" && scopes.category && scopes.category.id != null) {
      delete oq.type;
      oq.filters = oq.filters || {};
      oq.filters.type_filters = oq.filters.type_filters || { filters: {} };
      oq.filters.type_filters.filters = oq.filters.type_filters.filters || {};
      oq.filters.type_filters.filters.category = { option: scopes.category.id };
      return oq;
    }
    return oq;
  }
  // the 5/6-link requirement a query carries (for the read-only picker chip), or null
  function queryLinks(oq) { try { return oq.filters.socket_filters.filters.links.min || null; } catch (e) { return null; } }
  // The browser ?q= trade URL for a query, reusing the item's own trade_url host+league so the URL
  // and the extension search run the SAME query. Pure string building — never calls pathofexile.com.
  function rareTradeUrl(query, refUrl) {
    var payload = encodeURIComponent(JSON.stringify({ query: query, sort: { price: "asc" } }));
    var base = "";
    if (refUrl) { var i = String(refUrl).indexOf("?q="); base = i >= 0 ? String(refUrl).slice(0, i) : String(refUrl); }
    // R6-S1: this URL flows to window.open()/href — a document-supplied refUrl must NEVER seed the
    // base. Only a real pathofexile.com/trade URL may; anything else (e.g. javascript:) is discarded
    // and the canonical trade URL is rebuilt below.
    if (!/^https:\/\/www\.pathofexile\.com\//i.test(base)) base = "";
    if (!base) { var lg = (state.meta && state.meta.league) || "Standard";
      base = "https://www.pathofexile.com/trade/search/" + encodeURIComponent(lg); }
    return base + "?q=" + payload;
  }
  function rareOf(key) { return (state.rares || {})[String(key)]; }

  // Price ONE rare via the extension using a client-built (refined) query. Reuses the tested D-0012
  // chunked path + v1.1 scan status + community-cache POST-back; the refined price folds into the
  // row + totals in place. Returns the priceRowsViaExtension promise (or {error} with no bridge).
  function priceRareCustom(key, query) {
    return priceRaresCustom([{ key: key, query: query }]);
  }
  // Price several refined rares (the in-picker Autoscan) in one chunked scan session.
  function priceRaresCustom(list) {
    var rows = [];
    (list || []).forEach(function (o) {
      var it = state.items.find(function (x) { return String(x.index) === String(o.key); });
      if (it) rows.push({ key: String(o.key), item: it, price: state.priced[String(o.key)] || {}, query: o.query });
    });
    return rows.length ? priceRowsViaExtension(rows) : Promise.resolve({ error: "no rows" });
  }
  // The no-extension refinement: remember the refined query+url on the row so its "open search" link
  // + tooltip reflect the picker's choice; the row STAYS in manual mode (no client-run search here).
  function setRareQuery(key, query, url) {
    key = String(key);
    var it = state.items.find(function (x) { return String(x.index) === key; });
    var cur = state.priced[key] || {};
    var u = url || rareTradeUrl(query, cur.trade_url || (it && it.trade_url));
    applyPrice(key, { trade_url: u, trade_query: { query: query, sort: { price: "asc" } }, refined: true }, { include: false });
    return u;
  }

  // ---- recent builds (localStorage; the public site has no /api/cache) ----
  function loadRecent() {
    // Type-coerce on read: a valid-JSON WRONG-TYPE value (string/number/object — from external
    // corruption, profile-sync mangling, or a future schema change) must heal to [] just like
    // unparseable garbage already does. Otherwise a later (state.recent||[]).filter(...) throws
    // inside loadBuild, aborting emit('manual')/emit('done') and unwinding to fail() so EVERY
    // build load ends in a false "could not reach the pricing service" error that persists across
    // reloads (R4S-1). Mirrors the type-safety the bpc_status_v2 / bpc_tier / bpc_manual keys have.
    var parsed; try { parsed = JSON.parse(lsget("bpc_recent_builds") || "[]"); } catch (e) { parsed = null; }
    state.recent = Array.isArray(parsed) ? parsed : [];
    emit("recent", state.recent);
  }
  function pushRecent(meta) {
    if (!meta) return;
    var url = meta.source_url && /^https?:\/\//i.test(meta.source_url) ? meta.source_url : (state.source && state.source.url) || "";
    if (!url) return;                                   // PoB imports have no shareable URL -> not saved
    var key = url;
    var entry = { key: key, url: url, character: meta.character || "Unknown", char_class: meta["class"] || "", level: meta.level || 0, ts: Date.now() };
    var list = (Array.isArray(state.recent) ? state.recent : []).filter(function (b) { return b && b.key !== key; });
    list.unshift(entry);
    state.recent = list.slice(0, 24);
    lsset("bpc_recent_builds", JSON.stringify(state.recent));
    emit("recent", state.recent);
  }

  // ---- mock / demo (render a full build with NO backend) ----
  function loadMock(snapshot) {
    state._mock = true; state.source = { mock: true }; reset();
    var j = snapshot || (typeof window !== "undefined" && window.BPC_SAMPLE);
    if (!j) { console.warn("[bpc] loadMock: no sample available"); return; }
    var clone = JSON.parse(JSON.stringify(j));
    state.meta = clone.meta || {};
    if (state.meta.status == null) state.meta.status = state.status;
    state.items = (clone.items || []).map(normItem);
    state.rares = clone.rares || {};
    state.warnings = clone.warnings || [];
    state.priced = {}; state._sig = {}; state.enabled = {};
    var np = clone.priced || {};
    Object.keys(np).forEach(function (k) {
      var p = np[k]; if (!p.chaos) p.chaos = { min: null, median: null, high: null };
      if (p.source == null) p.source = (p.chaos.median != null ? (p.method === "skill" ? "poe.ninja" : "trade") : "none");
      state.priced[k] = p; state._sig[k] = sigOf(p);
      if (p.chaos.median != null) state.enabled[k] = defaultOn(k);
    });
    emit("meta", state.meta);
    emit("items", state.items);
    emit("priced", { keys: Object.keys(state.priced), state: state });
    emit("totals", totals());
    state.phase = "done"; emit("state", state);
    emit("manual", manualRows());
    emit("done", state);
  }

  // ---- init ----
  function init(opts) {
    opts = opts || {}; loadPrefs();
    initBridge();
    if (opts.mock || qp("mock") != null) { loadMock(opts.mock && opts.mock !== true ? opts.mock : null); return api; }
    loadRecent();
    return api;
  }

  var api = {
    on: on, off: off, state: state, init: init,
    start: start, startUrl: startUrl, startCache: startCache, rerun: rerun, researchAll: researchAll,
    setControl: setControl, loadPrefs: loadPrefs,
    price: price, priceHTML: priceHTML, curImg: curImg, nfmt: nfmt, esc: esc, divRate: divRate, tierEx: tierEx,
    totals: totals, setEnabled: setEnabled, setIncludeSwap: setIncludeSwap, includeSwap: includeSwap, needsScan: needsScan, setGroupEnabled: setGroupEnabled, isPriced: isPriced, itemsByGroup: itemsByGroup,
    setIncludeMagicFlasks: setIncludeMagicFlasks, includeMagicFlasks: includeMagicFlasks, groupEnabled: groupEnabled, groupHasPriced: groupHasPriced,
    gemGroups: gemGroups, gemBreakdown: gemBreakdown, gemHost: gemHost,
    setPurchased: setPurchased, isPurchased: isPurchased,
    // public pricing
    parseWhisper: parseWhisper, applyWhisper: applyWhisper, clearManual: clearManual, manualRows: manualRows,
    autoscan: autoscan, priceViaExtension: priceViaExtension, scanStatus: scanSnapshot,
    // per-rare affix picker (D-0015): pure query builder + the extension/URL price paths
    buildRareQuery: buildRareQuery, rareDefaultPicks: rareDefaultPicks, affixPrefill: affixPrefill,
    // D-0016: priority-tier -> groups (item 3), category<->base scope (item 2), rare distribution (item 4)
    tierGroups: tierGroups, applyScope: applyScope,
    rareTiersFromPrices: rareTiersFromPrices, tiersFromChaos: tiersFromChaos,
    rareTradeUrl: rareTradeUrl, queryLinks: queryLinks, rareOf: rareOf,
    priceRareCustom: priceRareCustom, priceRaresCustom: priceRaresCustom, setRareQuery: setRareQuery,
    cacheOptOut: cacheOptOut, setCacheOptOut: setCacheOptOut,
    cacheKey: cacheKey, itemIdentity: itemIdentity, leagueKeyspace: leagueKeyspace,
    loadMock: loadMock,
    STATUS_LABEL: STATUS_LABEL, STATUS_ORDER: STATUS_ORDER, GROUPS: GROUPS,
    TIER_LABEL: TIER_LABEL, TIER_ORDER: TIER_ORDER
  };
  if (typeof window !== "undefined") window.bpc = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;   // node unit tests
})();
