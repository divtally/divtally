# Notes - DivTally brand sweep (D-0010)

Date: 2026-07-27. Swept the public name **DivTally** through the public-facing deliverables per
decision-log D-0010. Canonical origin `https://divtally.com`; Pages/staging origin
`divtally.pages.dev`; production content-script matches = `divtally.com` + `www.divtally.com` +
`divtally.pages.dev` (localhost stays in the dev manifest only). Local dev app keeps its repo
identity (`bpc` package, `buildpricechecker-poe1` repo, `bpc-trade-bridge@buildpricechecker`
gecko id, `bpc_*` localStorage keys, `bpc-page`/`bpc-ext` wire protocol) - all left untouched.

## Per-file changes

### extension/manifest.json
- `name`: "PoE1 Build Price Checker - Trade Bridge" -> **"DivTally - Trade Bridge"**.
- `description`: reworded to "Prices rares/uniques for DivTally ..."; not-affiliated line kept verbatim.
- `action.default_title`: "PoE1 Trade Bridge" -> "DivTally Trade Bridge".
- `content_scripts[0].matches`: `["https://REPLACE-WITH-YOUR-DOMAIN/*"]` ->
  `["https://divtally.com/*", "https://www.divtally.com/*", "https://divtally.pages.dev/*"]`.
- gecko id unchanged (repo identity).

### extension/manifest.dev.json
- `name` -> "DivTally - Trade Bridge (DEV)"; `default_title` -> "DivTally Trade Bridge (DEV)".
- matches: kept localhost/127.0.0.1 + `*.pages.dev` + `*.vercel.app`; the lone
  `https://REPLACE-WITH-YOUR-DOMAIN/*` placeholder replaced with `divtally.com` + `www.divtally.com`
  (the custom domain isn't covered by the `*.pages.dev` wildcard). Placeholder token now gone.

### extension/README.md  (shipped inside the store zips)
- Title + intro rebranded to DivTally.
- manifest.json bullet: "placeholder ... REPLACE-WITH-YOUR-DOMAIN" -> "DivTally production matches
  already baked in (divtally.com / www / divtally.pages.dev)"; "no `*.pages.dev`" -> "no wildcard hosts".
- "Adding origins" (production): placeholder-replace instruction -> "origins already set; edit only
  if the origin ever changes".
- build-zips line: "prints a loud warning" -> "refuses (non-zero exit)" (matches current script behavior).

### docs/store-listings.md
- Doc title -> "DivTally: Trade Bridge"; header note now says site URL is baked to `https://divtally.com`
  and only `<REPO-URL-PLACEHOLDER>` remains (repo not published yet - kept and clearly marked).
- Store **Title** field -> "DivTally - Trade Bridge".
- **Short summary** (<=132): now leads with the one-liner - "DivTally - what does that Path of Exile
  build cost? Prices rares & uniques from your own browser & IP. Logged-out, open source." (127 chars).
- **Full description** now leads with the one-liner "DivTally - what does that Path of Exile build
  cost?"; all "Build Price Checker" website/site/domain references -> DivTally; `<SITE-URL-PLACEHOLDER>/how-it-works`
  -> `https://divtally.com/how-it-works`; `<REPO-URL-PLACEHOLDER>` kept.
- Permission justification for the content-script match: `https://<your-domain>/*` -> the three baked
  divtally origins; blurb rebranded.
- Privacy disclosure + screenshots checklist: "Build Price Checker" -> DivTally.
- Submission-sequence note: reflects site URL + manifest domains already baked; only repo placeholder left.

### docs/launch-post.md
- Retitled "[Tool] DivTally - ..."; intro line rebranded.
- Placeholder legend: dropped `<SITE-URL>` (now fixed to `https://divtally.com`); kept repo + store link placeholders.
- Body `<SITE-URL>` and `<SITE-URL>/how-it-works` + Discord venue trim -> `https://divtally.com`.

### GOING-PUBLIC.md
- H1 parenthetical -> "(DivTally)"; money summary: "optional custom domain" -> "~$10/yr divtally.com
  domain, registered in Phase 1.0".
- "Decide this ONE thing first" section rewritten -> "Your public origin is already decided - DivTally"
  (divtally.com canonical, divtally.pages.dev fallback, all baked).
- **NEW Phase 1.0** "Register `divtally.com` (do this FIRST)": Cloudflare Registrar (~$10/yr at-cost;
  Dashboard -> Domain Registration -> Register Domain) with a **Porkbun fallback** note; states the
  Pages custom-domain **attach** happens later (Phase 5.1). Phase 1 heading now "Domain + accounts +
  store submissions FIRST".
- **Step 1.2** reduced: manifest is PRE-BAKED with the divtally origins, so the owner just runs
  `python public\dist\build_zips.py` (no manifest edit). Guard behavior described without the literal
  placeholder token.
- Step 1.3 placeholder note -> only `<REPO-URL-PLACEHOLDER>`; site URL already `https://divtally.com`.
- All running-example URLs swapped: `poe1price` -> `divtally` (pages.dev, vercel.app, project names),
  `poe1-price-cache` -> `divtally-price-cache`, scheduled-task name -> "DivTally Price Cache Seed".
- Pages deploy (2.3): project name must be `divtally` to match the baked `divtally.pages.dev`; noted the
  custom-domain attach can happen here or in 5.1.
- **Phase 5.1** rewritten from "register (optional)" to "**attach** `divtally.com` to Pages" (already
  registered in 1.0); the "add to manifest + resubmit extension" step removed since matches are baked.
- Quick-reference table: removed the `REPLACE-WITH-YOUR-DOMAIN` row (manifest pre-baked) and the
  `<SITE-URL-PLACEHOLDER>` (baked to divtally.com); added a note that both are already baked.

### public/site/index.html
- `<title>` "PoE1 Build Price Checker" -> "DivTally . Path of Exile build price checker".
- Header topnav `.brandmark` -> "DivTally".
- Footer: added `<span class="brandmark">DivTally</span>` as the first item (content-only; reuses the
  existing class, no CSS/layout rules changed). "Not affiliated ..." line kept verbatim.

### public/site/how-it-works.html
- `<meta description>` + `<title>` rebranded ("How DivTally works" / "How it works . DivTally").
- Topnav brandmark -> "DivTally"; "Back to the checker" -> "Back to DivTally".
- Prose (where natural): callout "This site never talks to..." -> "DivTally never talks to..."; "every
  server this site contacts" -> "every server DivTally contacts"; extension bullet "this site's own
  domain" -> "DivTally's own domain".
- Footer "The checker" home link -> "DivTally". Incidental "the site"/"this site" left to avoid repetition.

### public/site/config.js
- Header comment brand -> "DivTally"; example URLs `poe1price.vercel.app` -> `divtally.vercel.app`,
  `poe1-price-cache.YOURSUB` -> `divtally-price-cache.YOURSUB`.
- Values `REPLACE_ME_API_BASE` / `REPLACE_ME_WORKER_BASE` / `STORE_URLS` / `REPO_URL` left as
  `REPLACE_ME*` placeholders on purpose: the site's placeholder detection is `/REPLACE_ME/.test(v)`
  (index.html + how-it-works.html), so renaming the tokens would make broken links render. Real values
  land at deploy.

### public/site/assets/core.js
- **No change.** It has no user-visible brand strings - only `bpc_*` localStorage keys and the
  `bpc-page`/`bpc-ext` wire-protocol identifiers, which the spec says to keep as-is (changing them
  would break the site<->extension protocol). Diff kept empty by design.

### public/dist/build_zips.py + zips
- Guard help-text example `poe1price.pages.dev` -> `divtally.pages.dev`. The guard's detection literal
  `"REPLACE-WITH-YOUR-DOMAIN"` is intentionally retained (that's the string it scans the manifest for).
- Rebuilt both zips (now that real domains are baked, the placeholder refusal no longer triggers):
  `trade-bridge-chrome-edge-1.0.0.zip` (32431 B) and `trade-bridge-firefox-1.0.0.zip` (32440 B).
  Both `testzip()`-clean; embedded manifest name = "DivTally - Trade Bridge"; matches = the three
  divtally origins; Chrome zip = `service_worker` only, Firefox zip = `service_worker` + `scripts`.

## Verification
- `json.load` clean on both manifests; both zips exist + unzip clean + carry the baked matches.
- Owned files: `REPLACE-WITH-YOUR-DOMAIN` gone from all manifests/site files (present only as the
  guard literal in build_zips.py); `poe1price` gone from every owned file; `DivTally` present in each
  rebranded deliverable.
- `python public\dist\build_zips.py` exits 0 (no `_INVALID_PLACEHOLDER`).

## Out-of-scope note / concern
- `extension/content.js` and `extension/background.js` each still carry an old-brand **source-comment
  header** ("PoE1 Build Price Checker - Trade Bridge : ...") on line 1. These files ship inside the
  store zips (readable by reviewers) but are NOT in this task's file-ownership list, so they were left
  untouched. Recommend a one-line follow-up to rebrand those two comments if the owner wants the
  shipped source fully consistent. No user-visible UI string is affected (popup.html/popup.js have no
  brand references).
