"""Vercel Python serverless function: POST/GET /api/build

Input:  a poe.ninja PoE1 character URL, a Path of Building code, or a PoB paste link
        (pobb.in / pastebin / poe.ninja), plus optional `league` + `status` overrides.
Output: ONE JSON document (see docs/public-contract.md) -- build meta, every item row with
        category/group/host-gem structure, poe.ninja prices where available, and for every
        rare/unpriced item the prebuilt trade_url + exact trade_query JSON.

HARD INVARIANT (D-0008 / B-001): this function NEVER calls pathofexile.com. Item prices
come only from poe.ninja; trade queries are BUILT for a client-side extension, never run
here. The `_lib._http` layer blocks pathofexile.com at the transport level as defence.

Usage:
  GET  /api/build?url=<poe.ninja char url>[&league=Standard][&status=online]
  POST /api/build   body: {"input": "<url or PoB code>", "league": "...", "status": "..."}
                    (also accepts "url" / "build" / "pob" as the input field name)
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Make the sibling `_lib` package importable regardless of Vercel's CWD.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import engine, response          # noqa: E402
from _lib._http import HttpError           # noqa: E402
from _lib.poeninja import PoeNinjaError    # noqa: E402

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
}
# Cache successful, deterministic-ish results at the CDN edge (poe.ninja data is not
# realtime). SWR lets a stale copy serve instantly while one revalidation runs in the bg.
_CACHE_OK = "public, s-maxage=600, stale-while-revalidate=86400"
_CACHE_ERR = "no-store"

_INPUT_FIELDS = ("input", "url", "build", "pob", "code", "text")


def _pick_input(d: dict) -> str:
    for k in _INPUT_FIELDS:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _source_kind(meta) -> str:
    return "pob" if (getattr(meta, "source_url", "") or "").startswith("(Path of Building") else "poe.ninja"


def _run(input_text: str, league: str, status: str):
    """Return (http_status, body_dict). Never raises."""
    if not input_text:
        return 400, {"ok": False, "error_type": "bad_input",
                     "error": "missing build input: pass ?url= (GET) or {\"input\": ...} (POST). "
                              "Accepts a poe.ninja PoE1 character URL, a Path of Building code, "
                              "or a PoB paste link."}
    try:
        meta, results, pricer, trade_league = engine.run_estimate(
            input_text, league=league or None, status=status or "available")
    except engine.EstimateError as e:
        return 400, {"ok": False, "error_type": "bad_input", "error": str(e)}
    except PoeNinjaError as e:
        return 502, {"ok": False, "error_type": "ninja_error", "error": str(e)}
    except HttpError as e:
        # A blocked-host error would land here (should be impossible in normal flow).
        return 502, {"ok": False, "error_type": "upstream_error", "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return 500, {"ok": False, "error_type": "server_error",
                     "error": f"{type(e).__name__}: {e}"}
    try:
        body = response.build_response(meta, results, pricer, trade_league, _source_kind(meta))
    except Exception as e:  # noqa: BLE001
        return 500, {"ok": False, "error_type": "server_error",
                     "error": f"response build failed: {type(e).__name__}: {e}"}
    return 200, body


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", _CACHE_OK if body.get("ok") else _CACHE_ERR)
        for k, v in _CORS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in _CORS.items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        inp = _pick_input({k: (v[0] if v else "") for k, v in qs.items()})
        league = (qs.get("league", [""])[0] or "").strip()
        status = (qs.get("status", [""])[0] or "").strip()
        code, body = _run(inp, league, status)
        self._send(code, body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b""
            data = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(data, dict):
                data = {}
        except (ValueError, TypeError):
            self._send(400, {"ok": False, "error_type": "bad_input",
                             "error": "request body must be JSON, e.g. {\"input\": \"<url>\"}"})
            return
        inp = _pick_input(data)
        league = str(data.get("league") or "").strip()
        status = str(data.get("status") or "").strip()
        code, body = _run(inp, league, status)
        self._send(code, body)
