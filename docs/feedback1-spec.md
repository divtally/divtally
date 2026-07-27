# Feedback round 1 (D-0006) — UI implementation spec

**Status: authoritative for the UI/skin agents.** This is the spec of record for the
engine→UI changes owner-requested in **D-0006** (`docs/00-decision-log.md`). The engine side
is DONE and verified offline (see `docs/port-notes-feedback1-engine.md`); every field below
is emitted TODAY by `bpc/poeninja.py` + `bpc/pricing.py` and was captured from the live
fixture `research/data/char_poe1.json` (account `example-0416`, char `TestCharacter`,
Elementalist L100).

The contract stayed **ADDITIVE** — no field was renamed or removed (`docs/research/contract.md`
§7 records the additions). Skins that ignore the new fields keep working; this spec says how to
USE them to deliver what the owner asked for.

Scope of who edits what:
- **`bpc/web.py`** — one required change (§B), plus recommended additive skeleton fields (§D).
- **`bpc/ui/*.html` skins + `bpc/ui/assets/core.js` + `bpc/ui/assets/sample.js`** — §C, §D, §E.

---

## A. Exact JSON additions (real payloads)

All additions ride in the gem `PriceResult.extra`, which `web._result_dict` merges into
`priced[idx]` (`d.update(r.extra)`), so every field below is read as `p.<field>` where
`p = JOB.priced[k]`. Nothing here changes the non-gem payload.

### A.1 A normal socketed skill — `priced[k]` for "Herald of Purity" (socketed in the weapon)

```json
{
  "chaos": {"min": 25.0, "median": 25.0, "high": 25.0},
  "confidence": "high", "method": "skill", "note": "poe.ninja gem prices: active + 1 support",
  "kind": "skill", "level": 20, "quality": 20, "corrupted": false, "source": "poe.ninja",
  "granted": false,
  "host_slot": "Weapon", "host_name": "The Golden Charlatan", "host_base": "Lion Sword",
  "host_unique": true, "host_inventory_id": "Weapon",
  "total_chaos": 25.0,
  "gems": [
    {"name": "Herald of Purity", "support": false, "granted": false, "level": 20,
     "quality": 20, "corrupted": false, "chaos": 12.5, "variant": "20/20", "note": "",
     "trade_url": "https://www.pathofexile.com/trade/search/Allflame?q=..."},
    {"name": "Empower Support", "support": true, "granted": false, "level": 3,
     "quality": 20, "corrupted": false, "chaos": 12.5, "variant": "3", "note": "",
     "trade_url": "https://www.pathofexile.com/trade/search/Allflame?q=..."}
  ]
}
```

### A.2 A genuinely item-granted skill — `priced[k]` for "Herald of the Hive" (granted by Lost Unity)

```json
{
  "chaos": {"min": null, "median": null, "high": null},
  "confidence": "none", "method": "skill",
  "note": "item-granted skill (comes free with the host item)",
  "kind": "skill", "level": 30, "quality": 0, "corrupted": false, "source": "poe.ninja",
  "granted": true,
  "host_slot": "Ring", "host_name": "Lost Unity", "host_base": "Formless Ring",
  "host_unique": true, "host_inventory_id": "Ring2",
  "total_chaos": null,
  "gems": [
    {"name": "Herald of the Hive", "support": false, "granted": true, "level": 30,
     "quality": 0, "corrupted": false, "chaos": null, "variant": "",
     "note": "granted by Lost Unity - not counted",
     "trade_url": "https://www.pathofexile.com/trade/search/Allflame?q=..."}
  ]
}
```

### A.3 Field reference (all additive)

| Field (on `priced[k]`) | Type | Meaning |
|---|---|---|
| `granted` | bool | The **active** gem is item-provided (see §B). |
| `host_slot` | str | Friendly slot label of the gear the group is socketed in (`"Body Armour"`, `"Weapon"`, `"Ring"`, `"Boots"`, …). `""` for PoB imports. |
| `host_name` | str | Host item display name (`"Blunderbore"`, `"The Golden Charlatan"`). `""` if unknown. |
| `host_base` | str | Host item base type (`"Astral Plate"`, `"Lion Sword"`). |
| `host_unique` | bool | Whether the host item is a unique. |
| `host_inventory_id` | str | Raw host `inventoryId` (`"BodyArmour"`, `"Weapon"`, `"Ring2"`) — the **stable grouping key** (see §D). |
| `total_chaos` | number \| null | Group total = sum of the **purchasable** gems (active + supports, granted excluded). `null` when nothing is purchasable. Equals `chaos.median`. |
| `gems[]` | array | Per-gem breakdown (see below). `gems[0]` is the group's primary/active. |

Each `gems[]` element:

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Gem name. |
| `support` | bool | The gem's REAL support-ness (a group can hold >1 active — e.g. two linked Heralds — so this is NOT just "index > 0"). |
| `granted` | bool | This gem is item-provided / built-in → excluded from `total_chaos`. |
| `level`, `quality` | int | |
| `corrupted` | bool | |
| `chaos` | number \| null | Per-gem price. **`null` iff granted** (or no poe.ninja price). |
| `variant` | str | poe.ninja bucket label (e.g. `"21/20c"`). |
| `note` | str | `""` normally; `"granted by <host> - not counted"` for granted; `"no poe.ninja price for this gem"` when unpriced. |
| `trade_url` | str | Clickable per-gem trade search. |

**Invariant (tested):** `total_chaos == sum(g.chaos for g in gems if g.chaos != null)`. Support
costs are INCLUDED; granted gems (chaos `null`) are the only ones excluded.

---

## B. GRANTED semantics — which field the UI reads

**Root cause of the owner's "everything says GRANTED" bug:** the flag was never computed in the
engine. `web.py` inferred it from `it.raw.inventoryId`:

```python
_inv = str((it.raw or {}).get("inventoryId") or "")
row["granted"] = not _inv.startswith("SkillSlot")     # PoE2-era heuristic — WRONG for PoE1
```

In PoE1, gems come from `skills[]` and their `itemData.inventoryId` is **always `None`**, so
`not "".startswith("SkillSlot")` is **always `True`** → every gem was tagged granted.

The engine now owns this decision from the character JSON (`itemProvidedGems` / `isBuiltInSupport`;
`bpc/poeninja.py::_gem_is_granted`). A gem is granted iff it is item-provided, a built-in support,
or has empty itemData (cannot be a real socketed tradeable gem). On the fixture this correctly
flags **only** "Herald of the Hive" (granted by the Lost Unity ring) and leaves every socketed
Herald / Leap Slam clean.

### B.1 REQUIRED `web.py` change (one line)

In `_run_job`, the gem skeleton block, replace the inventoryId heuristic with the engine value:

```python
# was:
_inv = str((it.raw or {}).get("inventoryId") or "")
row["granted"] = not _inv.startswith("SkillSlot")
# becomes:
row["granted"] = bool(it.granted)
```

That is the whole fix for the tag. `core.js::itemGranted(k)` already reads `it.granted` off the
skeleton row (`state.items`), and already:
- defaults a granted skill OUT of the total (`state.enabled[k] = !itemGranted(k)`), and
- keeps granted skills OUT on "enable all" (`setGroupEnabled`).

No `core.js` change is required for the tag or the total-exclusion — the correct data flows into
the existing logic. (Granted-only groups also carry `chaos.median == null`, so they are excluded
from the total regardless; the tag + default-off is now correct rather than firing on everything.)

### B.2 What the skins render for the tag

- **Row-level GRANTED badge:** read **`it.granted`** (skeleton row), NOT the inventoryId, NOT
  "is the gem icon blank". Show the badge only when `it.granted === true`.
- **Per-gem GRANTED marker (optional, in the breakdown):** read `p.gems[i].granted`. Style a
  granted gem as excluded (e.g. struck-through price, "granted — not counted"); its `chaos` is
  `null`, so never print a number for it.

Edge case (rare): a granted ACTIVE that has real socketed supports. `total_chaos` already counts
the supports and excludes the active, and `p.gems[0].granted` is true while the support entries
are counted. If a skin wants such a row included-by-default (its supports cost real chaos), key the
include-default on `p.chaos.median != null` rather than `!granted`. Not required for correctness of
the total — it is already right — only for the default checkbox state.

---

## C. Flask belt rule (supersedes the PoE2 doll layout)

PoE1 has a **5-slot flask belt**. The engine emits **every** flask in the build in **belt order**
(the poe.ninja `flasks[]` array order), all in `group === "flask"`. There is **no** life/mana
classification and **no** name-guessing.

Skins MUST:
1. Render **5 generic belt slots**, filled **in flask order** (`JOB.items` order within the flask
   group == belt order — verified; the engine preserves it end to end).
2. If a build has **more than 5** flasks (weapon-swap sets, edge cases), render the overflow too —
   **never drop** a flask. Slots 6+ render below/after the 5 (a wrap row is fine).
3. **Delete** the old PoE2-derived "life | 3 utility | mana" doll: no slot is labelled life or
   mana, no flask is placed by its base/effect. A slot is just "belt position N".

The fixture has exactly 5 flasks; their belt order is
`Wine of the Prophet, The Overflowing Chalice, Cinderswallow Urn, Atziri's Promise, Quicksilver`.
A flask's defining line is its `utilityMods` (already folded into the pricer). Count and order are
guaranteed by the engine (tests: `normalize: 5 utility flasks all emitted`, `flask belt order
preserved`, and `price_build: flask belt order preserved`).

---

## D. Gem section rule — group under host item, nest supports under their active

Render the gem section grouped by **host item**, not as one flat list.

### D.1 Grouping

- Group gem rows by **`p.host_inventory_id`** (stable key; fall back to `p.host_slot` then
  ungrouped). Each group header shows **`host_slot` — `host_name`** (e.g. "Body Armour —
  Blunderbore", "Weapon — The Golden Charlatan", "Ring — Lost Unity"). Mark the header if
  `host_unique` (uniques drive most granted/linked setups).
- A host can hold **multiple skill groups** (the fixture's weapon holds 3 Herald pairs). List each
  skill row under its host header.
- Gems whose host is unknown (`host_inventory_id === ""`, e.g. PoB imports) fall under a generic
  "Gems" / "Other" header — do not drop them.

**Timing note:** `p.host_*` arrives with the priced entry. Gems price fast (poe.ninja, no trade
budget), so grouping-on-price is fine. For grouping BEFORE the price lands, `web.py` may
additively copy the host fields onto the gem skeleton row (recommended, additive):

```python
# in _run_job, the `if it.category == CAT_GEM:` block — additive, optional:
row["host_slot"] = it.host_slot
row["host_name"] = it.host_name
row["host_unique"] = it.host_unique
row["host_inventory_id"] = it.host_inventory_id
```

Then skins can group off `it.host_inventory_id` immediately and fill prices as they arrive.

### D.2 Nesting supports under their active

- `p.gems[0]` is the group's **active/primary**; `p.gems[1:]` are its linked gems, in order.
- `it.supports[i]` (skeleton) mirrors `p.gems[i+1]` **by position** (same order, same length).
  Match them **by array index**, not by a `support === true` filter — a group can contain a second
  ACTIVE gem (e.g. Herald of Agony linked beside Herald of Ice) whose `support` is `false`, and it
  still nests under the primary and still carries a price.
- For each nested gem show name · Lv/quality · its `chaos` price (or "—" when `null`). Style
  `granted` nested gems as excluded.
- The row's headline price is `p.total_chaos` (== `p.chaos.median`) = active + every support, with
  granted gems excluded. Support costs are part of it.

(The existing stash `supportsHTML` matches supports by lowercased name against
`p.gems[].support`; switch it to **index alignment** `it.supports[i] ↔ p.gems[i+1]` so linked
second-actives and duplicate-named gems price correctly.)

---

## E. Autoscan button (top of the rare affix picker)

Owner ask (D-0006): the bulk "price all remaining rares with default searches" action becomes a
prominent, **glowing** button labelled **"Autoscan"** at the **TOP** of the rare affix picker; a
small **non-glowing** "skip all (don't price)" stays **below** the picker as before. Per-item
**Search** / **Skip** (`#pSearch` / `#pSkip`) and **Back** are unchanged.

### E.1 Wiring (unchanged core.js API — do NOT rename these)

- **Autoscan** → `bpc.searchAllRares()` (prices every remaining rare with its default all-affix
  query — this is exactly the former "Search all N (default)" action).
- **skip all (don't price)** → `bpc.skipAllRares()` (unchanged).

Both are already exported by `core.js` (`bpc.searchAllRares`, `bpc.skipAllRares`). No `core.js`
change is needed for the buttons.

### E.2 Markup change (each picker copy)

Today each picker renders the bulk row at the **bottom**:

```js
if(!info.single && remain>1) h+=`<div class="pbulk">
  <button class="stone-btn pa-skip"   id="pSkipAll"   type="button">Skip all ${remain}</button>
  <button class="stone-btn pa-search" id="pSearchAll" type="button">Search all ${remain} (default)</button>
</div>`;
```

Change to: an **Autoscan** button at the **TOP** of the picker body (before the affix rows), and a
small **skip-all** kept below (near/after the per-item buttons). Same
`!info.single && remain>1` visibility guard (only when >1 rare remains):

```js
// TOP of the picker (prepend, before the affix list):
if(!info.single && remain>1) top+=`<div class="pautoscan">
  <button class="stone-btn autoscan" id="pSearchAll" type="button"
          title="price all ${remain} remaining rares with default all-affix searches">
    ⚡ Autoscan${remain>1?` (${remain})`:''}</button></div>`;

// BELOW the picker (small, non-glowing), replacing the old bottom bulk row:
if(!info.single && remain>1) h+=`<div class="pbulk">
  <button class="stone-btn pa-skip small" id="pSkipAll" type="button">skip all (don't price)</button></div>`;
```

Keep the ids **`#pSearchAll`** and **`#pSkipAll`** so the existing `pkWire*` handlers
(`sa.onclick=()=>bpc.searchAllRares()`, `ka.onclick=()=>bpc.skipAllRares()`) bind unchanged.
Only the label, placement, and styling change.

### E.3 Glow recipe (skin adapts to its own accent)

Generic, self-contained; each skin swaps `--accent` for its own accent colour (do NOT hardcode a
palette — use the skin's existing accent variable):

```css
.stone-btn.autoscan{
  --accent: /* skin's accent, e.g. var(--bz-hi) / var(--val) / #d9a441 */;
  position:relative; font-weight:700; letter-spacing:.04em;
  border-color:var(--accent);
  color:var(--accent);
  box-shadow: 0 0 0 1px var(--accent) inset,
              0 0 8px  color-mix(in srgb, var(--accent) 55%, transparent),
              0 0 18px color-mix(in srgb, var(--accent) 35%, transparent);
  animation: autoscanPulse 1.8s ease-in-out infinite;
}
.stone-btn.autoscan:hover{ filter:brightness(1.12); }
@keyframes autoscanPulse{
  0%,100%{ box-shadow: 0 0 0 1px var(--accent) inset,
                       0 0 6px  color-mix(in srgb, var(--accent) 45%, transparent),
                       0 0 14px color-mix(in srgb, var(--accent) 25%, transparent); }
  50%    { box-shadow: 0 0 0 1px var(--accent) inset,
                       0 0 12px color-mix(in srgb, var(--accent) 70%, transparent),
                       0 0 26px color-mix(in srgb, var(--accent) 45%, transparent); }
}
@media (prefers-reduced-motion: reduce){ .stone-btn.autoscan{ animation:none; } }
```

(If a skin's CSS can't use `color-mix`, fall back to layered `rgba()` shadows in the accent hue.)
The small skip-all stays plain (`.pa-skip.small` — muted, no glow, smaller font).

### E.4 EVERY copy of the picker markup

Several skins render the picker markup **more than once** (different layouts/modes). You MUST apply
E.2 to **every** copy in the file, or one layout keeps the old bottom "Search all (default)" button.
Known example: **`stash.html` has THREE** picker renderers — `pkRender` (~L1454), the survey variant
`pkRenderSurvey` (~L1715), and the classic variant `pkRenderClassic` (~L1760) — each with its own
`#pSearchAll`/`#pSkipAll` block AND its own `pkWire*`. `binder.html` and `waterfall.html` also carry
the bulk buttons. Grep each skin for `pSearchAll` / `pSkipAll` and fix them all.

---

## F. UI-agent checklist

1. **`web.py`**: `row["granted"] = bool(it.granted)` (§B.1). Optional: copy `host_*` onto the gem
   skeleton row (§D.1).
2. **GRANTED badge**: render off `it.granted` (§B.2). Only "Herald of the Hive"-type item-provided
   gems should light up now.
3. **Flasks**: 5-slot belt in flask order, overflow shown, no life/mana slots (§C).
4. **Gems**: group by `host_inventory_id` under a "`host_slot` — `host_name`" header; nest
   `p.gems[1:]` under `p.gems[0]` by index; show per-gem prices; granted gems shown excluded (§D).
5. **Autoscan**: glowing "Autoscan" (`bpc.searchAllRares`) at the picker TOP; small non-glowing
   "skip all (don't price)" (`bpc.skipAllRares`) below; per-item Search/Skip unchanged; fix EVERY
   picker copy (§E).
6. Nothing renamed/removed — all additive. Divine/chaos math and every other payload field are
   unchanged.
