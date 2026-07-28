# D-0020 Round 4 — fix round 1 (2026-07-28)

Fixes for the five blocker/major findings from R4's edge/adversarial sweep
(`r4-offline.md` R4-4/R4-1/R4-2/R4-5, `r4-state.md` R4S-1). All harnesses green; contracts
additive (no response field renamed/removed). Bar = graceful degradation: no hang, no silent
wrong number, no stuck/misleading persistent state.

## Suite status (after)
| harness | result |
|---|---|
| `python tests.py` (bpc) | All self-tests passed (+7 new PoB assertions) |
| `python public/api/_verify.py` phase A (offline) | ALL CHECKS PASSED |
| `node public/site/test_scanstatus.mjs` | **106** passed, 0 failed (was 64; +42) |
| `node public/site/test_picker.mjs` | 98 passed, 0 failed |
| `node public/worker/worker.test.mjs` | 55 passed, 0 failed |
| `node extension/test_protocol.mjs` | PASS |
| hermetic end-to-end (`scratchpad/probe_e2e_pob.py`) | ALL PASS (PoB path through real pipeline) |

---

## R4-4 (blocker) — build fetch had no timeout → hung API = permanently stuck UI
**File:** `public/site/assets/core.js` (`start()`).
An API that accepts the TCP connection but never sends an HTTP response (firewall DROP,
half-open/overloaded server, LB gateway timeout) left `fetch(url).then().catch()` pending
forever — the page sat in `phase:"loading"` with the spinner, no error, no recovery
(Playwright: still `loading` after 14 s). The refused/non-JSON/500 cases already degraded in
<3 s; only the *unresponsive* case hung. The extension bridge/chunk paths have timeouts
(D-0012); the build fetch did not.

**Fix:** wrap the build fetch in an `AbortController` + `setTimeout(BUILD_TIMEOUT_MS)`
(default **45 s**, config/`?buildTimeout`-overridable). On timeout → `abort()` + `fail("The
pricing service took too long to respond…")`. A `settled` flag de-dupes so the timeout and a
late reply/abort can never both report. `AbortController` is feature-detected — absent, the
timer still fires `fail()` (degrades without abort). Mirrors the bridge/chunk timeout
discipline. Happy path unchanged (positive control asserts a responsive API still reaches
`done`).

## R4-1 (major) — PoB path ignored gem corruption → ~25 % low on gem-heavy builds
**Files:** `public/api/_lib/pob.py` + `bpc/pob.py` (vendored twins; kept in sync).
`pob.py` inferred `corrupted` only for gear, never for gems. PoB encodes gem corruption
**implicitly** — a corrupted gem is level 21 or quality 23, **no explicit attribute** (verified
across the real export's 35 gems: `L20 Q23 ×2`, `L21 Q20 ×1`, none carrying a corrupt attr). So
every PoB gem came out `corrupted:false`, matching the cheap uncorrupted poe.ninja economy line.

**Fix:** in the gem loop, `corrupted = (level > 20 or quality > 20)` plus an explicit
`corrupted="true"` marker (defensive, for a future/variant export). The gem pricer keys on
`item.corrupted` (`querybuild._gem` → `econ.gem_price(..., corrupted)`; poe.ninja bucket scoring
adds a 100-penalty on corruption mismatch), so a corrupted gem now matches the correct (dearer)
line — parity with the poe.ninja path, which reads corruption from socket data.
**Proof (fixture char):** Faster Projectiles L21, Herald of Agony/Thunder Q23 → `corrupted:true`
in the response and priced with `corrupted=True`; the other 26 gems stay uncorrupted (selective).

## R4-2 (major) — PoB path had no weapon-swap exclusion (D-0018) → totals +136 %
**Files:** `public/api/_lib/pob.py` + `bpc/pob.py`.
The poe.ninja path flags Weapon2/Offhand2 gear `swap` (D-0018: out of totals unless the toggle
re-includes). The PoB path flagged nothing: swap weapons **and their socketed skill gems** were
counted (aurab: ninja 1810.3c vs pob 4280.6c, +2470c), and the toggle couldn't remove them.

**Fix:** the swap flag is `raw.inventoryId in ("Weapon2","Offhand2")` (what `response._is_swap`
+ `_item_row` read). Now:
- `_SLOT_MAP`: `"Weapon 1 Swap" → Weapon2`, `"Weapon 2 Swap" → Offhand2` (was `Weapon`).
- the shield/focus off-hand remap is gated to `slot == "Weapon 2"` (exact) so a **swap** off-hand
  shield keeps its `Offhand2` id instead of being downgraded to `Offhand`.
- the gem loop reads the skill's `slot`; skills in `"Weapon 1/2 Swap"` tag each gem
  `raw.inventoryId = Weapon2/Offhand2`. Swap gems are **emitted** (excluded-by-default,
  toggle-able), matching how swap gear behaves — strictly better than the ninja doc, which omits
  them entirely.
**Proof (fixture char):** 7 swap rows — 2 swap weapons (Maloney's Mechanism→Offhand2,
Thicket Bow→Weapon2) + 5 swap gems; headline total = sum of **non-swap** priced items only
(50c of swap gems excluded; `priced_items` 24 not 29). Including swap would inflate it — the
exclusion is real and non-vacuous.

> R4-3 (minor, structural: flat PoB gems / no host-grouping) is **not** in this round's scope —
> totals are unaffected by it; left for a later pass.

## R4-5 (major) — whisper folded locale/thousands separators into the headline
**File:** `public/site/assets/core.js` (`parseWhisper`).
`"1,000 chaos" → 0`, `"1 000 chaos" → 0`, `"1.000.000 chaos" → 0`, `"1'000 chaos" → 0`,
`"35,5 chaos" → 5`. The regex matched the digit-run *after* the separator and folded that
fragment in as a confident `medium` price. GGG whispers never use separators; only manual entry
does.

**Fix:** capture the matched amount's absolute index, then reject when it is flanked by a
grouping separator (`, . ' ’` / space / NBSP / thin / narrow-NBSP) that itself sits between
digits — i.e. the matched run is a fragment of a separated number. Return `null` →
`applyWhisper` re-prompts with the existing "couldn't read a price" message (never fabricate a
number we can't derive). All five silent-wrong cases now reject; legitimate `35 chaos` /
`1000 chaos` / `2.5 div` / `35.5 chaos` / `1/3 div` / `~b/o 1500 chaos` still parse, and a GGG
whisper carrying stash coords ("left 12, top 3") is not false-rejected (the check is local to the
price, not the whole string).
> R4-6/R4-7 (minor/info: divine-multiply upper cap; dead `amount<0` guard) are out of this
> round's stated five-finding scope — flagged, not changed.

## R4S-1 (major) — corrupt `bpc_recent_builds` (wrong-type) → false persistent "network" error
**Files:** `public/site/assets/core.js` (`loadRecent`, `pushRecent`) + `public/site/index.html`
(`renderRecent` feed).
Unparseable garbage self-healed (`try/catch` → `[]`), but a **valid-JSON wrong-type** value
(string/number/object) parsed fine and became `state.recent`. Then `(state.recent||[]).filter(…)`
in `pushRecent` threw inside `loadBuild`, aborting `emit('manual')`/`emit('done')` and unwinding
to `fail()` — so **every** build load ended in a false "Could not reach the pricing service"
error with the manual panel dead, persisting across reloads. (Also `renderRecent`'s
`recentData.filter` threw at landing for `"hello"`.) Trigger is external corruption/tampering
(the app only writes arrays), low real-world probability — but exactly this round's robustness bar.

**Fix:** type-coerce on read — `state.recent = Array.isArray(parsed) ? parsed : []` in
`loadRecent`; harden `pushRecent` to `(Array.isArray(state.recent) ? state.recent : []).filter(…)`
(defends against mid-session external mutation); and the index.html `recent` handler guards
`recentData = Array.isArray(bs) ? bs : []`. Mirrors the type-safety `bpc_status_v2`/`bpc_tier`/
`bpc_manual` already have. **Proof:** `"hello"`/`42`/`{"k":1}`/`true`/garbage all heal to `[]`
with no throw and an array `recent` event; a valid array is preserved; and a build load
completes to `done` even with `state.recent` forced wrong-type post-load (pushRecent guarded).

---

## Files changed
- `public/site/assets/core.js` — build-fetch AbortController+timeout (+`BUILD_TIMEOUT_MS`
  config), whisper grouping-separator rejection, `loadRecent`/`pushRecent` type-coercion.
- `public/site/index.html` — `renderRecent` feed array-guard.
- `public/api/_lib/pob.py` **and** `bpc/pob.py` — gem corruption inference + weapon-swap
  flagging (identical edits to the vendored twins).
- `public/site/test_scanstatus.mjs` — +3 scenarios (build timeout, whisper separators, recent
  coercion; 64→106).
- `tests.py` — +PoB corruption/swap parse-layer assertions.

## Contract
Additive only. No response field added, renamed, or removed. `row["swap"]` /
`row["corrupted"]` were already emitted by `response._item_row`; the PoB path now populates them
(it did for the poe.ninja path already). Client `includeSwap()` toggle already consumes
`it.swap`. `BUILD_TIMEOUT_MS` is a new optional client config key (default 45 s).

## Verification artifacts (scratchpad, not repo)
`probe_pob.py` (parse-layer flags on the real sample), `probe_e2e_pob.py` (full public pipeline:
parse → price → response, swap-excluded + corruption-flagged). Both trade-free (poe.ninja
fixtures only; no pathofexile.com).
