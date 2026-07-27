# Public build — functional re-verification round 1 (post-D-0009)

**Verifier:** functional re-verification agent, 2026-07-27. **Verdict: PASS.** Every finding from
the prior round (`pub-functional.md` + `pub-adversarial.md`, fixed in D-0009 /
`notes-public-fix1.md`) is confirmed resolved, and nothing regressed. **No new findings.** The hard
invariant holds: nothing server-side can reach pathofexile.com. No live trade call and no live cache
seed were run; the only live network was zero this round (all checks offline/local). All local
servers killed and confirmed down.

Spec read verbatim first: `docs/00-decision-log.md` D-0006..D-0009, `docs/backlog.md` B-001, and the
two prior verify reports + `notes-public-fix1.md`.

## Containment / method
- Wrote **only** this report inside the project (file-ownership honored). Ran build_zips.py once
  (it emitted two gitignored `*_INVALID_PLACEHOLDER.zip` into `public/dist/` by design) and
  **deleted them**, restoring `public/dist/` to just `build_zips.py`. No other project writes.
- Temp harness scripts (parity/mock/site drivers, an item fixture) live in the session scratchpad,
  not the project. All checks ran offline or against a local `python -m http.server` (killed).

---

## Prior findings — all RESOLVED

**MAJOR-2 (transparency page self-falsified — fonts/poecdn).** RESOLVED.
- 0 `googleapis`/`gstatic` refs in `index.html` and `how-it-works.html`; both link
  `/assets/fonts.css`; 6 self-hosted woff2 present and serve 200 (`Content-type: text/css` on
  fonts.css). `web.poecdn.com` disclosed as a row in the how-it-works endpoints table.
- Cache numbers render **"community &middot; unverified"** with a neutral (non-green) dot at
  `index.html:1478`; cache note reworded at `core.js:600`. Softened "no tracking" wording present.

**MAJOR-1 (open cache: forgeable signals + zero-cost DoS).** RESOLVED. `node worker.test.mjs` =
**55/55**. Code confirmed: `confidence` DERIVED server-side via `confFromTotal(total_found)`
(client value ignored); `MAX_TIER=1e8` per-tier cap in `num()`; soft per-IP daily write budget
`MAX_WRITES_PER_IP_DAY=600` keyed on `CF-Connecting-IP` (env-overridable); `MAX_BODY_BYTES=262144`
→ **413 before JSON parse**. Site marks cache source `community`, neutral dot.

**MINOR-1 (redirect not re-guarded).** RESOLVED. `_http.py` has `_GuardedRedirectHandler`
(`max_redirections=5`) re-running `_guard_host` per hop via a shared `_OPENER`. **Runtime test:**
redirect hop to `www.pathofexile.com/api/trade/fetch` → `HttpError`.

**MINOR-2 (placeholder ships submittable).** RESOLVED. `build_zips.py` with the placeholder present
→ **real exit code 1** and outputs named `..._INVALID_PLACEHOLDER.zip`. Stale placeholder zips are
gone from `public/dist/` (only `build_zips.py` remains).

**MINOR-3 (.gitignore drops build script).** RESOLVED. No blanket `dist/`; a comment guards against
re-adding it; `*.zip` still ignores artifacts (build_zips.py is tracked).

**pub-functional MINOR-1 (priced_items over-count).** RESOLVED. `response.py:157` `priced_n` uses
`_priced_ninja(r)` (requires a finite chaos tier), so a granted-only gem group no longer inflates
the count.

**pub-functional MINOR-2 (vercel.json at public/ root).** Unchanged owner deploy step (documented
in GOING-PUBLIC Phase 2.2 + notes-public-api §6). Not a regression.

---

## Regression sweep — all green

**API runner vs contract.** `_verify.phase_a()` (offline fixtures, real Vercel `handler`) → all
assertions PASS (rare rows carry trade_url + trade_query, PoB 5L/6L carries links filter, bad input
→ ok:false + error_type). No item lacks a query; zero `/api/trade` in output.

**Server-side pathofexile.com reachability — NONE.** grep for fetch primitives
(`urlopen|urllib.request|requests|http.client|socket|fetch(`) across `public/api` outside
`_http.py` → nothing. Every `pathofexile.com` hit in server code is a comment/guard/`?q=` trade-link
builder / worker `trade_url` whitelist (`startsWith https://www.pathofexile.com/trade`) — no socket
to GGG. **Runtime `_guard_host`:** blocks `www.`/apex/`prod.` pathofexile.com, allows poe.ninja.

**Key-recipe 3-way parity (seeder ↔ core.js ↔ worker).** For a shared item+league
(`"Hardcore  Allflame"`, unicode name, unsorted mods, gem w/ 2 supports): Python `cache_key` ==
JS `bpc.cacheKey` **byte-for-byte** — unique `v1_38bbdeaa5b9f805e8f7e92dc5ed4cfc8`, gem
`v1_a2fe838f9c434400b831797560070ebe`; `worker.validKey` accepts, `kvName` →
`p1:hardcore allflame::…`; `leagueKeyspace` collapses the double space in all three. Separators
(`US=\x1f RS=\x1e GS=\x1d`), `canon`=NFC+trim, and `KEY_VERSION=v1` identical py/js.
(A first-pass Python mismatch was a harness bug — `open()` used the Windows codepage instead of
UTF-8, mojibaking the unicode name; fixed with `encoding='utf-8'`. Not a code defect.)

**Site local load.** `parseWhisper` correct (`35 chaos`→chaos 35; `200 exalted`→chaos null, kept
out of totals). `loadMock` (with `sample.js`) → **26 items, median 14060.2** — identical to the
prior report. Static serve (`:8952`): index.html, `?mock`, how-it-works.html, fonts.css, a woff2,
core.js, config.js, sample.js, stub-build.json all **200**.

**Extension manifest + zips.** `manifest.json`: MV3, v1.0.0, `permissions:["storage"]`,
`host_permissions:["https://www.pathofexile.com/api/trade/*"]`, no tabs/cookies/history/webRequest/
scripting/activeTab, no `<all_urls>`. Content-script match is still the `REPLACE-WITH-YOUR-DOMAIN`
placeholder (expected pre-deploy; build_zips gates on it). Prebuilt zips deliberately absent — owner
regenerates with a real domain per GOING-PUBLIC.

## Reproduce
```
node public/worker/worker.test.mjs                       # 55/55
python -c "import sys;sys.path.insert(0,'public/api');import _verify;_verify.phase_a()"
python public/dist/build_zips.py ; echo $?               # exit 1, _INVALID_PLACEHOLDER names (delete outputs)
# key parity + loadMock + parseWhisper + static-serve: inline python/node harnesses (session scratchpad)
```
Not run (rule): live cache seed, live trade call, `wrangler dev`, real browser paint (owner should
eyeball `index.html?mock` once for the self-hosted-font look).
