# Fix-minors pass — port notes

Written 2026-07-26. Fixes the four MINOR findings from `docs/verify/v1-tests.md`,
`docs/verify/v3-web.md`, and `docs/verify/v4-review.md`, and closes the six documented-
promise test-coverage gaps from `v1-tests.md`. All changes are verifiable **offline** against
the fixtures in `research/data/`; **no live pathofexile.com trade call** was made. Every claim
below is grounded in the code/fixtures; `[INFERRED]` marks anything not directly observed.

Verification: `python -c "import bpc.engine, bpc.cli, bpc.pricing, bpc.trade, bpc.poeninja,
bpc.pob, bpc.currency, bpc.report, bpc.statmap, bpc.web"` clean; `python tests.py` → **All
self-tests passed** (EXIT 0); web boot smoke on port 8901 (`GET /` 200, `/v/stash?mock` 200,
`/v/abacus?mock` 200), server killed, port freed.

---

## Fix 1 (v4 MINOR-1) — PoB import now populates sockets/links

**Problem:** `bpc/pob.py` consumed the `Sockets:` line as a skip-able header property, so every
PoB-imported item had `max_link=0`. `pricing.Pricer._links_filter` needs `max_link>=5` to pin a
5L/6L search, so a PoB-imported 6-link body armour / 2H weapon searched with **no links filter**
and underpriced vs the poe.ninja path (which derives links via `poeninja._sockets_info`).

**Change (`bpc/pob.py`):**
- New `_parse_sockets(spec)` mirrors `poeninja._sockets_info`'s four outputs
  `(sockets, max_link, total_sockets, socket_colours)`. Notation from `docs/research/pob1.md`
  §3.4 and the primary-source fixture `research/data/pob_sample.xml` (item 25 "Blunderbore",
  Astral Plate: `Sockets: W-G-R-W-G-G` = a single 6-linked group; item 20 `R-G-W` = a 3-link):
  linked sockets are joined by `-`, a **space separates unlinked groups**, `max_link` = size of
  the largest hyphen-run. Socket shape is `[{group, attr, sColour}]`.
  - `_SOCKET_ATTR` maps colour→GGG attribute letter (R→S, G→D, B→I, W→G, A→A). Cosmetic parity
    only — pricing keys on `max_link`, never `attr`. The colour→attr mapping is the standard GGG
    convention but **[INFERRED]** for the PoB path (PoB exports colour, not attr).
- `_parse_item_text` captures the `Sockets:` value in the body loop **before** the generic
  header-property skip, and returns the four socket fields.
- `parse()`'s equipment `Item(...)` now passes `sockets/max_link/total_sockets/socket_colours`
  (jewels/flasks have no `Sockets:` line → empty fields; gems are built on a separate path).

**Test:** a synthetic PoB 6-link Astral Plate is parsed and asserted `max_link==6`,
`total_sockets==6`, and — the load-bearing check — `Pricer._links_filter(pob_body) ==
Pricer._links_filter(ninja_body)` (both `{"socket_filters":{"filters":{"links":{"min":6}}}}`),
i.e. **identical links filter across both input paths**. Plus an unlinked-groups case
(`"R-G B W"` → `max_link=2`, `total=4`) proving space-vs-dash semantics.

## Fix 2 (v4 MINOR-2) — economy league normalised like the trade league

**Problem:** `engine.prepare()` / `prepare_from_cache()` built `PoeNinjaEconomy(meta.league)` with
the **raw** build league. For an SSF build `meta.league` is e.g. `"SSF Allflame"` / `"HC SSF
Allflame"`; poe.ninja publishes no economy for SSF leagues, so gem prices and currency rates
silently degraded even though the trade *search* was correctly mapped to the tradeable parent.

**Change (`bpc/engine.py`):** all three `PoeNinjaEconomy(meta.league)` sites now use
`PoeNinjaEconomy(trade_league)` — the already-resolved league from `resolve_trade_league`
(`_norm_league` strips the non-tradeable `ssf` qualifier and maps to the live trade-league id).
`prepare_from_pob` already set `meta.league = trade_league`, so that site is a no-op change kept
for uniformity. (No `bpc/recover.py` exists in this port — the v4 reference was to the parent.)

**Test:** extends the existing HC/SSF cases near `tests.py` line 205 (not duplicated). With the
live league list stubbed offline, `resolve_trade_league("SSF Allflame") == "Allflame"`,
`resolve_trade_league("HC SSF Allflame") == "Hardcore Allflame"`, and the resulting
`PoeNinjaEconomy(...).league` carries **no `ssf`** and equals the tradeable parent.

## Fix 3 (v1 gap #4 guardrail) — budget-skipped rows now carry a trade link

**Problem:** when `SEARCH_BUDGET` was hit, `pricing.price_build` marked overflow items
`method="skipped"` with **no `trade_url`** — unlike every other unpriceable row. The
README/CLAUDE guardrail is "unpriceable = trade link + no number."

**Change (`bpc/pricing.py`):**
- New `_skip_trade_url(item)` builds the query the item's category **would** have run
  (unique: name+type+links; rare: base-scope + default affix/defence/links query; magic: base
  type) and returns a `?q=` URL via the existing local `_q_url` — **no search executed**.
- The skipped-row `PriceResult` now sets `trade_url=self._skip_trade_url(it)`.
- To avoid duplicating query construction (RULE 6), extracted two pure helpers reused by both
  live pricing and the skip path: `_rare_query(item, scope, stat_groups, equip_filters)`
  (assembles one rare scope query) and `_rare_default_filters(item)` (the default "require all
  searchable affixes + 85% defence totals" parts). `_price_rare_query` and `price_rare` were
  refactored onto them with **no behaviour change** (covered by the new tests 5b/5c/5d).

**README:** no contradiction found — the guardrail prose (README "How it works", lines ~181-182)
only ever promised unpriceable→link+no-number; this fix makes it universally true (including
budget-skipped rows), so README needed no edit (RULE 8 verified, not just assumed).

**Test:** a forced-budget `price_build([unique])` yields `method=="skipped"`,
`confidence=="none"`, no numeric tier, and a `trade_url` starting
`https://www.pathofexile.com/trade/search/`; a skipped **rare** likewise gets a link built from
its default query with no search run.

## Fix 4 (v3 finding 1 / v4 MINOR-3) — dead PoE2 `.rune`/`.currency` CSS removed

The engine emits categories `{unique,rare,magic,gem,normal}` and groups
`{equipment,flask,jewel,gem}`; skins build their rarity/group classes from those closed sets
(verified: abacus `it.category`→`r-*`, console `rarClass()`, foundry `mtag ${it.category}`,
manifest `rt=(it.rarity||it.category)`, stash `hc='h-'+it.category` and mods only pass
`imp`/`exp`). So the following never match a rendered element and were removed — exactly the
selectors/vars the verify docs enumerate, nothing else (no layout/theme touched):

| File:line | Removed |
|---|---|
| `abacus.html:79` | `.r-currency`, `.r-rune` |
| `console.html:178` | `.rar-rune` |
| `foundry.html:162` | `.mtag.rune` |
| `manifest.html:17` | `--rune` custom property |
| `manifest.html:235` | `.rtag.rune`, `.rtag.currency` |
| `stash.html:508` | `.tt-head.h-rune` (kept `.h-currency`, per the verify docs' list) |
| `stash.html:532` | `.tt-mod.rune` |
| `waterfall.html:15` | `--g-rune` custom property |

Kept live (still referenced by real selectors): the `--currency` var (abacus `.lsline .b` /
`.picker .pseudorow`; stash `.slot.r-currency` / `.tt-head.h-currency`). **Considered and kept:**
`manifest.html` "EXALT AIR" — decorative airline theme flavour; Exalted is a real PoE1 currency;
not a base-unit/PoE2 reference (v3 finding 2). Out of scope and untouched: `stash.html:290-291`
`.slot.r-currency`, `binder.html` `--r-currency` (neither file/line was in the task list), and the
unreachable `if(c==='currency')` JS branch in `abacus.html:240` (a JS branch, not a CSS
selector/var; leaving it has no visual effect since no currency item ever appears in gear).

## Fix 5 (v1 gaps #1-#6) — six documented-promise coverage tests

All offline, appended to `tests.py`:
- **(a) `--status` mapping:** a real `Pricer` (with `_load_types` stubbed) built for each of the 5
  documented statuses maps to `{"option": <status>}`; bogus/empty fall back to `online`.
- **(b) rare default requires ALL searchable affixes:** `_rare_default_filters` on a 3-mod rare
  (2 mapped, 1 unmapped) → one `and` group with exactly the 2 mapped ids; `n_unsearchable==1`.
- **(c) `armour_filters` from `Item.defences`:** `{ar:1000, es:200}` → `{ar:{min:850},
  es:{min:170}}` (85%), embedded under `filters.armour_filters` by `_rare_query`.
- **(d) no-match guardrail:** a search returning 0 → `confidence=="none"`, tier min/median `None`,
  `trade_url` still present.
- **(e) `to_chaos` non-chaos multiply:** divine (2→205) and mirror (3→50361) via a stubbed
  economy; `_lookup` sources divine/mirror from the economy and returns `None` for an unknown
  currency.
- **(f) version-unique auto-detection:** `_variant_affixes` flags a build affix present in `<50%`
  of stubbed listings as version-specific (mappable), treats a widely-shared affix as a fixed
  roll (not flagged), and disables detection below 4 listings. (v1 called this "harder to test
  offline"; it is in fact testable by stubbing the listing pattern-distributions directly, so the
  full slice — not a reduced one — is covered.)
