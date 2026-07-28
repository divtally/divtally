# League-rollover runbook (DivTally / PoE1 Build Price Checker)

**What this is:** the exact owner steps when a PoE1 league ends and a new one starts (Allflame ->
next league). Derived from the R6 rollover audit (`docs/bugtest/r6-rollover.md`), which drove the
league code paths against a mocked post-rollover index and proved the key behaviours live on
poe.ninja.

---

## Bottom line (read this first)

**The site keeps pricing new-league builds on day 1 with ZERO action from you.** League is read
live from poe.ninja per build, every default self-heals off poe.ninja's `index-state`, and the
worker cache isolates by league and expires in 24h. The steps below are **refinement, not an
outage fix**:

- **Nothing you must do to avoid breakage.** A new-league build pastes and prices immediately.
- **One thing worth doing (Step 1-2): regenerate + redeploy the variant registry** so socket/
  count and variant-label mapping for a handful of variant uniques use fresh data. Safe to skip
  for a while - the runtime prices variants from LIVE poe.ninja lines, never from the registry's
  baked (old-league) numbers; a stale registry only ever degrades to a trade link, never a wrong
  price.
- **One optional nicety (Step 3): re-seed the community cache** so popular new-league builds render
  fully for visitors with nothing installed.

---

## A. What auto-heals - do nothing

1. **PoB imports with no league** and the site's "League: Auto" default -> the new challenge
   league, the instant poe.ninja lists it in `index-state.economyLeagues`.
2. **Site league dropdown** -> seeded with `Standard` + `Hardcore` + Auto, and it appends each
   loaded build's own league automatically. No hardcoded league to change.
3. **Worker community cache** -> every league gets its own KV namespace and every entry has a 24h
   TTL, so last league's entries can't leak into or collide with the new league and are gone
   within a day. **No worker redeploy for a rollover.**
4. **Standard pricing** -> always live (verified: a Standard character prices end-to-end today).
5. **Old bookmarked links** to last league's characters keep working while poe.ninja retains the
   old snapshot (it keeps them for months), priced against that league's frozen end-of-league
   economy. (See caveat M2 in the R6 doc - the header honestly shows the old league.)

---

## B. Owner steps at league start (numbered)

Run from the repo root: `C:\scripts\buildpricechecker-poe1`. Python + Node/npm as in
`GOING-PUBLIC.md`.

### 1. Regenerate the variant-unique registry (fresh, from the new league)

```
:: validate against LIVE new-league poe.ninja data WITHOUT writing (preview)
python tools\build_variant_registry.py --check --refresh

:: if it prints coverage and "validated OK", write the artifact for real
python tools\build_variant_registry.py --refresh
```

- `--refresh` (no `--league`) live-resolves the new league from poe.ninja `index-state` and
  re-fetches the Unique* overviews; it writes `public\api\_data\variant_uniques.json`.
- To pin the league name explicitly (belt-and-suspenders): add `--league "<New League Name>"`.
- **Do NOT pass `--offline`** at rollover - the offline default league is still `Allflame`
  (last league) and would harvest stale dumps.
- The tool **fails loud (non-zero exit, no write)** if any defining stat id fails to resolve or a
  durable variant name is missing, so a bad run can't ship a broken registry.
- Duration: ~1 minute (8 polite poe.ninja fetches + validation).
- Best run a **few days into the league**, once poe.ninja has enough listings for the variant
  count/label lines to be populated. Running on launch day is safe but yields thinner
  `observed_variants` (still fine - prices are live).

### 2. Redeploy the API so the new registry ships

The registry is bundled into the Vercel Python function (`public/api`). Redeploy it:

```
:: one-time-per-deploy prerequisite (see GOING-PUBLIC.md 2.2): vercel.json at the root
copy public\api\vercel.json public\vercel.json

vercel --prod
```

(Or, if you use GitHub push-to-deploy: commit the regenerated `variant_uniques.json` and push -
Vercel auto-builds.)
- Duration: ~2-3 minutes (Vercel build + propagate).
- After it goes live, the CDN may still serve a cached `/api/build` for up to ~10 min fresh (and
  up to 24h stale-while-revalidate) per identical build URL; new URLs are fresh immediately.

### 3. (Optional) Re-seed the community cache for the new league's popular builds

On YOUR PC only (this is the one place trade calls happen; it honours the local rate limiter):

```
python tools\seed_cache.py --worker-url https://divtally-cache.divtally.workers.dev/cache -n 20
```

- League defaults to the current/first poe.ninja snapshot = the new league; no `--league` needed
  (add `--league "<slug>"` only to force one).
- Preview first with `--dry-run` (lists the builds, prices nothing) or `--from-cache-only`
  (records from already-priced local results, zero trade calls).
- Duration: a few minutes for 20 builds (paced ~3s apart). Purely a visitor nicety; skip freely.

### 4. (Optional, cosmetic) Refresh the offline demo build's league

`public/site/assets/sample.js` (and `bpc/ui/assets/sample.js`) still say `league: "Allflame"` in
the placeholder build shown before a real fetch. Update the string and redeploy Pages if you want
the demo to read current. No functional effect.

---

## C. What you do NOT redeploy for a rollover

- **The Cloudflare Worker** (`public/worker`) - league-agnostic; keys are computed client-side and
  it namespaces by league automatically. Leave it.
- **The site / Cloudflare Pages** - the dropdown self-seeds and `DEFAULT_LEAGUE` is `""`. Only
  redeploy Pages if you did Step 4 (cosmetic) or are changing store URLs.
- **`trade_stats.json` / `trade_items.json`** - stat ids and base types are stable across leagues;
  regenerate only if a new league actually changes the stat dictionary (rare; you'd see registry
  Step 1 fail validation if a defining id vanished).

---

## D. Verify (copy-paste)

1. **New-league default resolves** - pick any current-league character on poe.ninja and:
   ```
   curl "https://divtally.vercel.app/api/build?url=<new-league poe.ninja character url>"
   ```
   Expect HTTP 200, `"ok": true`, `"league": "<New League>"`, and priced rows with chaos tiers.
2. **Registry is on the new league** - open `public\api\_data\variant_uniques.json`, check
   `_meta.ninja_league` == the new league and `_meta.generated` is today.
3. **A variant unique prices** - price a build carrying e.g. Watcher's Eye / Impresence / a
   timeless jewel; confirm a number or a clean trade link (never a blank crash).
4. **Standard still works** - paste any Standard character link (or set the dropdown to Standard).
5. **Cache namespaced** - a repeat appraisal of the same new-league build shows community numbers
   within a day of seeding; old-league keys are gone after 24h.

---

## E. Expected total duration

| Step | Action | Time | Required? |
|---|---|---|---|
| - | New-league builds price with no action | 0 | already true |
| 1 | Regenerate registry (`--refresh`) | ~1 min | recommended |
| 2 | Redeploy API (`vercel --prod`) | ~2-3 min | recommended (ships Step 1) |
| 3 | Re-seed community cache | ~few min | optional |
| 4 | Refresh demo league string | ~1 min | cosmetic |

**Realistic hands-on: ~5 minutes** (Steps 1-2), best done a few days into the league.

---

## F. Rollback

- Registry: `variant_uniques.json` is deterministic and versioned in git - `git checkout` the
  previous copy and redeploy if a regen looks wrong. (Never runs git in an agent; this is a manual
  owner step.)
- API: `vercel` keeps prior deployments - promote the previous one from the Vercel dashboard.
- Nothing here touches the worker or user data, so there is no destructive state to undo.
