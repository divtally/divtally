"""Public pipeline: input (poe.ninja char URL / PoB code / PoB paste link) -> normalised
items -> poe.ninja pricing + built trade queries. NO pathofexile.com calls.

ADAPTED from bpc/engine.py. Differences:
  * builds a `querybuild.PublicPricer` (no TradeClient) instead of a trade `Pricer`.
  * league resolution is poe.ninja-only: an override wins, else the poe.ninja-resolved
    league (challenge-league display names equal the trade league id -- verified against
    the trade `data/leagues` fixture), else (PoB, no league) poe.ninja's current challenge
    league. The parent's `resolve_trade_league` called the trade `data/leagues` endpoint;
    that is forbidden here.
  * StatMapper + valid base types come from the BUNDLED reference data (refdata), built
    once per process.
"""
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from . import poeninja, pob, refdata
from ._http import get_text
from .currency import CurrencyConverter
from .models import BuildMeta, PriceResult
from .querybuild import PublicPricer
from .statmap import StatMapper

# Only these hosts may be fetched server-side for a PoB paste (no arbitrary URLs / SSRF).
_POB_LINK_HOSTS = ("pobb.in", "pastebin.com", "poe.ninja")

_mapper_singleton: Optional[StatMapper] = None
_types_singleton: Optional[dict] = None


class EstimateError(RuntimeError):
    """A user-facing problem (bad URL, unmatched league, fetch failure)."""


def _mapper() -> StatMapper:
    global _mapper_singleton
    if _mapper_singleton is None:
        _mapper_singleton = StatMapper(refdata.stats_data())
    return _mapper_singleton


def _types() -> dict:
    global _types_singleton
    if _types_singleton is None:
        _types_singleton = refdata.item_types()
    return _types_singleton


def resolve_league(meta_league: str, override: Optional[str], client: poeninja.PoeNinjaClient) -> str:
    """Best trade-league id WITHOUT any trade call. Override wins; else the poe.ninja league
    (equal to the trade id for challenge leagues); else the current challenge league."""
    if override:
        return override
    if meta_league:
        return meta_league
    try:
        return client.current_challenge_league()
    except Exception:
        return "Standard"


def _make_pricer(trade_league: str, status: str) -> PublicPricer:
    econ = poeninja.PoeNinjaEconomy(trade_league)
    return PublicPricer(trade_league, econ, _mapper(), _types().get("all", set()), status=status)


def prepare_from_url(url: str, league: Optional[str] = None, status: str = "online"):
    """Fetch + normalise a poe.ninja character; build a PublicPricer. No pricing yet."""
    client = poeninja.PoeNinjaClient()
    # A malformed/overview/PoE2/wrong-host URL is a CLIENT input mistake, not an upstream
    # failure: re-raise it as EstimateError so build.py returns 400 bad_input (contract sec.4
    # lists a build-overview link under bad_input), reserving ninja_error/502 for genuine
    # fetch failures from fetch_character below (R1: overview + PoE2 links were 502 ninja_error).
    try:
        parsed = poeninja.parse_build_url(url)
    except poeninja.PoeNinjaError as e:
        raise EstimateError(str(e))
    data = client.fetch_character(**parsed)                # genuine fetch failures stay 502
    meta, items = poeninja.normalize(data)
    meta.source_url = url
    trade_league = resolve_league(meta.league, league, client)
    return meta, items, _make_pricer(trade_league, status), trade_league


def _pob_raw_candidates(url: str) -> List[str]:
    p = urlparse(url if "//" in url else "https://" + url)
    host, path = p.netloc.lower(), p.path.rstrip("/")
    cands = []
    if "pobb.in" in host:
        cands.append(f"https://pobb.in{path}/raw")
    elif "pastebin.com" in host:
        cands.append(f"https://pastebin.com/raw/{path.strip('/').split('/')[-1]}")
    cands += [url.rstrip("/") + "/raw", url]
    return cands


def _fetch_pob_link(url: str) -> str:
    """Fetch a PoB code from an allowlisted paste host (pobb.in / pastebin / poe.ninja)."""
    host = urlparse(url if "//" in url else "https://" + url).netloc.lower()
    if not any(h == host or host.endswith("." + h) for h in _POB_LINK_HOSTS):
        raise EstimateError(f"{host or url!r} isn't a supported build host. Paste a "
                            "pobb.in/pastebin/poe.ninja link or the PoB code itself.")
    for cand in _pob_raw_candidates(url):
        ok, _status, text = get_text(cand, timeout=30)
        if ok and text and pob.looks_like_code(text):
            return text.strip()
    raise EstimateError("couldn't get a Path of Building code from that link "
                        "(try pasting the code itself).")


def prepare_from_pob(code_or_xml: str, league: Optional[str] = None, status: str = "online"):
    """Build a PublicPricer from a PoB code/XML. PoB codes carry no league -> `league` or
    poe.ninja's current challenge league."""
    client = poeninja.PoeNinjaClient()
    trade_league = resolve_league("", league, client)
    try:
        meta, items = pob.parse(code_or_xml, _types())
    except pob.PobError as e:
        raise EstimateError(str(e))
    meta.league = trade_league
    meta.source_url = "(Path of Building import)"
    return meta, items, _make_pricer(trade_league, status), trade_league


def prepare_auto(text: str, league: Optional[str] = None, status: str = "online"):
    """Detect poe.ninja character link / PoB paste link / raw PoB code and route."""
    t = (text or "").strip()
    if not t:
        raise EstimateError("paste a poe.ninja character link or a Path of Building code.")
    low = t.lower()
    if low.startswith("http") or "poe.ninja/" in low or "pobb.in/" in low or "pastebin.com/" in low:
        p = urlparse(t if "//" in t else "https://" + t)
        host, path = p.netloc.lower(), p.path.lower()
        if "poe.ninja" in host and "/character/" in path:
            return prepare_from_url(t, league, status)
        if ("pobb.in" in host or "pastebin.com" in host
                or ("poe.ninja" in host and "/pob/" in path)):
            code = _fetch_pob_link(t)
            return prepare_from_pob(code, league, status)
        if "poe.ninja" in host:
            return prepare_from_url(t, league, status)     # -> helpful error
        code = _fetch_pob_link(t)
        return prepare_from_pob(code, league, status)
    if pob.looks_like_code(t):
        return prepare_from_pob(t, league, status)
    raise EstimateError("that's not a recognised poe.ninja character link, Path of "
                        "Building code, or PoB paste link.")


def run_estimate(text: str, league: Optional[str] = None, status: str = "online"
                 ) -> Tuple[BuildMeta, List[PriceResult], PublicPricer, str]:
    """Full public pipeline (fetch + price everything from poe.ninja + build trade queries)."""
    meta, items, pricer, trade_league = prepare_auto(text, league, status)
    results = pricer.price_build(items)
    return meta, results, pricer, trade_league
