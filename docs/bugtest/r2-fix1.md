# R2 FIX-1 — F1 (MAJOR): variant-unique 0-match placeholder counted in the headline

**Round:** 2 of the D-0020 campaign. **Finding fixed:** F1 (`docs/bugtest/r2-judge.md` §3;
reproduced on Build 3 = R2c-1 and Build 4 = R2d-1). **Scope of this fix:** F1 only. **Files touched:**
`public/site/assets/core.js`, `public/site/test_scanstatus.mjs`, `docs/00-decision-log.md`, this note.
**No deploy** (the coordinator deploys after). **Date:** 2026-07-28.

Every number below is source-derived: an offline-harness assertion or a live `bpc.totals()` /
`bpc.scanStatus()` / rendered-DOM reading from the verification run (`scratchpad/r2fix1_results.json`).

---

## 1. The defect (as judged)

A D-0019 **variant unique** (Watcher's Eye; Forbidden Flame/Flesh) gets a poe.ninja name-level
**placeholder** price at load and is counted at it. Its exact locked-mod trade search then returns
`total_found = 0`, but instead of falling back to link-only (as the 3 genuine 0-match rares do, and as
Bubonic Trail — a variant with **no** placeholder — correctly does) the row **kept the placeholder,
rendered it as its price, stayed `included`, and its warning chip cleared** — a misleading number in
the headline. Headline-visible at **2.9 % (55c / 1924.6c)** on Build 4's Watcher's Eye.

**Source-traced root cause (verbatim, pre-fix):** `foldBatch`'s `amount==null` branch called
`applyPrice(key, {…/* NO chaos */}, {include:false})`. In `applyPrice`,
`merged = Object.assign({}, cur, patch)` retained the load-time ninja placeholder chaos (patch had no
`chaos`), and the include gate `else if (!(key in state.enabled))` was **false** for a row already
enabled from its load-time economy price → `{include:false}` was a **no-op** → `totals()` kept summing
the placeholder. `method` became `extension`, so `needsScan()` no longer re-flagged it and the chip
cleared.

## 2. The fix (compliance with Locked D-0019 — no amendment needed)

D-0019 already says the floor is *"a PLACEHOLDER, not its price"* and *"unmatchable → link + no number
as ever"* (decision-log line 236). The code was non-compliant; this makes it compliant. Chosen the
judge's **primary** option (drop to link-only), not the keep-a-floor alternative (which would have
required amending D-0019). Three parts, all additive — no contract field added/removed/renamed:

1. **`dropIfPlaceholder(key, patch)` helper** (new, next to `needsScan`). Given a failure patch, it
   nulls the chaos **iff** the row's *current* price is still the ninja placeholder for a variant
   unique — `it.variant && chaos.median != null && /^unique-ninja/.test(method)` (mirrors `needsScan`'s
   own signal + "has a number to drop"). Evaluated **before** `applyPrice` overwrites `state.priced`,
   so it reads the pre-scan price. **Scoped to the placeholder only:** a real whisper / cache /
   prior-scan price is a different `method` and is never touched by a failed re-scan.
2. **All four `foldBatch` failure branches** (error, `amount==null`/nobuyout, no-rate, whole-chunk
   error/timeout) now wrap their patch: `applyPrice(key, dropIfPlaceholder(key, {…}), {include:false})`.
   A variant-unique placeholder that fails its exact search for *any* reason drops to link-only.
3. **`applyPrice` invariant** — added an `else { delete state.enabled[key]; }` to the
   `merged.chaos.median != null` gate. A row with no number must never stay counted; this clears the
   stale enable when the placeholder is withdrawn (and closes the one path that nulled a price without
   clearing its enable). `totals()` already skips null medians, so the row also leaves the `priced`
   count. Every other enable site already guarded on `median != null`; this row is now consistent with
   them.

Net effect: a failed variant-unique scan is now **indistinguishable from a 0-match rare** —
`chaos:{null,null,null}`, `enabled=false`, `source:"trade"`, link + no number.

## 3. Verification

### 3a. Offline harness (deterministic, real `core.js` in a Node `vm`)
Added `scenarioVariantPlaceholder` to `public/site/test_scanstatus.mjs` (drives the exact
autoscan → `foldBatch` → `applyPrice` → `totals` path with a fake extension). It reproduces the
load-time "both placeholders counted" state, then asserts: the 0-match placeholder drops
(`median null`, not enabled, `source trade`, terminal); a **successful** exact search *replaces* the
placeholder with the real price; the 55c leaves the headline (the exact F1 arithmetic); a genuine
0-match rare stays link-only (control); and **scoping** — a failed re-scan of a **cache-priced**
variant unique keeps its 300c (not a ninja placeholder). `node test_scanstatus.mjs` → **64 / 0**
(was 47 / 0).

**All harnesses green (re-run post-fix):**
`node public/site/test_scanstatus.mjs` 64/0 · `node public/site/test_picker.mjs` 98/0 ·
`node extension/test_protocol.mjs` PASS · `python tests.py` all passed ·
`BPC_SKIP_LIVE=1 python public/api/_verify.py` ALL CHECKS PASSED ·
`python tools/build_variant_registry.py --check --offline` validated OK.

### 3b. Live end-to-end (real extension v1.2.1 + real trade calls, no deploy)
Driver `scratchpad/r2fix1driver.mjs`: navigate the real `https://divtally.com` origin (so the
origin-locked extension content script injects) and **route-swap** `/assets/core.js` for the local
**fixed** file — a sentinel (`window.__CORE_SWAPPED__==='fix1'`) confirmed the swap took effect. Build:
**yalokk-2571 / TimeForAurab** (the F1 poster child). One full hands-free scan; the only
pathofexile.com traffic was the extension's own, under its limiter. **15 / 15 assertions PASS:**

| Row | Pre-fix (r2-build4.md) | Post-fix (this run) |
|---|---|---|
| **Watcher's Eye** (variant, 3-aura, tf 0) | 55c placeholder, **counted**, chip cleared | `chaos.median=null`, `enabled=false`, `source=trade`, `stage=nobuyout`, **DOM price empty** — link-only |
| Bubonic Trail (control, no placeholder) | 1.0c real match | 1.0c real match (`tf 2878`, done) — unchanged |
| 3 genuine 0-match rares | link-only | link-only (identical shape to Watcher's now) |
| **Headline** | `priced=28, included=26, min=1924.628c` (15.5 div) | **`priced=27, included=25, min=1869.628c`** (≈15.1 div) — exactly the **55c** removed |

Hard criteria still met: **(a)** scan-duration audit produced (`totalMs=67 480 ms`, matching the
report's 67.5/67.6 s); **(b)** hands-free fruition — auto-started at +5 s with zero clicks, **13/13
rows terminal, 0 stuck, 0 pageerrors, 0 console errors**; the 27.9 s window back-off on Watcher's Eye
resolved itself as an honest countdown. Raw capture: `scratchpad/r2fix1_results.json`,
`r2fix1_progress.jsonl`, `r2fix1_final.png`.

## 4. Notes / boundaries

- **Local-app edition N/A.** `bpc/ui/assets/core.js` (the stash-tab VIEW) has no
  `foldBatch`/autoscan/`unique-ninja` flow — F1 is exclusive to the public site. Confirmed by grep.
- **Scoping is deliberate.** A failed re-scan of a row carrying a *real* price (whisper/cache/prior
  trade) keeps that price — only the poe.ninja placeholder is droppable. This matches the finding's
  isolation of "the placeholder as the cause" (Bubonic Trail priced correctly).
- **F2 is separate and untouched.** The zero-match note copy ("listings exist but none had a buyout
  price") is F1-adjacent but is its own finding; this fix intentionally does not change that copy.
- **F1 fix does not depend on F3** (raw per-item `ms`); `totalMs` (used for the audit here) is correct.
