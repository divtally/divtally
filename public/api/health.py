"""Vercel Python serverless function: GET /api/health

A tiny, OFFLINE readiness check. It never touches the network (not poe.ninja, and -- per
the hard invariant -- never pathofexile.com). It loads the BUNDLED trade reference data so
a green health check also proves `api/_data/*.json` shipped with the function.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import refdata                       # noqa: E402
from _lib.response import SCHEMA_VERSION        # noqa: E402
from _lib.statmap import StatMapper             # noqa: E402

_CORS = {"Access-Control-Allow-Origin": "*",
         "Access-Control-Allow-Methods": "GET, OPTIONS",
         "Access-Control-Allow-Headers": "Content-Type"}


def _payload() -> dict:
    try:
        stats = refdata.stats_data()
        mapper = StatMapper(stats)
        types = refdata.item_types()
        return {
            "ok": True,
            "service": "bpc-public-api",
            "schema_version": SCHEMA_VERSION,
            "calls_pathofexile_com": False,          # hard invariant
            "refdata": {
                "stat_groups": len(stats.get("result", [])),
                "stat_patterns": len(mapper._map),
                "base_types": len(types.get("all", set())),
            },
            "ts": int(time.time()),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "service": "bpc-public-api",
                "error": f"reference data not loadable: {type(e).__name__}: {e}",
                "ts": int(time.time())}


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
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
        body = _payload()
        self._send(200 if body.get("ok") else 503, body)
