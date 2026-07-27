/*
 * Offline unit tests for the PER-RARE AFFIX PICKER query builder (D-0015).
 *   node test_picker.mjs
 *
 * No browser, no network, no pathofexile.com. Loads assets/core.js (it exports its
 * API under CommonJS) and exercises the pure, client-side query builder the picker
 * drives: bpc.buildRareQuery / rareDefaultPicks / affixPrefill / rareTradeUrl.
 *
 * The spec (docs/00-decision-log.md D-0015): the default state has EVERY searchable
 * affix ticked with its roll prefilled — the tool never unticks anything; only the
 * USER subtracts or edits. So "all ticked, unedited" must reproduce the item's own
 * strict query (modulo ordering), and every user action (untick / edit a min / fold
 * resistances / clear a min) must change the query in exactly the documented way.
 *
 * Also parse-checks assets/core.js and the index.html inline <script>.
 */
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const bpc = require("./assets/core.js");

let passed = 0, failed = 0;
function ok(cond, msg) { if (cond) { passed++; } else { failed++; console.error("  FAIL:", msg); } }
function eq(a, b, msg) { ok(JSON.stringify(a) === JSON.stringify(b), `${msg}  (got ${JSON.stringify(a)} want ${JSON.stringify(b)})`); }

// ---- order-independent canonical form: sort object keys recursively + sort stats filters ----
function canon(v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === "object") {
    const o = {}; Object.keys(v).sort().forEach((k) => { o[k] = canon(v[k]); }); return o;
  }
  return v;
}
function canonQuery(q) {
  const c = canon(q);
  if (Array.isArray(c.stats)) c.stats.forEach((g) => {
    if (Array.isArray(g.filters)) g.filters.sort((a, b) => (JSON.stringify(a) < JSON.stringify(b) ? -1 : 1));
  });
  return JSON.stringify(c);
}
function eqQ(a, b, msg) { const ca = canonQuery(a), cb = canonQuery(b); ok(ca === cb, `${msg}\n     built ${ca}\n     want  ${cb}`); }
// the set of stat-filter ids in a built query's single AND group
function statIds(q) { return ((q.stats && q.stats[0] && q.stats[0].filters) || []).map((f) => f.id).sort(); }
function filterFor(q, id) { return ((q.stats && q.stats[0] && q.stats[0].filters) || []).find((f) => f.id === id); }
function armour(q) { return (q.filters && q.filters.armour_filters && q.filters.armour_filters.filters) || null; }

// =====================================================================
//  FIXTURE — one rich rare: Life (normal) + Fire/Cold res + a NEGATED
//  ("reduced") stat + an UNSEARCHABLE mod + a defence (es) total; two
//  resistance pseudo totals (elemental + chaos). Its `orig` query is the
//  item's own strict trade_query, authored roll-min + pseudo-folded — i.e.
//  exactly what the picker's all-ticked default should reproduce.
// =====================================================================
const RARE = {
  affixes: [
    { kind: "stat", text: "+112 to maximum Life", stat_id: "explicit.stat_life", value: 112, default_min: 112, default_max: null, searchable: true, resist: false, negated: false },
    { kind: "stat", text: "+41% to Fire Resistance", stat_id: "explicit.stat_fire", value: 41, default_min: 41, default_max: null, searchable: true, resist: true, negated: false },
    { kind: "stat", text: "+38% to Cold Resistance", stat_id: "explicit.stat_cold", value: 38, default_min: 38, default_max: null, searchable: true, resist: true, negated: false },
    { kind: "stat", text: "21% reduced Mana Cost of Skills", stat_id: "explicit.stat_manacost", value: -21, default_min: null, default_max: -21, searchable: true, resist: false, negated: true },
    { kind: "stat", text: "1 Added Passive Skill is Blowback", stat_id: null, value: null, default_min: null, default_max: null, searchable: false, resist: false, negated: false, reason: "no trade filter matches this mod" },
    { kind: "equip", key: "es", text: "Total Energy Shield", value: 520, default_min: 520, default_max: null, searchable: true, resist: false, negated: false },
  ],
  pseudo: [
    { kind: "stat", text: "+#% total Elemental Resistance", stat_id: "pseudo.pseudo_total_elemental_resistance", value: 79, default_min: 79, default_max: null, searchable: true, resist: true, negated: false },
    { kind: "stat", text: "+#% total to Chaos Resistance", stat_id: "pseudo.pseudo_total_chaos_resistance", value: 24, default_min: 24, default_max: null, searchable: true, resist: true, negated: false },
  ],
};
// the item's own strict query (roll-min, pseudo-folded, 6-link) — key order deliberately DIFFERENT
// from the builder's output, to prove the "modulo ordering" comparison really is order-independent.
const ORIG = { status: { option: "online" }, type: "Vaal Regalia",
  stats: [{ type: "and", filters: [
    { id: "explicit.stat_life", value: { min: 112 } },
    { id: "explicit.stat_manacost", value: { max: -21 } },
    { id: "pseudo.pseudo_total_elemental_resistance", value: { min: 79 } },
    { id: "pseudo.pseudo_total_chaos_resistance", value: { min: 24 } } ] }],
  filters: { socket_filters: { filters: { links: { min: 6 } } }, armour_filters: { filters: { es: { min: 520 } } } } };

// a category-scope rare (no base type): scope lives in filters.type_filters, which must be preserved
const CAT_RARE = { affixes: [
  { kind: "stat", text: "12% increased maximum Life", stat_id: "explicit.stat_lifepct", value: 12, default_min: 12, default_max: null, searchable: true, resist: false, negated: false } ], pseudo: [] };
const CAT_ORIG = { status: { option: "online" },
  filters: { type_filters: { filters: { category: { option: "jewel" } } } },
  stats: [{ type: "and", filters: [{ id: "explicit.stat_lifepct", value: { min: 12 } }] }] };

console.log("· parse-check: assets/core.js + index.html inline <script>");
try { new vm.Script(fs.readFileSync(join(HERE, "assets", "core.js"), "utf8"), { filename: "core.js" }); ok(true, "core.js parses"); }
catch (e) { ok(false, "core.js parse error: " + e.message); }
(function () {
  const html = fs.readFileSync(join(HERE, "index.html"), "utf8");
  const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  const main = blocks.find((b) => b.includes("bpc.init("));
  ok(!!main, "found index.html inline script");
  try { new vm.Script(main, { filename: "index-inline.js" }); ok(true, "index.html inline script parses"); }
  catch (e) { ok(false, "index.html inline parse error: " + e.message); }
})();

console.log("· rareDefaultPicks: every searchable affix ticked; pseudo default ON");
{
  const d = bpc.rareDefaultPicks(RARE);
  ok(d.usePseudo === true, "usePseudo ON when the item has resistance pseudo totals");
  ok(d.affix[0].ticked && d.affix[1].ticked && d.affix[2].ticked && d.affix[3].ticked && d.affix[5].ticked, "all searchable affixes + equip ticked by default (D-0015)");
  ok(d.affix[4].ticked === false, "the unsearchable affix is never ticked");
  eq({ min: d.affix[0].min, max: d.affix[0].max }, { min: 112, max: null }, "normal roll prefills MIN");
  eq({ min: d.affix[3].min, max: d.affix[3].max }, { min: null, max: -21 }, "negated ('reduced') roll prefills MAX");
  eq({ min: d.affix[5].min, max: d.affix[5].max }, { min: 520, max: null }, "defence total prefills MIN only");
  ok(d.pseudo[0].ticked && d.pseudo[1].ticked, "pseudo rows ticked by default");
  const d2 = bpc.rareDefaultPicks({ affixes: [], pseudo: [] });
  ok(d2.usePseudo === false, "usePseudo OFF when there are no resistances");
}

console.log("· CASE 1 — all-ticked == the item's own strict query (modulo ordering)");
{
  eqQ(bpc.buildRareQuery(RARE, ORIG, bpc.rareDefaultPicks(RARE)), ORIG, "explicit all-ticked picks reproduce ORIG");
  eqQ(bpc.buildRareQuery(RARE, ORIG), ORIG, "omitted picks default to all-ticked and reproduce ORIG");
  eqQ(bpc.buildRareQuery(CAT_RARE, CAT_ORIG), CAT_ORIG, "category-scope rare: all-ticked reproduces ORIG (type_filters preserved)");
}

console.log("· CASE 1b — structural fidelity vs a PRESENCE-ONLY (real-API-style) original");
{
  // The public API's default query is looser than the picker (presence-only `{id}` stats, 85%
  // armour). The picker is deliberately stricter (min = the roll), but it must still require the
  // SAME set of affixes + the SAME scope + links — dropping nothing, inventing nothing (D-0015).
  const PRESENCE = { type: "Vaal Regalia", status: { option: "online" },
    stats: [{ type: "and", filters: [
      { id: "explicit.stat_life" }, { id: "explicit.stat_manacost", value: { max: -21 } },
      { id: "pseudo.pseudo_total_elemental_resistance" }, { id: "pseudo.pseudo_total_chaos_resistance" } ] }],
    filters: { socket_filters: { filters: { links: { min: 6 } } }, armour_filters: { filters: { es: { min: 442 } } } } };
  const q = bpc.buildRareQuery(RARE, PRESENCE);
  eq(statIds(q), statIds(PRESENCE), "same set of stat-filter ids as the API's strict query");
  eq(q.type, PRESENCE.type, "type scope copied verbatim");
  eq(q.status, PRESENCE.status, "status copied verbatim");
  eq(q.filters.socket_filters, PRESENCE.filters.socket_filters, "links socket filter copied verbatim");
  eq(Object.keys(armour(q)).sort(), ["es"], "armour_filters keys == the item's defence totals");
}

console.log("· CASE 2 — untick one affix removes exactly that filter");
{
  const p = bpc.rareDefaultPicks(RARE); p.affix[0].ticked = false;   // untick Life
  const q = bpc.buildRareQuery(RARE, ORIG, p);
  ok(!filterFor(q, "explicit.stat_life"), "unticked Life is gone");
  eq(statIds(q).length, statIds(ORIG).length - 1, "exactly one fewer stat filter");
  ok(!!filterFor(q, "pseudo.pseudo_total_elemental_resistance"), "the rest are untouched");
}

console.log("· CASE 3 — pseudo fold on/off swaps individual resistances <-> the totals");
{
  const on = bpc.buildRareQuery(RARE, ORIG, bpc.rareDefaultPicks(RARE));
  ok(!filterFor(on, "explicit.stat_fire") && !filterFor(on, "explicit.stat_cold"), "fold ON: individual fire/cold absent");
  ok(filterFor(on, "pseudo.pseudo_total_elemental_resistance") && filterFor(on, "pseudo.pseudo_total_chaos_resistance"), "fold ON: pseudo totals present");
  const pOff = bpc.rareDefaultPicks(RARE); pOff.usePseudo = false;
  const off = bpc.buildRareQuery(RARE, ORIG, pOff);
  ok(filterFor(off, "explicit.stat_fire") && filterFor(off, "explicit.stat_cold"), "fold OFF: individual fire/cold present");
  ok(!filterFor(off, "pseudo.pseudo_total_elemental_resistance") && !filterFor(off, "pseudo.pseudo_total_chaos_resistance"), "fold OFF: pseudo totals absent");
}

console.log("· CASE 4 — editing a min flows through; clearing a min loosens to presence-only");
{
  const p = bpc.rareDefaultPicks(RARE); p.affix[0].min = 150;         // raise the Life min
  eq(filterFor(bpc.buildRareQuery(RARE, ORIG, p), "explicit.stat_life").value, { min: 150 }, "edited min appears in value.min");
  const p2 = bpc.rareDefaultPicks(RARE); p2.affix[0].min = null;      // clear it -> "any roll"
  ok(filterFor(bpc.buildRareQuery(RARE, ORIG, p2), "explicit.stat_life").value === undefined, "cleared min -> presence-only {id} (no value)");
  const p3 = bpc.rareDefaultPicks(RARE); p3.affix[0].min = 90; p3.affix[0].max = 130;
  eq(filterFor(bpc.buildRareQuery(RARE, ORIG, p3), "explicit.stat_life").value, { min: 90, max: 130 }, "both bounds honoured");
}

console.log("· CASE 5 — a NEGATED affix filters as a max, not a min");
{
  eq(filterFor(bpc.buildRareQuery(RARE, ORIG), "explicit.stat_manacost").value, { max: -21 }, "negated -> value.max = the (negative) roll");
}

console.log("· CASE 6 — the unsearchable affix is NEVER emitted (even if forced ticked)");
{
  const p = bpc.rareDefaultPicks(RARE);
  p.affix[4] = { ticked: true, min: 1, max: null };                  // pretend the UI ticked it
  const q = bpc.buildRareQuery(RARE, ORIG, p);
  ok(statIds(q).indexOf("null") < 0 && statIds(q).length === statIds(ORIG).length, "unsearchable (stat_id null) contributes no filter");
}

console.log("· CASE 7 — defence totals go to armour_filters (min-only) and untick removes them");
{
  eq(armour(bpc.buildRareQuery(RARE, ORIG)), { es: { min: 520 } }, "equip -> armour_filters.es.min");
  const p = bpc.rareDefaultPicks(RARE); p.affix[5].ticked = false;
  ok(armour(bpc.buildRareQuery(RARE, ORIG, p)) === null, "unticking the defence total drops armour_filters entirely");
  const p2 = bpc.rareDefaultPicks(RARE); p2.affix[5].min = 600;
  eq(armour(bpc.buildRareQuery(RARE, ORIG, p2)), { es: { min: 600 } }, "editing the defence min flows through");
}

console.log("· CASE 8 — links + scope come ONLY from the item's query, never invented");
{
  const NOLINK = { type: "Amber Amulet", status: { option: "any" }, stats: [{ type: "and", filters: [] }] };
  const q = bpc.buildRareQuery({ affixes: [{ kind: "stat", text: "x", stat_id: "explicit.stat_z", value: 5, default_min: 5, searchable: true, resist: false }], pseudo: [] }, NOLINK);
  ok(!q.filters || !q.filters.socket_filters, "no links in the source query -> none invented");
  eq(q.status, { option: "any" }, "status carried verbatim from the source query (not defaulted)");
  eq(q.type, "Amber Amulet", "type carried verbatim; never guessed");
  ok(bpc.queryLinks(ORIG) === 6 && bpc.queryLinks(NOLINK) === null, "queryLinks reads the links chip value");
}

console.log("· CASE 9 — rareTradeUrl builds one ?q= from the same query, reusing host+league");
{
  const q = bpc.buildRareQuery(RARE, ORIG);
  const url = bpc.rareTradeUrl(q, "https://www.pathofexile.com/trade/search/Standard?q=OLDENCODED");
  ok(url.indexOf("https://www.pathofexile.com/trade/search/Standard?q=") === 0, "reuses the item's host+league path");
  ok((url.match(/\?q=/g) || []).length === 1, "exactly one ?q= (old payload replaced, not appended)");
  const decoded = JSON.parse(decodeURIComponent(url.split("?q=")[1]));
  eqQ(decoded.query, q, "the URL encodes the SAME query the extension would run");
  eq(decoded.sort, { price: "asc" }, "sorted price asc, like the server");
}

// =====================================================================
//  D-0016 — priority tiers -> groups (item 3), category<->base scope
//  (item 2), rare price distribution (item 4). All pure + offline.
// =====================================================================
// A rare with API `priority` hints (contract §3) + a `scopes` payload (rare/magic carry both).
const TRARE = {
  scopes: { category: { id: "weapon.wand", label: "Wand" }, base: { type: "Opal Wand", label: "Opal Wand" } },
  affixes: [
    { kind: "stat", text: "+45 to maximum Life",  stat_id: "explicit.stat_life",    value: 45, default_min: 45, default_max: null, searchable: true,  resist: false, negated: false, priority: "required" },
    { kind: "stat", text: "+30% to Fire Damage",  stat_id: "explicit.stat_firedmg", value: 30, default_min: 30, default_max: null, searchable: true,  resist: false, negated: false, priority: "nice" },
    { kind: "stat", text: "+12% to Cast Speed",   stat_id: "explicit.stat_cast",    value: 12, default_min: 12, default_max: null, searchable: true,  resist: false, negated: false, priority: "notimp" },
    { kind: "stat", text: "1 Added Passive is X", stat_id: null,                     value: null, default_min: null, default_max: null, searchable: false, resist: false, negated: false, priority: "skip", reason: "no trade filter matches this mod" },
  ],
  pseudo: [],
};
// its DEFAULT (category-scoped) query — what the API hands the row as origQuery
const TORIG = { status: { option: "online" },
  filters: { type_filters: { filters: { category: { option: "weapon.wand" } } } },
  stats: [{ type: "and", filters: [ { id: "explicit.stat_life" }, { id: "explicit.stat_firedmg" }, { id: "explicit.stat_cast" } ] }] };

console.log("· D-0016 item 3 — rareDefaultPicks prefills each tier from the API priority");
{
  const d = bpc.rareDefaultPicks(TRARE);
  eq(d.affix[0].tier, "required", "priority required -> tier required");
  eq(d.affix[1].tier, "nice", "priority nice -> tier nice");
  eq(d.affix[2].tier, "nice", "priority notimp -> tier nice (D-0015: never auto-excluded)");
  eq(d.affix[3].tier, "notneeded", "priority skip (unsearchable) -> tier not-needed");
}

console.log("· D-0016 item 3 — tier assignment -> groups (required=AND, nice=count)");
{
  const picks = bpc.tierGroups(TRARE, bpc.rareDefaultPicks(TRARE));
  eq(picks.groups.length, 2, "one AND + one count group");
  eq(picks.groups[0].type, "and", "group 0 = AND (required)");
  eq(picks.groups[1].type, "count", "group 1 = count (nice-to-have)");
  eq(picks.groups[1].min, 2, "count default N = the nice count (all of them; strictest)");
  const q = bpc.buildRareQuery(TRARE, TORIG, picks);
  ok(q.stats.length === 2, "built query has two stat groups");
  const andG = q.stats.find(g => g.type === "and"), cG = q.stats.find(g => g.type === "count");
  eq(andG.filters.map(f => f.id).sort(), ["explicit.stat_life"], "AND group holds only the required affix");
  eq(cG.filters.map(f => f.id).sort(), ["explicit.stat_cast", "explicit.stat_firedmg"], "count group holds the nice affixes");
  eq(cG.value, { min: 2 }, "count group carries group-level value.min = 2");
}

console.log("· D-0016 item 3 — count 'match at least N' spinner loosens/clamps");
{
  const base = bpc.rareDefaultPicks(TRARE); base.countMin = 1;   // user drops N from 2 to 1
  const picks = bpc.tierGroups(TRARE, base);
  eq(picks.groups[1].min, 1, "countMin=1 loosens the nice group to 'match at least 1'");
  eq(bpc.buildRareQuery(TRARE, TORIG, picks).stats.find(g => g.type === "count").value, { min: 1 }, "the loosened N flows into the query");
  const hi = bpc.rareDefaultPicks(TRARE); hi.countMin = 9;       // above #nice
  eq(bpc.tierGroups(TRARE, hi).groups[1].min, 2, "countMin above #nice clamps to #nice");
  const lo = bpc.rareDefaultPicks(TRARE); lo.countMin = 0;       // below 1
  eq(bpc.tierGroups(TRARE, lo).groups[1].min, 1, "countMin below 1 clamps to 1 (never a 0-of-N no-op)");
}

console.log("· D-0016 item 3 — a NOT-NEEDED affix is dropped (that IS a user action)");
{
  const p = bpc.rareDefaultPicks(TRARE); p.affix[1].tier = "notneeded";   // demote Fire Damage
  const q = bpc.buildRareQuery(TRARE, TORIG, bpc.tierGroups(TRARE, p));
  const ids = q.stats.reduce((a, g) => a.concat(g.filters.map(f => f.id)), []);
  ok(ids.indexOf("explicit.stat_firedmg") < 0, "the not-needed affix is gone from the query");
  ok(ids.indexOf("explicit.stat_life") >= 0 && ids.indexOf("explicit.stat_cast") >= 0, "the rest remain");
  eq(q.stats.find(g => g.type === "count").value, { min: 1 }, "one remaining nice -> count(min 1)");
}

console.log("· D-0016 item 3 — all-required tiers == the previous single-AND behaviour");
{
  const p = bpc.rareDefaultPicks(TRARE);
  Object.keys(p.affix).forEach(i => { if (p.affix[i]) p.affix[i].tier = "required"; });
  const grouped = bpc.buildRareQuery(TRARE, TORIG, bpc.tierGroups(TRARE, p));
  const flat = bpc.buildRareQuery(TRARE, TORIG);           // legacy all-ticked single-AND query
  eqQ(grouped, flat, "all-required tiers reproduce the previous single-AND query");
  ok(grouped.stats.length === 1 && grouped.stats[0].type === "and", "exactly one AND group");
}

console.log("· D-0016 item 2 — scope selector: category <-> base, both drive the query");
{
  const baseQ = bpc.applyScope(TRARE, TORIG, "base");
  eq(baseQ.type, "Opal Wand", "base scope sets type = the exact base");
  ok(!baseQ.filters || !baseQ.filters.type_filters, "base scope drops the category type_filters");
  const catQ = bpc.applyScope(TRARE, TORIG, "category");
  eq(catQ.filters.type_filters.filters.category, { option: "weapon.wand" }, "category scope keeps the category option");
  ok(catQ.type === undefined, "category scope has no exact type");
  const qb = bpc.buildRareQuery(TRARE, bpc.applyScope(TRARE, TORIG, "base"), bpc.rareDefaultPicks(TRARE));
  eq(qb.type, "Opal Wand", "buildRareQuery on the base scope emits type=base");
  ok(!qb.filters || !qb.filters.type_filters, "…and no category filter");
  const qc = bpc.buildRareQuery(TRARE, bpc.applyScope(TRARE, TORIG, "category"), bpc.rareDefaultPicks(TRARE));
  eq(qc.filters.type_filters.filters.category, { option: "weapon.wand" }, "buildRareQuery on the category scope emits the category option");
  ok(qc.type === undefined, "…and no exact type");
  // a scope swap must preserve status + the 5/6-link socket_filters (never invented, never dropped)
  const withLinks = JSON.parse(JSON.stringify(TORIG));
  withLinks.filters.socket_filters = { filters: { links: { min: 6 } } };
  const bl = bpc.applyScope(TRARE, withLinks, "base");
  eq(bl.filters.socket_filters, { filters: { links: { min: 6 } } }, "scope swap preserves the 5/6-link socket_filters");
  eq(bl.status, { option: "online" }, "scope swap preserves status");
  // an unavailable scope returns the query unchanged (never invents)
  const noBase = { scopes: { category: { id: "jewel", label: "Any Jewel" }, base: null } };
  eqQ(bpc.applyScope(noBase, TORIG, "base"), TORIG, "requesting an absent scope leaves the query unchanged");
}

console.log("· D-0016 item 4 — rare tiers from the extension's prices[] (local distribution math)");
{
  // scam-low (1) + typo-high (9999) get trimmed; kept = [20,22,25,30]
  const prices = [ { amount: 1, currency: "chaos" }, { amount: 20, currency: "chaos" }, { amount: 22, currency: "chaos" },
                   { amount: 25, currency: "chaos" }, { amount: 30, currency: "chaos" }, { amount: 9999, currency: "chaos" } ];
  const t = bpc.rareTiersFromPrices(prices, 100);
  eq(t.min, 20, "min = cheapest KEPT (scam-low 1 trimmed, not the raw cheapest)");
  eq(t.median, 23.5, "median of the kept set [20,22,25,30]");
  eq(t.high, 28.5, "high = linear-interp 90th percentile of the kept set");
  eq(t.sample, 4, "two outliers trimmed -> 4 kept");
  eq(bpc.rareTiersFromPrices([{ amount: 1, currency: "div" }, { amount: 1, currency: "div" }], 100).median, 100, "divine converts at the given rate (1 div = 100c)");
  ok(bpc.rareTiersFromPrices([], 100) === null, "no prices -> null (falls back to single value)");
  ok(bpc.rareTiersFromPrices(null, 100) === null, "missing prices -> null");
  ok(bpc.rareTiersFromPrices([{ amount: 5, currency: "exalted" }], 100) === null, "all-non-convertible -> null (never fabricated)");
  eq(bpc.tiersFromChaos([10]), { min: 10, median: 10, high: 10, sample: 1 }, "single value -> min=median=high");
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
