# R6 - League-rollover lens (fresh eyes)

**Date:** 2026-07-28
**Round:** 6 (fresh lenses). Lens: **league rollover** - Allflame WILL end; what breaks, what
auto-heals, and the owner runbook (`docs/league-rollover-runbook.md`).
**Trade rule honoured:** ZERO calls to pathofexile.com. Evidence came from (a) a hermetic
monkeypatched index-state harness driving the PUBLIC `_lib` league paths offline, and (b) LIVE
poe.ninja-only probes (`economy/*/current/overview` for ended leagues + one real Standard
character priced end-to-end through the public engine). The local `bpc` trade path was read and
characterised statically (not executed - it would call trade).
**Method artifacts (scratchpad):** `rollover_harness.py` (mock index, both variants),
`live_probe.py` (ended-league economy + Standard pricing).

## Verdict

**PASS - the system is remarkably rollover-robust. No blocker, no major, no crash, no
silently-wrong price.** The league flows from each build's OWN data end-to-end; every league
default reads live from poe.ninja's index-state and self-heals the moment poe.ninja flips to the
new league; the worker cache isolates by league and expires in 24h; the variant registry's
runtime use is league-invariant (recipes, not prices). Five **MINOR** findings below, all
UX/labeling or forward-looking - none produce a wrong number and none block a new-league
appraisal on day 1. The real deliverable is the runbook.

Two load-bearing questions were answered empirically (not assumed):
- **Does an ENDED league still price?** YES. poe.ninja keeps serving `.../current/overview` for
  long-dead leagues: Ancestors / Mirage / Keepers each returned full economy today
  (86-115 currency lines, 784-827 UniqueArmour lines) vs the Allflame control (101 / 900). So a
  just-ended league does NOT go blank - it prices against its FROZEN end-of-league snapshot.
- **Does a STANDARD character price TODAY?** YES. The public engine priced a live Standard
  Chieftain (lvl 100, 38 items, 20 priced; The Golden Charlatan 165,999c high-conf, The Gull
  33,589c, Cloak of Flame 6,085c variant), `meta.league='Standard'`. The standard-migration /
  voidborn path is sound.

---

## What auto-heals (owner does NOTHING; verified)

| Mechanism | Why it heals | Evidence |
|---|---|---|
| `current_challenge_league()` (PoB import w/ no league) | Returns the first non-perma name in `index-state.economyLeagues`; poe.ninja flips this to the new league at launch. | Harness: with a mocked post-rollover index it returned `'Redemption'` (both mock variants). |
| Public `engine.resolve_league('', None)` default | Delegates to `current_challenge_league()`. | Harness: `-> 'Redemption'`. |
| Site league dropdown | Seeded only with `['Standard','Hardcore']` + Auto; the loaded build's own league is appended on `meta` (`index.html` `seedLeagues`). No hardcoded Allflame. | `index.html:1190-1205, 2402-2403`. |
| Site `DEFAULT_LEAGUE` | `""` = use each build's own league (no pin). | `config.js:39`, `core.js:94-95`. |
| Worker cache isolation | KV name = `p1:<leagueKeyspace>::<key>`; every league gets its own namespace and each entry has a 24h TTL, so old-league entries can neither leak into nor collide with the new league and vanish within a day. **No worker redeploy needed** (keys are computed client-side; a recipe bump never touches the worker). | `worker.js:75-85, 54`. |
| Runtime variant pricing | Registry supplies the STRATEGY/recipe only; the price NUMBER comes from LIVE poe.ninja lines for whatever league is active. Recipes are league-invariant (stat ids, base types, strategies). | `querybuild.py:754-823` + `poeninja.py::unique_price/_registry_price`. |
| Local `bpc` CLI on a dead-league link | `resolve_trade_league` validates `meta.league` against live trade leagues; a dead league raises a CLEAN `EstimateError` ("...not a current trade league. Available: ... Re-run with an explicit league override.") - fail-safe, no crash, no wrong number. | `bpc/engine.py:38-54` (read, not executed). |

---

## Findings (all MINOR - ranked)

### M1 - Public `fetch_character` silently resolves an old-league link to the CURRENT league (bounded)
`public/api/_lib/poeninja.py::_snapshot_candidates` (used only by the PUBLIC `fetch_character`)
falls back through EVERY `buildLeagues` exp snapshot when the pasted slug has no primary match.
Harness result, "allflame slug fully GONE" mock + the same account/name existing in the new
league: `fetch_character('allflame', ...) -> _league='Redemption'` - it priced a DIFFERENT
character (the current-league one) than the URL named, with no notice.

Why it is **MINOR, not major**:
- It requires poe.ninja to have **fully dropped** the `allflame` slug from `snapshotVersions`.
  Empirically that does NOT happen for many months - Ancestors/Mirage/Keepers (all long dead)
  are STILL in today's `snapshotVersions` (106 entries) and still fetch. For the entire relevant
  window the realistic "RETAINED" mock holds, where `allflame` is tried FIRST and correctly
  returns the Allflame character (`_league='Allflame'`, verified).
- Even in the worst case it also requires the SAME account AND identical character name to exist
  in the new league.
- When it does fire, the **displayed league and the priced league always agree** (both become
  the current league) - there is never a price/label mismatch, and poe.ninja only returns a
  character that genuinely exists under that overview. So it is a "which character did you mean"
  UX surprise, not a wrong number.
- The LOCAL `bpc` path does not have this fallback (it calls `resolve_snapshot`, which raises a
  clean error when the slug is gone - harness: `PoeNinjaError: league slug 'allflame' is not in
  poe.ninja's current snapshots. Known: ...`).

Optional hardening (owner's call, not required): when `fetch_character` had to fall off the
requested slug onto a different league, stamp a flag the UI can surface ("this character was
found in <league>, not the league in your link").

### M2 - A retained ended-league link prices against FROZEN end-of-league numbers, unlabeled
Realistic post-rollover flow: a user pastes their OLD Allflame poe.ninja link (still in
history/bookmarks). Because poe.ninja retains the slug (see PROBE 1), the public engine fetches
the frozen Allflame snapshot, sets `meta.league='Allflame'`, and prices it against Allflame's
**frozen** `.../current/overview` economy (proven still-served). The numbers are internally
consistent (Allflame data at Allflame prices) but are frozen in time and no longer reflect where
the items actually live now (Standard, post-migration). There is no "this league has ended -
prices are frozen at league end; switch to Standard for current value" caveat.

MINOR: honest per its own league (the header does say Allflame), degrades safely, no wrong-league
number. A one-line hint keyed on "meta.league not in live economyLeagues" would remove the
confusion. (The public engine cannot cheaply know a league ended without a call; the cheap signal
is `index_state().economyLeagues` membership, which it already fetches.)

### M3 - `tools/build_variant_registry.py` hardcodes `DEFAULT_LEAGUE = "Allflame"` (offline fallback)
`resolve_league(prefer, offline)` returns `DEFAULT_LEAGUE` when `--offline` is passed OR when the
live index-state resolve throws. At rollover, an `--offline` regen (or a regen while poe.ninja is
flaky) would harvest against the now-dead Allflame dumps. Normal `--refresh` (no `--league`)
live-resolves the new league correctly, so this only bites the offline path. **Mitigated by the
runbook**: regen with `--refresh` (optionally `--league <New>`), never `--offline`, at rollover.
Low blast radius anyway - registry PRICES are not used at runtime (M-note below).

### M4 - Worker `LEAGUE_RE` accepts letters+spaces only (forward-looking cache gap)
`worker.js:57` `LEAGUE_RE = /^[A-Za-z][A-Za-z ]{0,49}$/`, mirrored by the letters-only filter in
`build_variant_registry.py::resolve_league` (`"Standard" not in nm and "Hardcore" not in nm`).
Every PoE1 challenge-league name to date is letters+spaces, so this holds. If GGG ever ships a
league name with a digit/apostrophe/hyphen, the worker would reject that league (`bad league` ->
shared cache silently disabled for it; the site still works, degrading to trade links /
whisper-paste). Not triggered by any known name; noting for the forward-looking audit.

### M5 - Cosmetic: the offline demo build still says league "Allflame"
`public/site/assets/sample.js:60` (and `bpc/ui/assets/sample.js`) hardcode `league:"Allflame"` in
the placeholder build shown before a real fetch. Purely cosmetic; refresh it at rollover if you
want the demo to read current. (`stub-build.json` already uses "Standard".)

---

## The "stale registry" question, answered and LABELED

**Pricing a NEW-league build against the Allflame-harvested registry is SAFE; stale variants are
acceptable.** Reason (source-derived from the code, not inferred):
- `variant_uniques.json._meta.ninja_league = "Allflame"` and each item's
  `ninja_variant_rule.observed_variants` carry Allflame chaos/listing numbers - but the runtime
  **never prices from them**. `querybuild.py::price_unique_ninja` passes only the `strategy`,
  `axis`, and (for socket-count uniques) the `observed_variants[].abyssal_count` label-mapping
  into `econ.unique_price`; the actual chaos tiers come from `econ._load_uniques()` = LIVE
  poe.ninja lines for the ACTIVE league.
- The recipes themselves (defining `stat_id`s, option splits, seed handling, base types,
  strategies) are league-invariant and are validated at build time against the static
  `trade_stats.json` (stat ids are stable across leagues per `refdata.py`).
- The one place Allflame data touches runtime - the abyssal-count -> variant-label map in
  `_match_count_line` - **degrades to live-label integer parsing** if the stale label no longer
  matches, and an unmatched variant returns None => unpriced + trade link, never a wrong number.

So: a league can be priced on last league's registry with no correctness loss. Regeneration is a
**refinement** (fresh `observed_variants` for count/label precision + picking up any new-league
unique reworks), NOT a correctness gate. Label to keep visible: **the registry's baked prices are
Allflame-era and inert at runtime; only its recipes are used.**

---

## Coverage of the lens' explicit asks

- resolve_snapshot / current_challenge_league / fetch_character fallback under a mocked
  allflame-less index: driven both ways (slug retained vs fully gone). No crash; the only silent
  cross-league path is M1 (bounded, minor).
- registry `_meta.league`: audited - stale is safe (above).
- worker league keyspaces: audited - per-league namespace + 24h TTL = clean isolation (auto-heal
  table); regex caveat = M4.
- site league dropdown seeding + seeder tool + docs: audited - no live hardcoded league; M3
  (regen offline default), M5 (demo cosmetic).
- Voidborn / Standard migration: a real Standard character prices today (PROBE 2). Sound.
