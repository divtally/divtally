# R1 fix re-verification pass 1 — LOCAL

**Round:** 1 (API end-to-end) of the D-0020 campaign. **Date:** 2026-07-28.
**Scope:** re-verify every fix claimed in `docs/bugtest/r1-fix1.md` (clusters A–G + contract
updates) resolves LOCALLY, all harnesses green, no regressions on the two most-affected builds.
**Method:** (1) read the fixed source in `public/api/_lib/` + vendored `bpc/`; (2) ran both
harnesses; (3) direct-engine invocation (`engine.run_estimate` → `response.build_response`) against
the two most-affected live poe.ninja builds; (4) hermetic `build._run` for the error paths. Only
poe.ninja was contacted — no pathofexile.com calls.

## Verdict: PASS
All 7 root-bug clusters are resolved in both the public code and the vendored `bpc/` copies where
duplicated. `public/api/_verify.py` = **ALL CHECKS PASSED** (phase A + variant + live phase B: 41
items, priced=20, no `/api/trade`). `tests.py` = **All self-tests passed.** The two most-affected
builds price correctly with every specific finding closed and no new drops. Two non-blocking notes
below.

## Harnesses
- `python public/api/_verify.py` → **ALL CHECKS PASSED** (0 failures). Phase B live char
  example-0416 fetched clean.
- `python tests.py` → **All self-tests passed.** Includes the new foil assertions
  (`ft9→unique`, `ft10→unique`, `rarity=Unique` fallback).

## Per-cluster source confirmation
| | Cluster | File(s) verified | Evidence |
|---|---|---|---|
| A | gem dedup on id-set | `_lib/poeninja.py:819-825` + `bpc/poeninja.py:598-603` | `frozenset(gem_ids)`; only dedups when `all(gem_ids)` (granted `id:null` → kept) |
| B | bad-URL → 400 | `_lib/engine.py:75-79` | only `parse_build_url` wrapped → `EstimateError`; `fetch_character` below stays 502 |
| C | link-tier selection | `_lib/poeninja.py:351-464`, `querybuild.py:731-733` | `_link_tier_lines` matches link COUNT (handles non-monotonic); point price when tier is single-line; `None` when unknown |
| D | implicit affixes | `_lib/querybuild.py:477-493, 514-515` | appended after pseudo fold; `group:"implicit"`, opt-in, excluded from default query |
| E | foil unique routing | `_lib/poeninja.py:570-579` + `bpc/:307-314`; `models.py:14` + `bpc/models.py:10` | `ft in (3,9,10)` + `rarity=="unique"` fallback; `10:"Unique"` in FRAME_RARITY |
| F | 1-abyssal singular | `_lib/variantreg.py:243-272` | count from `sockets[].attr/sColour=='A'` when text-match fails |
| G | swap out of totals | `_lib/response.py:100-131` | `_is_swap` skips Weapon2/Offhand2 in `_sum_tier` + `_priced_ninja` |

Contract doc (`public-contract.md`) carries the D-0020-R1 note (§ top, §2.2/2.3 swap, §2.6/§3
implicit + link-tier); decision log has `D-0020 R1` entry.

## Live re-verify — the two most-affected builds
**build3 `f1fti-6231/ArleAllflame`** (was: 1 blocker + 2 major + 2 minor)
- **E (blocker)** Nimis: `category:unique`, `unique-ninja`, median **7238c**, present in `rares`.
  Was `category:normal`, dropped, ~27% undercount. **FIXED.** No `category:normal` rows remain.
- **C** Inpulsa's 6L: `unique-ninja-variant`, point **350/350/350** (was range 10/81/291.8). **FIXED.**
- **D** 8 implicit picker rows now present. **FIXED.**
- **G** 1 swap-priced row (Atziri's Disfavour) excluded from totals/`priced_items`. **FIXED.**

**build4 `yalokk-2571/TimeForAurab`** (was: 4 major + 2 minor)
- **F** Bubonic Trail (1 abyssal socket, singular text): `unique-ninja-variant`, **1.0c**,
  `locked_stats` non-empty (min==max==1). Was `unique-unpriced` / empty filter / "count variant". **FIXED.**
- **C** Victario's Influence 5L: `unique-ninja-variant`, point **33.5** (was range 1/33/102.6). **FIXED.**
- **G** 2 swap-priced rows (Silverbranch, Replica Maloney's) excluded from totals. **FIXED.**
- **D** 10 implicit picker rows present. **FIXED.**

**Error paths (hermetic):** overview link → **400 `bad_input`**; PoE2 link → **400 `bad_input`** (B). **FIXED.**

### The `priced+unpriced != len(items)` gap is expected, not a regression
build3: 23+12=35 vs 36 items (Δ1 = the 1 swap-priced row); build4: 18+11=29 vs 31 (Δ2 = 2 swap-
priced rows). Post-G, a priced *swap* item is correctly in neither `priced_items` nor
`unpriced_items` (D-0018 "out of totals/scans/counts"), while still present in `items[]`/`rares{}`.
build4 `priced_items`=18 reconciles exactly: 19 (orig, incl 2 swaps) − 2 (swap excluded) + 1
(Bubonic now priced via F). No item is dropped.

## Non-blocking notes (not regressions; for owner/round tracking)
1. **`r1-fix1.md` header "all Round-1 findings fixed" overstates scope.** The 7 clusters cover
   every blocker/major + the swap & implicit minors, but several MINOR findings from the build
   reports are neither in a cluster nor listed as deliberate deferrals: uppercase `HTTP://` scheme
   (build2 m6), `EquipmentJewels` slot label leak (build4 m1), raw `#` account-fragment truncation
   (build4 m2), co-socketed active auras mislabeled as supports (build2 m4 / build3 5), no
   cache-bust / `fresh=1` ignored (build1 F4), 404 message quality (contract F3), wire-visible
   Cache-Control (contract F2), oversized-POST 413 JSON shape (contract F5). All are MINOR and out
   of the fix doc's stated 7-cluster scope, so they do not affect this PASS — but the "all findings
   fixed" wording is inaccurate and these remain open for a later pass.
2. **Bubonic label grammar:** renders `"1 Abyssal Sockets"` (plural word, singular count); the fix
   doc predicted `"1 Abyssal Socket"`. Cosmetic only — price, `locked_stats`, and non-placeholder
   label are all correct.

## Provenance
Source read read-only under `C:\scripts\buildpricechecker-poe1`. Live ground truth = poe.ninja
character + economy overviews via the project's own client. No pathofexile.com endpoint contacted.
Probe script kept in the session scratchpad (harness temp), not committed.
