# f1 engine-side data verification — ROUND 1 re-run (D-0006, feedback round 1)

**Date:** 2026-07-26
**Scope:** re-run the OFFLINE data validation of decision-log entry **D-0006** (flasks,
gem host-grouping + per-gem breakdown, GRANTED audit), judged against D-0006 verbatim +
`docs/feedback1-spec.md` §A–D. Primary focus of this round: **did the previous round's
findings actually get resolved** (see `docs/verify/f1-data.md`, `docs/verify/v1-tests.md`).
**Environment:** Windows 11, Python 3.13, `requests` installed.
**Verdict:** **PASS.** `tests.py` green + provably offline; every D-0006 engine invariant
holds against the real fixture driven with the on-disk poe.ninja economy; and the **one
open finding from the previous round (the `web.py` §B.1 skeleton `granted` one-liner) is
now RESOLVED in code.** No trade endpoints were called.

All figures below are SOURCE-DERIVED (engine code under `bpc/`, the live fixture
`research/data/char_poe1.json`, and the on-disk poe.ninja SkillGem economy cached at
`cache/…` key `poeninja:econ1i:Allflame:SkillGem`). No web-claimed / inferred numbers.
Fixture identity: account `example-0416`, character `TestCharacter`, Elementalist L100,
league `Allflame`.

---

## 0. Previous-round findings — resolution status (the point of this re-run)

| # | Prior finding (source) | Status now | Evidence |
|---|---|---|---|
| **F1** | `web.py` §B.1 skeleton `granted` not applied — the gem skeleton row still used the PoE2-era `not inventoryId.startswith("SkillSlot")` heuristic, so every gem defaulted to GRANTED and dropped out of the total (`f1-data.md` §7 — the round's only finding). | **RESOLVED** | `bpc/web.py:316` is now `row["granted"] = bool(it.granted)`; the old heuristic is deleted (RULE 6 clean cutover — no dead fallback). Remaining `SkillSlot` strings in the tree are **comments only** (`web.py:313`, `poeninja.py:499`) documenting the fixed bug, not live code. |
| **F1b** | Optional additive `host_*` skeleton fields (§D.1) absent from the gem skeleton row. | **RESOLVED (bonus)** | `bpc/web.py:320–324` now copies `host_slot / host_name / host_base / host_unique / host_inventory_id` onto the skeleton row, so skins can group gems before the price lands. |
| v1 §Gaps 1–6 | Six MINOR test-coverage gaps (status mapping, rare all-affix default, armour_filters totals, no-match guardrail, `to_chaos` multiply, version-unique detection). | **Out of this round's scope** — these were D-0005 port-coverage backlog items, not D-0006. Not re-audited here; they remain missing-tests (not failures) and do not affect this PASS. |

The previous round's single actionable engine-facing finding is closed. The GRANTED bug is
now correct **end to end**: engine computes it, `web.py` reads it, `core.js` badges + defaults
off it.

---

## 1. `python tests.py` — GREEN + provably OFFLINE

```
cd C:\scripts\buildpricechecker-poe1
python tests.py
-> All self-tests passed.        (exit 0)
```

The fixture-gated `normalize` + D-0006 blocks RAN (fixture present; no "(skipped
char_poe1.json…)" line). The D-0006 coverage is present and green — including the
`itemProvidedGems` index, `_gem_is_granted` signals + the socketed "NOT granted" case
(the owner's mis-flag bug, `tests.py:592`), the fixture granted set == `["Herald of the
Hive"]` (`tests.py:604`), `price_skill` total==sum(supports included, granted excluded)
(`tests.py:657–681`), fully-granted ⇒ total None (`tests.py:689`), and flask belt order
(`tests.py:624`).

**Offline proof (load-bearing).** Re-ran the suite via `runpy` with the network hard-blocked
at the socket layer — `socket.getaddrinfo`, `socket.create_connection`, and
`socket.socket.connect`/`connect_ex` all raise, socket class left intact so `ssl`/`requests`
still import:

```
All self-tests passed.
```

Green with DNS + every connect path blocked ⇒ nothing in the suite touches the network.

---

## 2. Flask belt — all flasks, belt order preserved (D-0006 clause 1)

Drove `normalize()` on the fixture (network-blocked). Result: **exactly 5 flasks, all in
`group == "flask"`, in raw `flasks[]` (belt) order**, matching the raw `itemData` array 1:1:

| belt # | engine display_name | raw `flasks[i].itemData` (name, typeLine) |
|---|---|---|
| 0 | Wine of the Prophet, Gold Flask | Wine of the Prophet, Gold Flask |
| 1 | The Overflowing Chalice, Sulphur Flask | The Overflowing Chalice, Sulphur Flask |
| 2 | Cinderswallow Urn, Silver Flask | Cinderswallow Urn, Silver Flask |
| 3 | Atziri's Promise, Amethyst Flask | Atziri's Promise, Amethyst Flask |
| 4 | Alchemist's Quicksilver Flask of the Cheetah | (magic Quicksilver) |

- engine order == raw `flasks[]` order (element-by-element). PASS.
- all 5 carry `group == "flask"`; none dropped. PASS.
- no life/mana classification — a flask is just belt position N (matches D-0006 "5 generic
  slots … in flask order … No life/mana slot guessing"). The 5-slot/overflow *rendering* is
  the skin's job; the engine emits every flask in belt order in one `flask` group, which is
  the data contract the skins consume. `price_build` re-sorts back to belt order after
  category-priority pricing (`tests.py:624` covers a mixed unique/magic belt).

---

## 3. Every skill row carries host info + per-gem breakdown (D-0006 clause 2)

Drove `Pricer.price_skill` on all 6 gem groups with the REAL on-disk economy (TTL bypassed by
monkeypatching `cache.get → cache.peek`; network hard-blocked ⇒ zero live calls), then
serialized with the exact web function `bpc.web._result_dict` (which does `d.update(r.extra)`).
Every emitted `priced[k]` carries `host_slot / host_name / host_base / host_unique /
host_inventory_id`, plus `granted`, `total_chaos`, and a `gems[]` breakdown. **All host fields
present on all 6 groups. PASS.**

| gem group (active) | host_slot | host_name | host_unique | host_inventory_id | total_chaos |
|---|---|---|---|---|---|
| Ethereal Knives of the Massacre | Body Armour | Blunderbore | true | BodyArmour | 2070.3 |
| Herald of Ice (+ Herald of Agony) | Weapon | The Golden Charlatan | true | Weapon | 156.0 |
| Herald of Ash (+ Herald of Thunder) | Weapon | The Golden Charlatan | true | Weapon | 107.4 |
| Herald of Purity (+ Empower) | Weapon | The Golden Charlatan | true | Weapon | 297.2 |
| Leap Slam (+ Arctic Armour, Righteous Fire, Arrogance) | Boots | Replica Voidwalker | true | Boots | 90.6 |
| Herald of the Hive | Ring | Lost Unity | true | Ring2 | null (granted) |

The weapon (`host_inventory_id "Weapon"`) hosts **3 Herald groups** — the multi-group-per-host
case the spec calls out (§D.1). `gems[0]` is always the active; `gems[1:]` are its linked gems
in order.

**Index alignment (spec §D.2):** `it.supports[i]` mirrors `gems[i+1]` by position (same length,
same order) — verified True for every group. This is why a **linked second active** prices
correctly: Herald of Ice's group carries `gems[1] = Herald of Agony` with `support: false`
(a second active, not a support) yet still priced 111c and summed (156 = 45 + 111). The
breakdown never relies on "index > 0 == support". Herald of Ash likewise carries a linked
second active (Herald of Thunder, 104.4c), and Leap Slam carries two (Arctic Armour, Righteous
Fire) plus one true support (Arrogance).

---

## 4. Support prices sum into the group total (D-0006 clause 2)

Invariant (spec §A.3): `total_chaos == sum(g.chaos for g in gems if g.chaos != null)` **and**
`total_chaos == chaos.median`. Verified True for ALL 6 groups (driver asserts both per group).

Concrete support-inclusion proof, main skill:

```
active-only (Ethereal Knives)          = 109.9 c
5 supports (1455 + 408 + 30.3 + 46.5 + 20.6) = 1960.4 c
group total_chaos                      = 2070.3 c   (== active + all supports)
```

The most expensive component is a support (Greater Spell Echo, 1455c) — exactly why the port
prices every support (D-0003/D-0006). Support costs are INCLUDED in every group total, as
D-0006 requires.

---

## 5. GRANTED audit — only genuinely item-provided gems flagged (D-0006 clause 3)

**Authority** (raw `itemProvidedGems` in the fixture) has exactly ONE entry:

```json
[{ "slot": 9, "gems": [{ "name": "Herald of the Hive", "level": 30, "quality": 0, "isBuiltInSupport": false }] }]
```

Engine result — `it.granted` per gem:

| gem | it.granted | why |
|---|---|---|
| Ethereal Knives of the Massacre | **false** | real socketed gem (has itemData baseType) |
| Herald of Ice | **false** | real socketed gem |
| Herald of Ash | **false** | real socketed gem |
| Herald of Purity | **false** | real socketed gem |
| Leap Slam | **false** | real socketed gem |
| Herald of the Hive | **true** | `itemProvidedGems` slot+name match (slot 9) **and** empty itemData `[INFERRED-safe]` |

- Granted set == exactly `["Herald of the Hive"]`. PASS — the item-provided Herald from the
  **Lost Unity** ring (Ring2, slot 9), the ONLY gem D-0006 says should be tagged. Every
  socketed Herald + Leap Slam + the main skill are clean.
- `isBuiltInSupport` is false for this entry, so the authoritative slot+name match is doing the
  work; the belt-and-suspenders empty-itemData rule (`[INFERRED]`, `bpc/poeninja.py::
  _gem_is_granted`) is strictly safe here — every real socketed gem in this build carries a
  `baseType`, so nothing is mis-flagged.

**Granted excluded from total; supports still count.** The granted active's payload has all
prices null, `total_chaos: null`, note "item-granted skill (comes free with the host item)",
and its single `gems[0]` has `chaos: null`, `granted: true` — field-for-field consistent with
`feedback1-spec.md` §A.2. No misleading number is printed for a free-with-item gem.

The "granted ACTIVE with a real socketed support → active excluded, support still counts" case
has no instance in this fixture (the one granted gem has no supports), but is covered by the
suite as a structural guarantee (`tests.py:669–681`: `total_chaos == the support's price alone,
active price null`).

---

## 6. D-0006 verbatim — clause-by-clause (engine side)

1. **Flask belt = 5 generic slots, overflow shown, no life/mana guessing.** Engine: PASS
   (§2). Every flask emitted in belt order in one `flask` group; overflow never dropped;
   no life/mana classification.
2. **Gems grouped by HOST ITEM; supports nested under their active; support costs in totals;
   host info + per-gem breakdown additive in `PriceResult.extra`.** Engine: PASS (§3–4). All
   `host_*` + `gems[]` present and additive; index alignment holds; supports summed.
3. **GRANTED audit — only genuinely item-provided gems tagged; granted excluded from totals
   while socketed supports still count.** Engine: PASS (§5). Only Herald of the Hive. **Now
   also correct end-to-end** — the `web.py` §B.1 skeleton `granted` fix (prior round's sole
   finding) has landed, so the rendered badge/default-off read the correct engine value
   (§0/F1).
4. **Autoscan button.** UI-only (a button + glow in the affix picker wired to the existing
   `bpc.searchAllRares` default all-affix path). Nothing engine-side changed; out of scope for
   this engine data verification (skin agents own it; the default all-affix rare query it
   triggers is unchanged and covered by existing rare-default tests).

---

## 7. How to reproduce (offline, no trade calls)

```
cd C:\scripts\buildpricechecker-poe1
python tests.py                        # green; re-run under a socket-level network block => still green

# engine data drive (network hard-blocked at socket layer):
#  - normalize(research/data/char_poe1.json) -> items         (flasks + gem groups)
#  - PoeNinjaEconomy("Allflame"); cache.get monkeypatched to cache.peek (TTL bypass)
#  - Pricer.price_skill(each of the 6 gem groups); serialize via bpc.web._result_dict
#  - assert: all host_* present; gems[] index-aligned with it.supports; total_chaos ==
#            sum(non-null gem chaos) == chaos.median; granted only on Herald of the Hive;
#            flask group == raw flasks[] order
```

All inputs are on disk: the fixture (`research/data/char_poe1.json`) and the poe.ninja SkillGem
economy (`cache/…` key `poeninja:econ1i:Allflame:SkillGem`). No pathofexile.com trade
search/fetch/exchange endpoints were called at any point.
