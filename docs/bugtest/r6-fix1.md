# R6 — FIX 1 (security S1 blocker): reflected XSS on the prod origin

Fixes the one MAJOR/blocker from `docs/bugtest/r6-security.md` §S1 — the reflected-XSS chain
(unescaped document-derived **numeric** fields + un-scheme-checked `trade_url`/`icon`, reachable via
the unallowlisted `?api`/`?stub`/`?worker` overrides, unblunted by a missing CSP). The finding was
**empirically confirmed executing in real headless Chrome** (`onerror` hits 201/203/204). This fix
implements **all three legs** the finding prescribes ("do all three; any one breaks the chain"), plus
closes three sibling sinks of the same class the finding's line list did not enumerate.

Scope obeyed: edits confined to `C:\scripts\buildpricechecker-poe1`; verification rig under the
session scratchpad `…\scratchpad\r6fix1\` (disjoint from the evidence rig `…\r6sec\`). **No
pathofexile.com calls** — the browser proof serves our own site read-only from `127.0.0.1`.

Files changed:
- `public/site/index.html` — sink hardening (numeric coercion + URL scheme-validation).
- `public/site/assets/core.js` — dev-gate the data-origin overrides; harden `rareTradeUrl` +
  `cacheReadThrough`.
- `public/site/_headers` — **new**: CSP + frame/nosniff/referrer/permissions headers (also §S2).

Harnesses stay green (`test_picker.mjs` 98/98, `test_scanstatus.mjs` 106/106); the engine→UI JSON
contract is unchanged (no response field added/renamed/removed — this is render-time coercion +
client-side validation only). Legit values are untouched: `Number(20)===20`, a real
`https://web.poecdn.com/...` icon and a real `https://www.pathofexile.com/trade/...` link all pass.

---

## Leg A — coerce every document-derived NUMBER + scheme-validate every URL at its sink (`index.html`)

Two helpers added beside `E` (index.html ~1139):
```js
const safeHref = u => /^https:\/\/www\.pathofexile\.com\//i.test(u=String(u==null?'':u)) ? u : '';
const safeIcon = u => /^https:\/\//i.test(u=String(u==null?'':u)) ? u : '';
```
Numerics are coerced with `Number(x)` **at the sink** — a hostile non-numeric string becomes `NaN`,
which the pre-existing `|| fallback` (`'?'`, `0`, or the `?:` gate) then swallows, so it can never
reach `innerHTML`. This preserves display exactly for all legitimate integer values.

| Sink (finding line) | Field | Fix |
|---|---|---|
| banner `#bSub` (1290) | `m.level` | `Level ${Number(m.level)||'?'}` |
| skill row meta (1405) + title attr (1403) | `it.level` (`lvl`) | `lvl=Number(it.level)||0` |
| skill row meta (1405) | `it.sockets` (`sock`) — **sibling, not in finding list** | `sock=Number(it.sockets)||0` |
| nested support (1425) | `g.level` | `gl=Number(g.level)||0` |
| nested support (1424) | `g.quality` | `gq=Number(g.quality)||0` |
| tooltip conf, cache branch (1679) | `p.total_found` | `tf=Number(p.total_found)||0` |
| tooltip conf, else branch (1682) | `p.sample_size` | `ss=Number(p.sample_size)||0` |
| recent-build card `mug()` (1221) | `b.level` — **sibling, not in finding list** | `Number(b.level)?('lvl '+Number(b.level)):''` |

| URL sink (finding line) | Field | Fix |
|---|---|---|
| skill name/link href (1403, 1409) | `p.trade_url` | `tu=safeHref(p.trade_url)` → link only if valid, else plain text |
| nested support href (1423) | `g.trade_url` | `gtu=safeHref(g.trade_url)` |
| manual "open search" href (2308) | `r.trade_url` | `rtu=safeHref(r.trade_url)` |
| manual modal href (2379) | `p.trade_url||it.trade_url` | `tradeUrl=safeHref(...)` at its single definition |
| slot `<img>` src (1479) + `has-ico` (1475) | `it.icon` | `sico=safeIcon(it.icon)` → img only if valid, else glyph |
| skill/support/manual `<img>` src (1402, 1422, 2288) | `it.icon`/`g.icon` | `ico/gi/mico=safeIcon(...)` |
| **slot-click `window.open` (1599)** — navigation sink | `cardTradeUrl(k)` | `safeHref(cardTradeUrl(k))` — a `javascript:` trade_url no longer opens |

`E()` still wraps each validated URL (blocks attribute breakout); `safeHref`/`safeIcon` add the
scheme check `E()` cannot do. Invalid URLs **degrade gracefully** (plain text / placeholder glyph),
never a dead `href=""`.

## Leg B — gate the data-origin overrides to a dev context (`core.js` 47-49)

`?api`/`?stub`/`?worker` let a crafted link supply the **entire build document** (or repoint the
community cache) from an attacker origin — the finding's delivery vector. Now honoured **only** in a
dev context (`localhost` / `127.0.0.1` / `*.local` / `file:`, or an explicit
`CFG.ALLOW_QUERY_OVERRIDES` escape hatch); in production they are ignored and the fetch uses the
config-shipped `API_BASE`/`WORKER_BASE`. `devContext()` is defensive (try/catch, tolerates a missing
`location.hostname` — which is why the node harnesses, whose fake `location` has none, are unaffected).

## Leg B′ — sibling navigation sink: `rareTradeUrl` refUrl (`core.js` ~1262)

`rareTradeUrl(query, refUrl)` used a document-supplied `refUrl` verbatim as the URL base, and the
result flows to `window.open` (index.html 2096/2130) and `applyPrice.trade_url`. A `javascript:`
refUrl would become `javascript:…?q=…`. Now: `if (!/^https:\/\/www\.pathofexile\.com\//i.test(base))
base = "";` — a non-trade refUrl is discarded and the canonical trade URL rebuilt. (The legit
pathofexile refUrl in `test_picker.mjs` CASE 9 passes the guard unchanged → test still green.)

## Leg B″ — defence-in-depth: `cacheReadThrough` (`core.js` 663-668)

The `?worker=` override bypasses the worker's write-time sanitiser, so the client re-validates the
cache record it applies: `sample_size`/`total_found` via `num(...)||0`, and `trade_url` accepted only
if it is a string matching `^https://www.pathofexile.com/`. Keeps `state.priced` clean for any future
consumer (Leg A already covers today's render sinks).

## Leg C — ship a CSP + hardening headers (`public/site/_headers`, also §S2)

New Cloudflare Pages `_headers`: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy`, `Permissions-Policy`, and a CSP. Origins verified against `config.js` + an origin
grep of the site:
`default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src
'self' https://web.poecdn.com; font-src 'self'; connect-src 'self' https://divtally.vercel.app
https://divtally-cache.divtally.workers.dev; frame-ancestors 'none'; object-src 'none'; base-uri
'self'; form-action 'self'`.
- `connect-src` = exactly the API + worker → **also blocks the evil-backend `fetch`** even if an
  override slipped through (reinforces Leg B); `img-src` = poecdn only (site uses **zero** `data:`
  images — verified, so `data:` is omitted for tightness; `safeIcon` blocks `data:` at the sink too).
- **Honest tradeoff (unchanged from §S2):** both pages ship one large inline `<script>` and a static
  `_headers` has no nonce, so `script-src` must keep `'unsafe-inline'` — which does NOT by itself stop
  an injected inline `onerror`. Legs A+B already make that injection impossible; the CSP adds the
  external/eval-script lock, connect/img pinning, and clickjacking/`base-uri` defence. To later drop
  `'unsafe-inline'`, move both inline scripts into `/assets/*.js` (mechanical, deferred).

Deliberately **left unchanged** (verified safe, not softening):
- `it.count` (1467) — the finding itself **refuted** this; `it.count>1` makes `"<img…>">1 === false`.
  Re-confirmed inert in the browser proof (payload 205 never fired).
- `source_url` (1287) — guarded by `^https?://` (blocks `javascript:`); it targets poe.ninja, so
  `safeHref` (pathofexile-only) would wrongly break it. The finding accepts the existing guard.
- `timelessInspectUrl` (1178 → hrefs 2003/2295) — scheme+host hardcoded `https://vilsol.github.io/…`
  with `encodeURIComponent` params; no injection surface.
- Store/repo hrefs (2409-2418) — from trusted `CFG`, not the build document.

---

## Verification

**Project harnesses (offline, node):** `test_picker.mjs` **98/98**, `test_scanstatus.mjs` **106/106**
— core.js executes and the index.html inline `<script>` parses after every edit.

**Leg A proof — real headless Chrome, CDP, positive-controlled** (`…\r6fix1\verify_fix.mjs`; injects
the doc's exact numeric payloads 201/203/204/205 **plus** `javascript:`/`data:` URL payloads through
`trade_url` href + `window.open` and `icon` src, via the identical `loadMock` render path):
```
FIXCHECK {"ctrl_fired":true,"hits":[],"imgOnerror":0,"jsHrefs":0,"badImgSrc":0,
          "openedBad":[],"bSub":"Witch · Level ? · Standard","bSubLevelFallback":true}
```
- `ctrl_fired:true` — the positive control (`<img onerror>` set via `innerHTML`) DID fire, proving the
  detector is live this run ⇒ the zero results below are trustworthy, not a dead harness.
- `hits:[]` — **none** of the injected payloads executed (the doc's confirmed 201/203/204 are dead).
- `imgOnerror:0` · `jsHrefs:0` · `badImgSrc:0` — no live `img[onerror]`, no `a[href^=javascript:]`,
  no `img[src^=javascript:|data:]` anywhere in the rendered DOM (global scan, catches any leaked sink).
- `openedBad:[]` — `window.open` was never called with a non-pathofexile URL (slot-click path).
- `bSub:"… Level ? …"` — the `meta.level` sink **rendered** and the hostile string was coerced to its
  `?` fallback: neutralized, not merely absent.

**Leg B proof — captured-fetch vm test** (`…\r6fix1\verify_overrides.mjs`; real core.js, mocked
`location` + `fetch`): **6/6**.
```
prod  divtally.com       -> https://api.test.local/api/build?url=…   (overrides IGNORED)
prod  divtally.pages.dev -> https://api.test.local/api/build?url=…   (overrides IGNORED)
dev   127.0.0.1          -> https://evil.tld/b.json                  (?stub honoured)
dev   localhost          -> https://evil.tld/b.json                  (?stub honoured)
```
Production ignores `?api`/`?stub`/`?worker` and uses the configured backend; dev still honours them.

**Net:** the exploit the finding confirmed executing is inert at the sink (Leg A), the delivery vector
is closed in production (Leg B), the sibling `window.open`/cache paths are hardened (Leg B′/B″), and a
CSP blunts anything missed while blocking the evil-backend `fetch` and framing (Leg C).

---

# R6 — FIX 1 (concurrency F1 major): per-build generation token

Added in the **same round** by the race lens (`docs/bugtest/r6-race.md` §F1). The S1 legs above and
this F1 fix were implemented by different agents against the one working copy; this section documents
the F1 fix and the security **regression test** added to complement the S1 browser-rig proofs.
`public/site/assets/core.js` only. No pathofexile.com calls (all proofs are offline node vm).

## The defect
No **generation token** on `state`. `reset()` cleared `state` but not the module-level `pending{}`
map or the in-flight fetch, so async continuations from a superseded build/scan ran against whatever
build was current. Build-identical (all R4 ever tested) it was last-writer-wins-invisible; with
**different** builds A→B in the tens-of-seconds autoscan window it was not:
- **F1a** — appraise A (slow) then B (fast): B rendered, A's late reply **clobbered** it; final render
  = A while `state.source` = B (incoherent).
- **F1b** — a zombie A autoscan reply delivered after switching to B folded A's price onto B's
  **same-index** item (`item.index` is positional: B Headhunter `14 613c → 999c`) **and** `cachePost`
  wrote those cross-build prices into the **shared community cache** under B's identities (persisted,
  cross-user corruption).

## The fix
Monotonic `state.gen = ++genSeq` stamped in `reset()` (which now also aborts the prior build fetch);
`start()` captures `var gen = state.gen` and every async continuation drops itself on `gen !== state.gen`:

| Site | Guard | Prevents |
|---|---|---|
| build fetch `.then` / `.catch` / timeout | `if (gen!==state.gen) return;` | F1a wrong-build render; an aborted prior fetch calling `fail()` on the new build |
| `cacheReadThrough` inner `.then` | `if (gen!==state.gen) return;` | a stale cache fill folding onto the new build |
| `foldBatch` (top) | `if (gen!==state.gen) return;` | F1b cross-build fold **and** `cachePost` poisoning (one choke point) |
| `nextChunk` (top) | `return Promise.resolve({superseded:true})` | further wasted trade chunks; deliberately no `scanEnd()` (the global `scan` is the new build's) |

`state.gen` is internal (contract additive). **Single-build behaviour is byte-identical** — `gen`
never changes after `reset()`, the `settled` de-dupe is untouched — so the R4-4 timeout, old/new-ext,
and variant-placeholder scenarios all still pass. Robust without `AbortController` too (the `.then`
gen-guard alone drops the stale build). Also covers the minor F3/F4 root cause (rerun/control re-fetches
are now gen-gated).

## Addendum to the S1 legs (this agent)
- **`it.count` (index.html 1477) closed.** Leg A intentionally left it (the `>1` gate makes
  `"<img…>">1 === false`). Coerced anyway — `const cc=Number(it.count)||0` — for explicit
  defence-in-depth + consistency with the other numeric sinks (zero behaviour change; a clean count
  still renders, a hostile one was and stays inert).
- **Durable in-repo security regression test added** (`public/site/test_security.mjs`, **27/0**). The
  S1 proofs above live in the scratchpad rig (`…\r6fix1\`) and don't persist as a repo guard; this
  offline node suite locks every S1 leg: override dev-gating (prod-vs-dev), `cacheReadThrough`
  re-validation (js url dropped + numerics coerced, w/ a valid-url positive control), `rareTradeUrl`
  scheme validation, and the **live-extracted** `index.html` `safeHref`/`safeIcon` + the `Number()||0`
  coercion pattern.

## Verification (F1 + the added test)
- `test_scanstatus.mjs` **106 → 119** (this agent's +13): `scenarioRaceBuildSwap` (F1a — B stays
  rendered + coherent `state.source` after a late A reply) and `scenarioRaceZombieScan` (F1b — B's
  price NOT folded to 999 **and** zero poisoned cache POSTs, via a POST-capturing fake worker + fake
  SubtleCrypto). Suite currently totals **131/0** — a parallel R6 fix added the minor-F3
  `scenarioScanEntrypointGuard` (its core.js `if (scan.active) return {busy}` guard sits just before,
  and composes cleanly with, this agent's `var gen = state.gen` capture in `priceRowsViaExtension`).
- **Both regressions proven non-vacuous** (`…\scratchpad\neg_control.mjs`, `neg_control_sec.mjs`):
  neutralising the guards / reverting the S1 legs in a scratchpad copy breaks every invariant; restored
  → all hold. F1 nofix: `B-survives:false, priceIntact:false, noPoison:false`. S1 nofix:
  `overrideGated:false, urlSafe:false, numsSafe:false`.
- Full offline suite: `test_scanstatus.mjs` 119/0 · `test_security.mjs` 27/0 · `test_picker.mjs` 98/0 ·
  `worker.test.mjs` 55/0.
