# F1-R1 — Re-run of the cross-skin consistency review of D-0006 (resolution + regression check)

**Spec of record:** D-0006 (`docs/00-decision-log.md`) + the UI implementation spec `docs/feedback1-spec.md`.
**Prior round:** `docs/verify/f1-skins.md` (FAILed: 1 blocker, 1 major, 1 minor) and `docs/verify/f1-data.md`
(engine PASS + the out-of-engine §B.1 gap). This re-run checks whether those findings are actually
resolved and whether anything regressed.
**Scope reviewed:** all 10 gallery skins (`bpc/ui/*.html`), the classic UI (`PAGE`/handlers in
`bpc/web.py`), and shared `bpc/ui/assets/core.js` + `sample.js`. Read-only except this file.
**Method:** targeted re-read of every prior finding site; broad greps for the old granted heuristic,
life/mana flask residue, `itemGranted` callers, and the full Autoscan/skip-all wiring across every
skin + classic; core.js export set diffed against every `bpc.*` call in binder; offline parse of all
12 skins' inline scripts (`node` `vm.Script`, parse-only), `node --check` on core.js/sample.js,
`ast.parse` on web.py; live spot-boot `python -m bpc.web --no-browser --port 8927` (7 routes HTTP 200,
then the process was force-killed and port 8927 confirmed closed).
**No pathofexile.com trade search/fetch/exchange endpoints were called.**

## VERDICT: **PASS** — all 3 prior findings resolved; no regressions found.

---

## Prior findings — resolution status

| # | Prior sev | Site | Status | Evidence |
|---|-----------|------|--------|----------|
| 1 | BLOCKER | `web.py` §B.1 granted passthrough | **RESOLVED** | `bpc/web.py:316` now `row["granted"] = bool(it.granted)`. The old `inventoryId`/`SkillSlot` heuristic is **deleted**, not left as a dead fallback (only referenced in the explanatory comment at L312-315). Grep for live `SkillSlot` logic in `bpc/` returns only comments (web.py:313, poeninja.py:499) + a stale `.pyc`. |
| 2 | MAJOR | `binder.html:853` un-exported `bpc.itemGranted` | **RESOLVED** | `binder.html:853` now `const granted=!!it.granted;` — reads the corrected skeleton field directly. `bpc.itemGranted` appears in **no** skin anymore (only as the private `core.js:125` helper, used internally at L344). The distinct `bpc.*` call set in binder no longer contains `itemGranted`; every remaining `bpc.*` call resolves to a real `core.js` export. |
| 3 | MINOR | `binder.html` picker ids renamed | **RESOLVED** | binder now uses the spec ids `#pSearchAll` (L1103) and `#pSkipAll` (L1128), wired at L1148-1149 to `searchAllRares`/`skipAllRares`. It now matches the §E.4 grep contract shared by the other 9 skins + classic. |

The engine side (`f1-data.md`) was already PASS; its lone gap was the `web.py` §B.1 one-liner, which is
finding 1 — now applied. **Bonus (additive, not a regression):** `web.py:320-324` now also copies the
optional §D.1 host_* fields (`host_slot/host_name/host_base/host_unique/host_inventory_id`) onto the gem
skeleton row, so skins can group before the price lands; `core.js gemHost()` reads priced-first then
falls back to these — additive, contract-preserving.

---

## Regression sweep — all previously-passing checks still hold

### (1) Flask belt — PASS (all 10 skins + classic), no regression
Every belt still renders ≥5 generic slots in flask order with overflow preserved and no life/mana
classification. binder (the edited skin) still `renderBelt` with `SLOTS=5; Math.max(SLOTS, items.length)`
(L809-812). The only `life/mana` string matches in the tree are **sample.js comments stating there are
NO life/mana slots** — no classifier code (`lifeFlask`/`manaFlask`/`isLife`/`classifyFlask`) exists.

### (2) Gems grouped by host + GRANTED — PASS, no regression
- Grouping: all skins still bucket via `bpc.gemGroups()` and nest supports via `bpc.gemBreakdown()`
  (index-aligned). binder still calls both (L830, L850). Host-less gems fall under the `""` bucket; no
  drops.
- GRANTED consumer: **all 10 skins + classic now read `!!it.granted`** — 9 already did, binder now does
  too (finding 2). classic reads it at `web.py:1003` (`const granted = !!it.granted`). Zero
  `inventoryId`/`SkillSlot` reads in any skin.
- Producer: `web.py:316` feeds the correct engine value into that already-correct consumer logic, so the
  live-path "everything GRANTED + defaults out of total" bug is closed end-to-end.

### (3) Autoscan — PASS, no regression
- Every skin's glowing top button carries `id="pSearchAll"` and is wired to `bpc.searchAllRares()`; every
  small non-glowing below button carries `id="pSkipAll"` → `bpc.skipAllRares()`. **No skin wires Autoscan
  to `skipAllRares`** (the price-nothing trap). Verified across abacus, atelier, binder, console, facts,
  foundry, ledger, manifest, stash, waterfall, and classic (`web.py:1154/1171/1244-1245`).
- **Every picker copy covered:** `stash.html` still has three renderers (Autoscan+skip pairs at
  L1486/1501, L1747/1763, L1790/1809) — all three consistent. No leftover old bottom
  "Search all N (default)" markup anywhere (grep clean).
- (Note: `abacus.html:749` binds Enter-to-Autoscan (`searchAllRares`) when >1 rare remains — a keyboard
  shortcut, correct action, not a finding.)

### (4) Layout / syntax / exports — PASS
- Parse: all 12 skins' inline scripts parse clean (`vm.Script`); `core.js` + `sample.js` pass
  `node --check`; `web.py` passes `ast.parse`.
- Exports: `core.js` api still exports `gemGroups/gemBreakdown/gemHost/searchAllRares/skipAllRares`
  (L489/492). `itemGranted` stays intentionally private — and now nothing external calls it, so no
  `undefined`-function break exists.
- Serve: spot-boot returned HTTP 200 for `/`, `/classic`, `/v/binder`, `/v/stash`, `/v/abacus`,
  `/assets/core.js`, `/assets/sample.js`; server force-killed; port 8927 confirmed closed.

---

## Adversarial hunts that came back CLEAN
- Old `inventoryId`/`SkillSlot` granted heuristic **live** anywhere: none (comments only).
- Any skin still calling un-exported `bpc.itemGranted`: none.
- Autoscan wired to `skipAllRares`: none.
- Picker id drift from `#pSearchAll`/`#pSkipAll`: none (binder realigned).
- Flask belt hardcoding <5 or life/mana classification: none.
- Grouping dropping host-less gem rows: none.
- New parse/export break introduced by the fixes: none.
