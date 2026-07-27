"""Tiny stdlib HTTP helper (urllib, no third-party `requests`).

Pure-stdlib keeps the serverless bundle dependency-free (fast cold starts, no
requirements.txt install step). Only GET is exposed -- the public function never POSTs.

DEFENCE-IN-DEPTH (D-0008 / B-001 ABSOLUTE RULE): every request host is checked against a
blocklist. Any attempt to reach pathofexile.com (or a subdomain) raises immediately -- on the
initial URL AND on every HTTP 3xx redirect hop (a custom opener re-runs the guard before
following any redirect, and caps redirect depth). The public function must NEVER touch the
trade API server-side; the guard makes that structurally impossible at the transport layer,
not merely by convention.
"""
import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Tuple

# A real browser UA + contact, what poe.ninja / paste hosts expect. Kept distinct from the
# trade client's UA (the trade client does not exist in the public build).
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 buildpricechecker-poe1-public/0.1")

# Hosts the public function is forbidden to reach server-side (the entire architecture
# exists so trade calls happen ONLY on user machines). Checked on every request.
_BLOCKED_HOSTS = ("pathofexile.com",)


class HttpError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _guard_host(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    for bad in _BLOCKED_HOSTS:
        if host == bad or host.endswith("." + bad):
            raise HttpError(
                f"BLOCKED: the public function must never call {host!r} server-side "
                "(trade pricing happens only on user machines). This is a hard invariant.")
    return host


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-run the host guard on every 3xx hop. Plain ``urlopen`` auto-follows redirects WITHOUT
    re-checking the target host, so a trusted host that 302'd to pathofexile.com would otherwise
    be followed. Guarding each hop closes that (and caps redirect depth against redirect loops /
    internal-redirect SSRF)."""
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _guard_host(newurl)   # raises HttpError before the blocked hop is ever opened
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Single shared opener: our guarded redirect handler REPLACES urllib's default one.
_OPENER = urllib.request.build_opener(_GuardedRedirectHandler())


def _open(url: str, timeout: float, headers: Optional[dict]):
    _guard_host(url)
    hdr = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
           "Accept-Encoding": "gzip"}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr, method="GET")
    return _OPENER.open(req, timeout=timeout)


def _read_body(resp) -> bytes:
    raw = resp.read()
    if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    return raw


def get_json(url: str, params: Optional[dict] = None, timeout: float = 30,
             headers: Optional[dict] = None) -> dict:
    """GET a URL and parse JSON. Raises HttpError on network / non-2xx / non-JSON."""
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    try:
        with _open(url, timeout, headers) as resp:
            body = _read_body(resp)
    except urllib.error.HTTPError as e:
        raise HttpError(f"HTTP {e.code} from {url}", status=e.code)
    except urllib.error.URLError as e:
        raise HttpError(f"could not reach {url}: {e.reason}")
    except (TimeoutError, OSError) as e:
        raise HttpError(f"network error calling {url}: {e}")
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HttpError(f"non-JSON response from {url}")


def get_text(url: str, timeout: float = 30, headers: Optional[dict] = None,
             max_bytes: int = 2_000_000) -> Tuple[bool, int, str]:
    """GET a URL as text (for PoB paste links). Returns (ok, status, text). Never raises
    for HTTP errors -- callers try several candidate URLs and pick the first that works."""
    try:
        with _open(url, timeout, headers) as resp:
            body = _read_body(resp)[:max_bytes]
            return True, getattr(resp, "status", 200) or 200, body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return False, e.code, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, 0, ""
