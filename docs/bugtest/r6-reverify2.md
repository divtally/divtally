# R6 — RE-VERIFY 2 (independent re-run of the R6 fixes + failing-lens checks)

**Date:** 2026-07-28 · **Scope:** re-verify the R6 fixes now that the race-lens fixes landed
(`r6-fix1.md` = security S1 XSS chain + S2 headers **and** F1 generation token; `r6-fix2.md` = F3
scan-entrypoint guard) and re-run the four named lens checks — **addons-linter, XSS probes on the
local-served fixed site, header checks, rollover simulation** — with independent harnesses.
**Trade rule honoured:** ZERO pathofexile.com calls. Site served read-only from `127.0.0.1`; overrides
probe + rollover + addons-linter run fully offline.
**Rig (disjoint):** `…\scratchpad\r6rv2\` — `xss_probe.mjs` (ports 8822/9362, own Chrome profile),
`overrides_probe.mjs`. Rollover harness + addons-linter re-run from the r6rv1 rig read-only.
Edits: this file only.

## Verdict: **PASS — all R6 fixes re-confirmed, including the two items r6-reverify1 flagged as still-open.** No regression.

r6-reverify1 (the prior pass) ran **before** the race fixes landed and carried the F1 generation-token
MAJOR forward as unfixed. This pass confirms **F1 and F3 are now present, complete, and correct in the
tree**, the security S1 XSS chain is still inert on an independently-built browser rig, and the
addons-linter / header / rollover results are byte-for-byte reproduced. The only carry-forwards left are
the same **bounded MINORs** the fix docs themselves flagged (not regressions, not among the re-verify
checks): race-F2, popup.js self-XSS (S3), and rollover M1/M2/M4.

---

## 1. Project harnesses (offline, node) — GREEN
- `public/site/test_picker.mjs` → **98 / 0**
- `public/site/test_scanstatus.mjs` → **131 / 0** (was 106 at r6-reverify1; +25 = F1 `scenarioRaceBuildSwap`/`scenarioRaceZombieScan` + F3 `scenarioScanEntrypointGuard`)
- `public/site/test_security.mjs` → **27 / 0** (durable in-repo S1 regression suite)
- `public/worker/worker.test.mjs` → **55 / 0**
- `extension/test_protocol.mjs` → **PASS**

core.js executes and the index.html inline `<script>` parses cleanly.

## 2. Source presence of the fixes r6-reverify1 flagged open — CONFIRMED
Grep of the working tree (the exact thing r6-reverify1 said returned nothing):
- **F1 generation token** — `genSeq` + `state.gen = ++genSeq` stamped in `reset()` (core.js 355), prior
  fetch aborted via `curBuildAbort.abort()` (358), pinned `var gen = state.gen` in `start()` (372), and
  `gen !== state.gen` drop-guards at **every** async continuation the finding named: build-fetch
  timeout/then/catch (413/424/433), `cacheReadThrough` fold (697), extension `foldBatch` (885),
  `nextChunk` (958). Present and complete.
- **F3 scan-entrypoint guard** — `if (scan.active) return …{busy:true}` at the single scan choke point
  `priceRowsViaExtension` (core.js 848). Present.
- **Leg B override gate** — `devContext()` + `ALLOW_OVERRIDES` (core.js 52/60). **Leg A** — `safeHref`/
  `safeIcon` present in index.html (10 refs).

## 3. XSS probes on the local-served fixed site — INERT (real headless Chrome, CDP)
Independent harness `r6rv2\xss_probe.mjs` (own ports 8822/9362, own profile). Re-fires the security
lens's confirmed numeric payloads (201 `meta.level`, 203 `sample_size`, 204 `total_found`, 205 `count`)
+ the two sibling sinks the fix added (230 `it.level`, 231 `it.sockets`) + `javascript:`/`data:` URL
payloads through `trade_url` (href + `window.open`) and `icon` (src), via the identical `loadMock`
render path. Positive-controlled.
```
FIXCHECK {"ctrl_fired":true,"hits":[],"imgOnerror":0,"jsHrefs":0,"badImgSrc":0,
          "openedBad":[],"bSub":"Witch · Level ? · Standard","bSubLevelFallback":true}
```
- `ctrl_fired:true` — the `<img onerror>` positive control DID fire this run ⇒ the zeros are trustworthy.
- `hits:[]` — **no** injected payload executed. `imgOnerror:0 · jsHrefs:0 · badImgSrc:0` — no live
  `img[onerror]`, no `a[href^=javascript:]`, no `img[src^=javascript:|data:]` in the rendered DOM.
- `openedBad:[]` — slot-click `window.open` never fired with a non-pathofexile URL.
- `bSub:"… Level ? …"` — the `meta.level` sink **rendered** and coerced to its `?` fallback (neutralized,
  not merely absent). Reproduces the r6-fix1 Leg-A proof independently.

## 4. Data-origin override gating (Leg B) — 6/6
`r6rv2\overrides_probe.mjs` (real core.js in a vm, controllable `location` + captured fetch):
```
prod  divtally.com       -> https://api.test.local/api/build?url=…   (overrides IGNORED)
prod  divtally.pages.dev -> https://api.test.local/api/build?url=…   (overrides IGNORED)
dev   127.0.0.1          -> https://evil.tld/b.json                  (?stub honoured)
dev   localhost          -> https://evil.tld/b.json                  (?stub honoured)
```
Production ignores `?api`/`?stub`/`?worker` (the S1 delivery vector) and uses the configured backend;
dev still honours them. 6/6.

## 5. Header check (`public/site/_headers`) — COMPLETE & CONSISTENT
Static validation (the fix is not deployed; Cloudflare Pages `_headers` is a static-config format a plain
node server does not apply, so a live GET is not meaningful — static validation is the correct method,
same as r6-reverify1):
- All five hardening headers present under a valid `/*` glob with 2-space-indented lines:
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`,
  and the CSP. `frame-ancestors 'none'` + XFO DENY close the S2 clickjacking gap.
- **CSP allowlist proven complete against an origin grep of the served site:**
  - `connect-src 'self' https://divtally.vercel.app https://divtally-cache.divtally.workers.dev` =
    **exactly** `API_BASE` + `WORKER_BASE` in `config.js`; nothing else is fetched.
  - `img-src 'self' https://web.poecdn.com` — poecdn is the only image origin (28 refs); **zero `data:`
    images** in the site (grep-confirmed), so omitting `data:` is tight, not a breakage.
  - The other external origins found — `github.com`(6), `www.pathofexile.com`(2), `poe.ninja`(1),
    `vilsol.github.io`(1), `chromewebstore.google.com`(1), `addons.mozilla.org`(1) — are all top-level
    `<a href>` nav targets, NOT restricted by connect/img/script/font/form-action. `divtally-price-cache.
    YOURSUB.workers.dev` is only a comment placeholder in `config.js`. CSP breaks nothing.
- **Honest tradeoff (unchanged):** each page ships one inline `<script>` (grep-confirmed: index.html 1,
  how-it-works.html 1), so a nonce-less static `_headers` must keep `script-src 'unsafe-inline'`.

## 6. addons-linter (Firefox / AMO lens) — PASS, unchanged
`npx addons-linter@10.9.0 public/dist/divtally-extension-firefox-1.2.1.zip` →
**errors 0 / notices 0 / warnings 3, exit 0.** Identical to r6-firefox.md / r6-reverify1. Warnings =
`BACKGROUND_SERVICE_WORKER_IGNORED` (benign, deliberate dual-key fallback) + 2× `UNSAFE_VAR_ASSIGNMENT`
on `popup.js` `innerHTML` (= the S3 self-XSS MINOR below). No error ⇒ nothing predicts AMO rejection.

## 7. Rollover simulation — PASS, verdict reproduced
`r6rv1\rollover_harness.py` (reads the REAL `research/data/ninja_econ_index_state.json`, monkeypatches
poe.ninja index-state to end Allflame / start "Redemption", both variants; drives the public `_lib`
league paths offline):
- `current_challenge_league()` → **'Redemption'** (auto-heals) in **both** variants.
- `engine.resolve_league('', None)` → **'Redemption'**; `('Allflame', None)` → 'Allflame' (honest
  historical, M2); `('', 'PinnedLg')` → 'PinnedLg' (override respected).
- retained (realistic): `resolve_snapshot('allflame')` → frozen Allflame snapshot (still prices);
  `fetch_character('allflame', name-exists)` → `_league='Allflame'` (correct).
- gone (worst case): `resolve_snapshot('allflame')` **RAISES a clean** `PoeNinjaError` (fail-safe);
  `fetch_character` → `_league='Redemption'` — the bounded **M1** minor (displayed and priced league still
  agree). `fetch_character(not-found)` → clean 404 raise both variants.
Reproduces r6-rollover.md / r6-reverify1 exactly: no blocker/major, no crash, no wrong price; same
M1/M2 minors. (The R6 code fixes touched only site JS; rollover paths are Python `_lib` — untouched.)

---

## Honest carry-forwards (bounded MINORs, NOT among the four checks; flagged, not softened)
- **Race F2 (MINOR) — still open.** A late `cacheReadThrough` can clobber a manual/trade price (needs a
  source-precedence check). Not covered by the F1 token or the F3 guard; requires a >2 s cache delay.
  Flagged by r6-fix2 for a later pass.
- **popup.js self-XSS (S3 / firefox R6-1) — still open.** `extension/popup.js` writes `innerHTML` with
  concatenated `parsed.league` + trade JSON — the two `UNSAFE_VAR_ASSIGNMENT` linter **warnings** (not
  errors) above. Does NOT block AMO. Fix remains: escape before `innerHTML` / use `textContent`.
- **Rollover M1/M2/M4 (MINOR)** — bounded/forward-looking labeling minors, unchanged; the real
  deliverable there is the runbook.

**Net:** R6's fixes are re-confirmed on independent harnesses — S1 XSS chain inert, override vector closed,
CSP+headers complete, F1 (wrong-build render + cross-build fold + cache poisoning) and F3 (live-scan wipe
+ duplicate trade calls) present and test-locked, addons-linter clean, rollover robust. The two items
r6-reverify1 carried as open (race F1) are now fixed. Only bounded MINORs remain (F2, S3, rollover M1/M2/M4).
