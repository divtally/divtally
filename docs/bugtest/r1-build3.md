# R1 (API end-to-end) — build 3: ArleAllflame

**Round:** 1 of 5 (D-0020) · **Lens:** API end-to-end (parse / price / taxonomy / variants / errors)
**Build:** https://poe.ninja/poe1/builds/allflame/character/f1fti-6231/ArleAllflame
(Ascendant, L100, Allflame — 11 gear + 5 flasks + 16 jewels + 4 skill groups)
**API under test:** `GET https://divtally.vercel.app/api/build?url=…&fresh=1` (live, 2026-07-27/28)
**Verdict:** FAIL — 1 blocker, 2 major, 2 minor. High-value unique silently dropped; error paths
misclassified; linked-unique pricing ignores links.

Method: fetched the RAW poe.ninja character JSON + all economy overviews (Currency / SkillGem /
Unique{Weapon,Armour,Accessory,Flask,Jewel}) for league **Allflame** as ground truth, then
cross-examined the live API response field-by-field. Every finding below is API-response vs
poe.ninja-raw vs contract (`docs/public-contract.md`). No pathofexile.com calls. Scratch scripts +
captured JSON kept in the session scratchpad (AppData\Local\Temp — harness temp, NOT OneDrive, NOT
the project); no read/scan of `C:\Users\user` was performed.

---

## Findings

| # | Sev | One-liner |
|---|-----|-----------|
| 1 | **blocker** | Foil unique **Nimis** (`frameType:10`) misrouted to `category:normal` → no price, no trade link, no picker, out of totals. Total undercounts ~27% (~7,680c / ~61 div). |
| 2 | **major** | Bad-URL parse errors (build-overview link, PoE2 link, non-poe.ninja host) return **HTTP 502 `ninja_error`** instead of the contract's **400 `bad_input`** — falsely blames poe.ninja for a user link mistake. |
| 3 | **major** | Non-registry multi-line uniques ignore the item's **known link count** (and poe.ninja's per-line `links`): 6-link **Inpulsa's** priced `min 10 / median 81` (unlinked & 5L lines) when the 6L line is ~350c; wrong numbers flow into totals. |
| 4 | minor | Weapon-swap unique is counted in `api.totals`, `priced_items`, and `rares[]`, contradicting D-0018 ("swap … out of totals, scans, rares list" by default). Site recomputes client-side so end-users are unaffected; non-site API consumers are not. |
| 5 | minor | Co-socketed **active** auras (Precision, Vaal Haste; `support:false`) are nested as "supports" of Wrath because normalize treats `allGems[1:]` as supports regardless of the gem's own flag. Pricing is correct; the taxonomy/label is not. |

---

### 1 — BLOCKER · Foil unique (`frameType:10`) dropped from pricing entirely
**Item:** `items[1]` Nimis, Topaz Ring (inventoryId `Ring2`).

Raw poe.ninja: `frameType:10`, `frameTypeId:"SupporterFoil"`, **`rarity:"Unique"`**, name "Nimis",
4 explicit mods. poe.ninja lists it: **1 line, chaosValue 7680, divineValue 61.1, 29 listings**
(UniqueAccessory). It is a real, priceable, high-value unique — the 2nd most valuable item in the
build after Headhunter.

API row:
```json
{"name":"Nimis, Topaz Ring","category":"normal","rarity":"Unknown","slot":"Ring",
 "price":{"chaos":{"min":null,"median":null,"high":null},"method":"none","source":"none",
          "note":"normal item; not priced"},
 "trade_url":"","trade_query":null}
```
It is **absent from `rares`** (key `"1"` missing) → no affix picker either. So the user gets: no
price, no clickable trade link, no query, no manual-refine entry, and it's excluded from the totals.

**Impact / fingerprint:** `totals.priced_items (23) + unpriced_items (12) = 35`, but `items[] = 36`.
Nimis is the invisible 36th row. True median total should be ~28,310c; API reports 20,630c — a
**~27% undercount** on this build, plus a silently un-priceable item with zero recourse.

**Root cause:** `public/api/_lib/poeninja.py::_categorise` (L514-524) routes only `frameType` 1-4;
anything else (here 10) falls to `CAT_NORMAL`. `models.FRAME_RARITY` (L11) has no 9/10 and its
comment wrongly asserts *"PoE1: 9 = Relic (foil uniques reuse the unique frame + a foil flag)"* —
the live data disproves it: foil uniques use **`frameType:10` (SupporterFoil)** (and `9`=Relic),
NOT `frameType:3`+flag. The `itemData.rarity:"Unique"` signal is present but ignored. **Class bug:**
every foil / supporter-foil / relic unique (frameType 9 or 10) is dropped this way.

**Fix hint:** in `_categorise`, treat `frameType in (3, 9, 10)` as `CAT_UNIQUE` (and/or fall back to
`d.get("rarity") == "Unique"` when frameType ∉ 1-4); add 10→"Unique",? to `FRAME_RARITY`. **Same
bug in the local `bpc/poeninja.py::_categorise` (L301-311)** — fix both (vendored verbatim).

---

### 2 — MAJOR · URL parse errors return 502 `ninja_error`, contract says 400 `bad_input`
Probed the build's URL on error variants:

| input | HTTP | error_type | contract §4 says |
|---|---|---|---|
| build-overview link `…/builds/allflame` (no `/character/`) | **502** | `ninja_error` | **400 `bad_input`** ("a build-overview link") |
| PoE2 link `…/poe2/builds/…/character/…` | **502** | `ninja_error` | 400 `bad_input` (unrecognised URL) |
| empty `url=` | 400 | bad_input | 400 ✓ |
| `"not a url at all"` | 400 | bad_input | 400 ✓ |

The message TEXT is helpful ("that looks like a build overview link…"), but the **status + type are
wrong**: `502 ninja_error` means "poe.ninja was unreachable / returned no data" (a retriable
upstream failure). Here poe.ninja was never contacted — the user simply pasted the overview page or
a PoE2 link (both very common mistakes). A client showing "poe.ninja is down (502)" or auto-retrying
is misled, and uptime monitors will log false upstream 5xx.

**Root cause:** `poeninja.parse_build_url` raises `PoeNinjaError` for all bad-URL cases
(overview / wrong host / no `poe1` / no `builds`). `engine.run_estimate` lets it propagate; `build.py`
`_run` maps `EstimateError→400 bad_input` (L67) but `PoeNinjaError→502 ninja_error` (L69). Parse-time
URL problems are user `bad_input`, not upstream failures.

**Fix hint:** classify parse/URL-shape errors as 400 `bad_input` — e.g. have `prepare_from_url` catch
`parse_build_url`'s `PoeNinjaError` and re-raise `EstimateError`, or split "reachability" vs
"bad URL" so only genuine fetch failures return 502. Contract §4 already lists "a build-overview
link" under `bad_input`.

---

### 3 — MAJOR · Linked uniques mispriced: `unique_price` ignores the item's link count
**Item:** `items[5]` Inpulsa's Broken Heart, Sadist Garb — a **6-link** (verified: `max_link:6`,
socket_colours `WWGGWB`, and its `trade_query` correctly carries `socket_filters.links.min:6`).

poe.ninja lines for Inpulsa's (all base Sadist Garb): **6L → 350c**, 5L → 80.5c, unlinked → 10c.
API result:
```json
"method":"unique-ninja-range","confidence":"low","n_variants":3,
"chaos":{"min":10.0,"median":81.0,"high":291.8}
```
i.e. `min` = the **unlinked** 10c line and `median` = the **5-link** 80.5c line, for an item that is
a **6-link** whose own price line (350c) poe.ninja lists explicitly. These wrong per-item numbers are
summed into `totals.chaos.min/median` (`_sum_tier` includes every poe.ninja row).

The link count is **known** on the item and poe.ninja exposes a **`links` field on every line**
(I see `links:6/5/null`), yet `PoeNinjaEconomy.unique_price` filters only by `base_type` and never by
links, and `price_unique_ninja` never passes `item.max_link`. Contrast the same build's Atziri's
Disfavour (a 2-link 6-socket axe): ignoring links happens to give the right line there, so the effect
is item-dependent and silent.

Mitigations: it's flagged `confidence:"low"` with "verify via trade link", the `high` tier (291.8)
approaches the true 6L, and the trade link's links filter is correct — so it's not catastrophic. But
a 6L unique showing `median 81 / min 10` (≈¼ and 1/35 of its ~350c value) is a wrong price feeding
the headline totals, and the fix is cheap because the data is already present.

**Fix hint:** in `unique_price`, when the item's `max_link ≥ 5` prefer the poe.ninja line whose
`links` matches (fall back to the aggregate range only when no link-matched line exists); thread
`item.max_link` from `price_unique_ninja`. Same code in local `bpc/`. *(May be a known design
limitation — flagging because it produces materially wrong totals for linked uniques.)*

---

### 4 — MINOR · Weapon-swap unique counted in server totals / `priced_items` / `rares`
`items[8]` Atziri's Disfavour is `inventoryId:Weapon2` → correctly flagged `"swap":true`. But the
server: (a) includes its 251.4c in `totals.chaos` all tiers (`_sum_tier` has no swap filter),
(b) counts it in `priced_items:23`, and (c) emits a `rares["8"]` picker entry. D-0018 (Locked):
weapon-swap items are *"out of totals, scans, and the rares list unless the toggle re-includes them"*
**by default**.

Not user-visible on the site: `core.js::totals()` (L154) recomputes from `state.enabled`, and
`defaultOn` (L142) starts swap rows OFF, so the displayed total excludes the axe (recompute:
median 20,379 excl-swap vs 20,630 incl-swap). But the **documented API contract**'s `totals` /
`priced_items` / `rares` are swap-inclusive, so the extension and any third-party consumer inherit a
swap-inclusive total contrary to D-0018. Either exclude default-swap rows server-side in
`response.py` (`_sum_tier`, `_priced_ninja`, the `rares` loop) or document that server totals are
swap-inclusive and clients must re-derive.

---

### 5 — MINOR · Co-socketed active auras nested as "supports"
`items[33]` "Wrath" (Gloves 4-link) reports `supports:[Enlighten, Precision, Vaal Haste]` — but
Precision and Vaal Haste are **active** aura gems (`support:false` in the raw data, and echoed as
`support:false` in the per-gem breakdown), not supports of Wrath. Cause: `normalize` treats
`allGems[0]` as the active and **all of `allGems[1:]` as supports** regardless of each gem's own
`support` flag (poe.ninja groups every gem in one socket-item together). Pricing is unaffected (each
gem is priced once and summed; `total_chaos` matches). Only the taxonomy/label is off — a UI
rendering "supports" will mislabel two auras. Inherited verbatim from the parent; low priority.

---

## Verified CORRECT (did not fault)

- **Item inventory:** all 11 gear + 5 flasks + 16 jewels present exactly once, in build order;
  4 skill groups → 4 gem rows. No drops, no dupes (incl. the two duplicate *Hollow Goad* and two
  *Might of the Meek* — both kept). `count` = 1 everywhere (correct; nothing stacked). Only defect
  is Nimis's category (finding 1), not a drop from the array.
- **Sockets / links:** every equipment row's `max_link`, `total_sockets`, `socket_colours` matches
  the raw `sockets[]` exactly (Replica Voidwalker BRBB/2L, Inpulsa's WWGGWB/6L, Atziri's Disfavour
  BGWWBB 6-socket-2-link, Piscator's WWW/1L, …). 6L Inpulsa's `trade_query` carries `links.min:6`;
  <5-link items carry none. Correct.
- **Categories / slots / swap flag:** all correct except finding 1. Weapon2→`swap:true`,
  Weapon/Ring/Amulet/etc. slot labels right; magic Diamond flask → `category:magic`.
- **Gems:** actives + all supports present; `granted:false` on every gem (correct — this build has
  `itemProvidedGems:[]` and no built-in supports); host attribution correct (Body Armour/Inpulsa's,
  Gloves/Soul Ascension, Off-hand/Foulborn Esh's Mirror, Helmet/The Fledgling); invariant
  `total_chaos == Σ gem.chaos` holds for all 4 groups.
- **Flasks:** all 5 present in belt order (Dying Sun, magic Diamond, The Wise Oak, Atziri's Promise,
  Cinderswallow Urn). Unique flasks priced by name; magic flask carries a category-scoped query.
- **Variant blocks (D-0019):** present on exactly the two registry uniques (Forbidden Flame `[16]`,
  Forbidden Flesh `[18]`) and **nowhere else** (Might of the Meek, Unnatural Instinct, the rare
  cluster/abyss jewels correctly have none). Labels truthful: both `"Slayer"` matching each jewel's
  own "Allocates Slayer …" mod; `locked_stats` option 43195 pinned into the query; method
  `unique-ninja-floor` / `confidence:"low"` per contract. (No timeless jewel in this build, so the
  seed+conqueror label path wasn't exercised.)
- **Unpriced rows:** every rare/magic/unique row carries a non-empty `trade_url` + `trade_query`
  (only Nimis lacks them — finding 1).
- **Price spot-checks (≥5) vs raw poe.ninja lines:** Headhunter 15210 ✓, Ashes of the Stars 321.4 ✓,
  Dying Sun 3017 ✓, The Taming 14.0 ✓ (exact). A few rows (Unnatural Instinct 359.1↔370, Forbidden
  Flame/Flesh floors, Atziri's Disfavour priced as a clean 1-line point) differ ~3-13% from my fresh
  fetch — **confirmed to be the server's 30-min economy cache**, not a bug: a repeat API call minutes
  later moved the total 20,630→20,880 as poe.ninja ticked. Names/bases/variant match; values within
  snapshot tolerance.
- **Totals arithmetic:** `totals.chaos.{min,median,high}` = exact Σ of all poe.ninja rows' tiers
  (verified to 1e-6); `divine = chaos / 125.7` exact; `priced_items 23`, `unpriced_items 12`,
  `divine_to_chaos 125.7`, `rates{}` all match the fresh Currency overview. (Values are raw floats
  with FP noise, e.g. 20557.699999999997 — cosmetic; site formats for display.) Only arithmetic issue
  is the swap inclusion (finding 4).
- **Affixes payload (rares):** complete and honest — every explicit line present; cluster-jewel
  ENCHANTS captured as a separate `(enchant)` group ("Adds 5 Passive Skills", etc.); the one
  unsearchable enchant ("1 Added Passive Skill is a Jewel Socket") correctly `searchable:false` +
  `reason`; `default_min`/priority tiers populated. `scopes` sane (jewels→`jewel`/"Any Jewel" with
  base alt; flask→`flask`).
- **URL-variant robustness:** `&i=junk`, `?i=junk` on the poe.ninja URL, trailing slash, `http://`
  scheme, and all combined → all HTTP 200, identical character + 36 items. Robust.

---

## Artifacts (session scratchpad, not committed)
`api.json` (live response), `char.json` (raw poe.ninja ground truth), `econ.json` (6 economy
overviews), `resolve.json` (index-state), `fetch.py` / `an1-3.py` / `probe_errs.py`.
Snapshot version at audit time: `0407-20260728-09123`, snapshotName `allflame`, league `Allflame`.
