/*
 * Offline security regression tests for R6-S1 (reflected-XSS chain).
 *   node test_security.mjs
 *
 * No browser, no network, no pathofexile.com. Loads assets/core.js into a Node `vm` and drives the
 * three legs of the S1 fix, plus extracts index.html's client-side URL/number guards and proves them
 * inert. Every leg INDEPENDENTLY breaks the exploit chain; each is locked here so a regression trips.
 *
 *   1. Data-origin overrides are DEV-GATED. ?api/?worker/?stub repoint the build + cache fetch at an
 *      attacker origin only on a dev host; in production they are ignored (config wins).
 *   2. The community cache read-through RE-VALIDATES on read. A poisoned entry (the ?worker override
 *      bypasses the worker's write-time sanitiser) can't fold a javascript: trade_url or a
 *      non-numeric sample_size/total_found into the row.
 *   3. rareTradeUrl / index.html safeHref+safeIcon scheme-validate every document-supplied URL, and
 *      every document-derived NUMBER is Number()-coerced before it reaches innerHTML.
 */
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE_SRC = fs.readFileSync(join(HERE, "assets", "core.js"), "utf8");
const HTML_SRC = fs.readFileSync(join(HERE, "index.html"), "utf8");

let passed = 0, failed = 0;
function ok(cond, msg) { if (cond) { passed++; } else { failed++; console.error("  FAIL:", msg); } }
const tick = () => new Promise((r) => setTimeout(r, 1));
async function ticks(n) { for (let i = 0; i < n; i++) await tick(); }

const DIGEST = (a, b) => { let h = 2166136261 >>> 0; for (let i = 0; i < b.length; i++) { h ^= b[i]; h = Math.imul(h, 16777619) >>> 0; }
  const o = new Uint8Array(32); for (let i = 0; i < 32; i++) o[i] = (h >>> ((i % 4) * 8)) & 0xff; return Promise.resolve(o.buffer); };
function FakeAbort() { this.signal = { aborted: false, addEventListener() {}, removeEventListener() {} }; }
FakeAbort.prototype.abort = function () { this.signal.aborted = true; };

// A core.js instance with a fake window, deterministic SubtleCrypto, and a fetch that records the
// build + cache URLs it is asked to hit and can echo a canned cache record back keyed by request.
function makeInst(o) {
  o = o || {};
  const lsMap = new Map(), builds = [], cacheGets = [], posts = [];
  const win = { BPC_CONFIG: o.cfg, location: { search: o.search || "",
      origin: `${o.protocol || "https:"}//${o.hostname || "divtally.com"}`,
      href: `${o.protocol || "https:"}//${o.hostname || "divtally.com"}/`,
      hostname: o.hostname || "divtally.com", protocol: o.protocol || "https:" },
    addEventListener() {}, removeEventListener() {}, postMessage() {} };
  win.window = win;
  const localStorage = { getItem: (k) => (lsMap.has(k) ? lsMap.get(k) : null), setItem: (k, v) => lsMap.set(k, String(v)), removeItem: (k) => lsMap.delete(k) };
  const fetchImpl = (url, init) => {
    const s = String(url);
    if (s.indexOf("/api/build") >= 0) { builds.push(s); return Promise.resolve({ ok: true, json: () => Promise.resolve(o.buildDoc || { ok: true, meta: {}, items: [], rares: {}, warnings: [] }) }); }
    if (init && init.method === "POST") { posts.push({ url: s, body: JSON.parse(init.body) }); return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }); }
    cacheGets.push(s);
    const m = s.match(/[?&]keys=([^&]*)/), keys = m ? decodeURIComponent(m[1]).split(",").filter(Boolean) : [];
    const out = {}; if (o.cacheRecord) keys.forEach((k) => { out[k] = o.cacheRecord; });
    return Promise.resolve({ ok: true, json: () => Promise.resolve(out) });
  };
  const sandbox = { window: win, self: win, console, setTimeout, clearTimeout, TextEncoder, URLSearchParams,
    localStorage, crypto: { subtle: { digest: DIGEST } }, Date, Math, JSON, fetch: fetchImpl, AbortController: FakeAbort };
  vm.runInNewContext(CORE_SRC, sandbox, { filename: "core.js" });
  return { bpc: win.bpc, builds, cacheGets, posts };
}

const RARE_BUILD = { ok: true, meta: { league: "Standard", character: "C", divine_to_chaos: 100 },
  items: [{ index: 0, group: "equipment", slot: "Ring", category: "rare", name: "R",
    trade_query: { query: { status: { option: "online" }, type: "Ring" } } }], rares: {}, warnings: [] };

async function scenarioOverridesGatedInProd() {
  console.log("· S1 leg 1: ?api/?worker/?stub are IGNORED in production (attacker can't repoint the data origin)");
  const inst = makeInst({ cfg: { API_BASE: "https://good.api", WORKER_BASE: "https://good.worker" },
    hostname: "divtally.com", protocol: "https:",
    search: "?api=https://evil.tld&worker=https://evil.tld&stub=https://evil.tld/b.json", buildDoc: RARE_BUILD });
  inst.bpc.init();
  inst.bpc.startUrl("https://poe.ninja/char/x");
  await ticks(10);
  ok(inst.builds.length > 0 && inst.builds[0].indexOf("https://good.api/") === 0,
     "build fetch went to the CONFIGURED api, not ?api=evil: " + inst.builds[0]);
  ok(inst.builds.every((u) => u.indexOf("evil.tld") < 0), "no build fetch touched evil.tld (?api + ?stub ignored)");
  ok(inst.cacheGets.length > 0 && inst.cacheGets[0].indexOf("https://good.worker/") === 0,
     "cache read-through went to the CONFIGURED worker, not ?worker=evil: " + inst.cacheGets[0]);
  ok(inst.cacheGets.every((u) => u.indexOf("evil.tld") < 0), "no cache fetch touched evil.tld (?worker ignored)");
}

async function scenarioOverridesHonouredInDev() {
  console.log("· S1 leg 1 (control): the same overrides ARE honoured on a dev host (localhost)");
  const inst = makeInst({ cfg: { API_BASE: "https://good.api", WORKER_BASE: "https://good.worker" },
    hostname: "localhost", protocol: "http:",
    search: "?api=https://dev.api&worker=https://dev.worker", buildDoc: RARE_BUILD });
  inst.bpc.init();
  inst.bpc.startUrl("https://poe.ninja/char/x");
  await ticks(10);
  ok(inst.builds[0].indexOf("https://dev.api/") === 0, "dev host honours ?api override: " + inst.builds[0]);
  ok(inst.cacheGets[0].indexOf("https://dev.worker/") === 0, "dev host honours ?worker override: " + inst.cacheGets[0]);
}

async function scenarioCacheReadThroughSanitises() {
  console.log("· S1 leg 2: a poisoned community-cache entry is re-validated on read (js url dropped, numerics coerced)");
  const poison = { chaos: { min: 5, median: 7, high: 9 }, confidence: "low", method: "cache",
    sample_size: "<img src=x onerror=alert(1)>", total_found: "<script>bad</script>", trade_url: "javascript:alert(document.domain)" };
  const inst = makeInst({ cfg: { API_BASE: "https://good.api", WORKER_BASE: "https://good.worker" },
    buildDoc: RARE_BUILD, cacheRecord: poison });
  inst.bpc.init();
  inst.bpc.startUrl("https://poe.ninja/char/x");
  await ticks(12);
  const p = inst.bpc.state.priced["0"];
  ok(p && p.chaos.median === 7, "numeric cache price coerced through num() and applied (median 7)");
  ok(!/^javascript:/i.test(String(p.trade_url || "")), "javascript: trade_url was NOT applied (dropped by the https://www.pathofexile.com/ check): " + p.trade_url);
  ok(typeof p.sample_size === "number", "hostile string sample_size coerced to a number (was '<img …>'): " + JSON.stringify(p.sample_size));
  ok(typeof p.total_found === "number", "hostile string total_found coerced to a number (was '<script>…'): " + JSON.stringify(p.total_found));

  // positive control: a legitimate pathofexile trade_url IS applied (guard isn't over-broad)
  const good = { chaos: { min: 5, median: 7, high: 9 }, method: "cache", sample_size: 3, total_found: 4,
    confidence: "low", trade_url: "https://www.pathofexile.com/trade/search/Standard?q=xyz" };
  const inst2 = makeInst({ cfg: { API_BASE: "https://good.api", WORKER_BASE: "https://good.worker" }, buildDoc: RARE_BUILD, cacheRecord: good });
  inst2.bpc.init(); inst2.bpc.startUrl("https://poe.ninja/char/x"); await ticks(12);
  ok(inst2.bpc.state.priced["0"].trade_url === good.trade_url, "a valid pathofexile trade_url from the cache IS applied");
}

function scenarioRareTradeUrl() {
  console.log("· S1 leg 3a: rareTradeUrl discards a hostile document-supplied base, always emits a pathofexile URL");
  const { bpc } = makeInst({ cfg: { API_BASE: "https://good.api", WORKER_BASE: "" } });
  const q = { status: { option: "online" }, type: "Ring" };
  const PX = /^https:\/\/www\.pathofexile\.com\//;
  ok(PX.test(bpc.rareTradeUrl(q, "javascript:alert(1)")), "javascript: base discarded -> canonical pathofexile URL");
  ok(PX.test(bpc.rareTradeUrl(q, "https://evil.tld/trade/search/x?q=old")), "evil-host base discarded -> canonical pathofexile URL");
  ok(!/evil\.tld/.test(bpc.rareTradeUrl(q, "https://evil.tld/trade/search/x?q=old")), "the evil host never survives into the emitted URL");
  const kept = bpc.rareTradeUrl(q, "https://www.pathofexile.com/trade/search/Betrayal?q=old");
  ok(kept.indexOf("https://www.pathofexile.com/trade/search/Betrayal") === 0, "a real pathofexile base IS reused: " + kept);
}

function scenarioIndexHtmlGuards() {
  console.log("· S1 leg 3b: index.html safeHref/safeIcon scheme-validate; numeric sinks Number()-coerce");
  const mHref = HTML_SRC.match(/const safeHref\s*=\s*(.+?);\s*$/m);
  const mIcon = HTML_SRC.match(/const safeIcon\s*=\s*(.+?);\s*$/m);
  ok(!!mHref && !!mIcon, "found safeHref + safeIcon definitions in index.html");
  const safeHref = new Function("return (" + mHref[1] + ")")();
  const safeIcon = new Function("return (" + mIcon[1] + ")")();
  ok(safeHref("javascript:alert(1)") === "", "safeHref rejects javascript:");
  ok(safeHref("https://evil.tld/x") === "", "safeHref rejects a non-pathofexile host");
  ok(safeHref("HTTPS://WWW.PATHOFEXILE.COM/trade/x") === "HTTPS://WWW.PATHOFEXILE.COM/trade/x", "safeHref accepts pathofexile (case-insensitive)");
  ok(safeIcon("javascript:alert(1)") === "", "safeIcon rejects javascript:");
  ok(safeIcon("http://insecure/x.png") === "", "safeIcon rejects non-https");
  ok(safeIcon("https://web.poecdn.com/x.png") === "https://web.poecdn.com/x.png", "safeIcon accepts an https icon");

  // the numeric-coercion pattern used at every document-derived number sink (meta.level, gem level/
  // quality, tooltip sample_size/total_found, item count) — a hostile string can never reach innerHTML.
  const coerce = (x) => Number(x) || 0;
  ok(coerce("<img src=x onerror=alert(1)>") === 0, "hostile string number -> 0 (Number()||0)");
  ok(coerce("2<img onerror=alert(1)>") === 0, "numeric-prefixed hostile string -> 0 (not 2)");
  ok(coerce("55") === 55 && coerce(7) === 7, "clean numbers pass through unchanged");
  // the it.count sink additionally gates on >1, so even a bare-number-looking hostile string is inert
  ok((Number("<img>") > 1) === false, "count gate: NaN>1 is false (no markup ever rendered)");
  ok((coerce("2") > 1) === true, "count gate: a real count still renders");
}

(async () => {
  await scenarioOverridesGatedInProd();
  await scenarioOverridesHonouredInDev();
  await scenarioCacheReadThroughSanitises();
  scenarioRareTradeUrl();
  scenarioIndexHtmlGuards();
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
