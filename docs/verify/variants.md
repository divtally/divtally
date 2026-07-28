# D-0019 verification — variant-unique registry + timeless jewels

Verifier: sole-trade-budget adversarial verify agent (2026-07-27). Scope: D-0019 end-to-end —
harnesses, registry sanity vs raw ninja dumps, LIVE trade spot-checks (12-POST budget), and an
adversarial hunt (illegal filter / wrong ninja line / seed-as-range).

**Verdict: NOT CLEAN — 1 MAJOR + 1 MINOR.** Every mechanism the task called out was verified
working LIVE (option-split, exact seed, aura family, count, ninja floor/variant), but the
roll-defined/mod-variant builder has a branch-ordering bug that silently drops the defining
filters and mislabels 4 registry items. No blockers: no illegal (400) filters, no crashes, no
wrong prices, no rate-limit violations.

---

## 1. Harnesses — ALL GREEN
| Harness | Result |
|---|---|
| `python tests.py` | All self-tests passed (exit 0) |
| `python public/api/_verify.py` (BPC_SKIP_LIVE=1, phase A + phase_variant) | ALL CHECKS PASSED |
| `python tools/build_variant_registry.py --check --offline` | validated OK; 40 items, 38 stat_ids resolve |
| registry determinism | committed `variant_uniques.json` `items` == fresh rebuild (byte-identical) |
| `node public/site/test_picker.mjs` | 83 passed / 0 failed |
| `node public/site/test_scanstatus.mjs` | 47 passed / 0 failed |
| `node extension/test_protocol.mjs` | PASS (all) |

## 2. Registry sanity — CLEAN
- **Stat-id resolution:** all 38 distinct defining/sample stat_ids resolve in the bundled
  `public/api/_data/trade_stats.json`. Option bases have children (Forbidden Flame/Flesh 165,
  Impossible Escape 48, Thread of Hope 5); option 4194 = "Allocates Berserker…", 41970 =
  "…Ancestral Bond…". All 20 timeless seed ids are in the **Explicit** group with the exact
  flavour text the seed parser keys on. Runtime-emittable option/aura/seed ids spot-checked to
  correct text.
- **8-entry ninja-dump audit** (registry `ninja_variant_rule` vs raw `research/data/ninja_uniques_*.json`):
  Forbidden Flesh (30.0/863 floor), Watcher's Eye (50.0/11320 floor), Lethal Pride (67.5/6189
  floor, single null-variant line — poe.ninja genuinely has NO seed split), Voices (3/5/7-passive
  lines + chaos), **Shroud of the Lightless** ("1 Jewel" line carries abyssal_count **3** @360.9c,
  "2 Jewels"=2 @3.0c — the non-literal-label handling is faithful to the dump), Impresence (5
  element lines), Mageblood (2/3/4-Flask lines), Bubonic Trail (1/2-Jewel + abyssal counts). Every
  variant/price/listing/abyssal value matches the raw dump. Floor = min(priced lines) in all 8.

## 3. LIVE trade spot-checks — ALL HTTP 200, narrowing + listings confirmed
Real characters found via poe.ninja ladder (league **Allflame**, live-verified as a real trade
league id). Queries built by the actual `PublicPricer` from each owner's own copy, POSTed to
`pathofexile.com/api/trade`. **7 search POSTs of the 12 budget used**; ≥4 s spacing; rate-limit
headroom throughout (peak 7/300s window); zero 400/403/429.

| Target (owner) | Query | HTTP | total_found | Listing check |
|---|---|---|---|---|
| Watcher's Eye baseline (name+base) | — | 200 | 10000 (cap) | universe |
| Watcher's Eye 3-aura combo (iDei) | `stat_1817023621`≥24 AND phasing/burning flags | 200 | 0 | honest sparse (exact triple-aura not listed) |
| Watcher's Eye 1-aura (Precision) | `stat_1817023621`≥24 | 200 | **227** | both fetched copies carry "+25% Crit Multi while affected by Precision" ✓ |
| **Impossible Escape option** (Poteitik) | `stat_2422708892` `{option:41970}` | 200 | **21** | all 3 fetched = Ancestral Bond copies (`…|41970`) ✓ (same option-split code path as Forbidden Flesh) |
| **Lethal Pride exact seed** (fanfon) | `pseudo_timeless_jewel_kaom` `{min:13556,max:13556}` | 200 | **1** | the 1 listing's seed line = "…13556 warriors under Kaom" ✓ (exact, not range) |
| Elegant Hubris exact seed x20 (example) | `pseudo_timeless_jewel_caspiro` `{min:29120,max:29120}` | 200 | 0 | honest sparse |
| Elegant Hubris broad (x20 proof) | `pseudo_timeless_jewel_caspiro`≥2000 | 200 | 2355 | fetched seeds 19780 / 108320 / 94640 — **all multiples of 20**, searchable by the DISPLAYED value → x20 handling correct |

Conclusions: the **option-split**, **exact-seed** (incl. x20), and **aura-family** filters are all
legal and narrow correctly; every fetched listing matched the intended variant. The Elegant
Hubris x20 note is documentation-only — no runtime code branches on it; the seed is parsed and
emitted identically to the other four timeless jewels (Lethal Pride live-proves the mechanism).

## 4. Adversarial findings

### MAJOR-1 — `family_all` branch shadows `is_presence`/`def_ids`; 4 items lose their defining filters + get a wrong "aura variant" label
`public/api/_lib/variantreg.py:278` — `if family_all or is_aura:` only ever matches
`"while affected by"` mods. Because **every** roll-defined/mod-variant defining family sets
`match:"family-all"` (build_variant_registry `defining_family`), `family_all` is always True, so
the `elif is_presence:` (line 283) and `elif def_ids:` (line 288) branches are **unreachable dead
code**. Any family item whose defining mods are NOT phrased "while affected by …" is mishandled:

| Item | class | intended | actual (confirmed) |
|---|---|---|---|
| **The Light of Meaning** (iDei, LIVE) | mod-variant | match "…in Radius…" amplify mod | `label="aura variant"`, `filters=[]` → name+base only |
| **Vessel of Vinktar** | mod-variant | match lightning conv/pen mod | same: no defining filter, "aura variant" |
| **Megalomaniac** | roll-defined (emit=presence) | AND the 3 "1 Added Passive Skill is <Notable>" | presence branch never runs; falls to own-rolls; `label="aura variant"`; flags "Adds N Passive Skills" as defining |
| **Aul's Uprising** | roll-defined (reservation) | match the "<Aura> has no Reservation" mod | own-rolls emits a generic `+Life` filter, NOT the reservation mod; `label="aura variant"` |

Impact: violates D-0019's "registry items get REQUIRED defining-mod filters" and "picker shows
defining mods" for these 4 (Megalomaniac/Aul's are floor-only on ninja, so the dropped/degraded
trade filter *is* their real price handle). The wrong `"aura variant"` string surfaces in the
item-row `variant_info.label` and picker. Not a blocker: all resulting queries are legal (name+base
/ own-rolls → HTTP 200), ninja still floor/variant-prices, no crash. Watcher's Eye / Sublime Vision
/ Circle-of-X / Doryani's Delusion are unaffected (their mods genuinely contain "while affected by").
Fix: dispatch by emit/axis (presence → presence match; aura only when a "while affected by" mod is
actually present; else def_ids / own-rolls) and stop labelling non-aura families "aura variant".

### MINOR-1 — `phase_variant` never exercises the presence / reservation / non-"while affected by" family items
`public/api/_verify.py` phase_variant covers option (Forbidden Flesh), aura-mods (Watcher's Eye),
seed (Lethal Pride), count (Voices/Shroud), and map-variant-defining=[] (Impresence) — but no
Megalomaniac, Aul's Uprising, The Light of Meaning, or Vessel of Vinktar. That gap is exactly why
MAJOR-1 shipped green. Add fixtures asserting each emits its intended defining filter + correct label.

## Notes for follow-up
- No illegal-filter (400) case found — the adversarial "illegal recipe" hypothesis is refuted for
  all 40 items at the schema level and live for the option/seed/aura paths.
- "seed filter as range instead of exact" — refuted: emitted `{min:N,max:N}`; Lethal Pride live
  returned exactly its seed (total_found=1).
- "ninja variant-match picking wrong line" — refuted: map-count keys on observed abyssal_count
  (Shroud dump audit), map-variant requires cover≥0.6 AND strictly beats runner-up (else →
  unpriced+link, fail-safe), map-base pins exact base.

---

## RESOLVED (2026-07-27)
- **MAJOR-1 — FIXED.** `variantreg.build_variant` now dispatches by `emit` + the copy's actual
  mods instead of the blanket `family_all` flag (variantreg.py:275-301): presence flags →
  `while affected by` aura mod actually present → def-ids → own-rolls. Megalomaniac emits its 3
  notable presence filters, Aul's Uprising captures its `<Aura> has no Reservation` mod (own-rolls),
  The Light of Meaning emits its `…in Radius` amplify filter, Vessel of Vinktar no longer says
  "aura variant". Watcher's Eye / Sublime Vision / Circle-of-X / Doryani's Delusion unchanged.
- **MINOR-1 — FIXED.** `phase_variant` gained 6 assertions covering the 4 items above (direct
  `build_variant` + one end-to-end floor check). All harnesses green.
- Detail + a noted registry-richness limitation (Aul's/Vessel rep-id can't match every family
  member): `docs/notes-variant-fix1.md`.
