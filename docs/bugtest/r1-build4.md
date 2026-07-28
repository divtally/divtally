# R1 / Build 4 — API end-to-end audit (owner test build)

**Round:** 1 (API end-to-end), per D-0020.
**Build:** `https://poe.ninja/poe1/builds/allflame/character/yalokk-2571/TimeForAurab`
(Champion, L100, Allflame — 12 gear, 5 flasks, 7 jewels, 7 skill groups).
**API:** `GET https://divtally.vercel.app/api/build?url=…&fresh=1` (HTTP 200, ok=true, schema 1.0).
**Method:** raw poe.ninja character JSON + poe.ninja economy overviews (Currency / SkillGem /
Unique* — the **primary-source ground truth**) cross-examined against our API document, plus the
relevant `public/api/_lib/*.py` code and `docs/public-contract.md` §2–5.
**Provenance:** every price/line below is **[poe.ninja LIVE]** (primary API); arithmetic is
**[DERIVED]** by me from those lines. No web/wiki claims used.

**Verdict: FAIL** — 4 MAJOR + 2 MINOR. The happy path works (gems, name-matched uniques, links,
counts, taxonomy all verified correct), but two unique-pricing paths (abyssal-socket count,
link-split variants) produce wrong/missing prices, the server `totals` include weapon-swap gear
against D-0018, and parse-level bad-URL errors are misclassified.

---

## MAJOR findings

### M1 — Weapon-swap items are summed into server `totals` and `priced_items` (violates D-0018)
**Where:** `public/api/_lib/response.py` `_sum_tier` (L100-110) and `_priced_ninja` (L113-121) —
neither filters `it.raw.inventoryId in (Weapon2, Offhand2)` / the `swap` flag.

**Evidence [DERIVED from the payload]:** reproducing `totals.chaos` two ways —
| | min | median | high |
|---|---|---|---|
| **API reported** | 2046.5 | 2083.5 | 2220.3 |
| recompute **incl. swaps** | 2046.5 | 2083.5 | 2220.3 ✅ exact |
| recompute **excl. swaps** (correct default) | 2033.5 | 2065.5 | 2135.1 |

The two swap items — **Silverbranch** (Weapon2, range 1/6/73.2) and **Replica Maloney's
Mechanism** (Offhand2, 12/12/12) — are both `swap:true` in the payload yet both land in the sum.
`priced_items` = 19 likewise counts them (should be 17).

**Why it's a bug:** D-0018 (Locked) — *"Weapon-swap items excluded by default … out of totals,
scans."* The reference site works around it client-side (`public/site/assets/core.js:570`
`if (it.swap && !includeSwap()) return false;` inside `totals()`), so the **site** is correct —
but the documented API `totals`/`priced_items` (contract §2.2) are what any direct consumer (the
extension, a userscript, a third party) reads, and they are inflated by swap gear. The swap flag
is plumbed everywhere *except* the server totals. Impact here: +18c median, +85c high, +2 items.

**Fix:** skip `swap` rows in `_sum_tier` + `_priced_ninja` (default), matching core.js.

---

### M2 — A unique with exactly **1 abyssal socket** is left UNPRICED with an empty defining filter and a placeholder label
**Item:** Bubonic Trail, Murder Boots (index 3). Sockets `[W, R, R, A]` → **1 abyssal socket**.
**API:** `price.method = unique-unpriced`, `source = none`, no chaos number;
`variant = {class:"socket-defined", label:"count variant", locked_stats:[]}`.
**Ground truth [poe.ninja LIVE, UniqueArmour]:** Bubonic Trail has 2 lines —
`"1 Jewel" → 1.0c (2564 listings)`, `"2 Jewels" → 10.0c (166)`. This copy is the **1-socket**
variant and is fully priceable.

**Root cause (proven):** the socket-defined matcher (`variantreg.py` L237-258) scans
`item.explicit_mods` for the registry's defining pattern `"Has # Abyssal Sockets"`
(stat `explicit.stat_3527617737`). The game renders the **singular** `"Has 1 Abyssal Socket"`
when the count is 1, and the StatMapper cannot match the singular form:

```
StatMapper.match("Has 1 Abyssal Socket")   -> None            # FAILS
StatMapper.match("Has 2 Abyssal Sockets")  -> stat_3527617737 # ok
StatMapper.match("Has 1 Abyssal Sockets")  -> stat_3527617737 # ok  (only the singular word breaks it)
```
So `found` never sets → `owned_count = None` → `build_variant` yields `filters=[]`,
`locked_stats=[]`, `label="count variant"` (the empty-parts fallback, L258). Then
`unique_price(strategy="map-count", owned_count=None)` → `_match_count_line` returns None →
`_registry_price` returns None → the item is unpriced.

**Three defects in one:**
1. **Dropped price** — should `map-count` to the `"1 Jewel"` line (1c). (Trivial here, but the
   same failure hits **Shroud of the Lightless / Lightless Gate / Command of the Pit /
   Darkness Enthroned** etc., where the 1-socket variant is a real, non-trivial item.)
2. **Broken trade query (violates D-0019)** — `locked_stats=[]` → the emitted `trade_query`
   carries **no** abyssal-socket-count filter, so the Bubonic Trail trade link matches *any*
   socket count. D-0019: registry items get *REQUIRED* defining-mod filters.
3. **Untruthful label (violates contract §2.8)** — `"count variant"` is a placeholder, not
   "a concise, deterministic description built from the copy alone" (should be e.g. "1 Abyssal
   Socket").

**Fix:** derive the abyssal count from the `sockets` array (`sum(s.attr=='A')`, already reliably
present — the registry's own note says *"Read the copy's abyssal socket count"*) instead of
parsing the plural-only mod text; or normalise singular/plural in the statmap. Counting sockets
also fixes the label and the locked filter.

---

### M3 — poe.ninja `links` field is ignored in unique variant selection → link-split uniques mispriced as a range
**Where:** `public/api/_lib/poeninja.py` `unique_price` (L393-415) disambiguates multi-line
uniques **only** by `variant`-string tokens; it never reads a line's `links` field, and never
uses the item's known `max_link`. Lines whose only differentiator is `links` all have
`variant = None`, so token cover = 0 → the code falls through to the `unique-ninja-range` branch.

**Evidence [poe.ninja LIVE, ground truth vs API]:**

*Victario's Influence (index 0) — item is a **5-link** (`max_link=5`), and it IS in the default total:*
| poe.ninja line | chaos | listings |
|---|---|---|
| links=None | 1.0 | 2428 |
| **links=5** | **28.5** | 18 |
| links=6 | 120.0 | 11 |

API returns `unique-ninja-range` **min=1 / median=33 / high=102.6** (confidence low). The **min
(1c) is the *unlinked* Victario's — a different item** than the player's 5-link corrupted copy;
the high (~102.6) tracks the 6L (120c) line. poe.ninja literally publishes a `links=5 → 28.5c`
line for exactly this item, but it is never selected. (median 33 ≈ the 5L line at the API's
snapshot — but that alignment is coincidental, being the middle of 3 sorted values.)

*Silverbranch (index 4) — item is a **3-link** (`max_link=3`):*
poe.ninja: base=1.0c, links=5=6.0c, links=6=86.0c. API returns range **1 / 6 / 73.2** — the
**median (6c) is the 5-LINK price applied to a 3-link item** (~6× over the correct base line of
1c). (Silverbranch is a swap, so M1 also wrongly folds this into totals.)

**Why it's a bug:** links are a first-class price component in this project (D-0002/D-0003 added
`max_link` to the model precisely for pricing). For link-split uniques the variant is *knowable*
(item `max_link` + line `links`), so degrading to a wide low-confidence range — whose endpoints
are the prices of *different link tiers* — is an avoidable mispricing that misrepresents the
owned item. It affects Victario's, which is in the (correct, swap-excluded) total's min/high.
Operates within the contract's documented range-fallback, so it's an accuracy defect rather than
a schema breach — but the numbers shown are wrong for the specific item.

**Fix:** when ninja lines carry `links`, bucket the item by `max_link` (<5 / 5 / 6) and select the
matching line (point price + real confidence) before falling back to a range.

---

### M4 — Build-overview / unrecognised URLs return `502 ninja_error` instead of `400 bad_input` (violates contract §4)
**Where:** `public/api/build.py` L69-70 maps **any** `PoeNinjaError` to `502 ninja_error`. But
`poeninja.parse_build_url` raises `PoeNinjaError` for *parse-level* input mistakes — a
build-overview link (no `/character/`), a non-poe.ninja host, a PoE2 link, a missing `/builds/`.

**Evidence [error-path probe]:**
```
url = https://poe.ninja/poe1/builds/allflame          (overview, no character)
  -> HTTP 502  error_type="ninja_error"
     error="that looks like a build *overview* link, not a specific character. Open a character…"
```
Contract §4 is explicit: **`bad_input` (400)** = *"unrecognised URL/code, **a build-overview
link**, an unsupported paste host, or missing input."* `ninja_error` (502) is reserved for
*"poe.ninja was unreachable / … character is private."* The message body is itself a bad-input
message, wrapped in the wrong (502/ninja_error) envelope. No network call even occurs — the parse
fails first.

**Why it's a bug:** a client following the documented taxonomy treats the user's most common
mistake (pasting an overview link) as a transient upstream outage — 5xx is retryable, so retry
logic hammers a permanently-bad URL, and monitoring records phantom "poe.ninja down" events. The
human message is correct; the `error_type` **field** and HTTP **status** are wrong for an entire
input class.

**Fix:** catch `parse_build_url`'s parse failures as `bad_input` (400) — either a distinct
exception type or a bad-input branch — reserving `ninja_error` for actual fetch failures.

---

## MINOR findings

### m1 — Abyss-jewel slot label leaks the raw `inventoryId` "EquipmentJewels"
Ulaman's Gaze (index 23), an abyss jewel socketed in Bubonic Trail's abyssal socket, has
`slot = "EquipmentJewels"`. `_INVENTORY_NAMES` (`poeninja.py` L27-32) maps `PassiveJewels→"Jewel"`
but has no `EquipmentJewels` entry, so `_slot_name` returns the raw id. Cosmetic; should be
"Jewel" / "Abyss Jewel". (All other slots map correctly.)

### m2 — Raw `#` account form is truncated by URL-fragment parsing; the dash-encode safety net never fires
`…/character/yalokk#2571/TimeForAurab` → `urlparse` treats `#2571/TimeForAurab` as the **fragment**,
leaving path `…/character/yalokk` (5 parts) → parses as an overview link → same misleading
`502 ninja_error` "overview link" message (see M4). Research §8 says to *"run the account through
the #→- encoder anyway to be safe against a hand-typed #,"* but `dash_account` runs on
`parts[bi+3]` **after** `urlparse` has already discarded everything past `#`, so it can't help.
Edge case (real poe.ninja URLs always use the dash form; only a hand-typed `#` triggers it), but
the guidance in the research note is not actually effective for a `#` in the raw URL.

---

## Verified CORRECT (checked, no defect)

- **Item coverage / counts:** 31 rows = 12 equipment + 5 flask + 7 jewel + 7 gem, reconciling
  exactly to raw `items`(12) + `flasks`(5) + `jewels`(7) + `skills`(7). **None dropped, none
  duplicated;** every `count=1` (the 3 Small Cluster Jewels are 3 distinct rows, not merged).
- **Categories/rarity** (frameType → unique/rare/magic/gem) all correct; **swap flags** correctly
  set only on Silverbranch (Weapon2) + Replica Maloney's (Offhand2).
- **Sockets/links:** `max_link` / `total_sockets` / `socket_colours` match the raw `sockets`
  groups on **all 12** items (5L Victario's, 3L 6-socket Silverbranch, the `A` abyssal colour on
  Bubonic Trail, etc.). Victario's 5-link correctly adds `socket_filters.links.min=5` to its
  `trade_query` (D-0003).
- **Gems:** all 7 groups present with correct host-item attribution; the only item-provided gem
  (**Generosity Support**, from `itemProvidedGems` on the body armour) is correctly `granted:true`,
  `chaos:null`, and excluded from its group total — every group's `total_chaos` = Σ non-null gem
  chaos (verified). **5+ gem price spot-checks vs [poe.ninja LIVE] SkillGem — all exact:** Anger
  21c=34.7, Wrath 21c=65.4, Enlighten 3c=460.0 / 2c=288.6, Determination 21c=78.0, Purity of Fire
  21/20c=377.1, Vaal Haste 20c=44.5, Purity of Ice 21c=39.0, Clarity→20 bucket=6.4.
- **Name-matched unique prices vs [poe.ninja LIVE]:** all exact — Hand of Phrecia 2, Ventor's 2,
  Alpha's Howl 2, Voideye 1, Jinxed Juju 3, Dark Seer 15, Ulaman's Gaze 2, Replica Maloney's 12,
  Foulborn Matua Tupuna 9 (variant "Aura Level"). `divine_to_chaos=125.7` matches the Divine line.
- **Watcher's Eye variant (roll-defined):** `label="affected by Determination, Grace, Purity of
  Ice"` is **truthful to the item's own mods** (the copy genuinely carries all three "while
  affected by …" lines) — correctly derived from the copy, not from the build's active auras
  (the build does *not* run Grace), per §2.8. All three aura mods captured in `locked_stats` and
  flagged `defining:true` in `rares[].affixes`; the 3 generic ES/Life/Mana mods present and not
  defining.
- **Variant blocks appear on exactly the 2 registry uniques** (Bubonic Trail, Watcher's Eye) and
  nowhere else — correct placement.
- **Rare affix payload complete:** Golem Trap belt lists all 7 explicit-style mods (5 explicit + 2
  crafted `+264 Armour` / `+24 ES`), every `searchable:true` with a real `stat_id`; `trade_query`
  carries 7 stat filters. (Base implicit `+40 Life` is shown in the row's `mods.implicit` but not
  in the affix picker — expected; base implicits aren't search affixes.)
- **Scopes sane:** flask→`flask`, cluster jewel→`jewel`, belt→`accessory.belt`, all with correct
  base alternatives.
- **Every row carries both `trade_url` and `trade_query`** (including the unpriced Bubonic Trail
  and all flasks/jewels).
- **Error paths:** `?i=…` junk on the inner URL, a trailing slash, and an `http://` scheme all
  correctly resolve to the same build (31 items) — only the two error-classification issues above.

## Notes / non-findings
- **Watcher's Eye 59.9c vs [poe.ninja LIVE] 50.0c:** not a logic bug — the floor logic (min line)
  is correct, and the registry's harvested floor (50.0) matches my live fetch. The API ran on an
  older char snapshot (its `cache_key` version `0332-…` vs my `0407-…`) and the economy overview
  is server-cached 1800s (`poeninja.py` L333), so its live floor line was 59.9 at that moment.
  All other unique prices matched to the cent, so this is snapshot skew, not a defect.
  (`&fresh=1` only busts the CDN key — build.py doesn't read it — so server-side econ cache still
  applied.)
- **Gem group with 4 active auras under one name** (index 24 "Anger" holds Anger/Precision/Wrath/
  Vaal Haste + Enlighten + Generosity, all in Victario's 6-socket): faithful to poe.ninja's own
  `skills[]` grouping (host-item grouping, D-0006); pricing is correct. Cosmetic naming only.
