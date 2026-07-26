# Docs + launchers port notes (PoE2 -> PoE1)

Written by the docs/launcher-port agent, 2026-07-26. Covers the root-level docs and
launchers only (`README.md`, `app.py`, `run.py`, `recover.py`, `bpc.cmd`, `bpc-web.cmd`,
`requirements.txt`). Grounded in the ported `bpc/` code I read + the research docs; nothing
here is from memory. `[INFERRED]` marks anything not directly read from source.

## What was ported (files I own)

- **README.md** — full rewrite for PoE1, parent structure/tone preserved.
- **app.py** — banner `PoE2 Build Price Checker` -> `PoE1 Build Price Checker`. No paths.
- **bpc.cmd** — comment + usage example: `PoE2` -> `PoE1`, `poe2/builds` -> `poe1/builds`.
  ASCII-clean (byte-verified).
- **bpc-web.cmd** — comment `PoE2` -> `PoE1`. ASCII-clean (byte-verified).
- **recover.py** — removed a dead call + injected the poe.ninja economy (see below).
- **run.py**, **requirements.txt** — inspected, **no change needed** (no PoE2 strings, no
  hardcoded old-folder paths, generic docstring/deps).

Verified:
- `python -m bpc --version` -> `bpc 0.1.0`.
- `bpc.cmd --version` (via full path) -> `bpc 0.1.0`.
- `python recover.py -h` prints usage cleanly.
- `python -m py_compile app.py run.py recover.py` -> OK.
- Neither `.cmd` file has any byte > 127.

## recover.py — two substantive fixes (not just strings)

1. **Removed `items = poeninja.dedupe_runes(items)`** (was a hard crash waiting to happen).
   `dedupe_runes` was **deleted** in the core port (rune concept gone entirely, per
   `docs/port-notes-core.md` / RULE 6). The call sits inside `main()` after argparse, so
   `recover.py -h` never reached it, but any real recovery run would have thrown
   `AttributeError`. This was a PoE2 leftover, so removing it is in-scope.

2. **Injected the poe.ninja economy into the `Pricer`.** recover.py builds its `Pricer`
   directly (it bypasses `engine.prepare_*`, which is where the economy is normally
   wired). The core port made `Pricer(..., economy=None)` the default, and with
   `economy=None` the `CurrencyConverter` falls back to the trade **`exchange`** endpoint
   for every non-chaos conversion — the exact ban-risk call the port set out to eliminate
   (D-0003 / port-notes-core "the parent's per-run ban-risk exchange call is eliminated
   for the normal path"). I now build `econ = poeninja.PoeNinjaEconomy(meta.league)` and
   pass `economy=econ`, mirroring `engine.prepare_from_cache` exactly (same
   `meta.league` source-economy argument). This keeps recovery runs on poe.ninja rates.
   - `PoeNinjaEconomy` is referenced only inside `main()` at runtime; verified the class
     exists (`bpc/poeninja.py:194`). A full recovery run needs live trade searches, which
     this agent is forbidden to make, so runtime pricing was NOT exercised end-to-end here
     — flagged for the coordinator's own live check.

## README — what changed vs the parent, and why (RULE 8: README is the contract)

Every claim below was reconciled against the ported code I read; where the code and the
old README disagreed, the code (PoE1 truth) won.

- **Game/branding:** PoE2 -> PoE1 throughout; poe.ninja links `poe.ninja/poe2/...` ->
  `poe.ninja/poe1/...`; trade2 -> trade.
- **Currency:** Exalted-base -> **Chaos-base**, Divine shown alongside (D-0002/D-0003).
  Step-3 rewritten: normalised to Chaos via **poe.ninja economy rates**, trade
  bulk-exchange only a fallback (was "converted to Exalted using live exchange rates").
- **Example CLI URL:** now the live-verified
  `https://poe.ninja/poe1/builds/allflame/character/example-0416/TestCharacter`
  (from `docs/research/poeninja-poe1.md:50`).
- **Gems section fully rewritten** to the new truth (port-notes-core): PoE1 gems are real
  tradeable items priced by name+level+quality+corruption from the poe.ninja SkillGem
  economy; **every** support gem is priced (Awakened/Empower/Enlighten/Enhance are the
  expensive ones). The entire uncut-gem + Jeweller's-Orb-ladder + lineage model is gone.
  Limitations line updated to "matched to the nearest tracked level/quality/corruption
  bucket" (was "ignores specific gem levels/quality and spirit gems").
- **Runes / Soul Cores section DELETED** from How-it-works (PoE1 has none). The intro's
  item list dropped "runes"; "Magic flasks/charms" -> "Magic flasks" (no charms).
- **Links section ADDED** to How-it-works + Limitations: 5L/6L body armour / 2H weapons
  carry a link filter so a 6L compares to 6Ls (port-notes-core "sockets/LINKS").
- **Defences:** now via the trade `armour_filters` (PoE1 has no `equipment_filters`).
- **Listing statuses:** documented all **5** with their trade-site labels (Instant Buyout
  and In Person / Instant Buyout / In Person (Online in League) / In Person (Online),
  default / Any), matching `bpc/web.py` lines 711-716 and `bpc/cli.py` `--status` choices.
  **The task premise ("PoE1 statuses only", implying pruning) is wrong** — per
  `docs/research/trade1.md` section 5, all five `status.option` values exist in PoE1; the
  parent's `Pricer.STATUS_OPTIONS` is unchanged (confirmed at `bpc/pricing.py:224`).
- **PoB terminology:** "Path of Building 2" -> "Path of Building" (PoE1 uses the PoB
  Community fork). CLI/web input still accepts poe.ninja link / PoB code / pobb.in link
  (matches `bpc/cli.py` help + `bpc/web.py` placeholder).
- **Version-unique examples:** swapped PoE2 examples (Darkness Enthroned) for PoE1 ones
  (Watcher's Eye variable-aura mods, Loreweave ring-derived resistance). Illustrative of
  the auto-detection mechanism (which is ported parent code), not a pricing-math claim.
- **Options block** matches `bpc/cli.py` exactly: `--league`, `--status` (5 choices,
  default `online`), `--json`, `--fresh`/`--refresh`, `-q/--quiet`, `--version`.
- **Project-layout** module blurbs updated (trade client not "trade2 client"; currency
  "Chaos/Divine formatting"; poeninja "+ gem/currency economy"; pricing "+ gem/link
  pricing"). `models.py` no longer lists CAT_RUNE.
- Kept the **10-skin gallery table**, `?mock`, recent-builds, include/exclude, and
  advanced-affix sections structurally (contract.md section 5 says they are unchanged);
  edited only the currency word, the "runes/gems" -> "gems" phrase, and the
  "how PoE2's trade groups them" -> "how the trade search groups them" line.

## Concerns for the coordinator / P2 (web+UI port)

- **`bpc/web.py:847` still literally renders `"Path of Building 2 import code"`** (and the
  JS `metaHead()` around it). This is a PoE2 leftover in P2's file (not mine to edit). The
  README now says "Path of Building" (the PoE1 truth). Per RULE 8, the code is the bug —
  **P2/coordinator should fix that string** so the page and README agree.
- **README `?mock`, the skin gallery, and the gem/rune/currency UI wording** describe P2's
  in-flight web/UI port (contract.md). I documented the *contracted* PoE1 behavior; if P2
  diverges from `docs/research/contract.md`, reconcile the README in the same turn.
- **recover.py runtime pricing not exercised** (needs live trade searches — forbidden to
  this agent). The `-h` path and imports are verified; the coordinator should do one live
  recovery run to confirm the economy injection prices correctly end-to-end.
- **SEARCH_BUDGET=30** (noted in port-notes-core) means recover.py, like the CLI, will mark
  overflow items "skipped" on jewel-heavy builds — expected ban-safety, not a bug.
