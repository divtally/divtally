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
