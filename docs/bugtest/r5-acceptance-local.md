# R5 — LOCAL-APP acceptance & regression (fresh eyes vs README)

**Round:** D-0020 Round 5 (regression + acceptance, LOOP-UNTIL-DRY).
**Lens:** judge the LOCAL app against its own written contract (`README.md`, RULE 8); prove the
four prior rounds' churn (this week's `core.js`/engine work) did not break the shipped UI.
**Date:** 2026-07-28. **Agent:** local-acceptance (fresh eyes).
**Scope touched:** read-only across the repo; ONE paced CLI build run (SergoheroGaz) = my sole
trade traffic; local web server booted on `127.0.0.1:8791` for `?mock` loads (no trade traffic in
mock). Only file written: this doc.

## Verdict

**PASS with 3 minor README-drift findings + 1 informational note.** Every functional promise the
README makes holds: all six CLI flags exist and work, a real end-to-end CLI run prices a build
correctly (tiered, chaos+divine, guardrails intact), the web UI boots and `/` lands on the stash
skin (D-0007), the gallery lists all ten skins, and **all 10 skins render `?mock` with zero console
errors / page errors / failed requests after this week's core.js+engine churn** — the regression is
clean. The findings are documentation drift (button label, expander label, a cache-duration claim)
and one expectation-vs-reality note about `/classic?mock`. No blocker/major; nothing functional is
wrong.

---

## A. CLI acceptance

### A1. Flags exist and match the README — PASS
`python -m bpc --help`:
```
usage: bpc [-h] [--league LEAGUE]
           [--status {online,any,onlineleague,available,securable}] [--json]
           [--fresh] [-q] [--version] [url]
```
Every documented option is present and its help text matches the README Options block
(`--league`, `--status` with the exact five choices, `--json`, `--fresh`/`--refresh`, `-q/--quiet`,
`--version`). `--version` → `bpc 0.1.0`. The `url` positional advertises all three documented input
formats ("poe.ninja character link, Path of Building code, or pobb.in link"). The `--status` mapping
in the README (online = In Person (Online), etc.) matches `STATUS_LABEL` in core.js. **No drift.**

### A2. One real CLI run — SergoheroGaz (smallest owner build) — PASS
`python -m bpc "…/Sergohero-2699/SergoheroGaz?i=19"` → exit 0, ~24 items, paced (no rate-limit
violation, no ban). Output is exactly what the README promises:
- Header: `SergoheroGaz - Deadeye (level 100) | League: Allflame | 1 divine = 118 chaos`.
- Three tiers per item (min / median / high) with a **conf** badge column.
- Every price shown in **chaos and divine** (e.g. Nimis `289 div (34,097 chaos)`).
- Uniques priced from real distributions (Headhunter 114 div, Nimis 289 div — the frameType-9
  **foil/relic unique routes to unique pricing**, confirming the D-0020 R1 fix still holds).
- Unpriceable rows get a note + trade link and **no number** (Inpulsa's, Dying Sun, several cluster
  jewels → "no listing matches…see trade_url") — the "link, never a misleading number" guardrail
  holds for every row class.
- Gems priced from poe.ninja ("active + N supports"); variant timeless jewel (Lethal Pride) flagged
  "variable unique — price spans different versions".
- Totals in chaos+divine, unpriced items excluded with a count note (`9 item(s) could not be
  priced … totals exclude them`).

### A3. `recover.py` (README-named CLI equivalent) — PASS
`python recover.py --help` → exit 0; accepts `url` + `--account/--character/--league/--links-only`,
matching the README's "reloads a cached build snapshot from the command line."

---

## B. Web UI acceptance (booted `python -m bpc.web --no-browser --port 8791`)

| Claim (README) | Result |
|---|---|
| `.\bpc-web.cmd` opens `http://127.0.0.1:8765` | web `main()` default port = **8765** ✓; `--port/--host/--no-browser` all parsed (README's pass-through options) ✓ |
| `/` lands on the **Stash Tab** skin (D-0007) | `/` → 200, `<title>bpc · stash tab</title>`, quad-stash markup; `do_GET` serves `stash.html` with a `# D-0007` comment ✓ |
| Alternate looks at `/gallery` | `/gallery` → 200, lists **all 10** version links (`/v/{stash,ledger,abacus,manifest,facts,waterfall,binder,foundry,console,atelier}`) ✓ |
| Classic UI at `/classic` (unchanged) | `/classic` → 200, standalone parent form ✓ |
| `/v/<id>` per-skin routing | each skin → 200; `/v/bogus` → **404** (correct rejection) ✓ |
| Shared engine at `/assets/core.js` | `/assets/core.js` → 200 ✓ |

---

## C. `?mock` regression — 10 skins + classic (real headless-chromium load)

Loaded every `?mock` URL in headless chromium, hooking `console.error`, `pageerror`,
`requestfailed`, and any response ≥400. Rig: `scratchpad/r5_mockdriver.mjs`.

| URL | items | median | count | console.err | pageerror | reqfail | render |
|---|---|---|---|---|---|---|---|
| `/v/stash?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/ledger?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/abacus?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/manifest?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/facts?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/waterfall?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/binder?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/foundry?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/console?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/v/atelier?mock` | 26 | 14060.2 | 24 | 0 | 0 | 0 | ✓ |
| `/classic?mock` | — | — | — | 0 | 0 | 0 | **form only (F4)** |
| `/` (no mock) | 0 | 0 | 0 | 0 | 0 | 0 | shell ✓ |
| `/gallery` (no mock) | — | — | — | 0 | 0 | 0 | list ✓ |

**All 10 gallery skins load the demo build identically and cleanly** — same engine totals
(items 26, median 14060.2c, 24 included), zero JS errors, zero failed asset requests. The
core.js/engine churn from R1–R4 did **not** regress any skin. `?mock` on "any version URL" (README
line 61) is satisfied for every `/v/` skin.

---

## D. Other README claims spot-checked

- **Project layout** (README §Project layout): all 13 listed `bpc/*.py` files present
  (cli, web, engine, poeninja, trade, statmap, pricing, pob, currency, util, report, models, cache)
  + `research/` + `cache/`. **No drift.**
- **Promised UI controls** present in the stash skin / core.js: Autoscan, "skip all (don't price)",
  Skip, **edit affixes**, combine-resistances/pseudo toggle, **Search all again**, PoB **Copy**
  button (`#pobBtn`), Recent list, tier buttons (min/median/high), advanced + fresh-pull checkboxes.
- **Controls persist & re-run** (README lines 78–86): core.js persists `bpc_status/bpc_league/
  bpc_advanced/bpc_tier` and `setControl` calls `rerun()` for every control except display-only
  `tier`. ✓
- **Local default listing status** = `online` = "In Person (Online)" (core.js line 60, stored under
  `bpc_status`) — **matches** README line 76's `(default)`. (D-0017's re-default to `available` was
  applied to the *public* core.js only, not this local one — no drift here.)
- **Rate-limit / cache promise** (README §Rate limiting): reads `X-Rate-Limit-Ip`, honours
  `Retry-After` (clamped ≤1800s), caches reference data 86400s (a day ✓) and trade prices 1800s
  (~30 min ✓). **One sub-claim drifted → F3.**

---

## Findings

### F1 — [minor] Default UI button is "Appraise", but the README says "click **Estimate**"
- **README** line 33 (Web UI walkthrough): "Paste the character link, click **Estimate**, watch
  live progress…".
- **Reality:** the default landing page is the stash skin (D-0007), whose submit button is
  labeled **"Appraise"** (`bpc/ui/stash.html:801` — `<button … id="go" …>Appraise</button>`).
  "Estimate" exists only in the `/classic` UI. A fresh user following the README on the default page
  looks for "Estimate" and won't find it.
- **Fix hint:** update README line 33 to "click **Appraise**" (or "**Appraise** — "Estimate" in the
  classic UI"). Cosmetic; no functional impact.

### F2 — [minor] Recent-builds expander is "+N more"/"show fewer", not "**See more**"
- **README** lines 85–86: "the page lists your 5 most recently searched builds; **See more** expands
  to every cached snapshot."
- **Reality:** the stash skin caps the list at 5 (`stash.html:887` `ordered.slice(0,5)`) and shows
  an expander, but its label is **"+N more"** (e.g. "+3 more") and, when expanded, "show fewer"
  (`stash.html:895`). The behavior matches the promise exactly; only the literal label "See more"
  is wrong.
- **Fix hint:** either rename the button to "See more" or soften the README wording to "an
  expander (+N more)". Cosmetic.

### F3 — [minor] README claims "league/rates cached **for hours**"; actual TTLs are 10–30 min
- **README** line 208: "caches results (reference data for a day, prices for ~30 min, **league/rates
  for hours**)".
- **Reality:** league lists cache **600s / 10 min** (`trade.py` `trade:data:leagues`,
  `poeninja.py` `index-state`); currency **rates** cache **1800s / 30 min** (`currency.py:33`,
  `poeninja.py:221`). Neither is "hours" — both are well under an hour. (The "a day" and "~30 min"
  sub-claims are accurate.)
- **Impact:** none functional (shorter TTLs are strictly safe — they just refetch a bit more often);
  purely an inaccurate documentation figure.
- **Fix hint:** change "league/rates for hours" → "league/rates for ~10–30 min", or lengthen the
  TTLs if "hours" is the intended behavior (owner call — RULE 5).

### F4 — [info] `/classic?mock` renders the input form, not a demo build
- The task asked to confirm "10 skins **+ classic** render `?mock`". The 10 gallery skins do; the
  **classic** page does **not** load a mock build — it's the standalone parent UI with its own
  inline JS and **no** `core.js`/`sample.js`/`?mock` wiring (verified: `web.py` PAGE has zero
  `mock`/`bpc`/`core.js` references). `/classic?mock` simply shows the normal empty "Paste a
  poe.ninja link… Appraise" form. **No exception is thrown** (0 console errors / pageerrors).
- **Not a strict README violation:** README scopes `?mock` to "any *version* URL" (the `/v/` skins),
  and classic is documented separately as "unchanged." Also **not a regression** — classic never
  used core.js, so this week's churn is irrelevant to it. Flagged only because the round brief named
  classic explicitly and a reader could expect parity. If mock-preview parity for classic is
  desired, it's a small feature, not a bug (→ backlog, owner call).

---

## Non-findings verified good (regression evidence)

- All 6 CLI flags + `--version` + 3-format `url` positional match the README exactly.
- Real CLI run: tiered min/median/high, chaos+divine, confidence badges, unpriceable→link guardrail,
  gems via poe.ninja, foil-unique (Nimis) priced, variant timeless-jewel flagged. No ban.
- Web boots; `/`→stash (D-0007), `/gallery` lists 10, `/classic` serves, `/v/<id>` works,
  `/v/bogus`→404, `/assets/core.js`→200.
- **All 10 skins render `?mock` with 0 console errors / 0 pageerrors / 0 failed requests** — clean
  after the R1–R4 core.js+engine churn.
- Project-layout file list accurate; promised UI controls present; controls persist + auto-rerun;
  X-Rate-Limit + Retry-After honoured; reference/price cache TTLs accurate.

## Rig artifacts (scratchpad, throwaway)
- `r5_mockdriver.mjs` — headless-chromium `?mock` loader (13 pages).
- `r5_cli_sergo.out` / `.err` — the SergoheroGaz CLI run.
- `r5_web.log` — local server log (port 8791).
