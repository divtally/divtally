/*
 * Offline event-flow tests for the v1.1 live-scan-status protocol (site side).
 *   node test_scanstatus.mjs
 *
 * No browser, no network, no pathofexile.com. Loads assets/core.js into a Node `vm`
 * context with a fake window (a postMessage bus), then plays the role of the Trade
 * Bridge extension so we can drive a full autoscan end-to-end and assert:
 *   - protocolVersion:1.1 is sent on every price message
 *   - the D-0012 chunking (3/msg, sequential) still holds
 *   - per-item progress (queued/searching/fetching/waiting/done/nobuyout/error) lands
 *     in the "scanstatus" event with correct order/ahead/current/done bookkeeping
 *   - final prices auto-apply from price-result, and failures are self-describing
 *     (the owner's "no buyout among N listings" + debug fields)
 *   - an OLD extension (no progress, no debug, ignores protocolVersion) still works:
 *     rows sit at generic "scanning" then resolve from the chunk reply. The UI never
 *     DEPENDS on v1.1 events.
 * Also compile-checks the index.html inline <script> (parse only).
 */
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE_SRC = fs.readFileSync(join(HERE, "assets", "core.js"), "utf8");

let passed = 0, failed = 0;
function ok(cond, msg) { if (cond) { passed++; } else { failed++; console.error("  FAIL:", msg); } }
function eq(a, b, msg) { ok(JSON.stringify(a) === JSON.stringify(b), `${msg} (got ${JSON.stringify(a)}, want ${JSON.stringify(b)})`); }
const tick = () => new Promise((r) => setTimeout(r, 1));
async function ticks(n) { for (let i = 0; i < n; i++) await tick(); }

// --- a fresh core.js instance in its own realm, plus a fake-extension message bus ---
function makeInstance(extMode, outcomes) {
  const listeners = [];
  const lsMap = new Map();
  const win = {
    BPC_CONFIG: { API_BASE: "", WORKER_BASE: "" },              // cache disabled -> no crypto/fetch needed
    location: { search: "", origin: "https://test.local", href: "https://test.local/" },
    addEventListener(type, cb) { if (type === "message") listeners.push(cb); },
    removeEventListener(type, cb) { const i = listeners.indexOf(cb); if (i >= 0) listeners.splice(i, 1); },
    postMessage(msg) {
      setTimeout(() => { const ev = { source: win, data: msg };
        listeners.slice().forEach((cb) => { try { cb(ev); } catch (e) { console.error("listener err", e); } }); }, 0);
    },
  };
  win.window = win;
  const localStorage = {
    getItem: (k) => (lsMap.has(k) ? lsMap.get(k) : null),
    setItem: (k, v) => lsMap.set(k, String(v)),
    removeItem: (k) => lsMap.delete(k),
  };
  const sandbox = { window: win, self: win, console, setTimeout, clearTimeout, TextEncoder, URLSearchParams,
                    localStorage, crypto: {}, Date, Math, JSON };
  vm.runInNewContext(CORE_SRC, sandbox, { filename: "core.js" });
  const bpc = win.bpc;

  const sent = [];            // every bpc-page message the page posted (ping + price)
  const EXT_VERSION = "1.1.0";
  function toPage(msg) { win.postMessage(Object.assign({ source: "bpc-ext" }, msg)); }
  function prog(reqId, key, stage, detail) { toPage({ type: "price-progress", reqId, key, stage, detail: detail || null }); }

  // The fake content-script + background service worker (only present when extMode !== "absent").
  function extListener(ev) {
    const d = ev.data;
    if (!d || d.source !== "bpc-page") return;
    sent.push(d);
    if (d.type === "ping") { toPage({ type: "pong", reqId: d.reqId, version: EXT_VERSION }); return; }
    if (d.type === "price") {
      const pv = d.protocolVersion || 0;
      const results = [];
      let chain = Promise.resolve();
      (d.queries || []).forEach((q) => {
        const o = outcomes[q.key] || { total: 5, amount: 10, currency: "chaos",
                                       debug: { searchStatus: 200, fetchStatus: 200, fetched: 5, nulls: 0 } };
        chain = chain.then(async () => {
          if (extMode === "new" && pv >= 1.1) {
            prog(d.reqId, q.key, "queued", null); await tick();
            prog(d.reqId, q.key, "searching", null); await tick();
            if (o.waitMs) { prog(d.reqId, q.key, "waiting", { waitMs: o.waitMs }); await tick(); }
            prog(d.reqId, q.key, "fetching", null); await tick();
            if (o.error) prog(d.reqId, q.key, "error", { message: o.error, status: o.debug && o.debug.searchStatus });
            else if (o.amount == null) prog(d.reqId, q.key, "nobuyout", { total: o.total, fetched: o.debug && o.debug.fetched, nulls: o.debug && o.debug.nulls });
            else prog(d.reqId, q.key, "done", { total: o.total, amount: o.amount, currency: o.currency });
          } else {
            await tick();       // old extension: silent while it works
          }
          // the final per-item result (price-result). Old ext omits `debug`.
          const base = o.error ? { key: q.key, error: o.error }
                               : { key: q.key, total: o.total, amount: o.amount, currency: o.currency, listingId: "x" };
          if (extMode === "new" && o.debug) base.debug = o.debug;
          results.push(base);
        });
      });
      chain.then(() => { toPage({ type: "price-result", reqId: d.reqId, results }); });
    }
  }
  if (extMode !== "absent") win.addEventListener("message", extListener);

  const snaps = [];
  bpc.on("scanstatus", (s) => snaps.push(JSON.parse(JSON.stringify(s))));
  return { bpc, win, sent, snaps };
}

const SAMPLE = {
  meta: { league: "Testleague", character: "Tester", divine_to_chaos: 100 },
  items: [
    { index: 1, group: "equipment", slot: "Helmet", category: "rare", name: "Alpha Crown",  trade_query: { query: { status: { option: "online" }, type: "Helm"  } } },
    { index: 2, group: "equipment", slot: "Gloves", category: "rare", name: "Beta Grip",    trade_query: { query: { status: { option: "online" }, type: "Glove" } } },
    { index: 3, group: "equipment", slot: "Boots",  category: "rare", name: "Gamma Tread",  trade_query: { query: { status: { option: "online" }, type: "Boot"  } } },
    { index: 4, group: "equipment", slot: "Belt",   category: "rare", name: "Delta Sash",   trade_query: { query: { status: { option: "online" }, type: "Belt"  } } },
  ],
  priced: {
    1: { chaos: { min: null, median: null, high: null }, method: "none", note: "" },
    2: { chaos: { min: null, median: null, high: null }, method: "none", note: "" },
    3: { chaos: { min: null, median: null, high: null }, method: "none", note: "" },
    4: { chaos: { min: null, median: null, high: null }, method: "none", note: "" },
  },
};
// key 1 -> priced OK; 2 -> nobuyout (the owner's mystery, w/ debug); 3 -> hits a rate-limit wait then prices; 4 -> HTTP error.
const OUTCOMES = {
  1: { total: 7,  amount: 25,  currency: "chaos",  debug: { searchStatus: 200, fetchStatus: 200, fetched: 7, nulls: 0 } },
  2: { total: 8,  amount: null, currency: null,    debug: { searchStatus: 200, fetchStatus: 200, fetched: 8, nulls: 8 } },
  3: { total: 3,  amount: 2,   currency: "divine", waitMs: 4000, debug: { searchStatus: 200, fetchStatus: 200, fetched: 3, nulls: 0 } },
  4: { error: "HTTP 403 from trade API", debug: { searchStatus: 403, fetchStatus: null, fetched: null, nulls: null } },
};

// --- F1 (R2): variant-unique poe.ninja placeholders + a 0-match exact search ---------------------
// Reproduces the load-time state the drive reports found (Build 3/4): a variant unique gets a
// poe.ninja NAME-LEVEL placeholder that is COUNTED, then its exact locked-mod search returns
// total_found=0. Per Locked D-0019 ("floor is a PLACEHOLDER, not its price"; "unmatchable ->
// link + no number") the placeholder must drop to link-only, exactly like a 0-match rare.
const SAMPLE_VU = {
  meta: { league: "Testleague", character: "Tester", divine_to_chaos: 100 },
  items: [
    // variant unique, poe.ninja placeholder, whose exact search 0-matches (Build 4's Watcher's Eye)
    { index: 10, group: "equipment", slot: "Ring", category: "unique", name: "Watcher's Eye", variant: true,
      trade_query: { query: { status: { option: "online" }, type: "Prismatic Jewel" } } },
    // variant unique whose exact search SUCCEEDS -> the real price must REPLACE the placeholder
    { index: 11, group: "jewels", slot: "Jewel", category: "unique", name: "Forbidden Flame", variant: true,
      trade_query: { query: { status: { option: "online" }, type: "Crimson Jewel" } } },
    // a genuine rare that 0-matches -> the existing link-only control (no placeholder to begin with)
    { index: 12, group: "equipment", slot: "Amulet", category: "rare", name: "Rare Pendant",
      trade_query: { query: { status: { option: "online" }, type: "Amulet" } } },
    // variant unique already carrying a REAL (cache) price -> a failed re-scan must NOT clobber it
    { index: 13, group: "equipment", slot: "Boots", category: "unique", name: "Bubonic Trail", variant: true,
      trade_query: { query: { status: { option: "online" }, type: "Boots" } } },
  ],
  priced: {
    10: { chaos: { min: 40, median: 55, high: 70 }, method: "unique-ninja-floor",   source: "poe.ninja", note: "poe.ninja floor" },
    11: { chaos: { min: 5,  median: 5,  high: 5  }, method: "unique-ninja-variant", source: "poe.ninja", note: "poe.ninja variant" },
    12: { chaos: { min: null, median: null, high: null }, method: "none", note: "" },
    13: { chaos: { min: 280, median: 300, high: 320 }, method: "cache", source: "cache", note: "community price" },
  },
};
const OUTCOMES_VU = {
  10: { total: 0,  amount: null, currency: null,    debug: { searchStatus: 200, fetchStatus: 200, fetched: 0,  nulls: 0 } },  // exact search: 0 matches
  11: { total: 12, amount: 8,    currency: "chaos", debug: { searchStatus: 200, fetchStatus: 200, fetched: 12, nulls: 0 } },  // real price
  12: { total: 0,  amount: null, currency: null,    debug: { searchStatus: 200, fetchStatus: 200, fetched: 0,  nulls: 0 } },  // genuine rare 0-match
  13: { total: 6,  amount: null, currency: null,    debug: { searchStatus: 200, fetchStatus: 200, fetched: 6,  nulls: 6 } },  // manual re-scan: no buyout
};

async function boot(inst) {
  inst.bpc.init();                 // registers the bridge listener + pings the (fake) extension
  await ticks(6);                  // let ping/pong settle so bridge activates
  inst.bpc.loadMock(SAMPLE);       // render a build with 4 unpriced rares, no backend
  await tick();
}

async function scenarioNew() {
  console.log("· scenario: NEW extension (emits v1.1 progress)");
  const inst = makeInstance("new", OUTCOMES);
  const { bpc, sent, snaps } = inst;
  await boot(inst);
  ok(bpc.state.bridge.active === true, "bridge activates from pong");
  eq(bpc.manualRows().filter((r) => !r.priced).length, 4, "4 unpriced rares to scan");

  await bpc.autoscan();
  await ticks(3);

  // --- protocol + chunking (D-0012 preserved) ---
  const priceMsgs = sent.filter((m) => m.type === "price");
  eq(priceMsgs.length, 2, "4 rares sent as 2 chunks (CHUNK=3, sequential)");
  ok(priceMsgs.every((m) => m.protocolVersion === 1.1), "every price message carries protocolVersion 1.1");
  eq(priceMsgs.map((m) => m.queries.length), [3, 1], "chunk sizes are 3 then 1");

  // --- intermediate stages were observed ---
  const stagesSeen = new Set();
  snaps.forEach((s) => Object.values(s.status).forEach((st) => stagesSeen.add(st.stage)));
  ["queued", "searching", "fetching", "waiting", "done", "nobuyout", "error"].forEach((stg) =>
    ok(stagesSeen.has(stg), `stage "${stg}" appeared during the scan`));

  // a queued row reported "N ahead" while an earlier row was active
  const sawAhead = snaps.some((s) => Object.values(s.status).some((st) => st.stage === "queued" && st.ahead > 0));
  ok(sawAhead, "a queued row reported ahead>0 (waiting behind earlier rows)");
  // the waiting row carried a waitUntil (drives the countdown chip)
  const sawWaitUntil = snaps.some((s) => s.status["3"] && s.status["3"].stage === "waiting" && s.status["3"].waitUntil);
  ok(sawWaitUntil, "the rate-limited row carried a waitUntil timestamp");

  // --- final scanstatus: everything resolved, bar full, inactive ---
  const last = snaps[snaps.length - 1];
  eq(last.active, false, "scan ends inactive");
  eq(last.total, 4, "final total = 4");
  eq(last.done, 4, "final done = 4 (bar reaches 100%)");
  eq(last.status["1"].stage, "done", "row 1 resolved done");
  eq(last.status["2"].stage, "nobuyout", "row 2 resolved nobuyout");
  eq(last.status["3"].stage, "done", "row 3 resolved done after the wait");
  eq(last.status["4"].stage, "error", "row 4 resolved error");

  // --- prices auto-applied from price-result (final results, single source of truth) ---
  const P = bpc.state.priced;
  eq(P["1"].chaos.median, 25, "row 1 priced 25c into the total");
  eq(P["3"].chaos.median, 200, "row 3 priced 2 div = 200c");
  ok(P["2"].chaos.median == null, "row 2 stays unpriced (no buyout)");
  ok(/none had a buyout/.test(P["2"].note) && /8 fetched/.test(P["2"].note) && /8 w\/o buyout/.test(P["2"].note),
     "row 2 note is self-describing with debug fields: " + P["2"].note);
  eq(P["2"].debug, OUTCOMES[2].debug, "row 2 keeps the raw debug object for the tooltip");
  ok(/HTTP 403/.test(P["4"].note), "row 4 note carries the real HTTP error: " + P["4"].note);

  // --- included totals reflect the two successes only ---
  ok(bpc.state.enabled["1"] && bpc.state.enabled["3"], "priced rows auto-included");
  ok(!bpc.state.enabled["2"] && !bpc.state.enabled["4"], "failed rows not included");
}

async function scenarioOld() {
  console.log("· scenario: OLD extension (no progress, no debug, ignores protocolVersion)");
  const inst = makeInstance("old", OUTCOMES);
  const { bpc, sent, snaps } = inst;
  await boot(inst);
  ok(bpc.state.bridge.active === true, "bridge activates from pong");

  await bpc.autoscan();
  await ticks(3);

  // page still sends protocolVersion 1.1; the extension simply never emits progress
  const priceMsgs = sent.filter((m) => m.type === "price");
  ok(priceMsgs.every((m) => m.protocolVersion === 1.1), "page still sends protocolVersion 1.1 to an old ext");

  // NO precise stages ever arrived — rows only ever sat at generic "scanning" before resolving
  const stagesSeen = new Set();
  snaps.forEach((s) => Object.values(s.status).forEach((st) => stagesSeen.add(st.stage)));
  ok(!stagesSeen.has("searching") && !stagesSeen.has("fetching") && !stagesSeen.has("waiting"),
     "no v1.1 progress stages with an old extension");
  ok(stagesSeen.has("scanning"), 'rows showed the generic "scanning" chip while the chunk was in flight');

  // …yet the scan still completes and prices still auto-apply from the chunk reply
  const last = snaps[snaps.length - 1];
  eq(last.active, false, "scan ends inactive (old ext)");
  eq(last.done, 4, "all 4 rows resolved from price-result (old ext)");
  eq(bpc.state.priced["1"].chaos.median, 25, "row 1 priced even without progress events");
  eq(bpc.state.priced["3"].chaos.median, 200, "row 3 priced even without progress events");
  ok(/none had a buyout/.test(bpc.state.priced["2"].note), "row 2 nobuyout still surfaced (old ext, no debug tail)");
  ok(bpc.state.priced["2"].note.indexOf("[") === -1, "old-ext nobuyout note has no debug bracket (no debug supplied)");
  ok(/HTTP 403/.test(bpc.state.priced["4"].note), "row 4 error still surfaced (old ext)");
}

async function scenarioSingle() {
  console.log("· scenario: single-row scan resolves + a fresh build resets the session");
  const inst = makeInstance("new", OUTCOMES);
  const { bpc, snaps } = inst;
  await boot(inst);
  await bpc.priceViaExtension("1");
  await ticks(3);
  eq(bpc.state.priced["1"].chaos.median, 25, "single-row scan priced row 1");
  const afterFirst = snaps[snaps.length - 1];
  eq(afterFirst.total, 1, "single-row scan tracked exactly 1 item");
  eq(afterFirst.active, false, "single-row scan ended");
  // a brand-new build clears the stale scan session (reset())
  bpc.loadMock(SAMPLE);
  await tick();
  const fresh = bpc.scanStatus();
  eq(fresh.total, 0, "loading a new build clears the scan session");
  eq(fresh.active, false, "fresh build has no active scan");
}

async function scenarioVariantPlaceholder() {
  console.log("· scenario: F1 — a 0-match variant unique drops its poe.ninja placeholder to link-only");
  const inst = makeInstance("new", OUTCOMES_VU);
  const { bpc } = inst;
  bpc.init();
  await ticks(6);
  bpc.loadMock(SAMPLE_VU);
  await tick();

  // load-time state reproduces the F1 setup: BOTH variant-unique placeholders are counted at their
  // stale ninja numbers (this is exactly the state Build 3/4 were in before their scans ran).
  ok(bpc.state.enabled["10"] === true, "load: Watcher's Eye placeholder is enabled (counted)");
  ok(bpc.state.enabled["11"] === true, "load: Forbidden Flame placeholder is enabled (counted)");
  eq(bpc.totals().included, 3, "load: 3 rows counted (10 + 11 placeholders + 13 cache)");
  eq(bpc.totals().median, 55 + 5 + 300, "load: headline carries both placeholders + the cache price");

  // autoscan targets the two ninja placeholders (10,11) + the unpriced rare (12), NOT the cache row (13)
  const scanned = bpc.manualRows().filter((r) => bpc.needsScan(r)).map((r) => r.key).sort();
  eq(scanned, ["10", "11", "12"], "autoscan scans the two placeholders + the unpriced rare, not the cache-priced row");

  await bpc.autoscan();
  await ticks(4);

  const P = bpc.state.priced, E = bpc.state.enabled;

  // --- F1 CORE: the 0-match placeholder is GONE (no number) and no longer counted (link-only) ---
  ok(P["10"].chaos.median == null, "Watcher's Eye placeholder dropped: median null (no misleading number)");
  ok(!E["10"], "Watcher's Eye no longer enabled — out of the headline, like a 0-match rare");
  eq(P["10"].source, "trade", "Watcher's Eye went through the exact search (source now trade)");
  const sw = bpc.scanStatus().status["10"];
  eq(sw && sw.stage, "nobuyout", "Watcher's Eye reached a terminal stage (hands-free)");

  // --- a SUCCESSFUL exact search REPLACES the placeholder with the real price ---
  eq(P["11"].chaos.median, 8, "Forbidden Flame priced by exact search (real 8c replaces the 5c placeholder)");
  ok(E["11"], "Forbidden Flame stays included at its real price");

  // --- the genuine 0-match rare control still resolves to link-only ---
  ok(P["12"].chaos.median == null && !E["12"], "genuine 0-match rare stays link-only (control)");

  // --- the headline no longer contains the dropped 55c (the exact F1 arithmetic from Build 4) ---
  eq(bpc.totals().median, 8 + 300, "headline = real 8c + 300c cache; the 55c placeholder is GONE");
  eq(bpc.totals().included, 2, "only the two real prices are counted now");
  eq(bpc.totals().priced, 2, "the numberless placeholder is not even in the priced count");

  // --- scoping: a failed re-scan of a row with a REAL (cache) price must NOT clobber it ---
  await bpc.priceViaExtension("13");
  await ticks(3);
  eq(bpc.state.priced["13"].chaos.median, 300, "cache-priced variant unique keeps its 300c on a failed re-scan (not a ninja placeholder)");
  ok(bpc.state.enabled["13"], "cache-priced row stays included after a failed re-scan");
}

function checkInlineScript() {
  console.log("· compile-check: index.html inline <script>");
  const html = fs.readFileSync(join(HERE, "index.html"), "utf8");
  const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  const main = blocks.find((b) => b.includes("bpc.init("));
  ok(!!main, "found the index.html inline script");
  try { new vm.Script(main, { filename: "index-inline.js" }); ok(true, "index.html inline script parses"); }
  catch (e) { ok(false, "index.html inline script parse error: " + e.message); }
}

(async () => {
  checkInlineScript();
  await scenarioNew();
  await scenarioOld();
  await scenarioSingle();
  await scenarioVariantPlaceholder();
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
