# Timeless-jewel community tools - inventory + feasibility (which expose consumable data)

Scout research sanctioned by **D-0019** (Timeless amendment, owner 2026-07-27): *"lean on community
tools for timeless-jewel cost info ... as a LABELED source tier ... a 'community estimate' price
class - always displayed as such (distinct confidence/badge), never blended with live-listing
numbers; exact-seed trade search + link remain the ground truth."* This doc says which tools exist
and which expose data DivTally can actually consume, plus a concrete integration design.

Read alongside `docs/research/timeless-jewels.md` (the seed/conqueror/displayed-value mechanics this
builds on). This doc does **not** re-derive those; it inventories the external tools.

**Provenance tags** (extends the house convention; this whole subject is community/web, so tag hard):
- **[SRC:repo]** - read directly from a tool's own GitHub repository, its source code, or the GitHub
  contents API. Authoritative **about the tool** (its license, file names/sizes, URL-param code) -
  NOT a statement about game balance or market price.
- **[SRC:tft-feed]** - read from the actual raw TFT `poehub-data-prices` JSON on GitHub
  (`raw.githubusercontent.com`), probed 2026-07-27.
- **[INFERRED]** - my reasoning from the above.
- **[NOT FROM SOURCE - <where>]** - community/web claim (SEO calculator page, guide, general lore).
  Cross-check context only; never a DivTally price input (global RULE: flag non-source loudly).

All web sources listed in section 5. No pathofexile.com trade endpoints were touched (project rule).

---

## 0. TL;DR - what's consumable, and the recommendation

Two very different classes of "community tool" exist, and only one of them turned out to expose data
we'd want:

1. **Seed-OUTCOME calculators** ("what does this seed *do*"): the open-source **Vilsol/timeless-jewels**
   tool is the real, authoritative one; every other 2026 "calculator" site is a reskin/clone of it or
   an AI-generated affiliate page. Vilsol is **consumable in the best possible way for us: a stable,
   code-confirmed deep-link URL** (`?jewel=&conqueror=&seed=&location=&mode=seed`) - so a DivTally
   timeless row can carry a **"see what this seed does"** link with zero vendoring, zero rate limit,
   zero legal exposure. [SRC:repo]

2. **VALUATION feeds** ("which seeds are *worth money*"): **there is no public, machine-readable,
   per-seed price feed.** The one candidate - TFT's `poehub-data-prices/lsc/bulk-legion-jewels.json` -
   prices timeless jewels **by NAME only** (`{"name":"Lethal Pride","chaos":15,"lowConfidence":true}`),
   i.e. the same junk-seed floor poe.ninja already gives us, with **no license file** and
   Discord-tied paths that "may change." [SRC:tft-feed] [SRC:repo] Per-seed valuation lives in traders'
   heads and Discord haggling; it is emergent from the trade search DivTally already runs. No feed
   grades seeds.

**Recommendation (fits D-0019 + the constraints exactly):**
- **Add the Vilsol deep-link** to every parseable timeless row as an *inspection* link ("see what
  seed N does"), next to the existing exact-seed trade link. It is the honest, stable way to honour
  the "community tools for cost info" ask: it lets the user *grade the seed themselves*.
- **Do NOT introduce a new community PRICE number.** The sanctioned "community estimate" for a
  timeless row stays exactly what D-0019 §7.3 already defines: the **name-aggregate floor** (we
  already fetch it from poe.ninja), labelled low-confidence. TFT's feed is a redundant second copy of
  that same floor with worse licensing - not worth vendoring.
- **Exact-seed trade search + link remain ground truth** (unchanged).

So the net change to the codebase is small and additive: one deep-link builder, an optional cached
name-floor cross-check, and a UI badge. Everything degrades gracefully to "link only" if a source
dies. Ranked options + the flags are in section 4.

---

## 1. Seed-OUTCOME calculators (what a seed transforms)

### 1.1 The one that matters: `Vilsol/timeless-jewels` [SRC:repo]
- **Repo:** https://github.com/Vilsol/timeless-jewels - "A timeless jewel calculator and skill tree
  for Path of Exile." Hosted (free, no auth) at **https://vilsol.github.io/timeless-jewels** (static
  GitHub Pages). [SRC:repo]
- **License:** **GPL-3.0** (copyleft). [SRC:repo] Deep-linking to the hosted site carries **no**
  license obligation. *Vendoring its data or code to compute outcomes locally would* - see 1.4.
- **Tech stack:** Go calculator compiled to **WebAssembly**, SvelteKit frontend; the whole thing runs
  client-side in the browser (no backend API to call). [SRC:repo]
- **Data source:** "Uses data extracted with https://github.com/Vilsol/go-pob-data" (also GPL-3.0),
  which extracts PoE game data via a CLI (`extract.sh`). [SRC:repo]
- **Determinism / per-league update story:** seed -> outcome is **deterministic and league-invariant**
  unless GGG changes the passive tree or the alternate-passive tables (matches
  `timeless-jewels.md`). The repo README says the tree "might get updated" for a new league "**but it
  is not guaranteed to contain correct data until a game download is available**" - i.e. the
  maintainer re-extracts from the client each league and commits refreshed data files. Manual,
  maintainer-driven, low-frequency. [SRC:repo]

### 1.2 The data files (format / size) [SRC:repo, GitHub contents API]
`data/` holds **gzip-compressed JSON** (`*.json.gz`), ~**1.75 MB total compressed**:

| file | bytes | what |
|---|---|---|
| stats.json.gz | 608,448 | stat definitions |
| SkillTree.json.gz | 461,416 | passive tree |
| stat_descriptions.json.gz | 436,357 | stat text |
| passive_skills.json.gz | 221,383 | passive nodes |
| alternate_passive_skills.json.gz | 6,823 | the timeless transform table |
| stat/passive description + possible_stats + additions | ~11 k combined | supporting tables |
| alternate_tree_versions.json.gz | 197 | jewel version ids |

The seed math is Go (`jewel_test.go`, `reverse_test.go`, `calculator/`), compiled to WASM. So "consume
the data offline" = ship ~1.75 MB of gzipped JSON **plus reimplement (or link) the Go RNG** - a real
project, and GPL-encumbered (1.4). We do **not** need this for the deep-link.

### 1.3 Deep-link contract (CONFIRMED from source - this is the consumable win) [SRC:repo]
Read straight out of `frontend/src/routes/tree/+page.svelte` (it reads and writes these exact
`searchParams`):

| param | type | meaning |
|---|---|---|
| `jewel` | int **1-5** | jewel version id: **1**=Glorious Vanity, **2**=Lethal Pride, **3**=Brutal Restraint, **4**=Militant Faith, **5**=Elegant Hubris (same ids as `local_unique_jewel_alternate_tree_version` in `timeless-jewels.md`) |
| `conqueror` | string | conqueror name, e.g. `Xibaqua`, `Caspiro` |
| `seed` | int | the seed value shown in the seed box (see 1.5 caveat) |
| `location` | int | passive **socket node id** (optional; omit to let the user pick) |
| `mode` | string | `seed` (forward: show what this seed does) or `stats` (reverse: find seeds by stat) |
| `stat`, `disabled` | int (repeatable) | reverse-search stat filters / disabled nodes (not needed by us) |

Base URL: `https://vilsol.github.io/timeless-jewels/tree`. Minimal link needs only
`jewel` + `conqueror` + `seed` + `mode=seed`; `location` is optional.

**Worked examples** (using the two sample jewels in `timeless-jewels.md`):
```
Glorious Vanity, Xibaqua, displayed seed 3496:
  https://vilsol.github.io/timeless-jewels/tree?jewel=1&conqueror=Xibaqua&seed=3496&mode=seed

Elegant Hubris, Caspiro, displayed 29120:  (see the x20 caveat 1.5 before trusting the value)
  https://vilsol.github.io/timeless-jewels/tree?jewel=5&conqueror=Caspiro&seed=29120&mode=seed
```
DivTally already parses `{jewel version, conqueror, displayed seed}` for the trade query
(`timeless-jewels.md` §7.1). The **same three parsed values** build this URL - so the deep-link is
free once the trade branch exists. For the PoB path (no structured version), map jewel **name** -> id
1-5 with a 5-row table.

### 1.4 Licensing reality for reuse [SRC:repo] [INFERRED]
- **Deep-link only (recommended): zero obligation.** A URL is not a derivative work.
- **Vendoring `data/*.json.gz` or the Go/WASM calc to compute outcomes locally: GPL-3.0 applies.**
  The extracted **game-data facts** themselves are arguably not copyrightable, but the repo as
  distributed is GPL; the safe reading is "don't vendor their files into a non-GPL tool." [INFERRED]
  We don't need to - flag it only so nobody reaches for the data dump later without noticing.
- If local seed->outcome is ever wanted, the clean paths are (a) our own game-file extraction
  (`pathofexile-dat`, the owner's poe2-datamine pattern, already parked in D-0019's backlog), or
  (b) accept GPL and fork Vilsol. Both are out of scope for pricing.

### 1.5 CAVEAT - Elegant Hubris seed scale on the deep-link (verify before shipping) [INFERRED]
`timeless-jewels.md` §3 proved EH's **displayed** value = internal seed x20 (Caspiro shows 29120 =
1456x20). The question for the deep-link: does Vilsol's `seed` box want the **displayed** value
(29120) or the **internal** seed (1456)?
- Evidence it wants the **displayed** value: multiple clone sites describe EH's seed range as
  "**2000 to 160000**" [NOT FROM SOURCE - SEO clones] - that's the displayed/coins span (source span
  2040-159840), so the user-facing box operates in displayed units; and `+page.svelte` binds `seed`
  straight to that box. [SRC:repo] [INFERRED] -> **pass the displayed value (29120)** for all five,
  which is exactly what DivTally parses. Convenient.
- Evidence of ambiguity: the library test `jewel_test.go` uses `seed = 2000` for version 5 at the raw
  function level (internal scale). [SRC:repo] That's below the frontend, so it doesn't settle the URL
  question, but it means the /20 conversion happens *somewhere* in the frontend and I did not read the
  exact line that does it.
- **Action:** before shipping the EH deep-link, do a **one-time empirical check** - open the URL for a
  known in-game EH jewel and confirm the rendered tree matches the jewel's actual radius. If it
  doesn't, divide the EH seed by 20 for the URL. The **other four jewels have displayed==internal**,
  so no ambiguity there. Ship those first; gate EH on the check. **[INFERRED - strong, unverified]**

### 1.6 The "successor"/clone field (2026) - all downstream of Vilsol
None of these is an independent data source; treat as **[NOT FROM SOURCE - SEO clone/reskin]**, don't
link them (link the upstream Vilsol instead):
`timeless-jewel-calculator.com`, `timelessjewelcalc.com`, `timelessjewelcalculator.online`,
`poetrades.net/timeless-jewel-calculator`, `poecalc.tools`, `nowcalculate.com`,
`neocalculators.com`, `alienfusiongenerator.com`, `poetimelessjewelcalculator.com`,
`playgohub.com`, `dev.mabts.edu`. They advertise Vilsol-identical features (all-5-jewel support,
tree preview, reverse "find seeds by notable" search); several are ad/affiliate pages, one literally
files posts under an author page named "VILSOL." [NOT FROM SOURCE - web] Unstable, unofficial, no API,
no attribution/terms - avoid.

---

## 2. VALUATION sources (which seeds are worth money) - the decisive finding

### 2.1 TFT / The Forbidden Trove - `poehub-data-prices` [SRC:repo] [SRC:tft-feed]
The only community valuation project that is **machine-readable and public** at all:
- **Repo:** https://github.com/The-Forbidden-Trove/poehub-data-prices - JSON price files sourced from
  the PoE Hub / TFT Discord pricing channels. Folders `lsc/` (league SC), `std/`, `mappings/`.
  Extremely active (tens of thousands of commits = frequent auto-updates). [SRC:repo]
- **Timeless coverage:** `lsc/bulk-legion-jewels.json` (Legion jewels = timeless jewels). **Probed the
  raw file 2026-07-27** [SRC:tft-feed]:
  ```json
  { "timestamp": <unix-ms>, "data": [
      {"name":"Lethal Pride",   "divine":0.05,"chaos":15,"lowConfidence":true,"ratio":1},
      {"name":"Elegant Hubris", "divine":0.04,"chaos":10,"lowConfidence":true,"ratio":1},
      {"name":"Militant Faith", "divine":0.02,"chaos":5, "lowConfidence":true,"ratio":1}
  ]}
  ```
  **It prices by jewel NAME only - no seed, no conqueror, no variant.** These are the bulk/junk-seed
  floor (Lethal Pride 15c, etc.), i.e. **the same thing poe.ninja's name-aggregate already gives us**
  (`timeless-jewels.md` §5), and everything is flagged `lowConfidence`. So TFT adds **no per-seed
  signal** - it cannot tell a god-seed from a vendor-seed. [SRC:tft-feed] [INFERRED]
- **License / terms:** **NO license file in the repo, and the README states no reuse terms or
  attribution rules.** [SRC:repo] Absent a license, the default is all-rights-reserved -
  redistributing/vendoring their JSON has no legal grant. The README only says paths "are subject to
  change if and when there are any channel changes" and to follow the Discord `#tool-dev-updates`
  channel. [SRC:repo] -> **treat as: attribution-required-and-permission-unclear; do not vendor.**
- **Cadence:** frequent (Discord-driven), but path-unstable by their own admission. [SRC:repo]

### 2.2 TFT bulk trade itself (bulk.tftrove.com / Discord) [NOT FROM SOURCE - web]
TFT's actual bulk trading is a Discord-listing tool; timeless jewels are **not a bulk category** there
(they're sold individually by seed, not in stacks), which is exactly why the only timeless entry in
their feed is the name-level bulk floor. Per-seed valuation on TFT = **manual Discord haggling**, not a
feed. [NOT FROM SOURCE - web] [INFERRED]

### 2.3 The honest conclusion on valuation
Per-seed timeless value is **emergent from the live trade market** (build demand x seed-at-socket
quality) and is **not published as any stable machine-readable per-seed feed** anywhere found. The
only machine-readable timeless numbers in existence are **name-aggregate floors** (poe.ninja, TFT),
which DivTally already obtains from ninja. **This is the ground truth DivTally's exact-seed trade
search is already built to discover** (`timeless-jewels.md` §7.2) - there is nothing better to
"lean on." [INFERRED]

---

## 3. Anything else current in 2026 that prices/grades timeless jewels

- **poe.ninja name line** - already integrated (`timeless-jewels.md` §5): one aggregate per jewel
  name, no seed. It's the de-facto "community estimate" floor. Machine-readable, stable, already
  probed. [SRC:ninja - see timeless-jewels.md]
- **vhpg.com/timeless-jewel** - a reference page combining (a) a seed->notable database and (b) a
  "pricing" table that is **just poe.ninja's name-level numbers re-displayed** (it shows
  "Glorious Vanity 30c, +224%, listed count" = ninja's aggregate line, not per-seed). No original
  per-seed valuation. [NOT FROM SOURCE - web] Do not consume.
- **SEO calculator hubs** (section 1.6) - seed-outcome reskins, some with a "pricing" widget that is
  again the ninja name aggregate. No per-seed valuation. [NOT FROM SOURCE - web]
- **Reddit / forum / streamer "god seed" lists** - anecdotal notable/keystone call-outs (e.g. which
  Militant Faith keystone+notable combos sell), never a maintained priced dataset. [NOT FROM SOURCE -
  community]
- **No dedicated "seed grading / seed appraisal API"** was found to exist in 2026. [INFERRED from the
  search sweep]

---

## 4. RECOMMENDATION - integration design under the constraints

Design goal (D-0019): timeless rows may carry a **"community estimate" price class** - a *distinct,
labelled* thing (own badge + confidence), never blended with live-listing numbers; exact-seed trade
search + link stay ground truth; sources cached/vendored where licenses allow; deep-links always;
graceful absence when a source dies.

### 4.1 What to actually build (small, additive)
On top of the timeless branch already specced in `timeless-jewels.md` §7:

1. **Vilsol "inspect seed" deep-link (the headline feature).** From the parsed `{version 1-5,
   conqueror, displayed seed}`, build the §1.3 URL and attach it as e.g.
   `extra["inspect_url"]` / a "See what this seed does" button, beside the exact-seed trade link.
   - Data-driven jewel-name -> id `{Glorious Vanity:1, Lethal Pride:2, Brutal Restraint:3,
     Militant Faith:4, Elegant Hubris:5}` for the PoB path; use the structured version directly on the
     ninja path.
   - **Gate the Elegant Hubris link on the §1.5 empirical check;** ship the other four immediately.
   - No vendoring, no rate limit, no auth, no license issue. If the hosted site 404s, the button just
     doesn't render (graceful absence).
2. **Keep the name-aggregate FLOOR exactly as D-0019 §7.3** - from **poe.ninja** (already probed,
   already has a fetch/cache path). Render it as the **`community-estimate` price class**: a distinct
   badge (e.g. "community floor - any seed"), **confidence hard-capped `low`**, note "cheapest of ALL
   seeds/conquerors of {name}; your exact seed is priced live via the trade link." This IS the
   sanctioned community-estimate class; it just happens to be sourced from ninja, not a new tool.
3. **Do NOT add TFT's number.** It's the same floor with worse licensing and unstable paths (2.1).
   Optionally cache it *only* as an internal cross-check of the ninja floor - never displayed, never
   redistributed - but simplest is to skip it.

### 4.2 The "community estimate" price class - display contract
| element | value |
|---|---|
| badge | `community estimate` (visually distinct from the green live-listing dot) |
| number | the name-aggregate floor (ninja), or none |
| confidence | **`low`** hard cap, always (never inherit the huge listing-count -> "high") |
| links | (a) exact-seed **trade** link = ground truth; (b) Vilsol **inspect** deep-link = "what this seed does" |
| absence | if seed/conqueror unparseable -> **link + no number** (D-0019 tail); if ninja floor missing -> just the two links; if Vilsol down -> hide only that button |

### 4.3 Ranked options (stability x honesty)
1. **Vilsol deep-link (seed-outcome).** TOP. Static, open-source (forkable if it dies, GPL), no rate
   limit/auth, deterministic, code-confirmed URL contract, and it makes **no price claim** so it
   cannot be "wrong." Lets the user grade the seed themselves - the most honest possible "community
   cost info." **Ship it.**
2. **poe.ninja name-floor.** Already integrated, stable, machine-readable - but name-aggregate only.
   Keep as the labelled low-confidence floor. **Already the plan.**
3. **TFT `bulk-legion-jewels.json`.** Redundant with #2 (name-aggregate), **no license**, self-declared
   unstable paths, Discord-tied. **Skip** (or silent internal cross-check at most). **Flag: no license
   = no redistribution right.**
4. **SEO clone calculators / vhpg / "god seed" lists.** Unstable, unofficial, no API, no terms; their
   "prices" are just ninja re-skinned. **Avoid**; link Vilsol upstream instead. **[NOT FROM SOURCE]**

### 4.4 Terms/reuse flags (explicit)
- **Vilsol/timeless-jewels + go-pob-data: GPL-3.0.** Deep-link = fine. **Vendoring their data/code to
  compute locally pulls in GPL** - don't, unless we deliberately go GPL or do our own extraction.
  [SRC:repo]
- **TFT poehub-data-prices: NO license = all-rights-reserved by default.** Do not vendor/redistribute
  their JSON; attribution + permission would be required and aren't granted in-repo. [SRC:repo]
- **poe.ninja:** unchanged from the existing integration (we already use it; polite cached probes).
- **SEO clones:** unknown/ad-driven terms; not used. [NOT FROM SOURCE]

Net: the only thing we *consume programmatically* from a new community tool is a **URL string**
(Vilsol), which is legally and operationally the safest possible integration and exactly honours "lean
on community tools for cost info" without ever fabricating a per-seed price.

---

## 5. Source index (reproduce these)
- Vilsol calculator repo (license GPL-3.0, tech stack, data note):
  https://github.com/Vilsol/timeless-jewels and `/blob/main/README.md`. [SRC:repo]
- Deep-link URL params (jewel/conqueror/seed/location/mode/stat/disabled): read from
  `frontend/src/routes/tree/+page.svelte` via
  `https://raw.githubusercontent.com/Vilsol/timeless-jewels/main/frontend/src/routes/tree/+page.svelte`.
  [SRC:repo]
- Data file names + sizes: GitHub contents API
  `https://api.github.com/repos/Vilsol/timeless-jewels/contents/data`. [SRC:repo]
- EH seed-scale test constant: `jewel_test.go` (version 5 test seed = 2000). [SRC:repo]
- Data-extraction dependency (GPL-3.0): https://github.com/Vilsol/go-pob-data. [SRC:repo]
- TFT feed: repo https://github.com/The-Forbidden-Trove/poehub-data-prices (folders lsc/std/mappings,
  no LICENSE); raw file probed
  `https://raw.githubusercontent.com/The-Forbidden-Trove/poehub-data-prices/master/lsc/bulk-legion-jewels.json`
  (name-aggregate only). [SRC:repo] [SRC:tft-feed]
- Clones / "pricing" pages (all [NOT FROM SOURCE], reskins of Vilsol / ninja): timeless-jewel-
  calculator.com, timelessjewelcalc.com, timelessjewelcalculator.online, poetrades.net,
  poecalc.tools, nowcalculate.com, neocalculators.com, alienfusiongenerator.com,
  poetimelessjewelcalculator.com, vhpg.com/timeless-jewel.
- Cross-reference: `docs/research/timeless-jewels.md` (seed/conqueror/displayed-value mechanics,
  poe.ninja name-aggregate finding), `docs/00-decision-log.md` D-0019 (the sanction).
