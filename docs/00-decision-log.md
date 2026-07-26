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
