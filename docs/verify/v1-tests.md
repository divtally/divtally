# v1 unit-test verification

**Date:** 2026-07-26
**Verdict:** PASS - suite is green AND provably offline.
**Environment:** Windows 11, Python 3.13.7, `requests` installed.

## How to run

Discovered from the file header (`tests.py` line 1: "Run: python tests.py"). It is a
flat script guarded by `sys.exit(1)` on any failure - no unittest/pytest discovery.

```
cd C:\scripts\buildpricechecker-poe1
python tests.py
```

## Result: GREEN

```
All self-tests passed.
EXIT: 0
```

All ~110 `check`/`approx` assertions passed. The real poe.ninja PoE1 character fixture
(`research/data/char_poe1.json`, 340 KB) is present, so the fixture-gated `normalize`
integration block RAN (not skipped) - confirmed by the absence of the
"(skipped char_poe1.json fixture tests...)" line and the presence of the
normalize/equipment/flask/jewel/gem assertions in the pass.

## Offline: CONFIRMED (this is the load-bearing check)

The suite imports `requests` and the whole `bpc` package (`trade.py`, `poeninja.py`,
`currency.py`, `engine.py`), so "it didn't obviously call the network" is not enough.
I re-ran it with the OS-level outbound-connection primitives monkeypatched to raise
BEFORE `tests.py` was imported:

```python
socket.getaddrinfo   -> raise   # DNS resolution
socket.create_connection -> raise
socket.socket.connect -> raise  # any direct connect()
runpy.run_path('tests.py', run_name='__main__')
```

Result: `All self-tests passed.` / `EXIT: 0`. With DNS and every connect path blocked,
a green run is proof that **zero live HTTP happened** - no trade search/fetch/exchange,
no poe.ninja call. Any accidental live call would have raised inside the guarded run.

(An earlier, more aggressive attempt that replaced `socket.socket` itself failed at
`import ssl` because `ssl.SSLSocket` subclasses `socket` - that TypeError was a test-harness
artifact of over-blocking, not a bpc network attempt. The connection-level block above is
the correct, non-destructive way to prove offline, and it passes.)

**No test performs a live trade search/fetch/exchange call.** All API-shaped surfaces are
driven by hand-built stubs/fakes:
- `StatMapper` -> `_FakeStatsClient` / `_FakeStats2` (inline stats JSON)
- `CurrencyConverter` -> built via `__new__` + `_FakeEcon` (no client)
- `PoeNinjaEconomy` -> built via `__new__` with `_gems` set directly
- `Pricer` -> built via `__new__`; only pure helpers exercised (`_spread`, `_links_filter`)
- `normalize` / `pob.parse` -> pure parsing over the local fixture + an inline PoB code
- `report.build_payload` -> `_ConvStub`

## Coverage vs RULE 8 (tests derive from README-documented promises)

Coverage of the documented contract is strong. Well-covered promises: input
auto-detection (poe.ninja URL parse incl. PoE2-link rejection, PoB-code detection),
category routing (frameType map incl. "ft5 is NOT a rune"), statmap polarity + group
scoping, sockets/links (5L/6L filter, `max_link`), gem name+level+quality+corruption
bucket pricing (incl. unknown -> None, PoB suffix fallback), Chaos-base/Divine-display
formatting, pseudo-resistance aggregation, tier math building blocks (median/percentile/
trim_outliers), Retry-After + rate-window rules, HC/SSF league normalization, non-dict
cache tolerance, defences-from-properties extraction, and the engine->UI JSON contract
(exalted->chaos rename). New-behavior-with-its-test discipline looks honoured.

### Gaps (all MINOR) - documented behaviors with no test

Each was grounded in both the README promise and the real code that implements it:

1. **`--status` / listing-status mapping is untested.** README documents a 5-row status
   table and the `--status online|any|onlineleague|available|securable` flag. Code:
   `Pricer.STATUS_OPTIONS` + `Pricer._status()` (pricing.py:224-239) validates the value
   and falls back to `online` for a bogus status. No test asserts `_status()` output or
   the bad-value fallback.

2. **Rare default "require ALL searchable affixes" is untested.** README (How it works ->
   Rares) and code `Pricer._rare_default` (pricing.py:~620, "require all of the item's
   searchable affixes") build the default rare query. Tests exercise `_links_filter` and
   statmap but never the rare query assembly / the all-affixes-required contract.

3. **Defences matched by TOTAL value via `armour_filters` is untested.** README promises
   defences are matched by total value (not individual affixes). Code builds
   `filt["armour_filters"]` (pricing.py:593,721). Tests cover `_defences` *extraction* from
   poe.ninja properties but not the total-value `armour_filters` query construction.

4. **Unpriceable -> trade link + NO number guardrail is untested.** README + CLAUDE.md
   guardrail: no-match items are left unpriced with a trade link, "never a misleading
   number." Code sets `r.confidence = "none"` on no-match (pricing.py:582,614). No test
   asserts a no-match yields confidence=none / null price while still emitting `trade_url`.
   Worth a test since it is an explicit correctness guardrail.

5. **`to_chaos` conversion for non-chaos currencies is untested.** README core promise:
   divine/chaos/mirror/exalted listing prices normalised to Chaos. Code
   `CurrencyConverter.to_chaos` multiplies `amount * rate(currency)` (currency.py:72-74).
   Tests only cover `to_chaos(3, "chaos")` (rate 1.0) plus `_lookup`/`divine_rate`; the
   actual multiply path (e.g. divine -> chaos) is never asserted end to end.

6. **Version-unique auto-detection is untested.** README (Uniques) promises Watcher's Eye /
   Loreweave-style "version uniques" are detected automatically (a build mod whose pattern
   is not shared by most listings -> narrow the search). No test covers this detection.
   (Harder to test offline; noted for completeness.)

None of these gaps affect the PASS verdict - they are missing tests, not failing ones.
Suggest filing them to `docs/backlog.md` as test-coverage tasks (RULE 7/8).

## Bottom line

`passed = true`: the suite runs green via `python tests.py` and is proven offline (green
under a full outbound-network block). Coverage against the README contract is good; six
minor documented-behavior coverage gaps are listed above for follow-up.
