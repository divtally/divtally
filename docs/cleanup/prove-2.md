# prove-2.md — Adversarial referee: README doc-drift candidates (batch 2)

Role: adversarial referee. For each candidate I tried to **refute** that the README line is
drift (i.e. tried to justify `delete=false` / "leave the line alone"). Every reference below was
**re-derived from scratch** with my own greps/reads — the finder's evidence was not trusted.
Both candidates are doc-drift, so `delete=true` = "fix the README line" (corrected wording given).

Scope note: I touched only this file. All reads were inside `C:\scripts\buildpricechecker-poe1`.

---

## Candidate 1 — [doc-drift] README.md:92 — `recover.py` "(see below)" dangling cross-ref

**Claim under test:** Line 92 says "The CLI equivalent is `recover.py` (see below)." but there is no
section below describing `recover.py`; the pointer is dangling. `recover.py` itself is real/used.

**Independent re-derivation**

- Exact line 92 text (Read README.md): `results. The CLI equivalent is `recover.py` (see below).`
  In full context (L88–92) it's the tail of the "Recent builds / Loading a build" paragraph:
  "…To refresh prices, use **Search all again** (re-runs every search)… The CLI equivalent is
  `recover.py` (see below)." — CONFIRMED verbatim.
- Every `recover` mention in the README (`grep -i recover README.md`): **line 92 only.** `recover.py`
  is named nowhere else in the file, so nothing "below" describes it. — CONFIRMED.
- All README headings (`grep '^#{1,6}\s'`), filtering out lines 123/126/129 which are `#` **bash
  comments inside the ```powershell fence**, not markdown headings:
  `## Install`(17), `## Usage`(26), `### Web UI`(28), `#### The look`(38), `### Command line`(120),
  `### Options`(143), `## How it works`(162), `### Rate limiting`(200), `## Limitations`(210),
  `## Project layout`(222). The headings after L92 are exactly Command line / Options / How it works
  / Rate limiting / Limitations / Project layout — matches the finder's list. **None is a recover.py
  section.**
- `recover.py` is real and maintained: `C:\scripts\buildpricechecker-poe1\recover.py` exists;
  argparse takes `url` positional + `--account` / `--character` / `--league` / `--links-only` /
  `-q`; docstring "Rebuild a build's info from the LOCAL CACHE when the poe.ninja profile is gone";
  it recovers the cached poe.ninja char, re-prices via the same engine/Pricer, injects the
  poe.ninja economy, and writes `recovered_*.json` + `.pob.txt` + `_prices.json`. `docs/port-notes-
  docs.md` further documents two substantive port fixes to it. So the **reference target is valid** —
  only the "(see below)" wayfinding word is wrong.

**Refutation attempts (all failed → line is drift)**

- R1 "There *is* a section below": grep shows recover.py appears only at L92. No section. FAILED.
- R2 "The nearest 'below' heading (Command line, L120–142) covers it": Read L120–142 — it documents
  only `bpc.cmd`, `python -m bpc`, `python -m bpc.web`. No recover.py. A reader following "(see
  below)" lands on nothing about recover.py. FAILED.
- R3 "recover.py doesn't exist, so the whole clause is wrong (bigger fix, not just the pointer)":
  recover.py exists and is used. So the clause "The CLI equivalent is `recover.py`" is TRUE — only
  "(see below)" is false. FAILED (confirms the minimal fix is dropping the pointer, not the clause).
- R4 "'(see below)' is an anchor/link I'm not rendering": it's plain text, no `[..](#..)` anchor. No.

**Verdict: delete=true (fix the README line).**
Semantic claim ("recover.py is the CLI equivalent of load-from-cache-and-reprice") is accurate — it
loads the cached character and runs fresh trade searches. Only the cross-reference is broken.

- Minimal fix (recommended): drop the dangling pointer —
  `The CLI equivalent is `recover.py`.`
- Optional fuller fix: keep the pointer and add a short subsection under **Command line**, e.g.
  "**Recover a deleted build.** `python recover.py "<url>"` (or `--account <acct> --character
  <name>`) rebuilds a build from your local cache when the poe.ninja profile is gone and re-prices
  it; `--links-only` skips pricing and just emits a trade link per item." (flags verified in
  recover.py argparse.)

---

## Candidate 2 — [doc-drift] README.md:99–106 — advanced-affix section omits D-0006 Autoscan / skip-all

**Claim under test:** The advanced-mode walkthrough documents only the per-rare buttons "Search this
item" and "Skip (don't price)", and never mentions the D-0006 bulk controls (a glowing "Autoscan
(N)" that auto-prices all remaining rares with default all-affix searches, and a small "skip all
(don't price)") that now sit at the top/bottom of the picker in every skin + classic.

**Independent re-derivation**

- README L99–106 (Read): documents `"Search this item"`, `**Skip (don't price)**`, and "Leave the
  box unchecked and rares are priced automatically, requiring **all** of the item's affixes." No
  mention of Autoscan or a bulk skip-all. The rest of the advanced block (L108–118: "edit affixes",
  resistance-pseudo toggle) also doesn't. — CONFIRMED.
- Whole-repo grep `autoscan|Autoscan|AUTOSCAN|searchAllRares|skipAllRares|skipall|skip all|skip-all`:
  **README.md has ZERO hits.** The README nowhere documents these controls. — CONFIRMED.
- The controls exist and are live (not dead markup):
  - `core.js:436 searchAllRares()` → for each remaining rare `submitRare(k, defaultRarePayload(k))`
    (= auto-price all remaining with default all-affix query); `core.js:441 skipAllRares()` → for
    each remaining rare `skipRare(k)`; both **exported** at `core.js:492`.
  - Classic PAGE in `web.py`: CSS `button.autoscan` (747) + `button.skipall` (763); render
    `<button class="autoscan" id="pSearchAll">⚡ Autoscan (N)</button>` (1163) and
    `<button class="skipall" id="pSkipAll">skip all (don't price)</button>` (1180); wired via event
    delegation (1253–1254) to `searchAllRares()` / `skipAllRares()`.
  - `stash.html` (THE app) L1486 renders the glowing `⚡ Autoscan (N)`, L1501 the small
    `skip all (don't price)`, wired L1543–1544 to `bpc.searchAllRares()` / `bpc.skipAllRares()`.
  - Every other skin renders + wires the same pair (verified by grep): atelier, console, foundry,
    waterfall, binder, facts, abacus, ledger, manifest. IDs `#pSearchAll`/`#pSkipAll` are stable
    across all of them. Guard `!info.single && remain>1` (web.py `remain>1`) shows the pair only
    while more than one rare is left to decide.
  - Provenance: D-0006 (decision log) specced & SHIPPED "glowing Autoscan wired to search-all-default
    in every picker copy" + a small "skip all (don't price)". `docs/feedback1-spec.md §E` matches.

**Refutation attempts (all failed → line is drift)**

- R1 "The README already mentions it somewhere else": zero README hits in the bulk-control grep.
  L79–82 lists "advanced affix search" only as a re-run trigger; L99–118 never names Autoscan/skip-
  all. FAILED.
- R2 "The buttons are dead / not wired (nothing to document)": defined in core.js, exported, rendered
  in all 11 UIs, and bound by id to the exported fns. Fully live. FAILED (confirms the omission).
- R3 "The current text is FALSE, so this is a correctness bug, not doc-drift": no — the per-rare
  "Search this item" / "Skip (don't price)" description is still true; the bulk controls are simply
  **unmentioned**. So it's an omission (low severity), still worth fixing before public launch, but
  not a contradiction. delete=true stands.
- R4 "Autoscan == the unchecked-box auto-price the README already covers, so it's redundant": not
  quite — Autoscan is an **on-demand, in-advanced-mode** button that applies the default all-affix
  search to *all remaining* rares at once (bail out of the manual queue), distinct from leaving the
  box unchecked up front. Worth its own sentence. FAILED to refute.

**Verdict: delete=true (fix the README line — add one sentence).**
Corrected wording — append to the advanced-affix paragraph (after L106):

> At the top of the picker a glowing **Autoscan (N)** button prices all N remaining rares at once
> with their default all-affix searches — handy once you've hand-picked the few that matter — and a
> small **skip all (don't price)** below drops the rest. Both appear only while more than one rare is
> still undecided.

(Every clause verified against source: glowing Autoscan(N) at top = stash.html:1486 / web.py:1163;
default all-affix behaviour = core.js `searchAllRares → submitRare(defaultRarePayload)`; small
skip-all below = stash.html:1501 / web.py:1180; ">1 remaining" guard = `!info.single && remain>1`.)

---

## Summary

| # | Candidate | Verdict | Fix |
|---|-----------|---------|-----|
| 1 | README:92 `recover.py` "(see below)" dangling | **delete=true** (fix line) | drop "(see below)"; optional short recover.py subsection |
| 2 | README:99–106 omits Autoscan / skip-all bulk controls | **delete=true** (fix line) | add one sentence describing the top-of-picker Autoscan(N) and the skip-all |

Both are genuine README drift confirmed by independent re-derivation; neither could be refuted. Both
are low-severity (a broken pointer and an omission) but both are user-facing README lines on the
about-to-go-public repo (D-0008), so both should be fixed as part of the cleanup pass.
