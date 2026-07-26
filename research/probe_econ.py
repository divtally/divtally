"""Live-probe the poe.ninja PoE1 ECONOMY API (currency rates + gem prices).

Run from the repo root:  python research/probe_econ.py

Writes representative responses to research/data/ninja_econ_*.json and prints a
compact summary. Hits ONLY poe.ninja (never pathofexile.com trade endpoints).

VERIFIED ENDPOINTS (live, 2026-07-26, league "Allflame"):
  index-state : GET https://poe.ninja/poe1/api/data/index-state
  currency    : GET https://poe.ninja/poe1/api/economy/exchange/current/overview
                    ?league=<Name>&type=Currency          (also: Fragment, Essence,
                    Scarab, DivinationCard, Oil, Fossil, Resonator, DeliriumOrb, Omen,
                    Tattoo, Artifact -- the bulk / stackable "exchange" categories)
  gems/items  : GET https://poe.ninja/poe1/api/economy/stash/current/item/overview
                    ?league=<Name>&type=SkillGem          (also: UniqueJewel, ClusterJewel,
                    UniqueWeapon/Armour/Accessory/Flask, BaseType -- the variant-bearing
                    "item" categories)

The OLD classic PoE1 paths /api/data/currencyoverview and /api/data/itemoverview are
GONE (HTTP 404 "not found") as of 2026-07. poe.ninja unified PoE1 + PoE2 under the same
new /<game>/api/economy/... structure.
"""
import json
import os
import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 buildpricechecker-poe1/0.1")
BASE = "https://poe.ninja/poe1/api"
EXCHANGE = BASE + "/economy/exchange/current/overview"   # currency-like / stackable
ITEM = BASE + "/economy/stash/current/item/overview"      # gems / uniques / jewels
INDEX_STATE = BASE + "/data/index-state"
OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT, exist_ok=True)

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                  "Referer": "https://poe.ninja/poe1/economy"})


def get(url, params=None):
    r = S.get(url, params=params, timeout=40)
    print(f"GET {r.url} -> HTTP {r.status_code} ({len(r.content)} bytes)")
    r.raise_for_status()
    time.sleep(0.8)
    return r.json()


def dump(name, obj):
    path = os.path.join(OUT, f"ninja_econ_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print(f"  wrote {path} ({os.path.getsize(path)} bytes)")


def current_league():
    idx = get(INDEX_STATE)
    dump("index_state", idx)
    econ = idx.get("economyLeagues", []) or []
    print("  economyLeagues:", [l.get("name") for l in econ])
    for l in econ:                       # first challenge league (skip perma-leagues)
        if l.get("name") not in ("Standard", "Hardcore"):
            return l["name"]
    return econ[0]["name"] if econ else "Standard"


def main():
    league = current_league()
    print("Current league:", league)

    # 1) Currency (chaos rates). primaryValue is in CHAOS (PoE1 primary). core.rates.divine
    #    = divine-per-chaos; chaos-per-divine = Divine Orb line's primaryValue.
    cur = get(EXCHANGE, {"league": league, "type": "Currency"})
    dump("currency", cur)
    core = cur.get("core", {})
    id2name = {it["id"]: it.get("name", "") for it in
               (cur.get("items", []) or []) + (core.get("items", []) or [])}
    print("  core.primary=%s secondary=%s rates=%s"
          % (core.get("primary"), core.get("secondary"), core.get("rates")))
    for wid in ("divine", "exalted", "mirror", "chaos", "annul", "vaal"):
        ln = next((l for l in cur["lines"] if l["id"] == wid), None)
        print("    %-8s (%s): %s chaos"
              % (wid, id2name.get(wid, "?"), ln["primaryValue"] if ln else "n/a"))

    # 2) SkillGem (active + support + transfigured + awakened, all in one list)
    gems = get(ITEM, {"league": league, "type": "SkillGem"})
    dump("skillgem", gems)
    lines = gems.get("lines", [])
    print("  SkillGem lines:", len(lines))
    if lines:
        print("  line keys:", list(lines[0].keys()))
    # a readable trimmed sample: every bucket of a few representative gems
    sample = {"_endpoint": ITEM, "_league": league, "_note": "trimmed sample of buckets",
              "lines": [l for l in lines
                        if l["name"] in ("Spark", "Arc", "Determination",
                                         "Awakened Enhance Support", "Empower Support",
                                         "Arc of Oscillating")]}
    dump("skillgem_sample", sample)

    # 3) Item-endpoint categories that matter as pricing fallbacks (counts only)
    for t in ("UniqueJewel", "ClusterJewel", "UniqueWeapon", "UniqueArmour",
              "UniqueAccessory", "UniqueFlask", "BaseType"):
        try:
            j = get(ITEM, {"league": league, "type": t})
            print(f"  item type={t}: {len(j.get('lines', []))} lines")
        except Exception as e:
            print(f"  item type={t} failed:", repr(e)[:80])

    print("Done. League:", league)


if __name__ == "__main__":
    main()
