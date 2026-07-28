# R3 fix pass 1 — all Round-3 query-truth findings fixed

**Round:** 3 (query TRUTH) of the D-0020 bug campaign. **Date:** 2026-07-28.
**Scope:** the 5 findings assigned from `docs/bugtest/r3-{derivation,live,picker}.md` — F1, F2 (offline
derivation), R3-1, R3-2 (picker), L1=F4 (live BLOCKER). Fixed in `public/api/_lib/` +
`public/site/assets/core.js`; contract updated additively. Every fix is proven through the REAL
code paths (probes below), not just asserted.

**Harness status after all fixes (all green):**
- `public/api/_verify.py` — **ALL CHECKS PASSED** (hermetic phase A + variant, AND live phase B:
  41-item Allflame character, priced=20, `no /api/trade in document`, health = never calls pathofexile).
- `public/site/test_picker.mjs` — **98 passed, 0 failed.**
- `public/site/test_scanstatus.mjs` — **64 passed, 0 failed.**
- Evidence probes (scratchpad, non-repo, reproducible): `probe_r3_server.py` **ALL PROBES PASSED**,
  `probe_r3_client.mjs` **ALL CLIENT PROBES PASSED**.

**Trade footprint:** zero. No pathofexile.com call of any kind; bundled schema + poe.ninja only.

---

## F1 (major) — option-stats emitted as verbatim `base|opt` instead of `{id:base, value:{option}}`
**Files:** `public/api/_lib/querybuild.py` (`affix_options`, `_rare_default_filters._statf`, new
`_split_option`), `public/site/assets/core.js` (`buildRareQuery`).
**Bug:** the bundled schema pre-flattens option-stats into one entry per option with the option
baked after a pipe (`enchant.stat_3948993189|31` = "…grant: 10% increased Area Damage"). The normal
affix path (`StatMapper.match → affix_options → _statf`) emitted that piped id **verbatim, with no
`option` value**; only the D-0019 variant path split it. Live (r3-live L2) the piped alias happens
to be honoured, but it is undocumented — a GGG validation tightening would 400 it.
**Fix:** `_split_option(sid)` turns a `base|opt` id into `(base, int(opt))`. In `affix_options` the
split runs right after `mapper.match`; a non-defining option row now carries `stat_id=base`,
`option=N`, and **no numeric prefill** (an option stat has no magnitude bound) — mirroring
`_apply_defining`, which still owns defining rows. `_statf` emits `{"id":base,"value":{"option":N}}`.
Client `buildRareQuery` emits the same wire form for a ticked non-defining option row
(`if (a.option != null) …`), so the picker path is hardened too (the 16 picker rows).
**Proof (`probe_r3_server.py` + `probe_r3_client.mjs`):** a Medium Cluster Jewel's grant enchant →
picker row `stat_id="enchant.stat_3948993189"`, `option=31`, `default_min/max=null`; default query
filter `{"id":"enchant.stat_3948993189","value":{"option":31}}`; **no `|` remains** in any query;
picker `buildRareQuery` emits `{id:base, value:{option:31}}` (no pipe, no spurious min).

## F2 (major) — singular "1 Added Passive Skill is a Jewel Socket" dropped from cluster-jewel queries
**File:** `public/api/_lib/statmap.py` (new `_normalise_pattern`, used in `match`).
**Bug:** the schema's only jewel-socket stat is the PLURAL `enchant.stat_4079888060`
("# Added Passive Skills are Jewel Sockets"). A Medium Cluster Jewel's single socket renders the
SINGULAR "1 Added Passive Skill **is a** Jewel Socket", whose pattern never equals the plural, and
being an ENCHANT it never falls back → dropped → search relaxed to a socket-less superset (price
biased low). Same singular/plural class as the R1 Bubonic Trail abyssal fix.
**Fix:** normalise the known singular PATTERN → the plural schema pattern inside `match()` (NOT
`_build`, so the pattern maps are unchanged and `slim._map/_groups == full` still holds). The count
is preserved (leading `#` untouched), so `first_number` still reads the item's count.
**Proof:** the singular mod → searchable, `stat_id="enchant.stat_4079888060"`, `default_min=1`
(count from "1"); the default autoscan query now INCLUDES `enchant.stat_4079888060` (was absent).
The default query emits the bare id (presence) exactly like the plural Large-Cluster case; the
picker prefills `min:1`.

## L1 = F4 (BLOCKER) — Allflame "Foulborn <unique>" name 400s the whole search
**File:** `public/api/_lib/querybuild.py` (new `_base_unique_name` / `_LEAGUE_NAME_PREFIXES`,
applied in `_unique_query`).
**Bug:** the engine emitted the league-decorated `name:"Foulborn Esh's Mirror"`, which the live
search rejects with **HTTP 400 "Unknown item name"** — dead trade link + failed client scan for
every Foulborn unique (r3-live S12). The base name "Esh's Mirror" returns 200 / 990 listings (the
Foulborn shields index under the base name).
**Fix:** strip the league prefix (`"Foulborn "`) from the trade `name` in `_unique_query` **only** —
`item.name` keeps the decoration so poe.ninja still prices the enumerated "Foulborn …" line
(pricing is by decorated name; the trade search is by base name — the two intentionally differ).
**Proof:** `_unique_query` for a "Foulborn Esh's Mirror" unique → `name:"Esh's Mirror"`,
`type:"Vaal Spirit Shield"`; `item.name` unchanged; `trade_url` carries the base name (no "Foulborn");
a normal name ("Headhunter") is untouched.

## R3-1 (major) — a variant-DEFINING resistance folded into the pseudo total and dropped
**File:** `public/site/assets/core.js` (`buildRareQuery` :1093-1103, `tierGroups` counting loop :1151-1152).
**Bug:** the resist-fold (`if (usePseudo && a.resist) return;`) ran BEFORE the `a.defining` branch,
so a defining mod that is also a resistance (Purity Watcher's Eye cold-res, Viridian Grand Spectrum)
was folded into the pseudo total and never emitted as its locked filter → wrong-variant / misleading
price (breaks D-0019 + D-0015).
**Fix:** move the `a.defining` branch ABOVE the resist-fold in `buildRareQuery` AND in the
`tierGroups` counting loop (so a defining resist is counted `required` → the AND group is created).
`place()` already checked defining first, so no change there. A defining mod is now emitted before
any fold, in every path.
**Proof (`probe_r3_client.mjs`):** Purity Watcher's Eye (defining cold-res + ordinary fire-res +
crit aura + elem pseudo) — in BOTH the all-ticked ✎ path and the survey/tier path: the defining
cold-res filter is **emitted with its locked roll (min 22)**, while the ORDINARY fire-res still
folds into the pseudo total. A defining resistance is never folded away.

## R3-2 (major) — the survey/default picker auto-excluded searchable unique mods + the pseudo total
**File:** `public/site/assets/core.js` (`_siteTierOf` :1019-1024).
**Bug:** `_siteTierOf` mapped `priority:"skip" → "notneeded" → unticked → dropped`, on the false
comment that "skip is only ever assigned to unsearchable affixes". But `querybuild.affix_options`
assigns `skip` to EVERY non-skill-level unique mod AND the unique pseudo total (all **searchable**).
Opening the picker on a unique and hitting Search with zero edits silently excluded most of its
searchable mods + its pseudo resistance total (51/53 uniques; breaches D-0015).
**Fix:** map `skip → "notneeded"` **only when the row has no `stat_id`** (genuinely unsearchable —
it can never be a filter); a searchable `skip` row → `"nice"` (searched, like `notimp`). Equip
defence-total rows (`stat_id==null`) are unchanged. Comment corrected.
**Proof (`probe_r3_client.mjs`):** a unique with a searchable `skip` Life mod + an unsearchable
`skip` mod + a `skip` pseudo total → `rareDefaultPicks` tiers = `nice / notneeded / nice`; the
survey query KEEPS the Life mod and the pseudo total, the unsearchable mod contributes no filter,
and the unique NAME still scopes the search. The D-0016 fixture (unsearchable skip → notneeded) is
unchanged (test_picker still green).

---

## Contract / doc updates (additive, back-compatible)
`docs/public-contract.md`: dated **D-0020-R3** header note (F1 split option wire form, F2 jewel
socket, L1 base name, R3-1/R3-2 client) + `affixes[].option` (§2.6) broadened from "defining only"
to "defining OR ordinary searchable option affix (flattened `base|opt`)". No field removed/renamed.

## Deliberate non-expansions / notes
- **F2 default-query shape:** the default autoscan query emits the **bare** `enchant.stat_4079888060`
  (presence = has a jewel socket), identical to how the plural Large-Cluster socket already emits.
  The `min:1` is redundant with presence; the picker still prefills `min:1` (the count) for the
  advanced path. Per r3-live L3 the socket filter is wire-valid (200); no live price change on the
  4 banked builds (their sole F2 item 0-matches regardless), but the completeness gap is closed.
- **F1 was rated live-minor** (piped alias honoured), but the split is the documented form and
  hardens both the default and picker paths; done as directed.
- **bpc/ package** (the local CLI variant) was **not** touched — the findings, hints, and the
  green harnesses all target `public/`. `bpc/` has no unique-overview pricing and a separate
  affix path; parity there is a possible follow-up, not required by these findings.
- **Carry-forward F2–F5 (r2 minors) in r3-picker §3** were out of scope for this pass (not in the
  assigned 5); still tracked there.
