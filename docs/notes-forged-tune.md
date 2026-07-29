# Forged-Metal tuning pass (D-0025 follow-up)

Three owner-approved tuning changes on top of the "Forged Metal" restyle. **Layout, markup,
ids, classes, and all `<script>` behaviour were preserved** — this is CSS + a small
price-render tweak, not a redesign. All edits are in
`public/site/index.html` (the whole stylesheet + inline `<script>` live there).
`assets/core.js` was **not** touched (the slot/cell price DOM is rendered entirely in
`index.html`, so the engine needed no change).

## 1. All text ~1.35× larger, without overflow
- **Bulk scale:** every `font-size:<n>px` in the file was multiplied by 1.35 and rounded
  (`int(n*1.35+0.5)`) — **183** values, applied by a one-shot transform
  (`scratchpad/forged_tune.py`; original backed up to `scratchpad/index.html.bak`).
  The grand-total `clamp(30px,4.2vw,38px)` (not a plain `Npx`) was set by hand to
  `clamp(40px,4.2vw,50px)`.
- **Currency icons scaled too** so the chaos/divine images keep pace with the bigger
  numbers beside them: every `.bpc-cur{ height / vertical-align }` was scaled 1.35× (11 rules).
- **Containers grown so nothing clips or overflows:** doll `grid-auto-rows` min 98→120,
  slot `min-height` 98→118 + `padding-top` 20→26, `.ico-wrap` min-height 46→58, stash
  `#stash .slot` min-height 110→132, `.grid12` gap 8→10, include/buy marks 27→30px,
  tooltip `#tt` 400→500px, picker `.pick` 640→760px, responsive doll slot 64→78.
- **No horizontal body scroll at 1280px** (verified: `documentElement.scrollWidth == 1280`).

### The one deliberate exception: doll/stash item-name band
The paper-doll is a fixed **5-column** grid (stash is 6-col); a name cell is only ~76–98px
wide. Measured word widths showed a full 1.35× (→18px) makes ordinary words overflow the
cell — "Empyrean" (83px), "Headhunter", "Gauntlets" — which forces `overflow-wrap` into a
mid-word cut (the exact bug in change 2). Even "Cinderswallow" (88px @13px) never fit the
original 76px cell. So, using the owner's sanctioned "widen cells or reflow gracefully —
your judgment":
- **Board split equalised** `1.05fr/1.25fr → 1fr/1fr`, doll padding 16→14, gap 10→8, name
  `padding` → `6px 6px 8px`. This widens each name cell to ~98px.
- **Slot names take a restrained bump to 14px** (weapon/body/off-hand 15px) instead of the
  full 18px. At 14px in the widened cell, the longest single word in the sample
  ("Cinderswallow", 94px) still fits on one line. Everything else on the page is the full
  1.35×; only this width-bound label is smaller by necessity.
- Verified: **0 of 21 board slots have a word wider than its cell** (so no forced mid-word
  break anywhere).

## 2. Whole-word wrapping (no mid-word breaks)
- `.slot .iname` changed `word-break:break-word; overflow-wrap:anywhere;` →
  `word-break:normal; overflow-wrap:break-word; hyphens:none;`. Names now break **only at
  spaces**; a word stays intact and wraps whole. `overflow-wrap:break-word` remains as a
  last-resort safety for any future word too long for even the widened cell (degrades
  gracefully rather than the aggressive `anywhere` cut).
- This one rule covers **both** the doll slots and the stash cells (they share `.slot .iname`).
  `.mrow .mr-name` was already `overflow-wrap:break-word` (rares panel) — left as-is.

## 3. Result-count state moved from the border to the cost
Previously a searched item showed a **red/orange slot border** for 0 / <5 listings. Now the
state lives in the **price text** (top-right of each slot/cell/row); the slot border stays
the rarity colour so the two cues never compete.
- **Removed** `.slot.notfound` / `.slot.fewresults` border rules + their `:hover` glows.
- **Added** `.slot.notfound .pricetag{color:#d6463a; font-size:11px}` and
  `.slot.fewresults .pricetag{color:#e08a2b}`.
- **`updateSlot()`** (index.html): a searched-but-unmatched slot now renders red **"not
  found"** text as its cost (no number, no currency) —
  `tag.innerHTML = el.classList.contains('notfound') ? 'not found' : ''`. The `.notfound`
  class is still set exactly as before (searched && !priced), so the trigger is unchanged;
  only its presentation moved from border → text.
- **`<5` listings:** the price **number** renders orange (currency image unaffected, so the
  symbol stays). Driven by the existing `.fewresults` class + the new pricetag colour rule.
- **Manual "Rares to price" rows** got the same `<5` treatment: `.mr-price` gets a
  `fewresults` class when `source != 'manual' && total_found < 5` (a pasted price never
  colours), plus `.mrow .mr-price.fewresults{color:#e08a2b}`.
- **Legend** in the Equipment header changed from border-swatches to cost-colour samples:
  red **"not found" = no listings** and orange **"12" = <5 listings** (`.lg-cost` replaces
  `.lg-sw`).

## Verification (all green)
- `node --check assets/core.js` → OK (unchanged).
- `node test_scanstatus.mjs` → 131 passed / 0 failed (includes a compile-check of the
  index.html inline `<script>`).
- `node test_picker.mjs` → 107 passed / 0 failed (parse-checks core.js + inline script).
- Headless (Playwright, 1280px, `/?mock`): no horizontal scroll; text visibly larger;
  Cinderswallow Urn wraps "Cinderswallow / Urn" (whole words); 0 slots with an
  over-wide word; red "not found" cost (rgb 214,70,58) on the 0-match jewel; orange "8.0"
  (rgb 224,138,43) on the <5 ring; tooltip + picker render cleanly at the new sizes;
  0 console/page errors.

## Note for a future full-1.35× on names
If the owner wants the doll names bigger than 14/15px, the only lever left is fewer/wider
columns or a JS auto-fit — pure CSS can't enlarge the name past the cell width without
either a mid-word break or a clip. Flagged rather than silently forced.
