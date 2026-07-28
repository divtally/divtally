# D-0020 Round 3 (LIVE) - query-truth verification against the real trade API

**Round:** 3 (LIVE half) of the D-0020 five-round campaign. Executes the 12-query LIVE SAMPLE from
`docs/bugtest/r3-derivation.md` sec 4 against the **real** `www.pathofexile.com/api/trade` search,
plus targeted controls to resolve the derivation's open live questions (F1 400-vs-drop, F4
name-form). **Question answered:** does every search we generate actually describe its item, and can
a real listing returned satisfy it?
**Date:** 2026-07-28. **League:** `Allflame` (live, tradeable). **Auditor:** the sole live-trade
agent for this phase. **Repo files touched:** only this file. Working scripts + raw captures live in
`scratchpad/` (not repo): `gen_r3_queries.py`, `r3_live_driver.py`/`_batch2`/`_batch3`,
`r3_queries.json`, `r3_live_results*.json`, `r3_live_log*.txt`.

Every query POSTed is the **exact** `trade_query.query` the real engine emits
(`public/api/_lib/engine.run_estimate(url, status="available")` -> `response.build_response`), sent
verbatim the way production does it (site requests `/api/build?...&status=available` -> server bakes
`status.option:"available"` into each query -> extension `background.js` POSTs
`{query, sort:{price:"asc"}}` unaltered). All numbers below are **source-derived** from live API
responses unless tagged `[DERIVED]`.

---

## 0. Verdict (read first)

The 12 generated queries are, with **one** exception, **TRUE**: every category, stat id, option,
exact-seed, abyssal-count, 85%-armour, 6-link and weapon-subcategory filter is live-valid and
**honoured** by the API, and **every listing returned matched the item it was searched for** (no
listing "lied"). Status `available` is accepted on 24/24 searches (D-0017 holds live).

The one exception is a **BLOCKER** and it is the derivation's F4 (previously only "verify-live"):
the Allflame **"Foulborn <unique>"** league-prefixed name is **rejected with HTTP 400 "Unknown item
name"**, breaking the whole search (and the item's trade link) for every Foulborn-decorated unique.

Two derivation MAJORs are **corrected by live evidence**: **F1** (piped option ids) does **NOT**
400 or silently drop - the live API **parses `base|opt` identically to the canonical split form**,
so those queries are functionally correct today; **F2** (dropped jewel socket) has **no demonstrable
live price impact** on these builds (its one item 0-matches with or without the socket, by the D-0015
strict default).

| ID | Sev (live) | Finding | Evidence |
|---|---|---|---|
| **L1** (=F4) | **BLOCKER** | `name:"Foulborn Esh's Mirror"` -> **HTTP 400 "Unknown item name"**; the correct search is the BASE name `"Esh's Mirror"` (-> 200, 990 listings, all "Foulborn Esh's Mirror" shields). Every "Foulborn <unique>" query 400s -> dead trade link + failed client scan. | S12 primary 400; `F4_esh_basename` 200/990. Blast radius on these builds: Foulborn Esh's Mirror (b3), Foulborn Matua Tupuna (b4). Task rule: "400 = blocker." |
| **L2** (=F1) | minor (was MAJOR) | Verbatim piped `enchant.stat_X\|opt` is **accepted and HONOURED** live (== the split `{id,value.option}` form), not 400'd/dropped. Residual: relying on an undocumented alt form is latent fragility - emit the split form as hardening, but **no query is broken today**. | Bare A(piped)=**4598** ~= B(split)=**4599**, both << C(all jewels)=**10000+**. Entropy Idol (S2) piped query returned the correct amulet. |
| **L3** (=F2) | minor | The dropped singular "1 ... is a Jewel Socket" is a real query-completeness gap, but its "over-broad / price-low" effect is **masked** on these builds: Pandemonium 0-matches with piped, piped-removed AND fully-fixed(+socket) alike. Socket filter is wire-valid (200). | S1 all three variants total=0. `enchant.stat_4079888060 {min:1}` accepted. |
| - | obs (D-0015) | Three strict rares (Pandemonium, Grim Coat, Storm Thirst) 0-match live, but their **scopes are honest** (relaxed scope matches 191 chests / 10000+ wands / the item's own mods) - the 0 is the known strict all-affix default (R2), not a query-truth defect. | S3 scope=191, S4 scope=10000+, S1 filters all valid. |

**No listing returned ever failed to match its query** - the only "the query lies" case is L1, where
the query is rejected outright rather than returning a wrong item.

---

## 1. Budget & rate-limit ledger (hard rule compliance)

| Metric | Value |
|---|---|
| Search POSTs used | **24 / 30** (12 primary + 12 controls) |
| Fetch GETs used | **12** (top-3/top-1 of items with listings) |
| 429s | **0** |
| Aborts / back-offs | **0** |
| Min spacing enforced | **3.5 s** between ANY two requests (task floor 3 s) |
| User-Agent | `buildpricechecker-poe1/0.1 (... contact: divtally@gmail.com)` (descriptive, real contact) |
| Canary | Headhunter first -> 200/69 before any budget spent |

**Live rate rules observed** (every response logged verbatim in `scratchpad/r3_live_log*.txt`):
- Search `trade-search-request-limit`: `X-Rate-Limit-Ip: 5:10:60,15:60:300,30:300:1800,600:21600:3600`
  (5/10s, 15/60s, 30/300s). Peak state reached `3:10`, `13:60`, `16:300` - never within 2 of any cap.
- Fetch `trade-fetch-request-limit`: `12:4:10,16:12:300,50:300:300,1000:21600:1800`. Peak `2:4`,
  `2:12`. Fetch id cap = 10 (unchanged from the probe's 11->400).
Pacing at 3.5 s kept searches ~7 s apart (interleaved with fetches) = well under 5/10s; 24 searches
< 30/300s. The 21600 s (6 h) bucket carried ~136->158 from earlier same-day work - far under 600.

---

## 2. Per-sample results (all 12 + controls)

Price order column checks the `sort:price:asc` invariant (cross-currency: chromatic < chaos < divine).

| # | Item (class tested) | Emitted query -> | total | Top listings verified | Price-asc | Verdict |
|---|---|---|---|---|---|---|
| 1 | **Pandemonium Shine** (F1+F2 Med Cluster) | **200** | **0** | (none) | - | Query TRUE, 0-match (strict default); F1 piped & F2 socket both wire-valid but don't change the 0. See sec 3/4. |
| 2 | **Entropy Idol** (F1 non-cluster rare) | **200** | **1** | Entropy Idol, Jade Amulet, **has enchant "Allocates Sanctuary"**, 6 explicit mods match, 1 div | ok | **PASS** - piped enchant honoured; correct single item. |
| 3 | **Grim Coat** (armour 85% + 6L) | **200** | **0** | (none); scope-only -> **191** incl. *Twilight Regalia 6L* ilvl86 | - | Query TRUE; scope honest (191 real chests); 0 from strict affix AND. |
| 4 | **Storm Thirst** (weapon subcat) | **200** | **0** | (none); scope-only `weapon.wand` -> **10000+**, top is a Wand | - | Query TRUE; subcategory honest; 0 from strict affix AND. |
| 5 | **Lethal Pride** (timeless exact-seed) | **200** | **1** | "Commanded leadership over **13032** warriors under Rakiata", 1 div | ok | **PASS** - exact seed matched; = R2 124.8c/1div. |
| 6 | **Forbidden Flame** (option contrast) | **200** | **0** | option 43195 (Allocates Slayer) unlisted; name-only -> **2594** (Radiant Crusade/Pathfinder/... variants) | ok | **PASS** - option HONOURED & correctly narrow; 0 = Slayer pair not listed, not a defect. |
| 7 | **Watcher's Eye** (roll-lock triple aura) | **200** | **0** | exact triple unlisted; single Determination>=53 -> **115** real Watcher's Eyes | ok | **PASS** - ids valid & match; 0 = genuinely rare triple, honest. |
| 8 | **Bubonic Trail** (socket-count) | **200** | **2890** | 3x Bubonic Trail, Murder Boots, **all "Has 1 Abyssal Socket" (sockets confirm 1 abyssal)**, 2 chrome | ok (2/2/2) | **PASS** - abyssal-count filter honoured. |
| 9 | **Headhunter** (plain unique name) | **200** | **69** | 3x **"Foulborn Headhunter"** Leather Belt (HH mods), 85/89/90 div | ok | **PASS** - base name matches Foulborn-decorated belts. |
| 10 | **Inpulsa's Broken Heart** (link-split 6L) | **200** | **84** | 3x Inpulsa's, Sadist Garb, **all 6-link**, corrupted, 230/260/270 c | ok | **PASS** - links filter honoured. |
| 11 | **Nimis** (foil unique + value) | **200** | **37** | 3x Nimis, Topaz Ring, **incl. a foil (frameType 10)**, 54/55/55 div | ok | **PASS** - name+base matches, foil indexed. |
| 12 | **Foulborn Esh's Mirror** (F4 prefix) | **400** | - | error `{"code":2,"message":"Unknown item name"}`; base-name "Esh's Mirror" -> **200/990** | - | **BLOCKER L1** - prefixed name rejected; base name is the fix. |

Controls (extra POSTs): S1 piped-removed=0, S1 split+socket-fix=0; S2 piped-removed=1, S2 split-fix=1
(same amulet); F1 bare A/B/C = 4598/4599/10000+; F4 base-name=990; S6 name-only=2594; S7 single=115;
S3 scope=191; S4 scope=10000+.

---

## 3. L2 / F1 deep-dive - the piped id is HONOURED live (corrects the derivation)

The derivation feared (per `variant-stats.md` sec 0.1) that a verbatim `base|opt` id "would 400 if
unsupported", and rated F1 **MAJOR** (whole search fails, or silently drops -> over-broad). **Neither
reproduces.** Decisive bare test (only the enchant filter + `category:jewel`, `enchant.stat_3948993189`
= "Added Small Passive Skills grant: 10% increased Area Damage", option 31):

| Variant | Query filter | total |
|---|---|---|
| A piped-only | `{"id":"enchant.stat_3948993189\|31"}` | **4598** |
| B split-only (the "fix" form) | `{"id":"enchant.stat_3948993189","value":{"option":31}}` | **4599** |
| C baseline | (no stat filter, `category:jewel`) | **10000+** (cap) |

A ~= B (differ by 1 - a single listing flickering in the ~1 s between requests) and both ~= 46% of
the all-jewel baseline. If the piped id were **ignored**, A would equal C (10000+); it is 4598, so it
is **not** ignored. If it **400'd**, A would be an error; it is 200. **The live search parses the
`|opt` suffix and applies the option constraint - identical to the split form.** GGG's own item JSON
confirms the model: the matched Entropy Idol carries its enchant as `stat.enchant.stat_2954116742|20832`
("Allocates Sanctuary") - the piped form **is** GGG's native hash, and the search endpoint accepts it.

**Consequence for the 10 F1 queries:** they are functionally correct on today's live API - the option
constraint they intend IS applied. F1 is therefore **not a live functional defect**. It remains worth
a hardening fix (emit the documented split `{id,value.option}` so a future GGG validation tightening
can't break it), but it is **minor**, not major, and it does **not** leave any item unpriceable today.
(Entropy Idol S2: the piped query returned exactly the right amulet at 1 div.)

## 4. L3 / F2 note - dropped jewel socket, impact masked here

F2 (the singular "1 Added Passive Skill is a Jewel Socket" dropped because the mapper only has the
plural `stat_4079888060`) is a real completeness gap in the emitted query. Its predicted effect
(relax to a socket-less superset -> price low) could **not** be demonstrated live: the only F2 item,
Pandemonium Shine, returns **total=0** for the emitted query, for the piped-removed control, AND for
the fully-corrected query (split option **+** `enchant.stat_4079888060 {min:1}` added) - all three 0,
because the 5-6 exact cluster affixes ANDed under the D-0015 strict default already match nothing.
The socket filter itself is **wire-valid** (the fixed query returned 200). So F2 is a genuine gap with
**no observable live price impact on these four builds**; on an item whose other affixes are loose it
would still bias the search, so the mapper fix is worth doing - severity **minor** on the evidence.

## 5. Cross-references vs the R2 hands-free scan prices

No gross disagreements. Divine rate `~124.8 c/div` `[DERIVED from R2 build2 Lethal Pride 124.8c = 1 div]`.

| Item | R2 recorded | Live cheapest (this sweep) | Assessment |
|---|---|---|---|
| **Lethal Pride** | 124.8c = **1 div** (exact seed 13032) | **1 divine**, seed 13032 in listing | **Exact agreement.** |
| **Nimis** | 7488c (**~60 div**) | **54 div** | Agree - cheapest-online just under the ninja-by-name aggregate. |
| **Headhunter** | 15201c (**~122 div**) | **85 div** (a *Foulborn* Headhunter) | Same order; cheapest-online < ninja aggregate, and the live cheapest is the Foulborn variant vs ninja's plain-name line. Consistent, not gross. |
| **Inpulsa's** | 349c (by-name, not 6L) | **230c** (6-link, corrupted) | Same order of magnitude (R2's number was not 6L-specific). |

## 6. What PASSED live (query-truth confirmations)

- **Status (D-0017):** `{"option":"available"}` accepted on **24/24** searches; 0 status-caused 400s.
- **Category scope (D-0016):** `jewel`, `accessory.amulet`, `armour.chest`, `weapon.wand`,
  `accessory.ring` all resolve to real inventory (armour.chest scope -> 191 chests incl. the exact
  Twilight Regalia base; weapon.wand -> wands).
- **armour_filters 85%:** `es>=1065` (85% of Grim Coat's 1253) matches real high-ES chests.
- **Links:** `socket_filters.links.min:6` honoured - every Inpulsa's and every scope-chest returned
  is a true 6-link.
- **Exact seed (D-0019):** `pseudo_timeless_jewel_rakiata {13032,13032}` -> the one seed-13032 jewel.
- **Notable option (D-0019):** `explicit.stat_2460506030 {option:43195}` honoured (narrows 2594 Forbidden
  Flames to the Slayer pairing; 0 currently listed) - the correct contrast that proves option-split works.
- **Socket-count (D-0019):** `explicit.stat_3527617737 {1,1}` -> every Bubonic Trail has exactly 1 abyssal.
- **Roll-lock (D-0019):** Watcher's Eye aura ids valid (Determination>=53 -> 115 real matches).
- **Foil routing (R1):** Nimis search returns a frameType-10 foil alongside frameType-3.
- **Option wire form:** both the piped `base|opt` AND the split `{id,value.option}` forms are accepted
  and equivalent (sec 3).
- **Price-asc sort:** monotonic in every multi-listing fetch, including correct cross-currency ordering
  (Esh: 2 chromatic < 1 chaos < 1 chaos).

---

## 7. Method / reproduction

1. `scratchpad/gen_r3_queries.py` - runs the real engine on all 4 Allflame builds
   (`engine.run_estimate(url, status="available")`), extracts the exact `trade_query` for the 12
   sample items -> `r3_queries.json`. (poe.ninja only; no trade calls. Queries reproduce the
   derivation byte-for-byte, incl. `enchant.stat_3948993189|31`, `enchant.stat_2954116742|20832`,
   `{option:43195}`, seed `{13032,13032}`, `name:"Foulborn Esh's Mirror"`.)
2. `scratchpad/r3_live_driver.py` (batch 1, 16 POST) - POSTs each emitted query to
   `POST /api/trade/search/Allflame {query,sort:{price:asc}}` (headers: real UA, Accept/Content-Type
   json, Origin/Referer), asserts status, records `total`, `GET /api/trade/fetch/<=3 ids?query=<id>`,
   verifies each listing's name/base/mods/sockets/price. Canary (Headhunter) first. 3.5 s throttle,
   header logging, one-shot Retry-After honour, 2-in-a-row 429 abort.
3. `scratchpad/r3_live_batch2.py` (6 POST) - F1 discrimination (A/B/C bare totals), F4 base-name,
   S6/S7 zero-explanations. `r3_live_batch3.py` (2 POST) - S3/S4 scope validation.
4. All request/response + headers captured in `r3_live_results*.json` + `r3_live_log*.txt`.

**Trade footprint:** 24 search POSTs + 12 fetch GETs, one IP, unauthenticated, 0x 429, 0 aborts,
6/30 POST budget unused.

## 8. Recommended fixes (ranked)

1. **L1 (BLOCKER):** strip the Allflame league prefix (`"Foulborn "`, and any sibling league
   decoration) from the trade `name` in `querybuild._unique_query` / the unique normalisation - search
   the base unique name (`"Esh's Mirror"`), which live returns the decorated listings. Without this,
   every Foulborn unique has a 400 trade link and cannot be scanned/verified client-side. **Confirmed
   fix works live (990 listings).**
2. **L2 / F1 (minor hardening):** emit the split `{id, value:{option}}` in `statmap.match`/`_statf`
   (the derivation's fix) so the query does not depend on GGG continuing to accept the piped alias.
   Not urgent - no query is broken today.
3. **L3 / F2 (minor):** normalise the singular "1 ... is a Jewel Socket" to `stat_4079888060` (mirror
   the R1 abyssal fix). No live price impact seen on these builds, but it closes a real gap.
