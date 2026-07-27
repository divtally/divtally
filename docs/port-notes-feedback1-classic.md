# Port notes — feedback round 1 (D-0006), CLASSIC UI

Spec of record: `docs/feedback1-spec.md` (D-0006 in `docs/00-decision-log.md`). Shared-JS side:
`docs/port-notes-feedback1-corejs.md`. Engine side (done): `docs/port-notes-feedback1-engine.md`.

## 0. Where the classic UI actually lives (the answer to "locate it")

**The classic UI is NOT a `bpc/ui/*.html` skin and does NOT use `core.js`.** It is a single,
self-contained HTML+CSS+JS page held in one Python string, **`PAGE`**, inside `bpc/web.py`
(the `PAGE = r"""…"""` literal, ~line 585). It is served verbatim by the `/classic` route:

```
elif path.path == "/classic":
    self._send(200, PAGE, "text/html; charset=utf-8")
```

The gallery landing page (`/`) links to it ("Prefer the known-good original? Open the classic
UI →"). Unlike the skins in `bpc/ui/` (stash/binder/waterfall/…), classic has **its own
rendering engine** written inline in `PAGE`'s `<script>` — it never touches `core.js`,
`sample.js`, or `/assets/*`, and therefore has **no `?mock` demo path**. It reads the same
engine→UI JSON contract (`/api/job` snapshot: `JOB.items`, `JOB.priced`, `JOB.rares`,
`JOB.meta`) directly and renders flat per-group tables via `GROUPS = [equipment, flask, jewel,
gem]`.

Because it owns its own rendering, none of the shared-JS D-0006 helpers (`bpc.gemGroups`,
`bpc.gemBreakdown`, `bpc.searchAllRares`, …) apply here — the three changes had to be
re-implemented **directly against the spec's JSON fields** in `PAGE`. That is what this round did.

**Files changed:** `bpc/web.py` — the `PAGE` string only (markup + inline CSS + inline script).
Nothing else in `web.py` was touched. In particular the shared `_run_job` granted heuristic at
`web.py:315` (`row["granted"] = not _inv.startswith("SkillSlot")`) is **NOT mine** — it feeds
every skin and is the `web.py`-agent's §B.1 one-liner (see §Cross-agent dependency below).

## 1. Flask belt (spec §C)

Before: the flask group rendered as an ordinary price table row-per-flask (no life/mana doll —
classic never had the PoE2 doll, so there was nothing to delete, only a belt to add).

After: the flask group renders a **5-slot belt** (`beltHTML(rows)`), filled **in flask order**
(`JOB.items` preserves the engine's belt order). Details:
- Slots are labelled `slot 1 … slot 5` — generic **belt positions**, no life/mana, no
  name/effect guessing.
- `Math.max(5, rows.length)` slots: fewer than 5 flasks → the remainder render as dashed
  **empty** slots; **more** than 5 (weapon-swap sets) → overflow slots wrap on below — **never
  dropped** (spec §C.2).
- Each filled slot carries the same `data-k` + `.c-min/.c-med/.c-high/.c-conf/.note/.iname/
  input.row` hooks the existing `fillPriced()` targets, so pricing, the include/exclude
  checkbox, the "Flasks · all" group toggle, and the desaturate-on-exclude styling all keep
  working unchanged — the belt is a re-layout, not a new data path.

## 2. Gems grouped by host item + corrected GRANTED tag (spec §D, §B)

Before: one flat gem table, one row per active skill group, supports not shown, **no GRANTED
badge at all** (the classic page never referenced `granted`).

After: a dedicated `renderGems()` builds the section grouped by **host item**:
- Group key = **`p.host_inventory_id`** (from the priced entry; falls back to `host_slot`,
  then a single ungrouped **"Gems"** bucket for PoB imports / pre-price). Header =
  `"<host_slot> — <host_name>"`, marked **unique** when `p.host_unique`. One host can hold
  multiple skill rows — all land under the one header. Rows are never dropped.
- Supports **nested under their active**: `gemRowHTML(it)` reads the priced entry's **`p.gems[]`**
  (`gems[0]` = active, `gems[1:]` = linked gems in engine order) and shows each nested gem's
  name · Lv/quality · its own `chaos` price (or `—` when `null`). A linked **second active**
  (`support === false`) still nests and still shows its price (matched by **index/position via
  `p.gems`**, not by name or a `support` filter — spec §D.2). Before the price lands it falls
  back to the skeleton `it.supports[]` (names/levels, no price).
- Headline "total" column = **`p.total_chaos` (== `p.chaos.median`)** = active + every support,
  granted excluded. `recompute()` already sums `p.chaos.median` per group into the build total,
  so support costs stay counted.
- **GRANTED tag corrected:** the row badge reads **`it.granted`** (skeleton row), styled amber;
  per-gem granted markers read **`p.gems[i].granted`** and render struck-through / excluded with
  no number (their `chaos` is `null`). Granted gems **default OUT** of the total (a gem's
  include-state is defaulted ON iff priced **and** not granted, first time its price lands). This
  is the spec's §B.2 rule — the classic now shows the tag *correctly* (only genuinely
  item-provided gems, e.g. a Lost Unity herald), where before it showed no tag.

Because gems are now fully owned by `renderGems()`, `fillPriced()` **skips gem keys**
(`if(gemKeys.has(k)) continue;`) so the two paths don't fight over the same rows. `renderGems()`
is signature-gated (rebuilds only when a gem's price / host / enabled state changes) and is
called from `poll()` right after `fillPriced()`; the final `done` poll renders it with all
prices before polling stops, and post-`done` checkbox toggles update the live DOM + `recompute()`
without needing a rebuild.

`tr[data-k]` selectors in `fillPriced()`/`recompute()` were generalised to `[data-k]` so they
match belt-slot `<div>`s and gem `<tr>`s alike (equipment/jewel rows are still `<tr>` and match
identically — the container element is always first in document order, ahead of its inner
`input[data-k]`).

## 3. Autoscan button (spec §E)

The classic picker (`renderPicker`) is a **single-rare** flow — it had per-item **Search this
item / Skip / Back** only, and **no** bulk "Search all N" / "Skip all N" row at all. So this
round *added* the bulk capability the owner asked for:
- **Glowing "Autoscan (N)"** button at the **TOP** of the picker (`id="pSearchAll"`,
  `class="autoscan"`), shown only when `remain > 1` rares still need a decision. It prices
  **every remaining rare** with its **default all-affix search** — a new `searchAllRares()` that
  builds the default payload per rare **without the DOM** via `defaultRarePayload(k)` (mirrors
  what "Search this item" submits with no edits: every searchable+`prefer` affix at its rolled
  value, pseudo-combined when the item has resistances, negated mods filtered on MAX). This is a
  faithful port of `core.js::defaultRarePayload` + `searchAllRares`.
- **Small, non-glowing "skip all (don't price)"** (`id="pSkipAll"`, `class="skipall"`) kept
  **below** the per-item buttons; wires to a new `skipAllRares()` (POST `{skip:true}` for each
  remaining rare). Same `remain > 1` guard.
- Per-item `Search this item` / `Skip` / `Back` unchanged. The old `submitRare` POST was factored
  into a shared `postRare(k, body)` reused by all three paths.
- Glow recipe per spec §E.3, adapted to classic's own accent (`--acc: #c79a4b`) via `color-mix`,
  with an `autoscanPulse` keyframe and a `prefers-reduced-motion` opt-out.

The ids `#pSearchAll` / `#pSkipAll` follow the spec's naming; classic wires them through its own
event-delegated click handler (it has no shared `pkWire*` handlers).

## 4. Verification performed (all offline / local — ZERO trade calls)

1. `python -c "ast.parse(open('bpc/web.py'))"` → parses clean (71,042 chars).
2. Extracted the `PAGE` inline `<script>` (28,268 B) and `node --check` → **clean** (no JS
   syntax errors).
3. Booted `python -m bpc.web --no-browser --port 8920`; `GET /classic` → **HTTP 200** (40,748 B).
   Confirmed the served page contains every new surface: `class="belt"` + `beltHTML`,
   `id="gemsec"` + `renderGems`, `function searchAllRares` / `skipAllRares`, `id="pSearchAll"`,
   `autoscanPulse`, `Autoscan`, `badge-granted`, `defaultRarePayload`, `gemKeys`. Server killed;
   port confirmed closed (no listener).

**Not exercised end-to-end at runtime:** the classic page has **no `?mock` path** (it doesn't
load `sample.js`), and live pricing is blocked this round (no trade calls). So belt-fill,
gem-grouping, and granted rendering were validated **by construction** — they consume exactly the
additive fields the engine already emits and the spec documents (§A), the same fields the
`corejs` agent semantically verified against `sample.js`. A future live/fixture run should
eyeball the three surfaces once the engine + web.py §B.1 fix are wired.

## 5. Cross-agent dependency (flagged — NOT my file)

Same dependency the `corejs` notes flagged: the shared `_run_job` granted flag at **`web.py:315`**
still uses the old PoE1-wrong heuristic `row["granted"] = not _inv.startswith("SkillSlot")`, which
tags **every** gem granted on **live** builds. Until the `web.py`-owning agent lands the §B.1
one-liner `row["granted"] = bool(it.granted)`, the classic gem badge/default-off will (correctly,
per the data it's handed) light up for every gem on live builds — my rendering reads `it.granted`
exactly as the spec prescribes, so it becomes correct the moment that one line lands. The
per-gem breakdown reads `p.gems[i].granted`, which the engine already computes correctly. No
classic-side change is needed for the fix to take effect.
