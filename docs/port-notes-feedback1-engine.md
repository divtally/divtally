# Port notes — feedback round 1 (D-0006), ENGINE side

What the engine-side agent changed for D-0006 (owner feedback: flasks, gem host-grouping,
GRANTED audit, autoscan). UI side is specced in `docs/feedback1-spec.md`. Everything here is
ADDITIVE to the engine→UI contract (`docs/research/contract.md` §7). All work verified offline
against the live fixture `research/data/char_poe1.json`; **no** pathofexile.com trade calls were
made (per the round's rate-limit hold — gems price off poe.ninja, and all query assembly is pure).

Files changed (owned): `bpc/models.py`, `bpc/poeninja.py`, `bpc/pricing.py`, `tests.py`,
`docs/research/contract.md` (additive), `docs/feedback1-spec.md` (new), this file (new).

---

## 1. GRANTED — root cause and fix

**Root cause (traced end-to-end):** the granted flag was never computed in the engine. `web.py`
`_run_job` inferred it:
```python
_inv = str((it.raw or {}).get("inventoryId") or "")
row["granted"] = not _inv.startswith("SkillSlot")
```
Ported from PoE2, where gem items carried a `"SkillSlots"` inventoryId. In PoE1, gems come from
`skills[].allGems[]` and their `itemData.inventoryId` is **always `None`** (proven on the fixture:
all 17 gems). So `not "".startswith("SkillSlot")` == `not False` == **`True`** for every gem →
the owner's screenshot where Herald of Purity/Ice, Leap Slam, … were all tagged GRANTED.

The UI reads the flag from the skeleton row: `core.js::itemGranted(k)` → `it.granted`, used to
default granted skills out of the total. So the data was wrong at the source; the skins rendered it
faithfully.

**Fix (DATA, in the engine):** `bpc/poeninja.py::_gem_is_granted` computes granted from the
character JSON's authoritative signals:
- `entry.isBuiltInSupport == true` (a built-in support), OR
- a match in `itemProvidedGems` by `(slot, name)` — `itemProvidedGems[].slot` is the host
  `itemSlot`; the fixture has `[{slot:9, gems:[{name:"Herald of the Hive"}]}]` and
  `skills[5].itemSlot == 9`, so `(9,"herald of the hive")` matches, OR
- empty `itemData` (no `baseType`/`typeLine`/`frameType`) — a gem with no real item data cannot be
  a socketed tradeable gem; it exists only because an item grants it. **[INFERRED]** but strictly
  safe: every real socketed gem carries a `baseType`, so this never mis-flags the socketed
  Heralds/Leap Slam (they all have full itemData). Name-only fallback covers a provided entry whose
  `slot` is absent.

On the fixture this flags **exactly** `Herald of the Hive` (granted by Lost Unity) and nothing
else — the owner's bug is fixed at the data layer.

**Exclusion from the total:** `pricing.py::price_skill` skips the economy lookup for a granted gem
(`chaos = None`), so it never enters `total_chaos`. Its **socketed supports still count** (each gem
is judged independently). A granted gem keeps a `note` ("granted by <host> - not counted") and a
`trade_url` for reference, but never a number.

**UI follow-up (specced, not owned here):** `web.py` must switch the skeleton row to
`row["granted"] = bool(it.granted)`. That is the only change needed for the tag — `core.js` already
reads `it.granted`. Documented in `feedback1-spec.md` §B.

**Name recovery:** the granted `Herald of the Hive` active has EMPTY `itemData`, so its name lived
only on the `skills[]` entry (`allGems[0].name`). `normalize` now falls back to the entry name when
`itemData` yields no base type, so the granted row is no longer blank.

## 2. Gem host-item info + per-gem breakdown

- `normalize` builds `_host_index(data)` = `itemSlot -> {inventory_id, slot_label, name, base,
  unique}` from `items[]`, and attaches the host to each skill group via `skills[].itemSlot`. On
  the fixture: Ethereal Knives → Body Armour/Blunderbore; the three Herald pairs → Weapon/The
  Golden Charlatan; Leap Slam → Boots/Replica Voidwalker; Herald of the Hive → Ring/Lost Unity.
- `Item` gained `host_slot/host_name/host_base/host_unique/host_inventory_id` (additive).
- `price_skill` puts host info + `granted` into `extra`, and the per-gem breakdown (`gems[]`) gains
  `granted` + `note`. `support` is now the gem's REAL support-ness (`itemData.support`), so a group
  holding a second ACTIVE (Herald of Agony linked beside Herald of Ice; `support:false`) is labelled
  correctly and priced via the active-gem trade category. `it.supports[]` elements likewise gained
  `support` + `granted`.
- **Support costs are INCLUDED** in the group total (they always were — port-notes-core §gems;
  proven now by an explicit invariant test: `total_chaos == sum(g.chaos for priced g)`).

## 3. Flasks — belt order + count

`normalize` already appended every `flasks[]` entry in array order (belt order) → the engine emits
all flasks, in order, in `group=="flask"`. The web skeleton iterates `items` in order, so the web
UI already had belt order. The gap was **`price_build`**, which sorted non-gems by category
(unique→rare→magic) for the search budget; a belt mixing unique + magic flasks got split in the
CLI report. Fixed: `price_build` now prices in budget-priority order but **returns results in the
build's original order** (captured as `{id(it): idx}`, sorted back at the end). Belt order is now
preserved in every consumer. Life/mana classification was never in the PoE1 engine (that was a
PoE2 doll layout in the skins — removed per `feedback1-spec.md` §C).

## 4. Tests added (all offline, `python tests.py` green)

- Host index + `itemProvidedGems` index + `_gem_is_granted` unit cases, incl. the NON-granted
  socketed-herald case (the owner's mis-flag) and each granted signal.
- Fixture assertions: only the item-provided gem is granted; socketed Heralds/Leap Slam clean;
  granted active name recovered; host slot/name/unique correct; supports carry support+granted;
  5 flasks in belt order.
- `price_skill` invariant: `total == sum of priced gems` (supports included); granted ACTIVE
  excluded while a socketed support still counts; fully-granted skill → `total_chaos None`, no
  number; host info present in `extra`.
- `normalize`: synthetic 5-utility-flask belt emitted in order (none dropped).
- `price_build`: a mixed unique/magic 5-flask belt is RETURNED in belt order (guards the
  category-sort-scramble regression).

## 5. Verification performed

- `python tests.py` → green (full suite, incl. all new D-0006 cases).
- Imports clean for every module incl. the consumers not owned here (`bpc.web`, `bpc.cli`,
  `bpc.pob`).
- Regenerated the priced payload OFFLINE from the fixture through the REAL `web._result_dict`
  merge (stubbed economy, zero trade calls) — confirmed `granted`, `host_*`, `total_chaos`, and the
  per-gem `gems[]` breakdown appear as specced for both a socketed skill and the granted skill.

## 6. Open / handed to the UI round (not blockers)

- `web.py` one-liner (`row["granted"] = bool(it.granted)`) + optional host fields on the gem
  skeleton row (`feedback1-spec.md` §B.1, §D.1).
- Skins: host grouping, support nesting by index, 5-slot belt, Autoscan button (every picker copy).
- D-0006's own INTERPRETATION NOTE stands: "Autoscan" = auto-price all remaining rares
  (`bpc.searchAllRares`), NOT skip-everything; flagged in the decision log for owner correction.
