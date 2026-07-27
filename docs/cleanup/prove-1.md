# prove-1 — adversarial referee pass over cleanup batch 1

Role: **adversarial referee**. For each candidate the finder flagged as dead, I re-derived every
possible consumer *from scratch* (never trusting the finder's evidence) and tried to **refute**
deadness. `delete=true` only where I found **zero** live references after my own searches;
anything uncertain / dynamic / public-launch-adjacent stays (`delete=false`). Doc-drift
`delete=true` = "fix the README line" (corrected wording included).

Scope obeyed: reads/searches confined to `C:\scripts\buildpricechecker-poe1` (+ read-only parent
never needed here). No network. Only file created: this one.

Search surface I checked for every candidate: all `bpc/*.py`, `bpc/web.py` (incl. the classic
`PAGE` string + the `/`, `/gallery`, `/classic`, `/v/<id>`, `/assets/`, `/api/*` routes), every
`bpc/ui/*.html` (10 skins + `_reference` + `_exttest`), `bpc/ui/assets/core.js` + `sample.js`,
`tests.py`, root scripts (`app.py`, `run.py`, `recover.py`), `.cmd` launchers, `extension/`, and
`docs/` (incl. the `backlog.md` B-001 plan). Dynamic dispatch considered: `getattr` / string-built
route paths / event-handler ids / `bpc.<name>` template refs / JSON field names read by skins.

---

## Candidate 1 — `[css] a` (finder evidence: `b`) → **KEEP (delete=false)**

`a` / `b` are placeholder tokens, not a derivable dead artifact (canary-shaped candidate). I tried
every plausible reading of "css `a`" and **each one is demonstrably live**, so deadness is refuted
concretely — there is nothing to delete:

- **As the bare `a` anchor-element selector:** live across the tree. `web.py::PAGE` classic UI
  styles it at line 657 — `a{color:#8fb6e8;text-decoration:none}a:hover{text-decoration:underline}`
  — over real `<a href=...>` trade links. The `_gallery_html` template styles `.foot a{color:var(--fg)}`
  (web.py:138) and emits `<a class="card" href="/v/{id}">` + `<a href="/classic">`. A bare
  `a{...}` / `a:hover{...}` type selector occurs **14 times across 8 skins**
  (ledger, console, binder, atelier, manifest, foundry ×2 each; waterfall, facts ×1).
- **As a literal `.a` CSS class:** live in `facts.html` — styled at `facts.html:276`
  (`.supp-servline .a{font-weight:700}`) and **rendered** at `facts.html:964`
  (`<span class="a">Searchable affixes</span>`), which is inside the Build Facts skin served at
  `/v/facts` (a shipped, gallery-listed skin per README). Not dead residue even under the
  "obvious residue only" rule for skins.

Verdict: no identifiable dead target; every interpretation is live. **delete=false.**

---

## Candidate 2 — `bpc/ui/_reference.html` → **KEEP (delete=false)**

**Zero live code references — re-derived independently.** A whole-repo grep for `_reference`
returns hits **only** in `docs/` (the finder's own `docs/cleanup/find-*.md`, plus history records
`docs/port-notes-web.md`, `docs/verify/v3-web.md`). Concretely, there is **no** reference in: any
skin, `core.js`/`sample.js`, `web.py` (the `/v/` handler serves it by filename but the router has
no hardcoded link to it, and `_list_versions()`/gallery **skip** every `_`-prefixed file at
web.py:62), `tests.py`, `extension/`, the `.cmd` launchers, `README.md`, or the B-001 plan in
`docs/backlog.md`. So on a pure reference-graph test it is unreferenced. I could not manufacture a
live link.

**But this is a KEEP, because "unreferenced" ≠ "dead residue" here, and the referee guard applies:**

1. **It is reachable, on purpose.** The `/v/<id>` route accepts `re.fullmatch(r"[A-Za-z0-9_-]+", vid)`
   (web.py:488) — underscore is in the class — and serves any existing file. `GET /v/_reference`
   returns it. It is intentionally hidden from the gallery (underscore) yet reachable by URL: the
   exact structural twin of `_exttest.html`, which the cleanup brief lists as **NEVER remove**.
2. **It is out of the D-0008 mechanical cleanup scope.** That scope is `bpc/*.py`, `web.py`,
   `core.js`, root files; for `bpc/ui/*.html` only **"obvious residue"** is in scope. A
   deliberately-authored, self-documenting worked example (its own header: *"exercises EVERY part of
   bpc core.js … worked example for builders"*) is not "obvious residue" (contrast a leftover dead
   CSS rule or an orphaned PoE2 file).
3. **The finder itself frames it as OWNER'S CALL**, not a deletion — keep as the canonical minimal
   `core.js` example (backing the README pitch *"drop a self-contained `*.html` into `bpc/ui/`"*),
   or remove for a pristine public tree. That is a documentary/design judgment reserved to the
   owner, not a mechanical dead-code fact for a referee to execute unilaterally.
4. **Removing it orphans nothing.** Its only asset deps (`/assets/sample.js`, `/assets/core.js`) are
   loaded by all 10 skins too, so `sample.js`/`core.js` stay live regardless.

Per the referee rule ("anything uncertain / public-launch-adjacent = delete=false"), defer to the
owner. Keeping it is zero-cost. **delete=false.**

---

## Candidate 3 — `README.md::Project layout` omits `pob.py` + `util.py` → **FIX (delete=true)**

Confirmed doc-drift. The `## Project layout` `bpc/` block (README:224-239) enumerates 11 modules
(cli, web, engine, poeninja, trade, statmap, pricing, currency, report, models, cache) and omits two
**real, imported, actively-used** source files:

- **`pob.py`** (14,256 B). Docstring: *"Parse a Path of Building (PoE1 community) import code / XML
  into priceable items."* Imported at `engine.py:16` (`from . import cache, poeninja, pob, pricing`)
  and used at `engine.py:167` (`pob.looks_like_code`), `:185` (`pob.parse`), `:186` (`pob.PobError`),
  `:216` (`pob.looks_like_code`). It powers the PoB-input path that is a first-class documented
  feature (README:136-141, 169-176). Definitely not internal-only.
- **`util.py`** (3,544 B). Docstring: *"Small helpers: rich-text stripping, number parsing, robust
  distribution stats."* Imported by **5** modules: `web.py:23`, `poeninja.py:19`, `currency.py:13`,
  `pricing.py:20`, `statmap.py:9`. (Note: the finder wrote "6 modules" but listed 5; the true count
  is **5** — `cli.py`, `engine.py`, `trade.py`, `report.py`, `models.py`, `cache.py` do **not**
  import it. Off-by-one in the finder's note; the verdict is unchanged.)

Fix — insert two lines into the layout block, matching the block's `name    description` alignment:

- after the `poeninja.py` line (input parsing sits together):
  `  pob.py        Path of Building import code/XML -> priceable items (the PoB input path)`
- after the `cache.py` line (leaf helper, alongside cache):
  `  util.py       shared helpers: rich-text stripping, number/mod-text parsing, percentile/outlier stats`

**delete=true** (= apply the README fix above).

---

## Summary

| # | candidate | verdict | one-line why |
|---|-----------|---------|--------------|
| 1 | `[css] a` (evidence `b`) | **KEEP** | placeholder/canary; every reading of "css a" is live (`a{}` in 8 skins + classic `web.py:657`; `.a` class live in `facts.html:276/:964`). |
| 2 | `bpc/ui/_reference.html` | **KEEP** | zero live refs, but reachable `/v/_reference`, out of cleanup scope, owner's-call twin of protected `_exttest.html`, orphans nothing. |
| 3 | `README.md::Project layout` | **FIX** | `pob.py` + `util.py` are real imported modules omitted from the layout block; add the two lines above. |
