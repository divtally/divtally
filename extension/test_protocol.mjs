/* Offline verification harness for the v1.1 per-item progress protocol (background.js).
 *
 * No network, no pathofexile.com, no browser. It loads background.js verbatim into a function
 * scope with STUBBED chrome.* + fetch (+ a clamped setTimeout so rate-limiter sleeps don't
 * actually block), then drives priceMany over fake items and asserts:
 *   - the exact progress event SEQUENCE (queued/searching/fetching/waiting/done/nobuyout/error),
 *   - the debug object attached to every final result,
 *   - the version + tab gating done in the message listener,
 *   - the enriched (status + body head) error message from tradeRequest,
 *   - protoAtLeast() version comparison.
 *
 * Run:  node extension/test_protocol.mjs   (exit 0 = all pass, 1 = any fail)
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BG_SRC = fs.readFileSync(path.join(__dirname, "background.js"), "utf8");

// ---------------------------------------------------------------- check runner
let failures = 0;
function check(name, cond, extra) {
  if (cond) {
    console.log("  PASS  " + name);
  } else {
    failures++;
    console.log("  FAIL  " + name + (extra !== undefined ? "   got=" + JSON.stringify(extra) : ""));
  }
}
function debugEq(d, exp) {
  return !!d && d.searchStatus === exp.searchStatus && d.fetchStatus === exp.fetchStatus
    && d.fetched === exp.fetched && d.nulls === exp.nulls;
}

// ---------------------------------------------------------------- fakes
function makeResponse(spec) {
  const status = spec.status != null ? spec.status : 200;
  const h = new Map();
  h.set("content-type", spec.contentType != null ? spec.contentType : "application/json");
  if (spec.rateLimitIp != null) h.set("x-rate-limit-ip", spec.rateLimitIp);
  if (spec.retryAfter != null) h.set("retry-after", String(spec.retryAfter));
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: (n) => { const v = h.get(String(n).toLowerCase()); return v == null ? null : v; } },
    json: async () => spec.json,
    text: async () => (spec.text != null ? spec.text : JSON.stringify(spec.json != null ? spec.json : "")),
  };
}
function planFetch(plan) {
  return async (url) => makeResponse(url.indexOf("/search/") !== -1 ? plan.search(url) : plan.fetch(url));
}
function makeChrome() {
  const store = {};
  const chrome = {
    runtime: {
      lastError: null,
      getManifest: () => ({ version: "1.1.0" }),
      onMessage: { _listener: null, addListener(fn) { this._listener = fn; } },
    },
    storage: {
      local: {
        get(key) {
          const keys = Array.isArray(key) ? key : [key];
          const out = {};
          for (const k of keys) if (Object.prototype.hasOwnProperty.call(store, k)) out[k] = store[k];
          return Promise.resolve(out);
        },
        set(obj) { Object.assign(store, obj); return Promise.resolve(); },
        remove(keys) { for (const k of (Array.isArray(keys) ? keys : [keys])) delete store[k]; return Promise.resolve(); },
      },
    },
    tabs: {
      events: [],
      sendMessage(tabId, msg, cb) { this.events.push({ tabId, msg }); if (typeof cb === "function") cb(); return Promise.resolve(); },
    },
  };
  return { chrome, store };
}

// Load background.js into a scope with injected globals. Top-level function declarations become
// locals of the factory; we return the ones under test. setTimeout is clamped to <=5ms real so
// (a) rate-limiter/429 sleeps are near-instant and (b) the microtask-resolved fake fetch always
// wins the race against the 30s abort timer.
function instantiate(chrome, fetchImpl) {
  const clampSetTimeout = (fn, ms) => setTimeout(fn, Math.min(Math.max((ms | 0), 0), 5));
  const factory = new Function(
    "chrome", "fetch", "setTimeout", "clearTimeout", "AbortController", "console",
    BG_SRC + "\n;return { priceMany, priceQuery, tradeRequest, protoAtLeast, emitProgress, snapshotDebug };"
  );
  return factory(chrome, fetchImpl, clampSetTimeout, clearTimeout, AbortController, console);
}

// ---------------------------------------------------------------- scenarios
async function scenarioA() {
  console.log("Scenario A: two items (done + nobuyout) - full sequence + debug");
  const { chrome } = makeChrome();
  let sc = 0, fc = 0;
  const plan = {
    search: () => ({ status: 200, json: { id: "S" + (++sc), total: 5, result: ["x1", "x2", "x3"] } }),
    fetch: () => {
      fc++;
      if (fc === 1) return { status: 200, json: { result: [{ listing: { price: { amount: 12, currency: "chaos" } } }] } };
      return { status: 200, json: { result: [{ listing: { price: null } }, { listing: {} }, { listing: { price: { amount: null, currency: null } } }] } };
    },
  };
  const api = instantiate(chrome, planFetch(plan));
  const results = await api.priceMany(
    [{ key: "k1", query: { q: 1 } }, { key: "k2", query: { q: 2 } }], "Settlers",
    { tabId: 1, reqId: "rA" }
  );
  const ev = chrome.tabs.events;
  const gotSeq = ev.map((e) => e.msg.stage + ":" + e.msg.key);
  const wantSeq = ["queued:k1", "queued:k2", "searching:k1", "fetching:k1", "done:k1", "searching:k2", "fetching:k2", "nobuyout:k2"];
  check("event sequence exact", JSON.stringify(gotSeq) === JSON.stringify(wantSeq), gotSeq);
  check("no 'waiting' (fresh limiter, under caps)", ev.every((e) => e.msg.stage !== "waiting"));
  check("every event -> tab 1 / reqId rA", ev.every((e) => e.tabId === 1 && e.msg.reqId === "rA"));
  const done = ev.find((e) => e.msg.stage === "done");
  check("done detail {total,amount,currency}", done && done.msg.detail.total === 5 && done.msg.detail.amount === 12 && done.msg.detail.currency === "chaos", done && done.msg.detail);
  const nb = ev.find((e) => e.msg.stage === "nobuyout");
  check("nobuyout detail {total,fetched,nulls}", nb && nb.msg.detail.total === 5 && nb.msg.detail.fetched === 3 && nb.msg.detail.nulls === 3, nb && nb.msg.detail);
  check("result k1 priced (12 chaos, listingId S1)", results[0].key === "k1" && results[0].amount === 12 && results[0].currency === "chaos" && results[0].total === 5 && results[0].listingId === "S1", results[0]);
  check("result k1 debug {200,200,1,0}", debugEq(results[0].debug, { searchStatus: 200, fetchStatus: 200, fetched: 1, nulls: 0 }), results[0].debug);
  check("result k2 nobuyout (amount null, listingId S2)", results[1].key === "k2" && results[1].amount === null && results[1].currency === null && results[1].total === 5 && results[1].listingId === "S2", results[1]);
  check("result k2 debug {200,200,3,3}", debugEq(results[1].debug, { searchStatus: 200, fetchStatus: 200, fetched: 3, nulls: 3 }), results[1].debug);
}

async function scenarioB() {
  console.log("Scenario B: search HTTP 400 - error stage + status + body-head diagnostics");
  const { chrome } = makeChrome();
  const bodyVisible = "ERRBODY_" + "a".repeat(72);         // exactly 80 chars -> all within slice(0,80)
  const body = bodyVisible + "SENTINEL_TRUNCATED_AWAY";    // beyond char 80 -> must be dropped
  const plan = {
    search: () => ({ status: 400, contentType: "application/json", json: { error: { message: "bad query" } }, text: body }),
    fetch: () => ({ status: 200, json: { result: [] } }),
  };
  const api = instantiate(chrome, planFetch(plan));
  const results = await api.priceMany([{ key: "k", query: { q: 1 } }], "Settlers", { tabId: 2, reqId: "rB" });
  const ev = chrome.tabs.events;
  check("sequence queued/searching/error", JSON.stringify(ev.map((e) => e.msg.stage)) === JSON.stringify(["queued", "searching", "error"]), ev.map((e) => e.msg.stage));
  check("no 'fetching' (search failed first)", !ev.some((e) => e.msg.stage === "fetching"));
  const err = ev.find((e) => e.msg.stage === "error");
  check("error detail.status === 400", err && err.msg.detail.status === 400, err && err.msg.detail);
  check("error detail.message starts 'HTTP 400 '", err && /^HTTP 400 /.test(err.msg.detail.message), err && err.msg.detail.message);
  check("error message carries body head (ERRBODY_)", err && err.msg.detail.message.includes("ERRBODY_"));
  check("error message truncated (no SENTINEL past 80)", err && !err.msg.detail.message.includes("SENTINEL"), err && err.msg.detail.message);
  check("error message length === 25 + 80", err && err.msg.detail.message.length === 105, err && err.msg.detail.message.length);
  check("result carries error string", results[0].error && /^HTTP 400 /.test(results[0].error));
  check("result debug {400,null,0,0}", debugEq(results[0].debug, { searchStatus: 400, fetchStatus: null, fetched: 0, nulls: 0 }), results[0].debug);
}

async function scenarioC() {
  console.log("Scenario C: pre-seeded limiter forces a >1s pause - waiting stage");
  const { chrome, store } = makeChrome();
  const now = Date.now();
  store["rl_search"] = { hits: [now, now, now] };          // == effective cap (3) in the 10s window
  const plan = {
    search: () => ({ status: 200, json: { id: "SC", total: 1, result: ["x1"] } }),
    fetch: () => ({ status: 200, json: { result: [{ listing: { price: { amount: 5, currency: "divine" } } }] } }),
  };
  const api = instantiate(chrome, planFetch(plan));
  const results = await api.priceMany([{ key: "k", query: { q: 1 } }], "Settlers", { tabId: 3, reqId: "rC" });
  const stages = chrome.tabs.events.map((e) => e.msg.stage);
  check("'waiting' present", stages.includes("waiting"), stages);
  const wi = stages.indexOf("waiting"), si = stages.indexOf("searching"), fi = stages.indexOf("fetching");
  check("waiting after searching, before fetching", si !== -1 && wi > si && fi > wi, { si, wi, fi });
  const w = chrome.tabs.events[wi];
  check("waiting detail.waitMs > 1000", w && w.msg.detail.waitMs > 1000, w && w.msg.detail);
  check("still resolves to done + priced", stages.includes("done") && results[0].amount === 5 && results[0].currency === "divine");
}

async function scenarioD() {
  console.log("Scenario D: version + tab gating via the message listener");
  const basePlan = () => ({
    search: () => ({ status: 200, json: { id: "SD", total: 1, result: ["x1"] } }),
    fetch: () => ({ status: 200, json: { result: [{ listing: { price: { amount: 1, currency: "chaos" } } }] } }),
  });
  function drive(chrome, msg, sender) {
    return new Promise((resolve) => {
      const ret = chrome.runtime.onMessage._listener(msg, sender, (resp) => resolve(resp));
      if (ret !== true) resolve(undefined);
    });
  }
  // D1: popup-style (no sender.tab, no protocolVersion) -> silently no progress.
  {
    const { chrome } = makeChrome();
    instantiate(chrome, planFetch(basePlan()));
    const resp = await drive(chrome, { type: "bpc-price", league: "L", queries: [{ key: "k", query: { q: 1 } }] }, {});
    check("D1 popup: pricing still returns a result", resp && resp.results && resp.results.length === 1 && resp.results[0].amount === 1);
    check("D1 popup: NO progress events", chrome.tabs.events.length === 0, chrome.tabs.events.map((e) => e.msg.stage));
  }
  // D2: tab + protocolVersion 1.1 -> progress, correct tabId + reqId.
  {
    const { chrome } = makeChrome();
    instantiate(chrome, planFetch(basePlan()));
    await drive(chrome, { type: "bpc-price", league: "L", queries: [{ key: "k", query: { q: 1 } }], reqId: "rD", protocolVersion: "1.1" }, { tab: { id: 7 } });
    const ev = chrome.tabs.events;
    check("D2 v1.1 tab: progress emitted", ev.length > 0);
    check("D2 v1.1 tab: all -> tab 7 / reqId rD", ev.every((e) => e.tabId === 7 && e.msg.reqId === "rD"));
    check("D2 v1.1 tab: has queued+searching+fetching+done", ["queued", "searching", "fetching", "done"].every((s) => ev.some((e) => e.msg.stage === s)), ev.map((e) => e.msg.stage));
  }
  // D3: tab present but protocolVersion 1.0 -> version gate blocks progress.
  {
    const { chrome } = makeChrome();
    instantiate(chrome, planFetch(basePlan()));
    await drive(chrome, { type: "bpc-price", league: "L", queries: [{ key: "k", query: { q: 1 } }], reqId: "rX", protocolVersion: "1.0" }, { tab: { id: 9 } });
    check("D3 v1.0 tab: NO progress (version gate)", chrome.tabs.events.length === 0, chrome.tabs.events.map((e) => e.msg.stage));
  }
}

function scenarioProto() {
  console.log("Scenario P: protoAtLeast() version comparison");
  const { chrome } = makeChrome();
  const p = instantiate(chrome, planFetch({ search: () => ({ json: {} }), fetch: () => ({ json: {} }) })).protoAtLeast;
  check("'1.1' >= 1.1", p("1.1", 1, 1) === true);
  check("'1.1.0' >= 1.1", p("1.1.0", 1, 1) === true);
  check("number 1.1 >= 1.1", p(1.1, 1, 1) === true);
  check("'1.2' >= 1.1", p("1.2", 1, 1) === true);
  check("'2.0' >= 1.1", p("2.0", 1, 1) === true);
  check("'1.0' < 1.1", p("1.0", 1, 1) === false);
  check("'1' < 1.1", p("1", 1, 1) === false);
  check("undefined < 1.1", p(undefined, 1, 1) === false);
}

async function main() {
  await scenarioA();
  await scenarioB();
  await scenarioC();
  await scenarioD();
  scenarioProto();
  console.log("");
  if (failures) { console.log("RESULT: FAIL (" + failures + " check(s) failed)"); process.exit(1); }
  console.log("RESULT: PASS (all checks passed)");
  process.exit(0);
}
main().catch((e) => { console.error("HARNESS ERROR:", e); process.exit(1); });
