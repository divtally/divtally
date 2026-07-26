# v3 - Web UI smoke verification (no live pricing)

**Date:** 2026-07-26
**Scope:** Smoke-verify the served web UI of `buildpricechecker-poe1` WITHOUT any live
pricing. Confirm pages render, the `?mock` demo build shows chaos prices with a divine
secondary, and there is no PoE2 residue (poe2 / exalted / rune / trade2) in the served
HTML/JS. Verify league + listing-status controls, trade links, and the PoB copy block are
all PoE1-shaped.

**Method:** Started `python -m bpc.web --no-browser --port 8899` (bound 8899). Fetched every
page + asset over HTTP with a real User-Agent and grepped the **fetched response bodies**
(not the on-disk files) in-memory. **No pathofexile.com trade search/fetch/exchange endpoint
was called.** Server killed cleanly at the end (port 8899 listener count = 0 after kill).

> Note: on startup `web.main()` spawns a best-effort `_warm_stats` thread that does ONE static
> GET to `pathofexile.com/api/trade/data/stats`. That is a static `/api/trade/data/*` GET
> (explicitly allowed sparingly), not a search/fetch/exchange call. It fires automatically on
> boot; I did not trigger any additional trade calls (I never hit `/api/leagues`, `/api/stats`,
> or `/api/price`).

## Result: PASS (with 2 minor cosmetic PoE2-residue findings)

All 24 fetched targets returned `200` with correct content types and non-empty bodies. Mock
pricing, currency formatting, controls, trade links and the PoB block are all correct and
PoE1-shaped. Two **non-rendering** cosmetic leftovers remain in served HTML (dead CSS + one
themed string) - detailed below; neither affects behavior.

## What was fetched (all 200 OK)

| Target | Bytes | Content-Type |
|---|---|---|
| `/` (gallery) | 5,592 | text/html |
| `/classic` | 28,500 | text/html |
| `/v/{abacus,atelier,binder,console,facts,foundry,ledger,manifest,stash,waterfall}` | 36k-112k | text/html |
| each `/v/<skin>?mock` | identical bytes to no-query (query is client-side) | text/html |
| `/assets/core.js` | 22,434 | text/javascript |
| `/assets/sample.js` | 24,243 | text/javascript |

10 version skins + gallery + classic + 2 assets. `?mock` returns byte-identical HTML because
the server ignores the query string for `/v/<id>`; the demo is loaded client-side (see below).

## Checks

### Pages render
All 24 GETs -> `200`, non-empty, `charset=utf-8`. Gallery auto-discovers the 10 skins;
title is "PoE1 Build Price Checker - choose a look". Every skin ships an inline
`<script src="/assets/core.js">`-driven view. PASS.

### `?mock` demo shows chaos prices with a divine secondary
`?mock` is wired **client-side**: every skin (and `_reference.html`) contains
`if (location.search.indexOf('mock')>=0){ bpc.init({mock:true}); ... }`, which calls
`bpc.loadMock(window.BPC_SAMPLE)` and ingests the demo snapshot with **no backend/trade
calls**. Verified the data + formatter that produce the on-screen numbers:
- `sample.js`: `divine_to_chaos: 106`, `chaos_img` + `divine_img` present (real poecdn orb
  icons), full priced build (chaos min/median/high on every slot).
- `core.js` `price()`/`priceHTML()`: chaos is the canonical unit and is always shown; once a
  price reaches >= 0.5 divine (`ex >= div * 0.5`) it is displayed as `<div> <divine-icon>
  (<chaos> <chaos-icon>)` - i.e. divine headline with the chaos value kept in parentheses;
  below that threshold it shows chaos only. This is the intended "normalized to chaos, divine
  as the secondary/convenience unit" behavior. Worked example from the sample: Headhunter
  (idx 4) median 11,660 chaos / 106 -> "110 divine (11,660 chaos)"; a 5-chaos item shows just
  "5 chaos". PASS.

  (Rendering is client-side JS; this smoke test confirms the wiring + data + formatter logic
  that generate it, not a headless-browser paint.)

### No PoE2 / exalted / rune / trade2 residue in served bodies
Case-insensitive scan of all 24 bodies for `poe2`, `trade2`, `exalt`, `rune`:
- **`poe2`: 0 hits anywhere.**
- **`trade2`: 0 hits anywhere** (see trade-link check).
- **`exalt`: 1 hit** - `manifest.html` line ~569, static text `EXALT AIR` (the boarding-pass
  theme's fictional airline name: "EXALT AIR / Build Itinerary - Boarding Pass"). Decorative
  flavor, **not** a currency reference. Note `bpc/currency.py` legitimately lists "exalted"
  as a convertible PoE1 currency, so Exalted is valid in PoE1 - it just must not be the base
  unit (it isn't; base is chaos). See Finding 2.
- **`rune`: dead-CSS hits only** in 6 skins (`abacus .r-rune`, `console .rar-rune`,
  `foundry .mtag.rune`, `manifest --rune/.rtag.rune`, `stash .h-rune/.tt-mod.rune`,
  `waterfall --g-rune`). **Every occurrence is inside a `<style>` block** - a CSS class or
  custom property. The engine's category set is closed: `{unique, rare, magic, gem, normal}`
  (models.py) and group set `{equipment, flask, jewel, gem}` (core.js). Views build these
  classes from those live values (e.g. manifest `class="rtag ${rt}"` where `rt` derives from
  `it.rarity||it.category`), so `.rune`/`--rune`/`.currency` selectors **never match a
  rendered element**. Non-rendering PoE2 residue. See Finding 1.

Clean (zero forbidden tokens): 12/24 including gallery, classic, core.js, sample.js,
atelier, binder, facts, ledger.

### League + listing-status dropdowns are PoE1-valid
- **Listing status** - `core.js STATUS_ORDER`/`STATUS_LABEL` and the classic `<select>` both
  expose exactly `available, securable, onlineleague, online, any` (the 5 PoE1 trade-site
  statuses). No unexpected/PoE2 statuses. PASS.
- **League** - served statically as only the "League: auto" seed; the real list is fetched at
  runtime from `/api/leagues` (which I did not call, to avoid a trade endpoint). No hardcoded
  PoE2 leagues in any body. PASS.

### Trade links point at pathofexile.com/trade (not trade2)
`trade2`: **0 hits in all 24 bodies.** Static `pathofexile.com/trade` occurrences: `stash`
(2), `core.js` (1, the mock re-price stub `https://www.pathofexile.com/trade`), `sample.js`
(1, `_TU = "https://www.pathofexile.com/trade/search/Allflame?q=demo"` - PoE1 trade URL
form). Other skins render the trade link dynamically from `p.trade_url` (the mock supplies the
PoE1 `_TU`). PASS.

### PoB copy block labeled for PoE1
Every skin references `pob_code` and copies the Path of Building import code. Labels found are
PoE1-appropriate: "Path of Building import code" (classic, stash) and input placeholders
"...Path of Building code, or a pobb.in link..." (pobb.in is the PoE1 PoB paste host). **No
"Path of Building 2" / "PoB2"** anywhere. `sample.js` supplies a demo `pob_code` so the block
renders in `?mock`. PASS.

## Findings

### Finding 1 (minor, cosmetic) - dead `.rune` / `.currency` CSS leftovers from the PoE2 parent
6 skins carry `<style>` rules and CSS custom properties for `rune` (and `currency`) rarity/
group categories that the PoE1 engine never emits, so they never match a rendered element:
- `abacus.html:79` `.r-rune`, `.r-currency`
- `console.html:178` `.rar-rune`
- `foundry.html:162` `.mtag.rune`
- `manifest.html:17,235` `--rune`, `.rtag.rune`, `.rtag.currency`
- `stash.html:508,532` `.tt-head.h-rune`, `.tt-mod.rune`
- `waterfall.html:15` `--g-rune`

**Impact:** none at runtime (dead CSS). **Recommendation:** per CLAUDE.md RULE 6 ("dead
trade2/PoE2 code paths are bugs, not harmless residue"), strip these selectors/vars for
cleanliness. Owner of these files should make the edit (I only own this verify doc).

### Finding 2 (minor, cosmetic) - `EXALT AIR` themed string in manifest skin
`manifest.html:569` renders the static string `EXALT AIR` as the boarding-pass theme's
airline name. It is decorative flavor, not a currency/PoE2 reference (and "Exalt" is a valid
PoE1 currency name anyway). Flagged only because it literally contains "exalt" and the brief
called out `exalted` residue. **Recommendation:** owner's call - likely intentional theme
flavor; rename (e.g. "CHAOS AIR" / "DIVINE AIR") only if the coincidental "exalt" substring is
undesirable. No functional impact.

## Environment / commands
- `python -m bpc.web --no-browser --port 8899` (bound 127.0.0.1:8899)
- fetches via `requests` with UA `bpc-smoke/1.0`; all grepping done in-memory on response
  bodies (no body files written to disk; containment respected)
- server stopped by `Stop-Process` on the PID owning port 8899; post-kill listener count = 0
