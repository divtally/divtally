/*
 * Community price cache — Cloudflare Worker (PoE1 Build Price Checker, B-001).
 *
 * PURPOSE
 *   A tiny shared key/value cache so a popular build's already-priced rares/uniques/gems
 *   render for every visitor with nothing installed. It is a DUMB store: it never calls
 *   pathofexile.com or poe.ninja, never prices anything, and never trusts the client's
 *   numbers beyond shape/size validation. Prices are produced ONLY on real machines
 *   (the owner-PC seeder in tools/seed_cache.py; later, extension users) and POSTed here.
 *
 * ENDPOINTS  (path = /cache ; CORS open for GET+POST+OPTIONS)
 *   GET  /cache?league=<name>&keys=k1,k2,...   -> { "<key>": <record>, ... }  (found keys only)
 *   POST /cache   body { league, entries: { "<key>": <record>, ... } }
 *                                              -> { ok, stored, rejected }
 *   OPTIONS /cache                             -> 204 preflight
 *
 * KEY RECIPE (authoritative copy: docs/notes-public-worker.md; mirrored in
 *   tools/seed_cache.py::cache_key and, on the site/extension, in JS). The WORKER does
 *   NOT compute keys — clients do — so a recipe bump never requires a redeploy. The worker
 *   only validates key SHAPE (KEY_RE) and namespaces every stored key by league.
 *     key = "v1_" + sha256_hex( leagueKeyspace(league) + "\x1d" + item_identity )[:32]
 *
 * RECORD SHAPE stored per key (a subset of the engine's per-item price dict):
 *     { chaos:{min,median,high}, confidence, method, sample_size, total_found,
 *       note, trade_url, ts }   — numeric tiers, whitelisted fields, <= MAX_VALUE_BYTES.
 *
 * TRUST HARDENING (this is an OPEN cache — anyone who knows the recipe can POST). To keep a
 * poisoned entry from forging a trust signal or exhausting the free tier:
 *   • `confidence` is DERIVED here from `total_found` (the client's `confidence` is ignored),
 *     so an entry cannot claim "high" independent of its sample. (The site additionally shows
 *     every cache-sourced number as "community · unverified", never as a verified price.)
 *   • each chaos tier is capped at LIMITS.MAX_TIER (blocks absurd inflation / overflow).
 *   • a soft per-IP daily write budget (LIMITS.MAX_WRITES_PER_IP_DAY, override with the
 *     MAX_WRITES_PER_IP_DAY Worker var) stops one scripted client from draining the KV
 *     free-tier write quota. A distributed flood is still possible (inherent to a keyless
 *     open cache on the free tier); the cache is best-effort and the site degrades to trade
 *     links / whisper-paste, so this is a bar-raiser, not a wall.
 *
 * KV binding: PRICES (see wrangler.toml). Stored KV name = "p1:" + leagueKeyspace + "::" + key
 *   so a forged key can never read another league's space.
 */

export const LIMITS = {
  MAX_ENTRIES: 60,        // per POST body, and per GET keys list
  MAX_VALUE_BYTES: 2048,  // serialized cap per stored record
  MAX_STR: 512,           // per-string field cap (note / trade_url)
  MAX_TIER: 1e8,          // sanity cap per chaos tier — no single PoE1 item approaches 100M
                          // chaos; blocks absurd inflation / Infinity-adjacent overflow.
  MAX_BODY_BYTES: 262144, // reject obviously-oversized POST bodies (256 KiB) before parsing.
  // Soft per-IP daily write budget (entries, not requests). Sized to fit one owner-seeder run
  // (~350 entries) with headroom; bounds a single scripted client well under the KV free-tier
  // daily write quota. Override per-deployment with the MAX_WRITES_PER_IP_DAY Worker var.
  MAX_WRITES_PER_IP_DAY: 600,
  TTL_SECONDS: 86400,     // 24h KV expirationTtl (short-lived community cache)
  // Leagues are trade league names: letters + spaces only (e.g. "Allflame",
  // "Hardcore Allflame", "Standard"). Rejects private/event leagues with digits/parens.
  LEAGUE_RE: /^[A-Za-z][A-Za-z ]{0,49}$/,
  // Client cache keys: "v<n>_" + lowercase hex (see recipe). 16..64 hex future-proofs the length.
  KEY_RE: /^v[0-9]{1,3}_[0-9a-f]{16,64}$/,
};

// pricing.py method strings: "unique-name", "rare-mods-base", "skill", "magic-base", ...
const METHOD_RE = /^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$/;

// --- pure, testable helpers (imported by worker.test.mjs) --------------------

export function normalizeLeague(raw) {
  if (typeof raw !== "string") return null;
  const s = raw.trim();
  return LIMITS.LEAGUE_RE.test(s) ? s : null;
}

// The league form used for the KV namespace + the key recipe: lowercased, whitespace-collapsed.
// MUST match tools/seed_cache.py::_league_keyspace and the site/extension JS exactly.
export function leagueKeyspace(league) {
  return String(league).trim().toLowerCase().split(/\s+/).join(" ");
}

export function validKey(k) {
  return typeof k === "string" && LIMITS.KEY_RE.test(k);
}

export function kvName(league, key) {
  return "p1:" + leagueKeyspace(league) + "::" + key;
}

function num(x) {
  // finite, non-negative, and within the sanity cap (blocks absurd/overflow inflation).
  return (typeof x === "number" && isFinite(x) && x >= 0 && x <= LIMITS.MAX_TIER) ? x : null;
}
function clampStr(x) {
  if (typeof x !== "string") return "";
  return x.length > LIMITS.MAX_STR ? x.slice(0, LIMITS.MAX_STR) : x;
}
function nonNegInt(x) {
  return (Number.isInteger(x) && x >= 0) ? x : 0;
}
// Confidence is DERIVED server-side from total_found; the client's own `confidence` is IGNORED
// so a poisoned entry cannot forge a "high" signal. Matches docs/public-contract.md §3 and
// core.js confFromTotal: >=5 -> high, >=2 -> medium, else low.
function confFromTotal(total) {
  const t = nonNegInt(total);
  return t >= 5 ? "high" : t >= 2 ? "medium" : "low";
}

// Validate + sanitize one incoming record into a stored record, or null if it fails a hard
// check (no tiers object, no finite tier, oversize). Only whitelisted fields survive; the
// server stamps `ts` so a client cannot backdate/forward-date an entry.
export function sanitizeEntry(raw, now) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const chaos = raw.chaos;
  if (!chaos || typeof chaos !== "object" || Array.isArray(chaos)) return null;
  const total_found = nonNegInt(raw.total_found);
  const clean = {
    chaos: { min: num(chaos.min), median: num(chaos.median), high: num(chaos.high) },
    confidence: confFromTotal(total_found),   // server-derived; client `confidence` ignored
    method: (typeof raw.method === "string" && METHOD_RE.test(raw.method)) ? raw.method : "",
    sample_size: nonNegInt(raw.sample_size),
    total_found: total_found,
    note: clampStr(raw.note),
    trade_url: "",
    ts: (typeof now === "number") ? now : Math.floor(Date.now() / 1000),
  };
  // trade_url only kept if it points at the official trade site (defends the "link, not a
  // misleading number" guarantee and blocks arbitrary URL injection).
  if (typeof raw.trade_url === "string" &&
      raw.trade_url.startsWith("https://www.pathofexile.com/trade")) {
    clean.trade_url = clampStr(raw.trade_url);
  }
  // Worth storing only if at least one finite chaos tier survived.
  if (clean.chaos.min === null && clean.chaos.median === null && clean.chaos.high === null)
    return null;
  if (JSON.stringify(clean).length > LIMITS.MAX_VALUE_BYTES) return null;
  return clean;
}

// --- HTTP plumbing -----------------------------------------------------------

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};

function jsonResponse(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

// Best-effort client IP for the per-IP write budget. CF-Connecting-IP is stamped by the
// Cloudflare edge; the X-Forwarded-For fallback covers local/dev. "?" groups the unknowns.
function clientIp(request) {
  const h = request.headers;
  const ip = h.get("CF-Connecting-IP") || (h.get("X-Forwarded-For") || "").split(",")[0].trim();
  return ip || "?";
}
function ipWriteCap(env) {
  const v = Number(env && env.MAX_WRITES_PER_IP_DAY);
  return (Number.isFinite(v) && v > 0) ? v : LIMITS.MAX_WRITES_PER_IP_DAY;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS")
      return new Response(null, { status: 204, headers: CORS });

    if (url.pathname !== "/cache")
      return jsonResponse({ error: "not found" }, 404);

    const KV = env && env.PRICES;
    if (!KV) return jsonResponse({ error: "cache not configured" }, 500);

    // ---- GET: bulk read ----
    if (request.method === "GET") {
      const league = normalizeLeague(url.searchParams.get("league"));
      if (!league) return jsonResponse({ error: "bad league" }, 400);
      const rawKeys = (url.searchParams.get("keys") || "")
        .split(",").map((s) => s.trim()).filter(Boolean);
      if (rawKeys.length === 0) return jsonResponse({});
      if (rawKeys.length > LIMITS.MAX_ENTRIES)
        return jsonResponse({ error: "too many keys" }, 400);
      const keys = [...new Set(rawKeys)].filter(validKey);
      const out = {};
      await Promise.all(keys.map(async (k) => {
        const v = await KV.get(kvName(league, k));
        if (v != null) { try { out[k] = JSON.parse(v); } catch (_e) { /* skip corrupt */ } }
      }));
      return jsonResponse(out);
    }

    // ---- POST: bulk write ----
    if (request.method === "POST") {
      const clen = parseInt(request.headers.get("Content-Length") || "0", 10);
      if (Number.isFinite(clen) && clen > LIMITS.MAX_BODY_BYTES)
        return jsonResponse({ error: "body too large" }, 413);
      let body;
      try { body = await request.json(); } catch (_e) { return jsonResponse({ error: "bad json" }, 400); }
      const league = normalizeLeague(body && body.league);
      if (!league) return jsonResponse({ error: "bad league" }, 400);
      const entries = body && body.entries;
      if (!entries || typeof entries !== "object" || Array.isArray(entries))
        return jsonResponse({ error: "bad entries" }, 400);
      const keys = Object.keys(entries);
      if (keys.length === 0) return jsonResponse({ ok: true, stored: 0, rejected: 0 });
      if (keys.length > LIMITS.MAX_ENTRIES)
        return jsonResponse({ error: "too many entries" }, 400);
      const now = Math.floor(Date.now() / 1000);

      // Soft per-IP daily write budget (anti-abuse; see header). Counter is itself a KV entry
      // under a private namespace, day-bucketed, TTL'd — approximate under KV eventual
      // consistency, which is fine for a bar-raiser.
      const cap = ipWriteCap(env);
      const ipKey = "p1:ipw:" + Math.floor(now / LIMITS.TTL_SECONDS) + ":" + clientIp(request);
      let used = parseInt((await KV.get(ipKey)) || "0", 10);
      if (!Number.isFinite(used) || used < 0) used = 0;
      const budget = Math.max(0, cap - used);
      if (budget === 0)
        return jsonResponse({ ok: true, stored: 0, rejected: keys.length, throttled: true });

      const writable = keys.slice(0, budget);       // overflow beyond the budget is throttled
      const throttled = keys.length - writable.length;
      let stored = 0, rejected = 0;
      await Promise.all(writable.map(async (k) => {
        if (!validKey(k)) { rejected++; return; }
        const clean = sanitizeEntry(entries[k], now);
        if (!clean) { rejected++; return; }
        await KV.put(kvName(league, k), JSON.stringify(clean),
          { expirationTtl: LIMITS.TTL_SECONDS });
        stored++;
      }));
      if (stored > 0)
        await KV.put(ipKey, String(used + stored), { expirationTtl: LIMITS.TTL_SECONDS });
      const resp = { ok: true, stored, rejected: rejected + throttled };
      if (throttled > 0) resp.throttled = true;
      return jsonResponse(resp);
    }

    return jsonResponse({ error: "method not allowed" }, 405);
  },
};
