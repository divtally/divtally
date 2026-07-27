# Launch post — ready to edit

Community announcement for DivTally. The honest architecture explanation *is*
the trust pitch — lead with it. Fill the `<PLACEHOLDER>`s (they mirror `config.js`), trim to fit
each venue (forum / Reddit / Discord), and post. Same story as the `/how-it-works` page.

The site is `https://divtally.com`. Remaining placeholders to fill:
- `<REPO-URL>` — your public, unminified source repo
- `<CHROME-URL>` / `<EDGE-URL>` / `<FIREFOX-URL>` — store listings once approved

---

## Title
```
[Tool] DivTally — paste a build link, get a full gear price breakdown (open source, no login)
```

## Body
```
Paste a public build link or a build import code and get the whole build priced — every
piece of gear, every flask, every skill + support gem — totaled in Chaos and Divine Orbs.

  ->  https://divtally.com

It's free, open source, needs no login, and — this is the important part — it never makes a single
trade-API call from a server. Here's exactly how it works and why that matters.

HOW IT WORKS (and why it's built this way)

Path of Exile's official trade API is the only source of live rare/unique prices, but two facts
make it impossible to price for thousands of visitors from one server:
  1) a web page isn't allowed to call it (the browser blocks cross-origin requests to it), and
  2) if everyone's searches went through one shared server IP, that IP would get rate-limited or
     banned within minutes.

So the tool splits the work by WHERE each price is allowed to come from:

  - The cache-friendly half — skill/support gems, currency, and uniques-by-name — comes from
    public economy data. One cached fetch serves everyone. This is the bulk of most
    builds and it's priced instantly, server-side, with zero trade calls.

  - Rare and unique items can only be priced live on the trade API — so those prices are produced
    on YOUR machine, never a server:
      * With nothing installed: each rare gets a one-click official trade-search link (priced on
        your own IP when you click), plus a paste-a-price box — paste the buyout whisper you copy
        in-game ("...listed for 35 chaos...") or just type "35c" / "2 div" and it folds into the
        total.
      * With the optional browser extension (below): those rare searches run automatically from
        your own browser and your own per-IP rate budget — hands-free, exactly as if you searched
        the trade site yourself.
      * Community cache: popular meta builds are pre-priced by the maintainer's own PC on a
        schedule and shared for a short time, so common builds often show rare prices for everyone
        with nothing installed.

The website itself NEVER receives price data from Grinding Gear Games' servers. Every trade price
you see arrived via a human paste, the community cache (seeded by a real machine), or the extension
running on a real user's IP. The server reads public economy data and builds trade links — nothing more.

THE OPTIONAL EXTENSION — "Trade Bridge"

If you want in-page live rare pricing without clicking each link, install the companion extension.
It's deliberately minimal and transparent:
  - Runs ONLY on this one website + the trade API path — nothing else.
  - Works completely logged out (credentials omitted): per-IP limits, zero account risk.
  - No cookies, no tabs, no history, no analytics, no tracking, collects no personal data.
  - Uses a careful built-in rate limiter that stays well under the trade API's per-IP limits.
  - Unminified and fully open source — read every line before you install.
  - Store-only distribution (no sideloading):
      Chrome:  <CHROME-URL>
      Edge:    <EDGE-URL>
      Firefox: <FIREFOX-URL>
The site is fully usable without it — the extension only automates the click.

FEATURES
  - Public build link OR build import code / paste-link as input.
  - Prices gear, flasks, jewels, and every skill + support gem (Awakened/Empower/Enlighten
    included — often the biggest cost).
  - Understands 5/6-links as a price factor on rares and uniques.
  - Totals in Chaos, shown alongside Divine, using live exchange rates.
  - Per-item trade links for anything not auto-priced.

ACCURACY / HONESTY CAVEATS
  - Server-side totals cover only economy-priced items (gems, currency, uniques-by-name), so the
    headline number is a FLOOR until rares are priced (via a click, a paste, the cache, or the
    extension).
  - Some variant uniques (Watcher's Eye, multi-mod jewels) can't be pinned to an exact roll from
    economy data alone — those show a range at low confidence, with an exact trade link. The
    extension can price them precisely.
  - Anything that can't be priced shows a trade link and NO number — never a misleading one.
  - Prices move constantly; treat everything as a snapshot.

OPEN SOURCE + TRANSPARENCY
  - Full source (site, function, worker, extension — all unminified): <REPO-URL>
  - How it works / privacy / rate-limit ethics / cache opt-out: https://divtally.com/how-it-works

Feedback, bugs, and "it mispriced X" reports very welcome.

Not affiliated with, endorsed by, or associated with Grinding Gear Games. "Path of Exile" is a
trademark of Grinding Gear Games.
```

---

### Venue trims
- **Reddit (r/pathofexile):** keep "HOW IT WORKS", the extension does/never list, and the caveats —
  that combination pre-empts the "is this safe / does it touch my account" questions.
- **Official forum:** the full text is fine; forums reward thoroughness.
- **Discord:** lead with the one-liner + `https://divtally.com`, then a 3-bullet "reads public economy
  data server-side, rares priced on your own IP, open source" and the repo link.
```
