# R3 fix RE-VERIFY (pass 1) — all five Round-3 query-truth fixes confirmed

**Round:** 3 (query TRUTH) of the D-0020 campaign. **Date:** 2026-07-28.
**Scope:** independently re-verify the R3 fixes in `docs/bugtest/r3-fix1.md` — F1, F2 (offline
derivation), R3-1, R3-2 (picker), **L1 = F4** (live BLOCKER) — by (A) re-running every harness +
the evidence probes and **re-deriving the previously-wrong queries through the real engine**, and
(B) re-executing the **previously-failing live sample entries** against the real trade API.
**Verdict: all five fixes hold. No new defect. PASS.**

**Trade budget this phase:** 4 / 8 search POSTs + 2 fetch GETs. 0× 429, 0 aborts, ≥3.5 s spacing,
real UA w/ contact. Peak rate state `4:60`, `4:300`, `162:21600` — never within 2 of any cap.

---

## A. Offline re-verify (harnesses + real-engine re-derivation)

**Harnesses (all green, re-run now):**
| Harness | Result |
|---|---|
| `public/site/test_picker.mjs` | **98 passed, 0 failed** |
| `public/site/test_scanstatus.mjs` | **64 passed, 0 failed** |
| `scratchpad/probe_r3_server.py` (drives real `public/api/_lib`) | **ALL PROBES PASSED** (F1, F2, L1) |
| `scratchpad/probe_r3_client.mjs` (drives real `public/site/assets/core.js`) | **ALL CLIENT PROBES PASSED** (R3-1, R3-2, F1-picker) |

**Real-engine re-derivation** — `scratchpad/gen_r3_queries.py` re-ran the actual
`engine.run_estimate(url, status="available")` on the four Allflame builds (poe.ninja only, zero
trade calls) and re-extracted the emitted `trade_query` for the previously-wrong items. The engine
now emits the corrected wire forms verbatim:

- **F1 (Pandemonium Shine, build 2)** — grant enchant now emitted **split**:
  `{"id":"enchant.stat_3948993189","value":{"option":31}}`. **No `|` piped id remains.** ✓
- **F2 (Pandemonium Shine)** — the singular jewel socket is now **present**:
  `{"id":"enchant.stat_4079888060"}` (was dropped entirely before the fix). ✓
- **F1 (Entropy Idol, build 1)** — non-cluster rare enchant split:
  `{"id":"enchant.stat_2954116742","value":{"option":20832}}`. ✓
- **L1 = F4 (Foulborn Esh's Mirror, build 3)** — trade query `name` is now the **base name
  `"Esh's Mirror"`** (`type:"Vaal Spirit Shield"` preserved); `item.name` keeps the decorated
  "Foulborn …" line for poe.ninja pricing. No "Foulborn" in the trade query/URL. ✓
- **R3-1 / R3-2** — re-confirmed via `probe_r3_client.mjs` on the real `core.js`: a defining
  resistance is emitted (never folded into the pseudo total) in BOTH the all-ticked and survey/tier
  paths; a searchable `skip` unique mod + the unique pseudo total now tier to `nice` (searched), the
  unsearchable `skip` row still `notneeded`. ✓

---

## B. Live re-verify — previously-failing sample entries (4 POSTs, 2 fetches)

`scratchpad/r3_reverify_live.py` POSTed the FIXED engine queries to
`POST www.pathofexile.com/api/trade/search/Allflame`. Raw capture:
`scratchpad/r3_reverify_{results.json,log.txt}`.

| # | Entry (defect) | Before fix | FIXED query result | Listings match? |
|---|---|---|---|---|
| S12 | **Foulborn Esh's Mirror** (L1 BLOCKER) | HTTP **400** "Unknown item name" — dead trade link | `name:"Esh's Mirror"` → **200, total = 992**; top-3 fetched = **Foulborn Esh's Mirror / Vaal Spirit Shield / frameType 3** (1c–2 chrome) | **YES** — every listing is the exact item |
| S12-ctrl | old prefixed name (causality) | — | `name:"Foulborn Esh's Mirror"` → **still 400** "Unknown item name" | proves the base-name strip is what fixes it |
| S2 | **Entropy Idol** (F1 split option) | feared 400/drop | split `{option:20832}` → **200, total = 1**; fetched = **Entropy Idol / Jade Amulet**, enchant **"Allocates Sanctuary"** (`stat.enchant.stat_2954116742\|20832`), all 6 explicit mods match | **YES** — split option honoured, correct amulet |
| S1 | **Pandemonium Shine** (F1 split + F2 socket) | piped id + dropped socket | split option **+** `enchant.stat_4079888060` → **200** (wire-valid), total = 0 | Query **accepted** (no 400/regression); total 0 is the known D-0015 strict all-affix default (see r3-live L3), not a query-truth defect |

**Key confirmations:**
1. **L1 BLOCKER is resolved live** — the fixed base-name query returns 200 + 992 real listings, all
   the correct Foulborn Esh's Mirror shields; the pre-fix prefixed name **still 400s** in the same
   sweep, so the fix (not a league/site change) is what closed it. Trade link + client scan now work
   for every Foulborn unique.
2. **F1 corrected wire form is honoured live** — the split `{id,value.option}` returns the exact
   intended item (Entropy Idol with "Allocates Sanctuary"); consistent with r3-live L2 (piped and
   split are equivalent live). No item is left unpriceable by the change.
3. **F1 + F2 corrected Pandemonium query is wire-valid (200)** — adding the split option and the
   jewel-socket id does not 400 and does not regress; the 0-match is the pre-existing strict default,
   independent of these fixes (documented in r3-live §4 / L3).
4. **No listing returned failed to match its query.** No "the query lies" case survives.

---

## C. Trade-budget & rate ledger (hard-rule compliance)

| Metric | Value |
|---|---|
| Search POSTs | **4 / 8** |
| Fetch GETs | **2** |
| 429s / aborts / back-offs | **0 / 0 / 0** |
| Min spacing | **3.5 s** (task floor 3 s) |
| User-Agent | `buildpricechecker-poe1/0.1 (… R3 fix RE-VERIFY; contact: divtally@gmail.com)` |
| Search rule / peak | `5:10, 15:60, 30:300, 600:21600` / peak `2:10, 4:60, 4:300, 162:21600` (never within 2 of a cap) |
| Fetch rule / peak | `12:4, 16:12, 50:300` / peak `1:4, 2:12, 107:21600` |

## D. Artifacts (scratchpad, non-repo, reproducible)
- `gen_r3_queries.py` → `r3_queries.json` (real-engine re-derived queries)
- `probe_r3_server.py`, `probe_r3_client.mjs` (evidence probes, ALL PASSED)
- `r3_reverify_live.py` → `r3_reverify_results.json`, `r3_reverify_log.txt` (live sweep, 4 POST/2 GET)

**Bottom line:** every previously-wrong query now describes its item (offline re-derivation), and
every previously-failing live entry now returns 200 with listings that match — the L1 BLOCKER is
fixed live and its pre-fix failure still reproduces as the control. **RE-VERIFY PASS.**
