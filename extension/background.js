/* PoE2 Build Price Checker - Trade Bridge : background service worker.
 *
 * Performs the official trade2 search+fetch on the USER'S machine/IP (extensions with
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

const BASE = "https://www.pathofexile.com/api/trade2";
const REALM = "poe2";

// Conservative starting rules per endpoint: [maxHits, windowSeconds]. We only ever TIGHTEN
// these from the authoritative X-Rate-Limit-Ip header. Mirrors _DEFAULT_RULES in trade.py.
const DEFAULT_RULES = {
  search: [[5, 10], [15, 60], [30, 300]],
  fetch:  [[12, 4], [16, 12]],
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
  return { rules: st.rules || DEFAULT_RULES[bucket], hits: st.hits || [] };
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
// so reads/writes of the persisted window never race.
async function rateLimitGate(bucket) {
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
  if (sleep > 0) await delay(sleep + 100 + Math.floor(Math.random() * 200));

  hits = st.hits.filter((t) => Date.now() - t <= maxWinMs);
  hits.push(Date.now());
  await rlSet(bucket, { rules: st.rules, hits });
}

async function applyHeaderRules(bucket, header) {
  const rules = mergeRules(bucket, header);
  if (!rules) return;
  const st = await rlGet(bucket);
  await rlSet(bucket, { rules, hits: st.hits });
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
async function tradeRequest(bucket, method, url, body, attempt) {
  attempt = attempt || 0;
  await rateLimitGate(bucket);

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
    if (attempt < 2) { await delay(2000 + attempt * 2000); return tradeRequest(bucket, method, url, body, attempt + 1); }
    throw new Error("network error calling trade API: " + (e && e.message ? e.message : e));
  }
  clearTimeout(to);

  await applyHeaderRules(bucket, r.headers.get("X-Rate-Limit-Ip"));

  if (r.status === 429) {
    let retry = parseRetryAfter(r.headers.get("Retry-After"));
    if (retry == null) retry = Math.max.apply(null, DEFAULT_RULES[bucket].map((x) => x[1]));
    retry = Math.max(5, Math.min(retry, 1800));
    await delay(retry * 1000 + 1000);
    if (attempt < 1) return tradeRequest(bucket, method, url, body, attempt + 1);
    throw new Error("repeatedly rate-limited by trade API; try again later");
  }
  if (r.status >= 500 && r.status <= 504 && attempt < 2) {
    await delay(3000 + attempt * 3000);
    return tradeRequest(bucket, method, url, body, attempt + 1);
  }
  if (!r.ok) {
    const txt = await r.text().catch(() => "");
    throw new Error("HTTP " + r.status + " from trade API" + (txt ? ": " + txt.slice(0, 160) : ""));
  }
  const ct = r.headers.get("content-type") || "";
  if (ct.indexOf("json") === -1) throw new Error("non-JSON response from trade API");
  return r.json();
}

// ---- search + fetch -> cheapest listing --------------------------------------
async function priceQuery(query, league) {
  if (!league) throw new Error("missing league");
  if (!query) throw new Error("missing query");
  const sUrl = BASE + "/search/" + REALM + "/" + encodeURIComponent(league);
  const sres = await tradeRequest("search", "POST", sUrl, { query, sort: { price: "asc" } });
  const ids = (sres.result || []).slice(0, 10);          // API caps fetch at 10 ids
  const total = (sres.total != null) ? sres.total : (sres.result ? sres.result.length : 0);
  if (!ids.length) return { total: 0, amount: null, currency: null, listingId: sres.id || null };

  const fUrl = BASE + "/fetch/" + ids.join(",") + "?query=" + encodeURIComponent(sres.id) + "&realm=" + REALM;
  const fres = await tradeRequest("fetch", "GET", fUrl);
  for (const L of (fres.result || [])) {
    const pr = L && L.listing && L.listing.price;
    if (pr && pr.amount != null) {
      return { total, amount: pr.amount, currency: pr.currency, listingId: sres.id || null };
    }
  }
  return { total, amount: null, currency: null, listingId: sres.id || null };   // results exist but no buyout price
}

// ---- serialize all trade work (one call at a time -> rate limiter is exact) ---
let _chain = Promise.resolve();
function serialize(fn) {
  const run = _chain.then(fn, fn);
  _chain = run.then(() => undefined, () => undefined);
  return run;
}

async function priceMany(queries, league) {
  const results = [];
  for (const item of (queries || [])) {
    try {
      const r = await serialize(() => priceQuery(item.query, league));
      results.push(Object.assign({ key: item.key }, r));
    } catch (e) {
      results.push({ key: item.key, error: String(e && e.message ? e.message : e) });
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
    priceMany(msg.queries, msg.league)
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
