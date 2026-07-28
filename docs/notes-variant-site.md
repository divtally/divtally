# Notes — VARIANT surfacing in the SITE (D-0019 consumer, site side)

**Date:** 2026-07-27 · **Scope of this change:** `public/site/**` only (+ this notes doc).
**Spec:** `docs/00-decision-log.md` **D-0019** (variant-unique registry + timeless jewels) under
**D-0015** (never drop mods the user kept — locking variant-defining mods ADDS required filters, so
it is MORE faithful to the item, not less). **Interface:** `docs/public-contract.md` variant section
(coordinate via the contract ONLY). **Registry (read-only context):** `docs/notes-variant-registry.md`
— DivTally's own `public/api/_data/variant_uniques.json` (40 items: 5 timeless seed-jewels,
4 notable-jewels incl. Forbidden Flesh, 7 socket-defined, 6 roll-defined, 18 mod-variant).

> STATUS: **in progress.** This file starts as a pre-implementation analysis (compaction insurance,
> RULE 2) and is finalised with the verification results once the code lands.

---

## What the site must do (task spec, verbatim intent)
1. **Unique rows with variant info** show the **variant label under the name**
   (`"Allocates: Unnatural Instinct"` / `"Lethal Pride - seed 11711, Kaom"`) **+ a lock glyph on the
   defining mods**.
2. The **picker ("edit affixes") for such uniques** lists **defining mods as LOCKED-required**
   (visible, not removable — they ARE the item; D-0015 note: locking reflects item identity, the user
   can still **Skip** the whole item) alongside any optional rolls.
3. **Timeless jewels:** the row **note explains honestly** — "priced by exact seed+keystone; thin
   market — verify via trade link".
4. Keep harnesses green (`test_picker` / `test_scanstatus` + `node --check`); extend `test_picker`
   with a **locked-defining-mod** case. `?mock`: add ONE variant unique (**Forbidden Flesh**) + ONE
   **timeless jewel** to sample data. Bump the asset `?v=` in index.html.

---

## Code map — exact injection points (verified by reading)

### Files & ownership (all mine)
- `public/site/index.html` (147 KB) — CSS in `<head>`; one big inline `<script>` (render + picker).
- `public/site/assets/core.js` (1269 lines) — pure logic; picker query builder; the node-test surface.
- `public/site/assets/sample.js` — `window.BPC_SAMPLE` demo build (mock data). MY definition, but the
  SHAPE must match the contract so the real site renders it identically.
- `public/site/test_picker.mjs` — offline node tests of the query builder (loads core.js via require).
- `public/site/test_scanstatus.mjs` — offline node tests of the scan protocol (loads core.js in a vm).

### Where "unique rows" render the NAME (candidates for the variant label)
- **Tooltip** `showTip()` index.html ~1548: `.tt-head` = name; `modsHTML(it.mods)` lists mods; `.base`
  sub-line class already exists (serif, under the name) → natural home for the **variant label**.
  The mod list here is where a **lock glyph on defining mods** belongs (hover surface, full mods).
- **Board slot** `fillSlotContents()` ~1394: `.iname` (small tile label). Secondary surface.
- **Manual/rares rows** `manualRowHTML()` ~2122: `.mr-name` + `.mr-slot`. Only shows items that are in
  `manualRows()` (unpriced rares/magic, or unpriced uniques). A priced variant unique (floor) is NOT
  a manual row → the tooltip/board are the reliable surfaces for a priced variant unique's label.

### The PICKER (edit affixes)
- Opens via `openPicker(k)` ~1701 — **requires `rareData(k)` = `bpc.rareOf(k)` = `state.rares[k]`**.
  Per contract §2.6 the `rares{}` map ALREADY includes uniques, so a variant unique will have an entry.
- **Entry points currently gate OUT uniques** (must be opened for variant uniques):
  - `isPickableRare(it)` ~1668 → `it.category==='rare'` only.
  - board click ~1502 → rare/magic open the picker/manual; uniques open the trade URL.
  - `manualRowHTML` affix button ~2129 → `it.category==='rare'` only.
  - `fillSlotContents` edit pip ~1386 → rare/magic only.
- **Survey row render** `svRowHTML(a,i,kind)` ~1837: the priority-tier segmented control (`.svseg`
  with required/nice/notneeded buttons) + min/max inputs. A **locked** defining mod must render here
  with the tier control REPLACED by a lock indicator (forced required, not changeable) — but still
  listed (visible), and still contributing its filter.
- Query build: `pkBuildQuery()` ~1774 → `bpc.buildRareQuery(rare, applyScope(...), currentPicks())`.
  `buildRareQuery` (core.js ~1024) already emits every ticked searchable affix's filter; a locked
  defining mod is just an always-ticked, required affix — the builder needs NO change IF the affix
  arrives as a normal searchable stat with the right prefill. Locking is a UI + tier concern.

### Timeless-jewel NOTE
- `price.note` flows to the tooltip `.tt-note` (~1578) and the manual-row note (~2143). If the API
  sets an honest note on timeless jewels, it surfaces already; the site may additionally hard-surface
  the "verify via trade link" line for the `unique` variant class.

### CSS patterns to mimic (palette: `--bz3`#c8aa6e bronze, `--unique`#af6025, `--parch`#aa9e82)
- Badge: `.sk-granted` ~205 (mono 9px uppercase, bronze border) → model for a `.variant-tag`.
- Sub-line under a name: `.tt-head .base` ~515 (serif, under name) → model for the variant label.
- Tier control: `.svseg`/`.segbtn` ~657 → the thing a lock replaces on a locked row.

---

## Asset version convention
`index.html` loads `fonts.css` / `sample.js` / `core.js` with `?v=20260727e` (date + letter suffix).
`config.js` is loaded WITHOUT a version (deploy-time file) — leave it. Bump the three versioned assets
to the next letter (`20260727f`) so browsers re-fetch the changed core.js/sample.js.

---

## Contract dependency (BLOCKING — polling `docs/public-contract.md`)
Building the consumer, the mock shape, and the test assertions all need the exact field names the API
emits for a variant unique / timeless jewel. Polling for the variant section (background poller).
**Do NOT guess field names into committed code** — wire to the landed contract. Expected additions
(from the registry notes; to be CONFIRMED against the contract before coding):
- an affix flag marking a **defining/locked** mod in `rares[k].affixes[]`;
- a **variant label** string on the item/price (richer than the existing `price.variant`);
- a timeless-jewel signal (method value and/or honest `price.note`; seed-exact min=max prefill).

## Verification plan
- After each owned file: `node --check` (core.js, sample.js) + `node test_picker.mjs` +
  `node test_scanstatus.mjs`; the picker/scanstatus harnesses also parse-check the index.html inline
  script. Baseline to preserve: **test_picker 83 · test_scanstatus 47** (per notes-v2-site.md).
- New: a `test_picker` case proving a LOCKED defining mod is always emitted as a required filter and
  cannot be unticked/excluded by the picker state (D-0015 identity), while a normal optional roll on
  the same item still toggles.
- `?mock` end-to-end smoke (headless Chrome, offline) once implemented.
