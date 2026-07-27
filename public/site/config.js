/* ===========================================================================
 * PoE1 Build Price Checker — PUBLIC SITE CONFIG
 * ---------------------------------------------------------------------------
 * Fill in every REPLACE_ME below before you deploy. Nothing else in the site
 * needs editing. This file is loaded FIRST (before core.js) and read by both
 * the engine (assets/core.js) and the page (index.html / how-it-works.html).
 *
 * The values are just origins (no trailing path). The site appends the paths
 * itself (`/api/build`, `/cache`).
 *
 *   API_BASE     the serverless build function (public/api on Vercel Hobby).
 *                e.g. "https://poe1price.vercel.app"
 *   WORKER_BASE  the Cloudflare Worker community price cache (public/worker).
 *                e.g. "https://poe1-price-cache.YOURSUB.workers.dev"
 *                Leave "" to disable the shared cache entirely (site still works).
 *   STORE_URLS   the extension listings, once each store approves it.
 *   REPO_URL     the public, open-source repository (linked from the footer and
 *                the /how-it-works page — part of the B-001 trust checklist).
 *
 * NOTE on the invariant (docs/backlog.md B-001): NONE of these endpoints ever
 * call pathofexile.com. Item numbers arrive only from poe.ninja (via API_BASE),
 * the community cache (WORKER_BASE, seeded by real machines), a human pasting a
 * whisper, or the browser extension running on the visitor's own IP.
 * =========================================================================== */
window.BPC_CONFIG = {
  API_BASE:    "REPLACE_ME_API_BASE",      // e.g. https://poe1price.vercel.app
  WORKER_BASE: "REPLACE_ME_WORKER_BASE",   // e.g. https://poe1-price-cache.yoursub.workers.dev  ("" disables cache)

  STORE_URLS: {
    chrome:  "REPLACE_ME_CHROME_STORE_URL",  // Chrome Web Store listing
    edge:    "REPLACE_ME_EDGE_STORE_URL",    // Microsoft Edge Add-ons listing
    firefox: "REPLACE_ME_FIREFOX_AMO_URL"    // Firefox AMO listing
  },

  REPO_URL: "REPLACE_ME_REPO_URL",           // e.g. https://github.com/you/buildpricechecker-poe1

  /* Optional. Leave as-is unless you know you need them. */
  DEFAULT_LEAGUE: "",                         // "" = use each build's own league; or pin e.g. "Standard"
  CACHE_MAX_KEYS: 60                          // per worker request cap (do not raise above the Worker's MAX_ENTRIES)
};
