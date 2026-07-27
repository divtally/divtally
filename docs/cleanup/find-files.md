# Cleanup pass 1 - dead files + doc drift (D-0008 step 1)

Pre-public dead-code cleanup, scope set by D-0008: root files + `bpc/*.py` + `bpc/ui/assets/core.js`.
The 9 alternate skins + classic + stash + `_exttest.html` stay (D-0007); flag only obvious residue in
them. NOT in scope for flagging (per the standing rules): `research/`, `docs/`, `cache/`, `.gitignore`,
`CLAUDE.md`, and anything the PUBLIC build needs (`extension/`, `_exttest.html`).

Method: read every root file + every `bpc/` module; built the full `import` graph for `bpc/`; grepped
(project-scoped only - never the home dir) for every questionable symbol's references; verified README
claims against the actual code (`cli.py` args, `web.py` routes + `main()`, `core.js` exports).

---

## A. DEAD FILES

### 1. `bpc/ui/_reference.html` - hidden dev worked-example; nothing references it at runtime  (OWNER'S CALL)
- **What it is:** its own header says it: *"Hidden reference view (filename starts with `_` so it's not
  in the gallery). It exercises EVERY part of bpc core.js and is the worked example for builders."* It is
  a bare, undesigned page that loads `/assets/sample.js` + `/assets/core.js` and wires the full core API.
- **Who uses it:** nobody, at runtime. `web.py._list_versions()` skips every `_`-prefixed file
  (`fn.startswith("_")`, web.py:62), so it never appears in `/gallery`. It is reachable ONLY by manually
  typing `/v/_reference` (the `/v/<id>` route regex allows `_`). No skin, no README line, no launcher, and
  nothing in the B-001 public-launch plan links to it. Every other reference is in `docs/` records
  (port-notes, verify) - history, not a live link.
- **Contrast with `_exttest.html`:** that one is PROTECTED (extension test harness the bridge test needs).
  `_reference.html` is NOT protected and is not needed for the public launch.
- **Risk / recommendation:** safe to delete - removing it changes no shipped surface. The only value it
  holds is documentary: it's the canonical minimal example of the `core.js` API, which lightly supports the
  README's "drop a `*.html` into `bpc/ui/`" extensibility pitch (README:58-60). So this is an owner's call:
  **remove it** for a clean public tree, OR **keep it** as the deliberate builder example (in which case it
  should stay in sync with `core.js`). Nothing else depends on the decision.

**No other dead files found.** Every root file and every `bpc/*.py` module is live (see B).

---

## B. FILES CHECKED -> LIVE (not dead)

**Root**
- `app.py` - KEEP. The packaged one-file `.exe` entry (`from bpc.web import main; serve([])`). This is the
  B-001 **Rung-0** "local exe/zip" path, which D-0008 explicitly keeps -> not dead. See the FYI in D below
  about the missing `.spec`.
- `run.py` - live. Launched by BOTH `bpc.cmd` and `bpc-web.cmd` (`--web` branch).
- `recover.py` - live. Standalone cache-recovery CLI; imports `bpc.engine/poeninja/report/cache/pricing/
  trade`; referenced by README:92 (see the drift note in D - the "(see below)" pointer is broken, but the
  file itself is real and used).
- `bpc.cmd`, `bpc-web.cmd` - live launchers (README "Usage").
- `tests.py` - live test suite (`python tests.py`, cited across `docs/verify/` + D-0005/6).
- `requirements.txt` - accurate: the one runtime dep `requests` is imported by `poeninja.py`, `trade.py`,
  `engine.py`; `playwright` is correctly commented as probe-only.
- `README.md` - the doc; drift items in D.

**`bpc/` package - full import graph, every module reachable from an entry point**
- Entry points: `cli.py` (via `__main__.py` + `run.py`), `web.py` (via `run.py --web`, `app.py`,
  `python -m bpc.web`).
- `cli.py` -> engine, poeninja, report. `web.py` -> cache, engine, poeninja, report, util, models, trade.
- `engine.py` -> cache, poeninja, **pob**, pricing, models, trade. `pricing.py` -> cache, util, currency,
  models, statmap, trade. `poeninja.py` -> cache, util, models. `currency.py` -> cache, util, trade.
  `report.py` -> currency, models. `statmap.py` -> util, trade. `trade.py` -> cache. `pob.py` -> models.
- Leaves imported widely: `models.py`, `cache.py`, `util.py`. `__init__.py` (`__version__`) + `__main__.py`
  (`python -m bpc`) both used. **No orphan module.**

**`bpc/ui/`**
- `assets/core.js` - live; loaded by all 12 skins. Read end-to-end: every function is either exported on
  the `api` object or called internally (emitter, prefs, totals, gem grouping, rare flow, mock). No dead
  function; `searchAllRares`/`skipAllRares` back the D-0006 Autoscan/skip-all buttons.
- `assets/sample.js` - live; `?mock` demo payload, `<script src="/assets/sample.js">` in all 12 skins;
  `core.js.loadMock()` reads `window.BPC_SAMPLE`.
- `stash.html` (THE app, `/`), `_exttest.html` (protected), and the 9 skins + classic (embedded `PAGE`
  string in `web.py`, served at `/classic`) - all in-scope-to-keep; no obvious dead residue found in them.

**PoE2 / rune "residue" check:** the `poe2|trade2|rune|soul core|uncut|desecrated` hits in `bpc/` are all
RULE-6 *cutover comments* ("PoE2's CAT_RUNE is deleted", "the old PoE2-era heuristic ... Deleted here",
etc.) documenting what was removed - not live code. Nothing to remove.

---

## C. NOT FLAGGED (deliberately)
- `research/`, `docs/`, `cache/`, `.gitignore`, `CLAUDE.md` - out of scope by rule.
- `__pycache__/` (root + `bpc/`) - regenerable bytecode, already `.gitignore`d; harmless, not source.
- Three near-identical picker-render blocks inside `stash.html` (Autoscan button HTML repeated ~L1486 /
  L1747 / L1790) - a possible refactor smell, but stash is THE protected app and this is not dead code;
  left alone per scope.

---

## D. DOC DRIFT (RULE 8) - README statements that no longer match the code

### D1. `## Project layout` omits two real source modules  (README:225-237)  [HIGH confidence]
The `bpc/` layout block lists 11 modules (cli, web, engine, poeninja, trade, statmap, pricing, currency,
report, models, cache) but is **missing `pob.py` and `util.py`** - both real, imported source files:
- `pob.py` = Path-of-Building import parsing (imported by `engine.py`; D-0005 gave it the socket/links
  parsing). The README documents PoB-code input as a first-class feature (README:136-141, 169-176), so the
  module that implements it should be in the layout.
- `util.py` = rich-text/number/percentile helpers, imported by 6 modules (poeninja, pricing, currency,
  statmap, web, +).
- **Truth / fix:** add `pob.py` (Path of Building import parsing) and `util.py` (mod-text / stats helpers)
  to the layout block.

### D2. `recover.py` "(see below)" points to a section that doesn't exist  (README:92)  [MED confidence]
Line 92: *"The CLI equivalent is `recover.py` (see below)."* There is **no section below** describing
`recover.py` - the headings after this point are Command line, Options, How it works, Rate limiting,
Limitations, Project layout, none about recovery. Dangling cross-reference (likely ported from the parent
README which had the section).
- **Truth / fix:** either drop "(see below)", or add the short recover.py section it promises (usage:
  `python recover.py "<url>"` / `--account/--character` / `--links-only` - rebuilds a build from local
  cache when the poe.ninja profile is gone).

### D3. Advanced-affix-search section omits the D-0006 Autoscan / skip-all buttons  (README:99-106)  [MED-LOW]
The advanced-mode walkthrough describes only the per-rare buttons ("Search this item", "**Skip (don't
price)**") but not the D-0006 bulk controls that now sit at the TOP/bottom of the picker in every skin
(incl. stash + classic): a glowing **"Autoscan (N)"** that prices all remaining rares with default
all-affix searches (`core.js.searchAllRares`), and a small **"skip all (don't price)"**
(`core.js.skipAllRares`). Verified in `stash.html` (L1486/L1501) and the classic `PAGE`
(`button.autoscan`/`button.skipall` CSS in web.py).
- **Truth / fix:** add a sentence to the advanced section: a glowing "Autoscan" at the top of the picker
  prices every remaining rare automatically (default all-affix search), and "skip all" leaves the rest
  unpriced - both without leaving the flow.

**FYI (not drift, but relevant to D-0008 step 2 packaging):** `app.py` is present and correct, but the
parent's PyInstaller spec (`PoE2-Build-Price-Checker.spec`) was NOT ported - this repo has no `.spec`,
`build/`, or `dist/`. The Rung-0 exe build will need a PoE1 `.spec` regenerated when packaging the public
deliverables. Flagging so it isn't a surprise mid-launch.

**Verified accurate (no drift):** `--league/--status/--json/--fresh|--refresh/-q|--quiet/--version` all
exist in `cli.py` with the exact `--status` choices + mapping the README lists; web routes `/`, `/gallery`,
`/classic`, `/v/<id>`, `?mock` auto-discovery; `--port 8765` default + `--no-browser` in `web.py.main()`;
stash-as-face at `/` (D-0007); chaos-normalised + divine secondary; gem/currency-from-poe.ninja pricing.
