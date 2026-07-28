# Backlog (RULE 7)

## B-002: Own game-file item database (parked 2026-07-27)
If the D-0019 registry (ninja harvest + poedb gap-fill) proves insufficient: extract item/mod/
variant data from the PoE1 game files ourselves via pathofexile-dat (the owner's
C:\scripts\poe2-datamine pipeline is the template). Fully primary, zero third-party runtime or
build-step dependency; refresh per patch. Build only on demonstrated registry gaps.

New feature ideas parked until the owner explicitly greenlights them. The initial goal is parity
with the parent project, on PoE1.

## B-001: Public deployment - "users are the scanners" (proposed 2026-07-26, awaiting owner go)
Replicate the PoE2 public architecture (see `C:\scripts\buildpricechecker\PoE2-Price-Checker-Public-Setup.docx`,
adapted to PoE1; the Trade Bridge extension is already ported in `extension/`):
- Central serverless function (Cloudflare Pages front-end + Vercel/Lambda function) serves only
  the cache-friendly half (poe.ninja gems/currency/uniques, PoB decode, trade-link generation).
- Rare/unique trade pricing stays on user IPs: Rung 1 = clickable `?q=` links (no install);
  Rung 2 = the extension auto-prices from the user's browser/IP (CORS-exempt, ported limiter
  with persisted state). Rung 0 = the existing local exe/zip pattern.
- NEW vs PoE2: optional shared community cache - extension results POSTed back (short TTL) so
  popular builds show rare prices for everyone; server never calls GGG.
- Steps: pick public skin -> extract `api/build.py` function -> staging deploy -> bridge test
  against real origin (`/v/_exttest`) -> package extension (Edge free / Chrome $5 one-time).
- **Refined 2026-07-26 (owner cost review):** zero-cost stack locked in: Cloudflare Pages (free,
  pages.dev subdomain) + free-tier function (Vercel Hobby or Workers) + Workers KV cache; custom
  domain optional ~$10/yr; extension DEFERRED at launch. Extension-less launch shape: Rung 1
  (poe.ninja-priced gems/currency/uniques + per-rare trade links + paste-a-price) PLUS an
  owner-seeded community cache - a scheduled job on the owner's PC prices top-N meta builds daily
  via the existing local app/limiter (same footprint as normal personal use) and uploads to the
  cache, so popular builds render fully priced for visitors with nothing installed. CORS facts
  live-verified 2026-07-26: neither poe.ninja nor the trade API sends ACAO to third-party
  origins; hands-free in-page rare pricing therefore requires a privileged install (extension /
  userscript / desktop companion) - deferred until user demand.
- **REVISED 2026-07-26 (owner):** extension is IN SCOPE AT LAUNCH (manual whisper-paste path +
  extension, site pushes the install) - supersedes "extension DEFERRED" above. Trust plan so it
  never reads sketchy ("official" = transparency + restraint, NOT GGG-looking - carry the
  standard not-affiliated-with-GGG footer): (1) store-only distribution (Chrome $5 / Edge /
  Firefox AMO), never sideload; (2) minimal manifest - host permissions ONLY pathofexile.com/api/
  trade/* + our domain, no cookies/tabs/all_urls, works logged-out; (3) open source, unminified,
  repo linked from store + site; (4) one identity everywhere (name/icon/publisher/domain -
  custom domain justified); (5) no dark patterns - site fully useful pre-install, calm inline
  upgrade card w/ does/never-does list, "bridge active" state post-install; (6) /how-it-works
  transparency page (endpoints, storage, cache opt-out, rate-limit ethics) doubling as launch-post
  copy; (7) store review queues take days - submit early in the launch sequence.
- **Rung-1 feedback UX (owner walkthrough 2026-07-26):** rare rows accept a pasted GGG
  copy-whisper string (parse the price from "...listed for 35 chaos..." / b/o variants - the
  PoE2 docx's "paste-the-whisper" pattern) or a typed "35c"/"2 div"; parsed price folds into
  totals client-side and persists in localStorage. Data flow summary: site itself NEVER receives
  data from GGG - prices arrive via (1) human whisper-paste, (2) the shared cache seeded by the
  owner's PC (later extension users), (3) the extension bridge (deferred).
