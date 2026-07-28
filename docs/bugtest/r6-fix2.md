# R6 — FIX 2 (race lens): F1 generation-token verified + F3 scan-entrypoint guard implemented

Closes the race-lens work from `docs/bugtest/r6-race.md`. Two parts, one root cause (async work from a
superseded build/scan running against the current one):

- **F1 (MAJOR) — per-build generation token:** already present in the working tree when this pass began
  (a parallel R6 fix landed it). **Verified complete + correct here — not re-applied.**
- **F3 (minor, same lens) — scan-entrypoint guard:** the remaining actionable gap. **Implemented this
  pass** at the single scan funnel plus the two UI button handlers that pre-disable a control.

Scope obeyed: edits confined to `C:\scripts\buildpricechecker-poe1`; verification rig under the session
scratchpad `…\scratchpad\r6fix2_negctrl.mjs` (disjoint). **Zero pathofexile.com calls** — all proofs run
offline in a Node `vm` against our own `core.js`. Harnesses green; the engine→UI JSON contract is
unchanged (`state.gen`, `scan.active`, and the `{busy}` return are all internal — no response field
added/renamed/removed). Additive only.

---

## Part A — F1 generation token: VERIFIED present + complete (not re-applied)

The task premise ("grep finds no `state.gen`/`genSeq` in `public/site/assets/core.js`") was **stale** — it
reflected the `r6-reverify1.md` snapshot. By the time this pass ran, the F1 fix had already landed in the
working tree (the concurrent "campaign process editing it" that `r6-race.md` §Provenance flagged, and that
the `D-0020 R6` decision-log entry documents). Rather than blindly re-apply the hint (which would have
double-stamped the token / broken the code), I **verified the existing fix against the finding's exact
prescription.** It is complete and correct — every async continuation class the finding named is gated:

| Continuation (finding F1) | core.js | Gate |
|---|---|---|
| `reset()` stamps the generation + aborts the prior fetch | 355, 358 | `state.gen = ++genSeq`; `curBuildAbort.abort()` |
| `start()` pins the generation | 372 | `var gen = state.gen` |
| build fetch timeout | 413 | `if (gen !== state.gen) return` |
| build fetch `.then` → `loadBuild` | 424 | guard sits **before** `loadBuild(j)` → wrong-build render impossible (F1a) |
| build fetch `.catch` (incl. our own abort) | 433 | `if (gen !== state.gen) return` |
| `cacheReadThrough` fold (applyPrice) | 697 | `if (gen !== state.gen) return` |
| extension scan `foldBatch` (fold + `cachePost`) | 876 | `if (gen !== state.gen) return` → no cross-build fold **and** no poisoned `cachePost` (F1b) |
| extension scan `nextChunk` (stop sending) | 949 | `if (gen !== state.gen) return …superseded` |

Its regression tests are also already present and green: `scenarioRaceBuildSwap` (F1a — appraise A held,
B fast → B renders, late A dropped) and `scenarioRaceZombieScan` (F1b — a held build-A scan reply cannot
fold onto B's same-index items nor POST poisoned entries to the shared cache). No change needed.

## Part B — F3 scan-entrypoint guard (the hint's "guard all scan entrypoints on scanStatus().active")

**The gap.** The F1 generation token does **not** cover F3: F3 is a *within-build* collision (same
`gen`), so the gen-guards never fire. `scanBegin()` (core.js 813-814) calls `scanReset()`
**unconditionally**, and only **2 of the reachable scan entrypoints** carried the
`if(bpc.scanStatus().active) return` guard — `maybeAutoStart` (index.html 2216) and `#autoscanBtn`
(2377). The unguarded ones all reach the extension scan and, mid-scan, would `scanReset()` the running
session (`BUG_sessionCollapsed`, 12→1) and re-send an already-dispatched row (a **duplicate on-IP trade
search** — rate-limit discipline is load-bearing, CLAUDE.md → temporary IP bans):

- `.mr-auto` per-row **⚡auto** button → `priceViaExtension` (index.html 2369)
- `#mpExt` manual-modal **⚡ price via extension** → `priceViaExtension` (index.html 2407)
- picker **Autoscan** → `priceRaresCustom` (`doPickerAutoscan`, index.html 2121)
- picker **re-search** → `priceRareCustom` → `priceRaresCustom` (`doPickerSearch`, index.html 2104)

**The fix — one authoritative guard at the choke point + two UI guards for feedback.**

1. **Engine (authoritative), `public/site/assets/core.js` 840-848.** *Every* scan entrypoint funnels
   through `priceRowsViaExtension`. One guard there closes them all — present and future — and can't be
   forgotten by a UI skin (matches the "engine owns all backend/state logic; views are pure VIEWs"
   guardrail):
   ```js
   if (scan.active) return Promise.resolve({ error: "scan in progress", busy: true });
   ```
   Placed right after the existing `if (!state.bridge.active) return {error:"no bridge"}`; callers already
   treat that resolved-object return as a no-op, so `{busy}` needs no caller changes. This prevents both
   the `scanReset` session-wipe (the guard returns *before* `scanBegin`) and the duplicate chunk send (it
   returns *before* the `nextChunk`/`bridgeSend` loop).

2. **UI (feedback + pattern-match), `public/site/index.html` 2369 & 2407.** The two **⚡ button** handlers
   pre-mutate a control (`textContent='…'; disabled=true`) *before* calling — so the engine guard alone
   would leave the button stuck disabled. Added the codebase's existing guard verbatim
   (`if(bpc.scanStatus().active) return;`) ahead of the mutation, matching the 3 handlers that already use
   it (1815 / 2216 / 2377).

   The two **picker** entrypoints (2104 / 2121) were left to the engine guard: they don't leave a stuck
   control (`doPickerAutoscan` calls `closePicker()` first; `doPickerSearch` advances the queue), the
   engine guard already neutralises the harm, and a UI guard there is architecturally moot (pick-mode and
   auto-scan are mutually exclusive by design — `maybeAutoStart` returns on `pickModeOn()`). Guarding the
   non-bridge branch would also have wrongly blocked the harmless "open trade search in a tab" path.

**Deliberately NOT changed** (matches the finding's own alternative "*and/or* make `scanBegin` merge"):
`scanBegin`/`scanReset` semantics are untouched — the guard prevents re-entry, so no merge logic is
needed, and the single-session behaviour every existing test asserts is preserved.

---

## Verification

**Project harnesses (offline, node) — all green after the edits:**
- `public/site/test_picker.mjs` → **98 / 0** (unchanged; picker tests touch no scan code)
- `public/site/test_scanstatus.mjs` → **131 / 0** (was 119; **+12** from the new `scenarioScanEntrypointGuard`)
- `extension/test_protocol.mjs` → **PASS** (untouched; no extension edits)

`core.js` executes and the `index.html` inline `<script>` parses cleanly after every edit (the
`checkInlineScript` compile-check passes).

**New regression — `scenarioScanEntrypointGuard` (test_scanstatus.mjs).** Drives a real held-reply
autoscan (4 rares, 2 chunks) so the scan stays **active**, then fires a 2nd entrypoint mid-scan and
asserts it is refused (`{busy}`), the session is **intact** (order still 4, `active` still true), and **no
extra `price` message** was sent. Confirms the picker funnel (`priceRaresCustom`) is refused by the same
one guard. Positive control: once the scan ends, the very same entrypoint is allowed to start a fresh scan
(the guard blocks *overlap* only, never permanently disables pricing).

**Liveness proof — negative/positive control** (`…\scratchpad\r6fix2_negctrl.mjs`; reads the repo
`core.js` read-only, loads it twice — as-is and with the guard line string-stripped — into isolated vm
realms, same overlap probe against each):
```
WITH guard   : {"orderBefore":4,"orderAfter":4,"active":true, "msgsBefore":1,"msgsAfter":1,"busy":true}
WITHOUT guard: {"orderBefore":4,"orderAfter":1,"active":false,"msgsBefore":1,"msgsAfter":2,"busy":false}
CONTROL PASS — the guard is load-bearing; the regression test is live.
```
Stripping the guard reproduces the F3 finding **exactly** — the live scan's session collapses **4→1**
(`BUG_sessionCollapsed`), the running scan is wiped (`active` → false), and a **2nd `price` message** is
sent (the duplicate on-IP trade search) — and the guard prevents all three. So the new test is not
vacuous: it fails without the fix.

---

## Scope / honest carry-forwards (flagged, not softened)

- **`bpc/ui/assets/core.js` (classic/local edition) — out of scope, structurally N/A.** It is a different,
  smaller (498-line) engine that polls `/api/job` and has **no** `priceRowsViaExtension`, `scan.active`,
  `genSeq`, extension bridge, or community cache (grep-confirmed: zero matches). The F1/F3 race findings
  are specific to the public one-shot-document + extension + shared-cache architecture, so they do not
  apply there. Not touched (would be unrequested scope; RULE 3).
- **F2 (MINOR, `r6-race.md`) — a late `cacheReadThrough` clobbering a manual/trade price — NOT addressed.**
  It is a separate precedence defect (needs a source-precedence check in `cacheReadThrough`'s applyPrice),
  not covered by the generation token or the scan guard, and it is **not** in this task's finding list
  (item 1 = F1 only; the hint adds the F3 scan guard). Its own honest caveat (narrow natural
  reachability — requires a >2 s cache delay) stands. Flagged for a later pass.
- **F4 (MINOR)** is the same root cause / same fix as F1 (rapid league/status `rerun()` re-fetches) and is
  covered by the generation token already verified in Part A.
- **popup.js self-XSS (S3 / firefox R6-1)** remains a separate open MINOR (linter *warning*, not error —
  does not block AMO); unrelated to the race lens, not in this task.

**Net:** the race lens is now addressed end-to-end — F1 (verified) closes wrong-build render +
cross-build fold + cache poisoning; F3 (implemented) closes the live-scan wipe + duplicate trade calls at
one choke point. F2 is the only race-lens item left open and is a bounded, narrowly-reachable minor.
Recommend: deploy, then re-sweep (LOOP-UNTIL-DRY — two clean rounds needed).
