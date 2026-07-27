# Dead-Python hunt (D-0008 cleanup, step 1)

Scope: `bpc/*.py` (incl. `web.py` server side) + root-level `.py` (`run.py`, `app.py`,
`recover.py`, `tests.py`). `research/` probe scripts and `docs/` are OUT of scope (protected
project record; CLAUDE.md). Read-only cross-checks against `bpc/ui/*` (all 10 skins + `_reference` +
`_exttest` + `assets/core.js` + `assets/sample.js`) and the classic UI (`web.py::PAGE`).

Method: read every module end-to-end, built a def/class inventory, then grepped the whole repo
(`*.py` + `bpc/ui/**`) for each symbol's callers, including dynamic paths (`getattr`/`hasattr`,
string-dispatch, endpoint strings). Verdicts below cite the exact searches.

---

## A. Endpoint reachability (server handlers vs. what the front-end requests) — NO dead endpoints

`web.py` serves exactly six `/api/*` routes. Grep `\b/api/[a-z]+\b` over `bpc/ui/**` +
the classic `PAGE` JS shows every one has a live consumer:

| handler (`web.py`) | consumer(s) | verdict |
|---|---|---|
| `POST /api/price` | `core.js:31`, classic `PAGE` | live |
| `GET  /api/job`   | `core.js:31`, classic `PAGE` | live |
| `POST /api/rare`  | `core.js:31`, classic `PAGE` | live |
| `GET  /api/cache` | `core.js:31`, classic `PAGE` | live |
| `GET  /api/leagues` | `core.js:31`, classic `PAGE` | live |
| `GET  /api/stats` | `stash.html:1564` (picker "add filter" feature) | live |

Note: the 9 alternate skins + `_reference.html` drive `core.js` for all fetches (D-0002); only
`stash.html` calls `/api/stats` directly. Its sole consumer is stash, but the handler is therefore
NOT dead. No handler is orphaned.

---

## B. Confirmed dead — functions / methods / classes never called (HIGH confidence)

Each verified by grepping the symbol across the whole repo `*.py` AND `bpc/ui/**`, and confirming
no dynamic reference (`getattr`/`hasattr` targets enumerated — all resolve to real fields:
`cache_key`, `source_url`, `pob_export`, `max_link`, `granted`, `host_*`, `tier.<attr>`,
`sys.frozen`).

1. **`bpc/report.py::render_html`** (line 144) — server-side HTML-fragment renderer for the results
   panel. The web UI renders results **client-side** (core.js / skins build the DOM from
   `JOB.priced` JSON produced by `web._result_dict` / `report.build_payload`); nothing calls
   `render_html`. Grep `render_html` over `*.py` → only the def (report.py:144); over `bpc/ui/**` →
   none. **Coupled cleanup:** `render_html` is the ONLY user of `import html as _html` (report.py:2,
   used at report.py:147) — removing the function makes that import dead too. B-001 (public launch,
   backlog.md) does NOT reintroduce a server-HTML path (it extracts a JSON-only `api/build.py`), so
   this is not a "keep for later" case.

2. **`bpc/util.py::numbers`** (line 55) — returns all numbers in a mod line. No caller and no test.
   Grep `\bnumbers\b` over the repo → only the def, a docstring (util.py:28), and prose in
   CLAUDE.md / decision-log / verify docs; the single-value need is served by `first_number`
   (util.py:49, which IS live via pricing).

3. **`bpc/statmap.py::StatMapper.top_filters`** (line 128) — the rare pricer builds its stat filters
   via `Pricer.affix_options` / `_rare_default_filters`, not this. Grep `top_filters` over the repo →
   only the def. Its internal calls to `match_line` / `_score` do NOT keep it or them alive:
   `match_line` has a live caller (pricing.py:420, `_variant_affixes`) and `_score` is imported and
   used by pricing (`_affix_tier`), so both survive independently. This is a leaf dead method.

4. **`bpc/poeninja.py::PoeNinjaEconomy.chaos_by_name`** (line 246) — currency conversion resolves by
   id, not name: `currency.py:49,82` call `economy.chaos_by_id(...)`. Grep `chaos_by_name` over the
   repo → only the def. (Sibling `chaos_by_id` at line 243 is live — keep it.)

5. **`bpc/pricing.py::Pricer._trade_url`** (line 292) — builds a trade link from a server
   `query_id`. Every result URL is instead built by `_q_url` (the never-expiring `?q=` link,
   pricing.py:298), `_gem_search_url`, or `_skip_trade_url`. Grep `_trade_url` over `*.py` → the def
   plus the DISTINCT `_skip_trade_url` (line 887, which IS called at line 934). `self._trade_url(`
   → zero matches.

6. **`bpc/pricing.py::Pricer._listings_prices`** (line 321) — chaos-price extraction from a listings
   list. Superseded: `_search_listings` (lines 363–376) inlines the same `to_chaos` extraction
   (while also collecting mod patterns), and `_search_collect` reads `[l[0] for l in listings]`.
   Grep `_listings_prices` over the repo → only the def.

7. **`bpc/models.py::BuildEstimate`** (line 108) — dataclass (`meta` + `results`). Never
   instantiated. Grep `BuildEstimate` over the repo → only the class def (models.py:108) and a
   docstring mention (report.py:1). The pipeline passes `(meta, results, conv)` tuples around
   instead of ever wrapping them in this type.

---

## C. Confirmed dead — unused import / write-only field / PoE2-shaped residue (MEDIUM confidence)

8. **`bpc/pricing.py` line 22 — unused import `CAT_NORMAL`.** Imported in the
   `from .models import (CAT_GEM, CAT_MAGIC, CAT_NORMAL, CAT_RARE, CAT_UNIQUE, ...)` line but never
   referenced in the module (grep `CAT_NORMAL` in pricing.py → only the import line). The other four
   `CAT_*` names ARE used (price_build / affix_options / _skip_trade_url). Drop `CAT_NORMAL` from the
   import list.

9. **`bpc/models.py::Item.mods_explicit`** (field, line 33) — self-documented "best-effort; unused in
   pricing." Assigned once in `poeninja.py::_make_item` (line 428) from `d["mods"]["explicit"]`, then
   **never read** anywhere (grep `\.mods_explicit\b` over the repo → zero reads; it is not emitted in
   the web skeleton, not in `report.build_payload`, not asserted in tests). Removing it means editing
   both `models.py:33` and `poeninja.py:428`. Low functional risk (write-only).

10. **`bpc/web.py` — PoE2 batched-gem residue (a coupled cluster; remove together).** The parent
    (PoE2) priced gems as a single batched "Gems" task; PoE1 prices each gem GROUP individually via a
    per-item `("skill", i)` task (D-0003 / D-0006). Leftovers that PoE1 never exercises:
    - **`_price_task(pricer, kind, payload, items_by_idx, gems)`** (line 231) — the `gems` parameter
      is never referenced inside the function body (lines 231–250 use only `items_by_idx`/`payload`).
    - **`gems` local** (line 297, `gems = [it ... if it.category == CAT_GEM]`) — its only consumers
      are the dead param (passed at line 434) and the dead state below. Grep `\bgems\b` in web.py:
      def(231)/local(297)/state(386)/pass(434) only.
    - **`j["_items"]`** (line 385) and **`j["_gems"]`** (line 386) — written to job state but never
      read (grep `_items`/`_gems` in web.py → only those writes). `_snapshot` strips `_`-prefixed
      keys; the worker loop uses the closure locals `items_by_idx`/`gems`; `/api/rare` reads only
      `_q`/`rares`/`priced`.
    - **`kind == "gems"` branches** (lines 425 and 427) — no `("gems", …)` task is ever enqueued
      (the only `q.put` kinds are `unique`/`rare_default`/`skill`/`magic`/`none`/`rare_custom`), and
      `_price_task` has no `"gems"` handler (it would fall to the `else` → "normal item"). Both
      branches are unreachable.

---

## D. Low confidence — flagged for owner judgement, do NOT auto-remove

11. **`bpc/models.py::Item.sockets`** (raw socket list, line 43) — populated by both loaders
    (`poeninja._sockets_info`, `pob._parse_sockets`) but the RAW list is never read in Python: only
    `max_link` drives pricing (`pricing._links_filter`, via `getattr`). **Risk / reason to keep:**
    it is a documented engine→UI contract field (`docs/research/contract.md` §126) and the sibling of
    the load-bearing `max_link` produced in the same tuple; removing it diverges from D-0002 ("keep
    the parent architecture verbatim") and could break a skin that reads `it.sockets`. Cheap to keep.
    Owner call.

    NB — the neighbouring `Item.total_sockets` (line 45) and `Item.socket_colours` (line 46) look
    similar but are **NOT dead**: `tests.py` asserts them (lines 373, 403, 404). Do not remove them.

---

## E. Doc drift caused by the removals above (fix in the same cutover — RULE 6)

12. **`bpc/report.py` line 1 docstring** — "Render a **BuildEstimate** as a readable terminal table,
    JSON, or **HTML**." Both referents die under §B: `BuildEstimate` (never used) and the HTML
    renderer (`render_html`). Update the docstring to "Render pricing results as a terminal table or
    JSON" when those are removed, else it advertises capabilities the module no longer has.

---

## F. Notable non-findings (checked, deliberately NOT flagged)

- **`Pricer._econ`** (pricing.py:247) — trivial `return self.economy` wrapper, but it HAS a caller
  (price_skill, line 807). Live; a simplification target at most, not dead code (out of scope).
- **`exchange` / trade fallback path** (`trade.py:227`, `currency._lookup:54`) — rarely hit (economy
  is the primary source, D-0003) but reachable when poe.ninja lacks a currency. Live.
- **`scourgeMods` / `crucibleMods` / `veiledMods`** in `poeninja._EXPLICIT_MOD_KEYS` (line 391) and
  the `scource`/`crucible`/`veiled` groups in `statmap._build` — these are real PoE1 mod groups
  (verified against `/api/trade/data/stats`), not PoE2 residue. Live.
- **All module-level constants have readers** (checked each): `_DEFAULT_RULES`, `_PRIORITY`,
  `_LOCAL_DEFENCE`, `_INVENTORY_CATEGORY`, `_DEF_LABEL`, `_GROUP_TYPES`, `_WEIGHT_TYPES`,
  `_SLOT_MAP`, `_PROP_PREFIXES`, `_INVENTORY_NAMES`, `_EXPLICIT_MOD_KEYS`, `FRAME_RARITY`, `PAGE`,
  `_GALLERY_TMPL`, `_METHOD_OK`, etc. None dead.
- **Unused imports:** only `CAT_NORMAL` in pricing.py (§C-8). `report.py`'s `import html as _html`
  becomes dead only AFTER `render_html` is removed (§B-1) — it is coupled, not independently dead.
- **`tests.py`** helpers (`check`, `approx`, `_fl_entry`, `_flaskI`) and fake clients are all
  exercised within the suite (e.g. `_fl_entry`/`_flaskI` → 12 refs). No dead test helpers found.
- **`run.py` / `app.py` / `recover.py`** — all live entry points (launcher, packaged-exe entry,
  cache-recovery tool). No dead code inside them.
