# Notes — per-rare affix-picker payload in `api/build` (D-0015 feature)

Working notes for the build round that exposes the **picker-ready affix payload** in the public
`api/build` response, additively. The owner's most-wanted feature (D-0015): the per-rare affix
picker, driven by data the server prepares but never acts on. This is the DATA layer only — the
public site's picker UI consumes it in a later round (today `public/site/assets/core.js` stores
`state.rares` but renders no picker from it).

## The spec (D-0015, verbatim intent)
> "if the user doesn't manually exclude an affix we should not be doing that for them."

Default = every affix ticked; only a USER action changes the query. So the payload must expose
**every** affix of every trade-queryable item — including the unsearchable ones (`searchable:false`,
greyed in the picker) — so the user sees everything and the tool hides nothing. The default
`trade_query` already requires ALL searchable affixes (verified invariant, below); this map is what
lets the user *subtract*.

## What shipped (all inside `public/api/**`, additive)
- **`_lib/querybuild.py` → `PublicPricer.affix_options`** now emits, per affix, on top of the
  existing `{kind,text,stat_id,value,searchable,resist,negated,prefer,priority,reason}`:
  - **`group`** — the mod's trade stat group from `Item.mod_src`: `explicit` / `crafted` /
    `fractured` / `enchant` / `veiled` / `scourge` / `crucible`; `equip` for defence totals;
    `pseudo` for pseudo entries. Defaults to `explicit` for PoB imports (they carry no per-mod
    `mod_src`).
  - **`default_min` / `default_max`** — the value the picker prefills (mirrors `bpc/web.py`
    `affixRow`): a normal roll prefills MIN = the item's value; a `negated` ("reduced") roll carries
    a NEGATIVE value on the opposite-polarity stat and prefills MAX instead. Both `null` for an
    unsearchable affix (no filter to prefill); `value` still carries the raw roll for display.
  - **`negated`** added to `equip`/`pseudo` entries too (always `false`) for shape parity.
- **`pseudo[]` entries** gained **`folds`**: `[{index, text, stat_id, value}, …]` — which of the
  item's affixes were summed into that resistance total, so the picker can grey out exactly the
  rows it replaced. `index` points into the same entry's `affixes` array. Bucketing mirrors
  `res_contributions()` exactly (all-Elemental → elemental; all-Resistances → BOTH totals;
  single-element → elemental; chaos → chaos).
- **`_lib/response.py`** — the `rares` map now also includes **magic** items (`kind:"magic"`),
  not just rare + unique. `kind` is a 3-way (`rare`/`unique`/`magic`); existing rare/unique entries
  are byte-identical apart from the new affix keys.

## Where the shapes came from (mirroring the local app)
- Read `C:\scripts\buildpricechecker-poe1\bpc\web.py`: `rares_meta` construction (~L298-351) and the
  picker JS (`affixRow`, `renderPicker`, `defaultRarePayload`, ~L1140-1232). The picker consumes
  `value`/`negated`/`resist` to derive min/max prefill and the resist-fold at render time; this
  build makes those derivations EXPLICIT (`default_min`/`default_max`/`folds`/`group`) so a public
  picker needs no client-side re-derivation.
- Parent `C:\scripts\buildpricechecker\bpc\web.py` (PoE2, read-only) confirmed the same
  `j["rares"]` map pattern — kept the top-level key name `rares` (site's `core.js` reads
  `doc.rares`); adding magic entries + new affix keys is inert for the current site.
- `affix_options` is the single source of the payload (as in the local app); `response.py` stays a
  thin shaper.

## Pseudo ids — source-verified (global [NOT FROM SOURCE] rule)
`pseudo.pseudo_total_elemental_resistance` and `pseudo.pseudo_total_chaos_resistance` are REAL
trade stat ids — both present in the bundled `public/api/_data/trade_stats.json` (grep-confirmed).
Defined as module constants in `querybuild.py` (`_PSEUDO_ELEM_RES` / `_PSEUDO_CHAOS_RES`), same as
`bpc/pricing.py` and `bpc/statmap.py`. No porting was needed; nothing invented.

## Interpretation flagged for the owner / main agent (RULE 1/5)
- **Scope now includes magic.** The task said "every rare/magic item that carries a trade_query";
  the pre-existing `rares` map covered rare + unique. I took the **union** (rare + unique + magic):
  magic is the task's explicit new ask; dropping unique would be a regression against the additive
  rule. Net effect: `rares` grew from 33 → 35 entries on the ascii fixture (adds the magic bow +
  magic flask). If the owner wants magic EXCLUDED, remove `CAT_MAGIC` from the loop guard in
  `response.py` — one line. **This is a scope decision that may warrant a decision-log entry**
  (I don't own `docs/00-decision-log.md`).
- **Implicits are NOT offered as pickable affixes** — the local app's `affix_options` only iterates
  `explicit_mods` (enchant/crafted/fractured/etc. live there via `mod_src`; true implicits are a
  separate `Item.implicit_mods` list carried on the item row's `mods.implicit`, and the local
  picker never lists them). Mirroring the local app, I kept that. The `group` field's value set is
  therefore the `mod_src` groups + `equip`/`pseudo` (no `implicit`). Flag if the owner wants
  implicits pickable — that would DIVERGE from the local app.

## Verification (offline, hermetic — no pathofexile.com)
`python public/api/_verify.py` (Phase A; `BPC_SKIP_LIVE=1` skips the live poe.ninja Phase B) —
**ALL CHECKS PASSED**. New/strengthened assertions:
- Every `rares[]` affix carries `group` + `default_min`/`default_max`; searchable affixes prefill
  ≤1 bound; `kind ∈ {rare,unique,magic}`.
- Every `pseudo[]` entry carries `folds` (a list); every fold member's `index` resolves to a
  `resist:true` affix on the same item.
- The ascii fixture has a `kind:"magic"` entry, a populated pseudo `folds`, and a group on every
  affix.
- Every rare/unique/magic item index has a `rares` entry.
- **D-0015 invariant (regression guard):** the default rare `trade_query` still has exactly one
  `stats` filter per searchable stat affix and one `armour_filter` per defence total — proving the
  enriched `affix_options` didn't alter the built query. Empirically confirmed across all 17 rares
  in the fixture (7/7, 4/4, 6/6, … all match).

No behavior change to existing response fields: the new keys are additive inside `rares[].affixes`
/ `.pseudo`; `items[]`, `totals`, `meta`, per-item `trade_query`/`trade_url`/`price` are untouched
(the query builder reads only the pre-existing affix keys). `json.dumps(..., allow_nan=False)`
stays clean.

## Files
- `public/api/_lib/querybuild.py` — `_affix_defaults`, `_res_fold_members` helpers; enriched
  `affix_options`.
- `public/api/_lib/response.py` — magic added to the `rares` loop; 3-way `kind`.
- `public/api/_verify.py` — new assertions (owned dev tool; never bundled/routed).
- `docs/public-contract.md` — §2.6 rewritten as the full authoritative schema + real fixture
  example (additive: every previously-documented field retained).
