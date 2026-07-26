"""Live probe of the OFFICIAL PoE1 trade API (www.pathofexile.com/api/trade).

Reverse-engineers the endpoints/JSON shapes needed to port the PoE2 (trade2) client in
bpc/trade.py, bpc/statmap.py, bpc/pricing.py to PoE1.

Rate-limit discipline (hard rule): real User-Agent, >=2.5s between requests, print every
X-Rate-Limit-* + Retry-After header verbatim, back off on 429. Staged so the SEARCH stage
only runs after DATA has revealed the real league name / base types / stat ids.

Usage (run from repo root C:\\scripts\\buildpricechecker-poe1):
    python research/probe_trade.py data      # 4 data GETs + trade-site HTML (no search budget)
    python research/probe_trade.py search     # unique/rare+links/price-sort/exchange/fetch
"""
import json
import os
import re
import sys
import time

import requests

OUT = r"C:\scripts\buildpricechecker-poe1\research\data"
os.makedirs(OUT, exist_ok=True)

BASE = "https://www.pathofexile.com/api/trade"   # NOTE: no "2"
UA = ("buildpricechecker-poe1/0.1 (PoE1 build cost estimator; research probe; "
      "contact: divtally@gmail.com)")

S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
})

_HEADERS_LOG = {}   # label -> {status, url, method, rate headers}
_LAST = [0.0]
GAP = 2.6           # seconds minimum between any two requests


def _throttle():
    dt = time.time() - _LAST[0]
    if dt < GAP:
        time.sleep(GAP - dt)
    _LAST[0] = time.time()


def _rate_headers(h):
    keep = {}
    for k, v in h.items():
        lk = k.lower()
        if lk.startswith("x-rate-limit") or lk in ("retry-after", "content-type"):
            keep[k] = v
    return keep


def req(label, method, url, *, json_body=None, extra_headers=None, save=None):
    _throttle()
    hdr = dict(extra_headers or {})
    print(f"\n=== {label} : {method} {url}")
    if json_body is not None:
        print("    body:", json.dumps(json_body, separators=(",", ":"))[:400])
    try:
        r = S.request(method, url, json=json_body, headers=hdr, timeout=40)
    except requests.RequestException as e:
        print("    NETWORK ERROR:", e)
        _HEADERS_LOG[label] = {"error": str(e), "url": url, "method": method}
        return None
    rh = _rate_headers(r.headers)
    print(f"    status: {r.status_code}")
    for k, v in rh.items():
        print(f"    {k}: {v}")
    _HEADERS_LOG[label] = {"status": r.status_code, "url": url, "method": method,
                           "rate_headers": rh}
    if r.status_code == 429:
        print("    !! 429 RATE LIMITED -- stopping stage to avoid ban")
        ra = r.headers.get("Retry-After")
        print("    Retry-After:", ra)
        _save_headers()
        sys.exit(2)
    body = None
    ctype = r.headers.get("content-type", "")
    if "json" in ctype:
        try:
            body = r.json()
        except Exception as e:
            print("    JSON parse error:", e)
            body = {"_raw": r.text[:2000]}
    else:
        body = {"_nonjson_ctype": ctype, "_text_head": r.text[:2000]}
    if save:
        p = os.path.join(OUT, save)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2, ensure_ascii=False)
        print(f"    saved -> {p}")
    return body


def _save_headers():
    p = os.path.join(OUT, "trade_headers.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(_HEADERS_LOG, f, indent=2, ensure_ascii=False)
    print(f"\n[headers log -> {p}]")


# --------------------------------------------------------------------------- DATA
def stage_data():
    leagues = req("data/leagues", "GET", f"{BASE}/data/leagues", save="trade_leagues.json")
    req("data/items", "GET", f"{BASE}/data/items", save="trade_items.json")
    stats = req("data/stats", "GET", f"{BASE}/data/stats", save="trade_stats.json")
    req("data/static", "GET", f"{BASE}/data/static", save="trade_static.json")
    # speculative: does PoE1 expose a filter-schema endpoint?
    req("data/filters?", "GET", f"{BASE}/data/filters", save="trade_data_filters.json")

    # --- current league names -------------------------------------------------
    if leagues:
        print("\n--- LEAGUES (id / realm / text) ---")
        for lg in leagues.get("result", []):
            print("   ", repr(lg.get("id")), "| realm=", lg.get("realm"),
                  "| text=", repr(lg.get("text")))

    # --- candidate stat ids I need for the search stage -----------------------
    if stats:
        wants = ["maximum life", "total elemental resistance", "total to chaos resistance",
                 "total maximum life", "to fire resistance", "elemental resistance",
                 "total energy shield", "total armour", "total evasion"]
        print("\n--- STAT ID CANDIDATES ---")
        for grp in stats.get("result", []):
            label = grp.get("label")
            for e in grp.get("entries", []):
                t = (e.get("text") or "").lower()
                sid = e.get("id", "")
                if any(w in t for w in wants):
                    print(f"   [{label}] {sid} :: {e.get('text')!r}")

    # --- trade-site HTML: extract filter-group field names --------------------
    html_filter_probe("Standard")
    _save_headers()


def html_filter_probe(league):
    url = f"https://www.pathofexile.com/trade/search/{league}"
    _throttle()
    print(f"\n=== trade-site HTML : GET {url}")
    hdr = {"Accept": "text/html,application/xhtml+xml", "User-Agent": UA}
    try:
        r = S.get(url, headers=hdr, timeout=40)
    except requests.RequestException as e:
        print("    NETWORK ERROR:", e)
        return
    print("    status:", r.status_code, "len:", len(r.text))
    _HEADERS_LOG["trade-site-html"] = {"status": r.status_code, "url": url,
                                       "rate_headers": _rate_headers(r.headers)}
    html = r.text
    # Field-name tokens we care about for the port.
    tokens = ["socket_filters", "equipment_filters", "armour_filters", "weapon_filters",
              "req_filters", "misc_filters", "type_filters", "trade_filters", "map_filters",
              "heist_filters", "sanctum_filters", "ultimatum_filters",
              '"links"', '"sockets"', '"ar"', '"ev"', '"es"', '"block"', '"ward"',
              '"pdps"', '"edps"', '"dps"', '"aps"', '"crit"', '"rune_sockets"',
              '"category"', '"rarity"', "onlineleague", '"online"', '"any"',
              "gem.activegem", "gem.supportgem", "armour.chest", "armour.helmet",
              "accessory.ring", "weapon."]
    found = {}
    for tok in tokens:
        idxs = [m.start() for m in re.finditer(re.escape(tok), html)]
        if idxs:
            # keep a short context window around the first hit
            i = idxs[0]
            found[tok] = {"count": len(idxs),
                          "context": html[max(0, i - 90):i + 110].replace("\n", " ")}
    out = {"source_url": url, "status": r.status_code, "html_len": len(html),
           "token_hits": found}
    # Try to isolate the inline filter-schema blob (varies by site version).
    for marker in ("filterGroups", "type_filters", "socket_filters"):
        m = re.search(re.escape(marker), html)
        if m:
            s = max(0, m.start() - 40)
            out.setdefault("schema_snippets", {})[marker] = html[s:s + 1400]
    p = os.path.join(OUT, "trade_site_filters.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"    token hits: {sorted(found)}")
    print(f"    saved -> {p}")


# --------------------------------------------------------------------------- SEARCH
def _load(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return json.load(f)


def stage_search():
    """Values are read from CLI args so I can pass verified league/base/stat ids.

    argv: search <LEAGUE> <BODY_BASE> <LIFE_STAT_ID> <PSEUDO_ELEM_ID> [UNIQUE_NAME] [UNIQUE_TYPE]
    """
    a = sys.argv
    league = a[2]
    body_base = a[3]
    life_id = a[4]
    pelem_id = a[5]
    uniq_name = a[6] if len(a) > 6 else "Goldrim"
    uniq_type = a[7] if len(a) > 7 else "Leather Cap"

    from urllib.parse import quote
    sB = f"{BASE}/search/{quote(league)}"
    shdr = {"Content-Type": "application/json",
            "Origin": "https://www.pathofexile.com",
            "Referer": f"https://www.pathofexile.com/trade/search/{quote(league)}"}

    # (1) UNIQUE by name+type, price sorted
    q1 = {"query": {"status": {"option": "online"}, "name": uniq_name, "type": uniq_type,
                    "stats": [{"type": "and", "filters": []}]},
          "sort": {"price": "asc"}}
    r1 = req("search:unique", "POST", sB, json_body=q1, extra_headers=shdr,
             save="trade_search_unique.json")

    # (2) RARE: body base + stat filters (life + pseudo elem res) + LINKS filter (socket_filters)
    q2 = {"query": {"status": {"option": "online"}, "type": body_base,
                    "stats": [{"type": "and", "filters": [
                        {"id": life_id, "value": {"min": 70}},
                        {"id": pelem_id, "value": {"min": 60}},
                    ]}],
                    "filters": {"socket_filters": {"filters": {"links": {"min": 6}}}}},
          "sort": {"price": "asc"}}
    r2 = req("search:rare+links", "POST", sB, json_body=q2, extra_headers=shdr,
             save="trade_search_rare_links.json")

    # (3) PRICE-SORTED + armour_filters (verify PoE1 defence-total group name/fields)
    q3 = {"query": {"status": {"option": "online"}, "type": body_base,
                    "stats": [{"type": "and", "filters": []}],
                    "filters": {"armour_filters": {"filters": {"ar": {"min": 100}}}}},
          "sort": {"price": "asc"}}
    r3 = req("search:pricesort+armour", "POST", sB, json_body=q3, extra_headers=shdr,
             save="trade_search_pricesort.json")

    # (4) BULK EXCHANGE: chaos <-> divine (very liquid). Verify endpoint + body + response.
    xB = f"{BASE}/exchange/{quote(league)}"
    qx = {"query": {"status": {"option": "online"}, "have": ["chaos"], "want": ["divine"]},
          "sort": {"have": "asc"}, "engine": "new"}
    rx = req("exchange:chaos->divine", "POST", xB, json_body=qx,
             extra_headers={"Content-Type": "application/json"},
             save="trade_exchange.json")

    # (5) FETCH: take up to 10 ids from the unique search + its query id.
    if r1 and r1.get("result"):
        allids = r1["result"]
        qid = r1.get("id")
        f10 = req("fetch:10ids", "GET",
                  f"{BASE}/fetch/{','.join(allids[:10])}?query={qid}",
                  save="trade_fetch.json")
        if f10:
            print("    -> fetch(10) returned", len(f10.get("result", []) or []), "results")
        # cap probe: does PoE1 accept >10 ids in one fetch?
        if len(allids) >= 11:
            f11 = req("fetch:11probe", "GET",
                      f"{BASE}/fetch/{','.join(allids[:11])}?query={qid}",
                      save="trade_fetch_11probe.json")
            if f11:
                n = len(f11.get("result", []) or [])
                print("    -> fetch(11) status-ok; returned", n, "results",
                      "(<=10 => capped/truncated)")

    # (6) FETCH a rare result to document the item JSON sockets/links shape.
    if r2 and r2.get("result"):
        rids = r2["result"][:5]
        rqid = r2.get("id")
        fr = req("fetch:rare", "GET",
                 f"{BASE}/fetch/{','.join(rids)}?query={rqid}",
                 save="trade_fetch_rare.json")
        if fr and fr.get("result"):
            it = (fr["result"][0] or {}).get("item", {})
            print("    -> rare item keys:", sorted(it.keys()))
            print("    -> sockets sample:", json.dumps(it.get("sockets"))[:300])

    _save_headers()


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "data"
    if stage == "data":
        stage_data()
    elif stage == "search":
        stage_search()
    else:
        print("unknown stage", stage)
