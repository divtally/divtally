# Verify — per-rare AFFIX PICKER round (D-0015), adversarial pass

Date: 2026-07-27. Scope: `public/site/{assets/core.js,index.html,assets/sample.js,stub-build.json,
test_picker.mjs}` + `public/api/_lib/{querybuild.py,response.py}` + `public/api/_verify.py`.
Method: code trace + all harnesses + git-diff scope check + desktop-parity cross-read
(`bpc/web.py`, `bpc/pricing.py`, read-only parent README). No pathofexile.com calls.

## VERDICT: PASS — no blockers, no majors. 3 minors (all safe-direction / doc-and-test clarity).

D-0015's veto ("if the user doesn't manually exclude an affix we should not be doing that for
them") is honored on every query-construction path. Nothing unticks / drops / relaxes an affix
without a user action. All harnesses green; the one change to existing code is the claimed
1-liner.

---

## 1. D-0015 compliance — every query path traced (blocker class: CLEAN)

**Client builder `buildRareQuery` (core.js L918-953) + `rareDefaultPicks` (L889-897) + `_pickOf`
(L905-910):**
- Default (no picks / omitted entry) → `affixDefaultTicked` = ON for every searchable stat +
  every equip defence total. Nothing is unticked by the tool. VERIFIED.
- An affix is dropped from the query ONLY when (a) `!searchable || !stat_id` (unsearchable — it has
  no trade filter and CANNOT be one; shown greyed with its reason, never silently omitted), or
  (b) the user's pick is `ticked:false`, or (c) it is a resistance folded into a pseudo total while
  the visible fold toggle is ON. No fourth path exists. VERIFIED by trace + `test_picker` CASE 6
  (unsearchable never emitted even if force-ticked) and CASE 2 (untick removes exactly one).
- Scope (`type`/`name`/`type_filters`) and the 5/6-link `socket_filters` are copied VERBATIM from
  the item's own `origQuery`; never invented (CASE 8). `armour_filters` are rebuilt from the same
  defence data the API used (100% of roll, min-only), not copied — correct, avoids double-sourcing.

**UI wiring `readPicks` (index.html L1720-1733):** builds a COMPLETE, correctly-indexed picks map —
each rendered `.afx[data-i]`/`.afx[data-pi]` row contributes `{ticked: cb.checked, min, max}` keyed
by the affix array index. Unticking a box therefore yields `ticked:false`, which `buildRareQuery`
honors. There is NO sparse-map hazard (a missing index defaults to ticked in `_pickOf`, but the UI
never omits a rendered searchable row) — so unticking is real, not silently re-ticked. VERIFIED.

**Pseudo fold default-ON is compliant, not a silent relax.** `rareDefaultPicks` sets
`usePseudo = pseudo.length>0`. D-0015's own text names "pseudo-resist fold as a visible user
toggle" as part of the picker spec, and the desktop app defaults it ON (`bpc/web.py` `showPicker`
L1136). The toggle is visible and flippable (index.html L1705-1706, L1768); turning it OFF restores
individual resistances (CASE 3). So the fold is governed BY the visible toggle exactly as task
item (c) requires and as the owner blessed in D-0015. Not a violation.

**Autoscan interplay (task item 3):** `maybeAutoStart` (index.html L1823-1835) returns early when
`pickModeOn()` (L1827) — pick mode never fires the extension autoscan. Pick mode OFF is byte-for-
byte the prior behavior; toggling the box OFF re-invokes `maybeAutoStart` (L1791). VERIFIED.

## 2. Harnesses + checks (all green, hermetic)

| check | result |
|---|---|
| `node --check` core.js, sample.js, worker.js, extension/{content,background,popup}.js | all OK |
| `node test_picker.mjs` (query builder) | **42 passed / 0 failed** |
| `node test_scanstatus.mjs` (scan status) | **47 passed / 0 failed** |
| `node extension/test_protocol.mjs` | **PASS (all checks)** |
| `BPC_SKIP_LIVE=1 python public/api/_verify.py` | **ALL CHECKS PASSED** (Phase B skipped) |

## 3. Regression hunt (task item 3: CLEAN)

- **Only 1 existing line changed in core.js** (git diff confirmed): L731
  `var q = r.query || (tq && (tq.query || tq));` — inert for the autoscan/single-item callers
  (they set no `r.query`). Everything else in this round is purely additive (new picker fns +
  exports). D-0012 chunking (CHUNK=3, per-chunk `30000+30000*n` timeout), `cachePost`, the v1.1
  scan-status machine, and the SHARED CACHE-KEY recipe (`itemIdentity`/`cacheKey`/`leagueKeyspace`)
  are UNTOUCHED.
- **Cache POST identity keys unchanged:** refined picker prices flow through the same
  `cachePost → cacheKey(league, rec.item) → itemIdentity(item)` path — keyed by item identity, not
  by the query. (Value-semantics caveat: see finding P-2.)
- **No server-side pathofexile.com reachability added:** `querybuild.py` imports only
  `urllib.parse` (URL string building); `response.py` has no network. The site prices rares only via
  the extension bridge (`postMessage`) / user-opened trade tab — never a site/server fetch to GGG.

## 4. UX vs parent README advanced-flow promises (task item 4: MET)

Parent README L88-107 promises, each satisfied: one-at-a-time queue (`presentQueue`/`advanceQueue`/
`openPicker{queue}`); tick + min/max per affix; "Search this item" → next rare; background pricing
continues (gems/uniques server-priced in the doc, `cacheReadThrough` runs regardless of pick mode —
only the rare *extension autoscan* is gated); Skip leaves the rare unpriced; every rare row has an
always-available "edit affixes" (L1918) that reopens that one rare (L1781-1783) and re-prices in
place; resistance→pseudo toggle default ON with untick-to-individual. All picker DOM ids resolve
(`pick`, `pickwrap`, `pickAffixCb`, `manualRows`, `autoscanBtn`, `autoAuto`). Real `sample.js` rare
payloads match the builder's expected shape; `affixPrefill` is robust to both the new
(`default_min`/`default_max`) and legacy (signed `value`) shapes.

---

## FINDINGS (all MINOR)

### P-1 (minor, test + decision-log clarity) — "all-ticked == API strict query" is builder self-consistency, not equivalence to the delivered query
The picker's all-ticked default is deliberately **stricter** than the API's delivered rare
`trade_query`:
- stats: **roll-min** `{id, value:{min}}` vs the API default's **presence-only** `{id}`
  (`querybuild.py` `_rare_default_filters._statf`);
- defence: **100%** of roll vs the API's **85%** (`int(value*0.85)`);
- resistances: **pseudo-total** stat-ids (fold default ON) vs the API default's **individual**
  resistance `{id}` filters (the API default never folds).

This is INTENDED and faithful to the desktop app — `bpc/pricing.py` `_rare_default_filters`
(the advanced-OFF autoscan) is byte-identical presence-only/85%, while `bpc/web.py` `affixRow`/
`defaultRarePayload` (the picker + in-picker Autoscan) is roll-min/100%/fold — i.e. the desktop has
the exact same "picker stricter than the plain autoscan" split. It also does NOT violate D-0015
(stricter never silently excludes; it's literally the "honest exactly-this-good" search D-0015
asks for). **The nuance to record:** `test_picker` CASE 1 asserts equality against `ORIG`/`PRESENCE`
fixtures that are themselves authored roll-min **and pseudo-folded** — so neither CASE 1 nor CASE 1b
compares the picker to the API's *actual* delivered shape (individual-resistance, presence-only,
85%). The harness proves the builder is internally consistent and drops/invents nothing (the real
D-0015 guarantee), which is correct and sufficient — but "42 passed" must not be read as "picker
all-ticked == what Autoscan searches" (it isn't, by design). Recommend: the short decision-log
entry the notes themselves request ("the public picker is roll-min / stricter-than-Autoscan,
faithful to the desktop app"), and relabel CASE 1b's `PRESENCE` fixture (its ids are the pseudo
totals, not the raw-API individual-resistance ids its comment implies).

### P-2 (minor, cache data-quality) — refined picker prices seed the community cache under the generic item key
A picker "Search this item" / in-picker "Autoscan" via the extension folds its price into the row
AND POSTs it to the shared cache (`foldBatch` → `cachePost`), keyed by `itemIdentity(item)` — the
SAME key a default all-affix price uses. So a user who unticks affixes or clears mins (looser →
cheaper) or tightens mins (stricter → pricier) seeds the shared "default" number other users read
for that exact item. Keys are unchanged (regression-clean), but the value now may not correspond to
the default query it will be shown against. Bounded by D-0009's "community · unverified /
best-effort" framing and intended per `docs/notes-picker-site.md`, but the pollution implication
looks unconsidered. Owner decision: either don't cache-POST refined searches, or key refined results
by a query hash. Not blocking.

### P-3 (minor, UX state-loss + slight doc overstatement) — a manually-unticked resistance is re-ticked across a pseudo-toggle round-trip
Untick an individual resistance (fold OFF) → toggle fold ON → toggle fold OFF: the resistance row
returns **ticked**. Cause: on each toggle `readPicks()` snapshots only *rendered* rows; while fold
is ON the individual resistance rows are hidden, so their unticked state isn't carried into the
re-render prefill and `affixRowHTML` falls back to the ticked default (index.html L1662, L1768).
`docs/notes-picker-site.md` says "Edits survive a pseudo toggle" — true only for rows that stay
rendered. Direction is SAFE for D-0015 (re-includes, never silently excludes) and still better than
the desktop (which drops ALL picker edits on every fold toggle). Fix optionally by preserving a
full picks history across toggles, or soften the doc claim.

---

## Commands run
```
node --check public/site/assets/core.js  (+ sample.js, worker.js, extension/*.js)   -> all OK
node public/site/test_picker.mjs           -> 42 passed / 0 failed
node public/site/test_scanstatus.mjs       -> 47 passed / 0 failed
node extension/test_protocol.mjs           -> PASS (all checks)
BPC_SKIP_LIVE=1 python public/api/_verify.py -> ALL CHECKS PASSED (Phase B skipped)
git diff HEAD -- public/site/assets/core.js  -> 1 existing line changed (L731); rest additive
```
Note: `_verify.py` writes its offline sample to the OS temp dir (pre-existing tool behavior,
task-mandated run) — not a repo write.
