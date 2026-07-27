# Public community price cache — Worker + owner-PC seeder

Implementation notes for B-001 / D-0008. Two deliverables:

- `public/worker/worker.js` (+ `wrangler.toml`, `package.json`, `worker.test.mjs`) —
  a Cloudflare Worker backed by Workers KV that stores per-item price records for a short
  TTL so popular builds render fully priced for visitors with nothing installed.
- `tools/seed_cache.py` — the owner-PC job that prices the top-N poe.ninja builds with the
  existing local engine and POSTs the records to the Worker.

**Hard invariant (B-001):** the SITE and the WORKER never call `pathofexile.com`. Prices are
produced ONLY on real machines — today the owner-PC seeder, later extension users — and
POSTed into the cache. The Worker is a dumb, validated store; it never prices anything.

---

## 1. THE CACHE KEY RECIPE  (authoritative — site, extension, and seeder MUST agree)

A cache key is a **stable hash of `(league + item identity)`**. The Worker does **not**
compute keys (clients do), so a recipe bump never needs a Worker redeploy — the Worker only
validates key *shape* and namespaces every key by league.

```
key = "v1_" + sha256_hex( league_keyspace + "\x1d" + item_identity )[0:32]
```

- `\x1d` (GS), `\x1e` (RS), `\x1f` (US) are ASCII separators that never occur in mod text.
- `league_keyspace(league)` = NFC-normalise, trim, lowercase, collapse internal whitespace
  to single spaces. (e.g. `"Hardcore  Allflame"` -> `"hardcore allflame"`.)
- `sha256_hex(...)[0:32]` = first 32 lowercase hex chars of the UTF-8 SHA-256 digest.
- Version prefix `v1_`. Bump to `v2_` etc. if the identity fields ever change.

### item_identity — built ONLY from engine->UI contract fields

Identity uses **only fields the browser already has** (the `web.py` skeleton row a visitor
receives), so a visitor computes the identical key from the same build data. It deliberately
**excludes slot** (price is slot-independent) and is **exact on rolls** (the seeder and the
visitor view the identical poe.ninja build → equal items hash equal; cross-build accidental
matches are a harmless bonus, never required).

**Gems** (`category == "gem"`):
```
identity = join(US, [
  "gem",
  canon(name),                          # display name, e.g. "Ethereal Knives of the Massacre"
  "L" + int(level),
  "Q" + int(quality),
  ("c" if corrupted else "n"),
  join("|", sort([                      # every support gem, sorted
     canon(sname) + "~L" + int(slvl) + "~Q" + int(squal) + "~" + ("c" if scorr else "n")
     for each support ]))
])
```

**Everything else** (unique / rare / magic / normal gear, flasks, jewels):
```
identity = join(US, [
  category,                             # lowercased: "unique" | "rare" | "magic" | "normal"
  canon(name),                          # display name incl. base, e.g. "Maloney's Mechanism, Ornate Quiver"
  join(RS, sort([ canon(m) for m in mods.implicit ])),
  join(RS, sort([ canon(m) for m in mods.explicit ]))
])
```

- `canon(s)` = `s.normalize("NFC").trim()`. Mod strings the browser receives are already
  `strip_rich`+`.strip()`'d by `web.py`; the seeder applies the same in `contract_from_item`,
  and `canon` is idempotent on them.
- **Sort order:** identity strings are ASCII in practice (English mods / unique names). Python
  `sorted()` (code-point order) and JS `Array.sort((a,b)=>a<b?-1:a>b?1:0)` agree for ASCII and
  for all BMP characters; they can only diverge on astral-plane code points (never seen in mods).

### Reference implementations

- **Python** — `tools/seed_cache.py`: `cache_key`, `item_identity`, `league_keyspace`,
  `contract_from_item` (the last mirrors `web.py`'s skeleton-row builder so live-seeding and
  `--from-cache-only` share one recipe).
- **JavaScript** (drop into the site's `core.js` and the extension — verified byte-identical
  to the Python, see §5):

```js
import { createHash } from "node:crypto"; // in-browser: use crypto.subtle.digest("SHA-256", ...)
const US = "\x1f", RS = "\x1e", GS = "\x1d";
const canon = (s) => (s || "").normalize("NFC").trim();
const leagueKeyspace = (l) => canon(l).toLowerCase().split(/\s+/).join(" ");
const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

function itemIdentity(it) {
  const cat = (it.category || "").toLowerCase();
  const name = canon(it.name || "");
  if (cat === "gem") {
    const sup = (it.supports || []).map((s) =>
      `${canon(s.name||"")}~L${parseInt(s.level||0)}~Q${parseInt(s.quality||0)}~${s.corrupted?"c":"n"}`
    ).sort(cmp);
    return ["gem", name, `L${parseInt(it.level||0)}`, `Q${parseInt(it.quality||0)}`,
            it.corrupted?"c":"n", sup.join("|")].join(US);
  }
  const mods = it.mods || {};
  const impl = (mods.implicit || []).map(canon).sort(cmp);
  const expl = (mods.explicit || []).map(canon).sort(cmp);
  return [cat, name, impl.join(RS), expl.join(RS)].join(US);
}
// browser: async because crypto.subtle.digest is async
async function cacheKey(league, it) {
  const material = leagueKeyspace(league) + GS + itemIdentity(it);
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(material));
  const hex = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
  return "v1_" + hex.slice(0, 32);
}
```

**Which league string?** Everyone keys on the build's **display league** (`meta.league`,
e.g. `"Allflame"`) — the value the browser already holds and the seeder reads from the build.
The seeder POSTs `league = meta.league`; the site GETs `?league=<meta.league>`; the Worker
namespaces KV by `leagueKeyspace(league)`. All three line up.

---

## 2. Worker HTTP API (`public/worker/worker.js`)

Path is `/cache`. CORS is open (`*`) for GET, POST, OPTIONS. KV binding = `PRICES`.

| Method | Request | Response |
|---|---|---|
| `OPTIONS /cache` | preflight | `204` + CORS |
| `GET /cache?league=<L>&keys=k1,k2,...` | up to 60 keys | `{ "<key>": <record>, ... }` (found keys only) |
| `POST /cache` | `{ league, entries: { "<key>": <record>, ... } }` (≤60) | `{ ok, stored, rejected[, throttled] }` |

`throttled: true` appears on a POST when the per-IP daily write budget clipped some/all entries
(see Guards); those keys are counted in `rejected`.

**Stored record** (subset of `web.py::_result_dict`, whitelisted):
```json
{ "chaos": {"min": 5.0, "median": 15.0, "high": 15.0},
  "confidence": "high", "method": "unique-name",
  "sample_size": 20, "total_found": 396,
  "note": "", "trade_url": "https://www.pathofexile.com/trade/...",
  "ts": 1753660000 }
```
The site folds a fetched record's `chaos` tiers into the build's row totals client-side, exactly
like the whisper-paste path (backlog B-001). Divine display is derived on the client from its
own chaos→divine rate; the cache stores chaos only.

**`confidence` is DERIVED, not accepted.** Because the cache is an OPEN store (anyone who knows
the public recipe can POST — that is how the extension shares results back), the Worker recomputes
`confidence` from `total_found` server-side (`≥5 high, ≥2 medium, else low`) and ignores whatever
the client sent — so a poisoned entry can't forge a "high" trust signal independent of its sample.
The **site** goes further and renders every cache-sourced number as **"community · unverified"**
with a neutral dot (never the green verified-price dot), so a forged listing count can't dress up
as a checked price (`index.html` tooltip + `core.js` cache note).

### Guards (see `LIMITS` in `worker.js`)
- **League:** `^[A-Za-z][A-Za-z ]{0,49}$` — letters + spaces only. Rejects private/event
  leagues (`"… (PL83768)"`), injection, empties, overlong. Bogus league → `400 {"error":"bad league"}`.
- **Per-request cap:** ≤ `MAX_ENTRIES` (60) keys per GET / entries per POST → else `400`.
- **Key shape:** `^v[0-9]{1,3}_[0-9a-f]{16,64}$`. Invalid keys are silently dropped from a GET
  and counted in `rejected` on a POST.
- **League isolation:** stored KV name = `"p1:" + leagueKeyspace + "::" + key`, so a forged key
  can never read another league's space (verified: a `Standard` GET can't see an `Allflame` entry).
- **Value validation** (`sanitizeEntry`): requires a `chaos` object with ≥1 finite non-negative
  tier; only whitelisted fields survive; **`confidence` is DERIVED from `total_found`** server-side
  (`≥5 high, ≥2 medium, else low`) — the client's `confidence` is ignored (anti-forgery); each
  chaos tier is **capped at `MAX_TIER` (1e8)** and nulled above it (blocks absurd inflation /
  overflow); `method` must match `^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$` else dropped;
  `note`/`trade_url` clamped to 512 chars; `trade_url` kept only if it starts with
  `https://www.pathofexile.com/trade`; **`ts` is server-stamped** (a client cannot
  back/forward-date); whole record capped at `MAX_VALUE_BYTES` (2048) as a backstop.
- **Per-IP write budget (anti-abuse):** a soft daily cap (`MAX_WRITES_PER_IP_DAY`, default 600,
  override via the `MAX_WRITES_PER_IP_DAY` Worker var) tracked in a day-bucketed, TTL'd KV counter
  keyed on `CF-Connecting-IP`. Stops one scripted client from draining the KV free-tier daily
  **write quota** in ~17 POSTs (the pre-fix DoS). A POST that hits the cap returns
  `{ok:true, stored:0, rejected:N, throttled:true}`. Sized to admit one owner-seeder run (~350
  entries) with headroom. A DISTRIBUTED flood is still possible — inherent to a keyless open cache
  on the free tier; the cache is best-effort and the site degrades to trade links / whisper-paste,
  so this is a bar-raiser, not a wall. **[NOT FROM SOURCE — Cloudflare's ~1,000 writes/day &
  ~100,000 reads/day free-tier limits are Cloudflare's public figures, not derived from this repo;
  the ~17-POST math follows from them.]**
- **Body guard:** a POST with `Content-Length > MAX_BODY_BYTES` (256 KiB) is rejected `413` before
  JSON parsing (the count check would otherwise happen post-parse).
- **TTL:** every `KV.put` uses `expirationTtl: 86400` (24h) — a short-lived community cache. The
  per-IP counter uses the same TTL.

---

## 3. Deploy the Worker (owner, one time)

`public/worker/wrangler.toml` carries a `REPLACE_ME` KV id. Steps:
```
cd public/worker
npm i -g wrangler            # or npx wrangler ...
wrangler login
wrangler kv namespace create PRICES      # prints id="..."  -> paste into wrangler.toml
# optional, for `wrangler dev`:
wrangler kv namespace create PRICES --preview   # -> paste into preview_id
wrangler deploy
# endpoint: https://poe1-price-cache.<your-subdomain>.workers.dev/cache
```
Put that endpoint in the site config and pass it to the seeder as `--worker-url`.

---

## 4. Seeder (`tools/seed_cache.py`)

Runs on the owner's PC. Fetches the top-N (default 15) poe.ninja builds via the ladder
(`research/probe_ninja.py` helpers — **poe.ninja only, never trade**), prices each with the
existing engine (honouring its persistent rate limiter + disk cache), extracts per-item
records, and POSTs them in ≤60-key batches.

```
python tools/seed_cache.py --dry-run [-n N] [--league SLUG]
    List the top-N builds that WOULD be priced. Hits poe.ninja for the ladder only;
    prices nothing, POSTs nothing.

python tools/seed_cache.py --from-cache-only [--out FILE] [--league SLUG] [--worker-url URL]
    ZERO trade calls, zero poe.ninja calls: scans the local disk cache for already-priced
    builds (`result:poeninja:char:*`), rebuilds records + keys, and either writes the POST
    payloads to --out (inspect) and/or uploads them to --worker-url.

python tools/seed_cache.py --worker-url https://poe1-price-cache.<sub>.workers.dev/cache [-n N]
    LIVE seed. The DEFAULT mode. run_estimate() drives the trade API (rate-limited) for each
    build, then POSTs. This is the ONLY trade-touching path in the whole public system.
```

- `--worker-url` accepts the base or the full `/cache` endpoint (`/cache` is appended if absent).
- `--delay` (default 3s) paces live seeding between builds.
- UTF-8 stdout is forced so non-ASCII build/account names (common — see `docs/research`) print
  instead of crashing the Windows console.

**Record extraction:** a build's item is stored only if its price has ≥1 finite chaos tier.
Skipped / unpriceable rows carry no number and therefore no cache entry — the same
"unpriceable ⇒ trade link, never a misleading number" guarantee the rest of the app honours.

---

## 5. Verification (offline; no trade calls, no live seed)

Per the task's hard rule I did **not** run a live seed (default mode) and did **not** call
`pathofexile.com` from anything. What ran:

1. **Worker logic — `node public/worker/worker.test.mjs` → 55 passed, 0 failed.** Exercises
   the pure validators AND the default `fetch()` handler end-to-end against an in-memory KV
   mock (Node global `Request`/`Response`/`URL`): league accept/reject, key-shape, entry
   sanitize (whitelist/clamp/server-ts/size, **server-derived confidence**, **tier magnitude
   cap**), OPTIONS preflight, POST→GET round-trip, league isolation, the **per-IP write budget**
   (throttle + budget-per-IP-across-leagues), the **413 body guard**, and every earlier guard
   (bad league/json/entries, over-cap, missing KV, 404/405).
   *`wrangler dev` was skipped deliberately — it needs network/login; the mock-KV harness is a
   stricter offline check.*
2. **Seeder `--from-cache-only`** against the one real cached build on disk
   (`example-0416/TestCharacter`, Allflame): 41 items → **23 priced records** extracted
   (18 skipped/unpriceable rows correctly omitted), payloads written, **no network**.
3. **Seeder `--dry-run -n 5`**: resolved league via poe.ninja index-state, fetched the ladder
   (poe.ninja protobuf), listed 5 builds including a Cyrillic name — poe.ninja only, no trade.
4. **Cross-parity harness** (JS reimplementation of the recipe using `node:crypto` vs the
   Python `cache_key`, over all 41 items of the cached build): **41/41 keys byte-identical**,
   and **23/23 priced records accepted by the Worker's own `sanitizeEntry`** — proving
   site/extension (JS) ↔ seeder (Python) ↔ Worker all agree.

### Owner smoke test after deploy (optional)
```
# after wrangler deploy + a real --worker-url seed, or a manual POST:
curl "https://poe1-price-cache.<sub>.workers.dev/cache?league=Allflame&keys=v1_<hex>"
```

---

## 6. Open follow-ups (not blockers)
- Wire the JS `cacheKey`/`itemIdentity` (§1) into the site's `core.js` and the extension, and
  add a `--worker-url` to the scheduled owner-PC seed task (GOING-PUBLIC.md).
- The extension's POST-back path (deferred per B-001) reuses this exact recipe + Worker API.
- Consider a `v2_` identity that folds `max_link` in if 6L-vs-4L rare collisions ever matter
  (today rares are priced by mods; links only add a filter at `max_link >= 5`).
