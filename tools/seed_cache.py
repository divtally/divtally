#!/usr/bin/env python3
"""Owner-PC community-cache seeder (B-001, D-0008).

Runs on the OWNER's machine only. It fetches the top-N popular PoE1 builds from the
poe.ninja ladder, prices each with the EXISTING local engine (same rate limiter + disk
caches as normal personal use), extracts per-item price records, and POSTs them to the
Cloudflare Worker cache (public/worker/worker.js). Visitors with nothing installed then
see those popular builds fully priced.

THE SITE / WORKER NEVER CALL pathofexile.com. Only THIS script (on the owner's PC) drives
the trade API, and only in the default "seed" mode. The two verification-safe modes make
ZERO trade calls:

    python tools/seed_cache.py --dry-run                 # list the top-N builds; price nothing
    python tools/seed_cache.py --from-cache-only --out payload.json
                                                         # build records from already-cached
                                                         # local results; no network at all

    python tools/seed_cache.py --worker-url https://poe1-price-cache.<sub>.workers.dev/cache
                                                         # LIVE seed (trade calls) -> POST

KEY RECIPE  (authoritative prose: docs/notes-public-worker.md; mirrored in the Worker's
comment header and the site/extension JS). Site, extension and this seeder MUST agree:

    key = "v1_" + sha256_hex( league_keyspace(league) + "\\x1d" + item_identity )[:32]

where item_identity is built ONLY from fields present in the engine->UI item contract
(what web.py sends the browser), so a visitor's client computes the identical key from the
same build data. See item_identity() below.
"""
import argparse
import glob
import hashlib
import json
import math
import os
import sys
import time
import unicodedata
from urllib import error as urlerror
from urllib import request as urlrequest

# --- make the repo importable (this file lives in tools/) --------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# poe.ninja build/account names are frequently non-ASCII (see docs/research); the default
# Windows cp1252 console would crash on print(). Force UTF-8 (replace on the rare unmappable).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from bpc import cache, engine                     # noqa: E402
from bpc.util import strip_rich                   # noqa: E402

# probe_ninja (research/) holds the poe.ninja-ONLY ladder helpers. It never touches trade.
sys.path.insert(0, os.path.join(ROOT, "research"))
import probe_ninja                                # noqa: E402


# =====================================================================================
# KEY RECIPE  — keep byte-for-byte in sync with docs/notes-public-worker.md + the JS.
# =====================================================================================
KEY_VERSION = "v1"
US, RS, GS = "\x1f", "\x1e", "\x1d"   # unit / record / group separators (never appear in mods)


def _canon(s: str) -> str:
    """NFC-normalise + trim. Applied to every name/mod so the seeder, site and extension
    hash identical bytes (mod strings the site receives are already strip_rich+strip'd;
    this is idempotent on those)."""
    return unicodedata.normalize("NFC", s or "").strip()


def league_keyspace(league: str) -> str:
    """Lowercased, whitespace-collapsed league — the form used in the key material AND the
    Worker's KV namespace. Mirrors worker.js::leagueKeyspace."""
    return " ".join(_canon(league).lower().split())


def item_identity(it: dict) -> str:
    """Stable identity string for one item, built ONLY from engine->UI contract fields
    (see web.py skeleton rows). `it` is a contract dict: {category, name, mods:{implicit,
    explicit}} for gear/flasks/jewels, or {category, name, level, quality, corrupted,
    supports:[{name,level,quality,corrupted}]} for gems.

    Design: identity deliberately EXCLUDES slot (an item's price is slot-independent) and
    is exact on rolls (the seeder and a visitor view the identical poe.ninja build, so
    equal items produce equal keys; cross-build accidental matches are a harmless bonus).
    """
    cat = (it.get("category") or "").lower()
    name = _canon(it.get("name") or "")
    if cat == "gem":
        sup = sorted(
            "%s~L%d~Q%d~%s" % (_canon(s.get("name") or ""), int(s.get("level") or 0),
                               int(s.get("quality") or 0), "c" if s.get("corrupted") else "n")
            for s in (it.get("supports") or []))
        parts = ["gem", name, "L%d" % int(it.get("level") or 0),
                 "Q%d" % int(it.get("quality") or 0),
                 "c" if it.get("corrupted") else "n", "|".join(sup)]
    else:
        mods = it.get("mods") or {}
        impl = sorted(_canon(m) for m in (mods.get("implicit") or []))
        expl = sorted(_canon(m) for m in (mods.get("explicit") or []))
        parts = [cat, name, RS.join(impl), RS.join(expl)]
    return US.join(parts)


def cache_key(league: str, it: dict) -> str:
    material = league_keyspace(league) + GS + item_identity(it)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return "%s_%s" % (KEY_VERSION, digest)


# =====================================================================================
# Item -> contract dict  (mirror of web.py's skeleton row builder, identity fields only)
# =====================================================================================
def contract_from_item(it) -> dict:
    """bpc.models.Item -> the same shape the browser receives (identity-relevant fields).
    Keeps normal (live) seeding and --from-cache-only (saved dicts) on ONE recipe."""
    if it.category == "gem":
        return {"category": "gem", "name": it.display_name,
                "level": it.gem_level, "quality": it.gem_quality,
                "corrupted": bool(it.corrupted),
                "supports": [{"name": s.get("name"), "level": s.get("level"),
                              "quality": s.get("quality"), "corrupted": s.get("corrupted")}
                             for s in (it.supports or [])]}
    return {"category": it.category, "name": it.display_name,
            "mods": {"implicit": [strip_rich(m).strip() for m in (it.implicit_mods or [])],
                     "explicit": [strip_rich(m).strip() for m in (it.explicit_mods or [])]}}


# =====================================================================================
# Price -> stored record  (subset of web.py::_result_dict; matches the Worker's whitelist)
# =====================================================================================
def _finite(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if (not math.isinf(x) and not math.isnan(x)) else None


def _has_tier(rec: dict) -> bool:
    c = rec.get("chaos") or {}
    return any(_finite(c.get(k)) is not None for k in ("min", "median", "high"))


def record_from_result(r) -> dict:
    return {"chaos": {"min": _finite(r.tier.minimum), "median": _finite(r.tier.median),
                      "high": _finite(r.tier.high)},
            "confidence": r.confidence, "method": r.method,
            "sample_size": int(r.sample_size or 0), "total_found": int(r.total_found or 0),
            "note": r.note or "", "trade_url": r.trade_url or ""}


def record_from_saved(p: dict) -> dict:
    ch = p.get("chaos") or {}
    return {"chaos": {"min": _finite(ch.get("min")), "median": _finite(ch.get("median")),
                      "high": _finite(ch.get("high"))},
            "confidence": p.get("confidence", "n/a"), "method": p.get("method", ""),
            "sample_size": int(p.get("sample_size") or 0),
            "total_found": int(p.get("total_found") or 0),
            "note": p.get("note", ""), "trade_url": p.get("trade_url", "")}


# =====================================================================================
# Worker POST  (batched; the only network the seeder does besides poe.ninja reads)
# =====================================================================================
MAX_ENTRIES = 60   # keep in sync with worker.js LIMITS.MAX_ENTRIES


def _cache_endpoint(worker_url: str) -> str:
    u = worker_url.rstrip("/")
    return u if u.endswith("/cache") else u + "/cache"


def post_entries(worker_url: str, league: str, entries: dict) -> dict:
    """POST one league's entries in <=MAX_ENTRIES batches. Returns aggregate counts."""
    endpoint = _cache_endpoint(worker_url)
    items = list(entries.items())
    stored = rejected = batches = 0
    for i in range(0, len(items), MAX_ENTRIES):
        chunk = dict(items[i:i + MAX_ENTRIES])
        body = json.dumps({"league": league, "entries": chunk}).encode("utf-8")
        req = urlrequest.Request(endpoint, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                j = json.loads(resp.read() or "{}")
        except urlerror.URLError as e:
            print("  ! POST failed: %s" % e)
            continue
        stored += int(j.get("stored") or 0)
        rejected += int(j.get("rejected") or 0)
        batches += 1
    return {"stored": stored, "rejected": rejected, "batches": batches}


# =====================================================================================
# Ladder resolution (poe.ninja only — cheap, cached, never trade)
# =====================================================================================
def resolve_ladder(slug, count):
    s = probe_ninja.session()
    idx = probe_ninja.index_state(s)
    slug = slug or idx["snapshotVersions"][0]["url"]
    version, snapname, league = probe_ninja.resolve_league(idx, slug)
    rows = probe_ninja.search_rows(s, version, snapname, limit=count)
    return slug, version, snapname, league, rows[:count]


# =====================================================================================
# Saved-result harvest for --from-cache-only (pure disk read; NO network at all)
# =====================================================================================
def saved_results():
    out = []
    for f in glob.glob(os.path.join(cache.CACHE_DIR, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        k = d.get("key", "")
        if not k.startswith("result:poeninja:char:"):
            continue
        v = d.get("value") or {}
        if not v.get("priced") or not v.get("items"):
            continue
        meta = v.get("meta") or {}
        out.append({"key": k, "ts": v.get("ts") or d.get("_ts", 0), "meta": meta,
                    "items": v.get("items") or [], "priced": v.get("priced") or {}})
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def entries_for_saved(sr) -> tuple:
    """(league, {key: record}) for one saved build. Only rows with a finite tier are kept
    (skipped/unpriceable rows carry no number -> no cache entry, per the guardrail)."""
    league = (sr["meta"] or {}).get("league", "") or ""
    items, priced = sr["items"], sr["priced"]
    entries = {}
    for idx_str, p in priced.items():
        try:
            i = int(idx_str)
        except (TypeError, ValueError):
            continue
        if i >= len(items):
            continue
        rec = record_from_saved(p)
        if _has_tier(rec):
            entries[cache_key(league, items[i])] = rec
    return league, entries


# =====================================================================================
# Modes
# =====================================================================================
def cmd_dry_run(args):
    slug, version, snapname, league, rows = resolve_ladder(args.league, args.count)
    print("DRY RUN -- nothing is priced, nothing is POSTed.")
    print("league slug=%s  display=%s  snapshot=%s  version=%s" % (slug, league, snapname, version))
    print("top %d popular builds that WOULD be priced (local engine, rate-limited) and "
          "POSTed to %s:" % (len(rows), args.worker_url or "(no --worker-url given)"))
    for i, row in enumerate(rows, 1):
        url = probe_ninja.user_url(slug, row["account"], row["name"])
        print("  %2d. %-24s %s" % (i, row["account"], row["name"]))
        print("      %s" % url)
    print("(seed for real by re-running WITHOUT --dry-run and WITH --worker-url.)")
    return 0


def cmd_from_cache(args):
    print("FROM-CACHE-ONLY -- zero trade calls; records built from already-priced local "
          "results on disk (%s)." % cache.CACHE_DIR)
    wanted = league_keyspace(args.league) if args.league else None
    picked, payloads, total = [], [], 0
    for sr in saved_results():
        league, entries = entries_for_saved(sr)
        if wanted and league_keyspace(league) != wanted:
            continue
        if not entries:
            continue
        picked.append((sr, league, entries))
        if len(picked) >= args.count:
            break
    for sr, league, entries in picked:
        meta = sr["meta"]
        print("  %-20s %-16s league=%-12s records=%d"
              % (meta.get("character", "?"), meta.get("class", ""), league, len(entries)))
        payloads.append({"league": league, "entries": entries})
        total += len(entries)
    print("builds harvested: %d   total records: %d" % (len(picked), total))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payloads, f, ensure_ascii=False, indent=1)
        print("wrote POST payloads -> %s (inspect; nothing was sent)" % args.out)
    if args.worker_url:
        for p in payloads:
            res = post_entries(args.worker_url, p["league"], p["entries"])
            print("  POST league=%s -> stored=%d rejected=%d (%d batch(es))"
                  % (p["league"], res["stored"], res["rejected"], res["batches"]))
    elif not args.out:
        print("(pass --out FILE to dump payloads, or --worker-url URL to upload.)")
    return 0


def cmd_seed(args):
    if not args.worker_url:
        print("ERROR: live seeding needs --worker-url (or use --dry-run / --from-cache-only).")
        return 2
    slug, version, snapname, league, rows = resolve_ladder(args.league, args.count)
    print("SEEDING %d builds on %s -> %s" % (len(rows), league, _cache_endpoint(args.worker_url)))
    grand_stored = 0
    for i, row in enumerate(rows, 1):
        url = probe_ninja.user_url(slug, row["account"], row["name"])
        print("[%d/%d] %s / %s" % (i, len(rows), row["account"], row["name"]))
        try:
            # LIVE: this is the ONLY trade-touching call in the whole system. It honours the
            # engine's persistent rate limiter + disk cache (same footprint as personal use).
            meta, results, pricer, trade_league = engine.run_estimate(url)
        except Exception as e:
            print("  ! skipped (%s)" % e)
            continue
        key_league = meta.league or trade_league
        entries = {}
        for r in results:
            rec = record_from_result(r)
            if _has_tier(rec):
                entries[cache_key(key_league, contract_from_item(r.item))] = rec
        if not entries:
            print("  (no priceable rows)")
        else:
            res = post_entries(args.worker_url, key_league, entries)
            grand_stored += res["stored"]
            print("  priced %d rows -> stored=%d rejected=%d" % (len(entries), res["stored"], res["rejected"]))
        if args.delay and i < len(rows):
            time.sleep(args.delay)
    print("done. total records stored: %d" % grand_stored)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Seed the PoE1 community price cache from the "
                                             "top-N poe.ninja builds (owner PC only).")
    ap.add_argument("--count", "-n", type=int, default=15, help="number of top builds (default 15)")
    ap.add_argument("--league", default=None, help="league url slug (default: current/first snapshot)")
    ap.add_argument("--worker-url", default=None, help="Worker cache endpoint (…/cache). Required to actually POST.")
    ap.add_argument("--dry-run", action="store_true", help="list the top-N builds; price nothing, POST nothing")
    ap.add_argument("--from-cache-only", action="store_true",
                    help="build records ONLY from already-priced local results on disk; zero trade calls")
    ap.add_argument("--out", default=None, help="(with --from-cache-only) write the POST payloads to a JSON file")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds to pause between builds when seeding live")
    args = ap.parse_args(argv)

    if args.dry_run:
        return cmd_dry_run(args)
    if args.from_cache_only:
        return cmd_from_cache(args)
    return cmd_seed(args)


if __name__ == "__main__":
    sys.exit(main())
