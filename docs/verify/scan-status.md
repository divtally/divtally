# Adversarial verification — v1.1 live scan-status round (2026-07-27)

Verifier: scan-status verify agent. Scope honored: reads only inside
`C:\scripts\buildpricechecker-poe1`; no pathofexile.com calls; no deploy; no git state changes.
Only file created/modified: this one.

**Verdict: PASS.** The v1.1 per-item progress protocol is implemented conformantly on both sides,
the D-0012 chunking is preserved, both compatibility directions degrade gracefully, the
auto-scan-on-load toggle **cannot loop** (BLOCKER cleared), the popup still works, all JS
`node --check`s clean, both store zips are 1.1.0 with the progress code and dev files excluded, and
`?mock` renders every new control. Three MINOR findings below — none functional-blocking for the
v1.1 round.

---

## 1. Protocol conformance (extension emit ↔ site consume) — CONFORMANT

Read both sides + ran both harnesses.

- **Message shape.** background `emitProgress` sends `{type:"bpc-price-progress", reqId, key, stage,
  detail}`; content.js relays verbatim as `{source:"bpc-ext", type:"price-progress", reqId, key,
  stage, detail}`; core.js consumes exactly that in the bridge `message` listener. Field names match
  the pin byte-for-byte.
- **Stages.** Emitter produces `queued|searching|fetching|waiting|done|nobuyout|error`; each `detail`
  matches the pin (`waiting{waitMs}`, `done{total,amount,currency}`, `nobuyout{total,fetched,nulls}`,
  `error{message,status}`, others `{}`). Site handles all 7 + its own injected `scanning` in
  `chipHTML`/`scanSnapshot`.
- **Debug object.** Every `price-result` element carries `debug:{searchStatus,fetchStatus,fetched,
  nulls}` (attached in `priceMany` for priced/nobuyout/error alike via `snapshotDebug`). Site folds it
  into the row note (`debugSuffix`) + keeps raw on `price.debug`. This is the owner's mystery-solver:
  `fetched:N,nulls:N` (fetch 200) vs `fetched:0` distinguishes "no buyout among real listings" from
  "search matched nothing".
- **Version gate.** `protoAtLeast(msg.protocolVersion,1,1)` AND `sender.tab.id!=null` required to
  build `ctx`. Number `1.1` (what the site sends) and strings `"1.1"/"1.1.0"` all pass; `"1.0"/"1"/
  undefined` fail. Popup (no `sender.tab`) → `ctx=null` → zero progress, pricing unaffected.
- **Routing.** Progress accepted only when `scan.active && scan.reqIds[reqId]` (reqId belongs to the
  live scan) and `scan.order.indexOf(key)>=0` (inside `scanSet`). Each chunk registers its reqId;
  `scanReset` clears them per build/scan. Per-tab isolation holds (progress goes to `sender.tab.id`).
- **Harnesses:** `extension/test_protocol.mjs` → 35/35 PASS (exit 0). `public/site/test_scanstatus.mjs`
  → 47/47 PASS (exit 0). Both are genuine (load the real source into stubbed realms and assert exact
  event sequences, gating, debug, and the OLD-extension degrade path).

## 2. Regression hunt

- **D-0012 chunking untouched (verified verbatim).** `CHUNK=3`, per-chunk timeout
  `30000 + 30000*len`, sequential `nextChunk().then(nextChunk)`, "a failed chunk never blocks the
  rest", per-chunk cache POST — all present. Site test asserts 2 msgs sized `[3,1]`, sequential. The
  v1.1 additions (`scanBegin/scanEnd`, `protocolVersion:1.1`, reqId registration, per-chunk `keys`
  fallback) are strictly additive around it.
- **old-ext / new-site:** page still sends `protocolVersion:1.1`; old worker ignores it → no progress;
  rows sit at generic `scanning` and resolve from the chunk reply. Prices + nobuyout + error all still
  surface (no debug tail). Proven by `scenarioOld`.
- **new-ext / old-site:** old page sends no `protocolVersion` → `protoAtLeast(undefined)=false` →
  `ctx=null` → no progress; `price-result` unchanged; the added `debug` field is ignored by an old
  page (additive). Proven by the gate + `protoAtLeast` units.
- **Auto-scan toggle CANNOT loop (BLOCKER cleared).** Traced every trigger into `maybeAutoStart`:
  `bpc.on('done',…)` (once per build load), tail of `renderManual` (fires on every `manual` emit), and
  the toggle `change` handler. Guards, in order: `_mock` (skips demo) · `!bridge.active` ·
  `!autoAutoOn()` · `scanStatus().active` (respects in-progress scan) · `autoFired.has(buildKey())` ·
  no-unpriced-rows. Critically `autoFired.add(bk)` runs **before** `bpc.autoscan()`. The one
  re-entrancy path — `autoscan → foldBatch → applyPrice → emit('manual') → renderManual →
  maybeAutoStart` — is blocked by **two** independent guards during the run (`scanStatus().active`
  true AND `autoFired.has(bk)`), and after the run by `autoFired` (never cleared this session; not
  cleared by `reset()`, which lives in core.js). No path re-invokes `autoscan` for a build whose key
  is in `autoFired`. Result: at most one autoscan per build identity per session → no trade-API
  hammering from user IPs.
- **Popup still works.** `popup.js` sends `bpc-price` with no `reqId`/`protocolVersion` from a
  non-tab context → `ctx=null` → priceMany runs progress-free, returns `results`, popup renders
  `results[0]`. No `chrome.tabs.sendMessage` is ever attempted for popup requests → no crash. Proven
  by test D1.
- **No collateral.** `git status` shows the round touched only extension/** + site core.js/index.html
  (+ new notes/test). Engine untouched; `worker.test.mjs` 55/55 (the cache path the extension POSTs
  to is intact).

## 3. Build hygiene

- `node --check` clean on background.js, content.js, popup.js, test_protocol.mjs, core.js, sample.js,
  config.js, test_scanstatus.mjs, worker.js, worker.test.mjs.
- Zips `trade-bridge-{chrome-edge,firefox}-1.1.0.zip`: manifest `version:1.1.0`; background.js in-zip
  has `emitProgress`/`protoAtLeast`/`bpc-price-progress`; content.js in-zip relays `price-progress` +
  forwards `protocolVersion`; `manifest.dev.json`, `generate_icons.py`, `test_protocol.mjs` excluded;
  Chrome = `service_worker` only, Firefox = `service_worker`+`scripts`; `testzip()` OK. Both
  `manifest.json` + `manifest.dev.json` at 1.1.0.
- `?mock` served over `python -m http.server`: index/core.js/sample.js/config.js all 200; markers
  `autoscanBtn`, `autoAuto`, `auto-scan on load`, `mr-scanchip`, `scan-fill`, `autoAutoWrap` present.
  (No live pricing exercised — rule-honored.)

---

## Findings (all MINOR — none block the v1.1 round)

**M-1 · D-0013 branding sweep not applied to the shippable ext/site artifacts.** D-0013 (Locked)
mandates the extension be renamed "DivTally Browser Extension" with `manifest name`, `zip filenames`,
and site strings (`"bridge active"→"extension active"`) swept. Only store *copy* was done (commit
031529c). Still on disk/in the zips: `manifest.json name="DivTally - Trade Bridge"` (and
`manifest.dev.json`, `default_title`, popup.html `<h1>PoE1 Trade Bridge`), `index.html` badge text
`"bridge active"`/`"no extension"`, zip names `trade-bridge-*-1.1.0.zip`. D-0013's own note
("Applied post-workflow — site/ext files owned by the scan-status agents at decision time") says the
main agent deferred this because these files were locked by this round. **Impact:** if the owner
builds/submits now, the store shows a name that contradicts his Locked decision → a resubmission to
fix. Out-of-band from the v1.1 protocol, but a real Locked-decision gap the main agent should apply
after this round merges. Fix: main-agent brand sweep + rebuild zips.

**M-2 · `nobuyout` note self-contradicts on a zero-match search.** When the extension's search returns
0 ids, `priceQuery` returns `{total:0, amount:null}` (fetch never runs → `fetchStatus:null,
fetched:0`), and `priceMany` emits `nobuyout{total:0,fetched:0,nulls:0}`. The site (core.js foldBatch)
then writes the fixed note **"listings exist but none had a buyout price"** + debug tail
`[search 200, 0 fetched, 0 w/o buyout]`, and the chip reads "no buyout among 0 listings". The prose
"listings exist" is false when 0 matched, and now visibly contradicts its own "0 fetched" tail. The
base note predates v1.1; the debug tail newly exposes the contradiction. Fix hint: branch the note on
`total===0` → "no matching listings found" vs the existing wording. Low impact (debug still
disambiguates; the owner's actual mystery is the `total>0` path, which reads correctly).

**M-3 · A progress-`done` row can end "✓ priced" yet contribute no number if the final reply is
lost.** foldBatch's unresolved-key sweep (core.js ~L807) skips any key where `scanResolved(key)` is
true. If a per-item progress `done` already marked a row terminal but that key is absent from the
final `price-result` (the reply arrived after the chunk's `30000+30000·len` timeout deleted
`pending[id]`, or the MV3 worker was killed after emitting progress but before `sendResponse`), the
row is skipped → `applyPrice` never runs → the chip stays "✓ priced" (progress) while the total omits
it and no error shows. Narrow trigger (progress landed but the same-batch reply did not — realistic
only on a mid-chunk worker kill), recoverable (user can re-price), and it neither loops nor hammers
the API. Fix hint: gate the sweep short-circuit on "resolved **and** actually priced" (e.g. check
`state.priced[key].chaos.median!=null`) so a done-without-number row falls through to the error
fallback.

## Housekeeping (not findings)
- `docs/notes-scan-status-site.md` and `public/site/test_scanstatus.mjs` are untracked; the main
  agent commits before/at deploy. (`notes-scan-status-ext.md` and the v1.1 source are already
  committed — working tree matches HEAD for those, so what was verified is what will deploy.)
