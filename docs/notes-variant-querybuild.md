# Wiring the variant-unique registry into pricing (D-0019, consumer phase)

**Date:** 2026-07-27 · **Scope:** the PUBLIC pricing path (`public/api/_lib/**` + `_verify.py`).
This is the CONSUMER half of D-0019: the registry artifact `public/api/_data/variant_uniques.json`
and its generator already existed (see `docs/notes-variant-registry.md`); this pass wires it into
querybuild / poe.ninja matching / the response, with hermetic tests. **No trade calls, no registry
regeneration** — the runtime reads the committed JSON only.

## What changed (files)
- **`_lib/variantreg.py` (NEW)** — the recipe engine. `lookup(name, base)` -> registry entry;
  `build_variant(item, entry, mapper)` -> a `VariantResult` (defining trade filters + locked mod
  indices + human label + owned count + ninja rule + confidence cap).
- **`_lib/refdata.py`** — `variant_data()` loader (bundled file, same pattern as stats/items;
  missing file -> empty registry, never an error).
- **`_lib/querybuild.py`** — `_variant_for(item)`; `_unique_query(item, var)` now injects the
  defining filters (additively over the skill-level + links filters); `affix_options` marks the
  defining mods (`defining/prefer/required` + `_apply_defining` sets base id / `option` / `exact`);
  `price_unique_ninja` is registry-aware (variant block in `extra`, ninja strategy, confidence cap).
- **`_lib/poeninja.py`** — `unique_price(..., reg_rule=, owned_count=)` + `_registry_price` and
  `_match_count_line` / `_match_variant_line` / `_match_base_line` / `_point_line`.
- **`_lib/response.py`** — promotes `extra["variant_info"]` to the item row's `variant` block
  (and excludes it from the `price` merge).
- **`_verify.py`** — new `phase_variant()` (hermetic) + `defining` field / variant-block checks in
  `validate_contract`. `models.py` unchanged (variant info rides `PriceResult.extra`, same pattern
  as the gem/host fields).
- **`docs/public-contract.md`** — additive: top note, item `variant` (§2.8), affix
  `defining`/`option`/`exact` (§2.6), `unique-ninja-floor` + confidence (§3).

## The three query encodings (from `variant-stats.md`, all verified live against the bundled schema)
1. **OPTION** (`notable-jewel`: Forbidden Flesh/Flame, Impossible Escape, Thread of Hope) — emit
   `{"id": base, "value": {"option": N}}`. **N is resolved by AXIS NAME**, not full-line text:
   `variantreg._option_axes` strips the boilerplate common to all `base|opt` children and matches
   the LONGEST remaining axis substring in the item's mod. This is deliberately robust to the item
   text diverging from the schema text — verified against the real divergences:
   Forbidden "...on Forbidden **Flame**" vs schema "...on Forbidden **Flesh**"; Impossible Escape
   "**Passives**"/no "Passage" vs schema "**Passive Skills** ... Passage"; Thread of Hope
   Large-vs-Very-Large (longest-match disambiguates). A full-line StatMapper match would FAIL these.
2. **EXACT** (`seed-jewel` timeless seed; `socket-defined` Voices/abyssal count) — split the item
   mod on `\n` (timeless seeds are `\n`-bundled with the "Conquered by" line), StatMapper each
   subline in the explicit group, emit `{"min": N, "max": N}`. Displayed seed == filter value
   (Elegant Hubris's displayed value is already the ×20 form; no transform).
3. **VALUE/roll-min** (`roll-defined` Watcher's-Eye aura combo; own-rolls) — StatMapper the item's
   own explicit mods, `{"min": roll}`. Watcher's Eye locks only the "while affected by" aura mods
   (the price identity); own-rolls uniques (Split Personality, That Which Was Taken) lock all their
   searchable rolls so they never fall back to a name-only search.

## poe.ninja matching by `ninja_variant_rule.strategy`
- **floor-only** (timeless / notable / roll-defined) -> the cheapest line = a LOW-confidence FLOOR
  (`unique-ninja-floor`). The `confidence_policy.cap` override is what stops a 6,000-listing floor
  from mis-rating as "high" (the whole point for timeless jewels).
- **map-count** (socket-defined) -> the line for the copy's count, mapped through the harvested
  `observed_variants[].abyssal_count` FIRST (Shroud of the Lightless's "1 Jewel" label carries 3
  abyssal sockets — non-literal), then the live label's integer.
- **map-variant** (Impresence, …) -> the line whose `variant` label tokens the copy's mods cover
  (≥0.6 and beats the runner-up).
- **map-base** (Grand Spectrum, Precursor's Emblem, Combat Focus) -> the line on the copy's base.

## Decisions / reconciliations worth recording
1. **Task overrides the registry's map-variant fallback.** The registry's `ninja_variant_rule.match`
   prose says an unmatched `map-variant` may "fall to the min..p90 range at LOW confidence". The
   TASK says **"no match -> unpriced + link (never cheapest-any-variant)."** I followed the task:
   for a REGISTRY item, no confident variant match -> `unique-unpriced` + trade link (source
   `none`), never a range/cheapest number. The legacy min..p90 `unique-ninja-range` path is kept
   ONLY for NON-registry multi-line names (unchanged behaviour, unchanged tests).
2. **Floor is shown (low), not suppressed.** `variant-audit.md` mused about making timeless jewels
   "no number at all". The registry (built later) chose to harvest a floor + cap it LOW
   (`ninja:"floor-low"`, `cap:"low"`), and `notes-variant-registry.md` §7.3 tells the consumer to
   honour the cap. So a floor-only unique shows a LOW-confidence floor number **plus** the
   exact-variant trade link — more useful than a blank, and honest (labelled a floor, min of the
   range). This satisfies the task's "roll-defined: ninja price allowed only w/ low confidence +
   range note".
3. **min==max prefill via `exact:true`, not two bounds.** The audit flagged that `_affix_defaults`
   had no min=max mode. Rather than set both `default_min` and `default_max` (which would break the
   contract's "≤1 prefilled bound" invariant + its `_verify` assertion), defining exact rows carry
   `default_min=N`, `default_max=null`, **`exact:true`** — the client locks `max=min`. Clean and
   invariant-preserving.
4. **Option ids are split at the source of truth.** The default unique `trade_query` emits the
   split form `{"id":base,"value":{"option":N}}` (the canonical trade wire form per
   `variant-stats.md` §0.1). The picker rows do the same (`_apply_defining`). No verbatim `base|opt`
   id is ever emitted. `_build_stat_groups`/`_statf` (rare-only paths) were NOT touched.
5. **D-0015 honoured.** Every filter is ADDITIVE: uniques previously carried an EMPTY stat group,
   so pinning the defining mods is strictly MORE faithful. The picker still lists every mod; the
   user drives any exclusion.

## FLAGGED for the D-0019 step-5 sole-trade-budget live spot-check (NOT resolvable under containment)
- **[INFERRED] option wire format.** No bundled dump runs an option-stat SEARCH. Strong indirect
  [SOURCE] evidence (GGG ships the stat dict pre-split and the trade site is built from it) says
  `{"id":base,"value":{"option":N}}` returns results, but this was not POSTed. One live search per
  form (Forbidden `Allocates`, Thread-of-Hope ring size, Impossible-Escape keystone) confirms it.
- **[INFERRED] Forbidden Flesh↔Flame stat direction.** The registry maps Flesh -> the stat whose
  text ends "Forbidden Flesh". My axis-name matcher is INDIFFERENT to the Flesh/Flame boilerplate
  (it keys off the notable name + the registry's per-item base id), so it is correct either way —
  but the live search should confirm the base id returns the item.

## Verification
`BPC_SKIP_LIVE=1 python public/api/_verify.py` -> **ALL CHECKS PASSED**, 0 failures.
- `phase_a` (unchanged fixtures) still green; the sample Allflame char's real **Elegant Hubris**
  now flows through the seed recipe end-to-end (variant block + exact-seed `trade_query` + picker
  `exact` row).
- `phase_variant` (new, hermetic): Forbidden Flesh (option filter + floor-capped-low), Watcher's
  Eye 2-mod (both aura filters, generic ES not required), Lethal Pride (seed min==max + conqueror
  id + floor-low), Voices (exact count + map-count "7 passives"), Shroud (map-count via non-literal
  label), Impresence (map-variant + unmatchable->unpriced+link), a non-registry unique keeping the
  legacy name-match, and the picker/variant-block payload.
Live phase B (one poe.ninja character) not run here (offline); it exercises the real handler and is
part of the D-0019 step-5 verify.
