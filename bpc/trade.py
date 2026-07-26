"""Client for the official PoE1 trade API (www.pathofexile.com/api/trade).

Everything here is unauthenticated GET/POST. The single most important job of this
module is to NEVER trip GGG's rate limiter (a violation yields IP bans of 5-30 min).
We therefore:
  * start with conservative rules,
  * tighten/relax to whatever the server reports in X-Rate-Limit-<bucket> headers,
  * proactively sleep before a call would exceed a safety fraction of any rule,
  * honour 429 Retry-After (or a full-window back-off) with a single retry.
"""
import email.utils
import math
import random
import time
import urllib.parse
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from . import cache

# PoE1 realm: /api/trade (NOT /api/trade2, and no /poe2/ path segment). PC is the default
# realm; xbox/sony would use ?realm=xbox|sony (unused here).
BASE = "https://www.pathofexile.com/api/trade"

# Contact info in the UA is good etiquette and what GGG asks for.
USER_AGENT = ("buildpricechecker/0.1 (PoE1 build cost estimator; "
              "contact: divtally@gmail.com)")

# Conservative starting rules per logical endpoint: list of (max_hits, window_secs).
# update_rules() only ever tightens these from the authoritative response headers.
# Seeded from the LIVE X-Rate-Limit-Ip headers observed 2026-07-26 (docs/research/trade1.md
# section 7): search adds a 4th 6h window, fetch adds 300s + 6h windows, exchange matches.
# (Reference 'data' endpoints send no rate headers; use a search-like floor anyway.)
_DEFAULT_RULES = {
    "search":   [(5, 10), (15, 60), (30, 300), (600, 21600)],
    "fetch":    [(12, 4), (16, 12), (50, 300), (1000, 21600)],
    "exchange": [(5, 15), (10, 90), (30, 300)],
    "data":     [(5, 10), (15, 60)],
}


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse a Retry-After header: delta-seconds or an HTTP-date (RFC 7231).
    Returns seconds to wait, or None if unparseable."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


class RateLimiter:
    """Sliding-window limiter that keeps usage under `margin` * each rule's cap."""

    def __init__(self, rules: List[tuple], margin: float = 0.7):
        self.rules = list(rules)
        self._floor = dict((w, c) for c, w in rules)  # window -> conservative cap
        self.margin = margin
        self.hits: deque = deque()  # monotonic timestamps of past requests

    def _effective_cap(self, cap: int) -> int:
        if cap <= 1:
            return 1
        # stay strictly below the real cap, and below margin*cap
        return max(1, min(cap - 1, int(math.floor(cap * self.margin))))

    def wait(self) -> None:
        now = time.monotonic()
        # prune anything older than the largest window
        max_window = max((w for _, w in self.rules), default=0)
        while self.hits and now - self.hits[0] > max_window:
            self.hits.popleft()

        sleep_for = 0.0
        for cap, window in self.rules:
            eff = self._effective_cap(cap)
            recent = [t for t in self.hits if now - t <= window]
            if len(recent) >= eff:
                # need the oldest in-window hit to age out
                oldest = recent[-eff]
                need = window - (now - oldest)
                sleep_for = max(sleep_for, need)
        if sleep_for > 0:
            time.sleep(sleep_for + random.uniform(0.05, 0.25))

    def record(self) -> None:
        self.hits.append(time.monotonic())

    def update_rules(self, rule_header: Optional[str]) -> None:
        """Merge authoritative server rules (header like '5:10:60,15:60:300') with our
        conservative defaults. We only ever TIGHTEN: every default window is kept, and
        for any window the effective cap is the min of default and server. This prevents
        a malformed/short header from silently widening the limiter past GGG's real cap
        (which would risk an IP ban). PoE1 headers are the same 3-part hits:window:penalty
        format PoE2 used, so parsing bits[0]:bits[1] is unchanged."""
        if not rule_header:
            return
        # start from the floor so default windows are never dropped
        merged = dict(self._floor)
        for part in rule_header.split(","):
            bits = part.split(":")
            if len(bits) >= 2:
                try:
                    cap, window = int(bits[0]), int(bits[1])
                except ValueError:
                    continue
                merged[window] = min(merged.get(window, cap), cap)
        self.rules = sorted(((c, w) for w, c in merged.items()), key=lambda t: t[1])

    def backoff_seconds(self) -> float:
        """A safe sleep when the server says we're limited but gives no usable hint:
        the longest window we track (the penalty period is at least that long)."""
        return max((w for _, w in self.rules), default=60)


class TradeError(RuntimeError):
    pass


class TradeClient:
    def __init__(self, league: str, verbose: bool = True):
        self.league = league
        self.verbose = verbose
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.limiters: Dict[str, RateLimiter] = {
            k: RateLimiter(v) for k, v in _DEFAULT_RULES.items()
        }
        self.search_count = 0  # for progress / budget reporting

    # ---- low level -------------------------------------------------------
    def _request(self, kind: str, method: str, url: str, *, json_body: Any = None,
                 headers: Optional[dict] = None, _attempt: int = 0) -> Any:
        lim = self.limiters[kind]
        lim.wait()
        try:
            r = self.s.request(method, url, json=json_body, headers=headers, timeout=30)
        except requests.RequestException as e:
            if _attempt < 2:
                time.sleep(2 + _attempt * 2)
                return self._request(kind, method, url, json_body=json_body,
                                     headers=headers, _attempt=_attempt + 1)
            raise TradeError(f"network error calling {url}: {e}")
        finally:
            lim.record()

        # learn the authoritative rules
        lim.update_rules(r.headers.get("X-Rate-Limit-Ip"))

        if r.status_code == 429:
            retry = _parse_retry_after(r.headers.get("Retry-After"))
            if retry is None:
                retry = lim.backoff_seconds()  # no usable hint -> wait a full window
            retry = max(5.0, min(retry, 1800.0))
            if self.verbose:
                print(f"  [rate-limited; backing off {retry:.0f}s]")
            time.sleep(retry + 1)
            if _attempt < 1:  # one retry after a full back-off is enough
                return self._request(kind, method, url, json_body=json_body,
                                     headers=headers, _attempt=_attempt + 1)
            raise TradeError("repeatedly rate-limited by trade API; try again later")

        if r.status_code in (500, 502, 503, 504) and _attempt < 2:
            time.sleep(3 + _attempt * 3)
            return self._request(kind, method, url, json_body=json_body,
                                 headers=headers, _attempt=_attempt + 1)

        if not r.ok:
            raise TradeError(f"HTTP {r.status_code} from {url}: {r.text[:200]}")
        ctype = r.headers.get("content-type", "")
        if "json" not in ctype:
            raise TradeError(f"non-JSON ({ctype}) from {url}: {r.text[:200]}")
        return r.json()

    # ---- reference data (cached on disk for a day) -----------------------
    def static_data(self) -> dict:
        return cache.cached("trade:data:static", 86400,
                            lambda: self._request("data", "GET", f"{BASE}/data/static"))

    def stats_data(self) -> dict:
        return cache.cached("trade:data:stats", 86400,
                            lambda: self._request("data", "GET", f"{BASE}/data/stats"))

    @staticmethod
    def list_leagues() -> List[dict]:
        def fetch():
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
            r = s.get(f"{BASE}/data/leagues", timeout=30)
            r.raise_for_status()
            return r.json().get("result", [])
        return cache.cached("trade:data:leagues", 600, fetch)  # leagues rarely change

    # ---- search + fetch --------------------------------------------------
    def search(self, query: dict) -> dict:
        url = f"{BASE}/search/{urllib.parse.quote(self.league)}"
        body = {"query": query, "sort": {"price": "asc"}}
        hdr = {"Content-Type": "application/json",
               "Origin": "https://www.pathofexile.com",
               "Referer": "https://www.pathofexile.com/trade/search"}
        self.search_count += 1
        return self._request("search", "POST", url, json_body=body, headers=hdr)

    def fetch(self, ids: List[str], query_id: str) -> List[dict]:
        if not ids:
            return []
        idpart = ",".join(ids[:10])  # API caps at 10 ids per fetch (11 -> HTTP 400)
        url = f"{BASE}/fetch/{idpart}?query={query_id}"
        data = self._request("fetch", "GET", url)
        return data.get("result", []) or []

    def exchange(self, want: str, have: str = "chaos") -> dict:
        url = f"{BASE}/exchange/{urllib.parse.quote(self.league)}"
        body = {"query": {"status": {"option": "online"}, "have": [have], "want": [want]},
                "sort": {"have": "asc"}, "engine": "new"}
        hdr = {"Content-Type": "application/json"}
        return self._request("exchange", "POST", url, json_body=body, headers=hdr)
