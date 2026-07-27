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
  var API_BASE = trimSlash(qp("api") || CFG.API_BASE || "");
  var WORKER_BASE = trimSlash(qp("worker") || (CFG.WORKER_BASE === undefined ? "" : CFG.WORKER_BASE));
  var STUB = qp("stub");                 // ?stub[=path] -> fetch a local build document instead of the API
  var MAX_KEYS = CFG.CACHE_MAX_KEYS || 60;

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
    status: "online", league: "", refresh: false,
    tier: "min",
    enabled: {}, purchased: {}, leagues: [], recent: [],
    bridge: { active: false, version: null },
    _sig: {}, _mock: false
  };

  // ---- prefs ----
  function loadPrefs() {
    var s = lsget("bpc_status"); if (s && STATUS_LABEL[s]) state.status = s;
    var l = lsget("bpc_league"); if (l !== null) state.league = l;
    else if (CFG.DEFAULT_LEAGUE) state.league = CFG.DEFAULT_LEAGUE;
    var ti = lsget("bpc_tier"); if (ti && TIER_LABEL[ti]) state.tier = ti;
  }
  function setControl(name, value, opts) {
    opts = opts || {};
    if (name === "status") { state.status = value; lsset("bpc_status", value); }
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

    fetch(url, init || undefined)
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        var j = res.j || {};
        if (j.ok === false || (!res.ok && j.ok !== true)) return fail((j && j.error) || "The build could not be loaded.");
        loadBuild(j);
      })
      .catch(function () { fail("Could not reach the pricing service. Check your connection, or try ?mock for a demo."); });
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
      if (p.chaos && p.chaos.median != null) state.enabled[k] = !itemGranted(k);
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
      if (opts.include) state.enabled[key] = !itemGranted(key);
      else if (!(key in state.enabled)) state.enabled[key] = !itemGranted(key);
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
    function findFirst(re) { var m = t.match(re); return m ? { amount: m[1], cur: m[2] } : null; }
    // priority: the machine "listed for" phrase, then a ~b/o / ~price note, then any bare "N cur".
    var hit = findFirst(new RegExp("listed for\\s*" + AMT_RE + tail))
           || findFirst(new RegExp("~\\s*(?:b/?o|price)\\s*" + AMT_RE + tail))
           || findFirst(new RegExp(AMT_RE + tail));
    if (!hit) return null;
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
                      (it.category === "unique" && (p.method === "unique-unpriced" || p.source === "trade"));
      if (!priceable) return false;
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
          Object.keys(found || {}).forEach(function (ck) {
            var rowKey = byCacheKey[ck]; if (rowKey == null) return;
            var rec = found[ck]; if (!rec || !rec.chaos) return;
            if (rec.chaos.median == null && rec.chaos.min == null && rec.chaos.high == null) return;
            applyPrice(rowKey, {
              chaos: { min: num(rec.chaos.min), median: num(rec.chaos.median != null ? rec.chaos.median : rec.chaos.min), high: num(rec.chaos.high) },
              confidence: rec.confidence || "low", method: (rec.method || "cache"), source: "cache",
              note: "Community-submitted price — not verified by this site. Confirm via the trade link.",
              sample_size: rec.sample_size || 0, total_found: rec.total_found || 0,
              trade_url: rec.trade_url || undefined
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
                    resolved: resolved, ahead: unresolvedBefore };
      if (!resolved) unresolvedBefore++;      // ahead = # of unresolved rows earlier in SEND order
    });
    for (i = 0; i < order.length; i++) { if (SCAN_ACTIVE[status[order[i]].stage]) { current = order[i]; break; } }
    if (current == null) { for (i = 0; i < order.length; i++) { if (!status[order[i]].resolved) { current = order[i]; break; } } }
    return { active: scan.active, total: order.length, done: done, current: current,
             order: order, names: Object.assign({}, scan.names), status: status };
  }
  function scanEmit() { emit("scanstatus", scanSnapshot()); }
  function scanBegin(rows) {
    scanReset(); scan.active = true;
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
    s.stage = stage; s.detail = detail || null;
    s.waitUntil = (stage === "waiting" && detail && detail.waitMs) ? (Date.now() + detail.waitMs) : null;
    scanEmit();
  }
  function scanEnd() { if (!scan.active) return; scan.active = false; scanEmit(); }

  // Price one or more rows via the extension. Groups by league (one price message per league,
  // per the protocol — the extension prices the batch serially under its own limiter).
  function priceRowsViaExtension(rows) {
    if (!state.bridge.active) return Promise.resolve({ error: "no bridge" });
    var byLeague = {};
    rows.forEach(function (r) {
      var it = r.item, p = r.price;
      var tq = (p && p.trade_query) || it.trade_query;
      var q = tq && (tq.query || tq);            // pass the INNER query object, not the wrapper
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
      var toCache = [];
      var seen = {};
      if (b.resp && !b.resp.error) {
        (b.resp.results || []).forEach(function (res) {
          var key = String(res.key); seen[key] = true;
          var it = state.items.find(function (x) { return String(x.index) === key; });
          if (!it) return;
          var dbg = res.debug || null;      // v1.1: {searchStatus, fetchStatus, fetched, nulls} (absent on old ext)
          if (res.error) {
            applyPrice(key, { confidence: "none", method: "extension", source: "trade",
              note: "extension: " + res.error + debugSuffix(dbg), debug: dbg }, { include: false });
            scanSet(key, "error", { message: res.error, status: dbg && dbg.searchStatus });
            return;
          }
          if (res.amount == null) {
            applyPrice(key, { confidence: "none", method: "extension", source: "trade",
              note: "listings exist but none had a buyout price" + debugSuffix(dbg),
              total_found: res.total || 0, debug: dbg }, { include: false });
            scanSet(key, "nobuyout", { total: res.total || 0,
              fetched: dbg ? dbg.fetched : null, nulls: dbg ? dbg.nulls : null });
            return;
          }
          var chaos = toChaos(res.amount, res.currency);
          if (chaos == null) {
            applyPrice(key, { confidence: "low", method: "extension", source: "trade",
              note: "cheapest: " + fmtAmt(res.amount) + " " + res.currency + " (no chaos rate to convert)" + debugSuffix(dbg),
              total_found: res.total || 0, debug: dbg }, { include: false });
            scanSet(key, "nobuyout", { total: res.total || 0, amount: res.amount, currency: res.currency, norate: true });
            return;
          }
          applyPrice(key, {
            chaos: { min: chaos, median: chaos, high: chaos }, confidence: confFromTotal(res.total),
            method: "extension", source: "trade",
            note: "priced via extension — cheapest buyout of " + (res.total || 0) + " online listings",
            sample_size: 1, total_found: res.total || 0, debug: dbg
          }, { include: true });
          scanSet(key, "done", { total: res.total || 0, amount: res.amount, currency: res.currency });
          // POST this real, on-IP price to the shared cache (short TTL) for everyone else
          toCache.push({ item: it, value: {
            chaos: { min: chaos, median: chaos, high: chaos }, confidence: confFromTotal(res.total),
            method: "extension", sample_size: 1, total_found: res.total || 0,
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
        applyPrice(key, { confidence: "none", method: "extension", source: "trade",
          note: "extension: " + msg }, { include: false });
        scanSet(key, "error", { message: msg });
      });
      if (toCache.length) { cachedCount += toCache.length; cachePost(toCache); }
    }
    var idx = 0;
    function nextChunk() {
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
  function autoscan() { return priceRowsViaExtension(manualRows().filter(function (r) { return !r.priced; })); }
  function priceViaExtension(key) {
    var r = manualRows().find(function (x) { return x.key === String(key); });
    return r ? priceRowsViaExtension([r]) : Promise.resolve({ error: "no such row" });
  }
  // convert an extension/whisper amount+currency to chaos (chaos + divine only; else null)
  function toChaos(amount, currency) {
    if (amount == null) return null;
    var c = CUR_ALIAS[String(currency || "").toLowerCase()] || String(currency || "").toLowerCase();
    if (c === "chaos") return amount;
    if (c === "divine") return divRate() ? amount * divRate() : null;
    return null;
  }
  function confFromTotal(n) { n = n || 0; return n >= 5 ? "high" : n >= 2 ? "medium" : "low"; }

  // ---- recent builds (localStorage; the public site has no /api/cache) ----
  function loadRecent() {
    try { state.recent = JSON.parse(lsget("bpc_recent_builds") || "[]") || []; } catch (e) { state.recent = []; }
    emit("recent", state.recent);
  }
  function pushRecent(meta) {
    if (!meta) return;
    var url = meta.source_url && /^https?:\/\//i.test(meta.source_url) ? meta.source_url : (state.source && state.source.url) || "";
    if (!url) return;                                   // PoB imports have no shareable URL -> not saved
    var key = url;
    var entry = { key: key, url: url, character: meta.character || "Unknown", char_class: meta["class"] || "", level: meta.level || 0, ts: Date.now() };
    var list = (state.recent || []).filter(function (b) { return b.key !== key; });
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
      if (p.chaos.median != null) state.enabled[k] = !itemGranted(k);
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
    totals: totals, setEnabled: setEnabled, setGroupEnabled: setGroupEnabled, isPriced: isPriced, itemsByGroup: itemsByGroup,
    gemGroups: gemGroups, gemBreakdown: gemBreakdown, gemHost: gemHost,
    setPurchased: setPurchased, isPurchased: isPurchased,
    // public pricing
    parseWhisper: parseWhisper, applyWhisper: applyWhisper, clearManual: clearManual, manualRows: manualRows,
    autoscan: autoscan, priceViaExtension: priceViaExtension, scanStatus: scanSnapshot,
    cacheOptOut: cacheOptOut, setCacheOptOut: setCacheOptOut,
    cacheKey: cacheKey, itemIdentity: itemIdentity, leagueKeyspace: leagueKeyspace,
    loadMock: loadMock,
    STATUS_LABEL: STATUS_LABEL, STATUS_ORDER: STATUS_ORDER, GROUPS: GROUPS,
    TIER_LABEL: TIER_LABEL, TIER_ORDER: TIER_ORDER
  };
  if (typeof window !== "undefined") window.bpc = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;   // node unit tests
})();
