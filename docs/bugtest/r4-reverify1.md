# D-0020 Round 4 — fix re-verify 1 (2026-07-28)

Independent re-verification of the five R4 blocker/major fixes recorded in `r4-fix1.md`
(R4-4, R4-1, R4-2, R4-5, R4S-1). Method: full harness suite + a fresh hermetic PoB parse probe +
a real-Chromium (Playwright) re-check of the three browser-observable regressions against the
**fixed** `core.js` served locally. No pathofexile.com traffic (all fixtures / local stubs; the
one live-API allowance was not needed — the previously-failing browser scenarios are exercised
with a local hang-server and a local mock-API returning a canned build doc).

**Verdict: all five fixes CONFIRMED. No regressions. No new findings.**

Rig files (scratchpad `r4rv1`, not repo): `probe_pob_rv.py` (parse-layer R4-1/R4-2),
`srv_rv.py` (127.0.0.1 static+hang+mock server), `driver_rv.mjs` (Playwright), profile `r4rv1/profile`.

---

## 1. Harness suite — all green (re-run)
| harness | result |
|---|---|
| `python tests.py` | All self-tests passed |
| `python public/api/_verify.py` (phase A offline) | ALL CHECKS PASSED |
| `node public/site/test_scanstatus.mjs` | **106 passed, 0 failed** (incl. the +3 R4 scenarios: build timeout, whisper separators, recent coercion) |
| `node public/site/test_picker.mjs` | 98 passed, 0 failed |
| `node public/worker/worker.test.mjs` | 55 passed, 0 failed |
| `node extension/test_protocol.mjs` | PASS |

## 2. Code presence & twin-sync (audited)
- `core.js`: `BUILD_TIMEOUT_MS` (default 45 s, `?buildTimeout` override) + `AbortController`+timer+
  `settled` de-dupe in `start()` (R4-4); grouping-separator rejection in `parseWhisper` (R4-5);
  `Array.isArray(parsed)?parsed:[]` in `loadRecent` + `Array.isArray(state.recent)?…:[]` guard in
  `pushRecent` (R4S-1). All present.
- `public/api/_lib/pob.py` ↔ `bpc/pob.py`: the two twins differ **only** in the module docstring /
  abbreviated comments (the vendored copy carries a "VENDORED VERBATIM" note); every functional
  line is identical — `_SLOT_MAP` swap entries, the `slot == "Weapon 2"` off-hand gate,
  `swap_inv` gem flagging, and `corrupted = (lvl > 20 or qual > 20 or gc in (...))` match verbatim.

## 3. R4-1 + R4-2 — hermetic PoB parse re-verify (`probe_pob_rv.py`, ALL PASS)
A synthetic PoB XML (L21 gem in a **Weapon 1 Swap** skill; L20/Q23 gem in the main **Weapon 1**;
L20/Q10 gem in **Body Armour**; a main bow + a swap bow) fed straight through the real
`public/api/_lib/pob.parse` with the bundled `refdata.item_types()`. No network.
- **R4-1 (gem corruption):** L21 gem → `corrupted=True`; L20/Q23 gem → `corrupted=True`;
  L20/Q10 gem → `corrupted=False` (selective — only the corrupt ones flip).
- **R4-2 (weapon-swap flag):** only the Weapon-1-Swap gem carries `inventoryId="Weapon2"` (swap);
  the main-hand and body gems carry no swap id. The swap-weapon gear item → `Weapon2`; the
  main-hand weapon → `Weapon` (not swap). Exactly what `response._is_swap` + the site's swap
  toggle key on, so D-0018 exclusion now applies on the PoB path.

## 4. Browser re-checks (Playwright, fixed `core.js` served on 127.0.0.1:8871)
### R4-4 (blocker) — hung API no longer stalls the UI — CONFIRMED
`?api=<hang-server:8872>&buildTimeout=4000`, hang server accepts the TCP connection and never
replies. Result: `phase → error` at **4066 ms** (the timer firing, not a connection error) with
`#errbox` = *"The pricing service took too long to respond…"*, **0 pageerrors**. Previously the
page sat in `loading` forever. Fixed.

### R4S-1 (major) — corrupt `bpc_recent_builds` self-heals — CONFIRMED
Set the LS key before scripts run, reload against the local mock-API (returns a valid build doc
with a real `source_url`, so the build load runs the exact `pushRecent` filter that used to throw):

| corrupt value | landing `state.recent` | build load | false network error | pageerrors |
|---|---|---|---|---|
| `"hello"` (string) | array, len 0 | **phase=done** | no | 0 |
| `42` (number) | array, len 0 | **phase=done** | no | 0 |
| `{"k":1}` (object) | array, len 0 | **phase=done** | no | 0 |
| `}{ not json` (unparseable) | array, len 0 | **phase=done** | no | 0 |
| `[{…legit…}]` (valid array) | array, len **1** (char "Keep" preserved) | — | — | 0 |

Both symptoms gone: no `renderRecent`/`pushRecent` throw at landing, and every build load reaches
`done` instead of the persistent false *"Could not reach the pricing service"* error. Legit
recents are untouched.

### R4-5 (major) — whisper separators rejected — CONFIRMED (live, deployed parser)
`window.bpc.parseWhisper` on the loaded page: all five separator inputs return `null` (re-prompt,
no silent-wrong number) — `1,000 chaos`, `1 000 chaos`, `1.000.000 chaos`, `1'000 chaos`,
`35,5 chaos`. All six legitimate inputs still parse: `35 chaos`→35, `1000 chaos`→1000,
`2.5 div`→2.5, `35.5 chaos`→35.5, `1/3 div`→0.333, `~b/o 1500 chaos`→1500.

---

## 5. Notes / residue (out of this round's scope, unchanged — not re-tested as fixes)
The fix round explicitly deferred R4-3 (flat PoB gems / no host-grouping), R4-6 (divine-multiply
upper cap / non-finite guard), R4-7 (dead `amount<0` guard), and the R4S-2/R4S-3 minors
(double-Appraise generation guard, single-global scan session). These remain open per `r4-fix1.md`
and are unaffected by the confirmed fixes above.

## Trade footprint
Zero pathofexile.com calls. PoB probe uses bundled refdata + a synthetic XML; the browser rig uses
a local hang-server and a local mock-API serving a canned response. No live poe.ninja or trade hit.
