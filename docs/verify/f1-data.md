# f1 engine-side data verification (D-0006, feedback round 1)

**Date:** 2026-07-26
**Scope:** validate the **engine side** of decision-log entry **D-0006** OFFLINE
(flasks, gem host-grouping + per-gem breakdown, GRANTED audit). Judged against D-0006
verbatim + `docs/feedback1-spec.md` §A-D.
**Environment:** Windows 11, Python 3.13.7, `requests` installed.
**Verdict:** **PASS (engine side).** `tests.py` is green and provably offline; every
D-0006 engine invariant holds against the real fixture driven with the real on-disk
poe.ninja economy. **One out-of-engine gap** (the spec-required `web.py` §B.1 one-liner)
is still unapplied in the code as read - flagged below; it belongs to the concurrent
web/UI agent, not the engine.

All numbers/quotes below are SOURCE-DERIVED (engine code, the live fixture
`research/data/char_poe1.json`, and the on-disk poe.ninja SkillGem economy cached at
`cache/` key `poeninja:econ1i:Allflame:SkillGem`, 5784 lines). No web-claimed or inferred
figures. The engine's one `[INFERRED]` rule (empty-itemData => granted) is called out where
it applies.

Fixture identity: account `example-0416`, character `TestCharacter`, Elementalist L100,
league `Allflame`.

---

## 1. `python tests.py` - GREEN + provably OFFLINE

```
cd C:\scripts\buildpricechecker-poe1
python tests.py
-> All self-tests passed.        (exit 0)
```

The fixture-gated `normalize` + D-0006 blocks RAN (fixture present; no
"(skipped char_poe1.json...)" line). The suite includes the D-0006 coverage added in the
engine port: host-index, `itemProvidedGems` index, `_gem_is_granted` signals + the socketed
"not granted" case, the fixture granted set, `price_skill` total==sum(supports included,
granted excluded), fully-granted => total None, and flask belt order (normalize + price_build).

**Offline proof (load-bearing).** Re-ran the suite with the network hard-blocked at the
Python level - `socket.getaddrinfo`, `socket.create_connection`, and a `socket.socket`
subclass whose `connect`/`connect_ex` raise - leaving the `socket` class intact so
`import ssl`/`requests` still load:

```
>>> OFFLINE-PROOF: suite completed with DNS/connect blocked -> GREEN + OFFLINE
All self-tests passed.
```

Green with DNS + connect blocked => nothing in the suite touches the network.

---

## 2. Flask belt - all flasks, belt order preserved (D-0006 clause 1)

`normalize()` on the fixture emits **exactly the 5 flasks, all in `group == "flask"`,
in `flasks[]` (belt) order**, matching the raw array 1:1:

| belt # | engine `name` | base | category |
|---|---|---|---|
| 0 | Wine of the Prophet | Gold Flask | unique |
| 1 | The Overflowing Chalice | Sulphur Flask | unique |
| 2 | Cinderswallow Urn | Silver Flask | unique |
| 3 | Atziri's Promise | Amethyst Flask | unique |
| 4 | (Quicksilver Flask) | Quicksilver Flask | magic |

- Engine order == raw `flasks[]` order (verified element-by-element). PASS.
- All 5 carry `group == "flask"`; none dropped. PASS.
- No life/mana classification - a flask is just belt position N (matches D-0006:
  "5 generic slots ... filled in flask order ... No life/mana slot guessing").

`price_build` additionally returns the flask group in belt order even though pricing runs in
category-priority order (the `order = {id(it): i ...}` re-sort in `pricing.py::price_build`);
the suite's `price_build: flask belt order preserved` covers a mixed unique/magic belt.

---

## 3. Every skill row carries host-item info + per-gem breakdown (D-0006 clause 2)

Drove `Pricer.price_skill` on each of the 6 gem groups with the REAL on-disk economy
(TTL bypassed via `cache.get -> cache.peek`, network hard-blocked => zero live calls), then
serialized with the exact web function `bpc.web._result_dict(r)` (which does `d.update(r.extra)`).
Every emitted `priced[k]` carries `host_slot / host_name / host_base / host_unique /
host_inventory_id`, plus `granted`, `total_chaos`, `kind`, and a `gems[]` breakdown. PASS.

Host grouping for the fixture (matches `docs/feedback1-spec.md` §D / the tests):

| gem group (active) | host_slot | host_name | host_unique | host_inventory_id |
|---|---|---|---|---|
| Ethereal Knives of the Massacre | Body Armour | Blunderbore | true | BodyArmour |
| Herald of Ice (+ Herald of Agony) | Weapon | The Golden Charlatan | true | Weapon |
| Herald of Ash | Weapon | The Golden Charlatan | true | Weapon |
| Herald of Purity | Weapon | The Golden Charlatan | true | Weapon |
| Leap Slam | Boots | Replica Voidwalker | true | Boots |
| Herald of the Hive | Ring | Lost Unity | true | Ring2 |

The weapon (`inventory_id "Weapon"`) hosts 3 Herald groups - the multi-group-per-host case
the spec calls out. `gems[0]` is always the active; `gems[1:]` are its linked gems in order.

**Emitted `priced[k]` - main skill (active + 5 supports), trade_urls trimmed:**

```json
{
  "chaos": {"min": 2070.3, "median": 2070.3, "high": 2070.3},
  "confidence": "medium", "method": "skill",
  "note": "poe.ninja gem prices: active + 5 supports",
  "kind": "skill", "level": 20, "quality": 20, "corrupted": false, "source": "poe.ninja",
  "total_chaos": 2070.3,
  "gems": [
    {"name": "Ethereal Knives of the Massacre", "support": false, "granted": false, "level": 20, "quality": 20, "corrupted": false, "chaos": 109.9,  "variant": "20/20"},
    {"name": "Greater Spell Echo Support",      "support": true,  "granted": false, "level": 2,  "quality": 20, "corrupted": false, "chaos": 1455,   "variant": "3/20"},
    {"name": "Greater Chain Support",           "support": true,  "granted": false, "level": 3,  "quality": 20, "corrupted": false, "chaos": 408.0,  "variant": "3/20"},
    {"name": "Hypothermia Support",             "support": true,  "granted": false, "level": 20, "quality": 20, "corrupted": false, "chaos": 30.3,   "variant": "20/20"},
    {"name": "Increased Critical Damage Support","support": true, "granted": false, "level": 20, "quality": 20, "corrupted": false, "chaos": 46.5,   "variant": "20/20"},
    {"name": "Faster Projectiles Support",      "support": true,  "granted": false, "level": 21, "quality": 20, "corrupted": true,  "chaos": 20.6,   "variant": "21/20c"}
  ],
  "granted": false,
  "host_slot": "Body Armour", "host_name": "Blunderbore", "host_base": "Astral Plate",
  "host_unique": true, "host_inventory_id": "BodyArmour"
}
```

**Index alignment (spec §D.2):** `it.supports[i]` mirrors `gems[i+1]` by position (same
length, same order) - verified True for every group. This is why a **linked second active**
prices correctly: Herald of Ice's group carries `gems[1] = Herald of Agony` with
`support: false` (a second active, not a support) yet still priced 111c and summed
(total 156 = 45 + 111). The breakdown never relies on "index > 0 == support".

---

## 4. Support prices sum into the group total (D-0006 clause 2)

Invariant (spec §A.3, tested): `total_chaos == sum(g.chaos for g in gems if g.chaos != null)`
and `total_chaos == chaos.median`. Verified True for ALL 6 groups.

Concrete support-inclusion proof, main skill:

```
active-only (Ethereal Knives) = 109.9 c
group total_chaos            = 2070.3 c
delta contributed by the 5 supports = 1960.4 c   (1455 + 408 + 30.3 + 46.5 + 20.6)
```

Across all groups, 7 support rows priced non-null and every one is folded into its group
total - support costs are INCLUDED, exactly as D-0006 requires ("support costs stay included
in totals"). The most expensive component here is a support (Greater Spell Echo, 1455c),
which is precisely why the port prices every support (D-0003/D-0006).

---

## 5. GRANTED audit - only genuinely item-provided gems flagged (D-0006 clause 3)

**The authority** (raw `itemProvidedGems` in the fixture) has exactly ONE entry:

```json
[ { "slot": 9, "gems": [ { "name": "Herald of the Hive", "level": 30, "quality": 0, "isBuiltInSupport": false } ] } ]
```

Engine result - which gems are flagged `granted` and WHY:

| gem | it.granted | why |
|---|---|---|
| Ethereal Knives of the Massacre | **false** | real socketed gem (has itemData baseType) |
| Herald of Ice | **false** | real socketed gem |
| Herald of Ash | **false** | real socketed gem |
| Herald of Purity | **false** | real socketed gem |
| Leap Slam | **false** | real socketed gem |
| Herald of the Hive | **true** | `itemProvidedGems` slot+name match (slot 9) **and** empty itemData `[INFERRED-safe]` |

- Granted set == exactly `["Herald of the Hive"]`. PASS. This is the item-provided Herald
  granted by the **Lost Unity** ring (Ring2, slot 9) - the ONLY gem D-0006 says should be
  tagged. Every socketed Herald + Leap Slam + the main skill are clean.
- The two granted signals agree here: the authoritative `itemProvidedGems` slot+name match,
  and the belt-and-suspenders empty-itemData rule (`[INFERRED]`, but strictly safe - every
  real socketed gem in this build carries a `baseType`, so nothing is mis-flagged;
  `bpc/poeninja.py::_gem_is_granted`). `isBuiltInSupport` is false for this entry, so it is
  the slot+name match doing the work.

**Granted excluded from total, supports still count (D-0006 clause 3, second half).** The
granted active's emitted payload (`priced[k]`) - all prices null, total null, correct notes;
field-for-field identical to `feedback1-spec.md` §A.2:

```json
{
  "chaos": {"min": null, "median": null, "high": null},
  "confidence": "none", "method": "skill",
  "note": "item-granted skill (comes free with the host item)",
  "kind": "skill", "level": 30, "quality": 0, "corrupted": false, "source": "poe.ninja",
  "granted": true,
  "host_slot": "Ring", "host_name": "Lost Unity", "host_base": "Formless Ring",
  "host_unique": true, "host_inventory_id": "Ring2",
  "total_chaos": null,
  "gems": [ {"name": "Herald of the Hive", "support": false, "granted": true, "level": 30,
             "quality": 0, "corrupted": false, "chaos": null, "variant": "",
             "note": "granted by Lost Unity - not counted"} ]
}
```

- Granted gems always carry `chaos: null` and never contribute to `total_chaos`
  (verified across all groups). No misleading number is printed for a free-with-item gem.
- The "granted ACTIVE with a real socketed support -> active excluded, support still counts"
  case is covered by the suite (test (b): total == the support's price alone, active price
  null). This fixture has no such setup (the one granted gem has no supports), so it is a
  structural + unit-test guarantee rather than a fixture observation.

---

## 6. D-0006 verbatim - clause-by-clause (engine side)

1. **Flask belt = 5 generic slots, overflow shown, no life/mana guessing.** Engine: PASS
   (Section 2). The 5-slot/overflow *rendering* is the skin's job; the engine emits every
   flask in belt order in one `flask` group, which is the data contract the skins consume.
2. **Gems grouped by HOST ITEM; supports nested under their active; support costs in totals;
   host-item info + per-gem breakdown additive in `PriceResult.extra`.** Engine: PASS
   (Sections 3-4). All host_* + `gems[]` present and additive; index alignment holds;
   supports summed.
3. **GRANTED audit - only genuinely item-provided gems tagged; granted excluded from totals
   while socketed supports still count.** Engine: PASS (Section 5). Only Herald of the Hive.
   **End-to-end caveat: see Section 7** - the engine computes it correctly, but the web
   skeleton row does not yet read the engine value, so the *rendered badge* is still wrong.
4. **Autoscan button.** UI-only (a button + glow in the affix picker wired to the existing
   `bpc.searchAllRares` / `price_rare` default all-affix path). Nothing engine-side changed;
   out of scope for this engine verification. The default all-affix rare query it triggers is
   unchanged and covered by the existing rare-default tests.

---

## 7. OUT-OF-ENGINE finding: `web.py` §B.1 skeleton `granted` not yet applied

**This is NOT an engine defect and does not change the engine PASS.** The engine emits the
correct `granted` on both the normalized `Item` (`it.granted`) and the priced payload
(`priced[k].granted`, via `r.extra`). Recording it because it is the literal crux of D-0006's
GRANTED clause **end-to-end**, it is a spec-REQUIRED change (`feedback1-spec.md` §B.1), and it
is a one-liner that - as of the code read here - has **not** landed. `bpc/web.py` is owned by
the concurrent web/UI agent(s), not by this engine verification; the coordinator should ensure
it lands (or confirm it already has in that agent's worktree).

`bpc/web.py` `_run_job` still builds the gem **skeleton** row with the old PoE2-era heuristic
(line ~315):

```python
_inv = str((it.raw or {}).get("inventoryId") or "")
row["granted"] = not _inv.startswith("SkillSlot")   # spec §B.1 says: row["granted"] = bool(it.granted)
```

For PoE1 every gem's `it.raw.inventoryId` is `None`, so this evaluates **True for every gem**.
Simulated against the real fixture:

```
gem                               raw.inventoryId   web.py skeleton   engine it.granted
Ethereal Knives of the Massacre   None              True              False
Herald of Ice                     None              True              False
Herald of Ash                     None              True              False
Herald of Purity                  None              True              False
Leap Slam                         None              True              False
Herald of the Hive                None              True              True
```

`core.js` reads the **skeleton** `it.granted` for both the GRANTED badge
(`renderGems`, ~L1002/L996) and the default-enable (`itemGranted`, ~L125 -> used at ~L344 and
~L185). Consequences if §B.1 is not applied: (a) the owner's original "everything says
GRANTED" bug persists - the badge fires on all 6 gems; and (b) worse, every priced gem
defaults **excluded** from the build total (`enabled[k] = !itemGranted(k)` with
`itemGranted` always true), so the whole gem spend (here ~2070c on the main skill alone)
drops out of the default total. The one-line fix (`row["granted"] = bool(it.granted)`) makes
the correct engine value flow into the existing, already-correct core.js logic.

(Separately, the OPTIONAL additive host_* skeleton fields in §D.1 are also not present on the
skeleton row; not required - skins can group off `priced[k].host_inventory_id` on price.)

---

## 8. How to reproduce (offline, no trade calls)

```
cd C:\scripts\buildpricechecker-poe1
python tests.py                       # green

# drive normalize + price_skill on the fixture with the on-disk economy, network-blocked:
#  - normalize(research/data/char_poe1.json) -> items
#  - PoeNinjaEconomy("Allflame") with cache.get monkeypatched to cache.peek (TTL bypass)
#  - Pricer.price_skill(each gem); serialize via bpc.web._result_dict
#  - assert total_chaos == sum(non-null gem chaos); granted only on Herald of the Hive;
#    flask group == raw flasks[] order
```

All inputs are on disk: the fixture (`research/data/char_poe1.json`) and the poe.ninja
SkillGem economy (`cache/` key `poeninja:econ1i:Allflame:SkillGem`). No pathofexile.com trade
search/fetch/exchange endpoints were called.
