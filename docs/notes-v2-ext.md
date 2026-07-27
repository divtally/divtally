# notes-v2-ext.md — D-0016 item 4 (extension side): return the whole price picture

**Date:** 2026-07-27  **Version:** extension 1.1.0 → **1.2.0**  **Spec:** D-0016 item 4 + D-0015.

## What changed (additive only — nothing renamed/removed)
`background.js` `priceQuery()` now returns a new **`prices`** field alongside the existing
`{ total, amount, currency, listingId }` + `debug`:

- `prices` = every fetched listing's buyout price as `[{ amount, currency }, …]` in **fetch order**.
  The search sorts price-ascending, so `prices[0]` equals the existing cheapest `amount`/`currency`
  fields (kept identical for backward compat).
- **Null-price listings are skipped** in `prices` but still counted in `debug.nulls`.
- A **no-buyout** item (results exist, none priced) returns `prices: []`.
- The **no-ids** early return (search found nothing) also returns `prices: []`.
- The page computes min/median/high tiers from this array with its own distribution math
  (trim + percentiles). Nothing is hidden or dropped — consistent with **D-0015** (no implicit
  affix exclusion; the whole fetched set is exposed for the user's sheet).

### `debug.nulls` semantics note
Old code returned early on the first priced listing, so `nulls` counted only null listings
*before* the first price. New code iterates ALL fetched listings to build `prices`, so `nulls` now
counts **every** null-price listing among the fetched set — a strict superset, more complete, and
purely diagnostic. Both existing test scenarios (`nobuyout` = all-null; `done` = single listing)
yield identical `nulls` under either definition, so no test regressed. Only the debug object of a
*priced* item with trailing null listings would differ — diagnostic-only, no consumer depends on it.

## Backward compatibility (old site ↔ new ext, and vice versa)
- Pre-existing fields (`total`/`amount`/`currency`/`listingId`/`debug`) are byte-for-byte the same.
- An **old site** (reads only the cheapest fields) works unchanged against a v1.2.0 extension.
- A **new site** (wants `prices`) works against an **old v1.1.0** extension too — it just gets no
  `prices` field and falls back to the single cheapest number.
- Protocol version stays **1.1** (progress protocol unchanged). `prices` is a plain additive result
  field, not a new handshake — no `protocolVersion` gating needed.

## Files touched (all owned)
- `extension/background.js` — `priceQuery()` collects `prices`; three return sites carry it.
  `node --check` OK.
- `extension/test_protocol.mjs` — asserts `prices` in Scenario A (`[{12,chaos}]` for the priced
  item, `[]` for no-buyout) and adds **Scenario E** (4 listings, one null → `prices` length 3,
  fetch order preserved, `prices[0]` == cheapest, `debug {200,200,4,1}`). **All 44 checks green.**
- `extension/manifest.json` + `extension/manifest.dev.json` — version `1.1.0` → `1.2.0`.
- `extension/README.md` — protocol section documents `prices` (v1.2.0, additive); version + zip
  filename references bumped to 1.2.0.
- `public/dist/` — rebuilt `divtally-extension-chrome-edge-1.2.0.zip` +
  `divtally-extension-firefox-1.2.0.zip` (both verified: manifest version 1.2.0, new `prices` code
  present). Stale 1.1.0 zips removed (gitignored build artifacts; clean cutover per RULE 6).
  `build_zips.py` exited 0 (placeholder guard passed).

## Verification run after each edit (owner instruction)
- After `background.js`: `node --check` OK.
- After `test_protocol.mjs`: `node --check` OK + full harness **RESULT: PASS (all checks passed)**.
- Zips: inspected both archives — manifest `version=1.2.0`, `prices.push` + `prices: []` present.

## Store note (from D-0016 item 4)
v1.1.0 is already submitted to Chrome; **v1.2.0 ships as a normal store update after**. Site-side
tier math (trim + percentiles) is the paired page-side work — NOT in this extension batch.
