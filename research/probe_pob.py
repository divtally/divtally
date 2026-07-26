"""Probe: obtain a REAL Path of Building (PoE1) export and decode it to XML.

Run from the repo root:  python research/probe_pob.py

Source of the PoB code (in priority order):
  1. research/data/char_poe1.json  -- if present, decode its "pathOfBuildingExport"
     (a poe.ninja PoE1 /character API response; see the live flow below for its shape).
  2. Live poe.ninja PoE1 flow (no login, no pathofexile.com trade calls):
       GET /poe1/api/data/index-state         -> current "exp" snapshot version + name
       GET /poe1/api/builds/<version>/search   -> protobuf table of ranked characters
                                                  (columns include name + account)
       GET /poe1/api/builds/<version>/character?account=..&name=..&overview=..&type=exp
                                                  -> JSON with "pathOfBuildingExport"

A PoB code is URL-safe base64 of zlib-compressed XML rooted at <PathOfBuilding>
(PoE1) -- identical envelope to PoB2's <PathOfBuilding2>. Writes the XML to
research/data/pob_sample.xml.

All network calls target poe.ninja only, politely (single-shot, real User-Agent).
"""
import base64
import json
import os
import re
import zlib

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 buildpricechecker-poe1/0.1")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CHAR_JSON = os.path.join(DATA, "char_poe1.json")
OUT_XML = os.path.join(DATA, "pob_sample.xml")
INDEX_STATE = "https://poe.ninja/poe1/api/data/index-state"


def decode(code):
    """PoB import code -> XML string (base64url or std base64, then zlib)."""
    code = re.sub(r"\s+", "", code or "")
    if code.lower().startswith("pob://"):
        code = code[6:]
    pad = "=" * (-len(code) % 4)
    last = None
    for fn in (base64.urlsafe_b64decode, base64.standard_b64decode):
        try:
            return zlib.decompress(fn(code + pad)).decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError("not a valid Path of Building code (%s)" % last)


# --- minimal protobuf wire reader (the /search response is application/x-protobuf) ---
def _read_varint(buf, i):
    shift = 0
    result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def _fields(buf):
    """Yield (field_number, wire_type, payload) for one protobuf message."""
    i = 0
    n = len(buf)
    out = []
    while i < n:
        try:
            key, i = _read_varint(buf, i)
        except IndexError:
            break
        fnum, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _read_varint(buf, i)
            out.append((fnum, 0, v))
        elif wt == 2:
            ln, i = _read_varint(buf, i)
            out.append((fnum, 2, buf[i:i + ln]))
            i += ln
        elif wt == 5:
            i += 4
        elif wt == 1:
            i += 8
        else:
            break
    return out


def _search_pairs(pb):
    """Extract row-aligned (account, name) pairs from the /search protobuf.

    Layout (reverse-engineered 2026-07-26): top msg -> field 1 (body) ->
    repeated field 5 = one column each {field 1 = column key, field 2 = repeated
    per-row value msg whose first length-delimited child is the string}."""
    body = next(v for f, wt, v in _fields(pb) if f == 1 and wt == 2)
    columns = {}
    for f, wt, v in _fields(body):
        if f != 5 or wt != 2:
            continue
        name = None
        rows = []
        for cf, cwt, cv in _fields(v):
            if cf == 1 and cwt == 2 and all(32 <= c < 127 for c in cv):
                name = cv.decode()
            elif cf == 2 and cwt == 2:
                s = None
                for rf, rwt, rv in _fields(cv):
                    if rwt == 2 and all(32 <= c < 127 for c in rv):
                        s = rv.decode()
                        break
                rows.append(s)
        if name:
            columns[name] = rows
    accts, names = columns.get("account", []), columns.get("name", [])
    return [(a, n) for a, n in zip(accts, names) if a and n]


def from_live():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    idx = s.get(INDEX_STATE, timeout=30).json()
    sv = next(v for v in idx["snapshotVersions"] if v.get("type") == "exp")
    version, snap = sv["version"], sv["snapshotName"]
    print("snapshot:", sv["name"], "version=", version, "overview=", snap)
    pb = s.get("https://poe.ninja/poe1/api/builds/%s/search" % version,
               params={"overview": snap, "type": "exp"}, timeout=60).content
    pairs = _search_pairs(pb)
    print("ranked characters found:", len(pairs))
    base = "https://poe.ninja/poe1/api/builds/%s/character" % version
    for acc, nm in pairs[:15]:
        r = s.get(base, params={"account": acc, "name": nm, "overview": snap,
                                "type": "exp", "timeMachine": ""}, timeout=45)
        if r.status_code != 200:
            continue
        j = r.json()
        code = j.get("pathOfBuildingExport")
        if code:
            print("using character:", acc, "/", nm)
            return code.strip()
    raise RuntimeError("no character with a pathOfBuildingExport found")


def main():
    if os.path.exists(CHAR_JSON):
        print("source: research/data/char_poe1.json")
        code = json.load(open(CHAR_JSON, encoding="utf-8"))["pathOfBuildingExport"].strip()
    else:
        print("source: live poe.ninja PoE1 flow")
        code = from_live()
    xml = decode(code)
    os.makedirs(DATA, exist_ok=True)
    open(OUT_XML, "w", encoding="utf-8").write(xml)
    print("XML length:", len(xml))
    print("root tag:", re.findall(r"<(\w+)[ >]", xml)[:1])
    m = re.search(r"<Build [^>]*>", xml)
    print("Build:", m.group(0)[:200] if m else None)
    slots = re.findall(r'<Slot [^>]*name="([^"]+)"[^>]*itemId="([^"]+)"', xml)
    equipped = [(n, i) for n, i in slots
                if i != "0" and "Abyssal" not in n and "Graft" not in n]
    print("equipped slots:", equipped)
    gems = re.findall(r'<Gem [^>]*nameSpec="([^"]+)"', xml)
    print("gems (named):", len(gems), "-> wrote", OUT_XML)


if __name__ == "__main__":
    main()
