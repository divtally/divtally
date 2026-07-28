# R6 — RE-VERIFY 1 (independent re-run of the R6 fixes, incl. the F1 race fix)

**Date:** 2026-07-28 · **Scope:** re-verify `docs/bugtest/r6-fix1.md` in full — both the security **S1**
XSS chain (Legs A/B/C) **and the F1 concurrency (generation-token) MAJOR that landed later in the same
fix doc** — with fresh, independent harnesses. Injection fixtures re-driven live; race scenarios re-run
**because a race fix landed**, and proven non-vacuous by an own negative control.
**Trade rule honoured:** ZERO pathofexile.com calls. Site served read-only from `127.0.0.1`; overrides,
rollover, race scenarios, and the negative control all run fully offline (node vm / local Chrome).
**Rig (disjoint):** `…\scratchpad\r6rv1\` — `xss_probe.mjs`, `overrides_probe.mjs`, and a `site\` copy of
core.js/test_scanstatus.mjs/index.html used for the mutation negative-control. Edits: this file only.

> Supersedes the earlier draft of this file (07:33), which was written **before** the F1 race fix was
> added to `r6-fix1.md` and therefore listed F1 as an open carry-forward. F1 is now fixed and re-verified
> below. The prior draft's S1/header/rollover/linter conclusions are reproduced and still hold.

## Verdict: **PASS — every R6 fix (S1 XSS + F1 race) re-confirmed present, correct, and NON-VACUOUS.** No regression.

One honest carry-forward remains (a pre-existing MINOR the fix deliberately scoped out): the popup.js
self-XSS (S3 / firefox R6-1). Flagged below for the coordinator, not softened.

---

## 1. Project harnesses (offline, node) — ALL GREEN
| Suite | Result |
|---|---|
| `public/site/test_picker.mjs` | **98 / 0** |
| `public/site/test_scanstatus.mjs` | **131 / 0** (incl. the 3 new race scenarios) |
| `public/site/test_security.mjs` | **27 / 0** (durable S1 regression lock) |
| `public/worker/worker.test.mjs` | **55 / 0** |
| `extension/test_protocol.mjs` | **PASS** (all checks) |

core.js executes and the index.html inline `<script>` parses cleanly (compile-check in scanstatus passes).

## 2. F1 race fix — PRESENT, and PROVEN NON-VACUOUS by an independent negative control
The generation token is in the working tree: `genSeq`/`state.gen` stamped in `reset()`, captured as
`var gen = state.gen` in `start()`/`priceRowsViaExtension`/`cacheReadThrough`, and **8** occurrences of
`if (gen !== state.gen) return;` guarding every async continuation (build fetch `.then/.catch`, cache
read-through fold, `foldBatch` cache-POST choke point, `nextChunk`).

The three race scenarios (`scenarioRaceBuildSwap` F1a, `scenarioRaceZombieScan` F1b,
`scenarioScanEntrypointGuard` F3) pass in-tree (part of the 131). To prove they are not vacuous, I copied
core.js into the rig, **neutralised every gen guard** (`sed 's/gen !== state.gen/false/g'`, 8→0), and
re-ran the identical suite:
```
FAIL: F1a: the late build-A reply is dropped — B stays rendered   (got "AAA", want "BBB")
FAIL: F1a: still only B's one item counted — A did not fold in     (got 2,     want 1)
FAIL: F1b: B's Headhunter price NOT folded to 999                  (got 999,   want 14613)
FAIL: F1b: B's row keeps its poe.ninja source                     (got "trade", want "poe.ninja")
FAIL: F1b: the zombie scan did NOT POST poisoned entries          (got 1,     want 0)
126 passed, 5 failed
```
With the guards off, **exactly** the finding's damage reappears: wrong-build render (A clobbers B),
cross-build price fold (999c onto B's Headhunter), source overwrite, and a poisoned shared-cache POST.
Restore the guards → 131/0. The fix genuinely closes F1a/F1b; the 5 failing asserts are the ones the fix
targets, nothing more (single-build scenarios stayed green under mutation → no collateral coupling).

## 3. Injection fixtures render safely (S1 Leg A) — live headless Chrome, positive-controlled
Independent `r6rv1\xss_probe.mjs` serves the **current** `public/site` from `127.0.0.1:8811`, drives real
headless Chrome over CDP, and injects the confirmed numeric payloads (201 `meta.level`, 203 `sample_size`,
204 `total_found`, 205 `count`) + the two sibling sinks the fix added (230 `it.level`, 231 `it.sockets`) +
`javascript:`/`data:` URL payloads through `trade_url` (href **and** `window.open`) and `icon` (src), via
the real `loadMock` render path:
```
FIXCHECK {"ctrl_fired":true,"hits":[],"imgOnerror":0,"jsHrefs":0,"badImgSrc":0,
          "openedBad":[],"bSub":"Witch · Level ? · Standard","bSubLevelFallback":true}
```
- `ctrl_fired:true` — the positive control (`<img onerror>` via `innerHTML`) DID fire ⇒ the detector is
  live this run, so the zeros are trustworthy, not a dead harness.
- `hits:[]` — **no** injected payload executed (201/203/204/205/230/231 + all URL payloads dead).
- `imgOnerror:0 · jsHrefs:0 · badImgSrc:0` — no live `img[onerror]`, no `a[href^=javascript:]`, no
  `img[src^=javascript:|data:]` in the rendered DOM (global scan catches any leaked sink).
- `openedBad:[]` — the slot-click `window.open` never fired with a non-pathofexile URL.
- `bSub:"… Level ? …"` — the `meta.level` sink **rendered** and coerced to its `?` fallback (neutralised,
  not merely absent). The 12 `safeHref`/`safeIcon` sink guards are all present in the current index.html.

## 4. Data-origin override gating (S1 Leg B) — 6/6 (offline)
`r6rv1\overrides_probe.mjs` (real core.js in a vm, controllable `location` + captured fetch): prod
(`divtally.com`, `divtally.pages.dev`) **ignores** `?api/?stub/?worker` and uses the configured backend;
dev (`127.0.0.1`, `localhost`) still honours them. **6/0.** The S1 delivery vector is closed in production.

## 5. Header / rollover / linter checks — reproduced from the 07:33 draft, still hold
- **Leg C `_headers`** — well-formed Cloudflare Pages syntax; all five hardening headers present; CSP
  `connect-src`/`img-src` allowlist == exactly what the site loads (API + worker; poecdn only). Honest
  unchanged tradeoff: nonce-less inline script keeps `script-src 'unsafe-inline'` (Legs A+B already make
  the injection impossible). *(Static check — fix not yet deployed, so no live GET.)*
- **addons-linter** `@10.9.0` on `divtally-extension-firefox-1.2.1.zip` → **errors 0 / warnings 3, exit 0**
  (benign `BACKGROUND_SERVICE_WORKER_IGNORED` + 2× popup.js `UNSAFE_VAR_ASSIGNMENT`). Nothing predicts AMO
  rejection.
- **Rollover** — `rollover_harness.py` reproduces `r6-rollover.md`: `current_challenge_league()`→'Redemption'
  auto-heal (both retained/gone variants); gone-worst-case raises a clean `PoeNinjaError` (fail-safe, no
  crash/wrong price). Only the bounded M1/M2 minors, unchanged (rollover paths are Python `_lib`, untouched
  by the JS fix).

---

## Honest carry-forward (NOT a re-verify failure; a pre-existing MINOR, scoped out of r6-fix1)
- **popup.js self-XSS (S3 / firefox R6-1) — still open.** `extension/popup.js:9` `setOut()` writes
  `innerHTML`; lines 57-58 concatenate `parsed.league` (user-pasted) + `r.amount`/`r.currency` (trade JSON)
  raw. r6-fix1 fixed only the S1 blocker + F1; this MINOR was intentionally deferred. Threat is low
  (extension-popup self-XSS: attacker inputs are the user's own pasted string, or GGG's controlled-vocab
  currency response), and it stays a linter **WARNING**, not an error → does not block AMO. Fix remains:
  escape before `innerHTML`, or build the price line with `textContent`. Surfaced, not softened.

**Bottom line for convergence:** the R6 fixes hold under independent re-run; the two race regressions and
the S1 injection chain are both demonstrably closed (and the race guards proven non-vacuous). The single
open item is a known, deferred MINOR — no new functional bug was found in this re-verify.
