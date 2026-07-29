# Notes — Forged Metal HYBRID restyle (site)

Owner request (2026-07-28): take the **current site's exact layout + functionality** and restyle it
with the **"Forged Metal"** component treatment from the `tex-forged.html` mockup. Owner likes the
mockup's **buttons**, its **bigger/more-legible fonts**, and its **textured plates** — but wants to
**keep the current layout** (paper-doll Equipment grid with real item images, Stash with jewel image
cells + gem rows + flask images, the banner). So: apply Forged Metal's *component* aesthetic to the
real classes **without changing layout, markup, ids, classes, or any JavaScript**.

## Scope of change
- **One file touched:** `public/site/index.html` — a single CSS block **appended at the very end of
  the `<style>`** (just before `</style></head>`). Nothing else in the file changed: no markup, no
  ids, no classes, no `<script>`, no `_headers`.
- **Append-only / override strategy (RULE 6 "delete what you supersede" doesn't apply — nothing is
  replaced):** every rule is additive and wins by **source order** at matched (or higher)
  specificity, so no existing rule the app relies on was deleted. State variants the JS drives
  (`.slot.nolist / .empty / .off / .loading`, `.hbtn.on`, `.bt-seg button.active`,
  `.stone-btn.autoscan[.scanning]`, `.pob-btn.copied`) all still win where they should.

## The load-bearing constraint: CSP forbids `data:` textures
The mockup builds its metal grain from an inline **`feTurbulence` SVG noise as a `data:` URI**
background. The production CSP (`public/site/_headers`) is:

```
img-src 'self' https://web.poecdn.com     (NO data:)
```

A CSS `background-image: url(data:...)` is governed by **`img-src`**, so that noise data-URI would be
**blocked in production** (console CSP violation + no texture), and the `_headers` comment explicitly
guarantees *"the site uses zero data: images — verified."* I can only edit `index.html`, not
`_headers`, so:

> **Every texture here is PURE CSS** — layered `linear-gradient` / `repeating-linear-gradient`
> (brushed metal) + `box-shadow` bevels/emboss + `radial-gradient` rivets. **No `data:` URIs.** The
> "zero data: images" CSP invariant is preserved, and the page fires zero texture requests.

(Note: `python -m http.server` does **not** serve the `_headers` CSP, so a data-URI would have passed
a local test yet failed on Cloudflare Pages — exactly the trap avoided.)

## Forged vocabulary, implemented in pure CSS
Reusable tokens added in a second `:root` (new names, no collisions):
`--fm-metal`, `--fm-head`, `--fm-tab`, `--fm-tab-on` (lit brass), `--fm-brushed` (brushed-metal
repeating-linear-gradient). The treatment = **brushed gradient + inset emboss + a hairline gold
top-bevel + outer drop shadow**, with buttons that **translateY on `:active`** (press-in) and a
**lit-brass gradient for the "on"/active state** with engraved dark text.

## Component classes restyled (all named in the brief)
| Component | Class(es) | Treatment |
|---|---|---|
| Panel plates | `.frame>.inner`, `.frame::before/::after` | brushed metal + hairline gold top-bevel + inset emboss; brighter lit corner **rivets** (existing 2 studs kept + brightened — no new pseudo-elements added, to avoid overlapping banner content) |
| Section headers | `.panel-head`, `.stash-section h4` | forged head-plate gradient + engraved `text-shadow`; font bumped 12→13 / 11→12 |
| Header toggles | `.hbtn` (weapon swap, magic flasks, flasks, jewels, gems) | raised metal tab; `:hover` lift; `:active` press-in; **`.on` = lit brass** with engraved text; font 13→14, roomier 32px target |
| Group toggles | `.panel-head .grp-toggle`, `.stash-section h4 .grp-toggle` ("toggle all") | matching mini metal tab |
| Action buttons | `.stone-btn` (+ variants: `.pob-btn`, `.re-all`, picker `.pbtns`/`.pbulk`, `.viewtrade`, `.addgrp`) | raised metal key; `:active` press-in; `:focus-visible` gold ring; 15px/600, 40px target |
| Primary buttons | `.stone-btn.go` (Appraise), `.pbtns .stone-btn.search` | keep their gold, gain lit-brass emboss + engraved text |
| Autoscan | `.stone-btn.autoscan` | **left untouched** — its own gold + pulsing glow (higher-specificity + running `@keyframes`) survive intact; it just inherits the press-in affordance |
| Selects | `.stone-sel` | quiet matching plate (boldness stays on buttons) |
| Segmented control | `.bantot .bt-seg` + buttons | inset metal **track** + raised keys with gaps; active = lit brass; font 11→12 |
| Grand total | `.bantot .bt-val` (+ `.bpc-cur`, `.bpc-exsub`, `.bt-head`) | **`clamp(30px,4.2vw,38px)`**, weight 700, tabular-nums, warm gold glow — the "prominent number" |
| Item cells | `.slot` (doll + stash) | subtle brushed overlay over the existing gradient (no blend, no data-URI → state variants untouched); item names +1px (`.iname` 12→13, weap/off/body 13→14), pricetag 11→12 |
| Banner name | `.char-name` | 26→28px |

## Legibility bumps (owner: "font is bigger")
Grand total (biggest lever), section headers, toggle/button labels, item names, and pricetags each
went up a notch. Boldness deliberately concentrated on **buttons + total + plate texture**; slots,
tooltips, and body copy stay quiet.

## Accessibility / responsiveness
- **`:focus-visible`** gold ring added for `.hbtn`, `.stone-btn`, `.stone-sel`, `.grp-toggle`, and the
  `.bt-seg` buttons.
- **`prefers-reduced-motion: reduce`** block appended: drops the button transitions and the
  press-travel transform (the existing reduced-motion blocks for slots/orb/tooltip/autoscan are
  untouched).
- No fixed widths introduced; grand total uses a `vw` clamp; buttons keep flex-wrap. No horizontal
  scroll at 1320px; the existing 720px stacking breakpoint is unchanged.

## Verification (all green)
- `node test_scanstatus.mjs` → **131 passed, 0 failed** (was 131/0 pre-change).
- `node test_picker.mjs` → **107 passed, 0 failed** (was 107/0).
- `node test_security.mjs` (bonus) → **27 passed, 0 failed**.
  (All three parse the inline `<script>` + run `assets/core.js`; CSS-only change leaves them green.)
- CSS brace balance in the `<style>` block: **614 `{` / 614 `}`**.
- `data:` substring appears **4×**, all inside the new explanatory CSS comments — **zero real
  data-URIs** → CSP invariant intact.
- **Headless Chrome render of `/?mock`** (served via `python -m http.server 8137`, then killed):
  board visible, **41 `.slot`s**, `bantot` shown with total, MIN/MEDIAN/HIGH control, 5 `.hbtn`,
  48 `.stone-btn`, Rares-to-price panel with 20 rows, 122 `web.poecdn.com` item-image refs; **no
  Uncaught / CSP-refused / Type/ReferenceError** in the console log. Screenshot confirmed the forged
  look with the current layout fully preserved. (poecdn is the static image CDN — **not** a
  pathofexile.com trade call.)

## Layout-preservation note
No structural risk found: the change is purely presentational (backgrounds, shadows, minor font-size
bumps, `:active`/`:focus-visible`). The `.frame` bottom-corner rivets from the mockup were
intentionally **not** added (they'd have needed `.inner` pseudo-elements that could overlap banner
content) — the existing two top studs were brightened instead, keeping the riveted read without any
overlap risk.
