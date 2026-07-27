# F1 — Adversarial cross-skin consistency review of D-0006 (flasks / gem host-grouping + GRANTED / Autoscan)

**Spec of record:** D-0006 (`docs/00-decision-log.md`) + the UI implementation spec `docs/feedback1-spec.md`.
**Scope reviewed:** all 10 gallery skins (`bpc/ui/*.html`), the classic UI (`PAGE` in `bpc/web.py`),
and the shared `bpc/ui/assets/core.js` + `sample.js`. Read-only; only this file was written.
**Method:** static read of every skin's flask / gem / picker code; broad greps for the old
granted source, life/mana flask residue, and the autoscan wiring; `bpc.*` call-graph diffed against
core.js's exported `api`; offline JS parse of every inline `<script>` via `node`'s `vm.Script`
(parse without execute, no temp files); `node --check` on core.js/sample.js; `ast.parse` on web.py;
and a live spot-boot `python -m bpc.web --no-browser --port 8925` (all pages returned HTTP 200, then
the server was killed). **No pathofexile.com trade search/fetch/exchange endpoints were called.**

## VERDICT: **FAIL** — 1 blocker, 1 major, 1 minor.

The **skins themselves are almost uniformly correct** for all four D-0006 asks. The blocker lives in the
**producer** (`web.py`), not in a skin: the required §B.1 engine-value passthrough was never applied, so
on the **live backend path every gem is tagged GRANTED and defaults out of the total** — the exact
owner-reported bug this round exists to fix. It is **masked in mock/demo mode** (sample.js carries correct
flags), which is why a page spot-boot alone will not surface it. One skin (binder) also calls a core.js
helper that isn't exported, throwing and blanking its gem section.

---

## Findings

| # | Sev | File:line | One-line |
|---|-----|-----------|----------|
| 1 | **BLOCKER** | `bpc/web.py:314-315` | Old `inventoryId`/`SkillSlot` granted heuristic still live; §B.1 fix (`row["granted"] = bool(it.granted)`) never applied → every gem GRANTED + excluded from totals on the live path (all 10 skins + classic). |
| 2 | **MAJOR** | `bpc/ui/binder.html:853` | Calls `bpc.itemGranted(k)`, which core.js does **not** export → `TypeError` in `gemRowHTML`, run for every gem row → binder's whole gem section throws/blanks on any build with gems (mock and live). |
| 3 | **MINOR** | `bpc/ui/binder.html:1103,1128,1148-1149` | Picker bulk buttons renamed to `#autoscanBtn`/`#skipAllBtn` instead of the spec-mandated `#pSearchAll`/`#pSkipAll` (§E.1 "do NOT rename these"). Functional, but diverges from the other 9 skins + classic and defeats the §E.4 grep-to-find-them-all maintenance contract. |

---

### Finding 1 — BLOCKER — `web.py` never got the §B.1 granted fix (root-cause bug still present on the live path)

`docs/feedback1-spec.md` §B.1 is explicit that this is **the whole fix for the tag** and the one required
`web.py` change:

```python
# was (PoE2-era heuristic — WRONG for PoE1):
_inv = str((it.raw or {}).get("inventoryId") or "")
row["granted"] = not _inv.startswith("SkillSlot")
# becomes:
row["granted"] = bool(it.granted)
```

`bpc/web.py:314-315` (inside `_run_job`, the `if it.category == CAT_GEM:` skeleton block) **still runs the
"was" version verbatim**, and nothing overrides `row["granted"]` afterward.

**Why it is wrong (deterministic, no network needed):** in PoE1 the character's `skills[]` gems have
`itemData.inventoryId == None`, so `it.raw.get("inventoryId")` is falsy → `_inv = ""` →
`not "".startswith("SkillSlot")` → **`True` for every gem**. (Verified the boolean directly:
`not str(None or "").startswith("SkillSlot") == True`.)

**Two independent receipts that the engine already does this correctly and the heuristic misfires:**
- `bpc/models.py:61` defines `Item.granted: bool`; `bpc/poeninja.py:566` sets
  `active.granted = _gem_is_granted(...)` from the character JSON (`itemProvidedGems`/`isBuiltInSupport`).
- `bpc/poeninja.py:497-500` documents the exact bug: *"the granted flag was NOT computed here at all — the
  web [heuristic] … gems, so `not "".startswith("SkillSlot")` flagged EVERY gem granted. The engine now owns
  this decision … the UI must read `it.granted`."* The producer ignores that engine value.

**Blast radius (all consumers, because they all read `row["granted"]` = `it.granted`):**
- Every gem row renders the **GRANTED badge** (the owner's original screenshot complaint), in all 10 skins
  and the classic UI.
- `core.js:344` defaults include-state `state.enabled[k] = !itemGranted(k)` → every gem defaults **OFF**, and
  `core.js:185` keeps them off on "enable all". So the **default total silently excludes all gem costs** —
  and the spec (D-0006 / §D) stresses gems (Awakened / Empower / Enlighten) are often the largest line. The
  headline total is materially understated until the user manually re-checks every gem.

**Why the spot-boot did not catch it:** the mock path (`?mock` → `bpc.loadMock` → `sample.js`) bypasses
`_run_job` entirely and supplies correct `granted` flags (only "Herald of Agony" granted). The bug only
manifests against the real backend.

**Fix:** apply the one-line §B.1 change at `web.py:315`. (Out of this reviewer's writable scope —
`web.py` is another agent's file — but it is the required deliverable of this round and is currently unshipped.)

---

### Finding 2 — MAJOR — binder calls the un-exported `bpc.itemGranted` → gem section throws

`core.js` defines `itemGranted(k)` as a **private** helper (`core.js:125`) and uses it internally
(`core.js:344`), but the exported `api` object (`core.js:484-496`) **omits it** — confirmed by grep
(`itemGranted:` appears nowhere in the export). Therefore `window.bpc.itemGranted` is `undefined`.

`bpc/ui/binder.html:853`:
```js
const granted=bpc.itemGranted(k);   // §B: row-level GRANTED tag from the corrected field ONLY
```
`gemRowHTML(it)` is invoked for **every** gem row (`binder.html:841`, inside `renderGems`'s
`g.items.forEach`). The first gem row throws `TypeError: bpc.itemGranted is not a function` **before**
`renderGems` assigns `$('#grid').innerHTML` (line 844), so binder's entire gem page fails to render. This
fires on any build that has gems — **including the mock/demo**, so it is a guaranteed, not edge-case, break.

Binder is the **only** skin affected: it is the sole `bpc.itemGranted` caller (all 9 other skins read
`!!it.granted` directly; classic reads `!!it.granted` at `web.py:994`).

**Fix:** match the other skins — `const granted = !!it.granted;` — or use the already-fetched breakdown
(`bd = bpc.gemBreakdown(k)` at line 850 → `bd.granted`). Alternatively, export `itemGranted` from core.js,
but the local read is simpler and consistent with the other 9 skins.

---

### Finding 3 — MINOR — binder renamed the picker bulk-button ids

Spec §E.1: *"Keep the ids `#pSearchAll` and `#pSkipAll` … do NOT rename these,"* and §E.4 tells maintainers to
*"Grep each skin for `pSearchAll` / `pSkipAll` and fix them all."* Binder uses `#autoscanBtn`
(`binder.html:1103`) and `#skipAllBtn` (`binder.html:1128`), wiring them itself at `binder.html:1148-1149`.
It is **functionally correct** (self-consistent, correct actions — see Autoscan section), but it silently
opts out of the project-wide id convention and would be missed by the §E.4 grep. Low risk, easy to align.

---

## Per-check results

### (1) Flask belt — PASS (all 10 skins + classic)
Every skin renders a **≥5-slot generic belt in flask order, overflow preserved, no life/mana
classification.** No skin hardcodes 3 slots; no `lifeFlask`/`manaFlask`/`isLife`/`classifyFlask`/standalone
`Life`/`Mana` identifiers exist in any skin (grep clean — "doll" in stash is the *equipment* paper-doll).

| Skin | Fn / site | Slot logic | Overflow |
|------|-----------|------------|----------|
| classic (`web.py:938`) | `beltHTML` | `Math.max(5, rows.length)` | grows |
| stash `:980` | belt = doll bottom row | 5 grid cells, flask order | `flasks.slice(5)` → stash "Flasks" section |
| abacus `:492` | `renderFlaskBelt` | `Math.max(5, n)` | `i>=5` marked `over` |
| atelier `:700` | `renderFlaskBelt` | `Math.max(5, fl.length)` | grows |
| facts `:633` | `flaskBeltHTML` | `Math.max(SLOTS=5, …)` | `i>=SLOTS` `overflow` |
| foundry `:600` | `paintFlaskBelt` | `Math.max(SLOTS=5, …)` | `i>=SLOTS` `over` |
| ledger `:641` | `flaskBeltHTML` | `Math.max(5, flasks.length)` | grows |
| manifest `:759` | `flaskBeltHTML` | `Math.max(N=5, items.length)` | grows |
| console `:728` | `flaskBeltHTML` | `Math.max(SLOTS=5, …)` | grows |
| waterfall `:615` | `beltHTML` | renders all items, pads up to 5 | all items rendered first |
| binder `:809` | `renderBelt` | `Math.max(SLOTS=5, …)` | `i>=SLOTS` `over` |

(stash keeps legacy CSS grid-area *names* `fl1/ch1/ch2/ch3/fl2`, but they are just positions filled
left-to-right in flask order — no life/mana semantics. Not a finding.)

### (2) Gems grouped by host + GRANTED — grouping PASS; GRANTED consumer PASS except binder; **producer BLOCKED (Finding 1)**
- **Grouping / no-drop:** all 10 skins group via `bpc.gemGroups()` and nest supports via
  `bpc.gemBreakdown()` (index-aligned; classic rolls its own equivalent at `web.py:960`). `gemGroups()`
  buckets host-less gems (`host_inventory_id === ""`, e.g. PoB imports) under a `"Gems"` header and never
  drops; every skin iterates **all** groups **and all** `g.items` (verified manifest `:786-797`,
  facts `:683-695`, binder `:833-843`, classic `:971-988`), so multi-active hosts and the fallback bucket all
  render. **No "dropped rows" defect found.**
- **GRANTED wired to the corrected field only:** zero `inventoryId`/`SkillSlot` references in any skin (grep
  clean). 9 skins read `!!it.granted` directly (waterfall:667, stash:1055, manifest:740, console:746,
  ledger:701, foundry:651, atelier:757, facts:605, abacus:425) and classic reads it at web.py:994 — **all
  correct sources.** binder intends the same but via the broken `bpc.itemGranted` (Finding 2).
- **Producer:** the value those correct consumers receive is wrong on the live path (Finding 1).

### (3) Autoscan — PASS (action wiring correct everywhere; no "wrong action wired")
- **Autoscan = price-all:** every skin's glowing button (`#pSearchAll`, or binder's `#autoscanBtn`) is wired
  to `bpc.searchAllRares()` — the former "Search all N (default)". **No skin wired Autoscan to
  `skipAllRares` (the trap that would skip pricing).** Verified: waterfall 1123, console 976, atelier 1066,
  stash 1543/1781/1824, facts 983, ledger 966, manifest 1078, foundry 933, abacus 686, binder 1148,
  classic web.py:1235.
- **skip-all = skip, non-glowing, still present:** every skin keeps a small non-glowing "skip all (don't
  price)" → `bpc.skipAllRares()` (web.py 1236, and the `#pSkipAll`/`#skipAllBtn` wirings above +1). Skip-all
  buttons carry muted classes (`pa-skip small` / `skipall` / `pskipall` / `skipall-btn` / `pa-skip-small`),
  never the glow class.
- **Top placement + glow CSS:** each skin defines a `.autoscan*` rule with the `autoscanPulse` keyframes and
  a `@media (prefers-reduced-motion: reduce)` off-switch, accent-adapted per skin, and places the Autoscan
  markup **above** the per-item buttons.
- **Every picker copy:** stash has **three** picker renderers (`pkRender` ~1486, `pkRenderSurvey` ~1747,
  `pkRenderClassic` ~1790) — **all three** carry an Autoscan at top + a skip-all below + matching wiring. No
  other skin has a second full picker renderer missing the button (single-unique "edit affixes" pickers
  correctly omit it via the `remain>1` guard). No leftover old bottom "Search all N (default)" buttons remain
  (stash:746 "Search all again" is the separate re-run-all-searches control; web.py:1144 is only a comment).

### (4) Layout / syntax sanity + undefined helpers — PASS except Finding 2
- **Parse:** every skin's inline `<script>` parses clean (node `vm.Script`, parse-only); `core.js`,
  `sample.js` pass `node --check`; `web.py` passes `ast.parse`.
- **Serve:** live boot returned HTTP 200 for `/`, `/classic`, `/v/binder`, `/v/stash`, `/assets/core.js`.
- **Undefined helpers:** all `bpc.*` calls across the 10 skins resolve to real `api` exports **except**
  `bpc.itemGranted` in binder (Finding 2). No skin reads a `sample.js` field that doesn't exist (gem skeleton
  omits `host_base`, but `gemHost()` falls back priced→skeleton→`""`, so no break).

---

## Adversarial hunts that came back CLEAN (ruled out)
- **"Autoscan wired to `skipAllRares`" (would skip instead of price):** not present in any skin — all
  Autoscans call `searchAllRares`.
- **"Grouping drops host-less gem rows":** not present — core `gemGroups()` buckets them under "Gems"; every
  skin iterates all groups/items.
- **"Flask belt hardcodes 3 slots":** not present — every belt is `Math.max(5, …)`.
- **"Skin reads a sample.js field that doesn't exist":** not found (the only missing-reference is the
  core.js export in Finding 2, not a data field).
- **Life/mana classification residue:** none in any skin.
