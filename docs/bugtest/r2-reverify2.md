# R2 RE-VERIFY 2 — second independent re-verification of the R2 fixes

**Round:** 2 of the D-0020 campaign. **Purpose:** a **second, independent** re-verification of the R2
fix(es), local where possible (offline harnesses + `?mock`/in-process drive) plus one live drive of the
worst-affected build via a locally-served `public/site` + `?api=` live override + the real extension.
**Deliberately different METHOD than `r2-reverify1.md`:** F1 is asserted by the **drop-transition**
(min/included/priced deltas at the exact poll Watcher's Eye resolves), not by an absolute headline-min
baseline — so market drift of the *other* rows between runs cannot produce a false FAIL (the single
tolerance-artifact FAIL that reverify1 recorded). **Files I touched:** this note only. **No deploy, no
product-code change, no decision change.** **Date:** 2026-07-28.

**Scope of R2 fixes to date = F1 ONLY** (`docs/bugtest/r2-fix1.md`; decision-log `D-0020 R2 F1`).
F2/F3/F4/F5 from `r2-judge.md` are **not yet fixed** (deferred to later rounds per the recommended fix
order) — nothing to re-verify for them; F2's presence is re-confirmed in passing below.

Every number below is source-derived: an offline-harness count, a direct code read, or a live
`bpc.totals()` / `bpc.scanStatus()` / rendered-DOM reading from this run
(`scratchpad/r2reverify2_results.json`, `r2reverify2_progress.jsonl`, `r2reverify2_final.png`).

---

## 1. What F1 fixed (recap) and confirmation the deployable file carries it
A D-0019 variant unique (Watcher's Eye) whose exact locked-mod search returns `total_found=0` was
**keeping its poe.ninja name-level placeholder, rendering it as a price, and staying counted** in the
headline (contradicting Locked D-0019 "floor is a PLACEHOLDER, not its price"). Fix in
`public/site/assets/core.js`: `dropIfPlaceholder(key,patch)` nulls the chaos **iff** the row is still the
`unique-ninja*` placeholder for a variant unique; all four `foldBatch` failure branches wrap their patch;
`applyPrice` gained an `else { delete state.enabled[key]; }` invariant so a withdrawn number never leaves a
stale enable. Direct read **this run** confirms it, correctly scoped:

- Helper `dropIfPlaceholder` — **core.js:892-898** (`it.variant && p.chaos.median != null &&
  /^unique-ninja/.test(p.method)`), runs BEFORE `applyPrice` so it reads the pre-scan price; a real
  whisper/cache/prior-scan price is a different `method` and is never clobbered.
- Four `foldBatch` failure branches wrapped — **core.js:797, 803, 816, 849** (error / nobuyout / no-rate /
  whole-chunk).
- `applyPrice` null-median invariant — **core.js:460-467** (`else { delete state.enabled[key]; }`).

This is the **exact CF-Pages source the coordinator deploys**; it is unchanged since `r2-fix1.md` /
`r2-reverify1.md`. F1 is **N/A** in the local-app VIEW (`bpc/ui/assets/core.js` has no
autoscan/`foldBatch`/`unique-ninja` path — 0 hits by grep), so there is no sibling file to fix.

## 2. Local re-verification (deterministic, zero trade traffic) — ALL GREEN

| Harness | Result |
|---|---|
| `node public/site/test_scanstatus.mjs` (incl. F1 `scenarioVariantPlaceholder`) | **64 / 0** |
| `node public/site/test_picker.mjs` | **98 / 0** |
| `node extension/test_protocol.mjs` | **PASS** |
| `python tests.py` | **All passed** |
| `BPC_SKIP_LIVE=1 python public/api/_verify.py` | **ALL CHECKS PASSED** |
| `python tools/build_variant_registry.py --check --offline` | **validated OK** |

`test_scanstatus.mjs` drives the **real** `core.js` in a Node `vm` through the exact
autoscan → `foldBatch` → `applyPrice` → `totals` path with a fake extension; its
`scenarioVariantPlaceholder` asserts the drop, the scoping (a cache-priced variant keeps its number), a
successful search replacing the placeholder, and a genuine 0-match rare control — so the F1 **logic** is
proven in-process without a browser. Contract-additive: no engine→UI JSON field added/removed/renamed.

## 3. Live re-verification — worst-affected build, independent setup, ONE scan

**Which fix needs the deploy:** F1 lives in `public/site/assets/core.js`; to be live on `divtally.com` it
needs the **coordinator's deploy**. Verified deploy-independently here:

- **Served `public/site` LOCALLY** — `python -m http.server 8137` on `127.0.0.1` → the browser loaded the
  **actual fixed `core.js` off disk** (in-page `fetch('assets/core.js')` confirmed `dropIfPlaceholder`
  present, 5 hits, plus the `delete state.enabled[key]` invariant → provenance proven, no route trickery).
- **`?api=https://divtally.vercel.app`** override → build data from the **live** Vercel build function
  (probed reachable, HTTP 400 on a junk URL = alive). **No pathofexile.com call from me** — the only
  trade traffic was the extension's own, under its limiter.
- **Real extension v1.2.1** in a fresh Playwright persistent context (`headless:false`), loaded via
  `--load-extension` from a fresh dev-manifest copy (`r2reverify2ext`, localhost content-script match) →
  bridge lit **"extension active · v1.2.1"** on the local page.
- **Build:** `yalokk-2571 / TimeForAurab` — the F1 poster child / worst-affected (Build 4). Fresh profile
  (`r2reverify2`), untouched defaults (autoscan ON, pick-affixes OFF, swap OFF, tier min, "Instant Buyout
  and In Person"), single sanctioned `Enter`; autoscan fired itself. **ONE full scan, no re-scans.**

**17 / 17 assertions PASS** (no artifact FAIL this time — the transition method is drift-proof):

**Pre-scan setup state (the F1 trigger) reproduced:** Watcher's Eye loaded as a **counted**
`unique-ninja-floor` placeholder, `median=50c`, `enabled=true`, `variant=true` — exactly the state F1
must correct. Headline while it was still counted: `included=26, priced=28` (matches the pre-fix
`r2-build4.md` baseline).

**F1 behaviour — the drop transition, captured live (@poll 16):**

| | included | priced | headline min |
|---|---|---|---|
| just BEFORE Watcher resolved | 26 | 28 | 1950.92c |
| AT the drop (its search 0-matched) | **25** | **27** | **1900.92c** |
| delta | **−1** | **−1** | **−50.00c** (= the exact placeholder value; isolates the removed number) |

The min fell by **exactly** Watcher's own pre-scan placeholder (50.00c ≡ `minDelta 50 == placeholderVal
50`) — this run's drift-robust proof that F1 removed *the placeholder and nothing else*, independent of
how the market moved the other 24 rows since yesterday.

**Watcher's Eye final row:** `stage=nobuyout`, `total_found=0`, `chaos={null,null,null}`, `enabled=false`,
`source=trade`, `method=extension`, **DOM price empty** → link + no number, indistinguishable from a
0-match rare. **Control — Bubonic Trail** (variant, no placeholder): `done`, real `1.0c` (4 of 2903
listings) — untouched, proving the scoping. **3 genuine 0-match rares** (Golem Trap / Armageddon Star /
Luminous Curio): all link-only, identical shape.

**D-0020 hard criteria — both PASS:**
- **(a) scan-duration audit produced:** `totalMs = 67 527 ms` (67.5 s; matches fix-agent 67 480 /
  reverify1 67 460).
- **(b) hands-free fruition:** auto-started, **13/13 rows terminal, 0 stuck, 0 pageerrors**; the ~28 s
  window back-off on Watcher's Eye resolved itself as an honest countdown. Only console line was the
  local-serve `/favicon.ico` 404 (python `http.server` has no favicon; the deployed CF Pages site does) —
  a serve artifact, not product behaviour.

## 4. F2 still present (deferred, not a new finding)
Confirmed still live in this run's Watcher chip — **"⚠ no buyout among 0 listings · 0 fetched, 0 without
a buyout"** and note **"listings exist but none had a buyout price [search 200, 0 fetched, 0 w/o
buyout]"** — the self-contradictory zero-match copy (`r2-judge.md` F2). Not yet fixed; nothing to
re-verify. F3/F4/F5 likewise deferred.

## 5. Verdict
**F1 is RE-VERIFIED (second independent pass) — GREEN, 17/17.** The deployable
`public/site/assets/core.js` carries the correct, correctly-scoped fix; all six offline harnesses pass
(F1 logic proven in-process); and a live end-to-end drive on the worst-affected build via an independent
local-serve + live-API + real-extension path shows Watcher's Eye behaving exactly like a 0-match rare
(link + no number, out of the headline), with the removed value isolated to **exactly** its placeholder
(−50.00c) via a drift-robust transition assertion — cleanly resolving the lone tolerance-artifact FAIL
reverify1 noted. Both D-0020 hard criteria met; clean console (favicon 404 aside).

**Needs the coordinator's DEPLOY to reach users** — F1 is a `public/site/assets/core.js` change, not yet
live on `divtally.com`. That deploy is the sole remaining step (out of my scope; no deploys).

**Not re-verified because not yet fixed:** F2 (zero-match "0 listings" copy — re-confirmed present),
F3 (chunk-cumulative raw per-row `ms`), F4 (magic-row scan scope, owner design call), F5 (header count
nit). Deferred to later rounds per `r2-judge.md` §6.
