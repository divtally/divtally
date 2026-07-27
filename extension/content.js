/* DivTally - Trade Bridge : content script.
 *
 * Injected into the public/staging site (and the local dev site). It bridges the PAGE
 * (which can only use window.postMessage) and the extension SERVICE WORKER (which can only
 * be reached via chrome.runtime.sendMessage and is the only context allowed to call the
 * trade API cross-origin).
 *
 * Protocol (all messages carry a `source` so each side ignores its own/foreign messages):
 *   page  -> ext : { source:"bpc-page", type:"ping",  reqId }
 *                  { source:"bpc-page", type:"price", reqId, league, queries:[{key, query}] }
 *   ext   -> page : { source:"bpc-ext", type:"hello", version }            (announced on load)
 *                   { source:"bpc-ext", type:"pong",  reqId, version }
 *                   { source:"bpc-ext", type:"price-result", reqId, results:[...] | error }
 *                   { source:"bpc-ext", type:"price-progress", reqId, key, stage, detail }  (v1.1)
 * Each `query` is the trade `query` object (status/type/name/stats/filters) -- exactly the
 * inner object the site already builds for its clickable ?q= links.
 *
 * v1.1 (additive): when the page's `price` request carries protocolVersion >= 1.1, the worker
 * streams per-item progress (queued/searching/fetching/waiting/done/nobuyout/error) which this
 * script relays verbatim as `price-progress`. A page that doesn't understand the type ignores it.
 */
(function () {
  "use strict";
  var VERSION = (chrome.runtime.getManifest && chrome.runtime.getManifest().version) || "0";

  function toPage(msg) {
    msg.source = "bpc-ext";
    window.postMessage(msg, window.location.origin);
  }

  // Announce presence so the page can light up "live pricing available" without polling.
  try { toPage({ type: "hello", version: VERSION }); } catch (e) {}

  window.addEventListener("message", function (ev) {
    if (ev.source !== window) return;                 // only same-window messages
    var d = ev.data;
    if (!d || d.source !== "bpc-page") return;         // ignore our own + foreign messages

    if (d.type === "ping") {
      toPage({ type: "pong", reqId: d.reqId, version: VERSION });
      return;
    }
    if (d.type === "price") {
      // Forward reqId + protocolVersion so the worker can label progress events and version-gate
      // them (>= 1.1). Additive only: a pre-1.1 worker ignores both fields; the request bridge
      // otherwise behaves exactly as before.
      chrome.runtime.sendMessage(
        { type: "bpc-price", league: d.league, queries: d.queries, reqId: d.reqId, protocolVersion: d.protocolVersion },
        function (resp) {
          if (chrome.runtime.lastError) {
            toPage({ type: "price-result", reqId: d.reqId, error: String(chrome.runtime.lastError.message) });
            return;
          }
          if (resp && resp.error) {
            toPage({ type: "price-result", reqId: d.reqId, error: resp.error });
            return;
          }
          toPage({ type: "price-result", reqId: d.reqId, results: (resp && resp.results) || [] });
        }
      );
    }
  });

  // v1.1 (additive, receive-only): relay per-item progress from the service worker to the page
  // verbatim. The request bridge above is untouched; this is a separate listener that never
  // sends a response (returns undefined so the message channel closes immediately).
  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg && msg.type === "bpc-price-progress") {
      toPage({ type: "price-progress", reqId: msg.reqId, key: msg.key, stage: msg.stage, detail: msg.detail || {} });
    }
  });
})();
