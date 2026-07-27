# Port notes - feedback round 1, fix pass 1 (D-0006 blocker/major remediation)

**Date:** 2026-07-26
**Spec of record:** `docs/00-decision-log.md` D-0006 + `docs/feedback1-spec.md` (SS B.1, SS D.1, SS E.1).
**Verification consumed:** `docs/verify/f1-data.md` (engine-side PASS + one out-of-engine finding)
and `docs/verify/f1-skins.md` (FAIL: 1 blocker, 1 major, 1 minor).
**Scope of this pass:** apply every verified blocker/major from those two reports plus the trivial
minors from the same reports. All changes are SOURCE-DERIVED (spec text, the engine code, the live
fixture, and the existing tests); no web-claimed or inferred numbers are involved.

---

## What was broken (verbatim from the verify reports)

1. **[blocker/major] `bpc/web.py` `_run_job` gem skeleton** still ran the PoE2-era heuristic
   `row["granted"] = not _inv.startswith("SkillSlot")`. In PoE1 every gem's `raw.inventoryId` is
   `None`, so this is `True` for EVERY gem. `core.js` reads the skeleton `it.granted` for both the
   GRANTED badge (`renderGems`) and the default-enable (`itemGranted` -> `enabled[k]=!itemGranted`),
   so on the live backend path every gem lit up GRANTED and defaulted OUT of the headline total -
   the exact owner-reported bug. Masked in `?mock` (sample.js carries correct flags), so a page
   boot alone did not surface it. (`f1-skins.md` Finding 1; `f1-data.md` SS7.)

2. **[major] `bpc/ui/binder.html:853`** called `bpc.itemGranted(k)`. `core.js` keeps `itemGranted`
   as a PRIVATE internal helper (`core.js:125`, used at `:344`) and does NOT export it
   (`core.js:489` export list omits it), so `bpc.itemGranted` is `undefined` -> `TypeError` inside
   `gemRowHTML`, which runs for every gem row before `renderGems` assigns `innerHTML` -> binder's
   whole gem section threw/blanked on ANY build with gems (mock included). Binder was the only skin
   affected; the other 9 read `!!it.granted` directly and classic reads it at `web.py`. (`f1-skins.md`
   Finding 2.)

3. **[minor] `bpc/ui/binder.html`** renamed the picker bulk-button ids to `#autoscanBtn` / `#skipAllBtn`
   instead of the spec-mandated `#pSearchAll` / `#pSkipAll` (feedback1-spec SS E.1 "do NOT rename these";
   SS E.4 relies on grepping those ids to find every picker copy). Functionally correct but diverged
   from the other 9 skins + classic. (`f1-skins.md` Finding 3.)

4. **[minor, additive] `bpc/web.py`** did not carry the optional SS D.1 host fields on the gem
   skeleton row, so skins could only group gems AFTER the price landed (via `priced[k].host_*`).
   (`f1-data.md` SS7 closing note.)

---

## Fixes applied (this pass owns the whole repo; all edits are additive to the contract)

### `bpc/web.py` - `_run_job`, the `if it.category == CAT_GEM:` skeleton block
- **SS B.1:** deleted the superseded PoE2 heuristic (`_inv = ...; row["granted"] = not
  _inv.startswith("SkillSlot")`) and the stale comment describing it, and replaced with the engine
  value: `row["granted"] = bool(it.granted)`. The engine already computes `it.granted` correctly
  from the character JSON (`itemProvidedGems` / `isBuiltInSupport`; `poeninja._gem_is_granted`) and
  it is unit-tested (`tests.py` "fixture: only the item-provided gem is granted" -> only "Herald of
  the Hive"). Per CLAUDE.md RULE 6 the old path is DELETED, not left as a dead fallback.
- **SS D.1 (additive):** copied the host fields onto the skeleton row so skins can group gems under
  their host BEFORE the price lands:
  `row["host_slot"] / host_name / host_base / host_unique / host_inventory_id = it.<same>`.
  All five are guaranteed present on the normalized `Item` (`models.py:62-66` defaults; asserted on
  the fixture at `tests.py:614-616`). `core.js gemHost()` already reads priced-first then falls back
  to these skeleton fields, so this is purely a group-before-price improvement - no consumer change.

### `bpc/ui/binder.html`
- **Line 853 (SS B.2):** `const granted = bpc.itemGranted(k);` -> `const granted = !!it.granted;`
  (`it` is the skeleton gem row from `bpc.gemGroups()`, always defined; plain property read cannot
  throw). Now identical to the 9 known-good skins and to spec SS B.2 ("read `it.granted` off the
  skeleton row"). Did NOT export `itemGranted` from core.js (the local read is the simpler,
  consistent fix and leaves the core.js contract untouched).
- **Picker ids (SS E.1):** `id="autoscanBtn"` -> `id="pSearchAll"` (glowing Autoscan, still wired to
  `bpc.searchAllRares()`); `id="skipAllBtn"` -> `id="pSkipAll"` (small non-glowing skip-all, still
  wired to `bpc.skipAllRares()`); the two `$('#...')` handler lookups updated to match. Only the ids
  changed - label, placement, glow class (`.autoscan`), and actions are unchanged, so binder now
  matches the project-wide id convention and the SS E.4 grep contract. Binder has a single picker
  renderer (grep confirmed), so no other copy needed the change.

No field was renamed or removed anywhere; the engine->UI JSON contract stayed additive.

---

## Verification (all OFFLINE; no pathofexile.com trade search/fetch/exchange calls)

- **`python tests.py` -> `All self-tests passed.` (exit 0).** The granted/host/flask engine
  invariants my one-liner now copies are all covered; no test asserted the old skeleton heuristic,
  so nothing needed updating and nothing regressed.
- **Static confirmation (grep):** binder no longer references `bpc.itemGranted` / `autoscanBtn` /
  `skipAllBtn`; it reads `!!it.granted` and uses `pSearchAll` / `pSkipAll`. The only remaining
  `SkillSlot` / `itemGranted` hits in the repo are (a) explanatory comments (web.py rationale,
  poeninja.py docstring) and (b) core.js's intentional PRIVATE `itemGranted` helper - all correct.
- **JS parse-check:** binder's inline `<script>` parses clean via node `vm.Script` (`OK: 1/1`).
- **Live `?mock` boot (`python -m bpc.web --no-browser --port 8926`, then killed):** server came up
  and every route returned HTTP 200 - `/`, `/v/binder?mock`, `/v/binder`, `/classic`,
  `/assets/core.js`, `/assets/sample.js`. The served `/v/binder?mock` HTML content-asserts the fix:
  no `bpc.itemGranted(` call, reads `!!it.granted`, carries `pSearchAll` + `pSkipAll`, no old
  `autoscanBtn`/`skipAllBtn`. web.py booting proves the SS B.1/D.1 edit imports and serves cleanly
  (classic UI unaffected).

**Correctness of the SS B.1 line by substitution:** the skeleton is now literally
`row["granted"] = bool(it.granted)`, and `it.granted` on the fixture is unit-tested to be
`[False x5, True]` (only Herald of the Hive, the Lost-Unity-granted skill). So the live backend now
badges only that one gem and defaults it (alone) out of the total - the owner's bug is closed
end-to-end. Driving the full threaded `_run_job` on the fixture was intentionally NOT done: rares/
uniques in that path would hit trade endpoints (banned this round), and the substitution + green
engine tests already establish the value.

## Residual / not-in-scope
- `core.js` intentionally unchanged: `itemGranted` stays a private internal helper (used for the
  default-enable at `:344`); only binder's misuse of it as an export was the defect.
- All other skins + classic were verified correct by `f1-skins.md` (flask belt, host grouping,
  Autoscan wiring, GRANTED consumer) - no changes needed.
