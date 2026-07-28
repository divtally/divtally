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

// ---- a core.js instance wired to a controllable fetch + AbortController (R4-4 build timeout,
//      R4S-1 build-load path). No extension bus needed; cache disabled (empty worker). ----
function makeNetInstance(opts) {
  opts = opts || {};
  const lsMap = new Map();
  const win = {
    BPC_CONFIG: { API_BASE: "https://api.test.local", WORKER_BASE: "",
                  BUILD_TIMEOUT_MS: opts.timeoutMs || 30 },
    location: { search: "", origin: "https://test.local", href: "https://test.local/" },
    addEventListener() {}, removeEventListener() {}, postMessage() {},
  };
  win.window = win;
  const localStorage = {
    getItem: (k) => (lsMap.has(k) ? lsMap.get(k) : null),
    setItem: (k, v) => lsMap.set(k, String(v)),
    removeItem: (k) => lsMap.delete(k),
  };
  class FakeAbortController {
    constructor() { this.signal = { aborted: false, addEventListener() {}, removeEventListener() {} }; }
    abort() { this.signal.aborted = true; }
  }
  const fetchImpl = opts.fetch || (() => new Promise(() => {}));
  const sandbox = { window: win, self: win, console, setTimeout, clearTimeout, TextEncoder, URLSearchParams,
                    localStorage, crypto: {}, Date, Math, JSON, fetch: fetchImpl,
                    AbortController: FakeAbortController };
  vm.runInNewContext(CORE_SRC, sandbox, { filename: "core.js" });
  return { bpc: win.bpc, win, lsMap, setLS: (k, v) => lsMap.set(k, v) };
}

async function scenarioBuildTimeout() {
  console.log("· scenario: R4-4 build fetch times out on an unresponsive API (never hangs)");
  // (a) a server that accepts the connection but NEVER replies -> the fetch promise never settles
  const inst = makeNetInstance({ fetch: () => new Promise(() => {}), timeoutMs: 20 });
  const { bpc } = inst;
  bpc.init();
  bpc.startUrl("https://poe.ninja/hung");
  eq(bpc.state.phase, "loading", "phase is 'loading' immediately after start()");
  await ticks(45);                        // exceed the 20ms bound
  eq(bpc.state.phase, "error", "R4-4: hung API resolves to 'error' (not stuck 'loading' forever)");
  ok(/took too long/i.test(bpc.state.error || ""),
     "R4-4: the error names the timeout, not a generic failure: " + bpc.state.error);
  // (b) positive control: a RESPONSIVE API still loads to 'done' (the wrapper didn't break happy path)
  const okDoc = { ok: true, meta: { character: "Ok" }, items: [], rares: {}, warnings: [] };
  const inst2 = makeNetInstance({
    timeoutMs: 5000,
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(okDoc) }),
  });
  inst2.bpc.init();
  inst2.bpc.startUrl("https://poe.ninja/ok");
  await ticks(6);
  eq(inst2.bpc.state.phase, "done", "responsive API still loads to 'done' (happy path intact)");
}

function scenarioWhisperSeparators() {
  console.log("· scenario: R4-5 whisper rejects ambiguous locale/thousands separators");
  const { bpc } = makeNetInstance({});
  const rate = 100;   // divine -> chaos
  // silently-wrong separator inputs must now REJECT (null), not fold a fragment into the headline
  ["1,000 chaos", "1 000 chaos", "1.000.000 chaos", "1'000 chaos", "35,5 chaos",
   "1 000 000 chaos", "12'345 chaos", "listed for 1,000 chaos"].forEach((s) =>
    ok(bpc.parseWhisper(s, rate) === null, `"${s}" rejected (was a silent wrong number)`));
  // legitimate inputs still parse (no over-rejection): [input, expected chaos]
  [["35 chaos", 35], ["1000 chaos", 1000], ["2.5 div", 250], ["35.5 chaos", 35.5],
   ["0.5 div", 50], ["1/3 div", 100 / 3], ["~b/o 1500 chaos", 1500], ["listed for 1000 chaos", 1000],
   ["10.25 chaos", 10.25], ["1.5 divine", 150]].forEach(([s, want]) => {
    const p = bpc.parseWhisper(s, rate);
    const got = p ? (p.chaos == null ? p.amount : p.chaos) : null;
    ok(p && Math.abs(got - want) < 1e-6, `"${s}" -> ${want} (got ${got})`);
  });
  // a GGG whisper carrying stash coords must not false-reject on the unrelated "left 12, top 3"
  const g = bpc.parseWhisper(
    'buy your Foo listed for 20 chaos in Standard (stash "~b/o 20 chaos"; position: left 12, top 3)', rate);
  ok(g && g.chaos === 20, "GGG whisper w/ coords still parses 20 chaos (no false reject): " + (g && g.chaos));
  ok(bpc.parseWhisper("no price here", rate) === null, "non-price text still returns null");
}

function scenarioRecentCoercion() {
  console.log("· scenario: R4S-1 corrupt bpc_recent_builds self-heals (wrong-type -> [])");
  // valid-JSON WRONG-TYPE values must heal to [] on read, like unparseable garbage already does
  ['"hello"', "42", '{"k":1}', "true", "}{ not json"].forEach((raw) => {
    const inst = makeNetInstance({});
    const { bpc } = inst;
    inst.setLS("bpc_recent_builds", raw);
    let ev, threw = false;
    bpc.on("recent", (r) => { ev = r; });
    try { bpc.init(); } catch (e) { threw = true; }
    ok(!threw, `init() does not throw on bpc_recent_builds=${raw}`);
    ok(Array.isArray(bpc.state.recent) && bpc.state.recent.length === 0, `state.recent heals to [] for ${raw}`);
    ok(Array.isArray(ev), `'recent' event carries an array for ${raw} (renderRecent-safe)`);
  });
  // a legitimate array is preserved untouched
  const inst2 = makeNetInstance({});
  inst2.setLS("bpc_recent_builds", JSON.stringify([{ key: "u", url: "u", character: "C" }]));
  inst2.bpc.init();
  eq(inst2.bpc.state.recent.length, 1, "a valid recents array is preserved");
  // pushRecent hardening: a wrong-type state.recent forced AFTER load (external mid-session
  // corruption) must NOT crash the build load into a false network error -- emit('done') still fires
  const okDoc = { ok: true, meta: { character: "Z", source_url: "https://poe.ninja/z" },
                  items: [], rares: {}, warnings: [] };
  const inst3 = makeNetInstance({
    timeoutMs: 5000,
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(okDoc) }),
  });
  inst3.bpc.init();
  inst3.bpc.state.recent = "hello";       // force wrong-type post-load
  return (async () => {
    inst3.bpc.startUrl("https://poe.ninja/z");
    await ticks(6);
    eq(inst3.bpc.state.phase, "done", "R4S-1: build load completes despite wrong-type state.recent");
    ok(Array.isArray(inst3.bpc.state.recent), "state.recent is an array after the guarded pushRecent");
  })();
}

// ==================================================================================================
//  R6-F1 (race lens) — the per-build generation token. Two live regressions of the MAJOR cluster:
//  F1a wrong-build render, F1b zombie-scan cross-build price fold + community-cache poisoning.
// ==================================================================================================

// A bridge instance whose FAKE extension HOLDS its reply until the test delivers it, wired to a fake
// SubtleCrypto + a fetch that CAPTURES cache POSTs — so we can prove a zombie scan neither folds onto
// the new build nor POSTs poisoned entries to the shared cache. Prod-looking origin (no ?query
// overrides), WORKER_BASE set so the community cache is enabled.
function makeBridgeInstance(opts) {
  opts = opts || {};
  const listeners = [], lsMap = new Map(), posts = [], sent = [];
  const win = {
    BPC_CONFIG: { API_BASE: "", WORKER_BASE: opts.worker || "https://worker.test/cache" },
    location: { search: "", origin: "https://divtally.com", href: "https://divtally.com/",
                hostname: "divtally.com", protocol: "https:" },
    addEventListener(type, cb) { if (type === "message") listeners.push(cb); },
    removeEventListener(type, cb) { const i = listeners.indexOf(cb); if (i >= 0) listeners.splice(i, 1); },
    postMessage(msg) { setTimeout(() => { const ev = { source: win, data: msg };
      listeners.slice().forEach((cb) => { try { cb(ev); } catch (e) {} }); }, 0); },
  };
  win.window = win;
  const localStorage = { getItem: (k) => (lsMap.has(k) ? lsMap.get(k) : null),
    setItem: (k, v) => lsMap.set(k, String(v)), removeItem: (k) => lsMap.delete(k) };
  // deterministic content-hash digest so cacheKey() resolves without WebCrypto (returns a 32-byte buffer)
  const crypto = { subtle: { digest: (algo, bytes) => {
    let h = 2166136261 >>> 0; for (let i = 0; i < bytes.length; i++) { h ^= bytes[i]; h = Math.imul(h, 16777619) >>> 0; }
    const out = new Uint8Array(32); for (let i = 0; i < 32; i++) out[i] = (h >>> ((i % 4) * 8)) & 0xff;
    return Promise.resolve(out.buffer);
  } } };
  const fetchImpl = (url, init) => {
    if (init && init.method === "POST") { posts.push({ url: String(url), body: JSON.parse(init.body) }); }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });   // GET cache read -> empty
  };
  const sandbox = { window: win, self: win, console, setTimeout, clearTimeout, TextEncoder, URLSearchParams,
                    localStorage, crypto, Date, Math, JSON, fetch: fetchImpl };
  vm.runInNewContext(CORE_SRC, sandbox, { filename: "core.js" });
  const bpc = win.bpc;
  function toPage(msg) { win.postMessage(Object.assign({ source: "bpc-ext" }, msg)); }
  // manual extension: activate the bridge on ping, capture price messages, HOLD price replies for the test
  win.addEventListener("message", (ev) => {
    const d = ev.data; if (!d || d.source !== "bpc-page") return;
    sent.push(d);
    if (d.type === "ping") toPage({ type: "pong", reqId: d.reqId, version: "1.2.0" });
  });
  return { bpc, win, sent, posts, deliver: (reqId, results) => toPage({ type: "price-result", reqId, results }) };
}

async function scenarioRaceBuildSwap() {
  console.log("· scenario: R6-F1a — appraise A (held) then B (fast) renders B, and a late A reply can't clobber it");
  let releaseA = null;
  const docA = { ok: true, meta: { character: "AAA", source_url: "https://poe.ninja/char/AAA", league: "Standard", divine_to_chaos: 100 },
    items: [ { index: 0, group: "equipment", slot: "Helmet", category: "unique", name: "A-Helm", price: { chaos: { min: 10, median: 10, high: 10 }, method: "unique", source: "poe.ninja" } },
             { index: 1, group: "equipment", slot: "Belt", category: "unique", name: "A-Belt", price: { chaos: { min: 20, median: 20, high: 20 }, method: "unique", source: "poe.ninja" } } ],
    rares: {}, warnings: [] };
  const docB = { ok: true, meta: { character: "BBB", source_url: "https://poe.ninja/char/BBB", league: "Standard", divine_to_chaos: 100 },
    items: [ { index: 0, group: "equipment", slot: "Helmet", category: "unique", name: "B-Helm", price: { chaos: { min: 99, median: 99, high: 99 }, method: "unique", source: "poe.ninja" } } ],
    rares: {}, warnings: [] };
  const fetchImpl = (url) => {
    const u = decodeURIComponent(String(url));
    if (u.indexOf("poe.ninja/char/AAA") >= 0) return new Promise((res) => { releaseA = () => res({ ok: true, json: () => Promise.resolve(docA) }); });
    return Promise.resolve({ ok: true, json: () => Promise.resolve(docB) });
  };
  const { bpc } = makeNetInstance({ fetch: fetchImpl, timeoutMs: 5000 });
  bpc.init();
  bpc.startUrl("https://poe.ninja/char/AAA");   // A's fetch is HELD (releaseA not called yet)
  bpc.startUrl("https://poe.ninja/char/BBB");   // B's fetch resolves immediately
  await ticks(6);
  eq(bpc.state.meta && bpc.state.meta.character, "BBB", "final render is B (the last build submitted)");
  eq(bpc.totals().priced, 1, "B's single item is counted (not A's two) — the render is B's document");
  ok(String(bpc.state.source.url).indexOf("BBB") >= 0, "state.source points at B (coherent with the visible build)");
  if (releaseA) releaseA();                      // release A LATE — the gen guard must drop it
  await ticks(6);
  eq(bpc.state.meta.character, "BBB", "F1a: the late build-A reply is dropped (gen guard) — B stays rendered");
  eq(bpc.totals().priced, 1, "F1a: still only B's one item counted — A did not fold in");
  ok(String(bpc.state.source.url).indexOf("BBB") >= 0, "F1a: state.source still coherent (points at B, not A)");
}

async function scenarioRaceZombieScan() {
  console.log("· scenario: R6-F1b — a held scan reply from build A can't fold onto build B or poison the shared cache");
  const inst = makeBridgeInstance({});
  const { bpc, sent, posts, deliver } = inst;
  bpc.init();
  await ticks(6);
  ok(bpc.state.bridge.active === true, "bridge activates from pong");

  // Build A: one unpriced rare at index 0 -> autoscan sends it; we HOLD the reply.
  const A = { meta: { league: "Allflame", character: "Azn", divine_to_chaos: 100 },
    items: [ { index: 0, group: "equipment", slot: "Belt", category: "rare", name: "A-Belt",
      trade_query: { query: { status: { option: "online" }, type: "Belt" } } } ],
    priced: { 0: { chaos: { min: null, median: null, high: null }, method: "none", note: "" } } };
  bpc.loadMock(A);
  await tick();
  const scanP = bpc.autoscan();                  // do NOT await — the fake ext holds the reply
  await ticks(3);
  const priceMsg = sent.find((m) => m.type === "price");
  ok(!!priceMsg, "A's autoscan sent a price message to the extension");
  const heldReqId = priceMsg.reqId;

  // Switch to Build B before A's reply lands. B carries a DIFFERENT item at the SAME positional index 0.
  const B = { meta: { league: "Allflame", character: "Bex", divine_to_chaos: 100 },
    items: [ { index: 0, group: "equipment", slot: "Belt", category: "unique", name: "Headhunter",
      mods: { implicit: [], explicit: ["+40 to all Attributes"] },
      price: { chaos: { min: 14000, median: 14613, high: 15000 }, method: "unique", source: "poe.ninja" } } ],
    priced: { 0: { chaos: { min: 14000, median: 14613, high: 15000 }, method: "unique", source: "poe.ninja" } } };
  bpc.loadMock(B);
  await tick();
  eq(bpc.state.meta.character, "Bex", "build B is loaded");
  eq(bpc.state.priced["0"].chaos.median, 14613, "B's Headhunter shows its real 14613c before the zombie reply");
  const postsBefore = posts.length;

  // Deliver A's zombie reply (a fabricated 999c) against the still-pending reqId.
  deliver(heldReqId, [{ key: "0", total: 5, amount: 999, currency: "chaos", listingId: "x" }]);
  await ticks(4);
  await scanP;                                    // the superseded scan chain resolves harmlessly

  eq(bpc.state.priced["0"].chaos.median, 14613, "F1b: B's Headhunter price NOT folded to 999 (gen guard dropped the zombie fold)");
  eq(bpc.state.priced["0"].source, "poe.ninja", "F1b: B's row keeps its poe.ninja source (not overwritten by the zombie 'trade' fold)");
  eq(posts.length, postsBefore, "F1b: the zombie scan did NOT POST poisoned entries into the shared community cache");
}

// ==================================================================================================
//  R6-F3 (race lens) — the scan-entrypoint guard. A 2nd scan fired from ANY entrypoint while one is
//  live must be refused at the priceRowsViaExtension choke point, so it can neither WIPE the running
//  session (scanBegin->scanReset) nor re-send an already-dispatched row (a duplicate on-IP trade call).
// ==================================================================================================
async function scenarioScanEntrypointGuard() {
  console.log("· scenario: R6-F3 — a 2nd scan entrypoint can't wipe or double-send a live scan");
  const inst = makeBridgeInstance({});
  const { bpc, sent, deliver } = inst;
  bpc.init();
  await ticks(6);
  ok(bpc.state.bridge.active === true, "bridge activates from pong");

  // 4 unpriced rares -> autoscan sends them as 2 chunks (CHUNK=3); the fake ext HOLDS every reply,
  // so the scan stays ACTIVE while we probe a second entrypoint.
  const M = { meta: { league: "Allflame", character: "Multi", divine_to_chaos: 100 },
    items: [0, 1, 2, 3].map((i) => ({ index: i, group: "equipment", slot: "Belt", category: "rare", name: "R" + i,
      trade_query: { query: { status: { option: "online" }, type: "Belt" } } })),
    priced: { 0: { chaos: { min: null, median: null, high: null }, method: "none", note: "" },
              1: { chaos: { min: null, median: null, high: null }, method: "none", note: "" },
              2: { chaos: { min: null, median: null, high: null }, method: "none", note: "" },
              3: { chaos: { min: null, median: null, high: null }, method: "none", note: "" } } };
  bpc.loadMock(M);
  await tick();
  const scanP = bpc.autoscan();                 // do NOT await — replies are held, so the scan stays live
  await ticks(3);
  ok(bpc.scanStatus().active === true, "the autoscan is live (replies held)");
  eq(bpc.scanStatus().order.length, 4, "the live scan tracks all 4 rows");
  const priceMsgsBefore = sent.filter((m) => m.type === "price").length;

  // Fire a SECOND scan entrypoint mid-scan — the per-row ⚡auto (priceViaExtension) on a row the
  // first scan already dispatched. PRE-FIX this ran scanReset() -> collapsed the session to 1 row and
  // re-sent the row (a duplicate trade search).
  const r = await bpc.priceViaExtension("2");
  await ticks(2);
  ok(r && r.busy === true, "F3: the 2nd entrypoint is REFUSED while a scan is active (resolves {busy})");
  eq(bpc.scanStatus().order.length, 4, "F3: the live scan session is INTACT (not collapsed to 1 row)");
  eq(bpc.scanStatus().active, true, "F3: the live scan is still active (scanReset did not wipe it)");
  eq(sent.filter((m) => m.type === "price").length, priceMsgsBefore,
     "F3: NO extra price message was sent — row 2 was not double-searched (rate-limit budget preserved)");

  // The picker entrypoints funnel through the same choke point -> also refused mid-scan.
  const rc = await bpc.priceRaresCustom([{ key: "3", query: { status: { option: "online" }, type: "Belt" } }]);
  ok(rc && rc.busy === true, "F3: priceRaresCustom (picker Autoscan) is refused mid-scan too (one guard covers all)");
  eq(sent.filter((m) => m.type === "price").length, priceMsgsBefore, "F3: still no extra price message after the picker attempt");

  // Drain the held chunk replies so the live scan ends cleanly.
  sent.filter((m) => m.type === "price").forEach((m) =>
    deliver(m.reqId, (m.queries || []).map((q) => ({ key: q.key, total: 5, amount: 10, currency: "chaos", listingId: "x" }))));
  await ticks(4);
  await scanP;
  eq(bpc.scanStatus().active, false, "the live scan ends after its held replies arrive");

  // Positive control: with NO scan active, the very same entrypoint is allowed (the guard blocks
  // OVERLAP only — it never permanently disables pricing).
  const afterEnd = sent.filter((m) => m.type === "price").length;
  bpc.priceViaExtension("2");                    // do NOT await (reply held) — just verify it was ALLOWED to start
  await ticks(3);
  ok(bpc.scanStatus().active === true, "positive control: with no scan active, the entrypoint starts a fresh scan");
  ok(sent.filter((m) => m.type === "price").length > afterEnd,
     "positive control: it actually sent a price message (guard blocks overlap, not legitimate reprices)");
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
  await scenarioBuildTimeout();
  await scenarioRaceBuildSwap();
  await scenarioRaceZombieScan();
  await scenarioScanEntrypointGuard();
  scenarioWhisperSeparators();
  await scenarioRecentCoercion();
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
