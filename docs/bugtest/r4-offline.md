# D-0020 Round 4 — offline/duo edge & adversarial sweep (2026-07-28)

Lens: break it like a hostile or unlucky user. Bar = graceful degradation; a crash, silent wrong
state, or stuck UI is major+. Four probes: (1) PoB round-trip cross-diff, (2) API-down grace in a
real browser, (3) whisper fuzz (pure), (4) live-worker abuse. Evidence scripts in the scratchpad
rig (`t1_*.py`, `t2_*.{py,mjs}`, `t3_whisperfuzz.mjs`, `t4_workerabuse.py`); build docs
`doc_{qwartus,aurab}_{ninja,pob}.json`. Live API + worker only; no pathofexile.com calls.

## Scoreboard
| # | Sev | Area | One line |
|---|-----|------|----------|
| R4-1 | **MAJOR** | PoB gems | PoB path drops gem **corruption** → level-21/qual-23 gems priced as uncorrupted → ~25% wrong total |
| R4-2 | **MAJOR** | PoB / D-0018 | PoB path has **no weapon-swap exclusion** → swap gems counted (aurab +136%), swap toggle inert |
| R4-3 | minor | PoB gems / D-0006 | PoB gems are **flat** (no host, `supports:[]`) → host-grouping + support nesting absent |
| R4-4 | **MAJOR** | API-down UI | Build fetch has **no timeout** → a hung (accept-no-reply) API leaves the page stuck "loading" forever |
| R4-5 | **MAJOR** | whisper | Thousands/locale separators silently parse to **0 or wrong** and enter the total ("1,000 chaos" → 0) |
| R4-6 | minor | whisper | Divine→chaos multiply **unguarded**: non-finite/negative `divine_to_chaos` → Infinity/negative chaos; no upper cap |
| R4-7 | info | whisper | Dead `amount < 0` guard (regex never captures a sign; "-5 chaos" → +5) |

**Clean passes (verified, no finding):** live worker abuse (Task 4) — every hardening claim holds;
whisper never throws / no ReDoS / injection-safe; API refused/non-JSON/500/worker-dead all degrade
gracefully; PoB league defaulting + item parity + variant-unique locked-mods round-trip correctly.

---

## Task 1 — PoB round-trip (owner's "corrupted PoB inputs")
Fetched the ninja doc for **qwartus** + **TimeForAurab (yalokk)**, took `meta.pob_code`, POSTed it
back as PoB input, cross-diffed ninja-doc vs pob-doc for the same character. Equipment/flask/jewel
parity is **exact** (12/5/1 and 12/5/7 both paths); the entire divergence is in **gems**.

### R4-1 (MAJOR) — PoB path ignores gem corruption
`pob.py` infers `corrupted` only for **gear** (lines 146–189); it never infers it for gems. The PoB
export encodes gem corruption **implicitly** (level 21 / quality 23, no explicit attr — verified in the
decoded XML), so every PoB-sourced gem comes out `corrupted:false`, including game-impossible L21/Q0
gems, and matches the wrong (cheap) poe.ninja economy line.
- **Isolated impact (qwartus, gem multisets equal 33≈31):** gem sum **2219.5c** (ninja, corruption-aware)
  vs **1669.2c** (pob) = **~550c / ~25%** of the total, silently wrong.
- **Per-gem evidence:** Determination L21/Q0 — ninja `corrupted:true` 866.8c vs pob `corrupted:false`
  10.0c (its Enlighten priced 500.6c *separately* in pob, so the ~356c gap on this one gem is pure
  corruption); Anger L21/Q0 633.1 vs 5.0; Vortex L21/Q0 corrupted vs 2.0c.
- **Direction:** ninja is right (a level-21 gem *is* corrupted); the PoB path underprices. Fix: infer
  gem `corrupted` from `level > 20 || quality > 20` (and any explicit XML marker) in `pob.py`.

### R4-2 (MAJOR) — PoB path violates D-0018 weapon-swap exclusion
The ninja path detects & excludes swap gear (aurab `swap_items = [Silverbranch, Replica Maloney's
Mechanism]`); the PoB path emits **`swap_items = []`** — no swap detection at all. Result: the swap
weapons' socketed skills are counted in the PoB total, and the "weapon swap" toggle can't remove them
(nothing is flagged `swap`).
- **aurab:** ninja **1810.3c** vs pob **4280.6c** (**+2470c / +136%**); the delta is the swap-socketed
  Greater/Eclipse/Invention/Scornful setups (2× Eclipse @1079c, 3× Scornful Herald @134.6c, 4× Greater
  Chain, Greater Fork/Spell Cascade, 3× Invention) — 10 gems present in the PoB export but absent from
  the (swap-excluded) ninja doc.
- Fix: mark PoB items in Weapon-Set-2 / swap slots as `swap:true` so D-0018 applies on both input paths.

### R4-3 (minor) — PoB gems are structurally flat (D-0006 not honored)
Every PoB gem is a top-level row with `host_name:""` and `supports:[]`; the ninja path nests supports
under their active gem and bundles the price ("active + N supports"). Totals are unaffected (each gem
counted once), but the picker/UI host-grouping + support nesting is absent for PoB builds. Related:
item-granted gems (e.g. Generosity from Victario's Influence, nested+granted on the ninja path) don't
appear on the PoB path.

### Verified correct (no finding)
- **League defaulting:** PoB carries no league; `engine.prepare_from_pob` → `resolve_league("", …)` →
  **current challenge league**; both builds resolved to **Allflame**. ✔
- **Item parity:** equipment/flask/jewel identical name-sets both paths. ✔
- **Variant blocks (D-0019):** Watcher's Eye (roll-defined: Determination/Grace/Purity of Ice) and
  Bubonic Trail (socket-defined: 1 Abyssal Sockets) carry identical `locked_stats` in both docs. ✔

---

## Task 2 — API-down grace (Playwright, site served locally, `?api=`/`?worker=` overrides)
| Scenario | Result | Verdict |
|---|---|---|
| API **refused** (dead port) | phase→error 2.5s, "Could not reach the pricing service…" | GRACEFUL |
| API **hang** (accept, no reply) | **phase stuck "loading" 14.2s+ forever**, spinner "fetching the build…", no error, no pageerror | **R4-4** |
| API **non-JSON** HTML 200 | phase→error, same helpful message (r.json throws → catch) | GRACEFUL |
| API **500** JSON `{ok:false}` | phase→error, surfaces "simulated upstream 500" | GRACEFUL |
| **Worker dead** + `?stub` build | phase→done, build renders, cache read-through fails **silently** | GRACEFUL |

### R4-4 (MAJOR) — build fetch has no timeout → hung API = permanent stuck UI
`core.js start()` uses a plain `fetch(url).then().catch()` with **no AbortController/timeout**. The only
timeouts in core.js are the bridge-detect (1300ms, line 681) and the extension chunk-reply timeout
(line 869, D-0012) — the *build* fetch has none. When the API accepts the TCP connection but never
sends an HTTP response (firewall DROP, overloaded/half-open server, LB gateway timeout), the page sits
in `loading` forever with no error and no recovery (confirmed: still `loading` after 14s, 0 pageerrors).
The common "API down = connection refused" case is fine (2.5s → error); this is the *unresponsive*
case. Fix: wrap the build fetch in an AbortController with a bounded timeout → `fail()` with a helpful
"the pricing service took too long" message (mirror the bridge/chunk timeout discipline already present).
No uncaught exceptions in any scenario.

---

## Task 3 — whisper fuzz (`parseWhisper`, pure, node/vm; 60+ hostile inputs)
**Robust:** 0 throws across all inputs; no ReDoS (every 10KB / pathological input < 50ms); HTML/script
tags never execute (returns null or extracts a bare number — the note is built from the constrained
`CUR_RE` currency vocabulary and `raw` is never rendered → XSS-safe by construction); numeric overflow,
Infinity, NaN, `1/0`, `0/0` all → null; exalt/mirror → `chaos:null` (kept out of totals, by design).

### R4-5 (MAJOR) — locale/thousands separators silently mis-parse into the total
The parser matches the digit-run *after* a separator:
`"1,000 chaos" → 0`, `"1 000 chaos" → 0`, `"1.000.000 chaos" → 0`, `"1'000 chaos" → 0`,
`"35,5 chaos" (euro decimal) → 5`. The wrong value is folded in as a confident `medium` price. Trigger
is human-typed/manual entry (GGG's own whisper uses no separators), but the failure is a silent wrong
number in the headline. Fix: strip grouping separators (or reject ambiguous separators and re-prompt).

### R4-6 (minor) — divine→chaos multiply unguarded
`chaos = divineRate ? amount*divineRate : null` — the only NaN/Inf poison found: `divineRate=Infinity`
→ `chaos:Infinity`; `divineRate=-5` → `chaos:-10`. The fraction path guards `isFinite` but this
multiply does not, and there is **no upper cap** (`"1e300 chaos"` folds 1e300 into the total, whereas
the worker caps at `MAX_TIER=1e8`). `meta.divine_to_chaos` is server-sourced (not user-controllable),
so this is defense-in-depth, but it contradicts the parser's "never fabricate a number we can't derive".

### R4-7 (info) — dead `amount < 0` guard
`AMT_RE` (`[0-9]+…`) never captures a sign, so the `amount < 0` check on line 506 is unreachable;
`"-5 chaos" → +5`. Cosmetic (no real negative whispers exist).

---

## Task 4 — live-worker abuse (browser headers to clear Cloudflare BIC) — CLEAN PASS
Verified against the **live** Worker (`divtally-cache…workers.dev`), writing to a throwaway
letters-only league (real Allflame cache untouched; TTLs out). Deliberately did **not** flood the
per-IP write budget against production (abusive to the real KV free-tier quota; covered offline).

- **GET guards:** bad league (parens/digits, punctuation) → 400; empty keys → `{}`; 61 keys → 400
  "too many keys"; invalid key shapes → omitted. ✔
- **POST guards:** 61 entries → 400 "too many entries"; real 300 KB body → **413** "body too large";
  bad json → 400; bad league → 400; `entries:[…]` → 400 "bad entries". ✔
- **Poison entry sanitization (all 11 pass):** client `confidence:"high"` **ignored** → derived `low`
  from `total_found`; negative & `1e300` tiers → null (250 kept); `<script>` method → dropped `""`;
  `sample_size:-9` → 0; `<img onerror>` note kept as **inert string, clamped ≤512**; foreign
  `trade_url` → dropped `""`; ancient `ts:1` → **server-restamped** to now; `junk`/`extra_evil`
  fields gone. Good entry: `total_found:396` → derived `high`; legit pathofexile.com trade_url kept.
- **Rejections:** sole over-cap tier → record rejected (stored 0); all-null tiers → rejected. ✔
- **Wrong-league isolation:** a valid key stored under the test league, read under `Standard` → miss. ✔
- **Method/path:** PUT → 405; unknown path → 404; OPTIONS → 204. ✔
- XSS surface nil: the site renders cache `note` as a **constant** string (never the stored value),
  and `method` is `METHOD_RE`-constrained.

---

## Recommended fix order
1. **R4-4** (add build-fetch timeout — stuck UI, cheap fix, affects everyone on a bad network).
2. **R4-2** + **R4-1** (PoB swap exclusion + gem corruption — both make PoB totals materially wrong;
   R4-2 is the larger magnitude, R4-1 the more insidious).
3. **R4-5** (whisper separator parsing).
4. R4-3 / R4-6 / R4-7 (structure/hardening/cosmetic).

Two rounds with no meaningful adjustments ends the campaign (D-0020 LOOP-UNTIL-DRY); R4 found 4 major
issues, so it is **not** dry.
