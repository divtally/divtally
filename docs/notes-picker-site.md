# Notes — the per-rare AFFIX PICKER on the public site (D-0015 feature, UI layer)

Working notes for the build round that wires the **per-rare affix picker** into the public stash
site (`public/site/index.html` + `assets/core.js`). The picker is the owner's most-wanted feature
(D-0015): the site never excludes an affix on its own — **every affix starts ticked; only the USER
subtracts or edits**. This round consumes the affix payload the API already prepares
(`docs/public-contract.md` §2.6, built in `docs/notes-picker-api.md`) and replicates the desktop
app's advanced flow (parent README "Advanced affix search" + "edit affixes" + "combine resistances"
sections = the UX spec).

Files I own for this task: `public/site/**` + this notes file. I did **not** touch `README.md`,
`docs/00-decision-log.md`, `public/api/**`, `bpc/**` (read-only reference).

---

## What shipped (all in `public/site/**`, additive — no regression to D-0012 / v1.1)

### `assets/core.js` — the client-side query builder (pure, node-testable) + two price paths
New exported surface (nothing else changed except a **one-line** override, below):
- **`buildRareQuery(rare, origQuery, picks)`** → the inner trade `query` object, built entirely
  client-side. `rare` = `state.rares[key]`; `origQuery` = the item's own `trade_query.query` (or its
  `scope_q`) — **the only source of scope** (`status`/`type`/`name`/`type_filters`) **and the 5/6-link
  `socket_filters`**; these are copied **verbatim, never invented**. `picks` =
  `{ usePseudo, affix:{i:{ticked,min,max}}, pseudo:{j:{ticked,min,max}} }`; omit it (or an entry) to
  use that affix's all-ticked default. Emits **one AND stat group**; per-filter `value.{min,max}`;
  `armour_filters` from ticked defence mins; unsearchable affixes are **never** emitted; when the
  pseudo toggle is on, resistance affixes are dropped and the pseudo `stat_id`s are added instead.
- **`rareDefaultPicks(rare)`** → the D-0015 default: **every searchable affix ticked** (equip too),
  min/max prefilled from `default_min`/`default_max`, pseudo rows ticked, `usePseudo` ON iff the item
  has any resistance pseudo total. `affixPrefill(a)` derives the prefill from `default_min`/`default_max`
  when present, else from the signed roll + `negated` (so it also works on older/mock payloads).
- **`rareTradeUrl(query, refUrl)`** → the browser `?q=` URL for a query, reusing the item's own
  trade host+league (so the URL and the extension run the **same** query). Pure string building —
  never calls pathofexile.com.
- **`queryLinks(q)`** / **`rareOf(key)`** — the read-only links-chip value; the rare's payload.
- **`priceRareCustom(key, query)`** / **`priceRaresCustom([{key,query}])`** — price refined rare(s)
  via the extension, reusing the tested **D-0012 chunked path + v1.1 scan chips + community-cache
  POST-back**. The one-line change that enables this: `priceRowsViaExtension` now honours an optional
  per-row `r.query` override (`var q = r.query || (tq && (tq.query||tq));`) — inert for the existing
  autoscan/single-item callers.
- **`setRareQuery(key, query, url)`** — the no-extension path: remembers the refined query+url on the
  row (its "open search" link now reflects the picker) while the row stays in manual mode.

### `index.html` — the picker UI (wires the **already-present, previously-unused** `.pick` CSS)
The stash skin already carried a full affix-picker stylesheet (`.pick` modal, `.afx` diamond
checkboxes, `.mm` min/max, `.afx.no` greyed, `.pseudo-switch`, `.pautoscan`, `.pbtns`, `.pbulk`) —
built but never driven. This round drives it:
- A remembered **"pick affixes"** checkbox in the "Rares to price" header (localStorage
  `bpc_pick_affixes`, **default OFF**), next to Autoscan / auto-scan-on-load.
- **When ON:** `maybeAutoStart` (extension auto-scan) is suppressed; unpriced rares **queue** and the
  picker presents them **one at a time** in the `.pick` modal (auto-opens once per build, then
  user-driven). Background pricing (gems/uniques by poe.ninja, community-cache read-through) keeps
  filling exactly as before — the picker only gates the *rare extension auto-scan*.
- Per rare: every affix listed with a checkbox (**all ticked**), editable min/max prefilled from the
  roll, **unsearchable lines greyed** with their reason, **defence totals** shown as editable min
  values, a read-only **"N-link required"** chip, and — when the item has resistances — a
  **"Combine resistances into a pseudo total"** toggle (**default ON**) that swaps the individual res
  rows for the pseudo total rows (and back). Edits survive a pseudo toggle.
- Buttons: **Search this item** (build the query from current ticks/mins → extension `priceRareCustom`
  if the bridge is active, else open the refined trade URL + keep the row manual) · **Skip (don't
  price)** · **← Back** · plus the desktop app's top-of-picker **⚡ Autoscan (N)** (extension only) and
  **skip all**.
- **Every rare row** gets an always-available **"edit affixes"** button (priced or not) that reopens
  that one rare's picker in single-edit mode; re-searching updates the row + totals in place, and
  extension refinements POST to the community cache like any extension result.

### Mock/stub fixtures (for the `?mock` and `?stub` demos)
- `assets/sample.js`: made **Rift Shroud (item 1)** a 6-link with a full roll-min `trade_query`
  (demos the links chip + defence total + pseudo fold on a *priced* rare via "edit affixes"), gave
  its rare payload the new-shape fields (`default_min`/`default_max`/`negated`/`group`/`prefer` +
  pseudo `folds`), and turned **Blazing Fettle (item 15)** into an **unpriced** cluster-jewel rare
  with two searchable enchants + two **unsearchable** notables + a `trade_query` — so the pick-mode
  **queue** presents it and the greyed-unsearchable rows show.
- `stub-build.json`: fixed items 1 & 2 `trade_query.stats` so all-ticked reproduces them.

---

## THE query-builder decision (fundamental — flagged for the owner / decision log; RULE 1/5)

**Semantics chosen: "roll-min", faithful to the desktop app's advanced picker.** A ticked normal
affix searches **`{id, value:{min: the roll}}`** ("an item at least this good"); a negated/"reduced"
roll searches `value:{max}`; a defence total searches `armour_filters:{key:{min: the roll}}` (100%).
This is exactly what `bpc/web.py` does (`affixRow` prefills the min with the roll; `submitRare` /
`price_rare_custom` emit `{min}`), and it is what the contract's `default_min` is for.

**Consequence (intended, matches the desktop app):** the picker's all-ticked default is
**stricter** than the API's *Autoscan* default. The public API builds each rare's `trade_query` with
**presence-only** stat filters (`{id}`, no min) + **85%** defence mins (see
`public/api/_lib/querybuild.py` `_rare_default_filters`) — the looser "carries all the affixes"
search. The picker (like the desktop advanced mode) is the precision tool: it prefills the exact
rolls and the user **loosens by clearing a min** (blank = any → presence-only) or unticking. So in
production, "picker all-ticked ≠ the API's Autoscan query" is the *same* advanced-vs-default
relationship the desktop app has, not a bug.

**Why the verify harness still asserts "all-ticked == the original strict query modulo ordering":**
the mock/stub fixtures author each rare's `trade_query` as the *picker's* strict query (roll-min,
pseudo-folded), so the exact-equality case holds against a controlled fixture; a **separate,
non-circular** structural assertion (`test_picker.mjs` CASE 1b) proves that against a *presence-only,
real-API-style* original the builder preserves the **same set of affixes + scope + links + defence
keys** and drops/invents nothing (the D-0015 guarantee that actually matters in production).

This is a genuine methodology point about how the picker's query relates to the API's default query.
I don't own `docs/00-decision-log.md`; **a short decision-log entry may be warranted** to record
"the public picker is roll-min / stricter-than-Autoscan, faithful to the desktop app."

Other faithful-to-local choices worth knowing:
- **usePseudo default ON** when resistances exist (desktop parity); toggling re-renders and swaps rows.
- The in-picker **Autoscan (N)** only appears with the extension active (it *is* extension bulk
  pricing); without the extension you Search each rare (opens its URL) or Skip.
- Per-item "Search this item" starts a **single-item** extension scan session. If a user rapid-fires
  several single searches before earlier ones resolve, the shared scan session resets between them,
  so the *live chip* of the earlier one can drop — but its **price still lands** (the price-result is
  keyed by its own reqId, independent of the scan session). Bulk pricing uses one session (Autoscan).

---

## Verification (offline, hermetic — no pathofexile.com, no browser)
- `node --check` clean on `assets/core.js`, `test_picker.mjs`, `test_scanstatus.mjs`.
- **`node test_picker.mjs` — 42 passed / 0 failed.** New harness. Cases: all-ticked == original
  (modulo ordering, key-order-independent) for base + category scope; structural fidelity vs a
  presence-only real-API original; untick-one; pseudo fold on/off; min edit + clear-to-presence; both
  bounds; negated→max; unsearchable never emitted; equip→armour_filters (+untick/edit); links/scope
  never invented; `rareTradeUrl` one `?q=` reusing host and encoding the same `{query,sort}`. Also
  parse-checks `core.js` + the index.html inline script.
- **`node test_scanstatus.mjs` — 47 passed / 0 failed** (regression guard: D-0012 3/msg chunking +
  v1.1 progress + old-extension fallback all intact; index.html still parses).
- **`?mock` served** (`python -m http.server`, curl) → HTTP 200 with the picker wiring present;
  server killed, port clear.
- **Headless render smoke** (scratchpad, throwaway; lenient Proxy DOM ran the *full* inline script +
  `?mock` build, then drove the picker) — 18/18: the queue picker rendered all-ticked checkboxes +
  editable mins + greyed unsearchable-with-reason + Search/Skip + "Rare 1 of 1"; edit-affixes on the
  priced 6-link showed the pseudo toggle + "6-link required" chip + defence row + "Re-search this
  item", with fold-ON hiding the individual fire-res row and showing the pseudo total.
- **Mock logic smoke** — 11/11 on the real `sample.js`: queue = the unpriced rare only; item-15
  all-ticked = the 2 searchable enchants (unsearchable excluded); item-1 pseudo on/off; edit/untick;
  `rareTradeUrl` reuse.

## Files
- `public/site/assets/core.js` — query builder + picker helpers + price paths + exports (+1-line
  `priceRowsViaExtension` query override).
- `public/site/index.html` — pick-affixes checkbox, "edit affixes" on rare rows, the picker module
  (queue + render + actions + wiring), `maybeAutoStart` guard, small CSS additions.
- `public/site/assets/sample.js`, `public/site/stub-build.json` — richer/consistent rare fixtures.
- `public/site/test_picker.mjs` — new offline harness (committed).
- `docs/notes-picker-site.md` — this file.
