# notes-variant-fix2 — D-0019 The Light of Meaning: WRONG defining stat + fictional test

Fixes `docs/verify/variants-r1.md` MAJOR r1-1 (registry data + test-validity). 2026-07-27.
Supersedes the LoM row of `docs/notes-variant-fix1.md` (which fixed only the dispatch/label and
described LoM emitting `stat_607548408` — true only for the fictional fixture, never a real copy).

## The two defects
1. **[major] Registry data wrong.** `variant_uniques.json` → The Light of Meaning defined its
   variant as `explicit.stat_607548408` "#% increased Effect of non-Keystone Passive Skills in
   Radius". That is **Might of the Meek's** mod (raw ninja `detailsId ...might-of-the-meek...`),
   not a current Light of Meaning mod — a presence filter on it matched **0 of 913** live LoM
   listings (variants-r1.md sec 3). Real copies carry the **"Passive Skills in Radius also grant
   X"** family (evasion `stat_3761482453`, mana `stat_3382199855`, ...). Driven offline through the
   real `build_variant`, every REAL copy → `filters:[]`, `label:''` (class `mod-variant` has no
   own-rolls fallback), i.e. the MAJOR-1 "defining filter silently dropped" outcome persisted for
   every real copy — fix1 corrected dispatch/label, not the data. LoM has **no ninja variant lines**
   (`observed_variants:[]`, floor 10c), so the trade filter is its ONLY real price handle.
2. **[major] Test passed on a fiction.** `_verify.py:523-527` fed
   `"50% increased Effect of non-Keystone Passive Skills in Radius"` — the ONLY string that resolves
   to the wrong id, and one no real copy has — asserting `filters==[{stat_607548408:{min:50}}]`. That
   fixture passes on BOTH the wrong and the right registry, so the registry bug could never fail the
   suite (MINOR-1 "coverage" for this item = coverage of a fiction).

## Root cause of the rep-id gap
`defining_family` serialised only the **rep_id** (sorted-first family member). Runtime `def_ids`
was `{rep_id}`, so a copy naming any OTHER family member (`stat_3761482453` etc.) `∉ def_ids` → not
picked. Same class of gap fix1 flagged for Aul's/Vessel — but stronger here: the rep id was not even
a real LoM mod. (The claim "stat_607548408 was LoM's OLD/pre-rework mod" is **[INFERRED — community
memory, NOT source-confirmed]**; the source-confirmed fact is only that live copies carry the "…also
grant X" family and none carry stat_607548408.)

## The fix
**Builder** `tools/build_variant_registry.py`:
- `defining_family(...)` gained `serialise_family_ids=False`. When True it writes the WHOLE sorted
  family id list into `from.family_ids`. Off by default so the large aura/presence families
  (Watcher's Eye 144, Megalomaniac 301, Aul's 116 members) — priced by the aura/presence branches,
  which never consult these ids — are NOT bloated. The `False` branch is byte-for-byte the old call,
  so every other entry is unchanged (determinism preserved).
- LoM roster entry: predicate `"in Radius" and "increased Effect"` → `"Passive Skills in Radius also
  grant"` (15 explicit members); `serialise_family_ids=True`; `samples` = the two live-fetched
  members (evasion + mana); pred_label/note/confidence text corrected. rep_id is now the deterministic
  sorted-first member `stat_1223932609` (max-Life grant).

**Runtime** `public/api/_lib/variantreg.py`, roll-defined/mod-variant branch:
- `def_ids` now = each defining entry's `stat_id` **∪ `from.family_ids`**. Entries without
  `family_ids` are unchanged (Aul's/Vessel still rep-only → own-rolls / ninja-map, exactly as fix1
  documented). Only LoM opts in, so **only LoM's behaviour changes** — minimal blast radius.

**Test** `public/api/_verify.py` phase_variant:
- Replaced the fiction with real strings. `"…also grant 7% increased Evasion Rating"` asserts
  `filters==[{explicit.stat_3761482453:{min:7}}]` AND no filter is the legacy id; a second fixture
  `"…grant +6 to maximum Mana"` asserts `[{explicit.stat_3382199855:{min:6}}]` (proves per-member
  matching, not a hardcoded single id). Both FAIL on the old registry (proven: old data → `filters:[]`).

## Per-copy outcome (offline via real build_variant, determinism-clean)
| Copy | before (committed) | after |
|---|---|---|
| `…grant 7% increased Evasion Rating` | `filters:[]`, `label:''` | `[{stat_3761482453:{min:7}}]`, label = the grant mod |
| `…grant +6 to maximum Mana` | `filters:[]`, `label:''` | `[{stat_3382199855:{min:6}}]` |
| evasion + mana (two mods) | `filters:[]` | both AND-grouped, `locked_idx:[0,1]` |
| FICTION `…increased Effect … in Radius` | `[{stat_607548408:{min:50}}]` | `filters:[]` (legacy id ∉ family — correctly rejected) |

Regression guard PROVEN: the new test's assertion is `False` on a synthetic old-style entry
(legacy id, no family_ids → `filters:[]`) and `True` on the committed fixed registry.

## Scope / NOT done (out of scope; still as fix1 documented)
- Aul's Uprising (reservation, 116) and Vessel of Vinktar (lightning, 18) keep the rep-id limitation
  (own-rolls / ninja map-variant). variants-r1.md sec 5 point 3's broader "audit every family/
  `samples:[]` mod-variant entry against live copies" is a separate live-budget task — not touched.
  If later desired, the mechanism is already in place: pass `serialise_family_ids=True` for those
  entries and rebuild.

## Harnesses (all green, 2026-07-27)
- `python tests.py` → All self-tests passed
- `BPC_SKIP_LIVE=1 python public/api/_verify.py` → ALL CHECKS PASSED (incl. 2 rewritten LoM asserts)
- `python tools/build_variant_registry.py --check --offline` → validated OK; 40 items, 0 drops,
  all defining stat_ids resolve
- registry determinism: committed `variant_uniques.json` `items` == fresh rebuild (byte-identical,
  82415 bytes)
- `node public/site/test_picker.mjs` → 83/0 · `test_scanstatus.mjs` → 47/0 ·
  `extension/test_protocol.mjs` → PASS

Files changed: `tools/build_variant_registry.py`, `public/api/_lib/variantreg.py`,
`public/api/_data/variant_uniques.json` (regenerated), `public/api/_verify.py`.
