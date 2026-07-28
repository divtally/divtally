# R1 — API end-to-end contract-conformance + robustness audit (LIVE)

**Round:** 1 of the D-0020 five-round bug campaign. **Lens:** contract-conformance + robustness of
the **live** API (`https://divtally.vercel.app`), no build-specific pricing correctness (that is R3).
**Date:** 2026-07-27. **Auditor:** subagent (containment: only this repo; no pathofexile.com calls).

**Method:** machine-validation of `public-contract.md` against live responses. Fetched the 2 owner
builds via `GET /api/build`; validated every documented field (presence / type / enum / additive
guarantees / `schema_version`). Ran the full error matrix (bad URL, PoE2 link, overview link,
nonexistent char, empty, oversized, invalid-base64 PoB, malformed-JSON body) checking shape + HTTP
status + headers + stack-trace leakage. Verified CORS + Cache-Control on success **and** error +
OPTIONS preflight at the raw-wire level. Cross-checked against **poe.ninja raw truth** (character
item counts, unique prices, divine rate). Validator + raw captures:
`scratchpad/r1_validate.py`, `scratchpad/cap_*.json|txt`, `scratchpad/r1_findings.json`.

Builds: `qwartus-3381/qwartus_niceboat`, `Sergohero-2699/SergoheroGaz` (Allflame).

## Verdict

The **success path is clean** — full schema conforms on both builds, prices match poe.ninja, zero
dropped items, invariants hold. All defects are in the **error contract + header/doc conformance**.
**1 major + 4 minor.** No blockers. No stack traces or platform crashes on any app-handled input.

| # | Sev | Area | One-line |
|---|-----|------|----------|
| F1 | **major** | errors | Malformed poe.ninja URLs (overview link, PoE2 link, bad path) return **502 `ninja_error`**; contract §4 says **400 `bad_input`** |
| F2 | minor | headers | Live success `Cache-Control: public` — missing the §6-documented `s-maxage=600, stale-while-revalidate=86400` (Vercel strips them; edge cache still works) |
| F3 | minor | errors | "Character not found" returns raw `HTTP 404 from https://poe.ninja/…/builds/<ver>/character?…` instead of the intended user guidance (which is unreachable on a 404) |
| F4 | minor | contract | Doc drift: live emits `meta.rates` + item `swap:true` (D-0018); neither is in `public-contract.md` §2.1/§2.3 |
| F5 | minor | robustness | POST body >~4.5 MB → non-JSON Vercel `413 FUNCTION_PAYLOAD_TOO_LARGE` (platform limit), not the documented `{ok:false}` JSON shape (≤500 KB is fine) |

---

## F1 (MAJOR) — build-overview / PoE2 / malformed poe.ninja URLs return 502 `ninja_error` instead of 400 `bad_input`

**Contract promise (§4):** `bad_input` (**400**) — *"unrecognised URL/code, **a build-overview link**,
an unsupported paste host, or missing input."* And §1: *"A poe.ninja build-overview link (no
`/character/`) is rejected with guidance."* `ninja_error` (**502**) is reserved for *"poe.ninja was
unreachable / returned no data / the character is private/unindexed."*

**Live behavior (verified):**

```
GET /api/build?url=https://poe.ninja/poe1/builds/allflame              -> HTTP 502  ninja_error
   error: "that looks like a build *overview* link, not a specific character. Open a character…"
GET /api/build?url=https://poe.ninja/poe2/builds/allflame/character/Foo-1234/Bar  -> HTTP 502  ninja_error
   error: "this looks like a Path of Exile 2 link; this tool only prices PoE1 builds…"
```

Both should be **400 `bad_input`**. (Non-poe.ninja hosts, non-URL garbage, and empty input are all
correctly `bad_input`/400 — only the poe.ninja-host-but-malformed URLs are misclassified.)

**Root cause:** `_lib/poeninja.py::parse_build_url` raises **`PoeNinjaError`** for every bad-URL case
(overview → line ~81-83; PoE2 / not-`/poe1/` → line ~71-73; no `/builds/` → line ~79; not a
poe.ninja host → line ~66). `build.py::_run` (lines 64-76) catches `EstimateError`→400 *first*, then
maps **all** `PoeNinjaError`→**502 `ninja_error`** unconditionally — conflating "the user pasted a
malformed URL" (a client error, poe.ninja never contacted) with "poe.ninja upstream failed."

**Impact (why major, not cosmetic):**
- **Wrong HTTP status on a very common user action** (pasting a PoE2 link or a build-overview URL).
  A consumer with retry-on-5xx logic will *retry a permanently-invalid input* — needless function
  invocations, and it never succeeds.
- **`error_type` actively misinforms.** The contract's documented meaning of `ninja_error` is
  "poe.ninja unreachable / character private." A UI branching on `error_type` (§4's entire purpose:
  *"branch on … `ok`"* → then on type for messaging) will tell the user *"poe.ninja is down, try
  again later"* when the real fix is *"paste a PoE1 character link, not this one."* The helpful
  `error` string contradicts its own `error_type`.

**Suggested fix:** make `parse_build_url` failures classify as bad input — either raise
`engine.EstimateError` (which already → 400 `bad_input`) for the malformed/overview/non-`poe1`
cases, or in `build.py::_run` distinguish parse-time `PoeNinjaError` from fetch-time and return 400
`bad_input` for the former. Add a promise-test (RULE 8) asserting overview + PoE2 URLs → 400
`bad_input`.

---

## F2 (MINOR) — success `Cache-Control` on the wire omits the documented `s-maxage` / `stale-while-revalidate`

**Contract promise (§6):** success carries
`Cache-Control: public, s-maxage=600, stale-while-revalidate=86400`.

**Live (raw wire capture of a 200 build response):**
```
Cache-Control: public
X-Vercel-Cache: HIT
Age: 66
```
The client-facing header is just `public`. **The functional promise still holds** — `X-Vercel-Cache:
HIT` + non-zero `Age` prove Vercel's edge *is* caching per `s-maxage`. Vercel deliberately strips
shared-cache directives (`s-maxage`, `stale-while-revalidate`) from the response it forwards to the
browser. `build.py` sets the full string (`_CACHE_OK`, line 39); the platform rewrites it downstream.

**Impact:** low — caching works as designed; the free-tier-cost rationale in §6 is satisfied. The
discrepancy is doc-vs-reality: a consumer reading §6 and inspecting the header will not see the
documented directives. **Errors are correctly `no-store`** on the wire (verified on every error
case; not edge-cached, `X-Vercel-Cache: MISS`) — the "errors must not be long-cached" requirement
**passes**.

**Suggested fix:** update §6 to state the browser-visible header is `public` and that Vercel's edge
honors `s-maxage`/SWR (they are stripped before the client). If browser-visible directives are truly
wanted, set them via `public/vercel.json` `headers` (not function-settable once Vercel strips them).

---

## F3 (MINOR) — "character not found" leaks a raw upstream 404 + internal URL instead of the intended guidance

**Live:**
```
GET /api/build?url=https://poe.ninja/poe1/builds/allflame/character/ZzzNoSuch-0000/ZzzNoSuchChar999
 -> HTTP 502 ninja_error
 error: "HTTP 404 from https://poe.ninja/poe1/api/builds/0412-20260728-25514/character?
         account=ZzzNoSuch-0000&name=ZzzNoSuchChar999&overview=hc-ssf-r-allflame&timeMachine="
```
Status **502 / `ninja_error` is correct** per §4. The **message is the problem**: it is a raw
upstream `HTTP 404 from <internal snapshot-versioned poe.ninja API URL>`. It (a) is not
user-actionable, (b) exposes the internal builds API URL + snapshot version, and (c) confusingly
names `hc-ssf-r-allflame` (the last of 8 tried snapshots) though the user searched "allflame".

**Root cause:** `_lib/poeninja.py::PoeNinjaClient._get` (line ~98-99) wraps any `HttpError` as
`PoeNinjaError(str(e))` = `"HTTP 404 from <url>"`. A nonexistent character 404s (not a 200-with-no
-items), so the friendly `producer()` message *"…Double-check the link, or the character may be
private/unindexed."* (lines ~191-194) is **never reached** for a 404, and `fetch_character` re-raises
that raw `last_err` after all candidates (line ~206). The intended guidance is effectively dead code
for the most common not-found path.

**Suggested fix:** when snapshot candidates are exhausted, raise the friendly not-found
`PoeNinjaError` (the "check the link / may be private/unindexed" text) rather than re-raising the raw
`HttpError`; keep the raw detail out of the user-facing `error` string.

---

## F4 (MINOR) — contract doc drift: `meta.rates` and item `swap` are emitted live but undocumented

Both live builds return `meta.rates` (16 currency ids) and `swap: true` on 2 items each — the D-0018
additive fields (`response.py` lines 214 and 66-67). `public-contract.md` documents its additive
updates D-0016 and D-0019 at the top and in §2.1/§2.3, **but not D-0018** — `rates` is absent from
the §2.1 `meta` table and `swap` is absent from the §2.3 common-fields table. Additive and
back-compatible (no consumer breaks), but the "source of truth" doc is incomplete, and D-0018 states
the **site depends on `meta.rates`** to convert non-chaos listing currencies.

**Suggested fix:** add `rates` to §2.1 and `swap` to §2.3, matching how D-0016/D-0019 fields are
already documented.

---

## F5 (MINOR) — oversized POST (> Vercel 4.5 MB limit) returns a non-JSON platform 413

`POST /api/build` with a ~6 MB body → `HTTP 413`, `Content-Type: text/plain`,
`x-vercel-error: FUNCTION_PAYLOAD_TOO_LARGE`, body `"Request Entity Too Large"`. This is Vercel's
serverless request-size limit; **our function never runs**, so it cannot emit the documented
`{ok:false,…}` JSON. A 500 KB body is handled correctly by the app (→ 400 `bad_input` JSON). Not a
stack trace; it is a clean platform rejection — but a consumer doing `r.json()` (§4: "branch on
`ok`") will throw on a non-JSON body.

**Suggested fix (low priority / partly platform-inherent):** the site/extension should cap input
length client-side before POST (a URL / PoB code is never megabytes); optionally document the 413
boundary in §4 and note consumers must guard against non-JSON responses.

---

## What PASSED (clean bill — baseline for R5 regression)

**Success schema — both builds, machine-validated, zero violations:**
- Top-level `ok`/`schema_version`(=`"1.0"`)/`meta`/`totals`/`items`/`rares`/`warnings` all present &
  typed. `meta` all 16 documented fields present & correct types; `currency_unit`=`"chaos"`,
  `source`=`"poe.ninja"`.
- Every `items[]` row: `index` == array position; `group`/`category`/`price.method`/`confidence`/
  `source` all within their documented enums (methods seen: `skill`, `unique-ninja`,
  `unique-ninja-variant`? no, but `unique-ninja-floor`, `unique-ninja-range`, `rare-unpriced`,
  `magic-unpriced`, `none` — good enum coverage). Socket block typed when present; gem rows carry all
  10 gem fields; non-gem rows carry `mods`.
- **Invariants hold:** `totals.chaos.{min,median,high}` == recomputed sum of poe.ninja-sourced items;
  `priced_items` == recomputed count; `divine.* == round(chaos/divine_to_chaos, 3)` per-item and per
  -total; gem `total_chaos == Σ(gem.chaos where non-null)`; granted gems have `chaos: null`.
- **`rares{}` ↔ items correspondence** exact (every rare/unique/magic item has an entry; no orphan
  keys). AffixOption kinds/priorities in enum; `equip` affixes carry `key`; **pseudo `folds[].index`
  each points to a `resist:true` affix**; `defining` affixes are searchable+prefer+`required`.
- **Variant block §2.8 exercised** (sergo `Lethal Pride, Timeless Jewel` → class `seed-jewel`, label
  `"Rakiata seed 13032"`, method `unique-ninja-floor` @ `confidence:"low"`). **Additive guarantee
  verified:** the `locked_stats[].stat_id` appears in the item's `trade_query.stats` (nothing
  dropped).

**Prices vs poe.ninja raw truth (spot-check, the R3-preview):**
- 18 name-matched uniques match poe.ninja economy lines (Headhunter 15210, Nimis 7680, Ashes of the
  Stars 321.4, Dying Sun 3017, Wine of the Prophet 2011, …). Sub-cache-window diffs only (Replica
  Voidwalker 5.0 vs 4.8; Cinderswallow 202 vs 215) — expected drift, not bugs. Chaos normalization
  (poe.ninja `chaosValue` used directly) is correct.
- `divine_to_chaos` 125.7 (API, edge-cached) vs 124.8 (live poe.ninja Divine `primaryValue`) — 0.7%,
  cache-window drift. Method correct.

**No dropped items (vs poe.ninja raw character JSON):**
- qwartus: equip/flask/jewel API `12/5/1` == raw `12/5/1`. sergo: `12/5/7` == raw `12/5/7`.
  `meta.level` / `class` match raw.

**Error contract — the correctly-handled cases:** empty→400 `bad_input`; non-URL garbage→400
`bad_input`; non-poe.ninja host→400 `bad_input`; nonexistent char→502 `ninja_error` (status/type
correct; only message quality = F3); invalid-base64 "PoB"→400 `bad_input`; 500 KB body→400
`bad_input`; malformed-JSON POST body→400 `bad_input`. **No stack traces / `Traceback` / HTML /
`FUNCTION_INVOCATION_FAILED` on any app-handled input.**

**Headers:** every response carries `Access-Control-Allow-Origin: *`; success + errors +
OPTIONS all send CORS. `OPTIONS /api/build` → 204 with `Access-Control-Allow-Methods: GET, POST,
OPTIONS`. **All error responses `Cache-Control: no-store`** (not edge-cached — the "errors must not
be long-cached" requirement passes). `/api/health` → 200, `no-store`, `ok:true`,
`schema_version:"1.0"`, `calls_pathofexile_com:false`, `refdata{stat_groups:9, stat_patterns:8077,
base_types:3952}` — matches its §1 contract.

**Non-findings noted:** `/api/health` advertises `Access-Control-Allow-Methods: GET, OPTIONS` (no
POST) — correct, health has no POST handler; §6's `GET, POST, OPTIONS` is the `/api/build` contract.

## Coverage caveats
- No PoB-import path exercised (owner PoB codes still pending per D-0020 / `inputs.json`
  `pob_files`); F1's fix should also be checked against PoB paste-host errors. R1 covered the
  poe.ninja-character + error paths only.
- Variant registry: only the `seed-jewel`/floor class appeared in these 2 builds; `notable-jewel`,
  `socket-defined`, `map-count`/`map-variant`/`map-base` classes were not live-exercised here.
