#!/usr/bin/env python
"""Rebuild a build's info from the LOCAL CACHE when the poe.ninja profile is gone.

The cached poe.ninja response holds the full item data + Path of Building export, so we
can reconstruct the build and run fresh trade searches (trade is independent of the
profile being removed) without poe.ninja.

Usage:
  python recover.py "<poe.ninja character URL>"
  python recover.py --account proyousart-4104 --character JOSIAHHHHH
  python recover.py ... --links-only      (skip pricing; just emit trade links)
"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bpc import engine, poeninja, report          # noqa: E402
from bpc.cache import CACHE_DIR                    # noqa: E402
from bpc.pricing import Pricer                     # noqa: E402
from bpc.trade import TradeClient                  # noqa: E402


def find_cached_char(account, character):
    """Newest cached poe.ninja character entry for account/character, or None."""
    hits = []
    for f in glob.glob(os.path.join(CACHE_DIR, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        k = d.get("key", "")
        if k.startswith("poeninja:char:") and k.endswith(f":{account}:{character}"):
            hits.append((d.get("_ts", 0), f, d.get("value")))
    hits.sort(reverse=True)
    return hits[0] if hits else None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", help="poe.ninja character URL")
    ap.add_argument("--account")
    ap.add_argument("--character")
    ap.add_argument("--league", help="override trade league")
    ap.add_argument("--links-only", action="store_true",
                    help="don't reduce to prices; just produce a trade link per item")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args()

    if a.url:
        try:
            p = poeninja.parse_build_url(a.url)
        except poeninja.PoeNinjaError as e:
            print(f"Error: {e}", file=sys.stderr); return 2
        account, character = p["account"], p["character"]
    elif a.account and a.character:
        account, character = a.account, a.character
    else:
        print("Provide a URL or --account and --character", file=sys.stderr); return 2

    hit = find_cached_char(account, character)
    if not hit:
        print(f"No cached data for {account}/{character} under {CACHE_DIR}.\n"
              "The cache only has builds you priced before. Check the spelling/discriminator.",
              file=sys.stderr)
        return 1
    ts, path, data = hit
    print(f"Recovered {account}/{character} from cache ({round((time.time()-ts)/3600,1)}h old)")
    print(f"  source file: {os.path.basename(path)}")

    meta, items = poeninja.normalize(data)
    meta.source_url = a.url or f"(recovered from cache) {account}/{character}"
    items = poeninja.dedupe_runes(items)
    print(f"  {meta.character} - {meta.char_class} level {meta.level} ({meta.league})")

    # Save the raw character data + the Path of Building import code.
    base = f"recovered_{account}_{character}".replace("#", "-")
    json.dump(data, open(base + ".json", "w", encoding="utf-8"), indent=1)
    pob = data.get("pathOfBuildingExport", "")
    if pob:
        open(base + ".pob.txt", "w", encoding="utf-8").write(pob)
    print(f"  saved {base}.json" +
          (f"  +  {base}.pob.txt  (paste into Path of Building -> Import)" if pob else ""))

    try:
        league = engine.resolve_trade_league(meta.league, a.league)
    except engine.EstimateError as e:
        print(f"  ! {e}", file=sys.stderr)
        league = a.league or meta.league
    print(f"  pricing/searching on trade league: {league!r}\n")

    progress = (lambda m: print("  " + m, file=sys.stderr)) if not a.quiet else None
    client = TradeClient(league, verbose=not a.quiet)
    pricer = Pricer(client, verbose=not a.quiet, progress=progress)
    results = pricer.price_build(items)

    if not a.links_only:
        print()
        print(report.render_text(meta, results, pricer.conv))
        payload = json.loads(report.render_json(meta, results, pricer.conv))
        json.dump(payload, open(base + "_prices.json", "w", encoding="utf-8"), indent=2)
        print(f"\nSaved prices + trade links to {base}_prices.json")

    print("\n--- Trade links (open in browser) ---")
    for r in results:
        if r.trade_url:
            print(f"{r.item.display_name}\n    {r.trade_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
