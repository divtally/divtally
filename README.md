# buildpricechecker (bpc) - Path of Exile 1

Estimate the currency cost of a **Path of Exile 1** build by pasting a
[poe.ninja](https://poe.ninja/poe1/builds) character link. It pulls the character's
gear/flasks/jewels/gems and prices each item against the official
**pathofexile.com trade** API, reporting three budget tiers:

| Tier | Meaning |
|------|---------|
| **min** | cheapest realistic listing (scam-low outliers trimmed) |
| **median** | typical going price |
| **high** | ~90th percentile — a clearly better-rolled / corrupted / linked copy |

All prices are normalised to **Chaos Orbs** (PoE1's trade index standard) and also shown
in **Divine Orbs** for readability.

## Install

Requires Python 3.9+ and `requests`:

```powershell
cd C:\scripts\buildpricechecker-poe1
pip install -r requirements.txt
```

## Usage

### Web UI (paste into a browser box)

```powershell
.\bpc-web.cmd            # opens http://127.0.0.1:8765 in your browser
```

Paste the character link, click **Appraise**, watch live progress, and get a styled
table (confidence badges, per-item trade links, totals). Runs entirely on your machine.
Options pass through, e.g. `.\bpc-web.cmd --port 9000 --no-browser`.

#### The look (and alternate UI versions)

The landing page (`/`) is the **Stash Tab** skin — PoE-diegetic gear slots + a quad-stash
grid, hover for priced tooltips (the primary, owner-picked interface; D-0007). Alternate
looks still exist at `/gallery`: every version drives the *same* engine and live prices —
only the interface differs.

| Version | URL | What it is |
|---------|-----|------------|
| **Stash Tab** (default, at `/`) | `/v/stash` | PoE-diegetic gear slots + a quad-stash grid; hover for priced tooltips. |
| **The Exilarch's Ledger** | `/v/ledger` | Itemized thermal-receipt with a running subtotal + barcode. |
| **Abacus Terminal** | `/v/abacus` | Keyboard-first TUI: a job log and box-drawn price tables. |
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

When you price a poe.ninja build, the page also shows that character's **Path of Building
import code** (with a **Copy** button) for reference, so you can paste it straight into PoB.

**League & listings dropdowns:** next to the link, pick the trade **league** (Auto = the
build's own league) and the **listing status** — the same options the PoE1 trade site
offers:

| Listing status | Meaning |
|----------------|---------|
| **Instant Buyout and In Person** | any listing with a price (buyout or negotiable) |
| **Instant Buyout** | only fixed buyout listings |
| **In Person (Online in League)** | seller online, playing in this league |
| **In Person (Online)** *(default)* | seller currently online |
| **Any** | every listing, online or not |

Both apply to every item search and are remembered between sessions (along with the
advanced checkbox). **Changing any control — league, listing status, advanced affix
search, or fresh pull — immediately re-runs whatever build is currently loaded with the
new setting**, so you can flip from In Person (Online) to Any (or switch leagues) and see
it re-price on the spot. This works for a build you pasted *and* for one you loaded from
the Recent list.

**Recent builds:** the page lists your 5 most recently searched builds; **+N more**
expands to every cached snapshot (the same character priced on different days appears
once per version). Click one to reload it **straight from your local cache** — this works
even if the poe.ninja profile has since been deleted. **Loading a build shows its
last-saved prices instantly and does no trade searching**; a build's full priced result is
remembered between sessions. To refresh prices, use **Search all again** (re-runs every
search) — changing the league/listing-status also re-searches, since those change the
results. The CLI equivalent is `recover.py` — it reloads a cached build snapshot from the
command line, even if the poe.ninja profile is gone.

**Include/exclude items:** every row has a checkbox (plus an "all" toggle per section).
Untick an item to drop it from the totals — the min/median/high recompute instantly and
the excluded row is greyed out (desaturated, prices struck through). Handy for "what does
this build cost without the Mageblood / mirror-tier rare?"

**Advanced affix search** (checkbox next to the link): rares are queued for you one at a
time. For each rare you see its affixes — tick the ones a comparable item must have and set
min/max per affix — then "Search this item" and you're immediately shown the next rare. The
uniques and gems price in the background the whole time, so the table keeps filling while
you choose; each rare you submit is queued and priced without breaking the flow. **Skip
(don't price)** leaves that rare out entirely (no search). At the top of the picker, the
glowing **Autoscan (N)** button prices every remaining rare immediately with the default
all-affix search, and a small **skip all (don't price)** below it drops them all instead.
Leave the box unchecked and rares are priced automatically, requiring **all** of the item's
affixes to be present (extras allowed).

Every rare row also has an **edit affixes** button (advanced mode). Click it any time —
even after the build has finished pricing — to re-open that rare's affix picker, change the
selection/min-max, and re-search just that one item; its row (and the totals) update in
place. Handy for narrowing or widening a single rare after you've seen what it costs.

When a rare has resistance mods, the picker shows a **"combine resistances into a pseudo
total"** toggle (on by default). It collapses the individual fire/cold/lightning/"all
elemental" rolls into the trade site's combined **+#% total Elemental Resistance** pseudo
stat (and a **total Chaos Resistance** pseudo), prefilled with the item's actual total — so
you match an item's *overall* resistance instead of each specific roll, which is how the
trade search natively groups them. Untick it to go back to individual resistance affixes.

### Command line

```powershell
# pass the URL as an argument
.\bpc.cmd "https://poe.ninja/poe1/builds/allflame/character/example-0416/TestCharacter"

# or just run it and paste when prompted
.\bpc.cmd

# equivalently, without the launcher:
python -m bpc "<url>"          # CLI
python -m bpc.web              # web UI
```

The one input field accepts any of:
- a **poe.ninja character link** (it contains `/character/` — browse
  https://poe.ninja/poe1/builds, click a character, copy the URL);
- a **Path of Building import code** (PoB → Import/Export → "Generate"/"Copy");
- a **PoB paste link** — pobb.in, pastebin, or a poe.ninja PoB link.

It auto-detects which one you pasted. PoB codes carry no league, so those price against
the current softcore league by default (use the league box to override).

### Options

```
--league NAME   price against a different trade league (e.g. "Standard", "Hardcore")
--status WHICH  listing status: online (default) | any | onlineleague | available | securable
--json          emit machine-readable JSON instead of the table (includes trade_url per item)
--fresh         fresh pull: ignore all caches and fetch everything fresh (alias: --refresh)
-q, --quiet     suppress progress output
--version
```

(`--status` maps to the trade site's statuses: `online` = In Person (Online),
`onlineleague` = In Person (Online in League), `available` = Instant Buyout and In Person,
`securable` = Instant Buyout, `any` = Any.)

If the build is on a league that the trade site doesn't list (e.g. an SSF league, which
maps to its tradeable equivalent automatically, or a since-rolled-over league), bpc tells
you the available leagues and you can re-run with `--league`.

## How it works

1. **Input** — the poe.ninja link is parsed into `(slug, account, character)`.
   `poe.ninja/poe1/api/data/index-state` resolves the league slug to a data snapshot
   version, then `poe.ninja/poe1/api/builds/<version>/character?account=...` returns the
   full character JSON (the same item data poe.ninja shows, including a Path of Building
   export).
2. **Pricing** — each item is priced via the official pathofexile.com trade API:
   * **Uniques** — searched by name + base type; the listing distribution gives the tiers.
     Most uniques have fixed affixes, so name is enough. A few are **version uniques**
     (e.g. Watcher's Eye's variable aura mods, or Loreweave's ring-derived resistance mods)
     where copies differ. These are detected automatically — a build mod whose pattern
     isn't shared by most current listings is treated as version-specific and the search is
     narrowed to the build's exact version (when enough are listed; otherwise the broad
     price is shown and flagged with a trade link). No hardcoded list.
   * **Rares** — searched by base type (or item category). By default a comparable must
     carry **all** of the item's searchable affixes (extras allowed); in *advanced* mode
     you choose the affixes and min/max per item. **Defences** (armour / evasion / energy
     shield / ward) are matched by the item's **total value** (via the trade `armour_filters`),
     not by the individual defence affixes — that's how the trade site searches them and it
     sidesteps the local-vs-global stat ambiguity. Resistances can be folded into a pseudo
     total. Genuinely uncommon/crafted items that nothing matches are left unpriced with a
     trade link rather than a misleading number.
   * **Links** — a **5-link / 6-link** is a major price component in PoE1. Any body armour
     or two-handed weapon with 5+ linked sockets carries a link filter in its search, so a
     6-link is compared against other 6-links (not the cheap unlinked base).
   * **Magic flasks** — priced by base type (these are typically cheap).
   * **Gems** — PoE1 skill gems are real tradeable items, so each is priced by
     **name + level + quality + corruption** from **poe.ninja economy data** (no trade
     searches, so no ban risk). Every socketed gem in a skill setup is priced, not just the
     active one: the **Awakened / Empower / Enlighten / Enhance** support gems are often the
     biggest single cost in a build. Clicking a skill opens a pre-built trade search for
     that gem (right level + quality) with no API call. A gem poe.ninja doesn't track shows
     as a link, not a number.
3. **Currency** — divine/chaos/mirror/etc. listing prices are normalised to **Chaos**
   using live **poe.ninja** economy rates (the trade bulk-exchange endpoint is only a
   fallback for a currency poe.ninja doesn't list). Totals are shown in Chaos and in Divine.

### Rate limiting

The trade API is strict (violations cause temporary IP bans). The client reads GGG's
`X-Rate-Limit` headers, stays well under every window, honours `Retry-After`, and caches
results (reference data for a day, prices for ~30 min, league lists ~10 min and currency rates ~30 min) so repeat
runs are fast and cheap. Because gem prices *and* currency rates come from poe.ninja (not
the trade API), a build uses fewer trade searches than the item count alone would suggest.
A full fresh build takes ~1–4 minutes; re-runs are near-instant. Nothing here requires
logging in (no POESESSID).

## Limitations / accuracy

* **Rare pricing is approximate.** A specific rare's exact mod combination is often
  unique, so we price "an item roughly this good." Treat rare rows as ballparks; the
  per-item confidence and `trade_url` (in `--json`) let you verify.
* **Uniques and the big-ticket items are accurate** (real listing distributions), and
  5L/6L body armours / weapons are priced with their link count.
* poe.ninja snapshots are not real-time; a character's gear may be a few hours/days old.
* **Gem prices come from poe.ninja economy snapshots**, matched to the nearest tracked
  level/quality/corruption bucket — close, but not the exact listing you'd find on trade.
* Prices move constantly; this is a snapshot estimate, not a quote.

## Project layout

```
bpc/
  cli.py        CLI entry point / argument handling / output encoding
  web.py        local web UI (stdlib http.server; serialised pricing jobs)
  engine.py     shared pipeline (URL -> items -> pricing) used by cli + web
  poeninja.py   URL parsing + character fetch + item normalisation + gem/currency economy
  trade.py      trade client (pathofexile.com/api/trade): rate limiter, search/fetch/exchange, caches
  statmap.py    map item mod text -> trade stat-filter ids (for rares)
  pricing.py    per-item query building + distribution -> min/median/high (+ gem/link pricing)
  pob.py        Path of Building import-code / paste-link parsing
  currency.py   exchange-rate lookups + Chaos/Divine formatting
  util.py       mod-text and misc shared helpers
  report.py     terminal table + JSON rendering
  models.py     dataclasses (Item / PriceResult / BuildEstimate)
  cache.py      tiny JSON disk cache with TTL
research/       reverse-engineering probes used to build this (not needed at runtime)
cache/          runtime cache (auto-created)
```
