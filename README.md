# buildpricechecker (bpc)

Estimate the currency cost of a **Path of Exile 2** build by pasting a
[poe.ninja](https://poe.ninja/poe2/builds) character link. It pulls the character's
gear/flasks/jewels/runes/gems and prices each item against the official
**pathofexile.com trade2** API, reporting three budget tiers:

| Tier | Meaning |
|------|---------|
| **min** | cheapest realistic listing (scam-low outliers trimmed) |
| **median** | typical going price |
| **high** | ~90th percentile — a clearly better-rolled / corrupted copy |

All prices are normalised to **Exalted Orbs** (the PoE2 base currency) and also shown
in **Divine Orbs** for readability.

## Install

Requires Python 3.9+ and `requests`:

```powershell
cd C:\scripts\buildpricechecker
pip install -r requirements.txt
```

## Usage

### Web UI (paste into a browser box)

```powershell
.\bpc-web.cmd            # opens http://127.0.0.1:8765 in your browser
```

Paste the character link, click **Estimate**, watch live progress, and get a styled
table (confidence badges, per-item trade links, totals). Runs entirely on your machine.
Options pass through, e.g. `.\bpc-web.cmd --port 9000 --no-browser`.

#### Choose a look (UI versions)

The landing page (`/`) is a **gallery**: every version drives the *same* engine and live
prices — only the interface differs. Pick whichever you like; it's just a bookmark.

| Version | URL | What it is |
|---------|-----|------------|
| **The Exilarch's Ledger** | `/v/ledger` | Itemized thermal-receipt with a running subtotal + barcode. |
| **Abacus Terminal** | `/v/abacus` | Keyboard-first TUI: a job log and box-drawn price tables. |
| **Stash Tab** | `/v/stash` | PoE-diegetic gear slots + a quad-stash grid; hover for priced tooltips. |
| **Cargo Manifest** | `/v/manifest` | Boarding-pass / shipping manifest with a barcoded fare total. |
| **Build Facts** | `/v/facts` | An FDA nutrition label: bold rules, % of total per slot, one giant Cost. |
| **Budget Waterfall** | `/v/waterfall` | A data-viz cost cascade — each item stacks onto a running budget bar. |
| **Card Binder** | `/v/binder` | Your build as a trading-card binder; review rares one card at a time. |
| **Foundry Schematic** | `/v/foundry` | A drafting-table blueprint with a titleblock cost stamp. |
| **Operator's Console** | `/v/console` | A sci-fi HUD: radial budget gauges and a scanning sweep as it prices. |
| **Atelier** | `/v/atelier` | A calm editorial spread: enormous total, the breakdown on demand. |

The classic UI remains at **`/classic`** (unchanged). New versions are auto-discovered:
drop a self-contained `*.html` into `bpc/ui/` (it drives the shared engine at
`/assets/core.js`) and it appears in the gallery. Append `?mock` to any version URL
(e.g. `/v/ledger?mock`) to preview a full demo build with no trade calls.

When you price a poe.ninja build, the page also shows that character's **Path of Building 2
import code** (with a **Copy** button) for reference, so you can paste it straight into PoB.

**League & listings dropdowns:** next to the link, pick the trade **league** (Auto = the
build's own league) and the **listing status** — the same options the PoE2 trade site
offers (Instant Buyout and In Person / Instant Buyout / In Person (Online in League) /
In Person (Online) / Any). Both apply to every item search and are remembered between
sessions (along with the advanced checkbox). **Changing any control — league, listing
status, advanced affix search, or fresh pull — immediately re-runs whatever build is
currently loaded with the new setting**, so you can flip from In Person (Online) to Any
(or switch leagues) and see it re-price on the spot. This works for a build you pasted
*and* for one you loaded from the Recent list.

**Recent builds:** the page lists your 5 most recently searched builds; **See more**
expands to every cached snapshot (the same character priced on different days appears
once per version). Click one to reload it **straight from your local cache** — this works
even if the poe.ninja profile has since been deleted. **Loading a build shows its
last-saved prices instantly and does no trade searching**; a build's full priced result is
remembered between sessions. To refresh prices, use **Search all again** (re-runs every
search) — changing the league/listing-status also re-searches, since those change the
results. The CLI equivalent is `recover.py` (see below).

**Include/exclude items:** every row has a checkbox (plus an "all" toggle per section).
Untick an item to drop it from the totals — the min/median/high recompute instantly and
the excluded row is greyed out (desaturated, prices struck through). Handy for "what does
this build cost without the Mageblood / mirror-tier rare?"

**Advanced affix search** (checkbox next to the link): rares are queued for you one at a
time. For each rare you see its affixes — tick the ones a comparable item must have and set
min/max per affix — then "Search this item" and you're immediately shown the next rare. The
uniques/runes/gems price in the background the whole time, so the table keeps filling while
you choose; each rare you submit is queued and priced without breaking the flow. **Skip
(don't price)** leaves that rare out entirely (no search). Leave the box unchecked and rares
are priced automatically, requiring **all** of the item's affixes to be present (extras
allowed).

Every rare row also has an **edit affixes** button (advanced mode). Click it any time —
even after the build has finished pricing — to re-open that rare's affix picker, change the
selection/min-max, and re-search just that one item; its row (and the totals) update in
place. Handy for narrowing or widening a single rare after you've seen what it costs.

When a rare has resistance mods, the picker shows a **"combine resistances into a pseudo
total"** toggle (on by default). It collapses the individual fire/cold/lightning/"all
elemental" rolls into the trade site's combined **+#% total Elemental Resistance** pseudo
stat (and a **total Chaos Resistance** pseudo), prefilled with the item's actual total — so
you match an item's *overall* resistance instead of each specific roll, which is how PoE2's
trade search natively groups them. Untick it to go back to individual resistance affixes.

### Command line

```powershell
# pass the URL as an argument
.\bpc.cmd "https://poe.ninja/poe2/builds/runesofaldur/character/example-0416/ResurrectGodAura"

# or just run it and paste when prompted
.\bpc.cmd

# equivalently, without the launcher:
python -m bpc "<url>"          # CLI
python -m bpc.web              # web UI
```

The one input field accepts any of:
- a **poe.ninja character link** (it contains `/character/` — browse
  https://poe.ninja/poe2/builds, click a character, copy the URL);
- a **Path of Building 2 import code** (PoB → Import/Export → "Generate"/"Copy");
- a **PoB paste link** — pobb.in, pastebin, or a poe.ninja PoB link.

It auto-detects which one you pasted. PoB codes carry no league, so those price against
the current softcore league by default (use the league box to override).

### Options

```
--league NAME   price against a different trade league (e.g. "Standard", "HC Runes of Aldur")
--status WHICH  listing status: online (default) | any | onlineleague | available | securable
--json          emit machine-readable JSON instead of the table (includes trade_url per item)
--fresh         fresh pull: ignore all caches and fetch everything fresh (alias: --refresh)
-q, --quiet      suppress progress output
--version
```

If the build is on a league that the trade site doesn't list (e.g. an SSF league, which
maps to its tradeable equivalent automatically, or a since-rolled-over league), bpc tells
you the available leagues and you can re-run with `--league`.

## How it works

1. **Input** — the poe.ninja link is parsed into `(league, account, character)`.
   `poe.ninja/poe2/api/data/index-state` resolves the league to a data snapshot, then
   `poe.ninja/poe2/api/builds/<version>/character?...` returns the full character JSON
   (the same item data poe.ninja shows, including a Path of Building export).
2. **Pricing** — each item is priced via the official trade2 API:
   * **Uniques** — searched by name + base type; the listing distribution gives the tiers.
     Most uniques have fixed affixes, so name is enough. A few are **version uniques**
     (e.g. Darkness Enthroned's "…as though it was a Body Armour", or Loreweave's
     ring-derived mods) where copies differ. These are detected automatically — a build
     mod whose pattern isn't shared by most current listings is treated as version-specific
     and the search is narrowed to the build's exact version (when enough are listed;
     otherwise the broad price is shown and flagged with a trade link). No hardcoded list.
   * **Rares** — searched by base type (or item category). By default a comparable must
     carry **all** of the item's searchable affixes (extras allowed); in *advanced* mode
     you choose the affixes and min/max per item. **Defences** (armour / evasion / energy
     shield / ward) are matched by the item's **total value** (via trade equipment filters),
     not by the individual defence affixes — that's how the trade site searches them and it
     sidesteps the local-vs-global stat ambiguity. Resistances can be folded into a pseudo
     total. Genuinely uncommon/crafted items that nothing matches are left unpriced with a
     trade link rather than a misleading number.
   * **Runes / Soul Cores** — priced from the bulk currency exchange.
   * **Magic flasks/charms** — priced by base type (these are typically cheap).
   * **Gems** — listed per **active skill** (with its support gems), priced from **poe.ninja
     economy data** (no trade searches, so no ban risk). Each skill's cost is the *uncut*
     DIY price — the Uncut Skill Gem at its level **+** the Jeweller's Orbs for its support
     sockets (Lesser→3, Greater→4, Perfect→5) — plus any **lineage** support gems (the only
     supports worth pricing). That uncut total feeds the build total. Normal support gems are
     free. Clicking a skill opens a pre-built trade search for it (right level + sockets) with
     no API call. (poe.ninja tracks only uncut gems, so the finished "cut" gem is a link, not
     a number.)
3. **Currency** — divine/chaos/mirror/etc. listing prices are converted to Exalted using
   live exchange rates.

### Rate limiting

The trade API is strict (violations cause temporary IP bans). The client reads GGG's
`X-Rate-Limit` headers, stays well under every window, honours `Retry-After`, and caches
results (reference data for a day, prices for 30 min, league/rates for hours) so repeat
runs are fast and cheap. A full fresh build takes ~1–4 minutes; re-runs are near-instant.
Nothing here requires logging in (no POESESSID).

## Limitations / accuracy

* **Rare pricing is approximate.** A specific rare's exact mod combination is often
  unique, so we price "an item roughly this good." Treat rare rows as ballparks; the
  per-item confidence and `trade_url` (in `--json`) let you verify.
* **Uniques and the big-ticket items are accurate** (real listing distributions).
* poe.ninja snapshots are not real-time; a character's gear may be a few hours/days old.
* Gem cost is a rough aggregate and ignores specific gem levels/quality and spirit gems.
* Prices move constantly; this is a snapshot estimate, not a quote.

## Project layout

```
bpc/
  cli.py        CLI entry point / argument handling / output encoding
  web.py        local web UI (stdlib http.server; serialised pricing jobs)
  engine.py     shared pipeline (URL -> items -> pricing) used by cli + web
  poeninja.py   URL parsing + character fetch + item normalisation
  trade.py      trade2 client: rate limiter, search/fetch/exchange, data caches
  statmap.py    map item mod text -> trade stat-filter ids (for rares)
  pricing.py    per-item query building + distribution -> min/median/high
  currency.py   exchange-rate lookups + Exalted/Divine formatting
  report.py     terminal table + JSON rendering
  models.py     dataclasses (Item / PriceResult / BuildEstimate)
  cache.py      tiny JSON disk cache with TTL
research/       reverse-engineering probes used to build this (not needed at runtime)
cache/          runtime cache (auto-created)
```
