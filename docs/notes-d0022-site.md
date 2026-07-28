# D-0022 item 2 — UNLOCK variant-defining mods in the affix picker (site)

**Scope:** the public site only (`public/site/index.html`, `public/site/assets/core.js`, tests).
Implements D-0022 item 2. Supersedes the forced-locked defining rows of D-0019/D-0020-R3.
D-0022 item 1 (the registry/API gap — Dragonfang's Flight) is a SEPARATE task on the API side.

## The decision (owner, verbatim in D-0022)
> "locking the mods is not necessary, if the user WANTS to deselect them they should be able to"

Defining mods now render as **NORMAL tier-controlled rows** (required / nice / not-needed),
**default required** (they define the item's price), but **fully deselectable**. A subtle
"variant-defining" hint stays. The client query builder **emits** the option/exact/seed filter when
the defining mod is ticked (required/nice) and **OMITS** it when the user sets it not-needed. Same in
the groups editor. The forced LOCK glyph is gone from the picker rows.

## What the defining mod's tier now means
| tier (user pick) | query effect |
|---|---|
| **required** (default) | the defining option/exact/seed filter is emitted in the AND group — the item's exact variant |
| **nice** | the same filter is emitted in the COUNT group (`match at least N`) |
| **not-needed** | the filter is OMITTED entirely (the deselect the owner asked for) |

The emitted **VALUE is always the item's identity** — the `{option:N}` split, the exact seed
`min==max`, or the roll min — built from the affix itself via `_definingFilter(a)`, never from the
picker's min/max. That is the reason the all-required default reproduces the D-0019 exact-variant
query byte-for-byte: only *whether* the filter is emitted changed, never its value.

Why the value stays identity-fixed (design choice, flagged): for an OPTION mod the filter has no
magnitude (`{option:N}`, `default_min/max` are `null`) and for an EXACT seed it must be `min==max`
(`default_max` is `null`, so a generic min/max box could not reconstruct it). Honoring an editable
magnitude would silently do nothing for those, so the defining row shows the value **statically**
(`svLockedValue`: `exact` / `= seed` / `≥ min`) beside the live tier control instead of editable
min/max inputs. The user's control is the tier (require / soften / drop), which is the owner's ask.

## Files changed

### `public/site/assets/core.js` (the query builder — the correctness-critical part)
- **`buildRareQuery`** defining branch: was *always* pushed in group 0 regardless of picks. Now reads
  the affix's pick — `if (!dpk.ticked) return;` (not-needed → **omit**), routes to its tier's group
  (`dpk.group`), then pushes `_definingFilter(a)` (identity value). Still handled BEFORE the
  resist-fold (D-0020 R3-1) so a defining RESISTANCE is never folded into a pseudo total.
- **`tierGroups`** counting loop: the special `if (a.defining) { req++; return; }` is gone; a defining
  mod is counted **by its tier** (required/nice). A defining resist skips the fold
  (`if (!a.defining && usePseudo && a.resist) return;`) so it still counts and creates its group.
- **`tierGroups` `place()`**: the special defining branch that forced `{ticked:true, tier:"required"}`
  is gone; a defining mod flows through the normal required→AND / nice→count / not-needed→untick
  routing, only skipping the resist-fold (`!a.defining`).
- `_definingFilter` comment updated (value is identity; D-0022 controls *whether* it is emitted).

### `public/site/index.html` (rendering + copy)
- **`svRowHTML`** (survey view): removed the `svLockedRowHTML` special-case. A defining mod now
  renders the normal `.svseg` segmented control (required/nice/not-needed, required selected by
  default) + a `variant-defining` hint + the static value (`svlockval`, spanning the min/max
  columns). No lock glyph, no lock chip. `svLockedRowHTML` deleted.
- **`grpAffixRowHTML`** (groups editor): defining rows now get a **checkbox** (`.acb`) and a
  **group-move** select (`.grpmove`), like any stat, plus the `variant-defining` hint and the static
  value. The `lockb` glyph + `afx.locked` styling are gone.
- **`renderSurveyBody`** + **`collectGroupRows`**: a defining resist is no longer folded away
  (`&& !a.defining`), so it shows as its own deselectable row (consistent with core.js R3-1).
- **`pkSync`** (survey): guarded the min/max read with `if(mn||mx)` so a defining row (no inputs)
  keeps its prefilled value instead of nulling it (matches the groups-view pattern).
- **Copy**: the variant banner no longer says "the search always requires them"; it now says the mods
  are "required by default … but you can set any to nice-to-have or not-needed to loosen or drop it".
  The "edit affixes"/pip tooltips + tt-link + two code comments that said "locked variant mods" now
  say "variant-defining". The item-card/manual variant tag reads "required by default in this item's
  trade search" instead of "locked into…". (LOCK_SVG is still used as the variant *label* marker on
  the item card tooltip/board tag — an accurate variant indicator, not a picker control.)
- **CSS**: `.svrow.locked`→`.svrow.defining`, `.afx.locked`→`.afx.defining`; dead `.svlockchip`,
  `.afx .lockb`, `.pvariant .lockg` removed; added `.vdef` hint + `svlockval` column-span rules.

### `public/site/test_picker.mjs`
Rewrote the D-0019 section (the fixtures VDEF/VORIG/VSEED are unchanged) to assert D-0022:
- defining **defaults required and is emitted**; no-picks + default-picks both reproduce the
  exact-variant ORIG (option split / exact seed).
- **unticking a defining mod DROPS its filter** (the exact opposite of the old locked assertion); the
  ordinary optional roll still toggles independently.
- **all-required tiers == the prior locked single-AND query**; **not-needed DROPS** the defining mod;
  **nice** moves it into the COUNT group still carrying its option value.
- **exact seed**: `min==max` when emitted (identity-locked against min/max edits), and **dropped**
  when the user deselects / not-needs it (both the direct-pick and tierGroups paths).

## Verification (all offline, no pathofexile.com)
- `node test_picker.mjs` → **107 passed, 0 failed** (was 98; +9 D-0022 assertions; core.js +
  index.html inline script parse-check green).
- `node test_scanstatus.mjs` → **131 passed, 0 failed** (unchanged — kept green).
- `node test_security.mjs` → **27 passed, 0 failed** (unaffected).
- Render smoke (scratchpad, extracts the real `svRowHTML`/`grpAffixRowHTML` from index.html): the
  defining survey row emits the live 3-button segmented control (required default) + `variant-defining`
  hint + static value + NO lock glyph/chip + no editable min; the defining groups row emits a checkbox
  + group-move + no lock. 14/14.

## Query-correctness invariant (the thing that must not regress)
`buildRareQuery(rare, origQuery)` and `buildRareQuery(rare, origQuery, rareDefaultPicks(rare))` (the
**autoscan / default** paths) are **unchanged** — every defining mod stays ticked+required by default,
so they still reproduce today's exact-variant query. The picker's survey default is likewise
unchanged (a `nice` optional roll still lands in the count group exactly as before). Only a
**user action** (untick / set not-needed) now drops a defining filter — precisely that one filter.

## Follow-up flags (NOT in this task's file scope)
- **`docs/public-contract.md` §2.6** still says of a `defining` affix: *"the picker should
  lock/highlight it."* The API **payload is unchanged** (still `defining:true`, `priority:"required"`,
  `option`/`exact`), so there is no functional contract break — but that advisory sentence is now
  stale and should read "highlight it (required by default, deselectable — D-0022)". Left untouched
  (file not owned by this task).
- **`docs/00-decision-log.md`** could get a "SHIPPED" addendum on D-0022 item 2 by the coordinator,
  in the style of D-0006/D-0009 (file not owned by this task).
