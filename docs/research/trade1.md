# PoE1 official trade API - reverse-engineering notes (for porting trade2)

Live-probed 2026-07-26 against `https://www.pathofexile.com/api/trade` (the PoE1 realm; NOT
`/api/trade2`). Every JSON shape / id / header below is copied from an actual 200 (or 400)
response saved under `research/data/trade_*.json`. Reproduce with
`python research/probe_trade.py data` then `python research/probe_trade.py search ...`.

Evidence tags: **[LIVE]** = seen in a real response this session. **[SCHEMA]** = from the
API's own `/api/trade/data/filters` schema. **[REF]** = from the parent PoE2 code we port.
**[INFERRED]** / **[NOT RE-TESTED]** = not directly exercised here - treat as a port risk.

---

## 0. Current leagues (July 2026) [LIVE - trade_leagues.json]
`/data/leagues` `result[]` = `{id, realm, text}`. Current challenge league id = **`Allflame`**
(realm `pc`); HC/Ruthless variants: `Hardcore Allflame`, `Ruthless Allflame`,
`HC Ruthless Allflame`. Permanent: `Standard`, `Hardcore`, `Ruthless`, `Hardcore Ruthless`.
Same ids repeat under realm `xbox` and `sony`. **Do not hardcode the league** - read it live
(TTL cache, as the parent does). The league string goes in the URL path verbatim (URL-encoded).

---

## 1. Endpoint paths [LIVE]
Base = `https://www.pathofexile.com/api/trade` (drop the `2`; there is **no `poe2` realm
segment** in the path). PC is the default realm; other realms use `?realm=xbox|sony`.

| Purpose | Method + path | Notes |
|---|---|---|
| Leagues | `GET /api/trade/data/leagues` | `{result:[{id,realm,text}]}` |
| Base types | `GET /api/trade/data/items` | `{result:[{label,entries:[{type[,name,text,flags]}]}]}` |
| Stat filters | `GET /api/trade/data/stats` | `{result:[{label,entries:[{id,text[,type,option]}]}]}` |
| Static (currency/img) | `GET /api/trade/data/static` | `{result:[{id,label,entries:[{id,text,image}]}]}` |
| **Filter schema** | `GET /api/trade/data/filters` | **exists in PoE1** - authoritative group/field/option names |
| Search | `POST /api/trade/search/{league}` | body `{query,sort}` -> `{id,complexity,result:[hash,...<=100],total}` |
| Fetch | `GET /api/trade/fetch/{id1,..,id10}?query={qid}` | **<=10 ids** (11 -> HTTP 400); `{result:[{id,listing,item}]}` |
| Bulk exchange | `POST /api/trade/exchange/{league}` | body `{query,sort,engine}` -> `{id,complexity,result:{hash:{...}},total}` |

`/data/*` responses carried **no `X-Rate-Limit-*` headers** [LIVE] (effectively uncapped/CDN
cached) - keep a gentle client-side floor anyway. Search/fetch/exchange are the throttled ones.

---

## 2. Search query JSON schema + real working examples

Envelope: `{"query": {...}, "sort": {"price":"asc"}}`. `query` fields used:
`status`, `name`, `type`, `term`, `stats` (array of stat-groups), `filters` (map of
filter-groups). All examples below returned **HTTP 200** this session.

### 2a. Unique by name+type, price-sorted [LIVE - trade_search_unique.json]
```
POST /api/trade/search/Allflame
{"query":{"status":{"option":"online"},"name":"Goldrim","type":"Leather Cap",
          "stats":[{"type":"and","filters":[]}]},
 "sort":{"price":"asc"}}
-> {"id":"7np9qdGnC5","complexity":6,"result":[<100 hashes>],"total":575}
```
`result` is up to **100** listing hashes (even though total=575); the parent's rank-spread
sampling over these is fine. `id` (`7np9qdGnC5`) feeds fetch `?query=` and the browser URL.

### 2b. Rare: base type + stat filters + LINK filter [LIVE - trade_search_rare_links.json]
```
{"query":{"status":{"option":"online"},"type":"Astral Plate",
   "stats":[{"type":"and","filters":[
       {"id":"explicit.stat_3299347043","value":{"min":70}},          // +# to maximum Life
       {"id":"pseudo.pseudo_total_elemental_resistance","value":{"min":60}}]}],
   "filters":{"socket_filters":{"filters":{"links":{"min":6}}}}},      // 6-link
 "sort":{"price":"asc"}}
-> {"id":"5nvVebPJSa",...,"total":2}
```
Links filter WORKS: total collapsed to 2, and the fetched item's `sockets` are all
`"group":0` (one 6-linked group). `socket_filters` is a **new PoE1 group with no trade2
equivalent** (trade2/PoE2 has no linked sockets).

### 2c. Price-sorted + armour defence total [LIVE - trade_search_pricesort.json]
```
{"query":{"status":{"option":"online"},"type":"Astral Plate",
   "stats":[{"type":"and","filters":[]}],
   "filters":{"armour_filters":{"filters":{"ar":{"min":100}}}}},
 "sort":{"price":"asc"}}
-> {"id":"KlOzGLLqs5",...,"total":1129}
```
**Defence totals live under `armour_filters` in PoE1, NOT `equipment_filters`** (which does
not exist here). `sort` also accepts other keys server-side (`{"stat_id":"asc"}` etc.); the
port only needs `{"price":"asc"}`.

### Stat-group object types
Live-tested: `{"type":"and","filters":[{"id":..,"value":{"min":..,"max":..}}]}`. PoE1 also
documents `and / not / if / count / weight / weight2` group types **[NOT RE-TESTED this
session]** - only `and` was exercised. Whether PoE1's *search* API rejects `weight`/`weight2`
the way trade2 does is **unverified** (the parent already coerces weight->count as a safety
net, so the port inherits safe behaviour). Per-filter `value` accepts `min`, `max`, `option`.

---

## 3. Fetch + listing/item JSON shape [LIVE - trade_fetch.json / trade_fetch_rare.json]

`GET /api/trade/fetch/{h1,..,h10}?query={qid}` -> `{"result":[ {id, listing, item}, ... ]}`.
Passing **11 ids -> HTTP 400** `{"error":{"code":2,"message":"Invalid query"}}` [LIVE], so the
parent's `ids[:10]` batching is correct for PoE1 too. `&realm=poe2` from the parent is dropped
(PC default; `&realm=xbox|sony` only if needed).

```
listing = {method:"psapi", indexed:"2026-07-26T20:34:32Z", stash:{...},
           price:{type:"~price", amount:1, currency:"chaos"},          // SAME shape as trade2
           account:{name:"...#5805", online:{league:"Allflame"}, lastCharacterName:"..."},
           whisper:"..."}
```
`listing.price.{amount,currency}` is read exactly as the parent does; PoE1 currency ids are
`chaos/divine/exalted/...` (section 6). Unpriced listings have `price:null` - keep the parent's
"no number, just a link" handling.

### item mods are OBJECTS, not strings  <-- BIGGEST PORT BREAK [LIVE]
`item.explicitMods` (and `implicitMods`, when present) is a **list of objects**, not the list
of strings the parent assumes:
```json
{"description":"+172 to maximum Life", "domain":"explicit",
 "hash":"stat.explicit.stat_3299347043",
 "mods":[{"name":"...","tier":"P3","level":42,"magnitudes":[{"min":"27","max":"32"}]}]}
```
- Display text = `mod.description` (this is the string to feed `util.mod_to_pattern`).
- Trade stat id = `mod.hash` with the leading `stat.` stripped -> `explicit.stat_3299347043`
  (a valid `query.stats` filter id). Verified against `extended.hashes.explicit`.
- `item.extended.hashes.explicit` = `[["explicit.stat_3299347043",[0]], ...]` - canonical
  stat-id list per item (indices point at the mod's roll lines). Prefer this over text-matching.

**Required port change:** `pricing.py::_search_listings` does
`{util.mod_to_pattern(m) for m in item.explicitMods}` treating `m` as a str - it must use
`m["description"]` (guard str-vs-dict). Same for `_variant_affixes`' listing-pattern build.
`statmap.py` text-matching is unaffected: it maps the user's **PoB** mod strings, not trade mods.

### item defence totals + other keys [LIVE]
`item` keys seen: `name, baseType, typeLine, frameType(int), frameTypeId, ilvl, identified,
corrupted, rarity, properties, requirements, implicitMods, explicitMods, sockets, extended,
league, note, icon, id, verified, w, h`. `frameType`: 0 normal,1 magic,2 rare,3 unique,4 gem,
5 currency,6 divcard (standard). `item.extended` carries API-computed defence totals:
`{ar:1166, ev, es, ar_aug:true, base_defence_percentile:35, hashes:{...}, text:...}` - a ready
source for `armour_filters` values if ever needed (the port normally takes defence from PoB).

### sockets/links array [LIVE - the new PoE1 feature]
`item.sockets` = `[{"group":0,"attr":"G","sColour":"W"}, ... x6]`. `group` = link-group index
(all equal => all linked; a 6-link = six sockets sharing one `group`). `sColour` R/G/B/W/A,
`attr` S/D/I/G(=generic/white)/A. Count of distinct max-size `group` gives the link count.

---

## 4. Bulk exchange [LIVE - trade_exchange.json]
```
POST /api/trade/exchange/Allflame
{"query":{"status":{"option":"online"},"have":["chaos"],"want":["divine"]},
 "sort":{"have":"asc"},"engine":"new"}
-> {"id":"le7kjsV","complexity":..,"total":13,
    "result":{ "<hash>": {id, item, listing}, ... }}          // result is a DICT keyed by hash
```
`engine:"new"` is accepted and returns the offers format the parent's `currency.py` expects:
```
result[hash].listing.offers = [
  {"exchange":{"currency":"chaos","amount":1,"whisper":"{0} Chaos Orb"},
   "item":    {"currency":"divine","amount":1,"stock":4,"id":"...","whisper":"{0} Divine Orb"}}]
```
`offer.exchange` = what the buyer pays (= `have`), `offer.item` = what they get (= `want`).
`currency.py::_lookup` already reads exactly this (`ex.currency==_BASE and it.currency==want`).
**Only change for the port: `_BASE` must become `"chaos"`** (PoE1 base currency), not
`"exalted"`. Endpoint + body + response shape are otherwise identical to trade2.

---

## 5. Listing statuses [SCHEMA - trade_data_filters.json status_filters]
`status.option` values (all valid in PoE1):

| option | label |
|---|---|
| `available` | Instant Buyout and In Person |
| `securable` | Instant Buyout |
| `onlineleague` | In Person (Online in League) |
| `online` | In Person (Online) |
| `any` | Any |

**Correction to the task's premise:** `securable` and `available` **DO exist** in PoE1 - the
parent's `Pricer.STATUS_OPTIONS = ("online","any","onlineleague","available","securable")` is
fully valid on PoE1, no pruning needed. Default `online` as before.

---

## 6. Reference-data ids the port depends on

### Pseudo stat ids [LIVE - trade_stats.json] - identical namespace to trade2
| id | text |
|---|---|
| `pseudo.pseudo_total_elemental_resistance` | +#% total Elemental Resistance |
| `pseudo.pseudo_total_chaos_resistance` | +#% total to Chaos Resistance |
| `pseudo.pseudo_total_life` | +# total maximum Life |
| `pseudo.pseudo_total_energy_shield` | +# total maximum Energy Shield |
| `pseudo.pseudo_total_resistance` | +#% total Resistance |
| `pseudo.pseudo_total_all_elemental_resistances` | +#% total to all Elemental Resistances |
| `pseudo.pseudo_total_fire/cold/lightning_resistance` | per-element totals |

The parent's `_PSEUDO_ELEM_RES` / `_PSEUDO_CHAOS_RES` constants are **unchanged** (same ids).
There is **no** `pseudo_total_armour` / `pseudo_total_evasion` (only ES has a pseudo total) -
use `armour_filters.ar` / `.ev` for those.

### Defence / equipment filter fields [SCHEMA]
- **`armour_filters`** filters: `ar` (Armour), `ev` (Evasion), `es` (Energy Shield),
  `ward` (Ward), `block` (Block), `base_defence_percentile`. (trade2 packed these into
  `equipment_filters`; **rename group to `armour_filters`**, keep the ar/ev/es/ward field
  names - they match. `_DEF_LABEL` keys es/ev/ar/ward are still right as the field names.)
- **`weapon_filters`** filters: `damage, aps, crit, dps, pdps, edps` (separate group in PoE1).
- **`socket_filters`** filters: `sockets`, `links` (numeric ranges; `{"min":N,"max":M}`).
  Colour/attr sub-counts on links/sockets exist on the site **[INFERRED - not tested]**; a
  plain `{"min":6}` on `links` is confirmed [LIVE].

### type_filters.category options (83 total) [SCHEMA]
All parent `_INVENTORY_CATEGORY` targets exist: `armour.chest/helmet/gloves/boots/shield`,
`accessory.amulet/belt/ring`, `weapon`, **`jewel`** (+`jewel.base/.abyss/.cluster`),
**`flask`**. Gems: `gem.activegem`, `gem.supportgem`, plus PoE1-only `gem.supportgemplus`
(Awakened). Also `accessory.trinket`, `armour.quiver`, `map*`, `card`, `currency*`, etc.
Item rarity options: `normal, magic, rare, unique, uniquefoil, nonunique`.

### misc_filters (gem search) [SCHEMA]
`gem_level`, `gem_level_progress`, `gem_transfigured`, `gem_vaal`, `quality`, `ilvl`,
`corrupted`, `identified`, `mirrored`, `fractured_item`, `synthesised_item`, ... **There is NO
`gem_sockets`** (PoE1 gems have no sockets). The parent's `_gem_search_url` must drop
`gem_sockets`; use `gem_level` (and optionally `gem_level_progress`) only.

### Currency ids [LIVE - trade_static.json] (`result[].entries[] = {id,text,image}`)
`chaos`=Chaos Orb, `divine`=Divine Orb, `exalted`=Exalted Orb, `mirror`=Mirror of Kalandra,
plus 100+ more (`alt, fusing, alch, regal, vaal, gcp, ...`). Static also has `image` per entry
(`currency_image()` port: same shape). Trade-price currency ids (for `trade_filters.price`):
includes `chaos_divine` composite.

### Stat groups present [LIVE - trade_stats.json labels]
`Pseudo, Explicit, Implicit, Imbued, Fractured, Enchant, Scourge, Crafted, Mercenary, Veiled,
Delve, Ultimatum, Sanctum, Crucible`. **No `rune`, no `desecrated`** (those are PoE2).
`statmap.py::_build` sets should become: `wanted = {explicit, implicit, pseudo, fractured}`,
`grouped = wanted | {enchant, crafted, ...}`. Id prefix scheme `sid.split(".",1)[0]` still
holds; note some ids are `imbued.pseudo_built_in_support|3582467606` (a `|`), `veiled.mod_###`,
`crucible.mod_###`, `delve.delve_###` - the prefix split is still robust.

---

## 7. Rate limits - VERBATIM headers observed this session [LIVE - trade_headers.json]
Header format: `X-Rate-Limit-<Rules>: hits:window_secs:penalty_secs, ...` and
`X-Rate-Limit-<Rules>-State: current_hits:window:active_penalty, ...`. `X-Rate-Limit-Rules: Ip`
=> the active bucket is `X-Rate-Limit-Ip` (unauthenticated; would add `Account` if logged in).

| Endpoint | `X-Rate-Limit-Policy` | `X-Rate-Limit-Ip` (VERBATIM) |
|---|---|---|
| search | `trade-search-request-limit` | `5:10:60,15:60:300,30:300:1800,600:21600:3600` |
| fetch | `trade-fetch-request-limit` | `12:4:10,16:12:300,50:300:300,1000:21600:1800` |
| exchange | `trade-exchange-request-limit` | `5:15:60,10:90:300,30:300:1800` |
| data/* | (none sent) | (no rate headers observed) |

Example state header (search, after 1st call): `X-Rate-Limit-Ip-State: 1:10:0,1:60:0,1:300:0,1:21600:0`.

**Diff vs the parent's `_DEFAULT_RULES` (caps as `hits:window`):**
- search: parent `5:10, 15:60, 30:300` -> PoE1 **adds a 4th window `600:21600`** (600 / 6 h).
- fetch: parent `12:4, 16:12` -> PoE1 **adds `50:300` and `1000:21600`**.
- exchange: parent `5:15, 10:90, 30:300` -> **identical caps** in PoE1.

The parent's `RateLimiter.update_rules` reads `X-Rate-Limit-Ip` and parses `bits[0]:bits[1]`
(hits:window), ignoring the 3rd `penalty` field - this works unchanged on PoE1's 3-part format.
Recommendation: seed `_DEFAULT_RULES` with the 4 search / 4 fetch / 3 exchange windows above so
the client is conservative before the first header arrives. 429 handling (`Retry-After`) is
unchanged; none was triggered this session.

---

## 8. Browser trade-site URL (for `trade_url` links)
PoE1 mirrors the API path minus `/api` and with **no realm segment** (contrast trade2's
`/trade2/search/poe2/{league}/{id}`):
- By server query id: `https://www.pathofexile.com/trade/search/{league}/{query_id}`
- Prefilled (never-expiring) query: `https://www.pathofexile.com/trade/search/{league}?q={urlencoded_json}`
  where the JSON is the same `{"query":..,"sort":..}` envelope, `json.dumps(...,separators=(",",":"))`
  then `urllib.parse.quote(...,safe="")`.

[Grounding: the API path `/api/trade/search/{league}` is [LIVE]-verified and query ids come
from it; the browser path is the standard `/api`-less mirror. A scripted GET of the HTML page
returns 403 (Cloudflare bot-block for non-browser UAs) - so the render was not scraped, but the
URL structure is the long-standing PoE1 convention and parallels the parent's PoE2 builder.]

Port edits: everywhere the parent writes `/trade2/search/poe2/` use `/trade/search/`; drop the
`REALM`/`poe2` path segment; keep the `{league}/{id}` and `?q=` forms.

---

## 9. Port checklist (trade.py / statmap.py / pricing.py)
1. `trade.py`: `BASE="https://www.pathofexile.com/api/trade"`; remove `REALM="poe2"` and the
   `poe2` path segment from search/exchange; drop `&realm=poe2` from fetch. [LIVE]
2. `trade.py`: `_DEFAULT_RULES` -> the section-7 windows (add search 600:21600; fetch 50:300 +
   1000:21600). Keep 10-id fetch cap. [LIVE]
3. `currency.py`: `_BASE="chaos"`; exchange `have=["chaos"]`; display in chaos + divine. [LIVE/REF]
4. `pricing.py`: `equipment_filters` -> **`armour_filters`** (ar/ev/es/ward field names kept);
   defence-total pricing unchanged otherwise. [SCHEMA]
5. `pricing.py`: add `socket_filters` support (`links`/`sockets` min/max) for 6-link uniques
   (e.g. Tabula, 6L bases) - a new capability with no trade2 analogue. [LIVE]
6. `pricing.py::_search_listings` + `_variant_affixes`: read `mod["description"]` from the
   object-form `explicitMods` (or use `item.extended.hashes.explicit` ids). **Do not** iterate
   mods as strings. [LIVE - biggest break]
7. `pricing.py` gem URL: drop `misc_filters.gem_sockets`; keep `gem_level`. `gem.activegem` /
   `gem.supportgem` categories unchanged. [SCHEMA]
8. `statmap.py::_build`: `wanted`/`grouped` sets -> PoE1 groups (drop `rune`/`desecrated`; keep
   explicit/implicit/pseudo/fractured/enchant/crafted). Pseudo elem/chaos-res ids unchanged. [LIVE]
9. `Pricer.STATUS_OPTIONS`: unchanged - all 5 exist in PoE1. [SCHEMA]
10. Trade-site URLs: `/trade/search/{league}[/{id} | ?q=...]`, no realm. [LIVE-adjacent]
11. `jewel` + `flask` categories exist -> `_INVENTORY_CATEGORY` jewel/flask entries are valid. [SCHEMA]

## 10. Open risks / not verified this session
- `count/if/not/weight/weight2` stat-group types not exercised on PoE1 (only `and`). Whether
  PoE1 search rejects `weight`/`weight2` like trade2 is unknown; parent's weight->count coercion
  is a safe default. [NOT RE-TESTED]
- `socket_filters` colour/attribute sub-counts (r/g/b/w on links/sockets) inferred from the
  site, not tested; only `links.min` confirmed. [INFERRED]
- Browser HTML not scraped (403 Cloudflare); URL format is convention-grounded, not render-verified.
- `/data/*` throttling: none advertised, but do not hammer it; keep a client floor.
- data/items groups are broad (`Armour`, not `Body Armours`); `load_item_types` `by_group`
  labels change, but the `all` union it relies on is unaffected.
