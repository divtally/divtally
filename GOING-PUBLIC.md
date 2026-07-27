# GOING PUBLIC — owner walkthrough (DivTally)

> **The assistant walks you through these phases in chat; this file is the durable copy.**
> If chat context is lost (auto-compaction), this file is the source of truth for every manual
> step. It is grounded only in what actually got built for B-001 / D-0008 (see
> `docs/00-decision-log.md`, `docs/backlog.md`, and the four `docs/notes-public-*.md`).

## The one hard rule that shaped everything (read once)
Nothing on a server ever calls **pathofexile.com**. The public site and its serverless function
read **poe.ninja** only; the community-cache Worker is a dumb key/value store. Every real trade
call happens on a **user's own machine/IP** — a trade link *they* click, the browser **extension**
running for them, or **your own PC** running the seeder. This is why the architecture is split the
way it is; do not "optimize" a server-side trade call back in.

## What you are deploying (four pieces + one scheduled job)
| Piece | Folder | Host | Cost |
|---|---|---|---|
| Static site (stash skin, public mode) | `public/site/` | Cloudflare Pages | free |
| Serverless pricing function (poe.ninja only) | `public/api/` | Vercel Hobby | free* |
| Community price-cache Worker + KV | `public/worker/` | Cloudflare Workers | free |
| DivTally browser extension (2 store zips prebuilt) | `extension/` → `public/dist/*.zip` | Chrome / Edge / Firefox stores | **$5 Chrome one-time**, Edge & Firefox free |
| Owner-PC cache seeder | `tools/seed_cache.py` | Windows Task Scheduler | free |

\* Vercel **Hobby is non-commercial only**. If this tool is ever monetized/work-related, move the
function to Vercel Pro ($20/mo) or AWS Lambda (code is identical) — see Phase 5.

**Money summary:** the whole thing runs **$0** except the **one-time $5 Chrome Web Store** dev
fee (skip it and ship Edge+Firefox for free), and the **~$10/yr `divtally.com` domain** — now
registered up front in Phase 1.0, because the store listings link to it.

## Prerequisites (all free accounts; tools you likely already have)
- **Cloudflare account** — https://dash.cloudflare.com (no credit card). Hosts the site + Worker.
- **Vercel account** — https://vercel.com (sign in with GitHub). Runs the Python function.
- **GitHub account** — optional but recommended (enables push-to-deploy).
- **Node.js + npm** — `node -v` / `npm -v` (provides `npx wrangler` and the Vercel CLI).
- **Python 3.13 + requests** — you already run the local app; the seeder reuses it.
- **Chrome or Edge** — to load/test the extension. (Firefox optional.)
- Browser store dev accounts (Phase 1).

## Your public origin is already decided — DivTally
The public brand **is** the domain: **`https://divtally.com`** (custom domain, registered in
Phase 1.0), with **`divtally.pages.dev`** as the Cloudflare Pages origin and staging fallback.
Both — plus `www.divtally.com` — are **already baked into the extension**
(`extension/manifest.json` content-script matches) and into this guide, so there is nothing to
pick. This guide uses **`divtally`** as the Pages/Vercel project name and `https://divtally.com`
as the canonical site URL throughout.

---

# PHASE 1 — Domain + accounts + store submissions FIRST
Store review queues take **days**, so submit the extension early — before the site is even live —
so approval lands when you're ready. The site is fully usable without the extension, so this
parallelizes cleanly. **Register the domain before you submit**, because the store listings and the
extension both carry `divtally.com`.

## 1.0 Register `divtally.com` (do this FIRST)
The name **is** the domain, and the store listings link to it, so register it before submitting
anything. It was verified unregistered on 2026-07-27 (Verisign RDAP).
1. **Cloudflare Registrar** (recommended — at-cost, ~$10/yr, no markup, free WHOIS privacy):
   https://dash.cloudflare.com → **Domain Registration** → **Register Domain** → search
   `divtally.com` → add to cart → complete purchase. Registering here also makes it a Cloudflare
   zone, so attaching it to Pages later (Phase 5.1) is CNAME + free SSL with zero DNS fiddling.
2. **Fallback — Porkbun** (https://porkbun.com) if Cloudflare Registrar is unavailable for the TLD
   or you prefer it: register `divtally.com` there, then in Phase 5.1 attach it to Pages via a
   CNAME (the guide covers the external-registrar path).
> Grab `www.divtally.com` handling too (it's the same registration; you'll point both at Pages in
> Phase 5.1). The raw `divtally.pages.dev` origin keeps working as a fallback either way.

## 1.1 Create the three browser dev accounts
1. **Chrome Web Store** — go to https://chrome.google.com/webstore/devconsole → sign in with a
   Google account → accept the developer agreement → **pay the one-time $5 USD registration fee**
   (this is the only required cost of the whole launch).
2. **Microsoft Edge Add-ons** — go to https://partner.microsoft.com/dashboard/microsoftedge →
   register as an Edge extension developer (**free**).
3. **Firefox AMO** — go to https://addons.mozilla.org/developers/ → sign in with a Firefox
   account → agree to the distribution agreement (**free**).

## 1.2 Build the store zips (origins already baked)
`public/dist/` ships only the build **script**; the zips are generated. The DivTally origins
(`divtally.com`, `www.divtally.com`, `divtally.pages.dev`) are **already baked into
`extension/manifest.json`**, so there is nothing to edit — just build both **unminified** store
artifacts:
```powershell
python public\dist\build_zips.py
```
It reads the version from `manifest.json`, copies every source file verbatim, and writes:
- `public\dist\divtally-extension-chrome-edge-1.1.0.zip`  (Chrome **and** Edge)
- `public\dist\divtally-extension-firefox-1.1.0.zip`      (Firefox AMO)

If the manifest's content-script domain is ever reverted to a bare placeholder, the script
**REFUSES**: it names the outputs `..._INVALID_PLACEHOLDER.zip` and exits non-zero, so a hurried
run can never emit a submittable-looking zip. `manifest.dev.json` and `generate_icons.py` are
excluded from the zips by design.

## 1.3 Submit to the Chrome Web Store
1. https://chrome.google.com/webstore/devconsole → **Add new item**.
2. Upload `public\dist\divtally-extension-chrome-edge-1.1.0.zip`.
3. Fill the listing from `docs/store-listings.md` (all copy is pre-written):
   - **Title**, **Short summary**, **Full description** — paste verbatim.
   - Replace `<REPO-URL-PLACEHOLDER>` (your repo). The site URL is already `https://divtally.com` in the copy.
   - **Category:** Tools. **Store icon:** `extension/icons/icon128.png`.
   - **Screenshots** (1280×800 or 640×400): capture per the checklist in `store-listings.md §Screenshots`.
   - **Permission justifications:** paste the `storage`, host-permission, and content-script blurbs
     from `store-listings.md` into each per-permission "why" field.
   - **Privacy practices:** select **"does not collect user data"**; paste the plain-language
     statement from `store-listings.md §Privacy disclosure`.
4. Submit for review.

## 1.4 Submit to Microsoft Edge Add-ons
1. https://partner.microsoft.com/dashboard/microsoftedge → **Create new extension**.
2. Upload the **same** `divtally-extension-chrome-edge-1.1.0.zip`.
3. Reuse the identical listing copy, category (**Productivity**), permission justifications, and
   privacy answers from `docs/store-listings.md`. Submit.

## 1.5 Submit to Firefox AMO
1. https://addons.mozilla.org/developers/addon/submit/ → choose **On this site** (listed).
2. Upload `public\dist\divtally-extension-firefox-1.1.0.zip` (this one carries the `gecko.id` +
   `background.scripts` fallback the Firefox zip build adds).
3. Category **Other** (tags: `path-of-exile`, `poe`, `trade`); paste the same description +
   privacy statement. Submit.

> Save the three listing URLs when each is approved — they go into `config.js` (`STORE_URLS`) and a
> Pages redeploy in Phase 2/5. The site works fine with the placeholders until then.

---

# PHASE 2 — Deploys
Order matters: the Worker and the function are independent; deploy them first so you have their
URLs, then fill `config.js`, then deploy the site.

## 2.1 Deploy the community-cache Worker (Cloudflare)
```powershell
cd C:\scripts\buildpricechecker-poe1\public\worker
npx wrangler login                          # opens a browser; authorize
npx wrangler kv namespace create PRICES     # prints:  id = "xxxxxxxx...."
```
1. Copy the printed **`id`** and paste it into `public\worker\wrangler.toml`, replacing
   `REPLACE_ME` in the `[[kv_namespaces]]` block (`binding = "PRICES"` must stay exactly that).
2. (Optional, only if you'll run `wrangler dev`) also run
   `npx wrangler kv namespace create PRICES --preview` and paste its id into `preview_id`.
3. Deploy:
   ```powershell
   npx wrangler deploy
   ```
   Your endpoint prints as **`https://divtally-price-cache.<your-subdomain>.workers.dev`**. The cache
   path is `/cache`. **Write this URL down** — it's `WORKER_BASE` in `config.js` and `--worker-url`
   for the seeder.
   - *(Optional)* The cache enforces a soft **per-IP daily write budget** (default 600 entries) so
     one script can't drain the KV free-tier write quota. If you seed several times a day from one
     IP and see `throttled`, raise it: uncomment `[vars]` `MAX_WRITES_PER_IP_DAY` in
     `wrangler.toml` (or `npx wrangler deploy --var MAX_WRITES_PER_IP_DAY:1200`).
4. Sanity check (offline logic was already proven — 55/55 tests; this just confirms it's live):
   ```powershell
   curl "https://divtally-price-cache.<sub>.workers.dev/cache?league=Standard&keys=v1_0000000000000000"
   ```
   Expect `{}` (empty — nothing seeded yet), **not** an error page.

## 2.2 Deploy the pricing function (Vercel)
**ACTION REQUIRED before first deploy** — Vercel reads `vercel.json` from the project **Root
Directory**, and file-ownership during the build put it one level too deep. Copy it up and set the
root to `public/`:
```powershell
cd C:\scripts\buildpricechecker-poe1
copy public\api\vercel.json public\vercel.json
```
Then deploy:
```powershell
npm i -g vercel            # first time only
cd C:\scripts\buildpricechecker-poe1\public
vercel                     # answer prompts (see below) -> prints a PREVIEW url
```
Prompt answers: **Set up and deploy = Yes**; scope = your account; **Link to existing = No**;
project name = `divtally` (or your choice); **Root Directory = ./** (you are already inside
`public/`, which must be the root so functions resolve as `api/build.py`).
1. Test the preview URL it printed:
   ```powershell
   curl "https://<preview-url>/api/health"
   ```
   Expect JSON with `"calls_pathofexile_com": false`. (`health` is offline; it validates the data
   bundle and never hits the network.)
2. Promote to the stable URL:
   ```powershell
   vercel --prod
   ```
   Your function is then at **`https://divtally.vercel.app`** (paths `/api/build`, `/api/health`).
   **Write this down** — it's `API_BASE` in `config.js`.
3. One real end-to-end call (this hits **poe.ninja only** — allowed; a handful of calls is fine):
   ```powershell
   curl "https://divtally.vercel.app/api/build?url=https://poe.ninja/poe1/builds/character/<acct>/<char>"
   ```
   Expect HTTP 200 with a build document. Confirm it contains **no** `/api/trade` strings — only
   browser `/trade/search` links (the invariant).

## 2.3 Deploy the static site (Cloudflare Pages)
Deploy once to **claim the `divtally.pages.dev` origin** (the Pages project name must be `divtally`
so it matches the `divtally.pages.dev` match already baked into the extension), then you'll fill
config and redeploy. You can attach the custom domain `divtally.com` now or in Phase 5.1.

**Fastest path — Direct Upload (no Git):**
1. https://dash.cloudflare.com → **Workers & Pages** (sidebar) → **Create application** → **Pages**
   tab → **Upload assets**.
2. **Project name** = `divtally` (this is what makes `divtally.pages.dev` — must match the origin
   already baked into the extension).
3. Drag the **`public\site`** folder (the one containing `index.html`) into the drop zone → **Deploy site**.
4. Open the printed `https://divtally.pages.dev` — it should render the stash skin. Rares won't
   price yet (config still has placeholders).

> Gotchas: a Direct-Upload project can't later convert to Git (pick deliberately). For the Git path
> instead: push the repo, Pages → Connect to Git, **Framework preset = None**, **Build command =
> BLANK**, **Build output directory = `public/site`**, Production branch = main.

## 2.4 Fill in `config.js` with the real URLs, then redeploy the site
Edit **`public\site\config.js`** — the **only** file you edit in the site — replacing every
`REPLACE_ME`:
```js
API_BASE:    "https://divtally.vercel.app",                        // from 2.2
WORKER_BASE: "https://divtally-price-cache.<sub>.workers.dev",          // from 2.1  ("" disables cache)
STORE_URLS: {
  chrome:  "https://chromewebstore.google.com/detail/<id>",         // from Phase 1 once approved
  edge:    "https://microsoftedge.microsoft.com/addons/detail/<id>",
  firefox: "https://addons.mozilla.org/firefox/addon/<slug>/"
},
REPO_URL: "https://github.com/divtally/divtally"
```
Store URLs can stay as placeholders until the stores approve (Phase 1) — just redeploy the site
again when they land. Then push the update:
- **Direct Upload:** open the Pages project → **Deployments** → **Create a new deployment** →
  **Production** → drag the updated `public\site` folder → **Deploy**.
- **Git path:** commit + push; Pages auto-redeploys.

---

# PHASE 3 — Wiring checks on the real origin
Do these against the **live** `divtally.pages.dev` (not localhost).

## 3.1 Mock render (no backend)
Open `https://divtally.pages.dev/index.html?mock`. The stash skin should render a full demo build
(sample snapshot) with no network calls to your API. Eyeball layout/animation — this is the render
the local tests couldn't paint.

## 3.2 One real build end-to-end
Open `https://divtally.pages.dev/`, paste a real **poe.ninja PoE1 build URL** (or a PoB code),
Appraise. Expect: gems/currency/uniques priced from poe.ninja; rares showing a red/orange "needs
pricing" cue and appearing in the **"Rares to price"** panel with an *open search ↗* link +
whisper-paste box. Totals read as a **floor** (poe.ninja-priced items only). This is the first true
poe.ninja → document → render pass.

## 3.3 Whisper-paste path
On a rare row, paste a GGG copy-whisper (`…listed for 35 chaos…`) or a bare `35c` / `2 div` into
its input. The price should fold into the total and **persist across reload** (localStorage).

## 3.4 Community-cache read-through
If `WORKER_BASE` is set, a freshly loaded popular build should auto-fill any rares the seeder has
already cached (`source:"cache"`). Nothing to price manually yet until you seed (Phase 4) — this
just confirms the site is reaching the Worker (check the browser Network tab for a `200` on
`/cache?...`).

## 3.5 Extension bridge test on the real origin (`/v/_exttest`-style)
The public site itself **is** the bridge target (the old `/v/_exttest` harness was the local app).
To test the live bridge before the store approves, side-load with the **dev** manifest:
1. In a **scratch copy** of `extension\`, rename `manifest.json` aside and rename
   `manifest.dev.json` → `manifest.json` (the dev manifest already matches `*.pages.dev`).
2. Chrome/Edge: open `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select
   the scratch folder. (Firefox: `about:debugging` → **This Firefox** → **Load Temporary Add-on** →
   pick the `manifest.json` file.)
3. Open `https://divtally.pages.dev/`. The top-nav **bridge badge** should flip to **"bridge
   active"** (the calm upgrade card hides once the bridge is detected).
4. Load a build with rares → click **Autoscan (N)** (or a per-row ⚡). The extension prices each
   rare **from your own IP** and folds the numbers in (`source:"trade"`), and POSTs them back to the
   community cache for the next visitor.
5. **Watch for HTTP 403 / empty results** in the extension's service-worker console — that's the one
   known unknown (the trade API sometimes wants a Referer a plain fetch can't set). If it happens,
   tell the assistant: the fix is a `declarativeNetRequest` Referer rule. If prices come back, ship.
> The **popup tester** (extension toolbar icon → paste a `?q=` trade link → **Price it**) is an even
> faster smoke test that search/fetch + rate limiting work from your IP, no site needed.

---

# PHASE 4 — Seed the community cache (owner PC, scheduled)
`tools/seed_cache.py` runs on **your** machine, prices the top-N popular poe.ninja builds with the
existing local engine (same rate limiter + disk cache as normal personal use — the **only**
trade-touching component in the whole system), and POSTs the results to the Worker so visitors with
nothing installed see popular builds fully priced.

## 4.1 Dry-run first (zero trade calls, zero risk)
```powershell
python C:\scripts\buildpricechecker-poe1\tools\seed_cache.py --dry-run -n 5
```
Lists the 5 builds it *would* price (hits poe.ninja's ladder only — prices nothing, POSTs nothing).
Confirm it resolves the league and lists sane build names.

## 4.2 One real seed (drives the trade API on your IP — run manually once)
```powershell
python C:\scripts\buildpricechecker-poe1\tools\seed_cache.py --worker-url https://divtally-price-cache.<sub>.workers.dev/cache -n 15
```
`--worker-url` accepts the base or the full `/cache`. `--delay` (default 3s) paces builds. This is
the same footprint as you pricing 15 builds yourself in the app. Afterward, reload a seeded build on
the live site with **no extension** and confirm its rares now show `source:"cache"` prices.

## 4.3 Schedule it daily (Windows Task Scheduler)
**CLI (run PowerShell as admin), daily at 06:00:**
```powershell
schtasks /Create /TN "DivTally Price Cache Seed" /SC DAILY /ST 06:00 /F ^
  /TR "python C:\scripts\buildpricechecker-poe1\tools\seed_cache.py --worker-url https://divtally-price-cache.<sub>.workers.dev/cache -n 15"
```
(Replace `<sub>`. `python` must be on PATH — if not, use its full path, e.g.
`C:\Python313\python.exe`. The script finds the repo itself via its own location, so the working
directory doesn't matter.)

**GUI equivalent** (if you prefer clicks):
1. Open **Task Scheduler** → **Create Task…**
2. **General:** name `DivTally Price Cache Seed`; **Run whether user is logged on or not**.
3. **Triggers:** New → **Daily**, start **06:00**, recur every **1 day**.
4. **Actions:** New → **Start a program** → Program/script = `python` (or full path) → Add
   arguments = `C:\scripts\buildpricechecker-poe1\tools\seed_cache.py --worker-url https://divtally-price-cache.<sub>.workers.dev/cache -n 15`.
5. **Conditions:** untick "Start only on AC power" if on a laptop. **OK**.
6. Right-click the task → **Run** once to verify, then check a seeded build on the live site.

> Keep N modest (10–15). The cache TTL is 24h by design, so a daily reseed keeps popular builds warm
> without any burst. Never point the seeder at a machine that isn't yours.

---

# PHASE 5 — Attach the custom domain + launch
## 5.1 Attach `divtally.com` to Cloudflare Pages
You already **registered** `divtally.com` back in Phase 1.0; now point it at your Pages site (this
can also be done at the tail end of Phase 2, once the Pages project exists).
1. Cloudflare Pages project → **Custom domains** → **Set up a domain** → enter `divtally.com`
   (repeat for `www.divtally.com`) → **Activate**. If you registered via **Cloudflare Registrar**
   it is already a Cloudflare zone, so CNAME + free SSL are automatic; an **external registrar**
   (e.g. Porkbun) needs a CNAME (for `www`) or a nameserver move (for the apex).
2. The extension already ships the `divtally.com` / `www.divtally.com` / `divtally.pages.dev`
   matches, so **no manifest edit or extension re-submission is needed**. Just confirm `config.js`
   points at your final origins and redeploy Pages.

## 5.2 Launch
1. Confirm the three store listings are approved and their URLs are in `config.js` `STORE_URLS`;
   redeploy Pages so the calm upgrade card links to real stores.
2. Post the community announcement. The ready-to-edit copy is in **`docs/launch-post.md`** — fill
   its placeholders (site URL, repo URL, store links) and post to the PoE forums / r/pathofexile /
   Discord. It doubles as the trust pitch (it's the same transparency story as `/how-it-works`).

---

## Quick reference — the placeholders you must replace everywhere
| Placeholder | Where | Becomes |
|---|---|---|
| `REPLACE_ME_API_BASE` | `public/site/config.js` | Vercel URL (2.2) |
| `REPLACE_ME_WORKER_BASE` | `public/site/config.js` | Worker URL (2.1) |
| `REPLACE_ME_*_STORE_URL` | `public/site/config.js` | store listing URLs (Phase 1) |
| `REPLACE_ME_REPO_URL` | `public/site/config.js` | your public repo |
| `REPLACE_ME` (KV id) | `public/worker/wrangler.toml` | `kv namespace create` output (2.1) |
| `<REPO-URL-PLACEHOLDER>` | store listings | your public repo (Phase 1) |
| `copy public\api\vercel.json public\vercel.json` | Vercel root | (2.2, do before deploy) |

> The extension's content-script domains and the store-listing site URL are **already baked to
> `divtally.com` / `divtally.pages.dev`** — no placeholder to replace there.

## Verification already done for you (so you know what's solid vs. owner-test)
- **api:** 41-item live poe.ninja build in ~1.6–2.2s, **zero** pathofexile.com calls; offline
  contract suite green (`docs/notes-public-api.md §7`).
- **worker:** 45/45 offline tests (validators + KV round-trip + league isolation).
- **site:** 74/74 offline core tests (whisper-paste, cache-key parity, bridge protocol). **Not** yet
  painted in a real browser or run against a live API — that's Phase 3, your rung.
- **extension:** manifests valid, JS `--check` clean, both zips build & verify; wire protocol matches
  the shipped content script byte-for-byte. **Not** yet run against a live trade call — Phase 3.5.
- **seeder:** dry-run + from-cache-only + cross-parity all green offline. A **live seed was never
  run** (by rule) — Phase 4.2 is its first.
