# R1 fix pass 1 — all Round-1 findings fixed

**Round:** 1 (API end-to-end) of the D-0020 five-round bug campaign.
**Date:** 2026-07-28. **Scope:** the 13 findings in `docs/bugtest/r1-{build1..4,contract}.md`
(many are duplicates of the same root bug). Fixed in `public/api/` (+ vendored `bpc/` where the
same code is duplicated). Every fix is proven through the REAL code paths, not just asserted.

**Harness status after all fixes:**
- `public/api/_verify.py` — **ALL CHECKS PASSED** (hermetic phase A + variant, AND live phase B:
  41-item real Allflame character, priced=20, no `/api/trade` in the doc).
- `tests.py` (bpc offline) — **All self-tests passed.**
- `scratchpad/e2e_r1.py` (new, end-to-end through normalize→price_build→build_response) — **ALL
  E2E PASSED.**

The 13 findings collapse to **7 distinct root bugs** (A–G). Mapping:

| Finding(s) in the task | Cluster |
|---|---|
| 1 | **A** gem-group dedup drops distinct gems |
| 2, 4, 7, 12, 13, contract-F1 | **B** bad-URL → 502 instead of 400 |
| 3, 8, 11 | **C** link-split uniques mispriced (ignore `links`) |
| 5 | **D** implicit mods dropped from the affix picker |
| 6 | **E** foil unique (frameType 9/10) dropped |
| 9 | **F** 1-abyssal-socket unique unpriced (singular/plural) |
| 10 | **G** weapon-swap items summed into totals |

---

## A — Gem-group dedup dropped distinct duplicate gems  [major]
**File:** `public/api/_lib/poeninja.py` `normalize()` (+ vendored `bpc/poeninja.py`).
**Bug:** the skill-group dedup key was the coarse `(base_type, gem_level, tuple(support_names))`;
later groups matching it were *skipped* (dropped, never counted). Three physically distinct Raise
Spectre gems in one quiver (distinct ids) collapsed to one row → 2 gems dropped; undercounts every
minion/aura-stacking build. It also ignored quality/corruption, so the dropped copy could be the
pricier one.
**Fix:** dedup on the **set of the gems' stable ids** (`frozenset` of active + support itemData
`id`s). Distinct copies → distinct id-sets → all kept; a genuine weapon-swap duplicate (the same
physical gems surfaced twice) has the identical id-set → collapses. When any id is missing (a
granted gem has `id:null`) the group is never deduped (kept) — we never silently drop a gem.
**Proof (e2e):** 3 distinct-id Raise Spectre → 3 rows; same-id Herald-of-Ice twice → 1 row; a
granted gem with `id:null` → kept.

## B — Bad URL returned 502 `ninja_error` instead of 400 `bad_input`  [major, ×6 findings]
**File:** `public/api/_lib/engine.py` `prepare_from_url`.
**Bug:** `parse_build_url` raises `PoeNinjaError` for every URL-shape problem (build-overview
link, PoE2 link, wrong host, no `/builds/`); `build.py` maps every `PoeNinjaError` → 502
`ninja_error`. A user's most common mistake (pasting the overview page) looked like a retryable
upstream outage, and `error_type` actively misinformed a UI branching on it — violating contract
§4, which lists a build-overview link under `bad_input` (400).
**Fix:** wrap ONLY the `parse_build_url` call in `prepare_from_url` and re-raise its
`PoeNinjaError` as `engine.EstimateError` (→ 400 `bad_input`). `fetch_character` failures below it
are left as `PoeNinjaError` → 502, so genuine "poe.ninja unreachable / character private / not
found" still correctly classifies as `ninja_error` (contract-F3 confirmed 502 is right there).
Surgical: the parse step is the only client-side URL error; every fetch-stage error is untouched.
**Proof (verify promise-tests):** overview link → 400 `bad_input`; PoE2 link → 400 `bad_input`
(both hermetic — parse fails before any network call).

## C — Link-split uniques priced as a vague range; the link tier never selected  [major, ×3]
**File:** `public/api/_lib/poeninja.py` `PoeNinjaEconomy.unique_price` (+ new
`_link_tier_lines`), threaded from `querybuild.py` `price_unique_ninja`.
**Bug:** poe.ninja splits many chest/weapon uniques into per-link lines (a real per-line `links`
field of 5 / 6; <5-link copies share the base/unlinked line — confirmed in
`research/data/ninja_uniques_uniquearmour.json`). `unique_price` disambiguated only by
variant-TEXT tokens (all `None` on link-split lines) and never read `links` or the item's
`max_link`, so a 6-link Inpulsa's returned `min 10 (unlinked) / median 81 (5L) / high 291.8`
instead of its 6L line (~344.5). Wrong per-item numbers flowed into totals.
**Fix:** added `max_link` to `unique_price`; `_link_tier_lines(lines, max_link)` returns the
copy's link tier (≥6 → the 6L line, or the highest linked tier ≤ max_link when there's no 6L;
5 → the 5L line; <5 → the unlinked/base line) and `None` when the name isn't link-split or the
link count is unknown (never guesses). A single-line tier → a **point** price
(`matched:"variant"`, `variant:"6-link"/"unlinked"`, real confidence from listing count);
a tier that is ALSO text-variant-split narrows to that tier then runs the existing token
disambiguation within it. Registry uniques (reg_rule) are untouched. **Matches the link COUNT,
not the price**, so non-monotonic tiers resolve correctly.
**Proof:** verify unit tests (6L→344.5, 5L→81, <5L→10-base, unknown→range) + validated against
REAL poe.ninja data — Replica Farrul's Fur (5L 3609 > 6L 1768): a 6L item correctly picks 1768,
not the pricier 5L; Stasis Prison / Cloak of Tawm'r Isley / Saqawal's Nest all pick the right
tier.

## D — Implicit mods dropped from the affix picker  [major]
**File:** `public/api/_lib/querybuild.py` `affix_options` (+ `_rare_default_filters`).
**Bug:** `affix_options` iterated only `item.explicit_mods`; `item.implicit_mods` were never
emitted as picker rows, so a searchable, price-defining corrupted implicit ("Corrupted Blood
cannot be inflicted on you" on Kraken Star) was invisible — violating D-0015 ("the tool hides
nothing").
**Fix:** enumerate `item.implicit_mods`, matched in the `implicit` stat group
(`mapper.match(text, group="implicit")`), listed like any affix (greyed when unmatched). They are
**opt-in**: `group:"implicit"`, `prefer:false`, `default_min/default_max:null`, and excluded from
the default rare query (base implicits come with the base; D-0015's "requires ALL searchable
affixes" stays scoped to EXPLICIT-style affixes). Appended AFTER the pseudo fold is computed so
existing affix indices and every `folds[].index` are unchanged; `resist:false` (implicit resists
are not folded into the pseudo totals, which sum explicit resists only — kept out of scope to
avoid a total/fold mismatch; noted as the build1-5b follow-up).
**Proof (e2e):** the corrupted implicit is now a searchable `group:"implicit"` row with a resolved
`stat_id`, not prefilled, and NOT in the default query (which still carries exactly the 2
explicits). `_verify` D-0015 invariant updated to "all searchable EXPLICIT affixes" and still
passes for all 18 rares.

## E — Foil unique (frameType 9/10) mis-categorised `normal` and dropped  [blocker]
**Files:** `public/api/_lib/poeninja.py` `_categorise`, `public/api/_lib/models.py`
`FRAME_RARITY` (+ vendored `bpc/` copies).
**Bug:** `_categorise` routed only frameType 1–4; a foil unique (Nimis, frameType 10
`SupporterFoil`, rarity "Unique", ~7,680c) fell to `CAT_NORMAL` → no price, no trade link, absent
from `rares`, out of totals (~27% undercount). `FRAME_RARITY`'s comment wrongly claimed foils
reuse frameType 3 + a flag.
**Fix:** route `frameType in (3, 9, 10)` → `CAT_UNIQUE`, with a final fallback to
`rarity == "Unique"` for any other foil frame id GGG adds; add `10:"Unique"` to `FRAME_RARITY`
and correct the comment. Fixed in the public code and the vendored `bpc/` (the blocker note
called out both).
**Proof (e2e):** a frameType-10 Nimis normalises to `category:"unique"`, prices from poe.ninja
(7680c), appears in `rares`, and is in the totals. tests.py gains `ft9→unique`, `ft10→unique`,
`rarity=Unique fallback` (existing ft 1–5/0 assertions unchanged).

## F — 1-abyssal-socket unique left UNPRICED (singular/plural)  [major]
**File:** `public/api/_lib/variantreg.py` `build_variant` (`socket-defined` branch).
**Bug:** the matcher parsed mod text for the plural stat "Has # Abyssal Sockets", but a 1-socket
copy renders the SINGULAR "Has 1 Abyssal Socket", which the StatMapper returns `None` for. So
`owned_count` stayed `None` → unpriced, `locked_stats:[]` (violates D-0019's required filter),
`label:"count variant"` (violates contract §2.8). Hits Bubonic Trail, Shroud of the Lightless,
Lightless Gate, Command of the Pit, etc.
**Fix:** derive the abyssal count from the copy's **socket array** (`sockets[].attr` /
`.sColour == 'A'`) — ground truth, as the registry's own note directs — when the mod-text match
fails, and locate the abyssal mod line (by substring) for the picker highlight. Fixes the price
(map-count → the "1 Jewel" line, 1c), the required trade filter (min==max==1), and the label
together. The plural path (2+ sockets, e.g. the Shroud test) still matches via text — the socket
fallback only fires when text-match fails.
**Proof (verify):** Bubonic Trail with singular text + a 1-abyssal socket array → priced 1c via
map-count, `locked_stats` non-empty, real label, and `trade_query` carries
`explicit.stat_3527617737 {min:1,max:1}`.

## G — Weapon-swap items summed into server totals / priced_items  [major]
**File:** `public/api/_lib/response.py` `_sum_tier`, `_priced_ninja` (+ new `_is_swap`).
**Bug:** both summed every poe.ninja-sourced row with no swap filter, so `swap:true`
(Weapon2/Offhand2) gear inflated `totals` and `priced_items` — contradicting D-0018 ("swap items
out of totals by default") and the site's own client-side `core.js totals()`.
**Fix:** skip `swap` rows (inventoryId Weapon2/Offhand2) in `_sum_tier` and `_priced_ninja` by
default, mirroring core.js. Swap items **stay** in `items[]` and `rares{}` (each flagged
`swap:true`) so the "weapon swap" toggle can re-include them client-side — and so the contract's
"every rare/unique/magic item has a picker entry" invariant holds.
**Proof (e2e):** Headhunter (main) + Silverbranch (Weapon2) + Replica Maloney's (Offhand2) →
`totals.median = 15000` (not 15018), `priced_items = 1` (not 3); all 3 still in `items[]` with
`swap:true` and all 3 still in `rares{}`.

---

## Contract / doc updates (additive, kept back-compatible)
`docs/public-contract.md`: added a dated D-0020-R1 update note; §2.2 (swap excluded from totals),
§2.3 (`swap` field + foil/relic rarity), §2.6 (`implicit` group, opt-in), §3
(`unique-ninja-variant` now covers link-tier). No schema field removed or renamed.

## Notes / deliberate non-expansions
- **bpc/ `unique_price`**: the local `bpc/poeninja.py` has **no** unique-overview pricing (it
  prices uniques via a trade search — see `engine.py`), so clusters C has no bpc counterpart to
  fix (the finding's "same code in bpc/" is inaccurate for this method). Cluster A's gem dedup and
  cluster E's `_categorise`/`FRAME_RARITY` ARE duplicated in bpc/ and were fixed there too.
- **Implicit resist → pseudo fold** (build1 finding 5b, a MINOR sub-note): left out of the pseudo
  totals to avoid a total/fold inconsistency and scope creep beyond finding 5 (the picker
  omission). Implicit resists are independently searchable as their own rows.
- Cluster B leaves genuine fetch failures (character not found / private / poe.ninja down) as 502
  `ninja_error` — correct per contract §4 and confirmed by the contract auditor.
