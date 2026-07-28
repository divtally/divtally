# R2 RE-VERIFY 1 — independent re-verification of the R2 fixes

**Round:** 2 of the D-0020 campaign. **Purpose:** independently re-verify the R2 fix(es) — locally
where possible (offline harnesses + a fresh live drive of the worst-affected build), with a **different
setup** than the fix agent used, to catch anything its route-swap masked. **Scope of R2 fixes to date:**
**F1 only** (`docs/bugtest/r2-fix1.md`; decision-log `D-0020 R2 F1`). F2/F3/F4/F5 from `r2-judge.md`
are **not yet fixed** (deferred to later rounds per the recommended order) — nothing to re-verify for
them. **Files I touched:** this note only. **No deploy, no product-code change.** **Date:** 2026-07-28.

Every number below is source-derived: an offline-harness count, or a live `bpc.totals()` /
`bpc.scanStatus()` / rendered-DOM reading from this run (`scratchpad/r2reverify1_results.json`,
`r2reverify1_progress.jsonl`, `r2reverify1_final.png`).

---

## 1. What F1 fixed (recap)
A D-0019 variant unique (Watcher's Eye) whose exact locked-mod search returns `total_found=0` was
**keeping its poe.ninja name-level placeholder, rendering it as a price, and staying counted** in the
headline (contradicting Locked D-0019 "floor is a PLACEHOLDER, not its price"). The fix
(`public/site/assets/core.js`): a `dropIfPlaceholder(key,patch)` helper nulls the chaos iff the row is
still the ninja placeholder for a variant unique; all four `foldBatch` failure branches wrap their patch
with it; `applyPrice` gained an `else delete state.enabled[key]` invariant so a withdrawn number never
leaves a stale enable. Net: a failed variant-unique scan is now indistinguishable from a 0-match rare
(link + no number). I read the deployed-candidate code (core.js:797/803/816/849 call sites, the helper at
892-898, the invariant at 460-467) — the implementation matches the fix note, is correctly scoped to the
`unique-ninja` placeholder method, and does not touch real whisper/cache/prior-scan prices.

## 2. Local re-verification (no deploy needed)

All offline harnesses re-run from a clean checkout — **all green**:

| Harness | Result |
|---|---|
| `node public/site/test_scanstatus.mjs` (incl. F1 `scenarioVariantPlaceholder`) | **64 / 0** |
| `node public/site/test_picker.mjs` | **98 / 0** |
| `node extension/test_protocol.mjs` | **PASS** |
| `python tests.py` | **All passed** |
| `BPC_SKIP_LIVE=1 python public/api/_verify.py` | **ALL CHECKS PASSED** |
| `python tools/build_variant_registry.py --check --offline` | **validated OK** |

The F1 fix is entirely in `public/site/assets/core.js` (the public-site scan engine). The offline
`test_scanstatus.mjs` drives the real `core.js` in a Node `vm` through the exact
autoscan → `foldBatch` → `applyPrice` → `totals` path with a fake extension, and its
`scenarioVariantPlaceholder` asserts the drop, the scoping (a cache-priced variant keeps its number), a
successful search replacing the placeholder, and a genuine 0-match rare control — so the fix's LOGIC is
proven locally without a browser. The local app edition (`bpc/ui/assets/core.js`) has no
autoscan/`foldBatch` path, so F1 does not apply there (confirmed by grep) — nothing to test.

## 3. Live re-verification (the part needing the coordinator's deploy)

**Why live at all:** F1 ships in the public-site `core.js`; to be live on `divtally.com` it needs the
**coordinator's deploy**. I re-verified it deploy-independently via an **independent setup** (deliberately
different from the fix agent's route-swap onto `divtally.com`):

- **Served `public/site` LOCALLY** (`python -m http.server 8123` on 127.0.0.1) so the browser loaded the
  **actual fixed `core.js` straight off disk** — an in-page `fetch('assets/core.js')` confirmed
  `dropIfPlaceholder` present (5 hits) → provenance proven, no route trickery.
- **`?api=https://divtally.vercel.app`** override → the build data came from the **live** Vercel build
  function (probed 200, 132 KB before the run). Local `config.js` already points there; the override is
  explicit belt-and-suspenders.
- **Real extension v1.2.1** in a fresh Playwright persistent context (`headless:false`), loaded via
  `--load-extension` with the **DEV manifest** (adds the `localhost` content-script match) → bridge lit
  **"extension active · v1.2.1"** on the local page. The only pathofexile.com traffic was the extension's
  own, under its limiter. **ONE full scan**, no re-scans.

**Build:** `yalokk-2571 / TimeForAurab` — the F1 poster child / worst-affected (Build 4). Fresh profile,
untouched defaults, single sanctioned `Enter`; autoscan fired itself at +5 s.

**14 of 15 assertions PASS. The one FAIL is a harness-tolerance artifact, not a product defect** (see §4).
F1 behaviour is exactly correct:

| Row | Pre-fix (r2-build4.md) | This re-verify run |
|---|---|---|
| **Watcher's Eye** (variant, tf 0) | 55c placeholder, **counted**, chip cleared | `chaos.median=null`, `enabled=false`, `source=trade`, `method=extension`, `stage=nobuyout`, **DOM price empty** — link-only |
| Bubonic Trail (control, no placeholder) | 1.0c real match | **1.0c** real match (`tf 2884`, done) — unchanged |
| 3 genuine 0-match rares | link-only | link-only (Golem Trap / Armageddon Star / Luminous Curio — identical shape to Watcher's) |
| **Headline** | `priced=28, included=26` | **`priced=27, included=25`** — each exactly −1 (the placeholder row left) |

**Placeholder removal is directly observed in the progress trace:** at +60 s Watcher's Eye was still
counted (`min=1950.922, incl=26, priced=28`); at +65 s its search resolved to `nobuyout` and it dropped
(`min=1900.920, incl=25, priced=27`). Min moved by **exactly 50.002c** — the placeholder value this run
(poe.ninja economy drifted from yesterday's ~55c). The placeholder is gone from the total; the row shows
a link and no number.

**D-0020 hard criteria — both PASS:**
- **(a) scan-duration audit produced:** `totalMs = 67 460 ms` (matches the fix-agent's 67 480 and the
  report's 67.5 s).
- **(b) hands-free fruition:** auto-started at +5 s, **13/13 rows terminal, 0 stuck, 0 pageerrors**. The
  ~28 s window back-off on Watcher's Eye resolved itself as an honest countdown. The only console line
  was a `/favicon.ico` 404 — a benign local-serve artifact (python `http.server` has no favicon; the
  deployed CF Pages site does), not product behaviour.

## 4. The single failing assertion is a harness artifact (NOT a finding)
My driver hard-coded `abs(min − 1869.6) < 8` (the fix-agent's absolute min). This run's absolute min was
**1900.92c** (delta 23.7c from the 1924.628 baseline, not 55c). This is **expected and not a defect**:
the headline min is a **live aggregate** of every included row's current trade price, and the *other*
priced rows moved with the market between the two runs. The F1-attributable quantity — the Watcher's Eye
placeholder — was removed **cleanly and completely** (−1 included, −1 priced, row link-only, 50c off the
running min at the instant it dropped). An absolute-min equality across two live runs a day apart was the
wrong assertion; the correct F1 invariants (row link-only + counts −1 + placeholder off the running total)
all PASS. No product issue.

## 5. Verdict
**F1 is RE-VERIFIED — green.** Offline harnesses all pass (F1 logic proven in-process); the fixed
`core.js` was exercised end-to-end live via an independent local-serve + live-API + real-extension path on
the worst-affected build, and Watcher's Eye now behaves exactly like a 0-match rare (link + no number,
out of the headline), with both D-0020 hard criteria met and a clean console (favicon 404 aside).

**Needs the coordinator's DEPLOY to reach users:** F1 is a `public/site/assets/core.js` change; it is not
yet live on `divtally.com`. This re-verify confirms the fixed file is correct — the remaining step is the
deploy (out of my scope; no deploys).

**Not re-verified because not yet fixed:** F2 (zero-match "0 listings" copy — still present verbatim in
this run's Watcher chip: *"no buyout among 0 listings · 0 fetched, 0 without a buyout"*), F3 (chunk-
cumulative raw per-row `ms`), F4 (magic-row scan scope), F5 (header count nit). These are deferred to
later rounds per `r2-judge.md` §6's fix order; nothing to re-verify until they land.
