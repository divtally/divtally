# R5 — Regression + Acceptance (fresh eyes)

**Round:** 5 (regression + acceptance vs the product's own written promises) of the D-0020 campaign.
**Date:** 2026-07-28. **Verdict: PASS — ZERO regressions, ZERO blockers.** Every defect fixed in
Rounds 1–4 is re-verified STILL fixed on the live product today; all six harnesses re-run green.

**Method.** Built a checklist of every fixed defect from `r1-fix1.md`, `r2-judge.md` (+ the
`D-0020 R2 F1` decision-log fix), `r3-fix1.md`, `r4-fix1.md`, then re-verified each through the REAL
code paths — not by re-reading the fix notes. Server fixes: dedicated probes through `public/api/_lib`
(offline + FRESH live poe.ninja on the real owner build). Client fixes: the node harnesses + ONE
hands-free browser drive of the largest owner build **TimeForAurab** (`yalokk-2571`) on **live
divtally.com + the real extension v1.2.1**. The live `assets/core.js` is **byte-identical** to the
repo (`v=20260727g`, 80171 B) — every client fix is deployed.

**Trade footprint (honored the hard limit):** exactly ONE build scan — the extension's own paced,
logged-out traffic on TimeForAurab. No direct `pathofexile.com` call by any probe (`_verify.py` live
phase, the two live poe.ninja probes, and the timeout sim are all trade-free; the sim's `/api/build`
hang and the extension's service-worker fetches never touch a trade search from a probe).

---

## 1. Harnesses — all green (re-run today)

| Harness | Result |
|---|---|
| `python tests.py` (bpc) | **All self-tests passed** |
| `python public/api/_verify.py` (offline A + live poe.ninja B) | **ALL CHECKS PASSED** — live 41 items, priced=20, `no /api/trade in document`, `health says never calls pathofexile` |
| `node public/site/test_scanstatus.mjs` | **106 / 0** (incl. F1 placeholder-drop, R4-4 timeout, R4-5 whisper, R4S-1 recent-coercion scenarios) |
| `node public/site/test_picker.mjs` | **98 / 0** (incl. D-0019 defining-mod / R3-1 / R3-2 cases) |
| `node public/worker/worker.test.mjs` | **55 / 0** |
| `node extension/test_protocol.mjs` | **PASS** |

---

## 2. Regression checklist — every FIXED defect re-verified STILL fixed

Receipts: `e2e` = `e2e_r1.py`, `pob` = `probe_e2e_pob.py`, `srv` = `probe_r5_server.py`,
`live` = `probe_r5_live.py` (fresh, real TimeForAurab), `ss`/`pk` = the node harnesses, `drive` = the
browser drive. All PASS.

| # | Defect (round) | Fix locus | Receipt(s) | Status |
|---|---|---|---|---|
| R1-A | gem-group dedup dropped distinct gems | `poeninja.normalize` id-set | e2e: 3 distinct Raise Spectre→3 rows; same-id→1; `id:null` kept | **STILL FIXED** |
| R1-B | bad URL → 502 not 400 | `engine.prepare_from_url` | srv: overview / PoE2 / wrong-host → `EstimateError` (400), pre-network | **STILL FIXED** |
| R1-C | link-split unique mispriced | `poeninja._link_tier_lines` | srv: non-monotonic 5L>6L → 6L copy picks the 6L line (count, not price) | **STILL FIXED** |
| R1-D | implicit mods absent from picker | `querybuild.affix_options` | e2e: corrupted implicit is an opt-in `group:"implicit"` row, not in the default query | **STILL FIXED** |
| R1-E | foil unique (ft 9/10) dropped to normal | `poeninja._categorise`, `models.FRAME_RARITY` | e2e: ft10 Nimis→unique+priced 7680c; srv: ft9/ft10/rarity-fallback→unique | **STILL FIXED** |
| R1-F | 1-abyssal unique unpriced (singular text) | `variantreg.build_variant` socket fallback | srv + live: `explicit.stat_3527617737 {min:1,max:1}`, label "1 Abyssal Sockets" | **STILL FIXED** |
| R1-G | weapon-swap summed into totals | `response._is_swap/_sum_tier` | e2e + live: Silverbranch/Replica Maloney's flagged `swap`, excluded from totals | **STILL FIXED** |
| R2-F1 | variant-unique 0-match placeholder counted | `core.js dropIfPlaceholder` + `applyPrice` | ss `scenarioVariantPlaceholder`; drive: no variant unique lingers counted | **STILL FIXED** |
| R3-F1 | option-stat emitted as `base\|opt` | `querybuild._split_option/_statf` | srv: Forbidden Flesh → `{id:explicit.stat_1190333629, value:{option:4194}}`, no pipe; live: 0 pipe-ids in the whole response | **STILL FIXED** |
| R3-F2 | singular jewel-socket enchant dropped | `statmap._normalise_pattern` | srv: "1 Added Passive Skill is a Jewel Socket"→`enchant.stat_4079888060` | **STILL FIXED** |
| R3-L1 | Foulborn name 400s the search | `querybuild._base_unique_name` | srv + **live fresh**: trade name → base ("Matua Tupuna"), display name keeps decoration | **STILL FIXED** |
| R3-1 | defining resistance folded into pseudo | `core.js buildRareQuery/tierGroups` | pk: defining mod stays in the AND group / can't be excluded | **STILL FIXED** |
| R3-2 | survey picker excluded searchable skip rows | `core.js _siteTierOf` | pk (98/0); D-0016 fixtures intact | **STILL FIXED** |
| R4-1 | PoB ignored gem corruption (~25% low) | `pob.py`+`bpc/pob.py` | pob + live: 7 L21 gems flagged `corrupted:true` on the real build | **STILL FIXED** |
| R4-2 | PoB no weapon-swap exclusion (+136%) | `pob.py`+`bpc/pob.py` | pob + live: headline 1761.3c = non-swap sum; **2780c swap excluded** (would be 4541.3c) | **STILL FIXED** |
| R4-4 | build fetch had no timeout (hung UI) | `core.js start()` AbortController | ss + **drive slow-endpoint sim**: /api/build hangs → error in 4.2s, never stuck | **STILL FIXED** |
| R4-5 | whisper folded locale/thousands seps | `core.js parseWhisper` | ss + **drive in-page**: 5 separated forms rejected, 4 legit parsed | **STILL FIXED** |
| R4S-1 | corrupt `bpc_recent_builds` → false error | `core.js loadRecent/pushRecent` | ss `scenarioRecentCoerce` (wrong-type → `[]`) | **STILL FIXED** |

---

## 3. Browser drive — TimeForAurab on live divtally.com (the one trade scan)

Untouched fresh profile; defaults read **status "available" (Instant Buyout and In Person), tier
"min", autoscan ON**; single sanctioned `Enter`; autoscan fired itself. Bridge lit **"v1.2.1"**.

**D-0020 hard criteria — both PASS:**
- **(a) scan-duration audit produced** — `totalMs 67428`, honest per-item median **3586 ms** (n=12),
  one 28 s window back-off (self-resolved hands-free).
- **(b) hands-free fruition** — **13 / 13 rows terminal, 0 stuck, 0 console errors, 0 page errors**,
  zero clicks after the Enter.

**Timing vs R2 Build 4 (regression check, within ±15%):**

| Metric | R2 Build 4 | R5 drive | Δ |
|---|---|---|---|
| totalMs | 67.6 s | **67.4 s** | −0.3% |
| honest per-item (median) | 3623 ms | **3586 ms** | −1.0% (band 3079–4166) |
| rows scanned | 13 | 13 | — |
| big window back-off | 27.9 s | 28 s | self-resolved |

The scan is the limiter doing its job (≈3.33 s pacing quantum + fetch interleave), exactly as R2
characterised — no engine waste re-appeared.

**Placeholder invariant (R2-F1) — PASS:** every variant unique ends as a real trade price OR
link-only; none counted at a poe.ninja placeholder. `Watcher's Eye` → `source=trade, median=null,
enabled=false, link=true` (its exact locked-mod search ran and correctly resolved to link-only);
`Bubonic Trail` likewise.

**R4-4 slow-endpoint sim — PASS:** `/api/build` routed to accept-then-hang, `?buildTimeout=4000` →
page recovered to `phase:"error"` in **4210 ms** with "The pricing service took too long to respond",
never stuck in `loading`.

**R4-5 whisper separators — PASS (in-page on the live bundle):** rejected `1,000` / `1 000` /
`1.000.000` / `1'000` / `35,5` chaos (→ null, no fabricated number); parsed `35` / `1000` / `2.5 div`
/ `35.5` chaos.

---

## 4. Fresh-eyes acceptance notes (NOT defects — no code change)

1. **Live Allflame economy has thinned since R2/R4.** Several variant uniques that priced by name
   then (Watcher's Eye, Bubonic Trail) now return `unique-unpriced` from the server — poe.ninja's
   Allflame overview no longer enumerates their exact variant lines. This is **D-0019-compliant**
   (link-only, with the correct locked filter carried), not a regression. Consequence: the R2-F1
   "drop a stale placeholder" scenario is **not reproducible on live data today** because upstream
   serves no floor number to drop. The drop guardrail is still proven deterministically by the green
   `test_scanstatus` scenario, and the live drive confirms the end-state invariant holds. The F1
   defect's live blast-radius is currently nil.
2. **Nimis** is not in the live Allflame unique overview right now, so it has no live poe.ninja price
   today. The R1-E fix (ft 9/10 → unique category) is intact and proven (e2e + srv); pricing is
   upstream-data-dependent.
3. **The R3-era scratchpad cache (`build4_yalokk_doc.json`) is stale** for R3-L1 — it shows an
   un-stripped `"Foulborn Matua Tupuna"` trade name (pre-fix). A FRESH `run_estimate` with today's
   code strips it correctly to `"Matua Tupuna"`. Caution for future rounds: regenerate; don't assert
   against R3-era caches.
4. **F3 (chunk-cumulative raw per-row `ms`) is still open** — it was never a *fixed* defect (an R2
   minor, deferred), so it is out of this regression's scope and not a regression. This drive timed
   per-item independently (inter-completion deltas) rather than trusting the raw field, consistent
   with R2's method.

---

## 5. Artifacts (rig: `…/scratchpad/r5reg/`, non-repo)

`probe_r5_server.py` (R1-B/C/E/F, R3-F1/F2/L1 — ALL PASS), `probe_r5_live.py` (fresh live TimeForAurab
re-verify + PoB round-trip — ALL PASS, `live_summary.json`), `probe_r5_drive.cjs` (browser drive —
ALL PASS, `drive_result.json`). Re-ran the prior-round proofs `e2e_r1.py` (R1 A/D/E/G — ALL PASS) and
`probe_e2e_pob.py` (R4-1/R4-2 — ALL PASS).

**Round verdict: DRY.** No meaningful adjustment surfaced — a clean regression + acceptance pass.
Every Round 1–4 fix holds together on the live product; the two D-0020 hard criteria pass on the
largest owner build with timing indistinguishable from R2.
