# Port notes — feedback round 1 (D-0006), SHARED-JS side (core.js + sample.js)

The shared-JS slice of D-0006 (spec of record: `docs/feedback1-spec.md`, decision `docs/00-decision-log.md`
D-0006, engine side already done: `docs/port-notes-feedback1-engine.md`). Everything here is
**ADDITIVE** — no core.js API was renamed or removed, so every existing skin keeps working. No
pathofexile.com trade calls were made (offline `node` + a local mock-mode server boot only).

Files I own / changed: `bpc/ui/assets/core.js`, `bpc/ui/assets/sample.js`, this file. I did **not**
touch `web.py` or any skin `*.html` (owned by other agents this round — see the dependency note at
the end).

---

## 1. core.js — new shared helpers (additive; searchAllRares/skipAllRares untouched)

Added one small helper block (after `itemsByGroup`) and three exports on the `bpc` object. Nothing
else in core.js changed. `node --check` clean.

### `bpc.gemGroups()` — group the gem section by host item (spec §D.1)
Returns an **ordered** array, one entry per host item:
```
{ key, slot, name, base, unique, header, items: [<skeleton gem row>, ...] }
```
- `key` = host `inventoryId` (stable grouping key), falling back to `host_slot`, then `""` (an
  ungrouped "Gems" bucket for PoB imports / unknown hosts — rows are **never dropped**).
- `header` = `"<slot> — <name>"` (e.g. `"Body Armour — Rift Shroud"`), or just the slot/name, or
  `"Gems"` when neither is known. `unique` is true if the host is a unique (mark the header).
- Group order **and** within-group row order follow `state.items`, so skill order is preserved. One
  host may hold multiple skill rows — all land under one header (the fixture's weapon holds 3).

### `bpc.gemBreakdown(key)` — per-gem breakdown accessor for ONE gem row (spec §D.2)
Returns `{ total, granted, gems: [ {name, support, granted, active, level, quality, corrupted,
chaos, variant, note, trade_url, icon}, ... ] }`.
- Reads the priced entry's `gems[]` (authoritative): `gems[0]` = the active, `gems[1:]` = linked
  gems in the **same order/length as `it.supports[]`**. Support ↔ skeleton matching is by **INDEX**
  (`gems[i>0]` ↔ `it.supports[i-1]`), never by name — so a link holding a 2nd active (support:false)
  still nests correctly and still carries its own price.
- `total` mirrors `p.total_chaos` (== `p.chaos.median`) = active + every support, granted excluded.
  **Tested invariant holds:** `total == sum(g.chaos for g in gems if g.chaos != null)`.
- Granted-only group → `total: null`, its one gem `chaos: null`, `granted: true`.
- Falls back to the skeleton (active + `it.supports`, prices `null`) if the priced `gems[]` has not
  arrived yet, so a skin can render the breakdown before/without a price.

### `bpc.gemHost(rowOrKey)` — host-item info reader for a single gem row
Returns `{ inventory_id, slot, name, base, unique }`. Reads the priced entry first (`p.host_*`,
authoritative once priced), then falls back to the skeleton row (`it.host_*`, present only if
`web.py` copied the fields per spec §D.1) so grouping works **before** the price lands. Accepts a
skeleton row object or an index/key.

### Autoscan / skip-all wiring — unchanged, confirmed
`bpc.searchAllRares()` (Autoscan = price every remaining rare with its default all-affix query) and
`bpc.skipAllRares()` (skip all, don't price) were **already** implemented and exported; I left them
exactly as-is per the spec (§E.1 "do NOT rename these"). The Autoscan button work is a skin-markup
change (spec §E.2), not a core.js change. Verified both are still exported after my edits.

## 2. sample.js — mock rebuilt to exercise the new UI

A fictional but plausible PoE1 **Firestorm Elementalist**, wired so any skin renders every D-0006
surface with `?mock`. Header block loudly marks it DEMO DATA — every chaos price and every
item→skill grant is a demo fabrication, never a source-of-truth number.

- **Flask belt = 5 utility flasks, in belt order** (spec §C): Bottled Faith, Cinderswallow Urn,
  Atziri's Promise, Quicksilver Flask of Adrenaline, Basalt Flask of the Iron Skin. All real PoE1
  utility flasks; **no life/mana slots** (the old sample's `Divine Life Flask` / `Eternal Mana Flask`
  are gone). `group:"flask"`, array order == belt order.
- **Gems grouped by host item** across **five hosts** (spec §D): Body Armour (rare `Rift Shroud`) =
  a **6-link** Firestorm (active + 5 supports); Weapon (`Doryani's Catalyst`) = Herald of Ash +
  Combustion; Helmet (`Crown of the Inward Eye`) = Determination + Enlighten (Enlighten drives the
  cost); Boots (`Atziri's Step`) = Flame Dash + Second Wind + Arcane Surge. Each priced gem carries
  `host_*` + `granted` + a per-gem `gems[]` breakdown with per-support prices; the invariant
  `total_chaos == sum(priced gems)` holds for every group. `host_*` is also copied onto the skeleton
  gem rows (representing `web.py`-with-§D.1) so grouping-before-price is exercised too.
- **Exactly ONE genuinely granted gem** (spec §B): Ring (`Lost Unity`, a real Formless Ring unique)
  grants **Herald of Agony** — `granted:true` on the skeleton row (→ row-level GRANTED badge), null
  price, excluded from totals by default. Modeled on the spec's canonical fixture example (§A.2
  Lost Unity → item-provided herald). The socketed **Herald of Ash** in the weapon is deliberately
  **NOT** granted — that contrast is the fixed bug made visible. (The old sample reproduced the very
  bug: it had `granted:true` on the socketed `Flame Dash` — removed.)
- **Support-count field:** each gem row's `sockets` = number of support gems (the `stash` skin
  renders it as the "· N sup" label — verified at `stash.html:1003/1012`); granted herald = 0.
- Icons: real `web.poecdn.com` PoE1 art; a few reused across slots/gems (no new/forged poecdn URLs —
  the hash segment is server-signed and can't be fabricated offline; reuse is the file's existing
  convention and is noted in the header).

## 3. Verification performed (all offline / local — zero trade calls)

1. `node --check bpc/ui/assets/core.js` and `… sample.js` → both clean (`node` v22.19.0).
2. **Semantic harness** (`scratchpad/verify_core.js`): ran the real `sample.js` through the real
   `core.js` (stubbed `window`/`localStorage`, no DOM/network) — **ALL GREEN**:
   - flask belt = 5, correct order, no life/mana;
   - `gemGroups()` = 5 hosts in items order, correct headers + unique flags, keys distinct;
   - `gemBreakdown()` invariant `total == sum(priced gems)` for all 4 priced groups; granted-only
     group → `total null`; exactly one active = `gems[0]`; Boots supports nested by index;
   - GRANTED audit: exactly one granted gem row (Herald of Agony), socketed Herald of Ash not
     granted, granted flows through the breakdown;
   - `totals()` defaults the granted gem OUT and includes the 4 socketed groups; `included==priced`;
   - `searchAllRares` / `skipAllRares` still exported; new helpers exported.
3. **Server boot** (`scratchpad/boot_and_fetch.py`): `python -m bpc.web --no-browser --port 8905`,
   then fetched `→ 200` each: `/assets/core.js` (27,427 B, contains `gemGroups`+`searchAllRares`),
   `/assets/sample.js` (31,808 B, contains `Herald of Agony`+`Bottled Faith`), `/v/stash?mock=1`
   (112,531 B, HTML). Server terminated; port left in TIME_WAIT only (no LISTENING).

## 4. Cross-agent dependency (flagged, NOT my file)

- **`web.py` §B.1 one-liner still pending.** `web.py:315` still has the old heuristic
  `row["granted"] = not _inv.startswith("SkillSlot")` (the PoE1 bug → every gem tagged granted on
  **live** builds). The `web.py` agent must change it to `row["granted"] = bool(it.granted)` (and
  may optionally copy `host_*` onto the gem skeleton row per §D.1). My core.js helpers + sample data
  are ready for that. **Mock mode is unaffected** — `loadMock` sets `state.items` straight from
  `sample.js`, so the correct `granted` flags already flow in the `?mock` demo regardless of the
  web.py fix. Skins own the GRANTED badge / host-group / flask-belt / Autoscan markup (spec §C/§D/§E).
