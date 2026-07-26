"""Reusable live-probe for the poe.ninja PATH OF EXILE 1 builds pipeline.

This maps the endpoints that a PoE1 port of ``bpc/poeninja.py`` depends on and
dumps one real character to ``research/data/char_poe1.json``. Everything here hits
ONLY poe.ninja (cheap, cached, polite) -- it NEVER touches the pathofexile.com
trade API. Run from the repo root:

    python research/probe_ninja.py                 # full pipeline, saves char JSON
    python research/probe_ninja.py --league allflame
    python research/probe_ninja.py --account example-0416 --name TestCharacter

Findings (verified live 2026-07-26, current league "Allflame"):

  index-state   GET https://poe.ninja/poe1/api/data/index-state          -> JSON
  search        GET https://poe.ninja/poe1/api/builds/{version}/search    -> PROTOBUF
                    ?overview={snapshotName}
  character     GET https://poe.ninja/poe1/api/builds/{version}/character  -> JSON
                    ?account={dash-account}&name={char}&overview={snapshotName}&timeMachine=

Key gotchas the port must honour:
  * Path prefix is /poe1/ (NOT /poe2/ and NOT the bare /api used by the old site).
  * ``overview`` must be the snapshotName, which differs from the league url slug
    for 96/106 snapshots (e.g. slug 'allflamehc' -> snapshotName 'hardcore-allflame').
  * The API accepts ONLY the dash-encoded account form ('Name-1234'); the raw
    'Name#1234' returns 404. Convert '#' + trailing digits -> '-' before calling.
  * The /search endpoint is protobuf; the /character endpoint is JSON. The port
    only needs /character (JSON) -- /search is used here purely to discover a real
    (account, name) pair to test with.
"""
import argparse
import json
import os
import sys
import urllib.parse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 buildpricechecker/0.1")
POE1 = "https://poe.ninja/poe1"
INDEX_STATE = POE1 + "/api/data/index-state"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    return s


# ---- index-state / league resolution -------------------------------------
def index_state(s):
    r = s.get(INDEX_STATE, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_league(idx, slug):
    """slug -> (version, snapshotName, displayName). Mirrors what the port needs.

    NOTE: each league url has TWO snapshotVersions (type 'exp' and 'depthsolo')
    with the SAME version + snapshotName, so we prefer type=='exp' for determinism.
    """
    matches = [sv for sv in idx.get("snapshotVersions", []) if sv.get("url") == slug]
    if not matches:
        known = sorted({sv.get("url", "") for sv in idx.get("snapshotVersions", [])})
        raise SystemExit("league slug %r not in current snapshots. Known: %s"
                         % (slug, ", ".join(known)))
    sv = next((m for m in matches if m.get("type") == "exp"), matches[0])
    league = next((b.get("name") for b in idx.get("buildLeagues", [])
                   if b.get("url") == slug), sv.get("name", slug))
    return sv["version"], sv["snapshotName"], league


# ---- generic protobuf decoder (search response only) ---------------------
def _rv(b, i):
    shift = 0
    res = 0
    while True:
        c = b[i]
        i += 1
        res |= (c & 0x7f) << shift
        if not (c & 0x80):
            break
        shift += 7
    return res, i


def _parse(b):
    """Yield (field_number, wire_type, value) for one protobuf message level."""
    i = 0
    out = []
    n = len(b)
    while i < n:
        try:
            key, i = _rv(b, i)
        except IndexError:
            break
        field = key >> 3
        wire = key & 7
        if wire == 0:
            v, i = _rv(b, i)
            out.append((field, 0, v))
        elif wire == 2:
            ln, i = _rv(b, i)
            out.append((field, 2, b[i:i + ln]))
            i += ln
        elif wire == 5:
            out.append((field, 5, b[i:i + 4]))
            i += 4
        elif wire == 1:
            out.append((field, 1, b[i:i + 8]))
            i += 8
        else:
            break
    return out


def _as_str(seg):
    try:
        t = seg.decode("utf-8")
        return t if t.isprintable() else None
    except Exception:
        return None


def search_rows(s, version, snapshot_name, limit=100):
    """Decode the columnar protobuf /search response into aligned dicts.

    The response wraps everything in field 1. Inside, field 5 holds the columnar
    result table: repeated Column{ key(1)=string; values(2)=repeated {1: string} }.
    Columns observed: name, account, class, skills, keypassives, level, life,
    energyshield, ehp, dps -- all the same length and aligned by row index.
    Returns a list of {"account","name"} (dash-encoded account form).
    """
    url = POE1 + "/api/builds/%s/search" % version
    r = s.get(url, params={"overview": snapshot_name}, timeout=60)
    r.raise_for_status()
    top = _parse(r.content)
    wrapper = next((v for f, w, v in top if f == 1 and w == 2), None)
    if wrapper is None:
        return []
    cols = {}
    for f, w, v in _parse(wrapper):
        if f != 5 or w != 2:
            continue
        key = None
        vals = []
        for sf, sw, sv in _parse(v):
            if sf == 1 and sw == 2 and key is None:
                key = _as_str(sv)
            elif sf == 2 and sw == 2:
                inner = next((x[2] for x in _parse(sv) if x[0] == 1 and x[1] == 2), None)
                vals.append(_as_str(inner) if inner is not None else None)
        if key:
            cols[key] = vals
    names = cols.get("name", [])
    accts = cols.get("account", [])
    rows = []
    for a, nm in list(zip(accts, names))[:limit]:
        if a and nm:
            rows.append({"account": a, "name": nm})
    return rows


# ---- account encoding -----------------------------------------------------
def dash_account(account):
    """Encode a PoE account so the /character API accepts it: the LAST '#'
    followed only by digits becomes '-' (matches poe.ninja's own encoder,
    regex /\\d/). 'Name#1234' -> 'Name-1234'. Already-dashed input is returned
    unchanged. The API returns 404 for the raw '#' form."""
    for i in range(len(account) - 1, -1, -1):
        ch = account[i]
        if ch.isdigit():
            continue
        if ch == "#":
            return account[:i] + "-" + account[i + 1:]
        break
    return account


# ---- character ------------------------------------------------------------
def fetch_character(s, version, snapshot_name, account, name):
    url = POE1 + "/api/builds/%s/character" % version
    params = {"account": dash_account(account), "name": name,
              "overview": snapshot_name, "timeMachine": ""}
    r = s.get(url, params=params, timeout=45)
    if not r.ok:
        raise SystemExit("HTTP %s for %s (account/name may be wrong, or the "
                         "character is private/unindexed)" % (r.status_code, r.url))
    ctype = r.headers.get("content-type", "")
    if "json" not in ctype:
        raise SystemExit("character endpoint returned %s, not JSON" % ctype)
    return r.json()


def user_url(slug, account, name):
    """The public poe.ninja character URL a user would paste."""
    return (POE1 + "/builds/%s/character/%s/%s"
            % (slug, urllib.parse.quote(dash_account(account)),
               urllib.parse.quote(name)))


def main():
    ap = argparse.ArgumentParser(description="Probe poe.ninja PoE1 builds pipeline")
    ap.add_argument("--league", default=None,
                    help="league url slug (default: first/current snapshot)")
    ap.add_argument("--account", default=None, help="account (dash or # form)")
    ap.add_argument("--name", default=None, help="character name")
    ap.add_argument("--out", default=os.path.join(DATA_DIR, "char_poe1.json"))
    args = ap.parse_args()

    s = session()
    idx = index_state(s)
    slug = args.league or idx["snapshotVersions"][0]["url"]
    version, snapshot_name, league = resolve_league(idx, slug)
    print("league slug=%s -> version=%s snapshotName=%s display=%s"
          % (slug, version, snapshot_name, league))

    if not (args.account and args.name):
        rows = search_rows(s, version, snapshot_name, limit=100)
        print("search returned %d rows; using row 0" % len(rows))
        if not rows:
            raise SystemExit("no rows from search; pass --account/--name explicitly")
        account = args.account or rows[0]["account"]
        name = args.name or rows[0]["name"]
    else:
        account, name = args.account, args.name

    print("fetching character account=%s name=%s" % (dash_account(account), name))
    data = fetch_character(s, version, snapshot_name, account, name)
    print("public URL: %s" % user_url(slug, account, name))
    print("top-level keys: %s" % ", ".join(data.keys()))
    print("class=%s level=%s items=%d flasks=%d jewels=%d skills=%d pob=%d bytes"
          % (data.get("class"), data.get("level"), len(data.get("items", [])),
             len(data.get("flasks", [])), len(data.get("jewels", [])),
             len(data.get("skills", [])), len(data.get("pathOfBuildingExport") or "")))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("saved %s" % args.out)


if __name__ == "__main__":
    sys.exit(main())
