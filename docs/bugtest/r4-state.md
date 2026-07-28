# D-0020 Round 4 — STATE-MACHINE ABUSE sweep (LIVE, 2026-07-28)

Lens: break the UI state machine like a hostile / unlucky / impatient user on the **live** site with
the **real** extension. Bar = graceful degradation; a crash, silent-wrong state, or stuck UI is
major+. This is a distinct lens from the same-day `r4-offline.md` (PoB / API-down / pure-whisper /
worker) — no findings overlap except where noted (whisper, which this round confirms **live**).

**Under test:** LIVE `https://divtally.com/?v=r4state*` + unpacked extension
`C:\scripts\buildpricechecker-poe1\extension` (**v1.2.1**, bridge `active:true` both runs), real
Chromium via Playwright persistent context (1300×950, headless:false).
**Build:** smallest owner build **SergoheroGaz** (`Sergohero-2699/SergoheroGaz`, Allflame; 29 items,
**9 scan rows** = 6 rare + 3 magic + 1 variant unique Lethal Pride).
**Trade footprint:** the ONLY pathofexile.com traffic was the extension's own limited calls — ~3
small SergoheroGaz scans (one clean, one overlap, one double-appraise-orphaned) + 1 single-row
picker re-scan. **0 pageerrors, 0 `429`/rate errors, 0 stuck-non-terminal rows in any clean scan.**
Drivers + raw capture (scratchpad, not repo): `r4state_driver.mjs` / `r4state_driver2.mjs`,
`r4state_results.json`, `r4state2_results.json`, `*_prog.jsonl`. Profiles: `scratchpad\r4state`,
`scratchpad\r4state2`.

Every number below is **source-derived** (a live `bpc.scanStatus()` / `bpc.totals()` reading, the
rendered DOM, captured console/pageerror, or the actual site source) unless tagged `[DERIVED]`.

---

## 0. Verdict (read first)

The gentle mid-scan abuses the task named are all **graceful**: rapid MIN/HIGH tier flips, the
weapon-swap toggle, and the pick-affixes toggle mid-scan never crashed, never spawned a second
session, never stranded a row — the scan stayed active and completed hands-free (28.6 s, 0 stuck,
0 errors). Hard-refresh mid-scan recovers cleanly (no zombie scan UI, recents intact), and
re-appraise-from-Recents correctly serves priced rows from the community cache with **no re-scan**.

Four state-machine defects surfaced, one MAJOR:

| # | Sev | Area | One line |
|---|-----|------|----------|
| **R4S-1** | **MAJOR** | corrupt-LS self-heal | A valid-JSON *wrong-type* `bpc_recent_builds` (string/number/object) makes **every build load end in a false "Could not reach the pricing service" error** with the manual-pricing panel dead — persists across reloads. Unparseable garbage self-heals; wrong-type does not. |
| R4S-2 | minor | double Appraise | Double-clicking **Appraise** fires two `/api/build` loads with no generation guard; the 2nd load's `reset()`→`scanReset()` **orphans the autoscan** → it runs **invisibly** (totals climb, `priced 20→22`) while the progress bar sits idle on "⚡ Autoscan" and `scanStatus().active=false`. Prices still land; the scan-progress instrument is silently dead. |
| R4S-3 | minor | picker × scan | A rare's picker **"Search this item"** fired mid-autoscan calls `scanBegin`→`scanReset()` on the single **global** `scan` object → the row is scanned **twice** (wasted trade + last-writer-wins on its price) and the old session's `scanEnd()` terminates the new session's `active`. Observed graceful (no stuck/crash), but a latent stuck-row path. |
| R4S-4 | minor | whisper (live) | **Live-confirms `r4-offline.md` R4-5/6/7 in the real headline**: `1,000 chaos`→**0**, `35,5 chaos`→5, `1e309 chaos`→309 fold a silent wrong number into the total; `99999999999999999999 chaos`→**1e20 uncapped**; `-5 chaos`→+5. XSS-safe, no throws/ReDoS. |

No **blocker** (no clean scan stuck/errored; the app never white-screened). One **major**
(R4S-1: silent-wrong / misleading persistent state from storage corruption).

---

## 1. R4S-1 (MAJOR) — corrupt `bpc_recent_builds` self-heals for garbage but NOT for wrong-type

The task requires: *"corrupt localStorage keys … then reload — the app must self-heal, not
white-screen."* The **literal** case passes; a nastier valid-JSON case does not.

**Self-heal PASS (landing render, driver1 P0):** `bpc_recent_builds = "}{ not json"` (unparseable) +
`bpc_status_v2 = "zzzz"` → reload → `state.recent` heals to `[]` (Array), `state.status` heals to
`available`, form present, **0 pageerrors**. `loadRecent`/`loadPrefs`' `try/catch` + the
`STATUS_LABEL[s]` guard handle it. ✔

**Self-heal FAIL — wrong-type (the finding):** the parse `try/catch` only catches a *throw*, never a
wrong *type*. `JSON.parse` of a non-array succeeds, so `state.recent` becomes a string / number /
object. Two escalating symptoms, both live-reproduced:

- **Landing (driver1 P0):** `bpc_recent_builds = '"hello"'` → `state.recent = "hello"` →
  `renderRecent` runs `recentData.filter(…)` → **`TypeError: recentData.filter is not a function`**
  (console.error via the `emit` wrapper; recents don't render). `'[1,2,3]'` → renders **3 junk
  portraits** (`data-k="undefined"`, click = no-op). Page survives (form present, not a white-screen)
  but is visibly wrong.
- **Build load (driver2 TC) — the real damage:** with a wrong-type `bpc_recent_builds` set, loading
  the build calls `pushRecent()` at `core.js:1264` → `(state.recent || []).filter(…)` throws
  (`"hello".filter` / `42.filter` / `{k:1}.filter`) **inside `loadBuild`**, which runs
  `pushRecent → restoreManual → cacheReadThrough → emit("manual") → emit("done")` in sequence. The
  throw aborts the tail, so **`emit("manual")` and `emit("done")` never fire** (manual panel stays
  empty, autoscan never arms) and the exception unwinds to the fetch chain's `.catch` →
  `fail("Could not reach the pricing service…")`.

  **Live result (all 3 wrong-type values):** `phase=error`, `errbox="Could not reach the pricing
  service. Check your connection, or try ?mock for a demo."`, `items=29` (board half-painted),
  `#manualRows` count **0**. `falseError=true`, `broken=true` for `"hello"`, `42`, and `{"k":1}`.

The error **blames the network for a storage bug**, the build is half-rendered but unpriceable, and
**a reload does not clear it** (localStorage persists) — the user is stuck until they manually wipe
storage. Silent-wrong + misleading + persistent = MAJOR by the round's bar.

**Trigger probability:** today the app only ever *writes* an array to `bpc_recent_builds`, so a
wrong-type value arises only from external corruption (a buggy co-installed extension, profile-sync
mangling, devtools tampering) or a **future** schema change to that key — not a normal in-app path.
Real-world likelihood is low, but this is exactly the robustness the round probes, and the fix is
trivial.
**Fix:** coerce on read — `state.recent = Array.isArray(parsed) ? parsed : []` in `loadRecent`; and
harden `pushRecent` to `Array.isArray(state.recent) ? state.recent : []`. (Same class as the
`bpc_status_v2`/`bpc_tier`/`bpc_manual` keys, which are already type-safe — only `recent` isn't.)

## 2. R4S-2 (minor) — double-click Appraise orphans the scan-status UI (no generation guard)

`#f` submit → `bpc.startUrl` → `start()`, which has **no in-flight guard**: two rapid clicks on
**Appraise** fire two `start()` calls, each `reset()`s state and issues its own `/api/build` fetch.
Live (driver2 TD): **2 `/api/build` GETs** (no dedup); then the second load's
`reset()`→`scanReset()` wipes the scan session the **first** load's autostart already began. The
first autoscan's chunk recursion lives in its own closure, so it **keeps folding prices** — but into
a session the UI can no longer see:

- `scanStatus().active = false`, `order = []` (total 0) the entire watch window, bar frozen on
  **"⚡ Autoscan"** (the idle label), **yet `totals().priced` climbed 20→22** (invisible scan). Cache
  was opted out this phase, so the climb is the extension, not a cache fill.
- No crash, no pageerror; the build ends correctly priced. The **scan-progress instrument** (a
  D-0020 hard-criteria feature) is just silently dead, and `autoFired` now blocks a clean autostart
  restart (the `#autoscanBtn` still works manually).

Degrades to "functional but invisible" → **minor**. Code-evident (not live-tested) worse variant:
because the last fetch's `.then` wins the render with no generation token, submitting **two
different URLs** quickly could render build A after B was requested last. **Fix:** ignore a second
submit while `phase==='loading'`, or stamp a generation id so a stale load can neither reset nor
render over a newer one.

## 3. R4S-3 (minor) — picker "Search" mid-autoscan shares one global scan session

`doPickerSearch` → `bpc.priceRareCustom` → `priceRowsViaExtension` → `scanBegin` → **`scanReset()`**
operates on the module-global `scan` object, so firing a rare's **"Search this item"** while an
autoscan runs starts a *second* session over the *same* global state. Live (driver2 TA, fired on
rare key 17 at +0.2 s into a 9-row scan):

- **Observed graceful:** `activeFlips=1` (normal end), `flapped=false`,
  `inactiveWithUnresolved=false`, **0 stuck rows, 0 errors**, drained clean. The overlapped row was
  also in the autoscan's own `order`, so the autoscan's reply resolved it — no strand.
- **But the hazards are real:** (a) the row is **scanned twice** (autoscan query + picker query =
  wasted trade, and **last-writer-wins** on its final `state.priced[key]` — a strict-autoscan
  nobuyout can overwrite the user's refined picker price or vice-versa, non-deterministically);
  (b) the old session's `scanEnd()` flips the **new** session's `active=false` (cross-session
  termination); (c) code-evident stuck-row path not hit here: fire the picker search on a row the
  autoscan has **already resolved**, and the old `scanEnd` marks the new session done while that
  row's reply is still pending → `scanSet` (guarded on `scan.active`) drops it → chip stuck though
  the price folds.

Live behavior was graceful, so **minor**, but the single-global `scan` is a latent state-hygiene
defect. **Fix:** per-session scan tokens (an id captured in each `nextChunk`/`scanEnd` closure so an
old session can't terminate a newer one), and skip rows already in an active session's `order`.

## 4. R4S-4 (minor) — whisper fuzz, LIVE headline confirmation of r4-offline R4-5/6/7

The task's "fill the whisper box with the fuzz classics on a real row" run (driver2 TB, 24 inputs on
a real unpriced rare, folding into the live total). No new *class* beyond `r4-offline.md` Task 3, but
those pure-parser findings are now **confirmed in the rendered headline**:

| Input | Live result | = offline |
|---|---|---|
| `1,000 chaos` / `1 000` / `1.000.000` / `1'000` | folds **0** chaos (`price "0.0"`, `method whisper`, included) — regex matches the digits *after* the separator | R4-5 |
| `35,5 chaos` (euro decimal) | folds **5** | R4-5 |
| `1e309 chaos` / `1e6 div` | **309** / **6 div** (sci-notation not matched; grabs the trailing digits) | R4-5 (family) |
| `99999999999999999999 chaos` | **1e20** folded uncapped → headline shows `834,028,356,964,136,700 div (100,000,000,000,000,000,000 chaos)` (site has **no cap**; worker caps at 1e8) | R4-6 |
| `-5 chaos` | **+5** (the `amount<0` guard is unreachable) | R4-7 |
| `<script>…` / `<img onerror=…> 5 chaos` | `<script>`→null (unpriced); `<img>`→parses `5 chaos`, **`window.__xss` never set** | XSS-safe ✔ |
| `''`, `NaN chaos`, `Infinity chaos`, `1/0 chaos` | all → null, row stays unpriced ✔ | robust |
| 6008-char string + `7 chaos` | parses `7`, no throw, no ReDoS (instant) ✔ | robust |

`xssFired=false`, 0 pageerrors across all 24 inputs. The silent-wrong-number cases (`1,000`→0 into a
"medium"-confidence total) are the substantive ones — see r4-offline R4-5 for the fix (strip/reject
grouping separators; cap the amount).

---

## 5. What PASSED (graceful under abuse — recorded)

- **MIN/HIGH tier flipped ×10 rapidly at scan start** → scan stayed `active`, `tier=high`, **0
  errors**; the display moved (this build has a real spread: min 28,677.5c / median 28,679.5c / high
  28,692.0c). ✔
- **Weapon-swap toggle on/off mid-scan** → scan stayed active both states, **same session `order`**
  (no second scan spawned), 0 errors. ✔
- **Pick-affixes toggle on/off mid-scan** → scan stayed active, no modal stuck, 0 errors; toggling
  off calls `maybeAutoStart` which correctly no-ops (`autoFired` + active-scan guards). ✔
- **Hands-free fruition under the gentle abuses** → all 9 rows terminal, **0 stuck**, hands-free
  completion `totalMs = 28,604` (6 priced incl. Hypnotic Ruin 839.3c, Lethal Pride 119.9c, Kraken
  Star 5c, Cataclysm 30c; 3 honest nobuyout), 0 pageerrors. ✔
- **Hard-refresh MID-SCAN** (during the orphaned invisible scan, `priced=22`) → reload lands
  `phase=idle`, **`scanStatus` empty (no zombie scan UI)**, `#manualRows` empty, board gone, **recents
  intact (1 portrait)**, 0 pageerrors. Scan state is in-memory only, so refresh can't leave a zombie.
  ✔
- **Re-appraise from Recents (cache path)** with autostart off → **5 rows served from the community
  cache** (`source:"cache"`), **`tradePriced=0`, `scanOrderLen=0` — no re-scan**; the 4 uncached
  nobuyout rares correctly stay manual (`needsScan`). "Should not re-scan already-priced rows"
  holds. ✔
- **XSS / injection / DoS** via the whisper box → none (see §4). ✔

## 6. Method / reproduction

1. `chromium.launchPersistentContext(profile, {headless:false, args:['--disable-extensions-except=
   <ext>','--load-extension=<ext>','--no-first-run','--no-default-browser-check']})`, ext v1.2.1.
2. **P0 / R4S-1 landing:** set `bpc_recent_builds` (5 shapes) + `bpc_status_v2`, reload, read
   `state.recent` type / `state.status` / pageerrors / portraits.
3. **P1 gentle mid-scan:** single Appraise → autostart; while `active`, click
   `#btSeg [data-tier]` ×10, `#swapInc` on/off, `#pickAffixCb` on/off; poll `scanStatus()`; drain.
4. **TA overlap (R4S-3):** during a fresh full scan, click a rare's `.mr-affix` then
   `#pickwrap.show [data-pk="search"]`; dense-poll 28 s for active-flap / stuck rows.
5. **TB whisper (R4S-4):** 24 fuzz inputs into a real `.mr-input` + `.mr-apply`; read
   `state.priced[k]` / `totals()` / `window.__xss`; `clearManual` between.
6. **TC corrupt-load (R4S-1):** set `bpc_recent_builds` to `"hello"`/`42`/`{"k":1}`, reload,
   Appraise, read `phase`/`#errbox`/`#manualRows`.
7. **TD/TE double-Appraise + refresh (R4S-2):** double-click `#go`, watch `/api/build` count +
   `scanStatus` + totals; then `page.reload()` mid-scan and assert no zombie + recents.
8. **TF recents cache path:** `bpc_autoscan_auto='0'`, click `#recent .portrait`, read
   `manualRows()` source per row.

**Trade footprint:** ~3 SergoheroGaz scans + 1 single-row picker re-scan, all by the extension under
its limiter; **0×429**, 0 aborts, 0 pageerrors. Mid-scan abuse necessarily requires live scans; kept
to the one small build (D-0020 "one small build scan + brief re-scans").

## 7. Recommended fix order
1. **R4S-1** (type-coerce `bpc_recent_builds` on read + guard `pushRecent`) — cheap, kills a
   misleading persistent-broken-state class.
2. **R4S-2** (generation guard on `start()` / ignore submit while `loading`) — kills the invisible
   double-appraise scan and the stale-render race.
3. **R4S-3** (per-session scan token; dedupe in-flight rows) — removes the shared-global scan hazard.
4. **R4S-4** → see `r4-offline.md` R4-5/6/7 (strip grouping separators, cap the whisper amount, drop
   the dead negative guard).

R4 (state lens) found **1 major + 3 minor** → the campaign is **not dry** (D-0020 LOOP-UNTIL-DRY).
