# R6 — CONCURRENCY / RACE lens (LIVE divtally.com)

**Date:** 2026-07-28 · **Lens:** overlapping async / races (fresh angle; the 4 standard lenses done, R5 found no functional bugs).
**Verdict:** **NOT dry.** One **major** cluster (silent wrong-build render + cross-build price fold + community-cache poisoning) and three **minor** confirmations, all from a single root cause: **the page-side state machine has no per-build "generation" token**, so async continuations from a superseded build/scan run against whatever build is currently loaded.

## Method (faithful + trade-safe)
- Driver: `…/scratchpad/r6race/driver.mjs` (+ `p4b.mjs`). Runs the **real** live page — `https://divtally.com` — whose `assets/core.js` I first confirmed **byte-identical** to the repo copy (`diff` = IDENTICAL, 80 171 bytes), so every line ref below is the deployed code.
- **Zero pathofexile.com calls.** To make races deterministic *and* avoid trade load, the driver intercepts only divtally's **own** infra — `/api/build` (Vercel) and the worker `/cache` — serving the real captured build docs (qwartus = **A**, sergo = **B**), and injects a **mock extension bridge** in-page (identical postMessage protocol to `extension/content.js`) so I control exactly *when* a `price-result` lands. The code under test (the page state machine, where the races live) is 100% live.
- **0 pageerrors, 0 console errors** across every probe — these are all **silent** failures (no crash, nothing surfaced to the user), which is the worst kind for trust.

---

## F1 (MAJOR) — Appraise A → B before A settles: wrong build shown + cross-build price fold + **community-cache poisoning**
**Root:** `start()` (core.js 338-402) sets `state.source` then fires `fetch`, gated only by a **per-call** `settled` flag (379-399) — there is **no generation token** on `state`. `reset()` (328) does **not** clear the module-level `pending{}` (696) map or cancel the previous fetch. So a second Appraise neither cancels the first fetch nor invalidates the first scan's in-flight replies; both continue and fold into the current build.

Known-issue note: R4S-2 / R4S-3 (`r4-state.md`) already flagged "no generation guard" but rated it **minor/graceful** — because R4 double-clicked the **same** build, where last-writer-wins is invisible. The concurrency lens with **different** builds is the untested gap, and there it is **not** graceful:

### F1a — last-writer-wins renders the WRONG build (P1, live)
Fire `startUrl(A)` (held 2.6 s) then `startUrl(B)` (120 ms) — i.e. "paste A ⏎, paste B ⏎". The appraise form's submit handler (`#f` → `bpc.startUrl`) has **no loading-lock**, so both submit.
- `loadOrder = [SergoheroGaz(B), qwartus_niceboat(A)]` — B rendered, then **A clobbered it**.
- **Final rendered build = `qwartus_niceboat` (A)** though the user's last request was **B**. `finalTotalsMedian = 2240.3` (A's total), `nItems = 30` (A has 30, B has 29).
- **Incoherent:** `state.source.url` = …/**SergoheroGaz** (B) while `state.meta`/items/priced = **A** → a subsequent refresh/rerun re-fetches B, and `pushRecent` logged A. The build pointer and the visible valuation disagree.

Reachable naturally whenever build A's fetch is slower than a later build B's (A cold vs. B CDN-cached is the common case).

### F1b — a zombie A extension scan folds A's prices onto B + poisons B's cache keys (P2, live)
Start A's autoscan (captured chunk-0 keys `["0","2","3"]`), **hold** the reply, switch to B, then deliver A's held `price-result` (fabricated 999 c, as the extension would). `pending[reqId]` survived `reset()`, so `foldBatch` (828) runs — and `state.items.find(index===res.key)` (834) matches **B's** items because `index` is **positional** (0,1,2… in every build):

| A key | folded onto B's item | before | after |
|---|---|---|---|
| 0 | Replica Voidwalker (unique) | 5 c poe.ninja | **999 c** extension |
| 2 | Honed Thicket Bow (magic) | unpriced | **999 c** |
| 3 | **Headhunter, Leather Belt** (unique) | **14 613 c** poe.ninja | **999 c** |

- **B's headline total corrupted `28 471 c → 15 851 c`** — the build the user is looking at now shows a bogus Headhunter price, no error.
- **Cache poisoned:** the same `foldBatch` pushed to `cachePost` (894) → **1 POST, `league:"Allflame"`, 3 entries, all median 999** — keyed under **B's** item identities (incl. Headhunter). `cacheKey` = `SHA-256(leagueKeyspace(B.league) ⋮ itemIdentity(B.item))`, so **other users** who appraise a build containing those identities and read the community cache get build A's fabricated number. This is persisted, shared, cross-user corruption — squarely the "**no zombie A scan feeding B's cache**" invariant, violated.

Reachability is realistic: a real autoscan runs tens of seconds (≥3.3 s/search × N rares); pasting a second build inside that window is a normal "let me check my other character" action. Only the reply *timing/content* was mocked; the page path (pending-survives-reset → index-collision fold → cachePost) is live.

**Fix (covers F1a+b, F3, F4):** stamp `state.gen = ++genSeq` in `reset()`; capture `var gen = state.gen` at the top of `start()`, and **drop** any continuation whose `gen !== state.gen` — the build fetch `.then`/`loadBuild`, `cacheReadThrough`'s applyPrice, and `foldBatch`/`cachePost`. Optionally abort the previous fetch and ignore submits while `phase==='loading'` (R4S-2's own recommendation).

---

## F2 (MINOR) — a late cache read-through clobbers a real/user price (no source precedence in `applyPrice`)
**New** (never flagged — confirmed by grep across all rounds). `applyPrice` (474-498) overwrites `state.priced[key]` **unconditionally** (480); its only guard protects `state.enabled` (the include toggle), not the price value — yet `cacheReadThrough` (642) applies its result **passively** with no `{include}` and **no check that the row already carries a better price**. The comment "so a user's own decision isn't overridden" is therefore only half true.

**P3 (live):** load A → `cacheReadThrough` GET goes in flight (I delayed it 2.5 s). Before it resolves, the user pastes a whisper on the first rare: `applyWhisper(key,"2 div")` → `source:manual, median:245.6`. The late cache GET then resolves → the row flips to **`source:cache, median:7`** — **the user's explicit 2-div price silently replaced by an unverified 7 c community value** (`BUG_whisperClobberedByCache = true`).

**Honest caveat:** natural reachability is narrow — the edge cache normally answers in ~200 ms, so the user (or the extension) must land a real price on the row *inside* that window; I forced a 2.5 s delay to demonstrate deterministically. Still a real precedence defect with a trivial, worthwhile fix (silent wrong value).

**Fix:** in `cacheReadThrough`'s applyPrice, skip when the row already has a non-cache real price (`state.priced[key].source` ∈ {manual, trade} and median != null) — cache is the lowest-precedence source.

---

## F3 (MINOR) — a 2nd scan from an UNGUARDED entrypoint wipes the active scan + double-prices (rate-limit budget)
`scanBegin` (772) calls `scanReset()` **unconditionally** (773). The active-scan guard `if(bpc.scanStatus().active) return` exists on only **2 of 5** scan entrypoints — `maybeAutoStart` and the top `#autoscanBtn` click handler (index.html). The per-row **⚡auto** button handler (`.mr-auto` → `priceViaExtension`), the picker **Autoscan** (`priceRaresCustom`) and picker re-search (`priceRareCustom`) have **no** guard. (R4S-3 saw this as "graceful"; the load-bearing cost is the doubled trade call.)

**P4/P4b (live):** full autoscan active (`scan.order` = 12 rows); mid-scan `priceViaExtension('2')` on a row the first scan **already sent**:
- **`scan.order` collapses 12 → 1** (`BUG_sessionCollapsed`) — `scanReset` wiped the first session; its remaining rows keep filling (chunk closures are per-call) but their chips/`ahead` counts are dead, and the progress bar restarts at 1/1.
- **Row '2' was sent to the extension twice** (`sends_for_victim = 2`) → **2 real trade searches for one item**. The picker-Autoscan-mid-scan variant re-sends *every* remaining rare → up to **2× a whole scan's** on-IP search+fetch budget. Rate-limit discipline is load-bearing (CLAUDE.md: violations → temporary IP bans).
- `cachePost` (678-691) has **no dedup**, and P2 already shows a `foldBatch` POSTs — so each of the two overlapping folds POSTs the shared row = duplicate KV writes (against the D-0009 per-IP daily write budget). (My manual reply delivery captured one POST cleanly; the duplicate follows from the code — cachePost is called per foldBatch with no guard.)

**Fix:** guard every scan entrypoint on `scanStatus().active` (or serialise), and/or make `scanBegin` merge rather than `scanReset` a live session.

---

## F4 (MINOR) — rapid league/status changes wipe the in-flight scan + fire overlapping ungated re-fetches
`setControl('status'|'league')` → `rerun()` → `start()` → `reset()`/`scanReset()` (106-107, 408). No debounce, no generation guard.

**P5 (live):** with a 12-row scan active, three quick control changes → **`scan.active` false, `order` = 0** (the in-flight autoscan **silently dies** while the user believes it's still scanning) and **4 overlapping `/api/build` re-fetches** race with the same last-writer-wins exposure as F1a. Graceful only by luck here (rerun re-fetches the *same* build, so the render stays coherent); the wasted fetches + killed scan are the cost. Same root cause / same fix as F1.

---

## Convergence
This round is **not** dry. It elevates a previously-"minor/graceful" cluster (R4S-2/R4S-3) to a **major** cross-build defect — wrong-build render and **shared-cache poisoning** — because those were only ever tested build-identical, and adds a genuinely new precedence bug (F2). All four findings collapse to **one** fix: a per-build generation token gating async continuations, plus a consistent scan-active guard and a cache-precedence check in `applyPrice`. Recommend fixing, deploying, then re-sweeping (LOOP-UNTIL-DRY: two clean rounds needed).

**Scope note (D-0020 hard criteria):** this is the race lens; I did **not** re-measure scan-duration / hands-free fruition (validated R2/R5) to conserve trade budget and because the mock-bridge probes don't exercise real limiter timing. Flagging for the coordinator, not fabricating numbers.

**Provenance / stability:** live `assets/core.js` was **stable throughout the run** (re-fetched at the end, byte-identical to the start snapshot), so every probe reflects one consistent deployed version; all core.js line refs are validated against that snapshot. Note: partway through, the **local** working-copy `core.js` **diverged** from live (a concurrent campaign process editing it) — live/deployed is unchanged and is what all evidence targets; index.html handlers are referenced by name because that file was also being edited locally during the run.

**Artifacts:** `…/scratchpad/r6race/{driver.mjs,p4b.mjs,results.json,p4b.json,prog.log}`; live core.js snapshot `…/r6race/live_core.js`.
