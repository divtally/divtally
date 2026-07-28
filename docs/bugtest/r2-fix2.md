# R2 FIX-2 — F1 (MAJOR): confirmation pass — no further code change; deploy-gated

**Round:** 2 of the D-0020 campaign. **Finding:** F1 (`docs/bugtest/r2-judge.md` §3), already fixed in
`docs/bugtest/r2-fix1.md` and independently re-verified in `docs/bugtest/r2-reverify1.md`.
**Resolution of this pass:** F1 needs **no further code change** — the fixed file is correct locally and
the sole remaining step is the coordinator's **deploy** of `public/site` to divtally.com (CF Pages),
which is **out of my scope (no deploys)**. **Files I touched:** this note only — **no product-code
change**. **No live re-scan** (justified in §4). **Date:** 2026-07-28.

Every number below is source-derived: a harness count or a direct code reading from **this** run.

---

## 1. The finding, and why it is resolved without a code change
F1: a D-0019 **variant unique** (Watcher's Eye) whose exact locked-mod trade search returns
`total_found=0` was **keeping its poe.ninja name-level placeholder, rendering it as a price, and staying
counted** in the headline — contradicting Locked D-0019 ("the floor is a PLACEHOLDER, not its price;
unmatchable → link + no number"). The fix already applied in `public/site/assets/core.js` makes a failed
variant-unique scan **indistinguishable from a 0-match rare** (link + no number).

The task's own hint is explicit — *"Coordinator deploys `public/site` to divtally.com (CF Pages); no
further code change needed for F1."* This pass **independently confirms** that: the fix is present and
correct in the deployable file, is complete (no sibling file needs it), keeps every harness green, and
is contract-additive. The only thing standing between the fix and users is the deploy.

## 2. Fix is present & correct in the deployable artifact (direct read, this run)
`public/site/assets/core.js` **is** the CF-Pages source the coordinator deploys. Read this run — matches
`r2-fix1.md`/`r2-reverify1.md` exactly, correctly scoped to the `unique-ninja` placeholder method:

- **Helper `dropIfPlaceholder(key, patch)` — lines 892-898.** Nulls the patch's chaos **iff**
  `it.variant && p.chaos.median != null && /^unique-ninja/.test(p.method || "")`. A real
  whisper/cache/prior-scan price is a different `method` and is never clobbered by a failed re-scan.
  Runs **before** `applyPrice` overwrites `state.priced`, so it reads the pre-scan price.
- **All four `foldBatch` failure branches wrap their patch** — call sites at lines **797, 803, 816, 849**
  (`applyPrice(key, dropIfPlaceholder(key, {…}), {include:false})`): error, `amount==null`/nobuyout,
  no-rate, whole-chunk error/timeout.
- **`applyPrice` invariant — lines 460-467.** The null-median branch now `delete state.enabled[key]`, so a
  row whose number is **withdrawn** never leaves a stale enable behind. `totals()` already skips null
  medians, so the row also leaves the `priced` count.

## 3. Local confirmation (deterministic, zero trade traffic)
**All six harnesses green — counts identical to `r2-fix1.md`/`r2-reverify1.md`:**

| Harness | Result |
|---|---|
| `node public/site/test_scanstatus.mjs` (incl. F1 `scenarioVariantPlaceholder`) | **64 / 0** |
| `node public/site/test_picker.mjs` | **98 / 0** |
| `node extension/test_protocol.mjs` | **PASS** |
| `python tests.py` | **All passed** |
| `BPC_SKIP_LIVE=1 python public/api/_verify.py` | **ALL CHECKS PASSED** |
| `python tools/build_variant_registry.py --check --offline` | **validated OK** |

- **Contract-additive:** the fix adds a helper, wraps four existing call sites, and adds an `else`
  branch — no engine→UI JSON field added, removed, or renamed. The green `test_scanstatus` (which drives
  the real `core.js` in a Node `vm` through autoscan → `foldBatch` → `applyPrice` → `totals`) proves the
  contract is intact and the F1 logic (drop, scoping, successful-replace, 0-match-rare control) holds.
- **Fix is complete — public-site-only, no sibling file:** the repo has exactly two `core.js`. The
  deployable `public/site/assets/core.js` carries the F1 markers (12 hits: `foldBatch`/`dropIfPlaceholder`
  /`unique-ninja`); the local-app VIEW `bpc/ui/assets/core.js` has **0** (`foldBatch`/`dropIfPlaceholder`/
  `autoscan`/`unique-ninja`) — it has no autoscan/re-scan flow, so **F1 is N/A there**. Nothing else to fix.

## 4. Live behaviour is already confirmed twice today — no redundant re-scan
F1 is a scan-behaviour fix, so a live receipt requires a full trade scan. **Two independent same-day live
confirmations already exist, both green, both on the worst-affected build (`yalokk-2571 / TimeForAurab`),
both meeting the two D-0020 HARD CRITERIA:**

| Live run | Setup (independent) | Result |
|---|---|---|
| `r2-fix1.md` §3b | route-swap fixed `core.js` onto real `divtally.com` origin | **15/15**; Watcher's Eye link-only; headline −55c; **(a)** `totalMs=67 480 ms`, **(b)** 13/13 rows terminal, 0 stuck |
| `r2-reverify1.md` §3 | `public/site` served locally + `?api=` live Vercel + real ext v1.2.1 | F1 exactly correct (Watcher's Eye link-only, counts −1/−1, placeholder off the running min); **(a)** `totalMs=67 460 ms`, **(b)** 13/13 terminal, 0 stuck (lone FAIL was a harness abs-min tolerance artifact, not a defect) |

**I deliberately did not run a third live scan.** I made **no code change** (none is needed), so a scan
would re-exercise an **unchanged** file already confirmed live twice today from two different setups. Under
the project's trade-discipline hard rule (the one-scan allowance is a ceiling for verifying a *fix*, not a
quota; needless trade traffic risks IP bans), generating trade traffic that yields **no new signal** is the
wrong call. The local confirmation above (direct read + all harnesses green) plus the two existing live
receipts fully establish the fixed file is correct and deploy-ready.

## 5. Verdict
**F1 — resolved to the limit of my scope. No further code change needed.** The fix is present and correct
in the deployable `public/site/assets/core.js`, complete (no sibling file), all six harnesses green,
contract-additive, and confirmed live twice today against both D-0020 hard criteria.

**Sole remaining step (out of scope, no deploys):** the coordinator deploys `public/site` to divtally.com
(CF Pages) so F1 reaches users. F2/F3/F4/F5 from `r2-judge.md` are separate findings, not addressed here.
