# Public build — trust fix round 1 (fixes pub-adversarial + pub-functional findings)

Fixes every blocker/major/minor from `docs/verify/pub-adversarial.md` and `docs/verify/pub-functional.md`
(there were no blockers). Spec of record: `docs/00-decision-log.md` D-0006..D-0009, `docs/backlog.md`
B-001, `docs/public-contract.md`, `docs/notes-public-worker.md`. Containment honored (all edits inside
`C:\scripts\buildpricechecker-poe1`); the ABSOLUTE rule held throughout — nothing server-side calls
pathofexile.com, no live seed was run, and the guarded HTTP opener was re-verified to block it.

---

## MAJOR-2 — Transparency page no longer self-falsifies (fonts + poecdn)

**Problem:** how-it-works.html claimed "these are every server this site contacts" + "no analytics,
no tracking", but the pages loaded Google Fonts (`fonts.googleapis.com` / `fonts.gstatic.com`) and
item icons from `web.poecdn.com` — neither disclosed.

**Fonts → self-hosted (removes Google entirely).** Downloaded the latin + latin-ext woff2 subsets for
the exact families/weights the site used (Cormorant Garamond 400/500/600 normal + 500 italic;
Marcellus 400) into `public/site/assets/fonts/` (6 files, ~139 KB) and generated
`public/site/assets/fonts.css` with local `@font-face` rules. Removed the three Google `<link>`s from
`index.html` (was 11-13) and `how-it-works.html` (was 6-8); both now `<link rel="stylesheet"
href="/assets/fonts.css">`. (Regenerator script: `scratchpad/fetch_fonts.py`. Note: Google serves
Cormorant 400/500/600 normal from one physical file — all three @font-face blocks reference it, same
as Google's own CSS.)

**poecdn → disclosed (icons are GGG's public image CDN, loaded client-side by `<img>`).** Added a row
to the how-it-works endpoints table: `GET web.poecdn.com/… (images)` → "GGG's public image CDN — your
browser, pictures only". Proxying was rejected (adds server cost; icons are the least-sensitive data
and are GGG's own public CDN) — disclosure is the honest, correct fix, and the table's "every server"
claim is now true.

**Wording softened to truthful.** "No account, no login, no cookies, no analytics, no tracking." →
"…no cookies **we set** — no analytics, no ad/tracking pixels, no third-party scripts. The only
third-party server your browser touches on a normal page load is GGG's image CDN (web.poecdn.com) for
item pictures; it sets nothing…". Post-table paragraph now notes icons come from poecdn and fonts are
served from this site. (The only "no tracking"-style claim was on how-it-works:132; index.html:932 is
about the extension and was already accurate.)

Files: `public/site/how-it-works.html`, `public/site/index.html`, `public/site/assets/fonts.css` (new),
`public/site/assets/fonts/*.woff2` (new).

---

## MAJOR-1 — Community cache: forgeable trust signals + zero-cost DoS

The cache is an **open** store — the extension POSTs results back (B-001), so writes cannot be
secret-gated; a shared-secret would break the extension path. Fix = derive/ignore forgeable fields +
raise the abuse bar + tell the truth in the UI.

**Worker (`public/worker/worker.js`):**
- **`confidence` derived server-side from `total_found`** (`≥5 high, ≥2 medium, else low`); the
  client's `confidence` is ignored — a poisoned entry can no longer forge a "high" signal independent
  of its sample. (Matches contract §3 + `core.js confFromTotal`.) Removed the now-dead `CONFIDENCE`
  set.
- **Tier magnitude capped** at `LIMITS.MAX_TIER = 1e8` (no single PoE1 item approaches 100M chaos);
  `num()` nulls anything above it → blocks absurd inflation / overflow. A sole over-cap tier ⇒ record
  rejected.
- **Soft per-IP daily write budget** (`LIMITS.MAX_WRITES_PER_IP_DAY = 600`, override via the
  `MAX_WRITES_PER_IP_DAY` Worker var): a day-bucketed TTL'd KV counter keyed on `CF-Connecting-IP`.
  Stops one scripted client from draining the KV free-tier write quota in ~17 POSTs (the flagged DoS).
  Sized to admit one owner-seeder run (~350 entries) with headroom. POST over budget →
  `{ok:true,stored:0,rejected:N,throttled:true}`. A **distributed** flood is still possible — inherent
  to a keyless open cache on the free tier; the cache is best-effort and the site degrades to trade
  links / whisper-paste, so this is a bar-raiser, not a wall.
  **[NOT FROM SOURCE — Cloudflare's ~1,000 writes/day & ~100,000 reads/day free-tier limits are
  Cloudflare's public figures, not from this repo; the ~17-POST math follows from them.]**
- **Body guard:** POST with `Content-Length > MAX_BODY_BYTES` (256 KiB) → `413` before JSON parse
  (addresses the "count check happens post-parse" NIT).

**Site UI honesty (`index.html` + `core.js`):** cache-sourced prices (`source==='cache'`) now render as
**"community · unverified"** with a neutral grey dot in the tooltip — never the green confidence dot a
verified poe.ninja price gets (that dot was the forgeable signal). The manual-panel source label is
`community` (was `cache`), and the cache note is now "Community-submitted price — not verified by this
site. Confirm via the trade link." how-it-works "what's stored" section rewritten to explain the cache
is open/untrusted and how the hardening works.

**Tests:** `worker.test.mjs` 45 → **55** (added: confidence-derivation ignores client value; tier cap
kept/nulled/rejected; per-IP budget throttle + budget-is-per-IP-across-leagues + default admits a
normal POST; 413 body guard). All green.

Files: `public/worker/worker.js`, `public/worker/worker.test.mjs`, `public/worker/wrangler.toml`
(documented optional `[vars]`), `public/site/index.html`, `public/site/assets/core.js`,
`public/site/how-it-works.html`.

---

## Minors

- **pub-adversarial MINOR-1 — redirect guard (`public/api/_lib/_http.py`).** `urlopen` auto-followed
  3xx without re-checking the host. Added `_GuardedRedirectHandler` (re-runs `_guard_host` on every
  hop, `max_redirections=5`) via a shared `_OPENER`; `_open()` uses it. The "structurally impossible"
  claim now holds on redirects too. Verified: a redirect to `www.pathofexile.com/api/trade` raises
  `HttpError`; poe.ninja still allowed.
- **pub-adversarial MINOR-2 — placeholder zips (`public/dist/build_zips.py`).** Now REFUSES when the
  manifest still has `REPLACE-WITH-YOUR-DOMAIN`: outputs are named `..._INVALID_PLACEHOLDER.zip` and
  the script exits non-zero, so a hurried run can't emit a submittable-looking zip. Deleted the two
  stale placeholder-embedding zips from `public/dist/` (they're gitignored build artifacts; the owner
  regenerates with a real domain per GOING-PUBLIC 1.2, now reworded).
- **pub-adversarial MINOR-3 — `.gitignore`.** Removed the blanket `dist/` (which had excluded the
  source script `public/dist/build_zips.py` from the store-linked repo); `*.zip` still ignores the
  artifacts. Added a comment so no one re-adds `dist/`.
- **pub-functional MINOR-1 — `priced_items` count (`public/api/_lib/response.py`).** `priced_n` now
  requires a finite chaos tier (`_priced_ninja`), not just `source=='poe.ninja'`, so a granted-only
  gem group (source poe.ninja, all tiers null) no longer inflates the count. Verified: ascii fixture
  `priced` 6 → 5; totals were already correct.
- **pub-functional MINOR-2 — `vercel.json` at `public/` root.** An owner deploy step already flagged
  ACTION REQUIRED in `notes-public-api.md §6` + GOING-PUBLIC Phase 2.2. No code change.

---

## Checks run (offline; no pathofexile.com, no live seed)

- `python tests.py` → **All self-tests passed** (local bpc engine; unaffected, confirmed green).
- `node public/worker/worker.test.mjs` → **55 passed, 0 failed.**
- `_http` guard smoke → opener builds; blocks apex/www/sub `pathofexile.com`; allows poe.ninja;
  redirect hop to trade host → blocked.
- api `_verify.phase_a()` (offline fixtures) → **phase_a OK**; ascii `priced=5` (was 6).
- `node --check` on core.js + both HTML pages' inline scripts → parse clean.
- Static serve (`:8961`) → `/`, `/how-it-works.html`, `/assets/fonts.css`, woff2 files, core.js,
  config.js all **200**; 0 googleapis/gstatic refs in either page; fonts.css link present; poecdn
  row + "community · unverified" + softened wording present.
- `build_zips.py` → refuses with placeholder (exit 1, `_INVALID_PLACEHOLDER` names); artifacts removed.

Not run (out of scope / rule): live cache seed (drives trade), `wrangler dev` (needs login/network),
a real browser paint (owner should eyeball `index.html?mock` once for the self-hosted-font look).
