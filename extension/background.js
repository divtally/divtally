/* DivTally browser extension : background service worker.
 *
 * Performs the official trade search+fetch on the USER'S machine/IP (extensions with
 * host_permissions are exempt from page CORS), so the public website never proxies trade
 * calls through one shared IP (which would be rate-limited/banned). Ported from the Python
 * client (bpc/trade.py): same endpoints, same conservative sliding-window rate limiter, same
 * 429 back-off and header-driven tightening.
 *
 * MV3 service workers are terminated when idle and restarted on demand, so the rate-limiter
 * state is PERSISTED to chrome.storage.local -- it survives a worker restart and we never
 * accidentally burst past GGG's per-IP cap after a wake-up.
 */
"use strict";

const BASE = "https://www.pathofexile.com/api/trade";
// PoE1 uses NO realm segment in the path (PC is default; xbox/sony would use ?realm=).

// Conservative starting rules per endpoint: [maxHits, windowSeconds]. We only ever TIGHTEN
// these from the authoritative X-Rate-Limit-Ip header. Mirrors _DEFAULT_RULES in trade.py --
// PoE1 windows (trade1.md sec 7): search adds a 600/6h window; fetch adds 50/300 + 1000/6h.
const DEFAULT_RULES = {
  search: [[5, 10], [15, 60], [30, 300], [600, 21600]],
  fetch:  [[12, 4], [16, 12], [50, 300], [1000, 21600]],
};
const MARGIN = 0.7;          // stay under MARGIN * each cap
const FETCH_TIMEOUT_MS = 30000;

function delay(ms) { return new Promise((r) => setTimeout(r, ms)); }

function effectiveCap(cap) {
  if (cap <= 1) return 1;
  return Math.max(1, Math.min(cap - 1, Math.floor(cap * MARGIN)));
}

// ---- persistent rate limiter -------------------------------------------------
async function rlGet(bucket) {
  const key = "rl_" + bucket;
  const got = await chrome.storage.local.get(key);
  const st = got[key] || {};
  return { rules: st.rules || DEFAULT_RULES[bucket], hits: st.hits || [], last: st.last || 0 };
}
async function rlSet(bucket, st) {
  await chrome.storage.local.set({ ["rl_" + bucket]: st });
}

// Merge authoritative server rules with our defaults; only ever tighten (mirrors update_rules).
function mergeRules(bucket, header) {
  if (!header) return null;
  const floor = {};
  for (const [c, w] of DEFAULT_RULES[bucket]) floor[w] = c;
  const merged = Object.assign({}, floor);
  for (const part of String(header).split(",")) {
    const bits = part.split(":");
    if (bits.length >= 2) {
      const cap = parseInt(bits[0], 10), win = parseInt(bits[1], 10);
      if (!isNaN(cap) && !isNaN(win)) merged[win] = Math.min(merged[win] != null ? merged[win] : cap, cap);
    }
  }
  return Object.keys(merged).map((w) => [merged[w], parseInt(w, 10)]).sort((a, b) => a[1] - b[1]);
}

// Wait until a call is safe under every rule, then record it. Serialized (see `serialize`),
// so reads/writes of the persisted window never race. `emit` (optional, v1.1) is a per-item
// progress callback used to surface a rate-limiter pause to the page.
async function rateLimitGate(bucket, emit) {
  const st = await rlGet(bucket);
  const now = Date.now();
  const maxWinMs = Math.max.apply(null, st.rules.map((r) => r[1])) * 1000;
  let hits = st.hits.filter((t) => now - t <= maxWinMs);

  let sleep = 0;
  for (const [cap, win] of st.rules) {
    const winMs = win * 1000;
    const eff = effectiveCap(cap);
    const recent = hits.filter((t) => now - t <= winMs);
    if (recent.length >= eff) {
      const oldest = recent[recent.length - eff];   // the hit that must age out
      sleep = Math.max(sleep, winMs - (now - oldest));
    }
  }
  // BREATHING ROOM (owner, D-0018): spread requests evenly across the tightest window instead
  // of bursting to its cap and stalling. Even pacing = same net throughput, no burst spikes.
  const [c0, w0] = st.rules[0];                       // rules sorted shortest-window-first
  const spacing = Math.ceil((w0 * 1000) / effectiveCap(c0));
  const sinceLast = now - (st.last || 0);
  if (sinceLast >= 0 && sinceLast < spacing) sleep = Math.max(sleep, spacing - sinceLast);

  if (sleep > 0) {
    const waitMs = sleep + 100 + Math.floor(Math.random() * 200);
    // v1.1 progress: only report a *real* pause (> 1s); sub-second jitter isn't worth a message.
    if (emit && waitMs > 1000) emit("waiting", { waitMs });
    await delay(waitMs);
  }

  hits = st.hits.filter((t) => Date.now() - t <= maxWinMs);
  hits.push(Date.now());
  await rlSet(bucket, { rules: st.rules, hits, last: Date.now() });
}

async function applyHeaderRules(bucket, header) {
  const rules = mergeRules(bucket, header);
  if (!rules) return;
  const st = await rlGet(bucket);
  await rlSet(bucket, { rules, hits: st.hits, last: st.last });
}

function parseRetryAfter(v) {
  if (!v) return null;
  const n = parseFloat(v);
  if (!isNaN(n)) return n;
  const d = Date.parse(v);
  if (!isNaN(d)) return Math.max(0, (d - Date.now()) / 1000);
  return null;
}

// ---- low-level request with retry/back-off (mirrors trade.py._request) -------
// `emit`/`dbg` (optional, v1.1) let a call report rate-limiter pauses and record its HTTP status
// for the page-visible debug object. Thrown errors carry `.status` when a response was received.
async function tradeRequest(bucket, method, url, body, attempt, emit, dbg) {
  attempt = attempt || 0;
  await rateLimitGate(bucket, emit);

  let r;
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    r = await fetch(url, {
      method,
      credentials: "omit",                 // unauthenticated -> per-IP limits (no account risk)
      headers: Object.assign({ "Accept": "application/json" },
                             body ? { "Content-Type": "application/json" } : {}),
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    clearTimeout(to);
    if (attempt < 2) { await delay(2000 + attempt * 2000); return tradeRequest(bucket, method, url, body, attempt + 1, emit, dbg); }
    throw new Error("network error calling trade API: " + (e && e.message ? e.message : e));
  }
  clearTimeout(to);

  // Record the HTTP status per endpoint so a failing item is self-describing (v1.1 debug).
  if (dbg) {
    if (bucket === "search") dbg.searchStatus = r.status;
    else if (bucket === "fetch") dbg.fetchStatus = r.status;
  }

  await applyHeaderRules(bucket, r.headers.get("X-Rate-Limit-Ip"));

  if (r.status === 429) {
    let retry = parseRetryAfter(r.headers.get("Retry-After"));
    if (retry == null) retry = Math.max.apply(null, DEFAULT_RULES[bucket].map((x) => x[1]));
    retry = Math.max(5, Math.min(retry, 1800));
    const waitMs = retry * 1000 + 1000;
    if (emit) emit("waiting", { waitMs });          // a 429 back-off is the biggest rate-limiter pause
    await delay(waitMs);
    if (attempt < 1) return tradeRequest(bucket, method, url, body, attempt + 1, emit, dbg);
    const e429 = new Error("repeatedly rate-limited by trade API (HTTP 429); try again later");
    e429.status = 429;
    throw e429;
  }
  if (r.status >= 500 && r.status <= 504 && attempt < 2) {
    await delay(3000 + attempt * 3000);
    return tradeRequest(bucket, method, url, body, attempt + 1, emit, dbg);
  }
  if (!r.ok) {
    // Diagnostics-in-product: name the real cause (HTTP status + first 80 chars of body) in the
    // page-visible error, instead of a bare "HTTP 4xx".
    const txt = await r.text().catch(() => "");
    const err = new Error("HTTP " + r.status + " from trade API: " + txt.slice(0, 80));
    err.status = r.status;
    throw err;
  }
  const ct = r.headers.get("content-type") || "";
  if (ct.indexOf("json") === -1) {
    const txt = await r.text().catch(() => "");
    const err = new Error("non-JSON response (HTTP " + r.status + ", content-type '" + ct
                          + "') from trade API: " + txt.slice(0, 80));
    err.status = r.status;
    throw err;
  }
  return r.json();
}

// ---- search + fetch -> cheapest listing --------------------------------------
// `emit`/`dbg` (optional, v1.1) report stage transitions and accumulate the debug counters
// (fetched / nulls) that make a "no buyout" outcome self-describing.
async function priceQuery(query, league, emit, dbg) {
  if (!league) throw new Error("missing league");
  if (!query) throw new Error("missing query");
  const sUrl = BASE + "/search/" + encodeURIComponent(league);
  if (emit) emit("searching", {});
  const sres = await tradeRequest("search", "POST", sUrl, { query, sort: { price: "asc" } }, 0, emit, dbg);
  const ids = (sres.result || []).slice(0, 10);          // API caps fetch at 10 ids
  const total = (sres.total != null) ? sres.total : (sres.result ? sres.result.length : 0);
  if (!ids.length) return { total: 0, amount: null, currency: null, listingId: sres.id || null, prices: [] };

  const fUrl = BASE + "/fetch/" + ids.join(",") + "?query=" + encodeURIComponent(sres.id);
  if (emit) emit("fetching", {});
  const fres = await tradeRequest("fetch", "GET", fUrl, null, 0, emit, dbg);
  const listings = fres.result || [];
  if (dbg) dbg.fetched = listings.length;                // how many listings we actually pulled
  // Capture EVERY fetched listing's buyout price in fetch order (the search sorts price-asc, so
  // prices[0] is the cheapest). null-price listings are skipped but counted in dbg.nulls. This is
  // the whole price picture the page needs to compute min/median/high tiers -- additive to the
  // existing cheapest-listing fields (amount/currency), which stay exactly prices[0] as before.
  const prices = [];
  for (const L of listings) {
    const pr = L && L.listing && L.listing.price;
    if (pr && pr.amount != null) prices.push({ amount: pr.amount, currency: pr.currency });
    else if (dbg) dbg.nulls++;                            // this listing carried no buyout price
  }
  if (prices.length) {
    return { total, amount: prices[0].amount, currency: prices[0].currency, listingId: sres.id || null, prices };
  }
  return { total, amount: null, currency: null, listingId: sres.id || null, prices };   // results exist but no buyout price
}

// ---- serialize all trade work (one call at a time -> rate limiter is exact) ---
let _chain = Promise.resolve();
function serialize(fn) {
  const run = _chain.then(fn, fn);
  _chain = run.then(() => undefined, () => undefined);
  return run;
}

// ---- v1.1 per-item progress protocol -----------------------------------------
// `ctx` = { tabId, reqId } is built (in the message listener) ONLY when the request opted into
// protocolVersion >= 1.1 AND arrived from a tab. Progress is fire-and-forget: a closed tab or a
// missing receiver must never break pricing, so every send failure is swallowed.
function emitProgress(ctx, key, stage, detail) {
  if (!ctx || ctx.tabId == null) return;
  try {
    chrome.tabs.sendMessage(
      ctx.tabId,
      { type: "bpc-price-progress", reqId: ctx.reqId, key, stage, detail: detail || {} },
      () => { void chrome.runtime.lastError; }        // read lastError to silence "no receiver"
    );
  } catch (e) { /* no tabs API / receiver gone -> ignore */ }
}

// True when a version string/number is >= major.minor (compares major then minor; tolerant of
// "1.1", "1.1.0", the number 1.1, etc.). Used to version-gate progress emission.
function protoAtLeast(v, major, minor) {
  if (v == null) return false;
  const parts = String(v).split(".");
  let maj = parseInt(parts[0], 10); if (isNaN(maj)) maj = 0;
  let min = parseInt(parts[1], 10); if (isNaN(min)) min = 0;
  if (maj !== major) return maj > major;
  return min >= minor;
}

function snapshotDebug(dbg) {
  return { searchStatus: dbg.searchStatus, fetchStatus: dbg.fetchStatus, fetched: dbg.fetched, nulls: dbg.nulls };
}

async function priceMany(queries, league, ctx) {
  const results = [];
  const items = queries || [];

  // "queued" for every item up front (only when progress is enabled).
  if (ctx) for (const item of items) emitProgress(ctx, item.key, "queued", {});

  for (const item of items) {
    const emit = ctx ? (stage, detail) => emitProgress(ctx, item.key, stage, detail) : null;
    const dbg = { searchStatus: null, fetchStatus: null, fetched: 0, nulls: 0 };
    try {
      const r = await serialize(() => priceQuery(item.query, league, emit, dbg));
      results.push(Object.assign({ key: item.key }, r, { debug: snapshotDebug(dbg) }));
      if (emit) {
        if (r.amount != null) emit("done", { total: r.total, amount: r.amount, currency: r.currency });
        else emit("nobuyout", { total: r.total, fetched: dbg.fetched, nulls: dbg.nulls });
      }
    } catch (e) {
      const message = String(e && e.message ? e.message : e);
      const status = (e && e.status != null) ? e.status : null;
      results.push({ key: item.key, error: message, debug: snapshotDebug(dbg) });
      if (emit) emit("error", { message, status });
    }
  }
  return results;
}

// ---- message API (used by content script bridge AND the popup tester) --------
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return false;
  if (msg.type === "bpc-ping") {
    sendResponse({ ok: true, version: chrome.runtime.getManifest().version });
    return false;
  }
  if (msg.type === "bpc-price") {
    // Build a progress context only when the caller opted into v1.1 AND the request came from a
    // tab (content script). Popup-origin requests have no sender.tab -> ctx stays null -> progress
    // is silently skipped; old (< v1.1) sites likewise get no progress. The price-result reply is
    // unchanged for everyone (old site + new extension and vice versa keep working).
    let ctx = null;
    if (sender && sender.tab && sender.tab.id != null && protoAtLeast(msg.protocolVersion, 1, 1)) {
      ctx = { tabId: sender.tab.id, reqId: msg.reqId };
    }
    priceMany(msg.queries, msg.league, ctx)
      .then((results) => sendResponse({ results }))
      .catch((e) => sendResponse({ error: String(e && e.message ? e.message : e) }));
    return true;   // async sendResponse
  }
  if (msg.type === "bpc-reset-limits") {
    chrome.storage.local.remove(["rl_search", "rl_fetch"]).then(() => sendResponse({ ok: true }));
    return true;
  }
  return false;
});
