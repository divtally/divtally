# Claude operating rules - PoE1 Build Price Checker

This file auto-loads into context whenever working under `C:\scripts\buildpricechecker-poe1`. It is
the durable contract for how to work on this project. **Conversation history is NOT durable** -
auto-compaction can summarize or drop it at any time. These docs are the source of truth.

These rules are ported from the Cardescent project (`C:\scripts\phone-game\CLAUDE.md`) at the
owner's request (2026-07-26), adapted where the original machinery was Cardescent-specific
(hub/survey portal, vertical-slice freeze). The rule numbers are kept aligned.

## RULE 1 - Record fundamental changes in docs IMMEDIATELY (highest priority)
The moment a fundamental design, scope, methodology, or architecture decision is **made or
changed**, write it to `docs/00-decision-log.md` **before** continuing the discussion or writing
code. Never let a decision live only in chat.
- **New decision** -> append a dated entry (status: Locked / Proposed / Superseded).
- **Changed or reversed decision** -> mark the old entry `Superseded`, add the new one, and fix any
  doc that now contradicts it (README.md, docs/) in the **same turn**.
- **"Fundamental"** here = pricing methodology (how a category of item is priced), which API
  endpoints/semantics we depend on, currency normalisation, rate-limit strategy, the engine->UI
  JSON contract, scope cuts.
- When in doubt, record it. It is cheap insurance against compaction.

## RULE 2 - Stay compaction-aware
Assume the next message could arrive after the conversation was summarized away. If you notice
context was compacted (or you're unsure), re-read `docs/00-decision-log.md` and the open docs
before acting. Before ending a working session, confirm the latest decisions are in the docs.

## RULE 3 - Keep going while clear work remains
If there is still clearly-defined work that advances an agreed goal, do NOT stop to check in - keep
building, testing, and committing green increments. Only pause when (a) continuing risks breaking
something (real ambiguity that could cause rework, a destructive/irreversible action, or a genuine
design fork that's the owner's call), or (b) the defined work is done. Default to pushing
multi-step work through in one go.
**Match the action to WHOSE work it is:** for the owner's explicit requests + already-agreed work,
keep going without asking. For NEW, self-initiated scope the owner did NOT ask for (a proactive
audit, a polish sweep, a refactor, an unrequested feature): PROPOSE it first and get the owner's
greenlight before spending effort. This project has no hub portal - proposals go in chat and/or
`docs/00-decision-log.md` with status `Proposed`.

## RULE 4 - Prefer subagents / parallelism (speed up production)
When a task or an independent sub-task can be delegated to a subagent - research, API probing,
broad search, an isolated implementation slice - do so as a FIRST priority. Launch background
subagents for long or independent work; relay only their conclusions. Delegated work stays on
disjoint files to avoid conflicts; subagents never spawn their own subagents.
- **CONTAINMENT (hard rule):** keep ALL agent work - reads, searches, writes - INSIDE
  `C:\scripts\buildpricechecker-poe1`. The parent project `C:\scripts\buildpricechecker` may be
  read **read-only** as reference. NEVER scan or read the home directory `C:\Users\user` or anything
  outside these two folders: it contains a synced OneDrive folder and scanning it hydrates cloud
  files. Every subagent/workflow prompt must state this scope explicitly.
- **ULTRATHINK every subagent:** every subagent + workflow agent reasons at maximum depth. Include
  `ultrathink` (plus "reason at maximum depth before acting") in EVERY agent prompt, and set
  `effort: 'high'` (or `'max'`) on every Workflow `agent()` call. When the session model is Fable,
  set `model: 'opus'` explicitly on every agent call. No exceptions.
- **RATE-LIMIT DISCIPLINE (project-specific hard rule):** at most ONE agent at a time may hit the
  pathofexile.com trade *search/fetch/exchange* endpoints (violations cause temporary IP bans).
  Static reference data (`/api/trade/data/*`) and poe.ninja endpoints are cheap but still cached
  and fetched politely.
- **STALL WATCHDOG (owner rule 2026-07-27):** never let a subagent go stale for more than 10
  minutes. Every background agent/workflow run gets an active Monitor (transcript-activity check,
  alert at <=600s of silence). On alert: read the transcript tail; if stuck, kill and
  relaunch/resume (workflows: `resumeFromRunId` replays the finished prefix from cache). Lost
  build time from silently-stuck agents is the failure mode this prevents.

## RULE 5 - Surface owner decisions async; never block mid-work
When a design/scope/priority decision is the owner's call, log it in `docs/open-questions.md`
(with a recommended pick marked) and raise it in chat at a natural boundary (start/end of a work
block) - never stop mid-work for a non-blocker (global no-asking rule). Prune each question the
moment its answer is in. (Cardescent routes these through its /hub survey portal; this project has
no hub, so chat + the open-questions doc are the channel.)

## RULE 6 - Reimplement from the decision log; DELETE what you supersede
When (re)implementing anything against a locked decision:
- **Ground in `docs/00-decision-log.md` + `docs/research/`, not a summary.** The research notes
  record what the live APIs actually return - read them before coding.
- **A change that REPLACES a mechanism must DELETE the old code in the same cutover.** Superseded
  code that still compiles silently wins. No "leave the old path for later." This includes PoE2
  leftovers: dead trade2/PoE2 code paths are bugs, not harmless residue.
- **"Module written" is not "done."** Wire producer -> consumer end-to-end (engine -> report/web ->
  UI) before calling a system complete.
- **When the build diverges from a plan/doc, update the doc; mark superseded docs superseded.**

## RULE 7 - Converge, then validate (adapted)
Once a working state has shipped, convergence work (bug fixes, verification, doc reconciliation)
outranks new features. New feature ideas - whether proposed by Claude OR requested casually - go to
`docs/backlog.md` unless the owner explicitly says to build them now. Verification ladder for any
feature: built -> tests green -> exercised end-to-end live -> owner-tested. Nothing advances by
silence; only the owner marks owner-tested. (Cardescent's vertical-slice freeze + hub validation
ledger do not apply here.)

## RULE 8 - Test the promise, not the implementation
The README (and docs/) text is the contract. Tests derive from **documented behavior** - the
tiers table, the input formats, the option flags, the pricing methodology per item category - not
from observed engine output. When code and README disagree, one of them is a bug: fix the code, or
if the promise itself is wrong/ambiguous, flag the fork to the owner (RULE 5). New behavior ships
WITH its test and its README line.

## RULE 9 - Periodic systems retro
Every **15 decision-log entries or 30 days** since the last retro, whichever comes first (or on
`/retro`), run the global `/retro` skill: grade the previous retro's changes FIRST (keep / extend /
revert by recorded metric), proposals need >=2 concrete receipts, max 3-5 proposals, owner gates
execution. Reports land dated in `docs/retro/`.

## What this project is
A clone of **buildpricechecker** (`C:\scripts\buildpricechecker`, PoE2) scoped to
**Path of Exile 1**: paste a poe.ninja build link (or PoB code / paste link) -> fetch the
character's gear/flasks/jewels/gems -> price each item against the official
**pathofexile.com/api/trade** API -> report min / median / high budget tiers, normalised to
**Chaos Orbs** and also shown in **Divine Orbs**.

## Architecture guardrails (inherited from the parent; do not drift)
- Same layout as the parent: `bpc/` package - `engine.py` shared pipeline used by both `cli.py`
  and `web.py`; self-contained UI skins in `bpc/ui/*.html` all driving `/assets/core.js`; tiny
  TTL disk cache. Keep the engine->UI JSON contract stable.
- **Rate limiting is load-bearing:** read GGG's `X-Rate-Limit` headers, stay well under every
  window, honour `Retry-After`, cache aggressively. Nothing requires logging in (no POESESSID).
- Unpriceable items get a trade link and no number - never a misleading number.
- Any pricing fact not derived from a live API response or the parent's verified code gets a loud
  **[NOT FROM SOURCE]** / **[INFERRED]** tag at point of use (global rule).
- Keep `.cmd`/`.ps1` files ASCII-only.

## Map of the project
- `CLAUDE.md` - this contract.
- `docs/00-decision-log.md` - dated, numbered decisions (D-0001...). The spec of record.
- `docs/research/` - live-API reverse-engineering notes for PoE1 (poe.ninja + trade).
- `docs/open-questions.md` / `docs/backlog.md` - owner forks / parked features.
- `bpc/` - the package. `research/` - probe scripts (not needed at runtime). `cache/` - runtime.
