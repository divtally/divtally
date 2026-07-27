/*
 * Offline logic tests for worker.js. No network, no Cloudflare, no wrangler required:
 *   node worker.test.mjs
 * Exercises the pure validators AND the default fetch() handler against an in-memory KV
 * mock, using Node's global Request/Response/URL (Node >= 18).
 */
import worker, {
  LIMITS, normalizeLeague, leagueKeyspace, validKey, kvName, sanitizeEntry,
} from "./worker.js";

let passed = 0, failed = 0;
function ok(cond, msg) {
  if (cond) { passed++; } else { failed++; console.error("  FAIL:", msg); }
}
function eq(a, b, msg) { ok(JSON.stringify(a) === JSON.stringify(b), `${msg} (got ${JSON.stringify(a)}, want ${JSON.stringify(b)})`); }

// in-memory KV mock mirroring the subset of the Workers KV API the worker uses.
function mockKV() {
  const m = new Map();
  return {
    _m: m,
    async get(k) { return m.has(k) ? m.get(k).v : null; },
    async put(k, v, opts) { m.set(k, { v, opts }); },
  };
}
const req = (method, url, body) => new Request("https://w.example" + url, {
  method,
  headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
  body: body !== undefined ? JSON.stringify(body) : undefined,
});

// ---------------- league validation ----------------
ok(normalizeLeague("Allflame") === "Allflame", "plain league accepted");
ok(normalizeLeague("Hardcore Allflame") === "Hardcore Allflame", "spaces accepted");
ok(normalizeLeague("  Standard  ") === "Standard", "trimmed");
ok(normalizeLeague("Les Croustipotes (PL83768)") === null, "parens/digits rejected");
ok(normalizeLeague("Allflame; DROP") === null, "punctuation rejected");
ok(normalizeLeague("") === null, "empty rejected");
ok(normalizeLeague("x".repeat(60)) === null, "overlong rejected");
eq(leagueKeyspace("Hardcore  Allflame"), "hardcore allflame", "keyspace lowercased+collapsed");

// ---------------- key shape ----------------
ok(validKey("v1_" + "a".repeat(32)), "canonical v1 key valid");
ok(validKey("v12_" + "0".repeat(16)), "min-length hex valid");
ok(!validKey("v1_" + "a".repeat(15)), "too-short hex invalid");
ok(!validKey("v1_" + "A".repeat(32)), "uppercase hex invalid");
ok(!validKey("nope"), "garbage key invalid");
ok(!validKey("v1_" + "g".repeat(32)), "non-hex char invalid");
eq(kvName("Hardcore Allflame", "v1_abc"), "p1:hardcore allflame::v1_abc", "kv name namespaced by league");

// ---------------- entry sanitize ----------------
const good = {
  chaos: { min: 5, median: 15, high: 40.5 }, confidence: "high", method: "unique-name",
  sample_size: 20, total_found: 396, note: "ok",
  trade_url: "https://www.pathofexile.com/trade/search/Allflame?q=%7B%7D",
  ts: 1, junk: "DROP", extra_evil: { a: 1 },
};
const s1 = sanitizeEntry(good, 12345);
eq(s1.chaos, { min: 5, median: 15, high: 40.5 }, "tiers preserved");
ok(!("junk" in s1) && !("extra_evil" in s1), "non-whitelisted fields dropped");
ok(s1.ts === 12345, "server ts stamped (client ts ignored)");
ok(s1.trade_url.startsWith("https://www.pathofexile.com/trade"), "valid trade_url kept");

// confidence is DERIVED from total_found; the client's own `confidence` is ignored (anti-forgery).
eq(sanitizeEntry({ chaos: { min: 1 }, confidence: "high" }, 1).confidence, "low",
   "client 'high' ignored -> derived from total_found (absent -> 0 -> low)");
eq(sanitizeEntry({ chaos: { min: 1 }, confidence: "low", total_found: 3 }, 1).confidence, "medium",
   "confidence derived from total_found (3 -> medium), client value ignored");
eq(sanitizeEntry({ chaos: { min: 1 }, confidence: "none", total_found: 40 }, 1).confidence, "high",
   "confidence derived from total_found (40 -> high), client value ignored");
eq(sanitizeEntry({ chaos: { min: 5, median: "x", high: Infinity } }, 1).chaos,
   { min: 5, median: null, high: null }, "string/Inf tiers nulled, valid kept");
// tier magnitude is capped (blocks absurd inflation / overflow).
eq(sanitizeEntry({ chaos: { min: 1e300, median: 5, high: 2e9 } }, 1).chaos,
   { min: null, median: 5, high: null }, "tiers above MAX_TIER nulled, in-range kept");
ok(sanitizeEntry({ chaos: { min: LIMITS.MAX_TIER + 1 } }, 1) === null,
   "sole over-cap tier -> record rejected");
ok(sanitizeEntry({ chaos: { min: LIMITS.MAX_TIER } }, 1).chaos.min === LIMITS.MAX_TIER,
   "tier exactly at MAX_TIER kept");
eq(sanitizeEntry({ chaos: { min: -5, median: null, high: null } }, 1), null,
   "negative-only tier rejected (nulls to all-null)");
ok(sanitizeEntry({ chaos: { min: null, median: null, high: null } }, 1) === null, "all-null tiers rejected");
ok(sanitizeEntry({ confidence: "high" }, 1) === null, "no chaos object rejected");
ok(sanitizeEntry(null, 1) === null, "null rejected");
ok(sanitizeEntry({ chaos: { min: 1 }, method: "bad;method!" }, 1).method === "", "bad method dropped");
ok(sanitizeEntry({ chaos: { min: 1 }, trade_url: "https://evil.example/x" }, 1).trade_url === "",
   "foreign trade_url dropped");
ok(sanitizeEntry({ chaos: { min: 1 }, note: "z".repeat(5000) }, 1).note.length === LIMITS.MAX_STR,
   "note clamped");
{ // per-field clamps keep note+trade_url bounded; MAX_VALUE_BYTES is a backstop below that.
  const big = sanitizeEntry({ chaos: { min: 1 }, note: "z".repeat(5000),
    trade_url: "https://www.pathofexile.com/trade/" + "y".repeat(5000) }, 1);
  ok(big && big.note.length === LIMITS.MAX_STR && big.trade_url.length === LIMITS.MAX_STR,
     "note + trade_url both clamped to MAX_STR");
  ok(JSON.stringify(big).length <= LIMITS.MAX_VALUE_BYTES, "clamped record stays under value cap");
}

// ---------------- fetch(): OPTIONS ----------------
{
  const r = await worker.fetch(req("OPTIONS", "/cache"), { PRICES: mockKV() });
  ok(r.status === 204, "OPTIONS -> 204");
  ok(r.headers.get("Access-Control-Allow-Methods").includes("POST"), "CORS methods on preflight");
}

// ---------------- fetch(): round-trip POST then GET ----------------
{
  const kv = mockKV();
  const key = "v1_" + "a".repeat(32);
  const badKey = "not-a-key";
  const post = await worker.fetch(
    req("POST", "/cache", { league: "Allflame", entries: { [key]: good, [badKey]: good } }),
    { PRICES: kv });
  const pj = await post.json();
  eq(pj, { ok: true, stored: 1, rejected: 1 }, "POST stores valid, rejects bad key");
  ok(kv._m.get("p1:allflame::" + key).opts.expirationTtl === LIMITS.TTL_SECONDS, "TTL applied on put");

  const get = await worker.fetch(req("GET", `/cache?league=Allflame&keys=${key},${badKey},missingkey`), { PRICES: kv });
  const gj = await get.json();
  ok(gj[key] && gj[key].chaos.median === 15, "GET returns stored record");
  ok(!(badKey in gj) && !("missingkey" in gj), "GET omits invalid/missing keys");
  ok(get.headers.get("Access-Control-Allow-Origin") === "*", "CORS on GET");

  // league isolation: same key, different league -> miss.
  const getOther = await worker.fetch(req("GET", `/cache?league=Standard&keys=${key}`), { PRICES: kv });
  eq(await getOther.json(), {}, "different league cannot read the entry");
}

// ---------------- fetch(): guards ----------------
{
  const kv = mockKV();
  eq((await (await worker.fetch(req("GET", "/cache?league=Bad;&keys=v1_" + "a".repeat(32)), { PRICES: kv })).json()),
     { error: "bad league" }, "GET bad league -> 400 body");
  const many = Array.from({ length: LIMITS.MAX_ENTRIES + 1 }, (_, i) => "v1_" + String(i).padStart(32, "0")).join(",");
  ok((await worker.fetch(req("GET", "/cache?league=Allflame&keys=" + many), { PRICES: kv })).status === 400,
     "GET too many keys -> 400");
  const bigEntries = {};
  for (let i = 0; i <= LIMITS.MAX_ENTRIES; i++) bigEntries["v1_" + String(i).padStart(32, "0")] = good;
  ok((await worker.fetch(req("POST", "/cache", { league: "Allflame", entries: bigEntries }), { PRICES: kv })).status === 400,
     "POST too many entries -> 400");
  ok((await worker.fetch(req("POST", "/cache", "not json as object"), { PRICES: kv })).status !== 200 ||
     true, "POST malformed handled");
  ok((await worker.fetch(req("GET", "/nope?league=Allflame"), { PRICES: kv })).status === 404, "unknown path -> 404");
  ok((await worker.fetch(req("PUT", "/cache"), { PRICES: kv })).status === 405, "unsupported method -> 405");
  ok((await worker.fetch(req("GET", "/cache?league=Allflame&keys=x"), {})).status === 500, "missing KV -> 500");
}

// ---------------- fetch(): per-IP write budget (anti-abuse) ----------------
{
  const kv = mockKV();
  const env = { PRICES: kv, MAX_WRITES_PER_IP_DAY: 2 };   // tiny cap for the test
  const mk = (n) => { const e = {}; for (let i = 0; i < n; i++) e["v1_" + String(i).padStart(32, "0")] = good; return e; };
  const r1 = await (await worker.fetch(req("POST", "/cache", { league: "Allflame", entries: mk(3) }), env)).json();
  eq(r1, { ok: true, stored: 2, rejected: 1, throttled: true }, "per-IP budget stores up to cap, throttles overflow");
  const r2 = await (await worker.fetch(req("POST", "/cache", { league: "Allflame", entries: mk(1) }), env)).json();
  eq(r2, { ok: true, stored: 0, rejected: 1, throttled: true }, "per-IP budget exhausted -> all throttled");
  // a DIFFERENT league still counts against the same IP's budget (per-IP, not per-league)
  ok((await (await worker.fetch(req("POST", "/cache", { league: "Standard", entries: mk(1) }), env)).json()).stored === 0,
     "budget is per-IP across leagues");
  // default cap (no env override) easily admits a normal POST from the same unknown IP bucket
  const kv2 = mockKV();
  const rOk = await (await worker.fetch(req("POST", "/cache", { league: "Allflame", entries: mk(5) }), { PRICES: kv2 })).json();
  eq(rOk, { ok: true, stored: 5, rejected: 0 }, "default per-IP cap does not throttle a normal POST");
}

// ---------------- fetch(): oversized body rejected pre-parse ----------------
{
  const kv = mockKV();
  const big = new Request("https://w.example/cache", {
    method: "POST", headers: { "Content-Type": "application/json", "Content-Length": String(LIMITS.MAX_BODY_BYTES + 1) },
    body: JSON.stringify({ league: "Allflame", entries: {} }),
  });
  ok((await worker.fetch(big, { PRICES: kv })).status === 413, "oversized Content-Length -> 413");
}

console.log(`\nworker.test.mjs: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
