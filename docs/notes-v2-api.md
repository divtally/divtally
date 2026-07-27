# Notes — v2 API scope work (D-0016 item 2, API side)

**Date:** 2026-07-27 · **Scope of this change:** `public/api/**` only (+ additive contract doc).
**Spec:** `docs/00-decision-log.md` D-0016 item 2 (generic category default) under D-0015 (no
implicit affix exclusion — untouched here). **Status:** shipped; `_verify.py` green hermetic
(`BPC_SKIP_LIVE=1`) **and** with the live poe.ninja phase.

---

## What changed

The **default** search scope for **rare and magic** items is now the item's generic trade
**category** (`type_filters.filters.category.option`, the site's "Item Category" dropdown), e.g.
*any wand* instead of *Opal Wand*. The exact base is still built and offered as the user's
alternative. **Uniques are unchanged** (name + type).

This default flows through three consumer surfaces, all from one place (`_rare_scopes(item)[0]`):

- the item row's top-level **`trade_query`** (the POST body) and **`trade_url`** (the `?q=` link);
- the `rares[<index>]` picker entry's **`scope`** (human label) and **`scope_q`** (default scope);
- the new **`rares[<index>].scopes`** payload exposing BOTH scopes for the picker (rare/magic only).

`scopes` shape (contract §2.6.1):
```jsonc
"scopes": {
  "category": { "id": "weapon.wand", "label": "Wand" } | null,   // the default (generic)
  "base":     { "type": "Opal Wand", "label": "Opal Wand" } | null  // the exact-base option
}
```

### Fallback & selection rules
| item's slot maps to a category? | base is a known trade type? | default `scope_q` | `scopes` |
|---|---|---|---|
| yes | yes | **category** | `{category:{…}, base:{…}}` |
| yes | no  | **category** | `{category:{…}, base:null}` |
| no  | yes | **base** `{type}` (fallback) | `{category:null, base:{…}}` |
| no  | no  | none (no query built) | `{category:null, base:null}` |

`category` always wins when present; `base` is the fallback default AND the always-available
user option. Order in `_rare_scopes` is `[category, base]`; consumers take `scopes[0]`.

---

## Files changed
- `public/api/_lib/querybuild.py`
  - `_INVENTORY_CATEGORY` — comment updated (it is now the *default* scope, was a fallback).
  - **new** `_WEAPON_SUFFIX_CATEGORY`, `_CATEGORY_LABEL`, `_weapon_subcategory()`, `_is_quiver()`.
  - **new** `_category_option(item)` — slot→category, refined for weapons/quivers.
  - `_rare_scopes(item)` — reordered **category-first** (was base-first); uses `_category_option`.
  - **new** `scope_choices(item)` — builds the `scopes` payload.
  - `_magic_query(item)` — now category-default (was base `type` only), via `_rare_scopes`.
- `public/api/_lib/response.py` — `rares[]` entries: `scope`/`scope_q` reflect the category
  default; **new** `scopes` on rare/magic entries; uniques untouched (no `scopes`).
- `public/api/_verify.py` — new hermetic assertions (see below).
- `docs/public-contract.md` — additive: Status note, §2.5 bullets, §2.6 shape + §2.6.1, examples.

No other files touched (containment + file-ownership honoured). `bpc/` local app **not** changed.

---

## Category-id provenance — nothing invented

Every category `option` id the builder can emit is verified **present in the source-of-truth**
`research/data/trade_data_filters.json` ("Item Category" options list) by `_verify.py`, and every
`scopes` label is asserted to match that file's display **text verbatim**. Ids emitted:

`weapon`, `weapon.wand`, `weapon.bow`, `weapon.sceptre`, `weapon.claw`, `armour.helmet`,
`armour.chest`, `armour.gloves`, `armour.boots`, `armour.shield`, `armour.quiver`,
`accessory.belt`, `accessory.amulet`, `accessory.ring`, `jewel`, `flask`.

### Weapon subcategory — **[INFERRED]**, deliberately conservative
The trade *items* endpoint groups **all** weapons under a single "Weapons" label, so the base
name is the **only** weapon-class signal in bundled data — there is no base→class table. The
subcategory is therefore **[INFERRED — base-name suffix heuristic, NOT a source class table]**.
Only suffixes that are **unambiguously one trade category** are mapped (each verified against the
full 716-base weapon list: every base with that last word is that class, and nothing else is):

| base ends in … | → category | verified single-class? |
|---|---|---|
| `Wand` (69 bases) | `weapon.wand` | yes |
| `Bow` (65) | `weapon.bow` | yes |
| `Sceptre` (49) | `weapon.sceptre` | yes |
| `Claw` (27) | `weapon.claw` | yes (claws not ending "Claw" — Paw/Fist/… — stay generic) |

**Unmapped by design → generic `weapon` ("Any Weapon", always a correct scope):**

- **Swords, axes, maces/mauls** — the base name can't tell **one- vs two-handed**
  (`weapon.onesword`/`weapon.twosword`, `weapon.oneaxe`/`weapon.twoaxe`,
  `weapon.onemace`/`weapon.twomace`), so no single id is derivable.
- **Staves** — `weapon.basestaff` vs `weapon.warstaff` not derivable from the name.
- **Daggers** — `weapon.basedagger` vs `weapon.runedagger`, *and* most dagger bases don't
  contain "Dagger" (Knife/Skean/Stiletto/Kris/Ambusher/Sai/Shank/…), so a suffix map would
  miss them and can't split base vs rune anyway.
- **Rapiers/foils** — a single class (`weapon.rapier`) but split across suffixes ("Rapier",
  "Foil", Estoc, Smallsword, …); left generic to avoid a large hand-maintained name list.
- **`Rod`** — mixed: `Fishing Rod` (weapon.rod) **and** non-rod bases (Capacity/Eventuality/
  Potentiality Rod), so the suffix is not single-class → not mapped.

A base→item-class table (from a datamine) would let us map the ambiguous classes exactly; that
is a future enhancement, not attempted here (would go beyond bundled source data). The user's
**exact-base** option (`scopes.base`) always gives a precise search regardless.

### Quiver — correctness fix (not just a refinement)
A quiver shares the **Offhand** inventory slot with shields, so the old `Offhand → armour.shield`
map is **wrong** for a quiver — and flipping the default to category would have mispriced every
rare/magic quiver as a shield. A base ending in `Quiver` (every quiver base ends in "Quiver";
nothing else does — verified) is redirected to **`armour.quiver`**. `armour.quiver` is in the
source filters list.

Slots whose id is a correct **superset** are left generic and unrefined (all correct, just
broad): `jewel` covers base/abyss/cluster jewels; `armour.*`/`accessory.*` are exact per slot.

---

## Tests (`_verify.py`, hermetic phase A + live phase B)

- **Source-of-truth (A):** every emitted category id ∈ `trade_data_filters.json` options; every
  `_CATEGORY_LABEL` matches the source text verbatim.
- **Scope selection (B, synthetic items):** wand → default `weapon.wand` + exact-base
  alternative + `scopes` payload; Offhand quiver → `armour.quiver` (not shield); ambiguous
  weapon (`Vaal Blade`) → generic `weapon`; no-category slot → base-fallback default +
  `scopes.category == null`.
- **Contract (every response, incl. live):** rare/magic entries carry `scopes{category,base}`;
  when a category maps, the item's **default `trade_query` is that category** (`type_filters`
  option == `scopes.category.id`); when none maps, it **falls back to the exact base `type`**;
  uniques carry **no** `scopes` (unchanged).
- **D-0015 invariant preserved:** the pre-existing "default rare query requires every searchable
  affix (+ each defence total)" assertion still passes — scope changes don't touch `stats` /
  `armour_filters`.

**Fixture coverage:** the Allflame fixture drives the real paths — a **magic Thicket Bow**
(`Weapon2`) → `weapon.bow`, a **magic Quicksilver Flask** → `flask`, **rare jewels**
(`PassiveJewels`) → `jewel`. The live phase (41-item build) re-confirms `Thicket Bow →
weapon.bow` and the jewels/flask scopes on real data.

Run: `python public/api/_verify.py` → `ALL CHECKS PASSED` (both with and without
`BPC_SKIP_LIVE=1`).

---

## Open / future (not in this change)
- Exact weapon one-/two-handed + dagger + rapier subcategories need a **base→item-class table**
  (datamine); the suffix heuristic intentionally does not guess these. Tracked as a future
  enhancement; today they resolve to the correct-but-broad generic `weapon`.
- Jewel subcategories (`jewel.cluster` / `jewel.abyss` / `jewel.base`) are derivable by
  suffix ("… Cluster Jewel", "… Eye Jewel") and could be added the same way if the picker
  wants tighter jewel scopes; left generic `jewel` here (correct superset) to keep this change
  to the owner's named example (weapons).
