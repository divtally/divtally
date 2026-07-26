/* Popup = a self-contained tester. Paste a trade ?q= link (or raw query JSON), and the
 * extension runs the real search+fetch from your IP and shows the cheapest listing. No web
 * page required -- this alone validates the extension end to end. */
"use strict";

var $ = function (id) { return document.getElementById(id); };
var statusEl = $("status"), outEl = $("out");

function setOut(html, cls) { outEl.className = cls || ""; outEl.innerHTML = html; }

// version / liveness check
chrome.runtime.sendMessage({ type: "bpc-ping" }, function (resp) {
  if (chrome.runtime.lastError) { statusEl.textContent = "service worker not responding"; return; }
  statusEl.innerHTML = '<span class="ok">&#9679; active</span> &middot; v' + (resp && resp.version || "?");
});

// Accept either a full trade URL (...trade/search/<league>?q=<json>) or raw query/{query} JSON.
function parseInput(text) {
  text = (text || "").trim();
  if (!text) throw new Error("paste a trade link or query JSON");
  if (/^https?:\/\//i.test(text)) {
    var u = new URL(text);
    var m = u.pathname.match(/\/search\/([^/?]+)/i);
    var league = m ? decodeURIComponent(m[1]) : "";
    var q = u.searchParams.get("q");
    if (!q) throw new Error("no ?q= payload in that URL");
    var obj = JSON.parse(q);
    return { league: league, query: obj.query || obj };
  }
  var parsed = JSON.parse(text);                 // raw JSON: either {query:{...}} or a bare query
  var query = parsed.query || parsed;
  var league = parsed.league || "";
  return { league: league, query: query };
}

$("price").addEventListener("click", function () {
  var parsed;
  try { parsed = parseInput($("in").value); }
  catch (e) { setOut("Could not parse input: " + e.message, "err"); return; }
  if (!parsed.league) {
    setOut("No league found. Use the full trade <code>?q=</code> URL (it carries the league), or add \"league\":\"&lt;name&gt;\" to your JSON.", "err");
    return;
  }
  setOut("searching as your IP… (rate-limited, may pause a few seconds)", "muted");
  chrome.runtime.sendMessage(
    { type: "bpc-price", league: parsed.league, queries: [{ key: "test", query: parsed.query }] },
    function (resp) {
      if (chrome.runtime.lastError) { setOut("error: " + chrome.runtime.lastError.message, "err"); return; }
      if (resp && resp.error) { setOut("error: " + resp.error, "err"); return; }
      var r = resp && resp.results && resp.results[0];
      if (!r) { setOut("no response", "err"); return; }
      if (r.error) { setOut("error: " + r.error, "err"); return; }
      if (r.amount == null) {
        setOut("Found <b>" + (r.total || 0) + "</b> listings, but none had a buyout price (offer-only).", "muted");
        return;
      }
      setOut('<span class="price">' + r.amount + " " + (r.currency || "") + "</span>"
             + '<div class="muted">cheapest of ' + (r.total || 0) + " online listings &middot; league " + parsed.league + "</div>", "ok");
    }
  );
});

$("reset").addEventListener("click", function () {
  chrome.runtime.sendMessage({ type: "bpc-reset-limits" }, function () {
    setOut("local rate-limit window cleared", "muted");
  });
});
