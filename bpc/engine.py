"""Shared pipeline used by both the CLI and the web UI:
URL -> poe.ninja items -> trade2 pricing -> (meta, results, converter).

Keeping this in one place means the two front-ends behave identically and the
rate-limit-sensitive trade logic has a single code path.
"""
import glob
import json
import os
import re
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from . import cache, poeninja, pob, pricing
from .models import BuildMeta, PriceResult
from .pricing import Pricer
from .trade import TradeClient, TradeError

Progress = Optional[Callable[[str], None]]

# Only these hosts may be fetched server-side for a PoB paste (no arbitrary URLs / SSRF).
_POB_LINK_HOSTS = ("pobb.in", "pastebin.com", "poe.ninja", "poe2.ninja")


class EstimateError(RuntimeError):
    """A user-facing problem (bad URL, unmatched league, fetch failure)."""


def _norm_league(s: str) -> str:
    """Normalise a league name for matching: lower-case, 'hardcore'->'hc', and drop the
    non-tradeable 'ssf' qualifier (SSF builds price against the tradeable equivalent)."""
    s = s.lower().replace("hardcore", "hc")
    return " ".join(t for t in re.split(r"\s+", s) if t and t != "ssf")


def resolve_trade_league(meta_league: str, override: Optional[str] = None) -> str:
    """Map the build's league to a current trade league id.
    Raises EstimateError (listing valid leagues) if it can't be matched."""
    if override:
        return override
    try:
        ids = [l.get("id", "") for l in TradeClient.list_leagues() if l.get("id")]
    except Exception:
        return meta_league  # couldn't verify; proceed with the build's own league
    if meta_league in ids:
        return meta_league
    hit = {_norm_league(i): i for i in ids}.get(_norm_league(meta_league))
    if hit:
        return hit
    raise EstimateError(
        f"League {meta_league!r} is not a current trade league. "
        f"Available: {', '.join(ids)}. Re-run with an explicit league override.")


def prepare(url: str, league: Optional[str] = None, refresh: bool = False,
            progress: Progress = None, status: str = "online"):
    """Fetch + normalise the build and build a Pricer, WITHOUT pricing anything yet.
    Returns (meta, items, pricer, trade_league). Lets a front-end drive pricing
    item-by-item (e.g. the interactive web flow). Raises PoeNinjaError/EstimateError."""
    if refresh:
        cache.disable_reads()
    parsed = poeninja.parse_build_url(url)  # PoeNinjaError on bad URL
    if progress:
        progress(f"Fetching {parsed['account']}/{parsed['character']} from poe.ninja...")
    data = poeninja.PoeNinjaClient().fetch_character(**parsed)

    meta, items = poeninja.normalize(data)
    meta.source_url = url
    items = poeninja.dedupe_runes(items)

    trade_league = resolve_trade_league(meta.league, league)
    client = TradeClient(trade_league, verbose=False)
    pricer = Pricer(client, verbose=False, progress=progress, status=status)
    pricer.economy = poeninja.PoeNinjaEconomy(meta.league)   # gem prices w/o the trade API
    return meta, items, pricer, trade_league


def list_cached_builds() -> List[dict]:
    """Every poe.ninja character build currently on disk in the cache, newest first.
    Each cached snapshot version is a separate entry (the same character priced on two
    different days appears twice)."""
    out = []
    for f in glob.glob(os.path.join(cache.CACHE_DIR, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        k = d.get("key", "")
        if not k.startswith("poeninja:char:"):
            continue
        parts = k[len("poeninja:char:"):].split(":")   # version:account:character
        if len(parts) < 3:
            continue
        version, account, character = parts[0], parts[1], ":".join(parts[2:])
        v = d.get("value") or {}
        out.append({
            "key": k, "ts": d.get("_ts", 0), "version": version, "account": account,
            "character": v.get("name") or character, "char_class": v.get("class", ""),
            "level": int(v.get("level", 0) or 0), "league": v.get("league", ""),
        })
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def prepare_from_cache(cache_key: str, league: Optional[str] = None,
                       progress: Progress = None, status: str = "online"):
    """Like prepare(), but rebuild the build from a cached poe.ninja response on disk
    (works even if the profile has since been removed from poe.ninja)."""
    data = cache.peek(cache_key)
    if not isinstance(data, dict) or "items" not in data:
        raise EstimateError("that cached build is no longer available on disk.")
    if progress:
        progress("Loading build from local cache...")
    meta, items = poeninja.normalize(data)
    meta.source_url = poeninja.build_url_from_cache_key(cache_key) or "(loaded from local cache)"
    meta.cache_key = cache_key
    items = poeninja.dedupe_runes(items)
    trade_league = resolve_trade_league(meta.league, league)
    client = TradeClient(trade_league, verbose=False)
    pricer = Pricer(client, verbose=False, progress=progress, status=status)
    pricer.economy = poeninja.PoeNinjaEconomy(meta.league)   # gem prices w/o the trade API
    return meta, items, pricer, trade_league


def _default_trade_league() -> str:
    """Best guess at the current softcore challenge league (PoB codes carry no league)."""
    try:
        ids = [l.get("id", "") for l in TradeClient.list_leagues() if l.get("id")]
    except Exception:
        return "Standard"
    for lid in ids:
        low = lid.lower()
        if "standard" not in low and not low.startswith("hc") and "hardcore" not in low:
            return lid
    return ids[0] if ids else "Standard"


def _pob_raw_candidates(url: str) -> List[str]:
    """Raw-code URLs to try for a PoB paste link, most specific first."""
    p = urlparse(url if "//" in url else "https://" + url)
    host, path = p.netloc.lower(), p.path.rstrip("/")
    cands = []
    if "pobb.in" in host:
        cands.append(f"https://pobb.in{path}/raw")
    elif "pastebin.com" in host:
        cands.append(f"https://pastebin.com/raw/{path.strip('/').split('/')[-1]}")
    cands += [url.rstrip("/") + "/raw", url]   # generic fallbacks (poe.ninja/pob, etc.)
    return cands


def _fetch_pob_link(url: str, progress: Progress = None) -> str:
    """Fetch a Path of Building code from a known paste host (pobb.in / pastebin /
    poe.ninja). Restricted to an allowlist to avoid fetching arbitrary user URLs."""
    if progress:
        progress("Fetching Path of Building code from link...")
    host = urlparse(url if "//" in url else "https://" + url).netloc.lower()
    if not any(h == host or host.endswith("." + h) for h in _POB_LINK_HOSTS):
        raise EstimateError(f"{host or url!r} isn't a supported build host. Paste a "
                            "pobb.in/pastebin/poe.ninja link or the PoB code itself.")
    sess = requests.Session()
    sess.headers.update({"User-Agent": poeninja.UA})
    for cand in _pob_raw_candidates(url):
        try:
            r = sess.get(cand, timeout=30)
        except requests.RequestException:
            continue
        if r.ok and len(r.content) < 2_000_000 and pob.looks_like_code(r.text):
            return r.text.strip()
    raise EstimateError("couldn't get a Path of Building code from that link "
                        "(try pasting the code itself).")


def prepare_from_pob(code_or_xml: str, league: Optional[str] = None, refresh: bool = False,
                     progress: Progress = None, status: str = "online"):
    """Build a Pricer from a Path of Building code/XML (no poe.ninja needed). PoB codes
    carry no league, so we price against `league` or the current softcore league."""
    if refresh:
        cache.disable_reads()
    trade_league = league or _default_trade_league()
    client = TradeClient(trade_league, verbose=False)
    if progress:
        progress("Reading Path of Building items...")
    try:
        types = pricing.load_item_types(client)
        meta, items = pob.parse(code_or_xml, types)
    except (pob.PobError, TradeError) as e:
        raise EstimateError(str(e))
    meta.league = trade_league
    meta.source_url = "(Path of Building import)"
    items = poeninja.dedupe_runes(items)
    pricer = Pricer(client, verbose=False, progress=progress, status=status)
    pricer.economy = poeninja.PoeNinjaEconomy(meta.league)   # gem prices w/o the trade API
    return meta, items, pricer, trade_league


def prepare_auto(text: str, league: Optional[str] = None, refresh: bool = False,
                 progress: Progress = None, status: str = "online"):
    """Detect what the user pasted (poe.ninja character link / PoB paste link / raw PoB
    code) and route to the right loader."""
    t = (text or "").strip()
    if not t:
        raise EstimateError("paste a poe.ninja character link or a Path of Building code.")
    low = t.lower()
    if low.startswith("http") or "poe.ninja/" in low or "pobb.in/" in low or "pastebin.com/" in low:
        p = urlparse(t if "//" in t else "https://" + t)
        host, path = p.netloc.lower(), p.path.lower()
        if "poe.ninja" in host and "/character/" in path:
            return prepare(t, league, refresh, progress, status)
        if ("pobb.in" in host or "pastebin.com" in host or "poe2.ninja" in host
                or ("poe.ninja" in host and "/pob/" in path)):
            code = _fetch_pob_link(t, progress)
            return prepare_from_pob(code, league, refresh, progress, status)
        if "poe.ninja" in host:                 # poe.ninja but not a character/pob link
            return prepare(t, league, refresh, progress, status)   # -> helpful error
        code = _fetch_pob_link(t, progress)      # other host: allowlisted, else rejected
        return prepare_from_pob(code, league, refresh, progress, status)
    if pob.looks_like_code(t):
        return prepare_from_pob(t, league, refresh, progress, status)
    raise EstimateError("that's not a recognised poe.ninja character link, Path of "
                        "Building code, or PoB paste link.")


def run_estimate(url: str, league: Optional[str] = None, refresh: bool = False,
                 progress: Progress = None, status: str = "online"
                 ) -> Tuple[BuildMeta, List[PriceResult], Pricer, str]:
    """Full pipeline (fetch + price everything). Used by the CLI."""
    meta, items, pricer, trade_league = prepare_auto(url, league, refresh, progress, status)
    if progress:
        n_price = sum(1 for it in items if it.category != "gem")
        progress(f"Pricing {n_price} items + gems on '{trade_league}' (rate-limited)...")
    results = pricer.price_build(items)
    return meta, results, pricer, trade_league
