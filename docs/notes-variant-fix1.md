# notes-variant-fix1 — D-0019 MAJOR-1 dispatch fix (variantreg.build_variant)

Fix for `docs/verify/variants.md` MAJOR-1 (+ MINOR-1 coverage). 2026-07-27.

## The bug
`public/api/_lib/variantreg.py` `build_variant`, roll-defined/mod-variant branch. Dispatch was:

```python
if family_all or is_aura:      # <- family_all is TRUE for EVERY family
    picked = [...while affected by...]
    label  = ... or "aura variant"
elif is_presence: ...          # unreachable
elif def_ids: ...              # unreachable
```

`family_all = any(from.match == "family-all")`. The registry builder (`defining_family`)
stamps `match:"family-all"` on **every** roll/mod-variant defining family, so `family_all`
was always True → the `is_presence` and `def_ids` branches were dead code. Any family whose
defining mods are NOT phrased "while affected by …" fell into the aura branch, matched 0 mods,
and got `filters=[]` + `label="aura variant"`.

## The fix (dispatch by emit + the copy's actual mods)
Removed `family_all` and `is_aura`. New order (variantreg.py:275-301):
1. `emit == "presence"` → pick the `1 Added Passive Skill is <Notable>` flags.
2. else a **real** `while affected by` mod is on the copy (`aura_mods` computed from `resolved`)
   → the aura branch.
3. else `def_ids` (copy mods resolving to a defining id).
4. else (roll-defined only) own rolls. Never a name-only unique search.

Nothing else in the function changed; `add()`, the emit loop, and the fallback are intact. The
querybuild consumer (`price_unique_ninja`, querybuild.py:737) still fills the label from the
ninja variant string only when `var["label"]` is empty — so pure-ninja mod-variants keep their
ninja label and the newly-fixed items keep their defining-mod label.

## Per-item outcome (verified live via build_variant, probe + hermetic _verify)
| Item | class | before | after |
|---|---|---|---|
| Megalomaniac | roll-defined (presence) | own-rolls, `label="aura variant"`, flagged "Adds N Passives" | 3 notable filters `stat_2780712583/2342448236/3599340381` each `{min:1}`; `label="Touch of Cruelty, Prismatic Heart, Fuel the Fight"` |
| Aul's Uprising | roll-defined (reservation) | `label="aura variant"`, generic +Life | own-rolls; captures `<Aura> has no Reservation` (`stat_2930404958`, valueless presence filter) + life; `label="rolled variant"` |
| The Light of Meaning | mod-variant (family=1) | `filters=[]`, `label="aura variant"` (LIVE-confirmed) | `filters=[{stat_607548408:{min:roll}}]`; `label` = the "…in Radius" amplify mod |
| Vessel of Vinktar | mod-variant (family=18) | `label="aura variant"` | `label=""`, `filters=[]` → ninja map-variant prices it (mislabel gone) |
| Watcher's Eye / Sublime Vision / Circle-of-X / Doryani's Delusion | aura families | correct (via family_all) | correct (via real aura_mods) — **no regression** |
| Split Personality / That Which Was Taken | own-rolls | correct | correct (unchanged) |

Doryani's Delusion element-pen copies ("Damage Penetrates % Lightning Resistance while
affected by Wrath") now get their element filter via the aura branch — the rep id
`stat_1077131949` literally contains "while affected by Wrath".

## Registry-richness limitation (NOT this fix — noted for backlog)
Aul's Uprising (reservation, 116-member family, `samples:[]`) and Vessel of Vinktar (lightning,
18, `samples:[]`) can't match a defining filter from the registry **rep** id unless the copy
happens to name that exact rep mod — the rep is just the sorted-first family member, not the
copy's mod. `def_ids` therefore misses and they fall to own-rolls (Aul's) or ninja map-variant
(Vessel). Both are strictly better than the old "aura variant" mislabel. Fully faithful trade
filters for these would require the builder to serialise the whole family's ids (or a matchable
text predicate) into the entry — a `build_variant_registry.py` change + rebuild + determinism
re-check, out of scope for the dispatch bug. Vessel/Light-of-Meaning are ninja map-variant
(not floor-only), so a trade filter is a bonus there, not the sole price handle.

## Tests
- Added 6 hermetic assertions to `public/api/_verify.py` `phase_variant` (closes MINOR-1: the
  presence/reservation/non-"while affected by" gap that let MAJOR-1 ship green). Direct
  `build_variant` checks for the 4 items + one end-to-end `price_unique_ninja` floor check that
  the presence label reaches `variant_info` and is not overwritten.

## Harnesses (all green, 2026-07-27)
- `python tests.py` → all passed
- `BPC_SKIP_LIVE=1 python public/api/_verify.py` → ALL CHECKS PASSED (incl. 6 new)
- `python tools/build_variant_registry.py --check --offline` → validated OK; 40 items, 38 stat
  ids resolve, 0 crosscheck drops (registry + builder untouched — no drift)
- `node public/site/test_picker.mjs` → 83/0
- `node public/site/test_scanstatus.mjs` → 47/0
- `node extension/test_protocol.mjs` → PASS

Files changed: `public/api/_lib/variantreg.py` (fix), `public/api/_verify.py` (fixtures).
Registry JSON + builder NOT modified.
