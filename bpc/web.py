"""Local web UI for the PoE1 build price checker.

    python -m bpc.web            # then open http://127.0.0.1:8765
    python -m bpc.web --port 9000 --no-browser

A single-user, localhost-only server. Pricing runs in a background thread so the
browser can show live progress; a global lock serialises pricing jobs so two builds
never hit the rate-limited trade API at once (which could get the IP banned).
"""
import argparse
import json
import mimetypes
import os
import re
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from urllib.parse import urlparse, parse_qs

from . import __version__, cache, engine, poeninja, report, util
from .models import (CAT_GEM, CAT_MAGIC, CAT_RARE, CAT_UNIQUE, PriceResult)
from .trade import TradeClient

_jobs = {}                      # job_id -> dict(...)
_jobs_lock = threading.Lock()
_price_lock = threading.Lock()  # serialise pricing so we never exceed trade limits
_active = None                  # most recent job id; starting a new one cancels the old

# ---- multi-version UI -------------------------------------------------------
# Every *.html in bpc/ui/ (except _underscore files) is a self-contained front-end
# "version" that drives the same /api/* backend through the shared engine at
# /assets/core.js. The landing page (/) is the stash skin (D-0007, owner pick); the
# picker gallery lives at /gallery; each version is at /v/<id>.
_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


def _safe_join(base, rel):
    """Join + confine to base (no path traversal). Returns abs path or None."""
    base = os.path.normpath(base)
    p = os.path.normpath(os.path.join(base, rel))
    if p == base or p.startswith(base + os.sep):
        return p
    return None


def _ui_meta(html, name, default=""):
    m = re.search(r'<meta\s+name="bpc-' + name + r'"\s+content="([^"]*)"', html, re.I)
    return m.group(1) if m else default


def _list_versions():
    """Discover UI versions from bpc/ui/*.html, reading their bpc-* meta tags."""
    out = []
    try:
        files = os.listdir(_UI_DIR)
    except OSError:
        return out
    for fn in files:
        if not fn.endswith(".html") or fn.startswith("_"):
            continue
        vid = fn[:-5]
        try:
            with open(os.path.join(_UI_DIR, fn), encoding="utf-8") as fh:
                head = fh.read(4000)
        except OSError:
            continue
        out.append({
            "id": vid,
            "title": _ui_meta(head, "title", vid),
            "tagline": _ui_meta(head, "tagline", ""),
            "accent": _ui_meta(head, "accent", "#7c5cff"),
            "vibe": _ui_meta(head, "vibe", ""),
            "order": _ui_meta(head, "order", "999"),
        })
    out.sort(key=lambda v: (int(v["order"]) if v["order"].isdigit() else 999, v["title"].lower()))
    return out


def _gallery_html():
    """Landing page: a gallery to pick a UI version (auto-discovered from bpc/ui/)."""
    vers = _list_versions()
    cards = []
    for v in vers:
        ac = v["accent"]
        vibe = ('<span class="vibe">' + _html_escape(v["vibe"]) + "</span>") if v["vibe"] else ""
        cards.append(
            '<a class="card" href="/v/{id}" style="--ac:{ac}">'
            '<span class="swatch"></span>'
            '<span class="ct"><b>{title}</b>{vibe}</span>'
            '<span class="cd">{tag}</span>'
            '<span class="go">open &rarr;</span></a>'.format(
                id=_html_escape(v["id"]), ac=_html_escape(ac),
                title=_html_escape(v["title"]), tag=_html_escape(v["tagline"]), vibe=vibe))
    if not cards:
        cards.append('<div class="empty">No UI versions are installed yet. '
                     'Drop <code>*.html</code> files into <code>bpc/ui/</code>.</div>')
    grid = "\n".join(cards)
    return _GALLERY_TMPL.replace("{{COUNT}}", str(len(vers))).replace("{{CARDS}}", grid)


def _html_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_GALLERY_TMPL = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PoE1 Build Price Checker - choose a look</title>
<style>
  :root{--bg:#0b0d12;--panel:#141821;--bd:#252b38;--fg:#e8ecf4;--mut:#8b93a7}
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 700px at 80% -10%,#181d2a,var(--bg));
    color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Arial;min-height:100vh}
  .wrap{max-width:1080px;margin:0 auto;padding:56px 24px 80px}
  h1{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}
  .sub{color:var(--mut);margin:0 0 6px;max-width:62ch}
  .sub b{color:var(--fg)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-top:30px}
  .card{position:relative;display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto auto;
    gap:2px 14px;text-decoration:none;color:inherit;background:var(--panel);
    border:1px solid var(--bd);border-radius:14px;padding:18px 18px 16px;overflow:hidden;
    transition:transform .12s ease,border-color .12s ease,box-shadow .12s ease}
  .card:hover{transform:translateY(-3px);border-color:var(--ac);box-shadow:0 10px 30px -12px var(--ac)}
  .card .swatch{grid-row:1/4;width:6px;border-radius:6px;background:var(--ac);align-self:stretch}
  .card .ct{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
  .card .ct b{font-size:18px;letter-spacing:-.01em}
  .card .vibe{font-size:11px;color:var(--ac);border:1px solid var(--ac);border-radius:99px;
    padding:1px 8px;opacity:.85}
  .card .cd{color:var(--mut);font-size:13px;grid-column:2;margin-top:4px}
  .card .go{grid-column:2;color:var(--ac);font-size:12px;margin-top:12px;opacity:0;transition:opacity .12s}
  .card:hover .go{opacity:1}
  .empty{color:var(--mut);padding:30px;border:1px dashed var(--bd);border-radius:14px}
  code{background:#0e121b;border:1px solid var(--bd);border-radius:5px;padding:1px 5px;font-size:12px}
  .foot{margin-top:34px;color:var(--mut);font-size:13px}
  .foot a{color:var(--fg)}
</style></head><body><div class="wrap">
  <h1>Build Price Checker</h1>
  <p class="sub">Pick a look. Every version drives the <b>same engine and live prices</b> &mdash;
  only the interface differs. <b>{{COUNT}}</b> to try. Your pick is just a bookmark; switch any time.</p>
  <div class="grid">
{{CARDS}}
  </div>
  <p class="foot">Prefer the known-good original? <a href="/classic">Open the classic UI &rarr;</a></p>
</div></body></html>"""


def _set_error(job_id, msg):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(state="error", error=msg)


def _result_dict(r: PriceResult) -> dict:
    f = report._finite
    d = {"chaos": {"min": f(r.tier.minimum), "median": f(r.tier.median),
                   "high": f(r.tier.high)},
         "confidence": r.confidence, "note": r.note, "method": r.method,
         "trade_url": r.trade_url, "sample_size": r.sample_size,
         "total_found": r.total_found}
    if r.extra:                       # e.g. gems carry kind/level/quality/total_chaos/gems
        d.update(r.extra)
    return d


def _snapshot(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


# ---- saved build results (so re-opening a build shows prices WITHOUT re-searching) ----
def _result_key(meta, cache_key):
    base = (getattr(meta, "cache_key", "") or cache_key or "")
    return ("result:" + base) if base else ""


def _load_saved_result(meta, cache_key):
    key = _result_key(meta, cache_key)
    if not key:
        return None
    saved = cache.peek(key)
    return saved if (isinstance(saved, dict) and saved.get("priced")) else None


# A saved result is keyed by item INDEX. If a normalize/pricing change reorders or re-counts the
# items (e.g. the gem-pricing rework), an old saved `priced` no longer lines up
# with the freshly-normalized items -- so seeding would show, and link, each slot to the WRONG
# item's price (a jewel opening a skill-gem search, a flask opening an armour search, ...). Guard:
# every saved entry's pricing METHOD must be consistent with the category of the item now sitting
# at that index. On any mismatch we refuse to seed and re-price instead (self-healing: the fresh
# run rewrites a correctly-aligned result).
_METHOD_OK = {CAT_GEM: ("skill",), CAT_UNIQUE: ("unique",),
              CAT_RARE: ("rare",), CAT_MAGIC: ("magic",)}


def _saved_result_aligned(saved, items):
    for idx_str, p in (saved.get("priced") or {}).items():
        try:
            idx = int(idx_str)
        except (TypeError, ValueError):
            continue
        if idx >= len(items):
            return False                      # priced an index that no longer exists
        method = (p.get("method") or "").lower()
        if not method or method in ("skipped", "error", "none"):
            continue                          # category-agnostic outcomes
        allowed = _METHOD_OK.get(items[idx].category)
        if allowed and not method.startswith(allowed):
            return False                      # e.g. a "skill" price sitting on a jewel/flask slot
    return True


def _save_result(job_id):
    """Persist a finished job's prices keyed by the build, for instant future loads."""
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j or not j.get("priced") or not j.get("_result_key"):
            return
        key = j["_result_key"]
        payload = {"meta": j.get("meta"), "items": j.get("items"),
                   "priced": dict(j.get("priced") or {}), "rares": j.get("rares"),
                   "searches": j.get("searches"), "advanced": j.get("advanced"),
                   "ts": j.get("saved_ts") or time.time()}
    try:
        cache.put(key, payload)
    except Exception:
        pass


def _price_task(pricer, kind, payload, items_by_idx, gems):
    idx = payload[0] if kind == "rare_custom" else payload
    it = items_by_idx[idx]
    if kind == "skill":
        return pricer.price_skill(it)
    if kind == "unique":
        return pricer.price_unique(it)
    if kind == "magic":
        return pricer.price_magic(it)
    if kind == "rare_default":
        return pricer.price_rare(it)
    if kind == "rare_custom":
        body = payload[1] if isinstance(payload[1], dict) else {}
        kw = dict(groups=body.get("groups"), selections=body.get("filters"),
                  equip=body.get("equip"))
        if it.category == CAT_UNIQUE:           # uniques search by name+base, not base/category
            return pricer.price_unique_custom(it, **kw)
        return pricer.price_rare_custom(it, **kw)
    return PriceResult(item=it, method="none", note="normal item; not priced",
                       confidence="none")


def _run_job(job_id, url, league, refresh, advanced, cache_key="", status="online",
             research=False):
    def progress(msg):
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["progress"].append(msg)

    with _price_lock:                       # one pricing run at a time
        with _jobs_lock:
            if job_id not in _jobs or _jobs[job_id].get("_cancelled"):
                return
            _jobs[job_id]["state"] = "running"
        try:
            if cache_key:
                meta, items, pricer, _lg = engine.prepare_from_cache(
                    cache_key, league=league or None, progress=progress, status=status)
            else:
                meta, items, pricer, _lg = engine.prepare_auto(
                    url, league=league or None, refresh=refresh, progress=progress,
                    status=status)
        except (poeninja.PoeNinjaError, engine.EstimateError) as e:
            _set_error(job_id, str(e)); return
        except Exception as e:
            _set_error(job_id, f"unexpected error: {type(e).__name__}: {e}"); return

        # Previously-priced result on disk? Unless the user asked to re-search, seed from
        # it and SKIP all trade searches (instant load). The worker still runs (idle), so
        # "edit affixes" can re-price a single rare and "Re-search all" can refresh.
        saved = None if (refresh or research) else _load_saved_result(meta, cache_key)
        if saved and not _saved_result_aligned(saved, items):
            progress("Saved prices are from an older layout; re-pricing to re-sync.")
            saved = None                      # stale index layout -> don't seed misaligned data
        result_key = _result_key(meta, cache_key)
        seed = bool(saved)
        if seed:
            progress("Loaded saved prices (no searching).")

        try:
            div = pricer.conv.divine_rate() if not seed else None
        except Exception:
            div = None

        # Build the item skeleton + task queue. Each active SKILL is its own row (with its
        # level, support-socket count and support list) priced cut/uncut.
        gems = [it for it in items if it.category == CAT_GEM]
        skeleton, items_by_idx, rares_meta = [], {}, {}
        q = Queue()
        for i, it in enumerate(items):
            items_by_idx[i] = it
            row = {"index": i, "name": it.display_name, "group": it.group,
                   "category": it.category, "slot": it.slot,
                   "count": it.count, "rarity": it.rarity, "icon": it.icon}
            if it.category == CAT_GEM:
                row["level"] = it.gem_level
                row["quality"] = it.gem_quality
                row["corrupted"] = it.corrupted
                row["sockets"] = len(it.supports)   # PoE1 gems have no sockets; carry support count
                row["supports"] = it.supports
                # GRANTED (feedback1-spec.md B.1): the engine now computes this from the character
                # JSON (itemProvidedGems / isBuiltInSupport; poeninja._gem_is_granted), so read the
                # engine value directly. The old PoE2-era heuristic
                # `not inventoryId.startswith("SkillSlot")` was WRONG for PoE1 -- gems have
                # inventoryId == None, so it flagged EVERY gem granted (the owner's reported bug).
                # Deleted here, not left as a dead fallback (CLAUDE.md RULE 6).
                row["granted"] = bool(it.granted)
                # Host-item info (spec D.1, additive): lets skins group gems under their host BEFORE
                # the price lands. core.js gemHost() reads priced-first then falls back to these
                # skeleton fields. All five are guaranteed on the Item (models.py defaults).
                row["host_slot"] = it.host_slot
                row["host_name"] = it.host_name
                row["host_base"] = it.host_base
                row["host_unique"] = it.host_unique
                row["host_inventory_id"] = it.host_inventory_id
            else:                                   # affixes for the hover tooltip
                mods = {"implicit": [util.strip_rich(m).strip() for m in (it.implicit_mods or [])],
                        "explicit": [util.strip_rich(m).strip() for m in (it.explicit_mods or [])]}
                if any(mods.values()):
                    row["mods"] = mods
            skeleton.append(row)
            # Rares AND uniques both get an affix-picker entry (rares_meta). Rares wait for the
            # user's picks in advanced mode; uniques always auto-price by default (price_unique,
            # which targets the build's skill-level rolls) and expose the picker via "edit
            # affixes" for manual refinement (count groups, lower rolls, weighted sums, ...).
            if it.category in (CAT_RARE, CAT_UNIQUE):
                is_uni = it.category == CAT_UNIQUE
                btype = pricer.resolve_type(it.base_type)
                spec = pricer.affix_options(it)
                if is_uni:
                    status_v, scope = ("priced" if seed else "queued"), ("unique: " + it.name)
                    scope_q = {"name": it.name, "type": it.base_type}
                else:
                    status_v = "priced" if seed else ("awaiting" if advanced else "queued")
                    scope = ("base: " + btype) if btype else "category"
                    _sc = pricer._rare_scopes(it)            # base scope (or category) fragment
                    scope_q = dict(_sc[0][0]) if _sc else {}
                rares_meta[str(i)] = {
                    "status": status_v, "name": it.display_name, "scope": scope,
                    "kind": "unique" if is_uni else "rare", "scope_q": scope_q,
                    "affixes": spec["affixes"], "pseudo": spec["pseudo"]}
                if not seed:
                    if is_uni:
                        q.put(("unique", i))
                    elif not advanced:
                        q.put(("rare_default", i))
            elif seed:
                pass                                # seeded: nothing to search
            elif it.category == CAT_GEM:
                q.put(("skill", i))
            elif it.category == CAT_MAGIC:
                q.put(("magic", i))
            else:
                q.put(("none", i))

        with _jobs_lock:
            j = _jobs[job_id]
            if seed and isinstance(saved.get("meta"), dict):
                j["meta"] = saved["meta"]           # reuse the meta priced-under (incl. div rate)
            else:
                j["meta"] = {"character": meta.character, "class": meta.char_class,
                             "level": meta.level, "league": meta.league,
                             "divine_to_chaos": report._finite(div),
                             "status": pricer.status,
                             "chaos_img": pricer.currency_image("chaos"),
                             "divine_img": pricer.currency_image("divine"),
                             "source_url": getattr(meta, "source_url", "") or "",
                             "pob_code": getattr(meta, "pob_export", "") or ""}
            # cache_key lets the client persist per-build state (e.g. purchase tracking) across
            # reloads. Inject on BOTH paths so seeded loads (old saved meta) get it too.
            j["meta"]["cache_key"] = getattr(meta, "cache_key", "") or j["meta"].get("cache_key", "")
            j["items"] = skeleton
            j["rares"] = rares_meta
            j["_q"] = q
            j["_items"] = items_by_idx
            j["_gems"] = gems
            j["_result_key"] = result_key
            j["from_saved"] = seed
            j["saved_ts"] = saved.get("ts") if seed else None
            if seed:
                j["priced"] = dict(saved.get("priced") or {})
                j["searches"] = saved.get("searches", 0)

        # dirty = "priced something this run, so the saved result should be (re)written".
        # A pure seeded load starts clean so it never rewrites (preserves the saved-at time);
        # editing a rare's affixes prices it -> dirty -> saved with a fresh timestamp.
        dirty = not seed

        # Worker loop: price queued tasks; in advanced mode wait while rares are still
        # awaiting the user's affix choices. We do NOT exit when the build is complete --
        # we idle (state "done"), staying ready to re-price any rare the user re-opens via
        # "edit affixes". We only exit when the job is cancelled (the user started a new
        # build), which releases the pricing lock for the next run.
        total = len(skeleton)
        while True:
            with _jobs_lock:
                if _jobs[job_id].get("_cancelled"):
                    return
            try:
                kind, payload = q.get(timeout=0.4)
            except Empty:
                save_now = False
                with _jobs_lock:
                    if _jobs[job_id].get("_cancelled"):
                        return
                    pending = any(r["status"] in ("awaiting", "queued")
                                  for r in _jobs[job_id]["rares"].values())
                    if q.empty() and not pending and _jobs[job_id]["state"] != "done":
                        _jobs[job_id]["state"] = "done"; save_now = True
                        if dirty:                          # fresh prices -> stamp refresh time
                            _jobs[job_id]["saved_ts"] = time.time()
                if save_now and dirty:
                    _save_result(job_id); dirty = False    # persist for instant future loads
                continue
            idx = "gems" if kind == "gems" else (payload[0] if kind == "rare_custom"
                                                 else payload)
            name = ("Gems" if kind == "gems"
                    else items_by_idx[idx].display_name if idx in items_by_idx else "item")
            with _jobs_lock:
                _jobs[job_id]["state"] = "running"        # re-pricing (or initial run)
                done = len(_jobs[job_id]["priced"])
            progress(f"Pricing {name} ({min(done + 1, total)}/{total})...")
            try:
                result = _price_task(pricer, kind, payload, items_by_idx, gems)
                priced_entry = _result_dict(result)
            except Exception as e:                  # never let one item kill the worker thread
                progress(f"  could not price {name}: {type(e).__name__}: {e}")
                priced_entry = {"chaos": {"min": None, "median": None, "high": None},
                                "confidence": "none", "method": "error", "trade_url": "",
                                "sample_size": 0, "total_found": 0,
                                "note": f"pricing failed ({type(e).__name__})"}
            with _jobs_lock:
                _jobs[job_id]["priced"][str(idx)] = priced_entry
                _jobs[job_id]["searches"] = pricer.client.search_count
                if str(idx) in _jobs[job_id]["rares"]:
                    _jobs[job_id]["rares"][str(idx)]["status"] = "priced"
            dirty = True                            # a fresh/edited price -> save on next done


class Handler(BaseHTTPRequestHandler):
    server_version = f"bpc/{__version__}"

    def log_message(self, *a):              # quiet console
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")  # always serve fresh page/JS
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or "{}")
        except (ValueError, TypeError):
            return None

    def do_GET(self):
        path = urlparse(self.path)
        if path.path == "/":
            # D-0007: the stash skin IS the app (owner pick); the gallery moved to /gallery.
            fp = _safe_join(_UI_DIR, "stash.html")
            if fp and os.path.isfile(fp):
                with open(fp, encoding="utf-8") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            else:
                self._send(200, _gallery_html(), "text/html; charset=utf-8")
        elif path.path == "/gallery":
            self._send(200, _gallery_html(), "text/html; charset=utf-8")
        elif path.path == "/classic":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path.path.startswith("/v/"):
            vid = path.path[3:].strip("/")
            fp = _safe_join(_UI_DIR, vid + ".html") if re.fullmatch(r"[A-Za-z0-9_-]+", vid or "") else None
            if fp and os.path.isfile(fp):
                with open(fp, encoding="utf-8") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            else:
                self._send(404, "<h1>unknown version</h1>", "text/html; charset=utf-8")
        elif path.path.startswith("/assets/"):
            fp = _safe_join(os.path.join(_UI_DIR, "assets"), path.path[len("/assets/"):])
            if fp and os.path.isfile(fp):
                ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                    ctype += "; charset=utf-8"
                with open(fp, "rb") as fh:
                    self._send(200, fh.read(), ctype)
            else:
                self._send(404, json.dumps({"error": "not found"}))
        elif path.path == "/api/job":
            jid = parse_qs(path.query).get("id", [""])[0]
            # serialize WHILE holding the lock: _snapshot is shallow, so priced/rares/progress
            # are the live objects the worker mutates -> json.dumps outside the lock can hit
            # "dictionary changed size during iteration" and spuriously 500 a healthy poll.
            with _jobs_lock:
                job = _jobs.get(jid)
                body = json.dumps(_snapshot(job)) if job else None
            if body is None:
                self._send(404, json.dumps({"error": "unknown job"}))
            else:
                self._send(200, body)
        elif path.path == "/api/cache":
            try:
                builds = engine.list_cached_builds()
            except Exception:
                builds = []
            self._send(200, json.dumps({"builds": builds}))
        elif path.path == "/api/leagues":
            try:
                leagues = [l.get("id") for l in TradeClient.list_leagues() if l.get("id")]
            except Exception:
                leagues = []
            self._send(200, json.dumps({"leagues": leagues}))
        elif path.path == "/api/stats":
            # full PoE1 trade stat dictionary (id/text grouped by type) so the picker can add
            # filters for mods not on the build's item. Disk-cached a day; league-agnostic.
            try:
                data = TradeClient("Standard").stats_data()
                groups = [{"label": g.get("label", ""),
                           "entries": [{"id": e["id"], "text": e.get("text", "")}
                                       for e in g.get("entries", []) if e.get("id")]}
                          for g in data.get("result", [])]
            except Exception:
                groups = []
            self._send(200, json.dumps({"groups": groups}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        global _active
        path = urlparse(self.path)
        if path.path == "/api/price":
            body = self._read_json()
            if body is None:
                self._send(400, json.dumps({"error": "bad request body"})); return
            url = (body.get("url") or "").strip()
            cache_key = (body.get("cache_key") or "").strip()
            if not url and not cache_key:
                self._send(400, json.dumps({"error": "no URL provided"})); return
            job_id = uuid.uuid4().hex
            with _jobs_lock:
                if _active and _active in _jobs:    # cancel any previous run
                    _jobs[_active]["_cancelled"] = True
                _active = job_id
                _jobs[job_id] = {"state": "queued", "progress": [], "error": None,
                                 "advanced": bool(body.get("advanced")), "meta": None,
                                 "items": [], "priced": {}, "rares": {}, "searches": 0}
            threading.Thread(target=_run_job, daemon=True, args=(
                job_id, url, (body.get("league") or "").strip(),
                bool(body.get("refresh")), bool(body.get("advanced")), cache_key,
                (body.get("status") or "online").strip(),
                bool(body.get("research")))).start()
            self._send(200, json.dumps({"job_id": job_id}))

        elif path.path == "/api/rare":
            qs = parse_qs(path.query)
            jid = qs.get("id", [""])[0]
            idx = qs.get("index", [""])[0]
            body = self._read_json() or {}
            with _jobs_lock:
                job = _jobs.get(jid)
                if not job or "_q" not in job:
                    self._send(404, json.dumps({"error": "unknown job"})); return
                rare = job["rares"].get(idx)
                if not rare:
                    self._send(404, json.dumps({"error": "unknown rare"})); return
                # allow re-submission (the user can go Back and fix a rare): re-queue it,
                # the worker overwrites the previous price for this item (last wins).
                if body.get("skip"):
                    # skip entirely: mark priced with no price, no trade search
                    rare["status"] = "priced"
                    job["priced"][idx] = {
                        "chaos": {"min": None, "median": None, "high": None},
                        "confidence": "none", "note": "skipped (not priced)",
                        "method": "skipped", "trade_url": "", "sample_size": 0,
                        "total_found": 0}
                else:
                    rare["status"] = "queued"
                    job["_q"].put(("rare_custom", (int(idx), body)))
                # re-pricing after the build finished: flip back to running so the page
                # keeps polling until the new price lands (the idle worker resets to done).
                if job.get("state") == "done":
                    job["state"] = "running"
            self._send(200, json.dumps({"ok": True}))
        else:
            self._send(404, json.dumps({"error": "not found"}))


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PoE1 Build Price Checker</title>
<style>
  :root{--bg:#15171c;--panel:#1d2027;--line:#2c313c;--fg:#d6d8de;--mut:#8b909c;
        --acc:#c79a4b;--green:#54b06a;--amber:#d6a23a;--grey:#6b7280;--red:#c9554e;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
       font:15px/1.45 ui-sans-serif,system-ui,Segoe UI,Roboto,Arial}
  .wrap{max-width:920px;margin:0 auto;padding:28px 18px 60px}
  h1{font-size:22px;margin:0 0 4px;color:var(--acc)}
  .tag{color:var(--mut);font-size:13px;margin-bottom:20px}
  form{display:flex;gap:8px;flex-wrap:wrap;align-items:center;
       background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
  input[type=text]{flex:1 1 420px;min-width:260px;background:#101216;color:var(--fg);
       border:1px solid var(--line);border-radius:7px;padding:10px 12px;font-size:14px}
  input[type=text]::placeholder{color:#5b606b}
  .opt{flex:0 0 150px}
  select#liststatus,select#league{background:#101216;color:var(--fg);border:1px solid var(--line);
       border-radius:7px;padding:10px 8px;font-size:14px;cursor:pointer}
  select#liststatus{flex:0 0 215px} select#league{flex:0 0 160px}
  label.chk{color:var(--mut);font-size:13px;display:flex;align-items:center;gap:6px}
  button{background:var(--acc);color:#1a1206;border:0;border-radius:7px;padding:10px 18px;
       font-weight:600;font-size:14px;cursor:pointer}
  button:disabled{opacity:.5;cursor:default}
  #status{margin:16px 0;color:var(--mut);font-size:13px;white-space:pre-wrap;min-height:18px}
  .spin{display:inline-block;width:12px;height:12px;border:2px solid var(--line);
       border-top-color:var(--acc);border-radius:50%;animation:s .8s linear infinite;
       vertical-align:-2px;margin-right:8px}
  @keyframes s{to{transform:rotate(360deg)}}
  .err{color:var(--red);background:#2a1b1a;border:1px solid #4a2a27;border-radius:8px;padding:12px}
  .meta h2{margin:18px 0 2px;font-size:19px}.meta .sub{color:var(--mut);font-size:13px}
  h3{margin:22px 0 8px;font-size:15px;color:var(--acc);border-bottom:1px solid var(--line);
       padding-bottom:5px}
  table{width:100%;border-collapse:collapse;font-size:14px}
  th{text-align:left;color:var(--mut);font-weight:500;font-size:12px;padding:5px 8px}
  td{padding:7px 8px;border-top:1px solid var(--line);vertical-align:top}
  td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
  img.cur{height:1.05em;vertical-align:-0.18em;margin:0 1px}
  .exsub{color:var(--mut)}
  .reaffix{margin-left:8px;font-size:11px;padding:1px 7px;border-radius:5px;border:1px solid var(--bd);
    background:#1c2230;color:var(--mut);cursor:pointer;vertical-align:1px}
  .reaffix:hover{color:var(--fg);border-color:#4a5468}
  .pobbox{margin-top:10px;border:1px solid var(--bd);border-radius:8px;padding:8px 10px;background:#161b26}
  .pobhd{font-size:12px;color:var(--mut);display:flex;align-items:center;gap:8px;margin-bottom:5px}
  .pobcopy{display:inline-flex;align-items:center;justify-content:center;padding:3px 6px;border-radius:5px;
    border:1px solid var(--bd);background:#1c2230;color:var(--mut);cursor:pointer;line-height:0}
  .pobcopy:hover{border-color:#4a5468;color:var(--fg)}
  .pobcopy.ok{color:#5bd66f;border-color:#2f6b39}
  .pobtext{width:100%;box-sizing:border-box;resize:vertical;font:11px/1.4 ui-monospace,Consolas,monospace;
    color:var(--mut);background:#0e121b;border:1px solid var(--bd);border-radius:6px;padding:6px;white-space:pre;overflow:auto}
  th.num{text-align:right}th:last-child{text-align:left}
  th.cb,td.cb{width:30px;text-align:center;padding-left:10px}
  a{color:#8fb6e8;text-decoration:none}a:hover{text-decoration:underline}
  .note{color:var(--mut);font-size:12px;margin-top:3px}
  input[type=checkbox]{accent-color:var(--acc);cursor:pointer;width:15px;height:15px}
  /* enabled rows are full-colour; excluded rows desaturate + dim + strike the prices */
  tbody tr{transition:opacity .12s,filter .12s}
  tbody tr:hover{background:#20242c}
  tr.on td:nth-child(2){box-shadow:inset 3px 0 0 var(--acc)}
  tr.off{opacity:.4;filter:grayscale(1)}
  tr.off td.num{text-decoration:line-through}
  tr.unpriced td.cb{opacity:.35}
  .gtog{font-size:12px;color:var(--mut);font-weight:400;margin-left:10px}
  .gtog input{vertical-align:-2px;margin-right:3px}
  .badge{font-size:11px;padding:2px 7px;border-radius:10px;text-transform:lowercase}
  .badge.high{background:#1c3324;color:var(--green)}
  .badge.medium{background:#332a16;color:var(--amber)}
  .badge.low{background:#22262e;color:var(--grey)}
  .badge.none{background:#2a1b1a;color:var(--red)}
  .totals{margin-top:26px;background:var(--panel);border:1px solid var(--line);
       border-radius:10px;padding:14px 18px}
  .totrow{display:flex;justify-content:space-between;padding:5px 0;border-top:1px solid var(--line)}
  .totrow:first-of-type{border-top:0}.totrow b{font-variant-numeric:tabular-nums}
  .warn{color:var(--amber);font-size:13px;margin-top:10px}
  #tinc{color:var(--mut);font-size:12px;margin-top:10px}
  .hint{color:#5b606b;font-size:12px;margin:8px 2px 0}
  .foot{color:#5b606b;font-size:12px;margin-top:10px}
  /* recent / cached builds */
  #recent{margin:16px 0 0}
  #recent .rhead{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px}
  .rbuild{display:flex;align-items:baseline;gap:10px;background:var(--panel);
       border:1px solid var(--line);border-radius:8px;padding:9px 12px;margin-bottom:6px;cursor:pointer}
  .rbuild:hover{border-color:var(--acc);background:#23272f}
  .rbuild .rname{font-weight:600}
  .rbuild .rmeta{color:var(--mut);font-size:12px}
  .rbuild .rwhen{color:#5b606b;font-size:12px;margin-left:auto;white-space:nowrap}
  #recent .more{background:transparent;color:var(--acc);border:1px solid var(--line);
       border-radius:7px;padding:6px 12px;font-size:13px;font-weight:500;margin-top:2px}
  tr.await td.num{color:var(--amber);font-style:italic}
  /* affix picker */
  #picker{margin:16px 0}
  .pcard{background:var(--panel);border:1px solid var(--acc);border-radius:10px;padding:16px 18px}
  .pcard .ptitle{font-size:16px;color:var(--acc);margin-bottom:2px}
  .pcard .psub{color:var(--mut);font-size:12px;margin-bottom:12px}
  .afx{display:grid;grid-template-columns:22px 1fr 96px 96px;gap:8px 10px;align-items:center;
       padding:6px 0;border-top:1px solid var(--line)}
  .afx:first-of-type{border-top:0}
  .afx.no{opacity:.5}
  .afx .atext{font-size:14px}
  .afx .areason{color:var(--mut);font-size:11px}
  .afx input.mm{width:100%;background:#101216;color:var(--fg);border:1px solid var(--line);
       border-radius:6px;padding:6px 8px;font-size:13px;text-align:right}
  .afx .mmh{color:var(--mut);font-size:11px;text-align:right}
  .pbtns{margin-top:14px;display:flex;gap:10px;align-items:center}
  .pbtns .skip{background:transparent;color:var(--mut);border:1px solid var(--line)}
  .pqueue{color:var(--mut);font-size:12px;margin-left:auto}
  .ptoggle{display:block;color:var(--amber);font-size:13px;margin:2px 0 12px;cursor:pointer}
  .ptoggle input{vertical-align:-2px;margin-right:6px}
  /* --- D-0006 flask belt (5 generic slots in flask order; no life/mana classification) --- */
  .belt{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 6px}
  .beltslot{flex:1 1 150px;min-width:140px;background:var(--panel);border:1px solid var(--line);
    border-radius:9px;padding:9px 11px;transition:opacity .12s,filter .12s}
  .beltslot .belthd{display:flex;align-items:center;justify-content:space-between;margin-bottom:3px}
  .beltslot .beltpos{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
  .beltslot .iname{font-weight:600;font-size:13px;line-height:1.3}
  .beltslot .beltnums{font-variant-numeric:tabular-nums;font-size:13px;margin-top:5px}
  .beltslot .c-conf{margin-top:4px}
  .beltslot .note{color:var(--mut);font-size:11px;margin-top:3px}
  .beltslot.on{box-shadow:inset 3px 0 0 var(--acc)}
  .beltslot.off{opacity:.4;filter:grayscale(1)}
  .beltslot.off .beltnums{text-decoration:line-through}
  .beltslot.unpriced input{opacity:.35}
  .beltslot.empty{opacity:.5;display:flex;flex-direction:column;justify-content:center;
    align-items:center;color:#5b606b;border-style:dashed;min-height:66px}
  .beltslot.empty .beltempty{font-size:12px;margin-top:4px}
  /* --- D-0006 gems grouped by host item; supports nested under their active --- */
  .gemgroup{margin:6px 0 14px}
  .gemhdr{font-size:13px;color:var(--fg);font-weight:600;margin:8px 0 2px;padding:5px 9px;
    background:#191c22;border:1px solid var(--line);border-radius:7px}
  .gemhdr .uniqtag{color:var(--acc);font-size:11px;font-weight:500;margin-left:6px;
    text-transform:uppercase;letter-spacing:.03em}
  .gmeta{color:var(--mut);font-size:11px;font-weight:400}
  .sups{margin-top:4px}
  .sups .sup{color:var(--mut);font-size:12px;padding:1px 0}
  .sups .sup .supprice{font-variant-numeric:tabular-nums;color:var(--fg)}
  .sups .sup.sgr{opacity:.6}
  .sups .sup.sgr .supprice{text-decoration:line-through}
  .badge-granted{font-size:10px;padding:1px 6px;border-radius:9px;background:#2a2016;
    color:var(--amber);text-transform:uppercase;letter-spacing:.03em;margin-left:4px}
  tr.gemrow.off .supprice{text-decoration:line-through}
  /* --- D-0006 Autoscan (glowing, top of picker) + small skip-all (below) --- */
  .pautoscan{margin:0 0 12px}
  button.autoscan{display:block;width:100%;background:transparent;color:var(--acc);
    border:1px solid var(--acc);font-weight:700;letter-spacing:.04em;padding:11px 18px;
    box-shadow:0 0 0 1px var(--acc) inset,
               0 0 8px  color-mix(in srgb,var(--acc) 55%,transparent),
               0 0 18px color-mix(in srgb,var(--acc) 35%,transparent);
    animation:autoscanPulse 1.8s ease-in-out infinite}
  button.autoscan:hover{filter:brightness(1.12)}
  @keyframes autoscanPulse{
    0%,100%{box-shadow:0 0 0 1px var(--acc) inset,
                       0 0 6px  color-mix(in srgb,var(--acc) 45%,transparent),
                       0 0 14px color-mix(in srgb,var(--acc) 25%,transparent)}
    50%    {box-shadow:0 0 0 1px var(--acc) inset,
                       0 0 12px color-mix(in srgb,var(--acc) 70%,transparent),
                       0 0 26px color-mix(in srgb,var(--acc) 45%,transparent)}}
  @media (prefers-reduced-motion:reduce){button.autoscan{animation:none}}
  .pbulk{margin-top:12px}
  button.skipall{background:transparent;color:var(--mut);border:1px solid var(--line);
    font-size:12px;font-weight:500;padding:6px 12px}
  button.skipall:hover{color:var(--fg);border-color:#4a5468}
</style></head>
<body><div class="wrap">
  <h1>PoE1 Build Price Checker</h1>
  <div class="tag">Paste a poe.ninja character link, a Path of Building code, or a pobb.in
    link to estimate its cost (min / median / high).</div>
  <form id="f">
    <input type="text" id="url" autofocus spellcheck="false"
       placeholder="poe.ninja character link, Path of Building code, or pobb.in link">
    <select id="league" class="opt" title="trade league to price against">
      <option value="">League: auto</option>
    </select>
    <select id="liststatus" class="opt" title="which listings to search (matches the trade site)">
      <option value="available">Instant Buyout and In Person</option>
      <option value="securable">Instant Buyout</option>
      <option value="onlineleague">In Person (Online in League)</option>
      <option value="online" selected>In Person (Online)</option>
      <option value="any">Any</option>
    </select>
    <label class="chk"><input type="checkbox" id="advanced" checked> advanced affix search</label>
    <label class="chk" title="Ignore saved data and re-fetch fresh prices (slower; uses more of the trade rate limit). Leave off unless prices moved."><input type="checkbox" id="refresh"> fresh pull</label>
    <button id="go" type="submit">Estimate</button>
  </form>
  <div class="hint">Advanced: pick exactly which affixes to require (with min/max) for each
    rare, one at a time, while the rest price in the background. Off: rares must have
    <i>all</i> the item's affixes (extras OK).</div>
  <div id="recent"></div>
  <div id="status"></div>
  <div id="picker"></div>
  <div id="out"></div>
  <div class="foot">Rare prices are estimates; uniques are accurate. A fresh build takes ~1-4 min.</div>
</div>
<script>
const $=s=>document.querySelector(s);
const GROUPS=[['equipment','Equipment'],['flask','Flasks'],['jewel','Jewels'],
              ['gem','Gems']];
let polling=null, JOB=null, jobId=null, advanced=false;
let lastSource=null;     // the current build's source ({url} or {cache_key}) so control changes can re-run it
let rendered=false, enabled={}, filled={}, rareOrder=[], curRare=0, picking=false;
let curRareKey=null, usePseudo=true, decided=new Set();
let gemKeys=new Set(), gemDefaulted=new Set(), gemSig='';   // D-0006 gem grouping state
let RECENT=[], showAllRecent=false;
function setBusy(b){ $('#go').disabled=b; }
function pnum(s){ s=(s||'').trim(); if(s==='') return null; const n=Number(s); return isNaN(n)?null:n; }
function divr(){ return JOB&&JOB.meta? JOB.meta.divine_to_chaos : null; }
function cssesc(s){ return String(s).replace(/"/g,'\\"'); }
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function nfmt(n,d){ return n.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}); }
// currency icon (chaos/divine) like the trade site; falls back to text if no image
function curImg(kind){
  const src = (JOB&&JOB.meta) ? (kind==='div'?JOB.meta.divine_img:JOB.meta.chaos_img) : '';
  return src ? '<img class="cur" src="'+esc(src)+'" alt="'+kind+'" title="'+(kind==='div'?'Divine Orb':'Chaos Orb')+'">' : esc(kind);
}
// returns HTML (with orb icons): chaos, switching to a divine form once worth >= 0.5 div
function fmt(ex,div){
  if(ex==null) return '-';
  const exStr=(ex>=10? nfmt(Math.round(ex),0) : nfmt(ex,1))+' '+curImg('chaos');
  if(div && ex>=div*0.5){
    const v=ex/div, vStr=(v<100? nfmt(v,1) : nfmt(Math.round(v),0))+' '+curImg('div');
    return vStr+' <span class="exsub">('+exStr+')</span>';
  }
  return exStr;
}
async function runJob(extra){
  if(extra && (extra.url||extra.cache_key)) lastSource=extra;   // remember what to re-run
  if(polling) clearInterval(polling);
  $('#out').innerHTML=''; $('#picker').innerHTML=''; $('#status').textContent='';
  JOB=null; rendered=false; enabled={}; filled={}; rareOrder=[]; curRare=0;
  picking=false; curRareKey=null; decided=new Set();
  gemKeys=new Set(); gemDefaulted=new Set(); gemSig='';
  advanced=$('#advanced').checked;
  setBusy(true);
  $('#status').innerHTML='<span class="spin"></span>starting...';
  const body=Object.assign({league:$('#league').value.trim(),
    refresh:$('#refresh').checked, advanced, status:$('#liststatus').value}, extra);
  let r;
  try{
    r=await fetch('/api/price',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)});
  }catch(e){ fail('could not reach the local server'); return; }
  const j=await r.json();
  if(!r.ok){ fail(j.error||'request failed'); return; }
  jobId=j.job_id; poll();
}
function start(ev){ ev.preventDefault(); const u=$('#url').value.trim(); if(u) runJob({url:u}); }
function startFromCache(key){ runJob({cache_key:key}); }
// re-run the build that's currently loaded (URL or recent/cache) with the latest control
// values, so changing league / listing status / advanced / fresh pull takes effect at once.
function rerun(){ if(lastSource && (lastSource.url||lastSource.cache_key)) runJob(lastSource); }

function reltime(ts){
  const s=Math.max(0, Date.now()/1000 - ts);
  if(s<90) return 'just now';
  if(s<3600) return Math.round(s/60)+'m ago';
  if(s<86400) return Math.round(s/3600)+'h ago';
  return Math.round(s/86400)+'d ago';
}
async function fetchRecent(){
  let r; try{ r=await fetch('/api/cache'); }catch(e){ return; }
  if(!r.ok) return;
  RECENT=(await r.json()).builds || []; renderRecent();
}
function renderRecent(){
  const el=$('#recent'); if(!RECENT.length){ el.innerHTML=''; return; }
  const list=showAllRecent? RECENT : RECENT.slice(0,5);
  let h='<div class="rhead">Recent builds ('+RECENT.length+' cached)</div>';
  for(const b of list){
    const meta=[b.char_class, b.level? 'lvl '+b.level:'', b.league].filter(Boolean).join(' · ');
    h+='<div class="rbuild" data-key="'+esc(b.key)+'" title="Load from cache">'+
       '<span class="rname">'+esc(b.character||'(unknown)')+'</span>'+
       '<span class="rmeta">'+esc(meta)+'</span>'+
       '<span class="rwhen">'+esc(reltime(b.ts))+'</span></div>';
  }
  if(RECENT.length>5)
    h+='<button class="more" type="button" id="moretoggle">'+
       (showAllRecent? 'See fewer' : 'See more ('+(RECENT.length-5)+' more)')+'</button>';
  el.innerHTML=h;
}
function fail(msg){ setBusy(false); $('#status').innerHTML=''; $('#picker').innerHTML='';
  $('#out').innerHTML='<div class="err">'+esc(msg)+'</div>'; }

function poll(){
  polling=setInterval(async()=>{
    let r; try{ r=await fetch('/api/job?id='+jobId);}catch(e){return;}
    if(!r.ok){ clearInterval(polling); fail('lost the job'); return; }
    JOB=await r.json();
    if(JOB.state==='error'){ clearInterval(polling); fail(JOB.error||'error'); return; }
    if(JOB.items && JOB.items.length && !rendered){ renderSkeleton(); rendered=true; }
    if(rendered){ fillPriced(); renderGems(); recompute(); if(advanced) maybePresentRare(); }
    const last=(JOB.progress&&JOB.progress.length)?JOB.progress[JOB.progress.length-1]:'working...';
    if(JOB.state==='done' && !picking){
      clearInterval(polling); setBusy(false);
      $('#status').textContent=(JOB.searches!=null? JOB.searches+' trade searches used.':'');
      fetchRecent();
    }else if(picking){
      $('#status').textContent='Pick affixes for the rare below - the rest is pricing in the background.';
    }else{
      $('#status').innerHTML='<span class="spin"></span>'+esc(last);
    }
  },1000);
}

// the familiar "copy" glyph (two overlapping rectangles) + a check for the copied state
const COPY_SVG='<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
const CHECK_SVG='<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
const STATUS_LABEL={available:'Instant Buyout and In Person', securable:'Instant Buyout',
  onlineleague:'In Person (Online in League)', online:'In Person (Online)', any:'Any'};
function metaHead(){
  const m=JOB.meta, div=divr();
  const stat = m.status? ' &nbsp;|&nbsp; listings: '+esc(STATUS_LABEL[m.status]||m.status) : '';
  const pob = m.pob_code ? '<div class="pobbox"><div class="pobhd">Path of Building import code'+
    ' <button class="pobcopy" type="button" title="Copy import code" aria-label="Copy import code">'+COPY_SVG+'</button></div>'+
    '<textarea class="pobtext" readonly rows="2" spellcheck="false" onclick="this.select()">'+esc(m.pob_code)+'</textarea></div>' : '';
  return '<div class="meta"><h2>'+esc(m.character)+' <span class="sub">'+esc(m['class'])+
    ' &middot; level '+m.level+'</span></h2><div class="sub">League: '+esc(m.league)+
    (div? ' &nbsp;|&nbsp; 1 '+curImg('div')+' = '+nfmt(Math.round(div),0)+' '+curImg('chaos'):'')+stat+'</div>'+pob+'</div>';
}
function renderSkeleton(){
  rareOrder=JOB.items.filter(it=>it.category==='rare').map(it=>String(it.index));
  gemKeys=new Set(JOB.items.filter(it=>it.group==='gem').map(it=>String(it.index)));
  let h=metaHead();
  for(const [g,title] of GROUPS){
    const rows=JOB.items.filter(it=>it.group===g);
    if(!rows.length) continue;
    h+='<h3>'+esc(title)+'<label class="gtog"><input type="checkbox" class="gall" data-g="'+g+'" checked> all</label></h3>';
    if(g==='flask'){ h+=beltHTML(rows); continue; }             // D-0006 §C: 5-slot belt
    if(g==='gem'){ h+='<div id="gemsec"></div>'; continue; }    // D-0006 §D: grouped, filled by renderGems()
    h+='<table><thead><tr><th class="cb"></th><th>Item</th><th class="num">min</th>'+
       '<th class="num">median</th><th class="num">high</th><th>conf</th></tr></thead><tbody>';
    for(const it of rows){
      const k=String(it.index), cnt=it.count>1? ' &times;'+it.count : '';
      const reaffix = (advanced && it.category==='rare')
        ? ' <button class="reaffix" type="button" data-k="'+esc(k)+'" title="Re-open the affix picker and search this item again">edit affixes</button>' : '';
      h+='<tr data-k="'+esc(k)+'" class="pending">'+
         '<td class="cb"><input type="checkbox" class="row" data-k="'+esc(k)+'" disabled></td>'+
         '<td><span class="iname">'+esc(it.name)+'</span>'+cnt+reaffix+'<div class="note"></div></td>'+
         '<td class="num c-min">&hellip;</td><td class="num c-med">&hellip;</td>'+
         '<td class="num c-high">&hellip;</td><td class="c-conf"></td></tr>';
    }
    h+='</tbody></table>';
  }
  h+='<div class="totals"><h3>Total estimated build cost</h3>'+
     '<div class="totrow"><span>Minimum (budget)</span><b id="tmin">-</b></div>'+
     '<div class="totrow"><span>Median (typical)</span><b id="tmed">-</b></div>'+
     '<div class="totrow"><span>High (~90th pct)</span><b id="thigh">-</b></div>'+
     '<div id="tinc"></div></div>';
  $('#out').innerHTML=h;
}
// D-0006 §C: render the flask group as a 5-slot belt in flask order (overflow shown, never
// dropped; no life/mana classification -- a slot is just "belt position N"). Slots carry the
// same c-min/c-med/c-high/c-conf/note/iname/input.row hooks fillPriced() fills in place.
function beltHTML(rows){
  const n=Math.max(5,rows.length);
  let h='<div class="belt">';
  for(let i=0;i<n;i++){
    const it=rows[i];
    if(!it){ h+='<div class="beltslot empty"><div class="beltpos">slot '+(i+1)+'</div>'+
       '<div class="beltempty">empty</div></div>'; continue; }
    const k=String(it.index), cnt=it.count>1? ' &times;'+it.count : '';
    h+='<div class="beltslot pending" data-k="'+esc(k)+'">'+
       '<div class="belthd"><span class="beltpos">slot '+(i+1)+'</span>'+
         '<input type="checkbox" class="row" data-k="'+esc(k)+'" disabled></div>'+
       '<span class="iname">'+esc(it.name)+'</span>'+cnt+
       '<div class="beltnums"><span class="c-min">&hellip;</span> / '+
         '<span class="c-med">&hellip;</span> / <span class="c-high">&hellip;</span></div>'+
       '<div class="c-conf"></div><div class="note"></div></div>';
  }
  return h+'</div>';
}
// D-0006 §D: render the gem section grouped by HOST ITEM, supports nested under their active.
// Data-driven from JOB.items(gem)+JOB.priced; rebuilt only when a gem signature changes.
// Grouping uses the priced entry's host_* (authoritative); before a price lands it falls back
// to an ungrouped "Gems" bucket -- rows are never dropped.
function renderGems(){
  const host=$('#gemsec'); if(!host) return;
  const gemItems=JOB.items.filter(it=>it.group==='gem'); if(!gemItems.length) return;
  // default a gem's include-state the first time its price lands: ON iff priced & not granted.
  gemItems.forEach(it=>{ const k=String(it.index), p=JOB.priced[k];
    if(p && p.chaos.median!=null && !gemDefaulted.has(k)){ gemDefaulted.add(k); enabled[k]=!it.granted; }});
  const sig=gemItems.map(it=>{ const k=String(it.index), p=JOB.priced[k];
    return k+':'+(p? (p.total_chaos+'|'+p.confidence+'|'+(p.gems?p.gems.length:0)+'|'+(p.host_inventory_id||'')+'|'+p.trade_url) : '-')+
      ':'+(enabled[k]?1:0)+':'+(it.granted?1:0); }).join(',');
  if(sig===gemSig) return; gemSig=sig;
  const groups=[], byKey={};
  gemItems.forEach(it=>{ const k=String(it.index), p=JOB.priced[k]||{};
    const gk=(p.host_inventory_id||it.host_inventory_id||'');
    let grp=byKey[gk];
    if(!grp){ grp={key:gk, slot:(p.host_slot||it.host_slot||''), name:(p.host_name||it.host_name||''),
        unique:!!(p.host_unique||it.host_unique), items:[]}; byKey[gk]=grp; groups.push(grp); }
    grp.items.push(it);
  });
  let h='';
  for(const grp of groups){
    const header = grp.slot&&grp.name ? esc(grp.slot)+' &mdash; '+esc(grp.name)
      : (grp.slot? esc(grp.slot) : (grp.name? esc(grp.name) : 'Gems'));
    h+='<div class="gemgroup"><div class="gemhdr">'+header+
       (grp.unique?' <span class="uniqtag">unique</span>':'')+'</div>'+
       '<table><thead><tr><th class="cb"></th><th>Skill</th>'+
       '<th class="num">total</th><th>conf</th></tr></thead><tbody>';
    for(const it of grp.items) h+=gemRowHTML(it);
    h+='</tbody></table></div>';
  }
  host.innerHTML=h;
}
function gemRowHTML(it){
  const k=String(it.index), p=JOB.priced[k], div=divr();
  const priced = !!(p && p.chaos.median!=null);
  const granted = !!it.granted;
  const active = (p && p.gems && p.gems.length) ? p.gems[0] : null;
  const cls=['gemrow']; if(granted) cls.push('granted');
  if(!priced && !granted) cls.push('unpriced');
  cls.push(enabled[k]? 'on':'off');
  const lv=(active? active.level : it.level), q=(active? active.quality : it.quality);
  let nm=esc(it.name)+' <span class="gmeta">Lv '+lv+'/'+q+'</span>';
  if(active && active.trade_url) nm='<a href="'+esc(active.trade_url)+'" target="_blank" rel="noopener">'+nm+'</a>';
  if(granted) nm+=' <span class="badge-granted">granted</span>';
  // nested linked gems: prefer the priced gems[1:] (per-gem price); fall back to skeleton supports.
  const nested = (p && p.gems && p.gems.length>1) ? p.gems.slice(1)
    : (it.supports||[]).map(s=>({name:s.name, level:s.level, quality:s.quality,
        chaos:null, granted:!!s.granted, support:s.support!==false}));
  let sup='';
  if(nested.length){
    sup='<div class="sups">';
    for(const g of nested){
      const gc = (g.chaos!=null)? fmt(g.chaos,div) : '&mdash;';
      const sc=['sup']; if(g.granted) sc.push('sgr');
      sup+='<div class="'+sc.join(' ')+'">'+(g.support===false?'+ ':'&#8627; ')+esc(g.name)+
        ' <span class="gmeta">Lv '+g.level+'/'+g.quality+'</span> '+
        '<span class="supprice">'+gc+'</span>'+
        (g.granted?' <span class="badge-granted">granted</span>':'')+'</div>';
    }
    sup+='</div>';
  }
  const note = (p && p.note)? '<div class="note">'+esc(p.note)+'</div>' : '';
  const total = priced ? fmt(p.chaos.median,div) : (granted? '&mdash;' : '&hellip;');
  const conf  = p? '<span class="badge '+esc(p.confidence)+'">'+esc(p.confidence)+'</span>' : '';
  return '<tr data-k="'+esc(k)+'" class="'+cls.join(' ')+'">'+
    '<td class="cb"><input type="checkbox" class="row" data-k="'+esc(k)+'"'+
      (priced?'':' disabled')+(enabled[k]?' checked':'')+'></td>'+
    '<td>'+nm+sup+note+'</td>'+
    '<td class="num">'+total+'</td><td>'+conf+'</td></tr>';
}
function fillPriced(){
  const div=divr();
  for(const k in JOB.priced){
    if(gemKeys.has(k)) continue;                  // gems are rendered by renderGems() (D-0006 §D)
    const p=JOB.priced[k], priced=p.chaos.median!=null;
    const sig=p.method+'|'+p.chaos.min+'|'+p.chaos.median+'|'+p.chaos.high+'|'+p.note+'|'+p.trade_url;
    if(filled[k]===sig) continue;                 // re-render when the price changes (re-search)
    const row=document.querySelector('[data-k="'+cssesc(k)+'"]'); if(!row) continue;
    filled[k]=sig;
    row.querySelector('.c-min').innerHTML=fmt(p.chaos.min,div);
    row.querySelector('.c-med').innerHTML=fmt(p.chaos.median,div);
    row.querySelector('.c-high').innerHTML=fmt(p.chaos.high,div);
    row.querySelector('.c-conf').innerHTML='<span class="badge '+esc(p.confidence)+'">'+esc(p.confidence)+'</span>';
    row.querySelector('.note').textContent=p.note||'';
    if(p.trade_url){
      const nameEl=row.querySelector('.iname'), a=document.createElement('a');
      a.href=p.trade_url; a.target='_blank'; a.rel='noopener'; a.className='iname';
      a.textContent=nameEl.textContent; nameEl.replaceWith(a);   // keep class so re-fills work
    }
    row.classList.remove('pending','await');
    const cb=row.querySelector('input.row');
    if(priced){ cb.disabled=false; cb.checked=true; enabled[k]=true; }
    else { row.classList.add('unpriced'); }
  }
  if(advanced) rareOrder.forEach(k=>{
    const row=document.querySelector('[data-k="'+cssesc(k)+'"]');
    if(row && !filled[k] && JOB.rares[k] && JOB.rares[k].status==='awaiting'){
      row.classList.add('await'); const med=row.querySelector('.c-med'); if(med) med.textContent='awaiting input';
    }
  });
}
function recompute(){
  if(!JOB||!JOB.items) return;
  const div=divr(); let mn=0,md=0,hi=0,inc=0,tot=0;
  for(const it of JOB.items){
    const k=String(it.index), p=JOB.priced[k];
    if(!p || p.chaos.median==null) continue;
    tot++;
    const row=document.querySelector('[data-k="'+cssesc(k)+'"]');
    if(enabled[k]){
      inc++; const c=it.count||1;
      if(p.chaos.min!=null) mn+=p.chaos.min*c;
      md+=p.chaos.median*c; if(p.chaos.high!=null) hi+=p.chaos.high*c;
      if(row){ row.classList.add('on'); row.classList.remove('off'); }
    }else if(row){ row.classList.add('off'); row.classList.remove('on'); }
  }
  if($('#tmin')){ $('#tmin').innerHTML=fmt(mn,div); $('#tmed').innerHTML=fmt(md,div);
    $('#thigh').innerHTML=fmt(hi,div); $('#tinc').textContent=inc+' of '+tot+' priced items included'; }
  document.querySelectorAll('input.gall').forEach(g=>{
    const ks=JOB.items.filter(it=>it.group===g.dataset.g).map(it=>String(it.index))
      .filter(k=>JOB.priced[k]&&JOB.priced[k].chaos.median!=null);
    g.checked = ks.length>0 && ks.every(k=>enabled[k]);
  });
}

// ---- advanced affix picker ----
function maybePresentRare(){
  if(picking) return;
  for(let i=0;i<rareOrder.length;i++){            // show the first rare not yet decided
    if(!decided.has(rareOrder[i])){ curRare=i; showPicker(rareOrder[i]); return; }
  }
  $('#picker').innerHTML='';                        // all rares handled
}
function backRare(){
  if(curRare<=0) return;
  curRare--;
  showPicker(rareOrder[curRare]);                   // re-open a previous rare to fix it
}
function reSearchRare(k){                            // "edit affixes": re-open + re-price a rare
  if(!JOB||!JOB.rares||!JOB.rares[k]) return;
  const i=rareOrder.indexOf(k); if(i>=0) curRare=i;
  if(polling) clearInterval(polling);
  poll();                                            // the build may have finished; resume polling
  setBusy(true);
  showPicker(k);
}
function copyPob(btn){
  const box=btn.closest('.pobbox'); if(!box) return;
  const ta=box.querySelector('.pobtext'); ta.select();
  const done=()=>{ btn.innerHTML=CHECK_SVG; btn.classList.add('ok');
    setTimeout(()=>{ btn.innerHTML=COPY_SVG; btn.classList.remove('ok'); },1200); };
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(ta.value).then(done,()=>{ try{document.execCommand('copy');}catch(e){} done(); });
  }else{ try{document.execCommand('copy');}catch(e){} done(); }
}
function showPicker(k){
  const rare=JOB.rares[k];
  if(!rare){ decided.add(k); maybePresentRare(); return; }  // missing data -> skip it
  picking=true; curRareKey=k;
  usePseudo = !!(rare.pseudo && rare.pseudo.length);  // default ON when resistances exist
  try{ renderPicker(); }
  catch(e){ picking=false; decided.add(k); $('#picker').innerHTML=''; maybePresentRare(); }
}
function affixRow(a){
  if(a.searchable){
    const v=a.value!=null? a.value : '';
    // negated ('reduced') mods carry a NEGATIVE value on the opposite-polarity stat -> prefill
    // MAX (e.g. max:-21 = "at least 21% reduced"), not MIN (which would be a near no-op filter).
    const neg = a.negated || (a.value!=null && a.value<0);
    const attr = a.kind==='equip' ? ('data-equip="'+esc(a.key)+'"') : ('data-sid="'+esc(a.stat_id)+'"');
    return '<div class="afx" '+attr+'><input type="checkbox" class="acb" checked>'+
       '<div class="atext">'+esc(a.text)+'</div>'+
       '<input class="mm amin" value="'+(neg?'':esc(v))+'"><input class="mm amax" value="'+(neg?esc(v):'')+'"></div>';
  }
  return '<div class="afx no"><div></div><div class="atext">'+esc(a.text)+
     '<div class="areason">'+esc(a.reason||'')+'</div></div><div></div><div></div></div>';
}
function renderPicker(){
  const k=curRareKey, rare=JOB.rares[k];
  const redo = decided.has(k);
  const remain = rareOrder.filter(x=>!decided.has(x)).length;   // D-0006 §E: rares still to decide
  let h='<div class="pcard"><div class="ptitle">Rare '+(curRare+1)+' of '+rareOrder.length+': '+esc(rare.name)+'</div>'+
    '<div class="psub">Tick the affixes a comparable item must have; set min/max (blank = any). Scope: '+esc(rare.scope)+
    (redo? ' <b>(already submitted - re-submit to replace it)</b>' : '')+'</div>';
  // D-0006 §E: glowing "Autoscan" at the TOP -- prices every remaining rare with its default
  // all-affix search (the former "Search all N"). Only shown when >1 rare still needs a decision.
  if(remain>1) h+='<div class="pautoscan"><button class="autoscan" id="pSearchAll" type="button" '+
    'title="price all '+remain+' remaining rares with default all-affix searches">'+
    '⚡ Autoscan ('+remain+')</button></div>';
  if(rare.pseudo && rare.pseudo.length){
    h+='<label class="ptoggle"><input type="checkbox" class="pseudotgl" '+(usePseudo?'checked':'')+'> '+
       'Combine resistances into a pseudo total (search the item\'s total resistance instead of each one)</label>';
  }
  h+='<div class="afx" style="border:0"><div></div><div></div><div class="mmh">min</div><div class="mmh">max</div></div>';
  // when pseudo is on, hide individual resistance affixes and show the combined totals
  rare.affixes.forEach(a=>{ if(!(usePseudo && a.resist)) h+=affixRow(a); });
  if(usePseudo) rare.pseudo.forEach(p=>{ h+=affixRow(p); });
  h+='<div class="pbtns">'+
     (curRare>0? '<button class="pback skip" type="button">&larr; Back</button>' : '')+
     '<button class="psubmit" type="button">'+(redo? 'Re-search this item' : 'Search this item')+'</button>'+
     '<button class="pskip skip" type="button">Skip (don\'t price)</button>'+
     '<span class="pqueue">Rare '+(curRare+1)+' of '+rareOrder.length+'</span></div>';
  // D-0006 §E: small, non-glowing "skip all (don't price)" kept below the per-item buttons.
  if(remain>1) h+='<div class="pbulk"><button class="skipall" id="pSkipAll" type="button">'+
    'skip all (don\'t price)</button></div>';
  h+='</div>';
  $('#picker').innerHTML=h;
}
async function submitRare(skip){
  if(curRare>=rareOrder.length) return;
  const k=rareOrder[curRare];
  let body;
  if(skip){ body={skip:true}; }
  else{
    const sels=[], equips=[];
    document.querySelectorAll('#picker .afx[data-sid]').forEach(row=>{
      const cb=row.querySelector('.acb'); if(!cb||!cb.checked) return;
      sels.push({stat_id:row.dataset.sid, min:pnum(row.querySelector('.amin').value),
                 max:pnum(row.querySelector('.amax').value)});
    });
    document.querySelectorAll('#picker .afx[data-equip]').forEach(row=>{
      const cb=row.querySelector('.acb'); if(!cb||!cb.checked) return;
      equips.push({key:row.dataset.equip, min:pnum(row.querySelector('.amin').value),
                   max:pnum(row.querySelector('.amax').value)});
    });
    body={filters:sels, equip:equips};
  }
  decided.add(k); picking=false; $('#picker').innerHTML='';
  await postRare(k, body);
  if(JOB) maybePresentRare();        // advance to the next rare still needing input
}
function postRare(k, body){
  return fetch('/api/rare?id='+jobId+'&index='+encodeURIComponent(k),
    {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).catch(()=>{});
}
// D-0006 §E: the default all-affix search for one rare, built WITHOUT the DOM (mirrors what
// "Search this item" submits with no edits). Negated ('reduced') mods carry a NEGATIVE value on
// the opposite-polarity stat -> filter on MAX, not MIN. `prefer` (backend) marks default-checked
// affixes; fall back to `searchable` for older payloads.
function defaultRarePayload(k){
  const r=JOB.rares[k]; if(!r) return {filters:[], equip:[]};
  const usePs=!!(r.pseudo && r.pseudo.length);
  const filters=[], equip=[];
  const want=a=>a.prefer!==undefined? !!a.prefer : !!a.searchable;
  const statF=a=>(a.negated||(a.value!=null&&a.value<0))
    ? {stat_id:a.stat_id, min:null, max:a.value}
    : {stat_id:a.stat_id, min:a.value, max:null};
  (r.affixes||[]).forEach(a=>{
    if(!a.searchable || !want(a)) return;
    if(usePs && a.resist) return;                       // covered by the pseudo total
    if(a.kind==='equip') equip.push({key:a.key, min:a.value, max:null});
    else filters.push(statF(a));
  });
  if(usePs) (r.pseudo||[]).forEach(p=>{ if(p.searchable && want(p)) filters.push(statF(p)); });
  return {filters:filters, equip:equip};
}
// D-0006 §E: Autoscan -- price every remaining rare with its default all-affix search.
async function searchAllRares(){
  picking=false; curRareKey=null; $('#picker').innerHTML='';
  const rem=rareOrder.filter(x=>!decided.has(x));
  for(const k of rem){
    decided.add(k);
    await postRare(k, JOB.rares[k]? defaultRarePayload(k) : {skip:true});
  }
  if(JOB) maybePresentRare();
}
// D-0006 §E: skip all -- decide every remaining rare as "don't price".
async function skipAllRares(){
  picking=false; curRareKey=null; $('#picker').innerHTML='';
  const rem=rareOrder.filter(x=>!decided.has(x));
  for(const k of rem){ decided.add(k); await postRare(k, {skip:true}); }
  if(JOB) maybePresentRare();
}

document.addEventListener('click',e=>{
  const t=e.target; if(!t.classList) return;
  if(t.id==='pSearchAll'){ searchAllRares(); return; }   // D-0006 §E: Autoscan (top of picker)
  if(t.id==='pSkipAll'){ skipAllRares(); return; }       // D-0006 §E: skip all (below picker)
  if(t.classList.contains('pback')){ backRare(); return; }
  if(t.classList.contains('psubmit')){ submitRare(false); return; }
  if(t.classList.contains('pskip')){ submitRare(true); return; }
  if(t.classList.contains('reaffix')){ reSearchRare(t.dataset.k); return; }
  const cp=t.closest&&t.closest('.pobcopy'); if(cp){ copyPob(cp); return; }
  if(t.id==='moretoggle'){ showAllRecent=!showAllRecent; renderRecent(); return; }
  const rb=t.closest && t.closest('.rbuild');
  if(rb){ startFromCache(rb.dataset.key); }
});
document.addEventListener('change',e=>{
  const t=e.target; if(!t.classList) return;
  if(t.classList.contains('pseudotgl')){
    usePseudo=t.checked; renderPicker();
  }else if(t.classList.contains('row')){
    enabled[t.dataset.k]=t.checked; recompute();
  }else if(t.classList.contains('gall')){
    const grp=t.dataset.g;
    JOB.items.forEach(it=>{ const k=String(it.index);
      if(it.group===grp && JOB.priced[k] && JOB.priced[k].chaos.median!=null){
        enabled[k]=t.checked;
        const cb=document.querySelector('input.row[data-k="'+cssesc(k)+'"]'); if(cb) cb.checked=t.checked;
      }});
    recompute();
  }
});
$('#f').addEventListener('submit',start);

// --- remember preferences between sessions (localStorage) ---
function lsget(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } }
function lsset(k,v){ try{ localStorage.setItem(k,v); }catch(e){} }
// advanced affix search: on by default
(function(){
  const a=lsget('bpc_advanced'); $('#advanced').checked = (a===null)?true:(a==='1');
  $('#advanced').addEventListener('change',e=>{ lsset('bpc_advanced', e.target.checked?'1':'0'); rerun(); });
})();
// listing status: default = In Person (Online); remembered
(function(){
  const s=lsget('bpc_status'); if(s) $('#liststatus').value=s;
  $('#liststatus').addEventListener('change',e=>{ lsset('bpc_status', e.target.value); rerun(); });
})();
// fresh pull: re-run the current build (re-fetching) the moment it's toggled
$('#refresh').addEventListener('change',rerun);
// league dropdown: populated from the trade site, default Auto; remembered
async function fetchLeagues(){
  let r; try{ r=await fetch('/api/leagues'); }catch(e){ return; }
  if(!r.ok) return;
  const sel=$('#league'), leagues=(await r.json()).leagues||[];
  sel.innerHTML='<option value="">League: auto</option>'+
    leagues.map(l=>'<option value="'+esc(l)+'">'+esc(l)+'</option>').join('');
  const saved=lsget('bpc_league');
  if(saved!==null && [...sel.options].some(o=>o.value===saved)) sel.value=saved;
}
$('#league').addEventListener('change',e=>{ lsset('bpc_league', e.target.value); rerun(); });
fetchLeagues();
fetchRecent();
</script>
</body></html>"""


def _bind(host, port):
    """Bind the first free port at/after `port` (so a stale instance or another app
    holding the default port doesn't make us crash silently)."""
    last = None
    for p in range(port, port + 12):
        try:
            return ThreadingHTTPServer((host, p), Handler), p
        except OSError as e:
            last = e
    raise SystemExit(f"could not bind a port in {port}-{port + 11} on {host}: {last}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="bpc.web", description="Local web UI for the PoE1 build price checker.")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)

    srv, port = _bind(args.host, args.port)
    url = f"http://{args.host}:{port}"
    print(f"PoE1 Build Price Checker is running.\n  Open: {url}\n  (Ctrl+C here to stop)",
          flush=True)
    # Pre-warm the (league-agnostic, disk-cached) trade stat dictionary in the background so
    # /api/stats is never a cold fetch racing a pricing search. Best-effort; ignore failures.
    def _warm_stats():
        try:
            TradeClient("Standard").stats_data()
        except Exception:
            pass
    threading.Thread(target=_warm_stats, daemon=True).start()
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
        srv.shutdown()


if __name__ == "__main__":
    main()
