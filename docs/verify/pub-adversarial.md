# Public build — adversarial trust / security / honesty review

Scope: `public/` (api = Vercel function, worker = CF Worker, site = static), `extension/`,
`tools/seed_cache.py`, `GOING-PUBLIC.md`, against `docs/backlog.md` B-001 + `docs/00-decision-log.md`
D-0006..D-0008. Method: read every server-side source file; grep for fetch primitives, secrets, and
external hosts; reason about the abuse surface. No pathofexile.com call was made by this review; the
cache seeder was NOT run (not even dry-run); no deploy/store action taken.

Reviewer date: 2026-07-26. Files read (absolute):
`C:\scripts\buildpricechecker-poe1\public\api\**`, `...\public\worker\**`, `...\public\site\**`,
`...\extension\**`, `...\tools\seed_cache.py`, `...\GOING-PUBLIC.md`.

---

## HEADLINE VERDICT

**The one inviolable HOLDS: nothing server-side can reach pathofexile.com.** No `trade.py` /
`pricing.py` is vendored into `public/api/_lib`; the trade-search methods were deliberately not
ported (`querybuild.py` only *builds* `?q=` URL strings, never fetches). Every socket-opening path
in `public/api` funnels through `_lib/_http.py`, whose `_guard_host()` raises on
`pathofexile.com` and any subdomain, and it is invoked inside `_open()` — the sole opener behind both
`get_json` and `get_text`. The Worker is a pure KV store (no outbound fetch at all). The page
(`core.js`) fetches only `API_BASE/api/build` and `WORKER_BASE/cache`; trade links open in the
user's own tab. **No blockers. No committed secrets. No server-side trade call is reachable.**

However, for a launch whose *entire pitch is trust*, there are **2 MAJOR honesty/abuse findings** and
**3 MINOR** items that should be addressed before going public. Details below, hunt-area by hunt-area.

---

## (1) Any server-side path to pathofexile.com — CLEAN (1 minor hardening)

- `public/api/_lib/_http.py` `_BLOCKED_HOSTS=("pathofexile.com",)`; `_guard_host` checks
  `host==bad or host.endswith("."+bad)` → blocks apex + `www.` + `api.` etc. Called in `_open()`,
  used by both `get_json` and `get_text`. **Belt-and-suspenders is real.**
- No fetch primitive exists in `public/api` outside `_http.py` (grep for
  `urlopen|urllib.request|requests|http.client|socket` returned nothing else). `_verify.py` has
  `urllib` but is a dev tool (below).
- `querybuild.py:227` constructs `https://www.pathofexile.com/trade/search/...?q=` as a **clickable
  string** — never fetched. Correct by design (query BUILT here, RUN client-side).
- `currency.py` deleted the parent's trade `exchange` fallback; `engine.py` allowlists PoB paste
  hosts (`pobb.in`/`pastebin.com`/`poe.ninja`) before fetching — no arbitrary-URL SSRF.
- `worker.js` never calls pathofexile.com or poe.ninja (its own header comment claims this and the
  code bears it out — KV only).

**MINOR-1 (redirect hardening).** `_http._open` uses `urllib.request.urlopen`, which **auto-follows
HTTP 3xx redirects without re-running `_guard_host`**. The docstring claims the block is "structurally
impossible at the transport layer" — the mechanism is slightly weaker than the claim: a trusted host
(poe.ninja / a paste host) that 3xx-redirected to `pathofexile.com` would be followed. Practically
unreachable (those hosts don't redirect to the trade API, and only GET is issued), so risk is low,
but the guarantee is stated more absolutely than enforced. Fix: install a custom
`HTTPRedirectHandler` that re-runs `_guard_host` on every hop (and, for the PoB-paste fetch, cap or
disallow redirects to also close internal-redirect SSRF). File:
`C:\scripts\buildpricechecker-poe1\public\api\_lib\_http.py`.

## (2) Manifest over-permission / store red flags — CLEAN (1 minor packaging)

- `extension/manifest.json`: `permissions:["storage"]` only; `host_permissions:
  ["https://www.pathofexile.com/api/trade/*"]`; content-script matches the site origin only. **No**
  `cookies`/`tabs`/`history`/`activeTab`/`<all_urls>`. MV3. Unminified. No remote code
  (`background.js` is local; `credentials:"omit"` → logged-out, per-IP). This is a textbook-minimal
  manifest and matches the trust plan (B-001 item 2) exactly.
- `background.js` `BASE` is fixed to the trade host and `league` is `encodeURIComponent`'d into the
  path — a malicious page cannot swap the host. Content script gates on `ev.source===window` +
  `d.source==="bpc-page"`. Reasonable bridge.

**MINOR-2 (placeholder ships in the artifact).** Production `manifest.json`'s content-script match is
the literal `https://REPLACE-WITH-YOUR-DOMAIN/*`, and the **prebuilt** `public/dist/*.zip` already
embed that placeholder. `build_zips.py` only **prints a warning** (non-blocking) when the placeholder
is present — a hurried run still emits a submittable, broken/likely-rejected zip. It IS documented
(GOING-PUBLIC 1.2), so this is guarded by docs+warning, not enforced. Fix: make `build_zips.py`
**refuse** to build (or name the output `*_INVALID_PLACEHOLDER.zip`) when
`REPLACE-WITH-YOUR-DOMAIN` remains. Files:
`C:\scripts\buildpricechecker-poe1\extension\manifest.json`,
`C:\scripts\buildpricechecker-poe1\public\dist\build_zips.py`.

## (3) Worker abuse surface — bounded, but MAJOR residual

Good: `sanitizeEntry` whitelists fields, nulls non-finite/negative tiers, **server-stamps `ts`**
(client can't backdate), clamps `note`/`trade_url` to 512, caps the record at `MAX_VALUE_BYTES`,
regex-restricts `method`, and **only keeps `trade_url` if it starts with the official trade host**
(blocks arbitrary-URL / `javascript:` injection). KV keys are namespaced `p1:<leagueKeyspace>::<key>`
with `LEAGUE_RE` (letters+spaces) and `KEY_RE` (hex) — **no namespace escape / league crossover**.
`MAX_ENTRIES=60`. The site's cache-read path even **overrides the attacker-supplied `note`** with its
own string, so there is **no stored-XSS via the cache**. All solid.

**MAJOR-1 (open cache: forgeable trust signals + zero-cost DoS).** The cache has **no write
authenticity and no rate limit** — the endpoint is public (URL in `config.js`) and the recipe is
public, so:
- **Poisoning:** anyone can POST a shape-valid record for any computable key. Critically,
  `confidence`, `sample_size`, and `total_found` are **taken from the client**, so a poisoned entry
  can present as `confidence:"high"` with a large sample and **folds into the visitor's total**. The
  numeric tier magnitude is not capped either (any finite ≥0 value stored). Mitigations that DO
  exist: 24h TTL, numeric-only + size-bounded, and the UI labels it "community cache" (the green
  confidence dot, however, is still forgeable). The trusted seeder and an anonymous attacker write on
  equal footing (last-write-wins).
- **DoS of the cache (trivially scriptable):** no per-IP cap → an attacker exhausts the Cloudflare KV
  free-tier **write quota (~1,000 writes/day)** in ≈17 POSTs (60 entries each), after which the
  legitimate seeder's writes fail for the day; the read quota (~100,000/day) is likewise
  exhaustible. **[NOT FROM SOURCE — the 1,000 writes/day & 100,000 reads/day figures are Cloudflare's
  public free-tier limits, not derived from this repo; the ≈17-POST math follows from them.]**

Impact is bounded (cache is best-effort; the site degrades to trade links / whisper-paste), so this
is not a blocker — but on a product whose thesis is trust, a **forgeable "high-confidence" number
that inflates/deflates the headline total** and a **free cache-disable DoS** warrant a fix. Options:
derive `confidence` server-side from `total_found` (ignore client value); cap tier magnitude; add a
light anti-abuse gate (Turnstile / per-IP cap / cheap PoW); and/or visibly mark cache-sourced numbers
as "community, unverified" where they enter the total. File:
`C:\scripts\buildpricechecker-poe1\public\worker\worker.js`.

**NIT:** POST body is fully JSON-parsed (`request.json()`) before the `MAX_ENTRIES` check; bounded by
CF's platform body limit, so low-risk, but the count check happens post-parse.

## (4) Trust-checklist honesty — MAJOR contradiction on the transparency page

- **Never-does list vs manifest reality — ACCURATE.** `index.html` upgrade card (lines 929-936):
  "No login/session cookie/POESESSID" (matches `credentials:"omit"`); "Touches only
  `pathofexile.com/api/trade` and this site — nothing else" (matches `host_permissions` +
  content-script match); "No tabs/history/all-sites access" (matches `permissions:["storage"]`).
- **How-it-works endpoints vs code — accurate for the endpoints it lists**, and the GGG
  not-affiliated disclaimer is present in the upgrade card, the footer (index.html:978), the
  how-it-works callout+footer, meta descriptions, and the extension manifest description. Good.

**MAJOR-2 (the "every server" claim is materially false).** `how-it-works.html` prints a table headed
*"These are every server this site contacts. You can verify them in your browser's Network tab,"*
and both pages assert *"No analytics, no tracking."* But the site loads, at runtime:
- **Google Fonts** — `fonts.googleapis.com` + `fonts.gstatic.com` (index.html:11-13,
  how-it-works.html:6-8). Google receives the visitor's IP + User-Agent + Referer on **every page
  load** — a third-party contact that is **not in the table** and is in tension with "no tracking."
- **`web.poecdn.com`** — 37 refs; item and currency icons are rendered as `<img src>` (core.js
  builds `chaos_img`/`divine_img` and `it.icon`/`s.icon` from the API's poecdn URLs). Another
  third-party server the browser contacts, **not in the table**.

For a launch whose centerpiece is radical transparency, the transparency page omitting two of the
servers it actually contacts is a self-falsifying trust gap. Fix (trivial): self-host the two font
families (removes Google entirely) and either proxy icons or add a poecdn row to the table; and soften
"no tracking" to the truthful "no analytics/cookies we set; fonts+icons load from Google/GGG CDNs."
Files: `C:\scripts\buildpricechecker-poe1\public\site\how-it-works.html`,
`C:\scripts\buildpricechecker-poe1\public\site\index.html`.

## (5) Secrets / PII — CLEAN

- No secrets committed. A repo-wide grep for `api_key|secret|token|password|bearer|authorization|
  BEGIN|AKIA|ghp_|xoxb|POESESSID` over `public/ extension/ tools/` (code/config only) returned
  nothing; the only hits were base-type/stat names inside the bundled `_data/*.json` game data.
- No user-data collection matching the claims: client state is `localStorage` only (keys match the
  how-it-works "what's stored" table); the API receives only the poe.ninja URL / PoB code the user
  pasted (public data, sent to the owner's own function); `credentials:"omit"` in the extension. The
  **shared cache key is a hash of league+item identity and stores no account/character** — matching
  the how-it-works promise ("holds no character name, account, or anything identifying"). Accurate.

## (6) GOING-PUBLIC.md correctness — accurate (1 minor repo-hygiene)

Commands map to the real tree: worker `wrangler.toml` `binding="PRICES"` matches `worker.js`
`env.PRICES`; project `name="poe1-price-cache"` and the `/cache` path match; `config.js` REPLACE_ME
keys match the guide's Quick-Reference table; `seed_cache.py` flags (`--dry-run`/`--from-cache-only`/
`--worker-url`/`-n`/`--delay`) match its argparse; `build_zips.py` path/behaviour match; the
health-check curl's `"calls_pathofexile_com": false` matches `health.py`. The **Vercel nesting caveat
is honestly flagged as ACTION REQUIRED** (Phase 2.2: `copy public\api\vercel.json public\vercel.json`,
Root Directory = `public/`); `vercel.json` `functions`/`includeFiles` resolve correctly under that
root. Dry-run seed hits poe.ninja ladder only (correct).

**MINOR-3 (`.gitignore` drops the extension build script).** `.gitignore` contains `dist/` and
`*.zip`, which excludes **`public/dist/build_zips.py`** — a *source* script the guide tells the owner
to run and part of the "open source, readable in the repo" promise (the repo is store-linked for
transparency). A fresh clone would lack the extension's build tooling (and prebuilt zips, which are
fine to drop as artifacts). The repo isn't initialized yet (`git` not present), so this is
prospective. Fix: add `!public/dist/build_zips.py` (or move the script out of a `dist/` dir). File:
`C:\scripts\buildpricechecker-poe1\.gitignore`.

## Dev tool note (not a finding)

`public/api/_verify.py` ships inside `api/` but is underscore-prefixed (Vercel does not route it) and
is imported by nothing in the bundle; Phase A monkeypatches to fixtures (and even the fake calls
`_guard_host`), Phase B hits **poe.ninja only** and asserts `"/api/trade" not in` the document and
`calls_pathofexile_com is False`. It never calls pathofexile.com. Reads fixtures from `research/data`
which is not in the deployed bundle. Harmless; could be excluded from deploy to shrink surface.

---

## Severity summary

| # | Sev | Finding | File |
|---|-----|---------|------|
| MAJOR-2 | major | Transparency page's "every server this site contacts" + "no tracking" omit Google Fonts + web.poecdn.com (both loaded at runtime) | public/site/how-it-works.html, index.html |
| MAJOR-1 | major | Open cache: client-supplied `confidence`/`sample_size` make poison masquerade as high-confidence in totals; no rate limit → ≈17 POSTs exhaust CF KV free write quota (cache DoS) | public/worker/worker.js |
| MINOR-1 | minor | `_guard_host` not re-applied on urllib auto-followed redirects; claim "structurally impossible" > mechanism | public/api/_lib/_http.py |
| MINOR-2 | minor | `REPLACE-WITH-YOUR-DOMAIN` ships in manifest + prebuilt zips; `build_zips.py` only warns, doesn't block | extension/manifest.json, public/dist/build_zips.py |
| MINOR-3 | minor | `.gitignore` `dist/`+`*.zip` excludes source script `public/dist/build_zips.py` from the (store-linked) repo | .gitignore |

**Inviolable (no server-side pathofexile.com call): PASS.** Secrets/PII: PASS. Manifest minimality:
PASS. GOING-PUBLIC accuracy: PASS. The two MAJORs are trust/honesty, not the core invariant — fixable
in an afternoon, and worth fixing before a trust-branded public launch.
