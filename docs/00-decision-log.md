# Decision log - PoE1 Build Price Checker

Dated, numbered decisions. Statuses: **Locked** / Proposed / Superseded. Newest at the bottom.
RULE 1: fundamental decisions land here BEFORE code continues.

---

## D-0001 - Project born as a clone of buildpricechecker, scoped to PoE1 (Locked, 2026-07-26)
Owner request: clone `C:\scripts\buildpricechecker` (the PoE2 build price checker) into a sibling
project that does the same job for **Path of Exile 1**. The Cardescent operating rules
(`C:\scripts\phone-game\CLAUDE.md`) are established here first, adapted (see `CLAUDE.md`):
hub-portal machinery replaced with chat + `docs/open-questions.md`; vertical-slice freeze replaced
with a general converge-then-validate rule; containment scope = this repo (+ read-only parent).
Owner tests personally once the clone works end-to-end.

## D-0002 - Port strategy: same architecture, PoE1 endpoints, chaos-normalised (Locked, 2026-07-26)
- Keep the parent's architecture and module layout verbatim (`bpc/` package, engine shared by
  CLI + web, UI-skin gallery on `core.js`, TTL disk cache). Package name stays `bpc`; the folder
  distinguishes the projects.
- **APIs:** poe.ninja PoE1 builds API (`poe.ninja/builds`, `/api/...` - NOT `/poe2/api/...`) for
  character data; official `pathofexile.com/api/trade` (NOT `trade2`) for pricing; poe.ninja
  economy overviews for gems/currency rates. Exact endpoint shapes are established by LIVE probes
  recorded in `docs/research/` - never assumed from memory (PoE1 differs from PoE2 in query
  schema, listing statuses, pseudo stats, and item taxonomy).
- **Currency:** normalise to **Chaos Orbs** (PoE1's trade index standard), display **Divine Orbs**
  alongside (parent normalised to Exalted + showed Divine).
- **Taxonomy deltas to handle (not exhaustive):** PoE1 has socket **links** (a 5/6-link is a major
  price component - searches must carry link filters), skill gems are socketed items priced by
  level/quality/corrupt (poe.ninja gem economy), no runes/soul cores (drop the rune section or
  repurpose for abyss/cluster jewels per research), flask suffixes/enchants, and different pseudo
  stat ids. Research phase decides each concretely; each becomes its own decision entry if it
  changes the report's section layout.
- **Engine->UI JSON contract stays structurally identical** to the parent's so all 10 UI skins port
  with string/branding changes; field names containing "exalted" are renamed to chaos equivalents
  in one coordinated pass (core port owns the rename; UI port follows the map in
  `docs/research/contract.md`).
- **Rate limits:** parent's limiter logic is kept; PoE1 windows are re-verified live. Only one
  agent at a time touches trade search/fetch/exchange (CLAUDE.md RULE 4).
- **Correction (2026-07-26, live-verified):** the poe.ninja PoE1 API base is
  `https://poe.ninja/poe1/api/...`, not `/api/...` as written above. See D-0003.

## D-0003 - Core-port decisions (Locked, 2026-07-26)
Recorded from `docs/port-notes-core.md` (core-port agent); all live-verified except where noted.
- **Currency: Chaos base, rates from poe.ninja economy** - `line.primaryValue` IS the chaos
  price (no rate multiply); `divine_rate()` = the Divine line's primaryValue (~103c/div at port
  time). Trade `exchange` is only a fallback -> the parent's per-run ban-risk exchange call is
  gone from the normal path.
- **Gems priced as real cut items** (name + nearest level/quality bucket + corruption preference)
  via the poe.ninja SkillGem overview; the active gem AND every support gem count (Awakened/
  Empower/Enlighten are often the biggest cost). PoE2 uncut-gem/Jeweller-ladder/lineage model
  DELETED. Method string stays `"skill"` for web compatibility.
- **Sockets/LINKS are a price component:** `Item` gained `sockets`/`max_link`/`total_sockets`/
  `socket_colours`; any `max_link >= 5` item adds `socket_filters.links.min` to unique AND rare
  searches (live-confirmed the API accepts it). Colour/attr sub-filters deliberately unused
  ([INFERRED]-only in research).
- **Defence totals via `armour_filters`** (PoE1 has no `equipment_filters`; field names ar/ev/es/
  ward unchanged).
- **Trade-listing mods are OBJECTS** (`{description, hash, mods}`) in PoE1 fetch responses -
  pricing reads `description`; statmap is unaffected (it maps build-side strings).
- **Rune/charm/desecrated concepts deleted** (RULE 6 clean cutover): no CAT_RUNE, no rune
  section, no frame-5 socketedItems extraction ("Flasks & Charms" -> "Flasks"). Gems appear in
  both `socketedItems` and `skills[]`; priced from `skills[]` only (no double-count).
- **poe.ninja economy = TWO endpoints** (`/poe1/api/economy/exchange/current/overview` for
  currency, `/poe1/api/economy/stash/current/item/overview` for SkillGem etc.); the old flat
  currencyoverview/itemoverview 404 in 2026.
- **poe.ninja builds pipeline:** `/poe1/api/data/index-state` (pick snapshotVersions type
  `"exp"`; `overview` param MUST be snapshotName, which differs from the url slug for 96/106
  snapshots) + `/poe1/api/builds/{version}/character`; account `#1234` discriminators MUST be
  dash-encoded (`-1234`) or the API 404s; non-ASCII names occur and are handled.
- **Engine->UI JSON contract structurally unchanged**; renames limited to currency
  (`*_exalted` -> `*_chaos`) + rune-section removal + gem `extra` reshape; exact map in
  `docs/research/contract.md`.
- `Pricer` now takes `economy=` via constructor injection (parent's post-hoc assignment gone).

## D-0004 - Port verified end-to-end (Locked, 2026-07-26)
Workflow `wf_18690cd3-380` (12 agents, ~2.3M tokens): research -> port -> 4-way verify. All four
verify agents PASSED with zero blocker/major findings: (1) `tests.py` green and proven offline
(socket monkeypatch); (2) LIVE CLI run on a real Allflame character (Belirs-4934/
RaiderFixEuServers, Pathfinder L100, 6-link Dendrobate + 5-link Darkscorn) - sane chaos numbers,
links filters applied, no rate-limit violations; earlier core smoke: Headhunter ~17,612c
(~170 div) on example-0416; (3) web smoke: all 10 skins + gallery + classic render PoE1-branded
in mock mode; (4) adversarial review refuted every plausible-port-bug hypothesis it hunted.
Minor findings (test-coverage gaps, PoB links parity, SSF economy league, overflow rows missing
trade_url, dead rune CSS) -> fix round logged as D-0005 when it lands.

## D-0005 - Minors fix round (Locked, 2026-07-26)
All verify-phase minor findings fixed, suite green (details: `docs/port-notes-fix-minors.md`):
- **PoB input parity for links:** `pob.py` now parses the `Sockets:` line into the same
  `sockets/max_link/...` Item fields the poe.ninja path sets, so PoB-sourced 5/6-links get the
  links filter (they underpriced before). Test asserts filter parity between both input paths.
- **SSF builds price via their tradeable parent league** for gem/currency economy (engine now
  passes the resolved trade league to `PoeNinjaEconomy`, not raw `meta.league`).
- **Budget-skipped rows carry a trade_url** (built without executing the search) - the
  "unpriceable = link, no number" guardrail now holds for every row class.
- **Dead PoE2 CSS/JS residue removed** across the six flagged skins, plus the leftover
  `currency`-category bits in stash/binder/abacus (engine never emits that category).
  `manifest.html`'s decorative "EXALT AIR" kept (theme flavour; Exalted is a real PoE1 currency).
- **Six promise tests added** (RULE 8): status mapping + fallback, rare all-affix default query,
  armour_filters totals, no-match guardrail, `to_chaos` non-chaos currencies, version-unique
  auto-detection (offline, stubbed listings). `python tests.py` green and offline.

## D-0006 - Owner feedback round 1: flasks, gem grouping, autoscan (Locked, 2026-07-26)
Owner tested the stash skin and requested (his words = the spec):
- **Flask belt = 5 generic slots.** PoE1 builds run ~5 (usually utility) flasks. The PoE2-derived
  "life | 3 utility | mana" name-classified doll layout is superseded: every skin displays the
  build's flasks as a 5-slot belt filled in flask order (overflow beyond 5 still shown, never
  dropped). No life/mana slot guessing.
- **Gems grouped by HOST ITEM, supports connected to their active.** Use `skills[].itemSlot` /
  host `inventoryId` to group each skill under the item it is socketed into; support gems render
  nested under their active gem with per-gem prices, and support costs stay included in totals.
  Engine exposes host-item info + per-gem breakdown additively in `PriceResult.extra`
  (contract.md updated additively - no breaking renames).
- **GRANTED tag audit:** owner screenshot shows every gem row tagged GRANTED, which is almost
  certainly wrong (Heralds are socketed, not item-granted). Root-cause end-to-end; only genuinely
  item-provided gems (`itemProvidedGems` / built-in supports) get the tag, and granted gems are
  excluded from trade-price totals while their socketed supports still count.
- **Autoscan button.** At the TOP of the rare affix selector: a glowing (skin-accent) button
  labeled "Autoscan" that prices all remaining rares automatically with default all-affix
  searches (the former "Search all N (default)"). A small non-glowing "skip all (don't price)"
  remains below. **INTERPRETATION NOTE:** owner said "make the skip all button... read
  'autoscan'"; read as "skip the manual affix flow" = auto-price, since a skip-everything button
  named Autoscan would price nothing. Flagged to owner for correction if wrong.

**SHIPPED 2026-07-26** (workflow wf_75fc1924-289, 18 agents, 1 fix round): engine emits host-item
info + per-gem breakdown additively; GRANTED root cause found and fixed - web.py's PoE2-era
skeleton heuristic (`not inventoryId.startswith("SkillSlot")`) flagged EVERY gem because PoE1 gem
inventoryId is always None; now reads the engine's `granted` computed from `itemProvidedGems` /
`isBuiltInSupport` (fixture: exactly Herald of the Hive via Lost Unity flags granted, excluded
from totals, its supports still counted). All 10 skins + classic: 5-slot belt in flask order,
host-grouped gems with nested priced supports, glowing Autoscan wired to search-all-default in
every picker copy. Verify caught + fix round resolved: the unshipped web.py line (blocker) and
binder.html calling non-exported `bpc.itemGranted` (major). Both re-verified green; tests green.

## D-0007 - Stash Tab is THE interface (Locked, 2026-07-26)
Owner: "i only like the style ive been using" (the stash skin from his screenshots) - build
around it. Effects: local web UI lands directly on the stash skin at `/` (picker gallery moved
to `/gallery`; `/v/<id>` and `/classic` unchanged); the public site (B-001) ships stash as the
face; new UI features land stash-FIRST and other skins are best-effort maintenance, no longer
feature-parity targets (supersedes the all-skins fan-out default of D-0006's round).

## D-0008 - GO PUBLIC greenlit; cleanup first (Locked, 2026-07-26)
Owner greenlit B-001 (public launch, full plan in docs/backlog.md): manual whisper-paste path +
Trade Bridge extension pushed via the trust checklist, zero-cost stack (CF Pages + free-tier
function + Workers KV), stash as the face (D-0007). Sequence he set: (1) dead-code cleanup pass
(scope: bpc/*.py, web.py, core.js, root files; alternate skins stay per D-0007 - only obvious
residue there), then (2) build the public deliverables (static site public-mode, api/build
function, KV cache worker, owner-PC seeding job, extension store packaging), with (3) a
step-by-step owner guide (GOING-PUBLIC.md) for every manual step (accounts, deploys, store
submissions, domain, scheduled seeding) - the PoE2 setup-docx pattern, updated for PoE1.
**Cleanup outcome (2026-07-26):** repo already clean - finders + main-agent referee: kept
`_reference.html` (documentary worked-example for skin builders) and the core.js unused exports
(deliberate API surface, public build consumes some); fixed 3 README drift items (recover.py
dangling cross-ref, Autoscan missing from advanced-search section, pob.py/util.py missing from
layout). Note: the workflow's two prove-agents died on a structured-output cap - verdicts were
re-derived by the main agent, not taken from the workflow's misleading "all refuted" return.

## D-0009 - Public-build trust fixes (fix round 1) (Locked, 2026-07-27)
Fixed the two MAJOR + all MINOR findings from the public-build verification (docs/verify/pub-*.md;
details in docs/notes-public-fix1.md). Two are fundamental to B-001's trust thesis:
- **Transparency page no longer self-falsifies (pub-adversarial MAJOR-2).** The two Google font
  families are now **self-hosted** (`public/site/assets/fonts/*.woff2` + `fonts.css`; Google
  `<link>`s removed from both HTML pages) so the browser contacts NO third party for fonts;
  `web.poecdn.com` (GGG's image CDN for item icons, loaded client-side) is added as a row in the
  how-it-works endpoints table; "no analytics, no tracking" softened to the truthful "no cookies
  we set / the only third-party contact is GGG's image CDN". "Every server this site contacts" is
  now an accurate claim.
- **Community cache trust model (pub-adversarial MAJOR-1).** The cache is an OPEN store (the
  extension POSTs results back, so writes can't be secret-gated). Hardened `worker.js`:
  `confidence` is now **DERIVED server-side from `total_found`** (client value ignored - can't
  forge "high"); each chaos tier is **capped at 1e8**; a soft **per-IP daily write budget**
  (`MAX_WRITES_PER_IP_DAY`, default 600, env-overridable) stops one script from draining the KV
  free-tier write quota (the ~17-POST DoS); oversized POST bodies rejected pre-parse. The **site**
  now renders every cache-sourced number as **"community · unverified"** (neutral dot, never the
  green verified-price dot) in the tooltip + manual panel. A distributed flood remains possible
  (inherent to a keyless open cache on the free tier) - documented as accepted; cache is
  best-effort. worker.test.mjs 45->55 green.
- **Minors:** `_http.py` now re-runs the host guard on every redirect hop (+caps depth) so the
  "structurally impossible" claim holds; `build_zips.py` REFUSES (non-zero exit, `_INVALID_
  PLACEHOLDER` output names) when the manifest domain placeholder remains, and the stale
  placeholder zips were removed from `public/dist/`; `.gitignore` no longer blanket-ignores
  `dist/` (kept `build_zips.py`, still ignores `*.zip`); `response.py` `priced_items` now requires
  a finite tier (a granted-only gem group no longer inflates the count: ascii fixture 6->5).
  pub-functional MINOR-2 (copy `vercel.json` to `public/` at deploy) is an owner step already
  documented - left as-is. `python tests.py` stays green; api `_verify` phase A green.

## D-0010 - Public name: DivTally (Locked, 2026-07-27)
Owner picked **DivTally** (his coinage; endgame lingo "how many divs?" + the tally/ledger
aesthetic) after rejecting BuildTally (live construction-software collision at buildtally.com).
Verified clean 2026-07-27: divtally.com + .net registry-confirmed unregistered (Verisign RDAP),
divtally.pages.dev free, no product named DivTally findable. Canonical origin =
**https://divtally.com** (Pages custom domain; staging + fallback origin divtally.pages.dev;
both, plus www, in the extension's production content-script matches - localhost stays in
manifest.dev.json only). Brand sweep: extension ("DivTally - Trade Bridge"), store listings,
public site titles/footer, how-it-works, launch post, GOING-PUBLIC (running example -> divtally;
domain registration moves from optional Phase 5 into Phase 1 since the name IS the domain).
Local dev app keeps its repo identity; DivTally is the public-facing brand.

## D-0011 - Copy rule: no third-party product names in descriptions (Locked, 2026-07-27)
Owner: "in descriptions of our product don't mention products other than path of exile official
ggg official products." Applied to store listings, launch post, site meta/hero/UI strings:
poe.ninja / Path of Building / pobb.in replaced with generic terms ("public build link", "build
import code", "public economy data"). Path of Exile itself stays (with the not-affiliated line).
CARVE-OUT (flagged to owner): the how-it-works ENDPOINTS TABLE keeps literal API hostnames - it
is a technical transparency disclosure, not marketing; strip on owner request. Public git
identity: repo-local user = DivTally <divtally@gmail.com>, full history rewritten to it
pre-publish (personal email never ships in public metadata).

## D-0015 - NO implicit affix exclusion; the picker is the mechanism (Locked, 2026-07-27)
Owner veto, his words: "if the user doesn't manually exclude an affix we should not be doing that
for them." D-0014's auto-relax REVERTED same day (deployed): the default query requires ALL of an
item's affixes again - honest exactly-this-good searches, even when that means no matches. Affix
selection is exclusively USER-driven via the per-rare AFFIX PICKER (next build round): prompted
per rare like the local app (checkboxes prefilled ALL-ticked, min/max, pseudo-resist fold as a
visible user toggle), driving the extension search or the trade link. Autoscan stays strict-all.
Lesson re-learned (feedback_ask_user_first / match-shop-patterns): he asked for his picker back;
I built an auto-relaxer instead - the owner's stated mechanism IS the spec, not the goal I infer
behind it.

## D-0014 - Rare default query relaxed to count(n-1 of n) - SUPERSEDED by D-0015 (2026-07-27)
Owner diagnosed the "no buyout" plague correctly: the AND-all-affixes default (inherited from the
local CLI default) over-constrains - exact combos match a handful of unpriced dump-tab listings.
LIVE-verified on PoE1 (count groups were previously untested here): the same rare 4 matches/0
buyouts strict -> 139 at count>=2 -> deployed default count>=n-1: 33 matches, fetched listings
priced. Shipped in public/api querybuild (n>=3 -> count n-1; n<=2 unchanged); browser trade_url
carries the same relaxed query (consistency). Tuning value n-1 is [INFERRED] (one build's
evidence) - revisit with real usage. Caveat recorded: relaxed matches bias LOW (cheapest of a
looser superset); acceptable for ballpark rare pricing per the README's own framing. NEXT
(Proposed): port the local app's per-rare AFFIX PICKER (choose affixes + min/max, pseudo-resist
folding) to the public site as advanced mode driving the extension - restores the control the
owner remembers from the local app.

## D-0013 - Extension named "DivTally Browser Extension"; how-it-works UX copy (Locked, 2026-07-27)
Owner: retire the "Trade Bridge" sub-brand - the extension is "the DivTally browser extension",
and that is its store name. Sweep: manifest name -> "DivTally Browser Extension", store-listing
title/copy, zip filenames, site strings ("bridge active" -> "extension active"), launch post,
guide. Also owner-approved: the how-it-works ONE RULE box is replaced by a concise HOW TO USE IT
bullet list (his copy direction: to-the-point, grammar-sacrificed) + ONE short line keeping the
rares-price-on-your-machine trust point, full story below. Applied post-workflow (site/ext files
owned by the scan-status agents at decision time).

## D-0012 - Autoscan bridge timeout bug (found by owner's live test; fixed 2026-07-27)
Owner's first real Autoscan (17 rares, extension installed) produced zero prices. Root cause:
core.js sent ALL rares as ONE bridge message with a fixed 45s reply timeout, while the extension
correctly prices serially under its conservative rate limiter (~2-4 min for 17 items) - the page
dropped the pending handler long before the (successful) reply arrived, so no rows filled and no
cache upload happened. Hypotheses REFUTED on the way: GGG does NOT reject chrome-extension
Origins (live-tested 200); page->extension payload shape and priceQuery arg order are correct.
Four questions: **instance** - chunked sequential sends (3 rares/message), per-chunk timeout
30s+30s/item, progressive row fill, per-chunk cache POST, failed chunk never blocks the rest;
**class** - the single-item path shares the same chunk code; no other multi-item bridge waits
exist; **guard** - comment at the call site names this bug; **invariant** - a page must never
await one multi-minute MV3 message reply; batch work is chunked so every reply lands well inside
its own timeout. Extension/zips UNCHANGED (bug was page-side only). Redeployed to Pages.
Validates the owner's test-before-store-submission call (D-0008 sequence change).
