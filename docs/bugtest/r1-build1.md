# R1 / Build 1 - API end-to-end audit

**Round:** 1 (API end-to-end) of the D-0020 five-round bug campaign.
**Build:** `qwartus-3381 / qwartus_niceboat` (Occultist L100, Allflame) -
`https://poe.ninja/poe1/builds/allflame/character/qwartus-3381/qwartus_niceboat`
**API under test:** `GET https://divtally.vercel.app/api/build?url=...`
**Date:** 2026-07-27. **Auditor scope:** read-only; no pathofexile.com calls; ground truth =
raw poe.ninja character JSON + poe.ninja economy overviews, cross-checked against the engine
source in `public/api/`.

Every number below is **source-derived** (a live API response, a live poe.ninja economy line, or
the actual engine code) unless tagged `[INFERRED]` / `[UNVERIFIED]`.

---

## 0. CRITICAL METHODOLOGY NOTE - snapshot/cache skew (read first)

The API served a build snapshot **older than live**, and there is **no way to force a fresh
fetch** (see Finding 4). Consequences for this audit:

- My first API call resolved poe.ninja snapshot version `0332-20260728-26629` (from
  `meta.cache_key`); live `index-state` at the same moment was already `0407-20260728-09123`.
- poe.ninja serves the **latest** snapshot for `timeMachine=""` regardless of the version in the
  URL path, so I **cannot** re-fetch the exact stale payload the API cached. The character
  re-rolled two rares in the gap: **Boots** (`Brood Slippers` live vs `Havoc Trail` in our
  response) and **Amulet** (`Entropy Idol, Jade Amulet` live vs `Maelstrom Braid, Amber Amulet`
  in our response). Grim Coat's ES/resist rolls also drifted +/-1-2.
- Therefore item **names/rolls on Boots + Amulet are NOT bugs** - they are snapshot skew and were
  excluded from name/roll validation. The other 7 rares, all uniques, all flasks, the jewel and
  all gems are **stable** (identical live vs our response) and were fully validated.
- Gem PRICES could only be checked against the *current* economy; small (<a few %) differences
  are economy drift, not bugs. One gem price could not be reconciled at all (Finding 6).

Data captured to scratchpad: `raw_ninja.json` (live 0407), `raw_pinned.json` (0332 path = also
live), `ours_api.json` (our response, cached 0332).

---

## 1. Findings summary

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| 1 | **major** | Gem-group dedup silently **drops distinct duplicate gems** | 3 Raise Spectre (distinct ids) on Offhand2 -> only 1 in `items[]`; 2 dropped |
| 2 | **major** | Build-overview & PoE2 links return **502 `ninja_error`** instead of **400 `bad_input`** | contract sec.4; live probe + build.py:69 |
| 3 | minor | API `totals` + `priced_items` **include weapon-swap items** (contra D-0018 "out of totals") | 1745.41 incl. 116.3 swap; response.py:100 |
| 4 | minor | **No cache-bust**; `fresh=1` ignored; up-to-30-min stale + nondeterministic totals | served 0332 vs live 0407; 1745.41 vs 1689.6 same version |
| 5 | minor | **Implicit mods omitted** from the affix picker (+ implicit chaos-res not folded into pseudo) | every item's `implicitMods` absent from `rares[].affixes` |
| 6 | minor `[UNVERIFIED]` | Shield Charge gem priced **91.0c**; nearest current bucket ~2c - unreconcilable | can't re-check (Finding 4) |

No **blocker**: the default (swap-excluded) headline total is approximately correct, nothing
crashes, and no priced item on the main build is grossly mispriced.

---

## 2. Detailed findings

### Finding 1 - [MAJOR] Gem-group dedup drops distinct duplicate gems
**File:** `public/api/_lib/poeninja.py:756-759` (verbatim from parent `bpc/poeninja.py:590-593`,
comment there: `# collapse duplicate setups (e.g. weapon swap)`).

`normalize()` deduplicates skill groups by the coarse signature
`(active.base_type, active.gem_level, tuple(support_names))` and **skips** (drops, never counts)
any later group with a matching signature:
```python
sig = (active.base_type, active.gem_level, tuple(s["name"] for s in sups))
if sig in seen_skill:
    continue           # <-- group dropped entirely, no count bump
seen_skill.add(sig)
items.append(active)
```
The build has **three** `Raise Spectre` gems socketed in the Offhand2 quiver (Maloney's
Mechanism), which poe.ninja returns as three single-gem `skills[]` groups. They are **physically
distinct gems** - verified distinct ids in the raw JSON:
`bbef5fa66c015b20`, `d54ef1cedf526b09`, `e95441c826d903bf` (all match the quiver's three
`socketedItems`). All three share the signature `("Raise Spectre", 19, ())`, so **two are
dropped**. Our `items[]` has exactly one Raise Spectre row for Offhand2 (`index 27`, `count 1`),
not three.

Full gem reconciliation confirms this is the *only* drop: raw `skills[]` = 33 gems total; our 10
gem rows represent 31 gems; delta = exactly the 2 dropped Raise Spectre.

**Why it's a real bug (not correct de-duplication):**
- The signature ignores **quality and corruption**, so two same-name/level groups that differ in
  quality/corrupt collapse too - and the *dropped* copy can be the more expensive one.
- Distinct gems in distinct sockets are legitimately separate items; collapsing them
  **undercounts** any build that runs duplicated identical gems (minion builds with N identical
  spectres/zombies/SRS, aura stacks, duplicate utility gems). This is squarely a "dropped items"
  defect.

**Impact on THIS build:** limited in chaos terms because the dropped copies sit on a weapon-swap
item (excluded from the default total). But `items[]` is objectively incomplete (missing 2 rows),
and with the "weapon swap" toggle ON the total under-counts by 2 x 14.9 = **29.8c**. On a
main-hand minion build the same defect would hit the headline total directly.

**Fix direction:** dedup only true duplicates (e.g. by gem-id set, or don't dedup within the same
host slot), or aggregate into `count` instead of dropping.

---

### Finding 2 - [MAJOR] Wrong error classification for build-overview and PoE2 links
**Files:** `public/api/build.py:69-70`; `public/api/_lib/poeninja.py:parse_build_url` (raises
`PoeNinjaError` for every URL problem: lines 60,66,71,79,81).

Live probes (this build's host):

| Input | HTTP | `error_type` | Correct per contract sec.4 |
|---|---|---|---|
| build-overview `.../poe1/builds/allflame` (no `/character/`) | **502** | **`ninja_error`** | 400 `bad_input` |
| PoE2 link `.../poe2/builds/.../character/...` | **502** | **`ninja_error`** | 400 `bad_input` |
| non-poe.ninja host `example.com/...` | 400 | `bad_input` | 400 `bad_input` (OK) |

Contract sec.4 is explicit: *"`bad_input` (400) - unrecognised URL/code, **a build-overview
link**, an unsupported paste host, or missing input."* Both failing cases are user-input errors
but are reported as **`ninja_error` (502)**, whose contract meaning is *"poe.ninja was unreachable
/ returned no data / the character is private/unindexed."*

**Root cause:** `parse_build_url` raises `PoeNinjaError` for URL problems; `build.py` maps
`PoeNinjaError` -> 502 `ninja_error` (it only maps `engine.EstimateError` -> 400). A non-poe.ninja
host is caught earlier as `EstimateError` (hence the correct 400 for `example.com`), so the
classification is *inconsistent* - only poe.ninja-shaped bad URLs get the wrong code.

**Impact:** a client that branches on `error_type`/HTTP status (the contract does say "branch on
`ok`", which mitigates) shows a "poe.ninja is down, try again later" style message - and may
**retry a 502 uselessly** - when the real problem is the user pasted a build-list/overview link
or a PoE2 link. The human-readable `error` string itself is correct and helpful; only the
type/status are wrong. Pasting the overview URL instead of a character URL is a common user
mistake, so this path is hit in practice.

**Fix direction:** raise `EstimateError` (or map `PoeNinjaError` from the *parse* stage) to
`bad_input`/400; keep `ninja_error`/502 only for actual fetch failures.

---

### Finding 3 - [MINOR] API `totals` (and `priced_items`) include weapon-swap items
**File:** `public/api/_lib/response.py:100-110` (`_sum_tier`) - sums every row with
`source == "poe.ninja"` with **no swap filter**; `priced_items` (line 194 / `_priced_ninja`)
likewise counts swap rows.

D-0018 says weapon-swap items are *"out of totals, scans, and the rares list unless the ... toggle
re-includes them."* The API total does **not** exclude them:

- `totals.chaos.median = 1745.41`. Swap-hosted priced rows = Maloney's Mechanism (12.0, Offhand2)
  + 3 swap Raise Spectre groups (59.6 + 29.8 + 14.9) = **116.3c**.
- Swap-excluded total = 1745.41 - 116.3 = **1629.11c**.

The **site** compensates: `core.js` `totals()` (lines 154-176) recomputes client-side from
`enabled` items, and `defaultOn()`/line 570 exclude swaps by default - so the *site* shows the
swap-excluded number. But the API's own `totals` field and `priced_items:15` are swap-inclusive
and **undocumented as such** in the contract (sec.2.2 only says "sums poe.ninja-priced items").
Any non-site consumer (the extension, a userscript) that trusts `totals` **overstates** by the
swap value, and `totals` disagrees with what the site displays for the same build.

**Fix direction:** either exclude swap rows from `_sum_tier`/`priced_items` to match D-0018 and the
site, or document in the contract that `totals` is swap-inclusive and consumers must subtract
`swap:true` rows.

---

### Finding 4 - [MINOR] No cache-bust; `fresh=1` ignored; stale + nondeterministic
**Files:** `public/api/build.py` (GET reads only `url/input/league/status` - **no `fresh`**);
`public/api/_lib/cache.py`; TTLs in `poeninja.py` (character `1800`s line 199, index-state `600`s
line 108, economy `1800`s).

- The task's `&fresh=1` is **silently ignored** - there is no cache-bypass parameter. The
  response came from the per-instance in-memory/`/tmp` cache: it served snapshot `0332` while live
  was `0407` (boots/amulet already re-rolled), so the audited gear was **staler than live** with
  no way to refresh.
- Caches are **per serverless instance** (cache.py note: cross-request caching is CDN + a future
  KV layer, "not by this module"), so repeated calls hit different warm instances. Live evidence:
  the same build at the **same** version `0407` returned `totals.median` **1745.41** (plain URL)
  vs **1689.6** (all URL-variant calls) - a ~3.3% swing with no build change.

**Impact:** a user who just changed gear can see up-to-30-min-stale pricing with no way to force a
refresh; identical requests can return materially different totals depending on which instance
serves them. Also blocks reliable price re-verification (Finding 6). Largely inherent to the
current caching design, hence minor - but a documented `fresh`/`nocache` param (bypassing the
in-process + `/tmp` layers) would fix both the UX and the auditability gap.

---

### Finding 5 - [MINOR] Implicit mods omitted from the affix picker
**File:** `rares[].affixes` construction (`querybuild.affix_options`; only explicit-style buckets
are walked). Every item's `implicitMods` are **absent** from the affix picker. Verified on stable
rares:

| Item | implicit(s) missing from `rares[].affixes` |
|---|---|
| Woe Ward (Helmet) | `7% of Physical Damage from Hits taken as Cold Damage`; `26% increased Mana Cost Efficiency` |
| Storm Thirst (Wand) | `Minions deal 30% increased Damage` |
| Grim Coat (Body) | `10% of Physical Damage from Hits taken as Lightning Damage`; `+2% to all maximum Resistances` |
| Entropy Gyre / Vortex Knuckle (Rings) | `+23% to Chaos Resistance` (Amethyst base implicit) |

All **explicit** mods are correctly covered (folded properly: defence mods -> `equip` totals with
`armour_filters` es-min at 85%; resistances -> stat + `pseudo` totals), so this is a completeness
gap, not a mispricing of the default query (rares are searched on explicits by design).

**Two consequences:** (a) a user cannot opt-in to search a build-**defining** corrupted/influence
implicit (e.g. a `+1 to all Skill Gems` corruption implicit) - it isn't offered at all; (b) the
implicit resistance is **not folded into the pseudo total** - e.g. Entropy Gyre's
`pseudo_total_chaos_resistance` = 33 (explicit only), understating the true 33+23 = 56. Low impact
on this build (all implicits are ordinary base implicits) but wrong in principle.

---

### Finding 6 - [MINOR / UNVERIFIED] Shield Charge gem price not reconcilable
Our response prices the Shield Charge gem (L20 / Q20 / non-corrupt, `index 22`) at **91.0c**. The
gem matcher (`gem_price`, nearest level -> quality -> corruption) against the **current** economy
picks `L20 Q0` (variant `20`) = **~2.0c** for that combo; no current Shield Charge line is near
91c (lines: L20=2.0, L20c=3.8, L20/23c=125.7, L21c=2.4, L21/20c=156.5, L1/20=40.0). 91c is a 45x
gap from the expected bucket.

Every other spot-checked gem reconciled within economy drift, and all 5 uniques matched exactly
(Maloney's 12, Vaal Caress 5, Bisco's Leash 2, Rumi's 15, Sorrow 1). This one is flagged
**[UNVERIFIED]**: because `fresh=1` cannot bypass the cache (Finding 4), I cannot re-price against
the economy snapshot the cached response actually used - the anomaly could be a since-removed
economy line, a transient spike, or a matcher quirk. **Recommend re-checking once a cache-bust
exists.**

---

## 3. What was verified CLEAN (no bug)

- **Item inventory 1:1** - all 12 gear, 5 flasks, 1 jewel present exactly once; no duplicates; the
  only dropped rows are the 2 Raise Spectre of Finding 1 (full 33-gem reconciliation closes).
- **Categories / rarities correct** - unique (Maloney's, Vaal Caress, Bisco's, 2 unique flasks),
  rare (8 + jewel), magic (3 flasks), gem, and the white Bone Bow correctly `normal`
  (method `none`, no misleading number - correct per contract).
- **Slots + weapon-swap flags** - `swap:true` exactly on Maloney's (Offhand2) and Bone Bow
  (Weapon2); Ring/Ring2 both labelled "Ring"; swap slot labels correct.
- **Sockets / links** match raw exactly on every stable item: Grim Coat 6L(6), Woe Ward 4L(4),
  Tempest Spell 3L(3), Storm Thirst 2L(3 sockets), Maloney's 1L... plus the `socket_filters
  links.min:6` correctly applied to Grim Coat's trade_query only.
- **Gem host attribution** correct on all 10 rows (`host_slot`/`host_name`/`host_inventory_id`
  match where each gem is socketed).
- **Active-vs-support taxonomy honest** - the second active skills sharing a link group
  (Creeping Frost of Floes, Pact of K'Tash, Frostblink, Elemental Weakness) are each flagged
  `support:false` with the correct `gem.activegem` trade category, and are priced + counted. Not
  mislabeled.
- **Granted flags** all `false`, correct - `itemProvidedGems` is empty, so no gem is item-granted.
- **Unique prices exact** (5/5) against live economy lines; **flask `utilityMods` handled** (Movement
  Speed / Suppress / Phasing appear as affixes; "Phasing" correctly greyed `searchable:false`).
- **Scopes correct** - `armour.helmet` / `weapon.wand` `[INFERRED by design]` / `armour.chest` /
  `accessory.ring` / `armour.shield` / `flask` / `jewel`, each with a valid exact-base alternative.
- **Affix explicit coverage complete** and searchable flags honest (unsearchable mods listed
  greyed with a reason).
- **Variant registry** - none of this build's uniques are in the 40-name registry; correctly
  **no** `variant` block appears on any row (nowhere it shouldn't).
- **Unpriced rows** all carry both `trade_url` and `trade_query`.
- **URL-variant robustness** - `?i=7` (the actual inputs.json form), trailing slash, `http://`,
  multi-junk query, and the raw `#`->`-` account form (`%23`) all parse to the same build.
- **Totals arithmetic** exact (float sum, no rounding/floor); `divine = chaos / 125.7` verified
  (1745.41 / 125.7 = 13.886).

---

## 4. Provenance
- Ground truth: `poe.ninja/poe1/api/builds/{version}/character` (live), `.../economy/stash/...`
  (SkillGem + Unique* overviews, live), `.../economy/exchange/...` (Currency, live).
- Contract: `docs/public-contract.md`; decisions D-0006/D-0016/D-0018/D-0019 in
  `docs/00-decision-log.md`.
- Code read (read-only): `public/api/build.py`, `public/api/_lib/{engine,poeninja,response,cache}.py`,
  `public/site/assets/core.js`, `public/api/_data/variant_uniques.json`.
- No pathofexile.com endpoint was contacted.
