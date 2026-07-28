# Round 1 bug test - Build 2 (API end-to-end)

**Build:** `https://poe.ninja/poe1/builds/allflame/character/Sergohero-2699/SergoheroGaz`
**Character:** SergoheroGaz (Sergohero-2699), Deadeye L100, Allflame. Kinetic Blast / wander.
**Date:** 2026-07-27. **Lens:** D-0020 Round 1 - API end-to-end (parse / price / taxonomy / variants / error paths).
**Method:** fetched the RAW poe.ninja character JSON (ground truth, index-state -> `/api/builds/{version}/character`)
and the RAW poe.ninja economy overviews (UniqueWeapon/Armour/Accessory/Flask/Jewel + SkillGem), then compared
against `GET https://divtally.vercel.app/api/build?url=...&fresh=1` field by field. No pathofexile.com calls.

**Verdict:** the pipeline is fundamentally sound - 29 rows, nothing dropped or duplicated, totals arithmetic
exact to the cent, and ~18 spot-checked prices match poe.ninja exactly. But there are **3 MAJOR + 3 MINOR real
bugs**. Detail + evidence below.

---

## Inventory reconciliation (PASS)
Raw: 12 gear + 5 flasks + 7 jewels + 5 skill groups = **29**. Our `items[]` = **29**, by (group,category):
equipment 11 unique + 1 magic; flask 3 unique + 2 magic; jewel 6 rare + 1 unique; gem 5. Every raw item is
present exactly once; none dropped, none duplicated. `rares{}` keys = exactly the 24 rare/unique/magic indices
(gems absent), no missing/extra. Weapon-swap flags correct (`swap:true` on Weapon2 Thicket Bow [idx 2] and
Offhand2 Maloney's [idx 8]). Sockets/links/colours faithful to raw (6L Inpulsa `{0:6}`, 2L bow, 1L gloves; the
all-white socket rows are real in the raw `sColour`). Flasks present in belt order; jewels all present. Host-item
gem attribution correct. `granted` all false (raw `itemProvidedGems` is empty - no false GRANTED, the D-0006 bug
stays fixed). Totals arithmetic exact: sum of the 20 ninja `min` tiers = 29393.8 to the cent; median/high exact
including the Inpulsa range; divine = chaos/125.7 rounded to 3dp (Headhunter 15210 -> 121.002, etc.).

**Price spot-checks vs raw poe.ninja economy (all EXACT):** Headhunter 15210, Nimis 7680, Ashes of the Stars
321.4, Death Rush 31, Dying Sun 3017, Cinderswallow 202, Wine of the Prophet 2011, Soul Ascension 60, The
Fledgling 25, Maloney's 12, Piscator's 1.0, Esh's Mirror 2.7; gems Kinetic Blast 30 / Greater Fork 228.4 /
Ele-Dmg-w-Attacks 44.1 / Volatility 45.6 / Trinity 31 / GMP(20/20c) 16.2, Haste 9.6, Precision 9.0, Wrath 4.0 -
every one matches its exact ninja line (name+variant+links). (Replica Voidwalker 5.0 vs live 4.8 and Lethal Pride
79 vs live 60.5 are live-economy ticks between the two fetches - single-line, mechanism correct, not defects.)

**Lethal Pride variant block is truthful:** class `seed-jewel`, label "Rakiata seed 13032", locked stat
`explicit.pseudo_timeless_jewel_rakiata` min==max==13032. Raw mod = "Commanded leadership over 13032 warriors
under Rakiata"; raw `mods.explicit` seed=13032. The stat id is a REAL trade id (present in the bundled
`trade_stats.json` Explicit group with the exact "# warriors under Rakiata" text). Variant block appears ONLY on
Lethal Pride (the sole registry item in this build) - nowhere else. Error paths `?i=junk`, trailing slash, and
`http://` all resolve end-to-end (200, same 29-item build).

---

## MAJOR findings

### M1 - Link-split uniques are priced as a vague range; the 6-link line is never selected (underprices)
**Where:** `public/api/_lib/poeninja.py` `PoeNinjaEconomy.unique_price` / `_load_uniques` (they store the full
line but never read `ln["links"]`).
**Item:** Inpulsa's Broken Heart, Sadist Garb (idx 7), a **6-link** (raw sockets group `{0:6}`, our row shows
`max_link:6`).
**Evidence:** poe.ninja splits this name into three lines by link count -
`links=6 -> 344.5c`, `links=5 -> 81c`, `links=None (unlinked) -> 10c`. `unique_price` disambiguates variants only
by `variant` TEXT tokens (all `None` here), so it falls to the `matched:"range"` branch and returns
`min=10 / median=81 / high=291.8`, `method:"unique-ninja-range"`. The item's link count (6) and poe.ninja's own
`links=6` line are both available and both ignored.
**Impact:** a 6-link Inpulsa's whose real poe.ninja value is **344.5c** is reported with **high = 291.8c (below
the true 6L)** and **median = 81c (the 5-LINK price)**; the reported **min = 10c is a price a 6L never sells for**.
Feeds understated totals (this one item contributes 10/81/291.8 instead of ~344.5). Systemic: hits every unique
poe.ninja splits by link count - i.e. most 5L/6L chest and weapon uniques - so the class of affected builds is
large. The trade link carries a `links.min` filter (correct), but the SERVER-SHOWN number and the totals are wrong.
**Fix sketch:** when a name's ninja lines differ by `links` and the item's `max_link` is known, select the line
whose `links` matches (or the highest `links <= max_link`), instead of collapsing to a text-variant range.

### M2 - URL-parse failures return HTTP 502 `ninja_error` instead of 400 `bad_input` (contract sec 4)
**Where:** `public/api/build.py` `_run` exception ordering (lines ~64-73) + `_lib/poeninja.py` `parse_build_url`
(raises `PoeNinjaError`, not `EstimateError`); `engine.prepare_from_url` calls it un-wrapped.
**Evidence (live):** a build-overview link `https://poe.ninja/poe1/builds/allflame` -> **502
`{"error_type":"ninja_error"}`**; `HTTP://poe.ninja/.../SergoheroGaz` -> **502 `ninja_error`**. The contract sec 4
lists exactly these under **`bad_input` (400)**: "unrecognised URL/code, a build-overview link, an unsupported
paste host, or missing input". `ninja_error` (502) is documented as "poe.ninja was unreachable / returned no data
/ the character is private". So every malformed / overview / wrong-host / PoE2 / empty URL is mis-reported as an
upstream failure.
**Impact:** the human-readable `error` message is still the correct guidance, but the machine-readable
`error_type` and the HTTP status are wrong. A consumer that branches on `error_type` tells the user "poe.ninja is
down, try again later" when the input is simply bad (and a build-OVERVIEW link is the single most common user
mistake - they copy the wrong URL). Wrong 502s also skew CDN/monitoring/retry logic. Clean, systematic contract
violation.
**Fix sketch:** either catch `PoeNinjaError` from the parse step and re-raise as `EstimateError`, or in
`build.py` classify parse-origin errors as `bad_input`/400. (A genuine parse error is client-side, never upstream.)

### M3 - Implicit mods are dropped from the affix picker (`rares[].affixes`), hiding searchable mods (D-0015)
**Where:** `public/api/_lib/querybuild.py` `PublicPricer.affix_options` iterates only `item.explicit_mods`;
`item.implicit_mods` are never emitted as picker rows (and so also never enter the default rare query).
**Evidence:** Kraken Star, Crimson Jewel (idx 18, rare) - raw implicits
`["Corrupted Blood cannot be inflicted on you", "21% reduced Effect of Shock on you"]`. The item row's
`mods.implicit` carries both, but its `rares["18"].affixes` list has only the 3 EXPLICITS. "Corrupted Blood cannot
be inflicted on you" is a **searchable, price-defining corrupted implicit** (StatMapper resolves it to
`explicit.stat_1658498488` / `implicit.stat_1658498488`) that players specifically search for - it is simply
absent from the picker (not even greyed). 8 of the 24 pickered items drop implicits this way (most are low-value
base implicits on uniques; Kraken Star's corrupted implicit is the price-relevant casualty).
**Impact:** violates the owner-championed D-0015 promise that the picker shows *every* affix ("the user sees
everything and the tool hides nothing") - the user cannot add a real, searchable price-driver to the search, and
the default rare query can't include it either.
**Fix sketch:** enumerate `item.implicit_mods` in `affix_options` too (group `"implicit"`, matched via
`mapper.match(text, group="implicit")`), listed like any other affix (greyed when unsearchable).

---

## MINOR findings

### m4 - A second active skill sharing a socket group is mislabeled as a support of the first
**Where:** `public/api/_lib/poeninja.py` `normalize` - assumes `skills[].allGems[0]` is the sole active and
`allGems[1:]` are supports.
**Evidence:** poe.ninja returns Haste + Wrath (both `support:false` active auras socketed together in Esh's
Mirror) as ONE `allGems` group. Our row 27 (Haste) gets `supports:[{name:"Wrath", support:false, ...}]` and there
is **no standalone Wrath row**. Wrath's price IS preserved (4.0c, counted inside Haste's `total_chaos`=13.6, exact
vs the ninja "Wrath 20c" line), so no total impact - but the taxonomy is wrong: an active aura is presented as a
"support" (a `supports[]` entry with `support:false`), and the UI would show "Haste + 1 support" where the
"support" is another aura. Common pattern (multiple auras/heralds share one item's sockets).
**Impact:** presentational/structural only; price + totals correct. Fix: when a group has >1 `support:false` gem,
emit each as its own active row (or otherwise flag co-actives), rather than nesting them under `allGems[0]`.

### m5 - Weapon-swap unique is counted in the API `totals` / `priced_items` (contra D-0018 default)
**Where:** `public/api/_lib/response.py` `_sum_tier` / `_priced_ninja` sum every `source=="poe.ninja"` row with
no `swap` check.
**Evidence:** Maloney's Mechanism (idx 8, `swap:true`, 12c) is included in `totals.chaos`
(min/median/high) and in `priced_items:20`. D-0018 says swap items are "out of totals ... by default". The
first-party site recomputes totals client-side and EXCLUDES swap by default (`core.js` `defaultOn` =
`!granted && !(swap && !includeSwap())`), so the site's headline total is 12c lower and shows 19 priced - i.e. the
API `totals`/`priced_items` disagree with the site's own default AND with D-0018.
**Impact:** magnitude tiny (12c / 0.04%), and the main UI is unaffected because it recomputes; but any consumer
that trusts the API `totals`/`priced_items` (the extension, third-party scripts) gets swap-inflated numbers, and
the contract sec 2.2 doesn't document swap treatment. Fix: exclude `swap` rows from the server totals/priced count
by default (or document that `totals` includes swaps and the client must re-filter).

### m6 - Uppercase URL scheme (`HTTP://`) is rejected
**Where:** `public/api/_lib/poeninja.py` `parse_build_url` line ~61 - case-sensitive `u.startswith("http")`.
**Evidence:** `HTTP://poe.ninja/poe1/builds/allflame/character/Sergohero-2699/SergoheroGaz` -> `PoeNinjaError:
not a poe.ninja link: 'HTTP:'`. Because the string does not start with lowercase `http`, the code prepends
`https://` to an already-schemed URL, producing `https://HTTP://...` (netloc becomes `HTTP:`). URI schemes are
case-insensitive (RFC 3986) and `urlparse` handles them fine; only this manual guard doesn't. (Compounds with M2:
end-to-end it surfaces as a 502 `ninja_error`.)
**Impact:** uncommon input, but a real robustness gap. Fix: lowercase-compare the scheme (`u.lower().startswith
("http")`) or test `"://" in u`.

---

## Checklist coverage
parse (URL variants) PASS (except m6) . items present-once/counts PASS . slots/groups/categories PASS .
swap flags PASS . sockets/links/colours PASS . gems actives+supports (m4) / granted PASS / host PASS .
flasks belt order PASS . jewels all present PASS . variant blocks only-where-registry PASS + labels truthful PASS .
every unpriced row has trade_url+trade_query PASS . ninja price spot-checks PASS . totals arithmetic PASS (swap
caveat m5) . scopes PASS . rare affixes completeness (M3 implicit gap) . error paths ?i=/slash/http PASS,
uppercase (m6) + error-type (M2).
