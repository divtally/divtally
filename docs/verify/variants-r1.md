# D-0019 RE-VERIFY (round 1) — after MAJOR-1/MINOR-1 "resolved"

Verifier: sole-trade-budget adversarial re-verify agent (2026-07-27). Scope: confirm the
`docs/verify/variants.md` findings are truly resolved, all harnesses green, and one LIVE
re-spot-check of the previously-FAILING query class (the non-"while affected by" family items
that MAJOR-1 was about — specifically **The Light of Meaning**, the item that was LIVE-confirmed
emitting `filters=[]` / `"aura variant"` in the original report).

**Verdict: MAJOR-1 dispatch fix is REAL and correct — BUT the live re-spot-check surfaced a
distinct, previously-uncaught defect: The Light of Meaning's registry DEFINING STAT IS WRONG, so
real copies STILL emit `filters=[]`. The green harness masks it with a fictional fixture.**
1 MAJOR (data + test-validity). No blockers: legal queries only, no crash, no wrong price
(ninja map-variant still prices the item), no rate-limit issue.

---

## 1. Harnesses — ALL GREEN (re-run 2026-07-27)
| Harness | Result |
|---|---|
| `python tests.py` | All self-tests passed |
| `BPC_SKIP_LIVE=1 python public/api/_verify.py` | ALL CHECKS PASSED (incl. the 6 new phase_variant asserts) |
| `python tools/build_variant_registry.py --check --offline` | validated OK; 40 items, 38 stat_ids resolve, 0 crosscheck drops |
| `node public/site/test_picker.mjs` | 83 / 0 |
| `node public/site/test_scanstatus.mjs` | 47 / 0 |
| `node extension/test_protocol.mjs` | PASS |

## 2. MAJOR-1 dispatch fix — CONFIRMED correct (code + behavior)
`variantreg.build_variant` (variantreg.py:275-318) now dispatches by `emit` + the copy's actual
mods, not the blanket `family_all` flag. Verified: `is_presence` → notable presence filters
(Megalomaniac emits `stat_2780712583/2342448236/3599340381`, real mod ids that DO match live
copies); real `while affected by` mod → aura branch (Watcher's Eye et al. unaffected); the dead
`elif is_presence/def_ids` branches are reachable again. The `"aura variant"` mislabel is gone for
non-aura families. This part of the "RESOLVED" note is accurate.

## 3. LIVE re-spot-check — The Light of Meaning (the MAJOR-1 poster child)
League **Allflame** (live-verified real trade league). Endpoint/UA/headers mirror `bpc/trade.py`.
Budget: **5 search POSTs + 1 fetch** (of the 6-POST cap); ≥3 s spacing; rate headroom throughout
(peak 4/300s window), zero 400/403/429.

| # | Query (name=The Light of Meaning, type=Prismatic Jewel) | HTTP | total |
|---|---|---|---|
| A | name-only (== old dropped-filter behavior) | 200 | **913** |
| B | + `explicit.stat_607548408` `{min:12}` | 200 | 0 |
| 3 | + `explicit.stat_607548408` `{min:7}` | 200 | 0 |
| 4 | + `explicit.stat_607548408` **presence (no value)** | 200 | **0** |
| 5 | name-only, capture ids → **fetch 3 listings** | 200 | 916 |

**The presence filter on the registry's defining stat returns 0 of 913 listings** → NO live Light
of Meaning carries `stat_607548408`. The 3 fetched copies' actual explicit mods:
- `Passive Skills in Radius also grant 7% increased Evasion Rating` → `explicit.stat_3761482453`
- `Passive Skills in Radius also grant +5 to maximum Mana` → `explicit.stat_3382199855`

The real Light of Meaning variant family is the **16-member "Passive Skills in Radius also grant
X"** set (stat_3761482453 evasion, stat_3382199855 mana, stat_1223932609 life, stat_3901726941
crit, …). The registry's `stat_607548408` = "#% increased Effect of non-Keystone Passive Skills in
Radius" is **not a current Light of Meaning mod at all** (looks like a pre-rework/legacy text —
that it is the OLD mod is **[INFERRED — community memory, NOT source-confirmed]**; source-confirmed
fact is only that live copies carry the "…also grant X" family and zero carry stat_607548408).

## 4. MAJOR (r1-1) — Light of Meaning registry entry has the WRONG defining stat; real copies still drop the filter
Registry `public/api/_data/variant_uniques.json` → The Light of Meaning:
`defining=[{stat_id:"explicit.stat_607548408", family_size:1, samples:[]}]` — factually wrong.

Runtime consequence, driven OFFLINE through the real `build_variant` (deterministic):
```
REAL "…also grant 7% increased Evasion Rating"  -> filters:[]  label:''
REAL "…also grant +5 to maximum Mana"           -> filters:[]  label:''
FIXTURE "50% increased Effect of non-Keystone…" -> filters:[{stat_607548408:{min:50}}] label:'50% increased…'
```
Because `class="mod-variant"` (no own-rolls fallback — that is roll-defined only), a real copy
whose mod ∉ `def_ids={stat_607548408}` picks nothing → `filters=[]`, `label=''`. **This is exactly
the MAJOR-1 outcome** (defining filter dropped) — the fix corrected the *dispatch/label*, but the
underlying registry DATA is wrong, so the enhancement silently never applies to any real copy.

**Why the harness is green on it (test-validity bug):** `_verify.py:523-527` feeds a FICTIONAL mod
`"50% increased Effect of non-Keystone Passive Skills in Radius"` — the only string that resolves
to the (wrong) registry id — so phase_variant asserts against ground truth that does not exist in
the game. MINOR-1's "coverage" for this item is coverage of a fiction.

**Impact (honest):** not a blocker. The Light of Meaning is ninja *map-variant* (not floor-only),
so it still gets a real price from the ninja variant line — no wrong number, no crash, queries all
legal (200). The user-facing loss is limited to D-0019's promise for this item: the REQUIRED
defining-mod filter is absent and the picker/label shows nothing for it (never the wrong mod, since
no copy matches the bad id). But it is a genuine **registry data-integrity error** + a **test that
passes on a fictional fixture**, and it is the single item I had budget to live-check — which raises
the question of how many other family/`samples:[]` mod-variant entries carry mis-harvested ids.

## 5. Recommended follow-up (not done here — file ownership + budget)
1. **Fix the registry entry:** rebuild The Light of Meaning's `defining` to the "Passive Skills in
   Radius also grant X" family (serialise the family's ids or a text predicate so any of the 16
   members on a copy matches), via `tools/build_variant_registry.py` + determinism re-check.
2. **Replace the fictional fixture** in `_verify.py` phase_variant with a REAL mod string
   (`"Passive Skills in Radius also grant 7% increased Evasion Rating"`) so the test asserts the
   emitted filter is `stat_3761482453` (or family-member), not the legacy id. Right now the fixture
   guarantees the bug can never fail the suite.
3. **Audit the other family/`samples:[]` mod-variant entries** (Vessel of Vinktar family=18,
   Aul's Uprising family=116, any other family_size≥1 with empty samples) against live copies for
   the same mis-harvest class — one live fetch per item settles each. (Aul's/Vessel were already
   flagged as rep-id-can't-match in `docs/notes-variant-fix1.md`; this is a stronger claim: verify
   the rep id is even a REAL current mod of the item, which for Light of Meaning it is not.)

## Budget / etiquette ledger
5 search POSTs + 1 fetch (under the 6-POST hard cap). ≥3 s spacing; real UA (contact email);
honored X-Rate-Limit-Ip / -Ip-State every call; no 400/403/429; only pathofexile.com endpoint used
was the sanctioned trade search/fetch. Offline confirmations used the vendored `build_variant`
(no network). Probe script: scratchpad `live_respotcheck.py` (outside the repo).

---

## RESOLVED (2026-07-27) — both defects fixed; detail in `docs/notes-variant-fix2.md`
- **MAJOR r1-1 (registry data) — FIXED.** The Light of Meaning's `defining` is rebuilt to the real
  15-member **"Passive Skills in Radius also grant X"** explicit family. `build_variant_registry.py`
  `defining_family` gained `serialise_family_ids=True` (LoM only), writing the whole family into
  `from.family_ids`; the runtime `variantreg.build_variant` folds `family_ids` into `def_ids`, so a
  copy's SPECIFIC member is emitted by its own id (`…grant 7% increased Evasion Rating` →
  `explicit.stat_3761482453 {min:7}`; mana → `stat_3382199855`). The wrong legacy `stat_607548408`
  (Might of the Meek's mod) is gone. Aul's/Vessel unchanged (still rep-only, as their fix1 note
  says). Registry rebuilt; determinism re-checked (byte-identical `items`).
- **Test-validity — FIXED.** `_verify.py` phase_variant no longer feeds the fictional
  `"increased Effect … in Radius"` string; it feeds real `"…also grant X"` copies and asserts the
  emitted filter is the family member id (evasion/mana), never the legacy id. Proven to FAIL on the
  old registry (`filters:[]`) and pass on the fixed one — the bug can now fail the suite.
- Audit of the OTHER family/`samples:[]` entries (sec 5 point 3) is a separate live-budget task, not
  done here.
