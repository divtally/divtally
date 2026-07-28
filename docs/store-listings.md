# Store listing copy — DivTally Browser Extension

Ready-to-paste listing text for the Chrome Web Store, Microsoft Edge Add-ons, and Firefox AMO.
One identity everywhere (name / icon / publisher / linked domain) per the B-001 trust checklist.
The site URL (`https://divtally.com`) and the source repo
(`https://github.com/divtally/divtally`, public) are both filled in — this copy is paste-ready.
Not affiliated with Grinding Gear Games.

Artifacts to upload: `public/dist/divtally-extension-chrome-edge-1.2.1.zip` (Chrome + Edge),
`public/dist/divtally-extension-firefox-1.2.1.zip` (Firefox). Store fees: Chrome one-time $5 dev
registration; Edge free; Firefox AMO free.

---

## Title (all stores)
```
DivTally Browser Extension
```

## Short summary / subtitle (≤132 chars — Chrome "summary", Edge "short description", AMO summary)
```
DivTally - what does that Path of Exile build cost? Prices rares & uniques from your own browser & IP. Logged-out, open source.
```

## Full description (paste into the long-description field)
```
DivTally - what does that Path of Exile build cost?

This is the companion extension for DivTally, the free, open-source website that turns a public
build link or a build import code into a full gear price breakdown in Chaos and Divine Orbs.
Most of that pricing comes from public economy data - but live prices for RARE and UNIQUE items
can only come from Path of Exile's official trade API, and a browser page is not allowed to call
that API directly (the browser blocks it, and pricing for thousands of visitors through one shared
server address would get that address rate-limited or banned).

This extension solves that the honest way: when you ask DivTally to price a rare or unique, the
search runs FROM YOUR OWN BROWSER AND YOUR OWN IP ADDRESS, using your personal per-IP rate budget
- exactly as if you searched on the official trade site yourself. DivTally never touches the
trade API. Install it only if you want in-page live rare/unique pricing; the website is fully
usable without it (clickable trade links + paste-a-price still work).

WHAT IT DOES
- Runs official trade searches from your browser when DivTally asks, and
  returns the cheapest online listing price for each rare/unique.
- Uses a careful, built-in rate limiter (ported from the app) that stays well under Path of
  Exile's published per-IP limits and honours the server's back-off headers.
- Works completely logged out. It never signs into your account.
- Activates ONLY on the DivTally website (a single domain you can see in the manifest).

WHAT IT NEVER DOES
- Never reads or sends your Path of Exile login, session, or account data (requests are sent
  logged-out, credentials omitted).
- Never collects, tracks, or transmits any personal data to us or anyone else. No analytics.
- Never runs on any site other than the DivTally domain and the trade API.
- Never touches cookies, browsing history, tabs, or other websites.
- Never obfuscates its code - the entire extension is unminified and readable, and the full
  source is public.

OPEN SOURCE
Full source (unminified): https://github.com/divtally/divtally
How it works / privacy / rate-limit ethics: https://divtally.com/how-it-works

NOT AFFILIATED
This is a fan-made tool. It is not affiliated with, endorsed by, or associated with Grinding Gear
Games. "Path of Exile" is a trademark of Grinding Gear Games.
```

---

## Permission justifications (paste into the store's per-permission "why" fields)

**`storage`**
```
Persists the extension's own rate-limiter state (a short list of recent request timestamps and the
current limit windows). This must survive the browser suspending the background service worker so
the extension can never accidentally burst past Path of Exile's per-IP rate limit after waking up.
No personal or browsing data is stored - only these internal counters.
```

**Host permission `https://www.pathofexile.com/api/trade/*`**
```
The extension's sole job is to run official Path of Exile trade searches (search + fetch) for
rare/unique item pricing, from the user's own IP. This permission is scoped to exactly the trade
API path and nothing else on pathofexile.com. Requests are sent logged-out (credentials omitted),
so no account data is accessed.
```

**Content-script matches** (`https://divtally.com/*`, `https://www.divtally.com/*`, `https://divtally.pages.dev/*`)
```
The extension only activates on the DivTally website, where it bridges the page's price
requests to the trade search running on the user's IP. It does not run on any other website.
```

---

## Privacy disclosure (Chrome "Privacy practices" / Edge / AMO data form)

- **Data collected: NONE.** Check "This extension does not collect user data" / equivalent.
- **Data sold or transferred: NO.**
- **Data used only for the single purpose disclosed: YES** (running the user's own trade searches).
- Plain-language statement to paste:
```
This extension collects no personal data and contains no analytics or tracking. It stores only its
own rate-limiter counters locally (chrome.storage.local) so it cannot exceed Path of Exile's
per-IP rate limits. Trade searches are sent from the user's own IP, logged-out (credentials
omitted); no account, session, or browsing data is read or transmitted.

Optional shared community cache (website-side, NOT this extension): if the DivTally
website later offers to contribute your rare/unique price RESULTS to a short-lived shared cache so
other visitors see popular builds priced, only the item price result (item + cheapest listing
price + league) is uploaded - never any personal, account, or identifying data - and it is opt-in.
This extension itself uploads nothing; it only returns results to the page.
```

---

## Category
- Chrome Web Store: **Tools** (alt: "Productivity").
- Edge Add-ons: **Productivity** (alt: "Tools/Utilities").
- Firefox AMO: **Other** or **Games/Entertainment** (AMO has no perfect fit; tags: path-of-exile,
  poe, trade, gaming).

## Screenshots checklist (1280×800 or 640×400; capture WITHOUT any account UI visible)
**RULE (owner, 2026-07-27): screenshots and promo material NEVER show a real player's character
or account name — always the fictional demo build (mock mode). Demo character name must be
OBVIOUSLY fake (e.g. "Example Exile"), not merely plausible.**
1. The DivTally site (stash skin) showing a full priced build with a rare/unique row
   live-priced by the bridge, and the "extension active" state visible.
2. The extension popup tester after a successful price ("● active · v1.2.1", a chaos/divine
   amount, and the "cheapest of N listings" line).
3. The calm in-page upgrade card (does / never-does list) the site shows before install.
4. (Optional) The `/how-it-works` transparency page (endpoints, storage, cache opt-out, rate-limit
   ethics).
5. (Optional) chrome://extensions card showing the narrow permissions ("Read and change your data
   on pathofexile.com" scoped to the trade API + the one site).

## Store icon / promo assets
- Store icon: use `extension/icons/icon128.png` (bronze coin, "1", stash tile). For Chrome's
  larger store tile (128) it is already provided; if a 300×300 or marquee promo is required,
  regenerate at that size via `generate_icons.py` (add the size to `SIZES`) on the same palette.

## Submission sequence note (B-001)
Store review queues take days — submit early in the launch sequence, BEFORE (or in parallel with)
the site go-live, so approval lands when the site is ready. The site URL (`https://divtally.com`)
and the manifest content-script domains are already baked in, and the repo URL
(`https://github.com/divtally/divtally`) is filled — just upload the zips from `public/dist/`.
