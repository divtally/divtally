/* bpc core.js — shared engine for every UI version.
 *
 * Owns ALL backend/state logic so each version is a pure VIEW. Talks to the same
 * /api/* endpoints the classic UI uses. Views subscribe to events and call methods;
 * they never fetch the API directly.
 *
 *   bpc.init()                       -> load prefs, fetch leagues + recent builds
 *   bpc.startUrl(text)               -> price a poe.ninja link / PoB code / pobb.in link
 *   bpc.startCache(key)              -> reload a cached build (from the recent list)
 *   bpc.setControl(name,val)         -> 'status'|'league'|'advanced'|'refresh' (auto re-runs)
 *   bpc.setEnabled(key,on) / setGroupEnabled(group,on)   -> include/exclude in totals
 *   bpc.totals()                     -> {min,median,high,included,priced}
 *   bpc.priceHTML(ex) / price(ex) / curImg(kind)         -> currency formatting (with orb icons)
 *   advanced rares: bpc.rareList(), openRare(k), reopenRare(k), backRare(), submitRare(k,payload), skipRare(k)
 *   bpc.loadMock(snapshot)           -> render a full build with NO backend (testing/demo)
 *
 * Events (bpc.on(name, cb); '*' for all):
 *   'phase'   (idle|loading|queued|running|done|error)
 *   'state'   (whole state object — fired on every poll tick / change)
 *   'meta'    (character/league/divine rate/pob — fired once when it lands)
 *   'items'   (the item skeleton — fired once when it lands)
 *   'priced'  ({keys:[changed], state}) — one or more rows got/changed a price
 *   'totals'  ({min,median,high,included,priced})
 *   'progress'(string)
 *   'recent'  ([builds]) / 'leagues' ([names]) / 'control' ({name,value})
 *   'rare'    ({key,rare,index,total,redo} | null) — advanced: show/close a picker
 *   'done'    (state) / 'error' (message)
 */
(function () {
  "use strict";
  var API = { price: "/api/price", job: "/api/job", rare: "/api/rare", cache: "/api/cache", leagues: "/api/leagues" };

  var STATUS_LABEL = {
    available: "Instant Buyout and In Person", securable: "Instant Buyout",
    onlineleague: "In Person (Online in League)", online: "In Person (Online)", any: "Any"
  };
  var STATUS_ORDER = ["available", "securable", "onlineleague", "online", "any"];
  var TIER_LABEL = { min: "min (budget)", median: "median (typical)", high: "high (~90th pct)" };
  var TIER_ORDER = ["min", "median", "high"];
  var GROUPS = [["equipment", "Equipment"], ["flask", "Flasks"], ["jewel", "Jewels"],
                ["gem", "Gems"]];

  function lsget(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsset(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

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
    phase: "idle", jobId: null, source: null,
    meta: null, items: [], priced: {}, rares: {}, searches: null,
    progress: "", error: null,
    advanced: true, status: "online", league: "", refresh: false,
    tier: "min",                       // which price tier the UI shows/totals by default
    enabled: {}, purchased: {}, leagues: [], recent: [],
    rareOrder: [], decided: new Set(), currentRare: null,
    fromSaved: false, savedTs: null,
    _sig: {}, _mock: false, _suppressAuto: false
  };
  var pollTimer = null;

  // ---- prefs ----
  function loadPrefs() {
    var a = lsget("bpc_advanced"); state.advanced = (a === null) ? true : (a === "1");
    var s = lsget("bpc_status"); if (s && STATUS_LABEL[s]) state.status = s;
    var l = lsget("bpc_league"); if (l !== null) state.league = l;
    var ti = lsget("bpc_tier"); if (ti && TIER_LABEL[ti]) state.tier = ti;
  }
  function setControl(name, value, opts) {
    opts = opts || {};
    if (name === "advanced") { state.advanced = !!value; lsset("bpc_advanced", value ? "1" : "0"); }
    else if (name === "status") { state.status = value; lsset("bpc_status", value); }
    else if (name === "league") { state.league = value; lsset("bpc_league", value); }
    else if (name === "refresh") { state.refresh = !!value; }
    else if (name === "tier") { state.tier = TIER_LABEL[value] ? value : "min"; lsset("bpc_tier", state.tier); }
    emit("control", { name: name, value: value });
    // 'tier' is display-only (all tiers are already computed) — never trigger a re-search.
    if (opts.rerun !== false && name !== "tier") rerun();
  }
  // current-tier chaos value of a priced row (null if unpriced)
  function tierEx(p) { return (p && p.chaos) ? p.chaos[state.tier] : null; }

  // ---- currency formatting ----
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
  // structured: {empty} | {ex, exStr, div|null, divStr|null}
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

  // ---- totals + include/exclude ----
  function isPriced(it) { var p = state.priced[String(it.index)]; return !!(p && p.chaos.median != null); }
  // a skill granted by gear/passives (blank-gem) -- not bought, so default it OUT of the total
  function itemGranted(k) { var it = state.items.find(function (x) { return String(x.index) === String(k); }); return !!(it && it.granted); }
  // min/median/high are the REMAINING spend (included items not yet purchased); spent* is what
  // the user has already bought (included + purchased). With nothing purchased they're identical
  // to the old totals, so other UIs are unaffected.
  function totals() {
    var mn = 0, md = 0, hi = 0, sMn = 0, sMd = 0, sHi = 0, inc = 0, tot = 0, bought = 0;
    state.items.forEach(function (it) {
      var k = String(it.index), p = state.priced[k];
      if (!p || p.chaos.median == null) return;
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
  // ---- purchase tracking (persisted per build so it survives reloads) ----
  function purchaseLSKey() {
    var ck = (state.meta && state.meta.cache_key) || "";
    if (!ck) return "";
    // Drop the snapshot-version segment so purchases persist across reloads AND across new
    // poe.ninja snapshots of the same character:
    // poeninja:char:<version>:<account>:<character> -> bpc_purchased:<account>:<character>
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
      // "enable all" still leaves gear/passive-granted skills OUT (they aren't bought); a
      // disable-all turns everything off. Non-gem items have no `granted` flag (-> included).
      if (state.priced[k] && state.priced[k].chaos.median != null) state.enabled[k] = on ? !it.granted : false;
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

  // ---- job lifecycle ----
  function resetJob() {
    if (state.currentRare != null) emit("rare", null);   // close any open picker on the OLD job
    state.jobId = null; state.meta = null; state.items = []; state.priced = {}; state.rares = {};
    state.searches = null; state.progress = ""; state.error = null; state.enabled = {}; state.purchased = {};
    state.rareOrder = []; state.decided = new Set(); state.currentRare = null; state._sig = {};
    state.fromSaved = false; state.savedTs = null;
  }
  function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
  function fail(msg) { stopPoll(); state.phase = "error"; state.error = msg; emit("error", msg); emit("phase", "error"); emit("state", state); }

  function start(source, opts) {
    opts = opts || {};
    if (source && (source.url || source.cache_key)) state.source = source;
    stopPoll(); state._mock = false; resetJob();
    state.phase = "loading"; emit("phase", "loading"); emit("state", state);
    var body = { league: state.league, refresh: !!state.refresh, advanced: state.advanced, status: state.status };
    if (state.refresh) { state.refresh = false; emit("control", { name: "refresh", value: false }); }  // one-shot, not sticky
    if (opts.research) body.research = true;       // force a fresh search (ignore saved result)
    if (source) { if (source.url) body.url = source.url; if (source.cache_key) body.cache_key = source.cache_key; }
    fetch(API.price, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) return fail((res.j && res.j.error) || "Request failed.");
        state.jobId = res.j.job_id; poll();
      })
      .catch(function () { fail("Could not reach the local server."); });
  }
  function startUrl(url) { if (url && url.trim()) start({ url: url.trim() }); }
  function startCache(key) { start({ cache_key: key }); }
  // control changes re-search (new params); plain loads use the saved result if present
  function rerun() { if (!state._mock && state.source && (state.source.url || state.source.cache_key)) start(state.source, { research: true }); }
  function researchAll() { if (state.source && (state.source.url || state.source.cache_key)) start(state.source, { research: true }); }

  function poll() {
    stopPoll();
    pollTimer = setInterval(function () {
      fetch(API.job + "?id=" + encodeURIComponent(state.jobId))
        .then(function (r) { if (!r.ok) throw 0; return r.json(); })
        .then(ingest)
        .catch(function () {/* transient; keep polling */});
    }, 1000);
  }

  function sigOf(p) { return p.method + "|" + p.chaos.min + "|" + p.chaos.median + "|" + p.chaos.high + "|" + p.note + "|" + p.trade_url; }

  function ingest(j) {
    if (j.state === "error") { state.phase = "error"; state.error = j.error || "error"; emit("error", state.error); emit("phase", "error"); emit("state", state); stopPoll(); return; }
    var firstMeta = !state.meta && j.meta;
    var firstItems = (!state.items || !state.items.length) && j.items && j.items.length;
    if (j.meta) state.meta = j.meta;
    if (j.items && j.items.length) state.items = j.items;
    if (j.rares) state.rares = j.rares;
    if (j.searches != null) state.searches = j.searches;
    state.fromSaved = !!j.from_saved; state.savedTs = j.saved_ts || null;
    state.progress = (j.progress && j.progress.length) ? j.progress[j.progress.length - 1] : state.progress;

    var changed = [], np = j.priced || {};
    Object.keys(np).forEach(function (k) {
      var sig = sigOf(np[k]);
      if (state._sig[k] === sig) return;
      state._sig[k] = sig; state.priced[k] = np[k]; changed.push(k);
      // auto-include priced items, EXCEPT skills granted by gear/passives (not bought)
      if (np[k].chaos.median != null && !(k in state.enabled)) state.enabled[k] = !itemGranted(k);
    });

    if (firstMeta) { loadPurchased(); emit("meta", state.meta); }
    if (firstItems) { buildRareOrder(); emit("items", state.items); }
    if (changed.length) emit("priced", { keys: changed, state: state });
    emit("progress", state.progress);
    emit("totals", totals());
    state.phase = j.state; emit("state", state);

    if (state.advanced && !state._suppressAuto) presentNext();
    if (j.state === "done" && state.currentRare == null) { stopPoll(); emit("done", state); }
  }

  // ---- advanced rare flow ----
  function buildRareOrder() { state.rareOrder = state.items.filter(function (it) { return it.category === "rare"; }).map(function (it) { return String(it.index); }); }
  function rareList() {
    return state.rareOrder.map(function (k) {
      return { key: k, rare: state.rares[k], priced: state.priced[k], decided: state.decided.has(k) };
    });
  }
  function presentNext() {
    if (state.currentRare != null) return;
    for (var i = 0; i < state.rareOrder.length; i++) {
      var k = state.rareOrder[i], r = state.rares[k];
      var priced = state.priced[k] && state.priced[k].chaos.median != null;
      // only prompt for rares that genuinely need a choice — never for ones already priced
      // (e.g. a build loaded from its saved result shows up "priced", not "awaiting").
      if (!state.decided.has(k) && r && r.status === "awaiting" && !priced) { openRare(k); return; }
    }
  }
  function openRare(k) {
    k = String(k);
    if (!state.rares[k]) { state.decided.add(k); presentNext(); return; }
    state.currentRare = k;
    var idx = state.rareOrder.indexOf(k);
    var single = idx < 0;   // not in the rare walkthrough (e.g. a unique opened via "edit affixes")
    emit("rare", { key: k, rare: state.rares[k], index: single ? 0 : idx,
                   total: single ? 1 : state.rareOrder.length,
                   redo: state.decided.has(k), single: single });
  }
  function reopenRare(k) {            // "edit affixes" — works after done; resumes polling
    k = String(k);
    if (!state._mock && !pollTimer && state.jobId) poll();
    openRare(k);
  }
  function backRare() {
    var i = state.currentRare != null ? state.rareOrder.indexOf(state.currentRare) : -1;
    if (i > 0) openRare(state.rareOrder[i - 1]);
  }
  function submitRare(k, payload) {
    k = String(k); payload = payload || {};
    state.decided.add(k); state.currentRare = null; emit("rare", null);
    if (state._mock) { mockPriceRare(k, payload); }
    else {
      if (state._sig) delete state._sig[k];            // allow row re-render with the new price
      fetch(API.rare + "?id=" + encodeURIComponent(state.jobId) + "&index=" + encodeURIComponent(k),
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).catch(function () {});
      if (!pollTimer && state.jobId) poll();
    }
    if (state.advanced && !state._suppressAuto) presentNext();
  }
  function skipRare(k) {
    k = String(k);
    state.priced[k] = { chaos: { min: null, median: null, high: null }, confidence: "none", note: "skipped (not priced)", method: "skipped", trade_url: "", sample_size: 0, total_found: 0 };
    state._sig[k] = sigOf(state.priced[k]);
    emit("priced", { keys: [k], state: state }); emit("totals", totals());
    submitRare(k, { skip: true });
  }
  // the default search for a rare: every searchable affix at its rolled value (pseudo-
  // combined when it has resistances) — i.e. what "Search" submits with no edits.
  function defaultRarePayload(k) {
    var r = state.rares[String(k)]; if (!r) return { filters: [], equip: [] };
    var usePseudo = !!(r.pseudo && r.pseudo.length);
    var filters = [], equip = [];
    // `prefer` (set by the backend) marks the default-checked affixes: every searchable affix
    // for rares, only the build-defining skill-level rolls for uniques. Fall back to
    // `searchable` for older payloads that don't carry `prefer`.
    function want(a) { return a.prefer !== undefined ? !!a.prefer : !!a.searchable; }
    function statF(a) { return a.negated ? { stat_id: a.stat_id, min: null, max: a.value }
                                          : { stat_id: a.stat_id, min: a.value, max: null }; }
    (r.affixes || []).forEach(function (a) {
      if (!a.searchable || !want(a)) return;
      if (usePseudo && a.resist) return;          // covered by the pseudo total
      if (a.kind === "equip") equip.push({ key: a.key, min: a.value, max: null });
      else filters.push(statF(a));
    });
    if (usePseudo) (r.pseudo || []).forEach(function (p) { if (p.searchable && want(p)) filters.push(statF(p)); });
    return { filters: filters, equip: equip };
  }
  function remainingRares() { return state.rareOrder.filter(function (k) { return !state.decided.has(k); }); }
  // bulk actions for impatient users: decide every remaining rare at once.
  function searchAllRares() {
    state._suppressAuto = true; state.currentRare = null; emit("rare", null);
    remainingRares().forEach(function (k) { if (state.rares[k]) submitRare(k, defaultRarePayload(k)); });
    state._suppressAuto = false; presentNext();
  }
  function skipAllRares() {
    state._suppressAuto = true; state.currentRare = null; emit("rare", null);
    remainingRares().forEach(function (k) { skipRare(k); });
    state._suppressAuto = false; presentNext();
  }

  // ---- side data ----
  function refreshRecent() {
    return fetch(API.cache).then(function (r) { return r.ok ? r.json() : { builds: [] }; })
      .then(function (d) { state.recent = d.builds || []; emit("recent", state.recent); }).catch(function () {});
  }
  function refreshLeagues() {
    return fetch(API.leagues).then(function (r) { return r.ok ? r.json() : { leagues: [] }; })
      .then(function (d) { state.leagues = d.leagues || []; emit("leagues", state.leagues); }).catch(function () {});
  }

  // ---- mock / demo (render a full build with NO backend) ----
  function loadMock(snapshot) {
    stopPoll(); state._mock = true; state.source = { mock: true }; state._suppressAuto = true;
    resetJob(); state.jobId = "mock";
    var j = snapshot || window.BPC_SAMPLE;
    if (!j) { console.warn("[bpc] loadMock: no sample available"); return; }
    var clone = JSON.parse(JSON.stringify(j));
    if (clone.advanced != null) state.advanced = clone.advanced;
    ingest(clone);
    state.rareOrder.forEach(function (k) { state.decided.add(k); });   // treat mock as "all decided"
    state.phase = clone.state || "done"; emit("state", state);
    if (state.phase === "done") emit("done", state);
  }
  function mockPriceRare(k, payload) {
    if (payload && payload.skip) return;
    state.priced[k] = { chaos: { min: 12, median: 34, high: 88 }, confidence: "medium", note: "(demo) re-priced", method: "rare_custom", trade_url: "https://www.pathofexile.com/trade", sample_size: 14, total_found: 120 };
    state._sig[k] = sigOf(state.priced[k]);
    emit("priced", { keys: [k], state: state }); emit("totals", totals());
  }

  // ---- init ----
  function init(opts) {
    opts = opts || {}; loadPrefs();
    if (opts.mock) { loadMock(opts.mock === true ? null : opts.mock); return api; }
    refreshLeagues(); refreshRecent(); return api;
  }

  var api = {
    on: on, off: off, state: state, init: init,
    start: start, startUrl: startUrl, startCache: startCache, rerun: rerun, researchAll: researchAll, setControl: setControl, loadPrefs: loadPrefs,
    price: price, priceHTML: priceHTML, curImg: curImg, nfmt: nfmt, esc: esc, divRate: divRate, tierEx: tierEx,
    totals: totals, setEnabled: setEnabled, setGroupEnabled: setGroupEnabled, isPriced: isPriced, itemsByGroup: itemsByGroup,
    setPurchased: setPurchased, isPurchased: isPurchased,
    rareList: rareList, openRare: openRare, reopenRare: reopenRare, backRare: backRare, submitRare: submitRare, skipRare: skipRare, presentNext: presentNext,
    defaultRarePayload: defaultRarePayload, remainingRares: remainingRares, searchAllRares: searchAllRares, skipAllRares: skipAllRares,
    refreshRecent: refreshRecent, refreshLeagues: refreshLeagues, loadMock: loadMock,
    STATUS_LABEL: STATUS_LABEL, STATUS_ORDER: STATUS_ORDER, GROUPS: GROUPS,
    TIER_LABEL: TIER_LABEL, TIER_ORDER: TIER_ORDER
  };
  window.bpc = api;
})();
