# v4 review - adversarial residue + correctness (PoE2 -> PoE1 port)

**Reviewer:** subagent (adversarial pass). **Date:** 2026-07-26.
**Scope:** whole repo excl. `docs/research/`, `research/`, `cache/`, `.git`.
**Baseline diff:** working tree vs `b2c5924` ("Initial clone from buildpricechecker (PoE2) - pre-port baseline").
**Method:** residue grep of live code; read every core module; cross-checked every data-shape / id claim against the live dumps in `research/data/`; ran the offline self-test suite; tried to *refute* the port's correctness against `docs/research/trade1.md`, `economy.md`, `pob1.md`.

## Verdict

**PASS with 3 minor follow-ups. No blockers, no majors.** The core pricing pipeline is
correctly ported and verified: trade endpoints/URLs, chaos-base currency normalisation, the
dynamic statmap, `armour_filters`/`socket_filters`/gem-search query construction, gem
name+bucket matching, listing statuses, league resolution, rate-limit windows, and the
engine->UI JSON contract. `python tests.py` => **All self-tests passed** (fully offline; no
trade calls made by this review).

The port is unusually clean: every item on the task's "plausible-but-wrong" hunt list was
checked and **refuted** (table below). Two premises in the task were themselves wrong and the
research already corrected them (also below).

---

## Residue sweep (live code)

Grepped `bpc/**`, `extension/**`, root `*.py`/`*.cmd`, `README.md` for `trade2`, `poe2`,
`exalt`, `rune(s)`, `soul core`, `uncut`, `jeweller`, `securable`, `desecrated`,
`equipment_filters`, `gem_sockets`, plus PoE2 league names.

| Term | Live-code hits | Verdict |
|---|---|---|
| `trade2` / `poe2` / `/api/trade2` / realm `poe2` | 0 in executable code | Clean. `BASE="https://www.pathofexile.com/api/trade"` in `bpc/trade.py:26` and `extension/background.js:15`; no realm segment. All comments referencing PoE2 are explanatory ("deleted", "unlike PoE2"), not code. |
| `equipment_filters` | 0 | Correctly renamed to `armour_filters` (`bpc/pricing.py:593,721`). |
| `gem_sockets` | 0 | Correctly dropped from `_gem_search_url` (`bpc/pricing.py:754-777`). |
| `desecrated` | 0 in code | Only comments; `desecratedMods` bucket dropped from `_EXPLICIT_MOD_KEYS` (`bpc/poeninja.py:391-394`). |
| `rune` / `soul core` / `uncut` | 0 in Python logic | `CAT_RUNE` deleted (`bpc/models.py:11-12`); `price_rune`/uncut/Jeweller ladder deleted from `pricing.py`. **Exception:** dead **CSS** `.rune`/`--rune` in 6 UI skins - see MINOR-3. |
| `jeweller` | 0 in code | Only a comment noting the deleted PoE2 synthesis (`pricing.py:784`). Jeweller's Orb is a legit PoE1 currency but is not referenced in code. |
| `securable` / `available` | present, intentional | **NOT residue** - both are valid PoE1 statuses (see premise correction). |
| `exalt` | present, intentional | **NOT residue** - `exalted` is a real PoE1 currency id (dump: `primaryValue` 0.7216 chaos). `_BASE="chaos"` (`currency.py:17`), not exalted. |
| PoE2 league names (Standard-only hardcodes, etc.) | 0 | League read live; only "Standard" as a last-ditch fallback (`engine.py:130,135`). Demo/placeholder strings use `Allflame` (a real PoE1 league). |

---

## Findings

### MINOR-1 - PoB-import path drops socket/link data => 5L/6L gear underpriced
**Files:** `bpc/pob.py:29-34,152-153,237-243` (Sockets line skipped as a property, `max_link`
never set) vs `bpc/pricing.py:283-290` (`_links_filter` requires `item.max_link>=5`).

The poe.ninja path correctly derives links (`bpc/poeninja.py:319-329` `_sockets_info`;
verified against `research/data/char_poe1.json`: a 6-link body armour -> `max_link=6`, and the
suite asserts it, `tests.py:352`). The **PoB parser never populates `max_link`** - the
`Sockets: R-G-W` line is consumed by `_is_property()` and discarded - so every PoB-imported
item has `max_link=0` and `_links_filter` returns `{}`. A PoB-imported 6-link body armour / 2H
weapon is therefore searched with **no links filter**, matching cheaper low-link listings and
**underpricing** it (the code's own docstring calls a 6-link "often the single largest cost on
a budget build", `pricing.py:284-286`).

**Provenance / severity:** This is a **documented, consciously-deferred gap**, not a silent
regression - `docs/research/pob1.md` §3.4 (lines 181-182: "link count **not** extracted ...
this is where 6-link value would come from - currently dropped") and §7 item 4 ("Optional
(pricing quality): parse `Sockets:` colored-link groups"). The query built is well-formed; the
input is just legitimately 0. Hence **minor**. It is worth flagging because the port *added*
link-pinning on the poe.ninja path, creating an **asymmetry**: the same 6-link build prices
differently depending on whether it is loaded via poe.ninja (pinned, correct) or PoB (not
pinned, low). Escalate to major if PoB-import 6L accuracy matters.

**Fix hint:** in `pob.py`, parse the `Sockets:` line (groups space-separated, sockets within a
group joined by `-`; notation documented in pob1.md §3.4) into `max_link = len(largest
hyphen-run)` and pass `max_link`/`total_sockets` to the `Item(...)`.

### MINOR-2 - Economy league not normalised like the trade league (SSF builds lose gem/currency pricing)
**Files:** `bpc/engine.py:74,120,190` and `bpc/recover.py:106` - `PoeNinjaEconomy(meta.league)`
is passed the **raw** build league, while the trade league is normalised via
`_norm_league`/`resolve_trade_league` (`engine.py:31-54`).

For an SSF build, `meta.league` is e.g. `"SSF Allflame"` / `"HC SSF Allflame"` (the codebase
knows this - `_norm_league` explicitly strips `ssf`, and `tests.py:205` asserts
`_norm_league("HC SSF Allflame")==_norm_league("Hardcore Allflame")`). poe.ninja publishes **no
economy** for SSF leagues, so `chaos_by_id`/`gem_price` return nothing: every gem shows
"couldn't price (poe.ninja economy unavailable)" (`pricing.py:791-796`) and currency conversion
falls back to the trade `exchange` endpoint. The trade *search* itself is fine (correctly mapped
to `Allflame`). Degrades gracefully - honest "couldn't price", never a misleading number - so
**minor**, and scoped to the niche SSF input.

**Fix hint:** feed the economy the same normalised/tradeable league the trade client uses
(strip the `SSF` qualifier), or resolve the build's league to its economy equivalent once and
pass it to both.

*(Related low-confidence note: the economy league string comes from buildLeagues `displayName`
(`poeninja.py:157-159`), while `economy.md` §1a says the overview endpoint wants economyLeagues
`name`. These coincide for the current challenge league (both `Allflame`), so no observed break;
flagging only as a rollover fragility to keep an eye on, not a current defect.)*

### MINOR-3 - Dead PoE2 "rune" CSS residue in UI skins (cosmetic)
**Files:** `console.html:178`, `manifest.html:17,235`, `abacus.html:79`, `waterfall.html:15`,
`foundry.html:162`, `stash.html:508,532` - `.rune` / `.r-rune` / `.rar-rune` / `--rune` /
`--g-rune` / `.mtag.rune` / `.tt-mod.rune` selectors and colour vars for a `rune`
category/group. Plus a decorative themed string `EXALT AIR` (`manifest.html:569`, an
airline-styled skin).

The PoE1 engine never emits a `rune` category or group (`CAT_*` = unique/rare/magic/gem/normal;
groups = equipment/flask/jewel/gem), so these selectors never match anything. Per RULE 6 they
are dead PoE2 residue worth deleting, but they are pure CSS/decoration and **cannot affect
prices or cause a crash** - hence minor/cosmetic. (Note some skins reuse `var(--rune)` for the
`currency` tag colour, e.g. `manifest.html:235`, `abacus.html:79` - re-point those before
deleting the var.)

---

## Refuted hypotheses (adversarial checklist - all PASS)

| Hypothesis to break | Result | Evidence |
|---|---|---|
| Links/socket filter malformed | **Correct shape** `{"socket_filters":{"filters":{"links":{"min":N}}}}` | `pricing.py:283-290`; matches trade1.md §2b [LIVE]; `tests.py:181-189`. (Omitted only on PoB path - MINOR-1.) |
| Statmap ids don't exist in `trade_stats.json` | **No hardcoded ids** - statmap is built from live `stats_data()` | `statmap.py:69-87`. Only 2 hardcoded ids (pseudo elem/chaos res, `pricing.py:38-39`) - both **present** in `research/data/trade_stats.json:23,28` [LIVE DUMP]. |
| Chaos/divine inversion (rate upside-down) | **No inversion** - uses the Divine *line* `primaryValue` (=chaos-per-divine, 102.5), never `core.rates.divine` (0.009761) | `currency.py:77-100`; `report.py:121`; every skin does `v = chaos / divine_to_chaos` (e.g. `web.py:751`, `core.js:97`). Verified vs `ninja_econ_currency.json`. |
| PoE1 trade URL format wrong | **Correct** `/trade/search/{league}[/{id}|?q=...]`, no realm, no `trade2` | `pricing.py:292-311`, `trade.py:211`, `stash.html:1601`; matches trade1.md §8. |
| Fetch batch size wrong | **Correct** - caps at 10 ids (11 -> HTTP 400) | `trade.py:222`, `pricing.py:360-362`, `background.js:156`; trade1.md §3. |
| Listing statuses invented | **All 5 valid in PoE1** | `pricing.py:224` = trade1.md §5 (online/any/onlineleague/available/securable). |
| Gem matching ignores quality/corruption | **Weights both** - `abs(dLevel)+0.3*abs(dQual)+100*(corrupt mismatch)` | `poeninja.py:286-297`; `tests.py:246-252`; keys verified in `ninja_econ_skillgem_sample.json`. |
| League hardcoded | **Resolved live** via `list_leagues()`; SSF/HC normalised | `engine.py:38-54,125-135`; "Standard" only as last-ditch fallback. |
| `_BASE`/exchange still `exalted` | **`_BASE="chaos"`**, `have=["chaos"]` | `currency.py:17`, `trade.py:227-232`; exchange offer read has no inversion (`currency.py:62-70`). |
| Rate-limit windows stale (PoE2) | **Reseeded to live PoE1 headers** (search +6h, fetch +300s/+6h) | `trade.py:37-42`, `background.js:21-24`; trade1.md §7; `tests.py:200-201`. |
| Gem double-counting (active + socketed) | **Not double-counted** - supports folded into the active group; `socketedItems` deliberately not extracted | `poeninja.py:460-499`; PoB path prices each gem once (`pob.py:255-277`). |

## Task-premise corrections (documented in research, not port bugs)

1. **`securable` / `available` are NOT PoE2-only** - both exist in PoE1's `status_filters`
   (trade1.md §5 [SCHEMA]; `research/data/trade_data_filters.json`). Keeping them in
   `STATUS_OPTIONS` is correct; flagging them would have been a false positive.
2. **`exalt(ed)` is a legitimate PoE1 currency**, just not the base unit. It appears correctly
   as a convertible currency id (`ninja_econ_currency.json` -> 0.7216 chaos), while the base is
   chaos. Not residue.

## Confirmed-correct data-shape dependencies (spot-checked vs live dumps)

- Currency lines expose `{id, primaryValue}` with ids matching trade `price.currency`
  (chaos=1, divine=102.5, exalted=0.7216, mirror=16787) - `poeninja.py:232-239` reads exactly
  these.
- Gem lines expose `gemLevel/gemQuality/corrupted/chaosValue/listingCount` with quality/corrupt
  nullable; code guards `or 0` / `bool(...)` (`poeninja.py:288-297`).
- Char items are frameType-3 uniques carrying `sockets:[{group,attr,sColour}]`; `_sockets_info`
  computes `max_link` from the largest `group` (`poeninja.py:319-329`).
- `.cmd` launchers are ASCII-only (verified: 0 non-ASCII bytes).
