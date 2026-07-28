# D-0019 RE-VERIFY (round 2) — after MAJOR r1-1 + test-validity "resolved"

Verifier: sole-trade-budget adversarial re-verify agent (2026-07-27). Scope: confirm the
`docs/verify/variants.md` (MAJOR-1/MINOR-1) **and** `docs/verify/variants-r1.md` (MAJOR r1-1 +
test-validity) findings are truly resolved, all harnesses green, registry deterministic, and ONE
LIVE re-spot-check of the previously-FAILING query class — **The Light of Meaning**, the item that
emitted `filters=[]` in r0 and whose *registry stat was wrong* (0 of 913 live listings) in r1.

**Verdict: CLEAN. All prior findings resolved; verified live.** No blockers, no majors, no minors.
The previously-failing query class now emits the copy's SPECIFIC defining-family member id, is a
legal trade filter, and narrows correctly against live listings.

---

## 1. Harnesses — ALL GREEN (re-run 2026-07-27)
| Harness | Result |
|---|---|
| `python tests.py` | All self-tests passed |
| `BPC_SKIP_LIVE=1 python public/api/_verify.py` | ALL CHECKS PASSED (incl. the rewritten real-string LoM asserts + presence/reservation coverage) |
| `python tools/build_variant_registry.py --check --offline` | validated OK; 40 items, 38 stat_ids resolve, 0 crosscheck drops |
| `node public/site/test_picker.mjs` | 83 / 0 |
| `node public/site/test_scanstatus.mjs` | 47 / 0 |
| `node extension/test_protocol.mjs` | PASS |
| registry determinism | committed `variant_uniques.json` `items` == fresh `--offline` rebuild (byte-identical, 82415 bytes, 40 items) |

## 2. Prior findings — RESOLVED, confirmed in code + behavior
- **MAJOR-1 (dispatch, variants.md)** — fixed & holding. `variantreg.build_variant` (roll-defined/
  mod-variant branch, variantreg.py:299-319) dispatches by `emit` + the copy's actual mods
  (`is_presence` → notable presence flags; real `while affected by` → aura; else `def_ids`; else
  own-rolls). The old `family_all` blanket shadow is gone; the presence/def-id branches are live.
- **MAJOR r1-1 (LoM registry data, variants-r1.md)** — fixed. The Light of Meaning `defining` now
  carries rep `explicit.stat_1223932609` **plus `from.family_ids`** serialising all **15** members
  of the "Passive Skills in Radius also grant &lt;X&gt;" family; runtime folds `family_ids` into
  `def_ids` so a copy's specific member matches by its own id. The wrong legacy `stat_607548408`
  (Might of the Meek's mod) is gone.
- **Test-validity (fictional fixture)** — fixed. `_verify.py` phase_variant feeds REAL copies
  (`"…also grant 7% increased Evasion Rating"` → asserts `explicit.stat_3761482453 {min:7}`; mana →
  `stat_3382199855 {min:6}`), not the old fiction. Proven to fail on the old registry.

Offline through the real `build_variant` (deterministic), both real LoM copies now emit correctly:
```
"…also grant 7% increased Evasion Rating" -> [{explicit.stat_3761482453:{min:7}}]  label = the grant mod
"…also grant +6 to maximum Mana"          -> [{explicit.stat_3382199855:{min:6}}]  label = the grant mod
```
(In r0 both gave `filters:[]`; in r1 the registry's wrong id gave `filters:[]` for real copies.)

## 3. LIVE re-spot-check — The Light of Meaning defining-family member (the r1 poster child)
League **Allflame** (fetched live from `/api/trade/data/leagues`; the current PC challenge league).
Endpoint/UA/headers mirror `bpc/trade.py`. Budget: **1 search POST** (+ 1 `data/leagues` GET, not a
search) of the 6-POST cap; real UA (contact email); rate-limit headers read every call.

| # | Query (name=The Light of Meaning, type=Prismatic Jewel) | HTTP | total_found |
|---|---|---|---|
| A | `explicit.stat_3761482453` `{min:1}` (evasion grant — the CORRECTED family member) | 200 | **14** |

Contrast with variants-r1.md sec 3: the registry's OLD wrong id `stat_607548408` as a presence
filter returned **0 of 913** listings. The corrected member id returns **14** real listings (HTTP
200, legal, narrows from the 913 name-only universe r1 measured). Rate-limit state after the call:
ip-state `1:10:0, 1:60:0, 1:300:0` — deep headroom, no `Retry-After`, no 429/403/400.

**Conclusion:** the previously-failing query class is fixed end-to-end — offline the runtime emits
the copy's own family-member id with the real defining-mod label; live that filter is legal and
narrows to genuine listings. D-0019's "registry items get REQUIRED defining-mod filters" promise now
holds for The Light of Meaning (its only price handle — no ninja variant lines).

## 4. Adversarial notes / residual scope (unchanged, honestly restated)
- **Not re-litigated (out of budget, already documented, NOT regressions):** Aul's Uprising
  (reservation, family 116, `samples:[]`) and Vessel of Vinktar (lightning, family 18, `samples:[]`)
  intentionally keep the rep-id limitation → own-rolls (Aul's) / ninja map-variant (Vessel), exactly
  as `notes-variant-fix1.md`/`fix2.md` document. Both are strictly better than the old "aura variant"
  mislabel; neither is floor-only, so a missing trade filter is a bonus loss, not a wrong price. The
  broader "audit every family/`samples:[]` mod-variant entry against a live copy" (variants-r1.md
  sec 5 pt 3) remains a separate live-budget task — one live fetch per such entry would settle each.
  This is a completeness backlog item, not a defect in the resolved findings.
- No illegal (400) filter, no crash, no wrong price, no rate-limit violation observed.

## Budget / etiquette ledger
1 search POST (of the 6-POST hard cap) + 1 `data/leagues` GET. ≥3 s spacing (single POST). Real UA
(contact email); honored X-Rate-Limit-Ip / -Ip-State; no 400/403/429; only sanctioned
pathofexile.com trade endpoints. Offline confirmations used the vendored `build_variant` (no
network). Determinism rebuild written to an in-project `.scratch/` (deleted) to honor containment.
