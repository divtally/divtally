# Dead shared JS/CSS — cleanup pass (D-0008 step 1)

Scope: the **shared** front-end only — `bpc/ui/assets/core.js`, the classic `PAGE` embedded in
`bpc/web.py`, and `bpc/ui/assets/sample.js`. Alternate skins were NOT deep-cleaned (D-0007); only
residue seen in passing is noted. Read-only reference: `bpc/engine.py`, `bpc/pricing.py`,
`bpc/web.py::_result_dict`/`_run_job`, `docs/research/contract.md`.

Consumers grepped for every finding: **all 12** `bpc/ui/*.html` (stash + 9 alternates + `_exttest`
+ `_reference`) **and** the classic `PAGE` in `web.py`. The classic PAGE does **not** load core.js
(`grep bpc\. web.py` → none), so core.js consumers = the 12 html files only.

---

## (a) core.js

### A1. `tierEx` — DEAD function (defined + exported, zero call sites) — safe delete
- Defined line 88: `function tierEx(p){ return (p&&p.chaos)? p.chaos[state.tier] : null; }`
- Exported line 487 (`tierEx: tierEx`).
- Evidence: `bpc.tierEx` across all `ui/*.html` + `web.py` = **0**. Within core.js the token
  `tierEx` occurs exactly **3×** = definition + export-key + export-value → **never invoked**
  anywhere (internal or external). Skins compute the per-tier value inline from `p.chaos[tier]`.
- Risk: **none**. Remove the function (line 88) and its export.

### A2. `TIER_ORDER` — DEAD constant (defined + exported, never read) — safe delete
- Defined line 39: `var TIER_ORDER = ["min","median","high"];`; exported line 495.
- Evidence: token `TIER_ORDER` occurs exactly **3×** in core.js = def + export-key + export-value;
  `bpc.TIER_ORDER` across consumers = **0**. (Its sibling `TIER_LABEL` *is* read internally by
  `loadPrefs`/`setControl`; `TIER_ORDER` has no reader at all.)
- Risk: **none**. Remove the const and its export.

### A3. Redundant exports — plumbing never called as `bpc.<name>` (function stays; drop the api key)
Each function below is **live internally** but its `bpc.<name>` export is referenced by **no**
skin/classic/_exttest (aggregate `bpc.X` grep across all 12 html = 0 for each). Trimming these
shrinks the public engine surface for launch; the code itself must NOT be deleted.

| export | internal caller(s) | note |
|---|---|---|
| `start` | startUrl, startCache, rerun, researchAll | core primitive; skins use startUrl/startCache |
| `rerun` | setControl | auto-invoked on control change |
| `loadPrefs` | init | init already calls it |
| `presentNext` | ingest, submitRare, openRare | internal advance |
| `defaultRarePayload` | searchAllRares | internal helper |
| `gemHost` | gemGroups | skins get host info via gemGroups() |
| `off` | the unsubscribe closure returned by `on()` | `bpc.off` never called directly |
| `GROUPS` (const) | itemsByGroup | skins use itemsByGroup() output |
| `TIER_LABEL` (const) | loadPrefs, setControl | internal validation table |

- Risk: **low**. Safe (no external caller), low value. Recommend dropping these api-object keys
  only if minimizing the public surface for the public build; otherwise harmless to keep.

### A4. Documented-but-unused public exports — KEEP (reported for completeness)
`bpc.openRare`, `bpc.loadMock`, `bpc.refreshRecent`, `bpc.refreshLeagues` are exported and
documented in the header block, but **no current skin calls them** (0 external):
- every skin enters mock via `bpc.init({mock:true})` (confirmed in all 10 skins + `_reference`),
  never `bpc.loadMock`; `init()` calls `refreshRecent`/`refreshLeagues`; `reopenRare` is used
  instead of `openRare`.
- Risk: **medium — recommend KEEP.** These are intentional, documented API a future skin may use;
  removing them is a contract change, not dead-code removal.

### A5. Dead branches for removed engine fields — NONE found (clean)
Cross-checked core.js against the fields `web.py::_run_job`/`_result_dict` actually emit and the
PoE2→PoE1 removals in `contract.md` §2/§3. `grep -nE 'uncut|lineage|rune|currency|exalted|cut_total'
core.js` → **only comments**. Every field core.js reads (`p.chaos`, `p.method`, `p.note`,
`p.trade_url`, `p.total_chaos`, `p.gems[]`, `p.granted`, `p.host_*`, `it.*`, `meta.*`) is emitted.
The PoE2 gem-extra reads (`.uncut/.cut/.lineage/.sockets`) were already removed in the port
(D-0005). No action.

---

## (b) classic `PAGE` (embedded in `bpc/web.py`)

### B1. `.warn` — DEAD CSS selector — safe delete
- Defined line 678: `.warn{color:var(--amber);font-size:13px;margin-top:10px}`.
- Evidence: `grep 'warn' web.py` → **only line 678**. Body scan (lines 767–1311) = 0 hits; not
  built dynamically (no `'warn'` string anywhere). PoE2-parent residue (a warning row that PoE1
  classic never renders).
- Risk: **none**. Delete the rule.

### B2. `var(--bd)` — undefined custom property in the classic PAGE (port residue) — cosmetic bug
- Used at lines 644 (`.reaffix`), 647 (`.pobbox`), 650 (`.pobcopy`), 654 (`.pobtext`) — all as
  `border:1px solid var(--bd)`.
- But the classic PAGE `:root` (line 608–609) defines `--line`, **not** `--bd`. `--bd` is defined
  **only** in the separate `_GALLERY_TMPL` `:root` (line 113), which does not style this document.
- Effect: those four borders are "invalid at computed-value time" → fall back to `currentColor`
  instead of the intended dark line colour. Real (if subtle) styling residue from the PoE2 parent.
- Risk: **cosmetic**. Fix = replace `var(--bd)` → `var(--line)` (or add `--bd` to the PAGE `:root`).

### B3. Dead JS functions — NONE found (clean)
All 40 functions defined in the PAGE occur ≥2× in `web.py` (definition + ≥1 call site). Every one
is wired via a call, an `addEventListener`, or the delegated `click`/`change` dispatchers
(lines 1251–1279). No dead function. (`.low`/`.medium` flagged zero-literal-hit are **false
positives** — applied dynamically via `class="badge "+p.confidence`, confidence ∈ high/medium/low/none.)

---

## (c) sample.js

### C1. Gem priced-entry `kind` + `source` — fields NO consumer reads (stack-wide dead metadata)
- In sample.js the gem priced entries carry `kind:"skill"` and `source:"poe.ninja"`
  (lines 173, 181, 185, 189, 194). These are not sample-only: the real engine emits them —
  `pricing.py` builds `r.extra = {"kind":"skill", ..., "source":"poe.ninja", ...}` at lines
  826–827 and 881–882, merged into the priced entry by `web.py::_result_dict` (line 163–164).
- Evidence: `grep` for `p.kind`/`.kind`/`p.source`/`.source` as a **priced-entry read** across
  core.js + all 12 html + classic PAGE = **0** readers. (The `.kind` hits that exist are affix
  `a.kind==='stat'|'equip'`; the `.source` hits are the build-`state.source` object and postMessage
  `ev.source` — unrelated.)
- Risk: **low**. Truly unread across the whole stack. Cleanest fix is at the emit side (drop
  `kind`/`source` from the gem `extra` in `pricing.py` + the sample), shrinking every gem payload.
  Dropping from the sample alone would make it diverge from the live contract — do both or neither.

### C2. Gem `gems[].variant` — copied through but never surfaced — low
- sample.js gems[] carry `variant` (e.g. `"21/20c"`). core.js `gemBreakdown` reads `g.variant`
  (line 262) and re-emits it, but **no** skin/classic renders the breakdown's `.variant`
  (`grep '\.variant\b'` across core.js + html → only core.js:262, the pass-through).
- Risk: **low**. Value dead-ends in `gemBreakdown`'s output; core.js guards with `|| ""`. Cosmetic;
  safe to leave. Flag only if trimming the gem contract in C1.

### C3. Checked and ALIVE (not dead) — recorded so the search isn't re-run
- `it.sockets` (gem support-count): read by **stash.html:1047** (`sock=(it.sockets!=null?...)`).
- `p.sample_size`: read by **stash.html:1302** ("N samples").
- `p.total_found`: read by **stash.html:1168** (`<5` → `.fewresults`).
- `meta.source_url`, `meta.pob_code`, `meta.status`, top-level `searches`/`advanced`: all read
  (core.js ingest / skins / classic metaHead). None dead.

---

## Alternate-skin residue seen in passing (NOT a deep clean — D-0007)
None flagged. The only alternate-skin reads touched during grepping (`stash` gem/sockets/samples,
`waterfall.isPriced`, `abacus.state.source`) are all live. No obvious dead residue observed; the
alternate skins were not audited beyond incidental matches, per scope.

---

## Recommended action order (owner gates)
1. Delete `tierEx` (A1) + `TIER_ORDER` (A2) from core.js — zero risk.
2. Delete `.warn` (B1); replace `var(--bd)`→`var(--line)` ×4 (B2) in web.py — zero/cosmetic.
3. (Optional, launch surface) drop the A3 plumbing exports; KEEP A4.
4. (Optional, payload trim) drop gem `kind`/`source` from `pricing.py` extra **and** sample.js
   together (C1), and `variant` with it (C2).
