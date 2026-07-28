# R6 - Firefox / AMO lens

**Target:** `public/dist/divtally-extension-firefox-1.2.1.zip`
**Tools (all local, no pathofexile.com):** official AMO `addons-linter@10.9.0` (run offline against the zip),
its bundled Firefox WebExtension schema, and its `@mdn/browser-compat-data` dependency (BCD), all installed
into the scratchpad. Provenance: findings tagged **[SRC]** are derived from that linter/schema/BCD output;
**[INFERRED]** = established Firefox behaviour not verifiable from this round's local sources.

## Verdict

**PASS - AMO-submittable.** `addons-linter` reports **0 errors, 0 notices, 3 warnings** (exit 0). No error =
nothing that predicts AMO rejection. The manifest cross-browser shape (dual background key, gecko id,
`data_collection_permissions`) is **validated correct by the current linter schema**, and the `chrome.*`
API surface is **source-confirmed portable to Firefox**. Only two low/minor items, both non-blocking.

## Findings

| id | severity | summary |
|----|----------|---------|
| R6-1 | minor | `UNSAFE_VAR_ASSIGNMENT` x2 - `popup.js` writes remote/user data to `innerHTML`. Linter WARNING (not error). Real exploitability very low (MV3 CSP + controlled inputs), but a legit hardening nit and reviewer-attention magnet. |
| R6-2 | minor **[INFERRED]** | Firefox has historically treated MV3 `host_permissions` as user-opt-in (granted via the extensions panel), unlike Chrome's install-time grant. If still true in current Firefox, the trade host permission is ungranted until the user acts and there is no in-product guidance - the extension silently can't price. NOT verified this round (no live Firefox). |

Everything else audited: **PASS**. Full linter output: 3 warnings only, itemised below.

---

## 1. AMO linter (offline)

`npx addons-linter@10.9.0 divtally-extension-firefox-1.2.1.zip` -> **errors 0 / notices 0 / warnings 3**, exit 0.

### W1 - `BACKGROUND_SERVICE_WORKER_IGNORED` (manifest.json) - EXPECTED / BENIGN **[SRC]**
> "The `/background/service_worker` manifest property is unsupported and ignored on Firefox. Please make
> sure `/background/scripts` or `/background/page` properties are providing appropriate Firefox compatibility."

This is the informational sibling of `BACKGROUND_SERVICE_WORKER_NOFALLBACK` (both defined in the linter). Because
the Firefox build **does** ship `background.scripts:["background.js"]` alongside `service_worker`, it earns the
*mild* IGNORED notice, not the worse NOFALLBACK finding. The dual-key strategy in `build_zips.py`
`firefox_manifest()` is therefore **correct and deliberately optimal**. Not a defect - do not "fix."

### W2/W3 - `UNSAFE_VAR_ASSIGNMENT` (popup.js:9, popup.js:14) -> R6-1

- **popup.js:14** `statusEl.innerHTML = '...v' + resp.version` - `resp.version` is
  `chrome.runtime.getManifest().version` (own manifest). Trusted input; flagged but effectively a false positive.
- **popup.js:9** `outEl.innerHTML = html` in `setOut()` - the real one. Callers concatenate **`r.currency`**
  (a string straight from the pathofexile.com trade JSON) and **`parsed.league`** (user-pasted) into `html`
  (lines 44/54/57-58). Remote-origin data reaching `innerHTML`.

**Why only minor:** the popup is an MV3 extension page under the default CSP (`script-src 'self'; object-src
'self'`). `innerHTML` never executes injected `<script>`, and inline event handlers (`<img onerror=...>`) are
blocked by that CSP - so there is **no script-execution path**. Inputs are also low-risk (currency is a fixed
GGG enum; league is self-pasted -> self-XSS only). Worst realistic case is malformed DOM, not code execution.
It's a WARNING, not an error, so it **does not predict AMO rejection**; but `innerHTML` with remote data can
draw a human reviewer's eye and is trivially avoidable. **Fix (optional hardening):** build the price/league
output with `textContent` / DOM nodes, or HTML-escape `r.currency` + `parsed.league` before interpolation.

---

## 2. Manifest cross-browser audit

Delta between the chrome-edge and firefox zips is **exactly one intended change** (verified by diff): the
firefox manifest adds `"scripts":["background.js"]` beside `"service_worker"`. No other drift.

| Item | Result | Evidence |
|------|--------|----------|
| `background` dual key (`service_worker` + `scripts`) | **CORRECT** | BCD: `background.service_worker` firefox `version_added:false`; `background.scripts` firefox `version_added:48`. Firefox ignores SW, runs `scripts`. MV3 itself is FF109+, and `scripts` (FF48+) covers 100% of MV3-capable Firefox -> no version gap. **[SRC]** |
| `background.js` safe as an event-page script | **CONFIRMED** | Grep of `background.js` finds **no** ServiceWorker-only globals (`self.`/`clients`/`skipWaiting`/`importScripts`/`install`/`activate`). It's a plain script; the `onMessage` listener is registered synchronously at top level (correct for a wake-on-event page). SW-idle state is persisted to `chrome.storage.local`, which equally handles Firefox event-page suspension. So Firefox loses nothing by ignoring `service_worker`. **[SRC-code]** |
| `browser_specific_settings.gecko.id` = `extension@divtally.com` | **VALID** | No `MISSING_ADDON_ID`; email-form id accepted. Uses `browser_specific_settings` (not the deprecated `applications`). **[SRC]** |
| `data_collection_permissions` shape | **VALIDATED CORRECT** | Linter's `validateDataCollectionPermissions` runs by default (`enableDataCollectionPermissions:true`). It enforces exactly: (a) property present (else `MISSING_DATA_COLLECTION_PERMISSIONS` warning), (b) no `has_previous_consent` (else `HAS_PREVIOUS_CONSENT_IS_RESERVED` **error**), (c) if `required` contains `"none"` it must be the sole value (else `NONE_DATA_COLLECTION_IS_EXCLUSIVE` **error**). Our `required:["none"]` -> present, no consent flag, length 1 -> passes all three. `"none"` is the canonical "no data collected" declaration and is correctly exclusive. **[SRC]** |
| `permissions:["storage"]`, `host_permissions:[".../api/trade/*"]`, `action`, `content_scripts` | **VALID** | Not flagged. BCD: `host_permissions` FF109+, `action` FF109+, content scripts / `run_at:document_start` supported. **[SRC]** |
| `icons` 16/32/48/128 PNG | **VALID** | No `CORRUPT_ICON_FILE`. **[SRC]** |
| `strict_min_version` absent | **OK (optional)** | Not required; Firefox <109 cannot load an MV3 extension anyway, so no bad-install risk. Could add `"strict_min_version":"109.0"` for explicitness. **[SRC/INFERRED]** |

---

## 3. `chrome.*` vs `browser.*` portability (static)

The zip ships raw `chrome.*` (no `webextension-polyfill`). APIs used: `chrome.storage.local.get/set/remove`,
`chrome.runtime.onMessage/sendMessage/getManifest/lastError`, `chrome.tabs.sendMessage`.

**Portable to Firefox - source-confirmed. [SRC]**

1. **Aliasing:** Firefox exposes `chrome` and `browser` as the same API objects.
2. **Promise semantics (the load-bearing part):** `background.js` does `await chrome.storage.local.get(key)`.
   The bundled Firefox schema marks `storage.StorageArea.get` as **`"async":"callback"`** - the Firefox marker
   meaning "the callback is optional; when omitted the function **returns a Promise**." So awaiting the
   `chrome.*` call resolves in Firefox (this is the behaviour the Chrome-only polyfill exists to add; Firefox
   has it natively). Callback-form uses (`sendMessage(msg, cb)`, `tabs.sendMessage(id, msg, cb)`, `onMessage`
   listener returning `true` + async `sendResponse`, reading `chrome.runtime.lastError` inside the callback)
   are all the Chrome-style shapes Firefox also supports.
3. **Surface exists:** BCD confirms every API used is supported in Firefox - `storage.local.get`/`runtime.
   sendMessage`/`runtime.onMessage`/`tabs.sendMessage`/`getManifest` since FF45, `runtime.lastError` since FF47.

The linter raised **zero** errors/warnings on any `chrome.*` usage, consistent with the above. No polyfill needed.

*Note (BCD [SRC]):* Firefox `runtime.getManifest()` "removes unsupported keys" - immaterial here (`.version`
is always present).

---

## R6-2 detail (host-permission UX) **[INFERRED - confirm on a live Firefox]**

Chrome grants declared `host_permissions` at install. Firefox's MV3 rollout has historically made host
permissions **user-opt-in** (granted post-install via the extensions panel / "..." menu). If that still holds
in current Firefox, then after install the background `fetch` to `pathofexile.com/api/trade` is **not
permitted until the user grants it**, and the UI has no first-run prompt explaining this - a Firefox user could
see silent "no results." This is a UX/runtime characteristic, **not** a manifest error (the linter is silent on
it, and BCD only records `host_permissions` = FF109+, not the grant model), so it is flagged INFERRED and
unverified this round. If confirmed, mitigations: a first-run note/`permissions.request()` flow, or surface a
clear "enable pathofexile.com access in Firefox" hint when a trade call returns a permission error.

---

## What this lens did NOT find (honest negatives)

- No linter errors -> nothing predicting AMO rejection.
- No manifest-shape defect: gecko id, `data_collection_permissions`, dual background, host/permissions, action,
  content scripts, icons all validate against the current AMO schema.
- No `chrome.*` portability break: schema (`async:"callback"`) + BCD confirm the exact APIs work in Firefox.
- No cross-build drift: firefox vs chrome manifests differ only in the intended `background.scripts` line.
- The `BACKGROUND_SERVICE_WORKER_IGNORED` warning is expected and correct - not a defect.

Net: the Firefox/AMO lens surfaces **no blocker/major**. Two minors (one `innerHTML` hardening nit; one
inferred, unverified host-permission UX note). Consistent with R6 being a low-adjustment round for this lens.
