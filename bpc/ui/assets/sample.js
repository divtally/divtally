/* A realistic, fully-priced job snapshot for demos + headless verification.
 * Lets any UI version render a complete PoE1 build (totals, exclude toggles, advanced
 * picker, currency icons, PoB copy, plus the D-0006 host-grouped gem section + 5-slot flask
 * belt) with NO backend / no trade calls:   bpc.loadMock(window.BPC_SAMPLE)
 *
 * ---- DEMO DATA — NOT a live pricing result. EVERY number here is illustrative. ----
 * A plausible but FICTIONAL Path of Exile 1 Firestorm Elementalist. Item / gem names and
 * bases are real PoE1 entities, but the assembled character, all chaos prices, and the
 * item->skill grants are demo fabrications — treat every value as [DEMO], never as a
 * source-of-truth price. This snapshot is built to EXERCISE the feedback-round-1 UI:
 *   - a 5-slot FLASK BELT of utility flasks in belt order, no life/mana slots (spec C);
 *   - GEMS grouped under their HOST ITEM — a 6-link Body skill (Firestorm), a Weapon herald,
 *     a Helmet aura, a Boots movement link — each support priced individually and nested
 *     under its active, support costs included in the group total (spec D);
 *   - exactly ONE genuinely item-granted gem: Herald of Agony, granted by the Lost Unity
 *     ring, so the GRANTED tag renders in one legitimate place and NOWHERE else. The
 *     socketed Herald of Ash in the weapon is deliberately NOT granted — that contrast is
 *     the D-0006 bug fix (heralds are socketed, not item-provided) made visible (spec B).
 * Icons are real web.poecdn.com PoE1 art; a few are reused across slots/gems purely so every
 * box has a picture. This is a demo, not a screenshot.
 */
// real web.poecdn.com PoE1 icon URLs (poe.ninja carries these per item/gem). Rare slots and
// a few gems reuse a plausible same-slot/same-theme icon purely so the demo has a picture in
// the box (see header) — the art is illustrative, not the actual item/gem.
var _IC = {
  helm:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9IZWxtZXRzL0Nyb3duT2ZUaGVJbndhcmRFeWUiLCJ3IjoyLCJoIjoyLCJzY2FsZSI6MX1d/fdb20856e4/CrownOfTheInwardEye.png",
  body:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9Cb2R5QXJtb3Vycy9Cb2R5SW50MUNVbmlxdWUiLCJ3IjoyLCJoIjozLCJzY2FsZSI6MX1d/4f3e22a163/BodyInt1CUnique.png",
  gloves:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9HbG92ZXMvQXNlbmF0aHNHZW50bGVUb3VjaCIsInciOjIsImgiOjIsInNjYWxlIjoxfV0/ea6e822bbe/AsenathsGentleTouch.png",
  boots:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9Cb290cy9BdHppcmlzU3RlcCIsInciOjIsImgiOjIsInNjYWxlIjoxfV0/ec85575514/AtzirisStep.png",
  belt:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQmVsdHMvSGVhZGh1bnRlciIsInciOjIsImgiOjEsInNjYWxlIjoxLCJyZWxpYyI6Nn1d/2b87042278/Headhunter.png",
  amulet:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQW11bGV0cy9HbGFjaWVyQ2Fjb29uVXBncmFkZSIsInciOjEsImgiOjEsInNjYWxlIjoxfV0/f54aa988e2/GlacierCacoonUpgrade.png",
  ring:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvUmluZ3MvVGhlVGFtaW5nIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/17c5d3d74b/TheTaming.png",
  ring2:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvUmluZ3MvUmluZzEwIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/55c8711fd7/Ring10.png",
  weapon:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvV2VhcG9ucy9PbmVIYW5kV2VhcG9ucy9TY2VwdGVycy9Eb3J5YW5pc0NhdGFseXN0IiwidyI6MiwiaCI6Mywic2NhbGUiOjF9XQ/aa54cbb507/DoryanisCatalyst.png",
  shield:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9TaGllbGRzL1NoaWVsZFN0ckludFVuaXF1ZTYiLCJ3IjoyLCJoIjozLCJzY2FsZSI6MX1d/89281a7dc3/ShieldStrIntUnique6.png",
  wand:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvV2VhcG9ucy9PbmVIYW5kV2VhcG9ucy9XYW5kcy9QaXNjYXRvcnNWaWdpbCIsInciOjEsImgiOjMsInNjYWxlIjoxfV0/332f80f7ac/PiscatorsVigil.png",
  shield2:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9TaGllbGRzL1RoZUNvcnVuZHVtIiwidyI6MiwiaCI6Mywic2NhbGUiOjF9XQ/f9ca50a663/TheCorundum.png",
  flask:"https://web.poecdn.com/gen/image/WzksMTQseyJmIjoiMkRJdGVtcy9GbGFza3MvQXR6aXJpc1Byb21pc2UiLCJ3IjoxLCJoIjoyLCJzY2FsZSI6MSwibGV2ZWwiOjF9XQ/8a5f4f13b4/AtzirisPromise.png",
  jewel:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvSmV3ZWxzL0VsZGVySmV3ZWwiLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/278c673716/ElderJewel.png",
  jewel2:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvSmV3ZWxzL0Nvbm5lY3RlZEpld2VsIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/1d2c1f698a/ConnectedJewel.png",
  firestorm:"https://web.poecdn.com/gen/image/WzMwLDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9GaXJlc3Rvcm0iLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/fc6447dde0/Firestorm.png",
  spellecho:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9TdXBwb3J0L0VjaG8iLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/1868afbf2e/Echo.png",
  cd:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9TdXBwb3J0L0NvbnRyb2xsZWREZXN0cnVjdGlvbkdlbSIsInciOjEsImgiOjEsInNjYWxlIjoxfV0/0fca4292bb/ControlledDestructionGem.png",
  ef:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9TdXBwb3J0L0VsZW1lbnRhbEZvY3VzIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/89a3556bad/ElementalFocus.png",
  conc:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9TdXBwb3J0L0NvbmNlbnRyYXRlZEFPRSIsInciOjEsImgiOjEsInNjYWxlIjoxfV0/4db641d292/ConcentratedAOE.png",
  ignite:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9TdXBwb3J0L0lnbml0ZVByb2xpZmVyYXRpb24iLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/e6a337b58f/IgniteProliferation.png",
  determination:"https://web.poecdn.com/gen/image/WzMwLDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9EZXRlcm1pbmF0aW9uIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/9d35188568/Determination.png",
  enlighten:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9TdXBwb3J0L0VubGlnaHRlbiIsInciOjEsImgiOjEsInNjYWxlIjoxfV0/05a949e270/Enlighten.png",
  flamedash:"https://web.poecdn.com/gen/image/WzMwLDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9GbGFtZURhc2giLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/09b5080831/FlameDash.png",
  secondwind:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9TdXBwb3J0L1NlY29uZFdpbmRTdXBwb3J0IiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/ccfc5c7b25/SecondWindSupport.png",
  arcanesurge:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9TdXBwb3J0L0FyY2FuZVN1cmdlIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/d3d0499c29/ArcaneSurge.png"
};
var _TU = "https://www.pathofexile.com/trade/search/Allflame?q=demo";   // demo trade link (PoE1 form)
window.BPC_SAMPLE = {
  state: "done",
  advanced: false,
  searches: 21,
  meta: {
    character: "AshweaverDemo", "class": "Elementalist", level: 96,
    league: "Allflame", divine_to_chaos: 106, status: "online",
    chaos_img: "https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lSZXJvbGxSYXJlIiwic2NhbGUiOjF9XQ/46a2347805/CurrencyRerollRare.png",
    divine_img: "https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lNb2RWYWx1ZXMiLCJzY2FsZSI6MX1d/ec48896769/CurrencyModValues.png",
    pob_code: "eNrtWVtT4zgWfu-q_g8u9rkxsmzZTld6tgRJN8wEyAS6Z-aJUmwlEThyypIDzK_fI8m5kQ7p7Z6anWGqJ7Etn3OdyzofuYwQ8evDS2BTLLPwQbe3t4PgkSnIRRG8YBhFQRTHQRQHQRgGYRRGfhT5fhAGYRiEvh_5fuD7vu_5vud5XV3X9bquNzc3Nzc3R0dHR0dHe3t7e3t7BwcHBwcHh4eHh4eHR0dHR0fHx8fHx8cnJycnJyenp6enp2dnZ2dn5-fn5xcXFxcXl5eXl1dXV9fX19c3Nzc3t7e3d3d3d_f39w8PDw-Pj4-Q",
    source_url: "https://poe.ninja/poe1/builds/allflame/character/DemoAccount/AshweaverDemo"
  },
  items: [
    { index: 0,  name: "Crown of the Inward Eye", group: "equipment", category: "unique", slot: "Helmet",      count: 1, rarity: "Unique", icon: _IC.helm,
      mods: { implicit: [], explicit: ["Increases and Reductions to Life also apply to Energy Shield at 30% of their value", "(15-25)% increased maximum Life", "(15-25)% increased maximum Mana"] } },
    { index: 1,  name: "Rift Shroud",             group: "equipment", category: "rare",   slot: "Body Armour", count: 1, rarity: "Rare", icon: _IC.body,
      mods: { implicit: [], explicit: ["+112 to maximum Life", "+41% to Fire Resistance", "+38% to Cold Resistance", "+520 to maximum Energy Shield"] } },
    { index: 2,  name: "Gauntlets of Malice",     group: "equipment", category: "rare",   slot: "Gloves",      count: 1, rarity: "Rare", icon: _IC.gloves,
      mods: { implicit: [], explicit: ["24% increased Attack Speed", "Adds 12 to 30 Fire Damage to Attacks", "+72 to maximum Life"] } },
    { index: 3,  name: "Atziri's Step",           group: "equipment", category: "unique", slot: "Boots",       count: 1, rarity: "Unique", icon: _IC.boots,
      mods: { implicit: [], explicit: ["118% increased Evasion Rating", "16% chance to Dodge Spell Hits", "+52 to maximum Life", "30% increased Movement Speed"] } },
    { index: 4,  name: "Headhunter",              group: "equipment", category: "unique", slot: "Belt",        count: 1, rarity: "Unique", icon: _IC.belt,
      mods: { implicit: ["+43 to maximum Life"], explicit: ["+40 to Strength", "+55 to maximum Life", "When you Kill a Rare monster, you gain its Modifiers for 20 seconds"] } },
    { index: 5,  name: "Empyrean Idol",           group: "equipment", category: "rare",   slot: "Amulet",      count: 1, rarity: "Rare", icon: _IC.amulet,
      mods: { implicit: ["+12% to all Elemental Resistances"], explicit: ["+1 to Level of all Fire Skill Gems", "+58 to maximum Life", "+35% to Fire Resistance", "24% increased Fire Damage"] } },
    // Lost Unity (real PoE1 Formless Ring unique) — GRANTS a skill; here it grants the one
    // genuinely item-provided gem in this demo (Herald of Agony, priced free below).
    { index: 6,  name: "Lost Unity",              group: "equipment", category: "unique", slot: "Ring",        count: 1, rarity: "Unique", icon: _IC.ring,
      mods: { implicit: ["+16% to all Elemental Resistances"], explicit: ["Grants Level 30 Herald of Agony Skill", "+45 to maximum Life", "10% increased Damage", "Minions deal (25-35)% increased Damage"] } },
    { index: 7,  name: "Brood Grasp",             group: "equipment", category: "rare",   slot: "Ring",        count: 1, rarity: "Rare", icon: _IC.ring2,
      mods: { implicit: ["+18% to Lightning Resistance"], explicit: ["+33% to Cold Resistance", "+58 to maximum Life", "Adds 8 to 16 Fire Damage to Attacks"] } },
    { index: 8,  name: "Doryani's Catalyst",      group: "equipment", category: "unique", slot: "Weapon",      count: 1, rarity: "Unique", icon: _IC.weapon,
      mods: { implicit: [], explicit: ["Adds (36-56) to (60-72) Lightning Damage", "1.8% of Elemental Damage Leeched as Life", "(30-40)% increased Elemental Damage"] } },
    { index: 9,  name: "Corpse Ward",             group: "equipment", category: "rare",   slot: "Off-hand",    count: 1, rarity: "Rare", icon: _IC.shield,
      mods: { implicit: [], explicit: ["+320 to maximum Energy Shield", "+84 to maximum Life", "+45% to Fire Resistance"] } },
    { index: 16, name: "Piscator's Vigil",        group: "equipment", category: "unique", slot: "Weapon (swap)",    count: 1, rarity: "Unique", icon: _IC.wand },
    { index: 17, name: "Prism Guardian",          group: "equipment", category: "unique", slot: "Off-hand (swap)",  count: 1, rarity: "Unique", icon: _IC.shield2 },

    // ---- FLASK BELT: 5 utility flasks, in belt order (no life/mana slots). All share one
    // flask icon purely for the demo picture (see header). ----
    { index: 10, name: "Bottled Faith",           group: "flask", category: "unique", slot: "Flask", count: 1, rarity: "Unique", icon: _IC.flask,
      mods: { implicit: [], explicit: ["Creates Consecrated Ground on Use", "Consecrated Ground created by this Flask has 100% increased Effect", "+2% to Critical Strike Chance against Enemies on Consecrated Ground during effect"] } },
    { index: 11, name: "Cinderswallow Urn",       group: "flask", category: "unique", slot: "Flask", count: 1, rarity: "Unique", icon: _IC.flask,
      mods: { implicit: [], explicit: ["Recover 3% of Life when you Ignite an Enemy", "Onslaught during Flask effect", "20% increased Critical Strike Chance during effect", "Enemies Ignited by you during effect take 10% increased Damage"] } },
    { index: 21, name: "Atziri's Promise",        group: "flask", category: "unique", slot: "Flask", count: 1, rarity: "Unique", icon: _IC.flask,
      mods: { implicit: [], explicit: ["25% of Physical Damage Converted to Chaos Damage during effect", "Gain 15% of Elemental Damage as Extra Chaos Damage during effect", "+35% to Chaos Resistance during effect"] } },
    { index: 22, name: "Quicksilver Flask of Adrenaline", group: "flask", category: "magic", slot: "Flask", count: 1, rarity: "Magic", icon: _IC.flask,
      mods: { implicit: [], explicit: ["40% increased Movement Speed during effect", "25% increased Movement Speed during effect"] } },
    { index: 23, name: "Basalt Flask of the Iron Skin",   group: "flask", category: "magic", slot: "Flask", count: 1, rarity: "Magic", icon: _IC.flask,
      mods: { implicit: [], explicit: ["15% additional Physical Damage Reduction during effect", "+1500 to Armour during effect"] } },

    // ---- JEWELS ----
    { index: 12, name: "Hale Fettle",             group: "jewel",     category: "rare",   slot: "Jewel",       count: 1, rarity: "Rare", icon: _IC.jewel,
      mods: { implicit: [], explicit: ["12% increased maximum Life", "18% increased Fire Damage", "9% increased Cast Speed"] } },
    { index: 13, name: "Watcher's Eye",           group: "jewel",     category: "unique", slot: "Jewel",       count: 1, rarity: "Unique", icon: _IC.jewel },
    { index: 14, name: "Thread of Hope",          group: "jewel",     category: "unique", slot: "Jewel",       count: 1, rarity: "Unique", icon: _IC.jewel2 },
    { index: 15, name: "Blazing Fettle (Large Cluster Jewel)", group: "jewel", category: "rare", slot: "Jewel", count: 1, rarity: "Rare", icon: _IC.jewel,
      mods: { implicit: ["Adds 8 Passive Skills"], explicit: ["Added Small Passive Skills grant: 12% increased Fire Damage", "1 Added Passive Skill is Blowback", "1 Added Passive Skill is Fan the Flames"] } },

    // ---- GEMS: grouped by HOST ITEM. `sockets` = support-gem count (skin label "N sup");
    // `supports[]` mirrors priced[k].gems[1:] by index (each carries its own support/granted). ----
    // Body Armour "Rift Shroud" (rare) — the 6-link main skill (active + 5 supports).
    { index: 18, name: "Firestorm",     group: "gem", category: "gem", slot: "", count: 1, rarity: "Gem", level: 21, quality: 20, corrupted: true, sockets: 5, icon: _IC.firestorm,
      host_slot: "Body Armour", host_name: "Rift Shroud", host_unique: false, host_inventory_id: "BodyArmour",
      supports: [
        { name: "Spell Echo Support",             support: true, granted: false, level: 21, quality: 20, corrupted: true, icon: _IC.spellecho },
        { name: "Controlled Destruction Support", support: true, granted: false, level: 21, quality: 20, corrupted: true, icon: _IC.cd },
        { name: "Elemental Focus Support",        support: true, granted: false, level: 21, quality: 20, corrupted: true, icon: _IC.ef },
        { name: "Concentrated Effect Support",    support: true, granted: false, level: 21, quality: 20, corrupted: true, icon: _IC.conc },
        { name: "Ignite Proliferation Support",   support: true, granted: false, level: 21, quality: 20, corrupted: true, icon: _IC.ignite } ] },
    // Weapon "Doryani's Catalyst" (unique) — a SOCKETED herald (NOT granted: the D-0006 fix).
    { index: 24, name: "Herald of Ash",  group: "gem", category: "gem", slot: "", count: 1, rarity: "Gem", level: 21, quality: 20, corrupted: false, sockets: 1, icon: _IC.firestorm,
      host_slot: "Weapon", host_name: "Doryani's Catalyst", host_unique: true, host_inventory_id: "Weapon",
      supports: [
        { name: "Combustion Support", support: true, granted: false, level: 20, quality: 20, corrupted: false, icon: _IC.ignite } ] },
    // Helmet "Crown of the Inward Eye" (unique) — an aura link; Enlighten drives the cost.
    { index: 19, name: "Determination", group: "gem", category: "gem", slot: "", count: 1, rarity: "Gem", level: 21, quality: 20, corrupted: true, sockets: 1, icon: _IC.determination,
      host_slot: "Helmet", host_name: "Crown of the Inward Eye", host_unique: true, host_inventory_id: "Helm",
      supports: [
        { name: "Enlighten Support", support: true, granted: false, level: 4, quality: 0, corrupted: true, icon: _IC.enlighten } ] },
    // Boots "Atziri's Step" (unique) — movement / utility link.
    { index: 20, name: "Flame Dash",    group: "gem", category: "gem", slot: "", count: 1, rarity: "Gem", level: 21, quality: 20, corrupted: true, sockets: 2, icon: _IC.flamedash,
      host_slot: "Boots", host_name: "Atziri's Step", host_unique: true, host_inventory_id: "Boots",
      supports: [
        { name: "Second Wind Support",  support: true, granted: false, level: 21, quality: 20, corrupted: true, icon: _IC.secondwind },
        { name: "Arcane Surge Support", support: true, granted: false, level: 21, quality: 20, corrupted: true, icon: _IC.arcanesurge } ] },
    // Ring "Lost Unity" (unique) — the ONE genuinely item-granted gem. granted:true -> GRANTED
    // badge here (and only here), null price, excluded from totals by default.
    { index: 25, name: "Herald of Agony", group: "gem", category: "gem", slot: "", count: 1, rarity: "Gem", level: 30, quality: 0, corrupted: false, sockets: 0, granted: true, icon: _IC.determination,
      host_slot: "Ring", host_name: "Lost Unity", host_unique: true, host_inventory_id: "Ring",
      supports: [] }
  ],
  priced: {
    "0":  { chaos: { min: 3,     median: 5,     high: 12 },    confidence: "high",   note: "",                                                     method: "unique",      trade_url: _TU, sample_size: 26, total_found: 340 },
    "1":  { chaos: { min: 45,    median: 82,    high: 180 },   confidence: "medium", note: "6-link; matched Life + 2 res + total ES",               method: "rare_default",trade_url: _TU, sample_size: 18, total_found: 210 },
    "2":  { chaos: { min: 10,    median: 22,    high: 55 },    confidence: "medium", note: "",                                                     method: "rare_default",trade_url: _TU, sample_size: 21, total_found: 480 },
    "3":  { chaos: { min: 3,     median: 4,     high: 9 },     confidence: "high",   note: "",                                                     method: "unique",      trade_url: _TU, sample_size: 30, total_found: 900 },
    "4":  { chaos: { min: 10500, median: 11660, high: 14000 },  confidence: "high",   note: "the chase belt",                                       method: "unique",      trade_url: _TU, sample_size: 20, total_found: 140 },
    "5":  { chaos: { min: 60,    median: 120,   high: 260 },   confidence: "medium", note: "+1 to Level of all Fire Skill Gems drives the price",   method: "rare_default",trade_url: _TU, sample_size: 15, total_found: 160 },
    "6":  { chaos: { min: 10,    median: 18,    high: 35 },    confidence: "high",   note: "grants Herald of Agony (the granted skill is free)",    method: "unique",      trade_url: _TU, sample_size: 24, total_found: 300 },
    "7":  { chaos: { min: 8,     median: 16,    high: 40 },    confidence: "low",    note: "few close listings",                                   method: "rare_default",trade_url: _TU, sample_size: 4,  total_found: 4 },
    "8":  { chaos: { min: 2,     median: 3,     high: 7 },     confidence: "high",   note: "",                                                     method: "unique",      trade_url: _TU, sample_size: 28, total_found: 520 },
    "9":  { chaos: { min: 6,     median: 14,    high: 35 },    confidence: "medium", note: "",                                                     method: "rare_default",trade_url: _TU, sample_size: 16, total_found: 190 },
    "16": { chaos: { min: 1,     median: 1,     high: 3 },     confidence: "high",   note: "",                                                     method: "unique",      trade_url: _TU, sample_size: 30, total_found: 900 },
    "17": { chaos: { min: 3,     median: 5,     high: 11 },    confidence: "high",   note: "",                                                     method: "unique",      trade_url: _TU, sample_size: 22, total_found: 260 },
    // ---- FLASK BELT prices (belt order 10,11,21,22,23) ----
    "10": { chaos: { min: 150,   median: 210,   high: 320 },   confidence: "high",   note: "chase utility flask",                                  method: "unique",      trade_url: _TU, sample_size: 22, total_found: 180 },
    "11": { chaos: { min: 20,    median: 38,    high: 75 },    confidence: "high",   note: "ignite / onslaught utility",                           method: "unique",      trade_url: _TU, sample_size: 24, total_found: 300 },
    "21": { chaos: { min: 10,    median: 15,    high: 25 },    confidence: "high",   note: "",                                                     method: "unique",      trade_url: _TU, sample_size: 27, total_found: 610 },
    "22": { chaos: { min: 1,     median: 2,     high: 5 },     confidence: "low",    note: "",                                                     method: "magic",       trade_url: _TU, sample_size: 12, total_found: 300 },
    "23": { chaos: { min: 2,     median: 4,     high: 9 },     confidence: "low",    note: "",                                                     method: "magic",       trade_url: _TU, sample_size: 12, total_found: 300 },
    // ---- JEWELS ----
    "12": { chaos: { min: 3,     median: 6,     high: 14 },    confidence: "low",    note: "",                                                     method: "rare_default",trade_url: _TU, sample_size: 8,  total_found: 40 },
    "13": { chaos: { min: 30,    median: 45,    high: 120 },   confidence: "medium", note: "generic Watcher's Eye; specific mod combos cost far more", method: "unique",   trade_url: _TU, sample_size: 19, total_found: 130 },
    "14": { chaos: { min: 130,   median: 151,   high: 200 },   confidence: "high",   note: "medium ring radius",                                   method: "unique",      trade_url: _TU, sample_size: 21, total_found: 95 },
    "15": { chaos: { min: null,  median: null,  high: null },  confidence: "none",   note: "no listing matches this exact 8-passive + notable combo - open the trade search", method: "rare_default", trade_url: _TU, sample_size: 0, total_found: 0 },
    // ---- GEMS: each carries host_* + granted + a per-gem gems[] breakdown (spec A/D).
    // Invariant: total_chaos == sum(g.chaos for g in gems if g.chaos != null) — supports included. ----
    // Body Armour "Rift Shroud" (rare host) — 6-link Firestorm.  9.2+99+88.5+65+148+18.9 = 428.6
    "18": { chaos: { min: 428.6, median: 428.6, high: 428.6 }, confidence: "medium", note: "poe.ninja gem economy: active + 5 supports", method: "skill", trade_url: _TU, sample_size: 6, total_found: 6, kind: "skill", level: 21, quality: 20, corrupted: true, source: "poe.ninja", granted: false, host_slot: "Body Armour", host_name: "Rift Shroud", host_base: "Vaal Regalia", host_unique: false, host_inventory_id: "BodyArmour", total_chaos: 428.6, gems: [
        { name: "Firestorm",                       support: false, granted: false, level: 21, quality: 20, corrupted: true, chaos: 9.2,  variant: "21/20c", note: "", trade_url: _TU },
        { name: "Spell Echo Support",              support: true,  granted: false, level: 21, quality: 20, corrupted: true, chaos: 99,   variant: "21/20c", note: "", trade_url: _TU },
        { name: "Controlled Destruction Support",  support: true,  granted: false, level: 21, quality: 20, corrupted: true, chaos: 88.5, variant: "21/20c", note: "", trade_url: _TU },
        { name: "Elemental Focus Support",         support: true,  granted: false, level: 21, quality: 20, corrupted: true, chaos: 65,   variant: "21/20c", note: "", trade_url: _TU },
        { name: "Concentrated Effect Support",     support: true,  granted: false, level: 21, quality: 20, corrupted: true, chaos: 148,  variant: "21/20c", note: "", trade_url: _TU },
        { name: "Ignite Proliferation Support",    support: true,  granted: false, level: 21, quality: 20, corrupted: true, chaos: 18.9, variant: "21/20c", note: "", trade_url: _TU } ] },
    // Weapon "Doryani's Catalyst" (unique host) — SOCKETED Herald of Ash, NOT granted.  5+8 = 13
    "24": { chaos: { min: 13,    median: 13,    high: 13 },    confidence: "medium", note: "poe.ninja gem economy: active + 1 support",  method: "skill", trade_url: _TU, sample_size: 8, total_found: 8, kind: "skill", level: 21, quality: 20, corrupted: false, source: "poe.ninja", granted: false, host_slot: "Weapon", host_name: "Doryani's Catalyst", host_base: "Vaal Sceptre", host_unique: true, host_inventory_id: "Weapon", total_chaos: 13, gems: [
        { name: "Herald of Ash",      support: false, granted: false, level: 21, quality: 20, corrupted: false, chaos: 5, variant: "21/20", note: "", trade_url: _TU },
        { name: "Combustion Support", support: true,  granted: false, level: 20, quality: 20, corrupted: false, chaos: 8, variant: "20/20", note: "", trade_url: _TU } ] },
    // Helmet "Crown of the Inward Eye" (unique host) — Determination + Enlighten.  120+919.6 = 1039.6
    "19": { chaos: { min: 1039.6, median: 1039.6, high: 1039.6 }, confidence: "medium", note: "poe.ninja gem economy: Enlighten 4 drives the cost", method: "skill", trade_url: _TU, sample_size: 2, total_found: 2, kind: "skill", level: 21, quality: 20, corrupted: true, source: "poe.ninja", granted: false, host_slot: "Helmet", host_name: "Crown of the Inward Eye", host_base: "Aventail Helmet", host_unique: true, host_inventory_id: "Helm", total_chaos: 1039.6, gems: [
        { name: "Determination",     support: false, granted: false, level: 21, quality: 20, corrupted: true, chaos: 120,   variant: "21/20c", note: "", trade_url: _TU },
        { name: "Enlighten Support", support: true,  granted: false, level: 4,  quality: 0,  corrupted: true, chaos: 919.6, variant: "4c",     note: "", trade_url: _TU } ] },
    // Boots "Atziri's Step" (unique host) — Flame Dash movement.  19+33+106 = 158
    "20": { chaos: { min: 158,   median: 158,   high: 158 },   confidence: "medium", note: "poe.ninja gem economy: active + 2 supports", method: "skill", trade_url: _TU, sample_size: 3, total_found: 3, kind: "skill", level: 21, quality: 20, corrupted: true, source: "poe.ninja", granted: false, host_slot: "Boots", host_name: "Atziri's Step", host_base: "Slink Boots", host_unique: true, host_inventory_id: "Boots", total_chaos: 158, gems: [
        { name: "Flame Dash",          support: false, granted: false, level: 21, quality: 20, corrupted: true, chaos: 19,  variant: "21/20c", note: "", trade_url: _TU },
        { name: "Second Wind Support", support: true,  granted: false, level: 21, quality: 20, corrupted: true, chaos: 33,  variant: "21/20c", note: "", trade_url: _TU },
        { name: "Arcane Surge Support",support: true,  granted: false, level: 21, quality: 20, corrupted: true, chaos: 106, variant: "21/20c", note: "", trade_url: _TU } ] },
    // Ring "Lost Unity" (unique host) — GRANTED Herald of Agony: null price, excluded from total.
    "25": { chaos: { min: null,  median: null,  high: null },  confidence: "none",   note: "item-granted skill (comes free with the host item)", method: "skill", trade_url: _TU, sample_size: 0, total_found: 0, kind: "skill", level: 30, quality: 0, corrupted: false, source: "poe.ninja", granted: true, host_slot: "Ring", host_name: "Lost Unity", host_base: "Formless Ring", host_unique: true, host_inventory_id: "Ring", total_chaos: null, gems: [
        { name: "Herald of Agony", support: false, granted: true, level: 30, quality: 0, corrupted: false, chaos: null, variant: "", note: "granted by Lost Unity - not counted", trade_url: _TU } ] }
  },
  rares: {
    "1": { status: "priced", name: "Rift Shroud", scope: "base: Vaal Regalia", kind: "rare", scope_q: { type: "Vaal Regalia" }, affixes: [
        { kind: "stat", text: "+112 to maximum Life",    stat_id: "explicit.stat_3299347043", value: 112, searchable: true,  resist: false, priority: "required", reason: "" },
        { kind: "stat", text: "+41% to Fire Resistance", stat_id: "explicit.stat_3372524247", value: 41,  searchable: true,  resist: true,  priority: "required", reason: "" },
        { kind: "stat", text: "+38% to Cold Resistance", stat_id: "explicit.stat_4220027924", value: 38,  searchable: true,  resist: true,  priority: "required", reason: "" },
        { kind: "equip", key: "es", text: "Total Energy Shield", value: 520, searchable: true, resist: false, priority: "required", reason: "" }
      ], pseudo: [
        { kind: "stat", text: "+79% total Elemental Resistance", stat_id: "pseudo.pseudo_total_elemental_resistance", value: 79, searchable: true, resist: true, priority: "required", reason: "" }
      ] },
    "2": { status: "priced", name: "Gauntlets of Malice", scope: "base: Sorcerer Gloves", kind: "rare", scope_q: { type: "Sorcerer Gloves" }, affixes: [
        { kind: "stat", text: "24% increased Attack Speed",           stat_id: "explicit.stat_210067635",  value: 24, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "Adds 12 to 30 Fire Damage to Attacks", stat_id: "explicit.stat_1573130764", value: 12, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "+72 to maximum Life",                  stat_id: "explicit.stat_3299347043", value: 72, searchable: true, resist: false, reason: "" }
      ], pseudo: [] },
    "5": { status: "priced", name: "Empyrean Idol", scope: "base: Amber Amulet", kind: "rare", scope_q: { type: "Amber Amulet" }, affixes: [
        { kind: "stat", text: "+58 to maximum Life",     stat_id: "explicit.stat_3299347043", value: 58, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "+35% to Fire Resistance", stat_id: "explicit.stat_3372524247", value: 35, searchable: true, resist: true,  reason: "" },
        { kind: "stat", text: "24% increased Fire Damage", stat_id: "explicit.stat_3962278098", value: 24, searchable: true, resist: false, reason: "" }
      ], pseudo: [] },
    "7": { status: "priced", name: "Brood Grasp", scope: "base: Vermillion Ring", kind: "rare", scope_q: { type: "Vermillion Ring" }, affixes: [
        { kind: "stat", text: "+33% to Cold Resistance", stat_id: "explicit.stat_4220027924", value: 33, searchable: true, resist: true,  reason: "" },
        { kind: "stat", text: "+58 to maximum Life",     stat_id: "explicit.stat_3299347043", value: 58, searchable: true, resist: false, reason: "" }
      ], pseudo: [] },
    "9": { status: "priced", name: "Corpse Ward", scope: "base: Titanium Spirit Shield", kind: "rare", scope_q: { type: "Titanium Spirit Shield" }, affixes: [
        { kind: "stat",  text: "+84 to maximum Life",     stat_id: "explicit.stat_3299347043", value: 84, searchable: true, resist: false, reason: "" },
        { kind: "stat",  text: "+45% to Fire Resistance", stat_id: "explicit.stat_3372524247", value: 45, searchable: true, resist: true,  reason: "" },
        { kind: "equip", key: "es", text: "Total Energy Shield", value: 320, searchable: true, resist: false, reason: "" }
      ], pseudo: [] },
    "12": { status: "priced", name: "Hale Fettle", scope: "category: Jewel", kind: "rare", scope_q: {}, affixes: [
        { kind: "stat", text: "12% increased maximum Life", stat_id: "explicit.stat_3299347043", value: 12, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "9% increased Cast Speed",    stat_id: "explicit.stat_2891184298", value: 9,  searchable: true, resist: false, reason: "" }
      ], pseudo: [] }
  }
};
