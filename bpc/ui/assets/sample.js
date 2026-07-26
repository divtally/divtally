/* A realistic, fully-priced job snapshot for demos + headless verification.
 * Lets any UI version render a complete build (totals, exclude toggles, advanced
 * picker, currency icons, PoB copy) with NO backend / no trade calls.
 *   bpc.loadMock(window.BPC_SAMPLE)
 */
// real web.poecdn.com icon URLs (poe.ninja build data carries these per item/gem)
var _IC = {
  helm:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9IZWxtZXRzL1VuaXF1ZXMvVGhlQmxhY2tDcmVzdCIsInciOjIsImgiOjIsInNjYWxlIjoxLCJyZWFsbSI6InBvZTIifV0/0d9e626b9a/TheBlackCrest.png",
  body:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9Cb2R5QXJtb3Vycy9CYXNldHlwZXMvQm9keURleEludDAyIiwidyI6MiwiaCI6Mywic2NhbGUiOjEsInJlYWxtIjoicG9lMiJ9XQ/31d5df47b6/BodyDexInt02.png",
  gloves:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9HbG92ZXMvQmFzZXR5cGVzL0dsb3Zlc0ludFN0cjAyIiwidyI6MiwiaCI6Miwic2NhbGUiOjEsInJlYWxtIjoicG9lMiJ9XQ/06defd5790/GlovesIntStr02.png",
  boots:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9Cb290cy9CYXNldHlwZXMvQm9vdHNEZXhJbnQwMyIsInciOjIsImgiOjIsInNjYWxlIjoxLCJyZWFsbSI6InBvZTIifV0/f36ea8ace2/BootsDexInt03.png",
  belt:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQmVsdHMvVW5pcXVlcy9NYWdlYmxvb2QiLCJ3IjoyLCJoIjoxLCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/79ac3ce7d3/Mageblood.png",
  amulet:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQW11bGV0cy9CYXNldHlwZXMvR29sZEFtdWxldCIsInciOjEsImgiOjEsInNjYWxlIjoxLCJyZWFsbSI6InBvZTIifV0/7da5b5dc6e/GoldAmulet.png",
  ring:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvUmluZ3MvVW5pcXVlcy9UaGVUYW1pbmciLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/c266aa1e19/TheTaming.png",
  ring2:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvUmluZ3MvQmFzZXR5cGVzL0JyZWFjaFJpbmciLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/cffe574bd0/BreachRing.png",
  weapon:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvV2VhcG9ucy9PbmVIYW5kV2VhcG9ucy9PbmVIYW5kU3BlYXJzL1VuaXF1ZXMvU2t5c2xpdmVyIiwidyI6MSwiaCI6NCwic2NhbGUiOjEsInJlYWxtIjoicG9lMiJ9XQ/b495502d39/Skysliver.png",
  weapon2:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvV2VhcG9ucy9PbmVIYW5kV2VhcG9ucy9PbmVIYW5kU3BlYXJzL1VuaXF1ZXMvVGhlT3JkYWluZWQiLCJ3IjoxLCJoIjo0LCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/6c52dd93b7/TheOrdained.png",
  offhand:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvV2VhcG9ucy9PbmVIYW5kV2VhcG9ucy9TY2VwdGVycy9VbmlxdWVzL0d1aWRpbmdQYWxtRmlyZSIsInciOjIsImgiOjMsInNjYWxlIjoxLCJyZWFsbSI6InBvZTIifV0/b0f8b93adf/GuidingPalmFire.png",
  flask:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ2hhcm1zL0Jhc2V0eXBlcy9UaGF3aW5nQ2hhcm0iLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/d9184b853a/ThawingCharm.png",
  jewel:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvSmV3ZWxzL1VuaXF1ZXMvQXBvc3RhdGVzSGVhcnQiLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/cc73484d32/ApostatesHeart.png",
  rune:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvUnVuZXMvRmlyZVJ1bmVUaWVyMiIsInciOjEsImgiOjEsInNjYWxlIjoxLCJyZWFsbSI6InBvZTIifV0/312239e491/FireRuneTier2.png",
  gem:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9OZXcvQmxhbmtHZW0iLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/250ec3ed08/BlankGem.png",
  lineage:"https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvR2Vtcy9OZXcvTmV3U3VwcG9ydC9MaW5lYWdlL09scm90aHNDb252aWN0aW9uIiwidyI6MSwiaCI6MSwic2NhbGUiOjEsInJlYWxtIjoicG9lMiJ9XQ/5b2fd28947/OlrothsConviction.png"
};
window.BPC_SAMPLE = {
  state: "done",
  advanced: false,
  searches: 23,
  meta: {
    character: "DorkSlayer", "class": "Acolyte of Chayula", level: 96,
    league: "Rise of the Abyssal", divine_to_exalted: 412, status: "online",
    exalted_img: "https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lBZGRNb2RUb1JhcmUiLCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/ad7c366789/CurrencyAddModToRare.png",
    divine_img: "https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lNb2RWYWx1ZXMiLCJzY2FsZSI6MSwicmVhbG0iOiJwb2UyIn1d/2986e220b3/CurrencyModValues.png",
    pob_code: "eNrtWVtT4zgWfu-q_g8u9rkxsmzZTld6tgRJN8wEyAS6Z-aJUmwlEThyypIDzK_fI8m5kQ7p7Z6anWGqJ7Etn3OdyzofuYwQ8evDS2BTLLPwQbe3t4PgkSnIRRG8YBhFQRTHQRQHQRgGYRRGfhT5fhAGYRiEvh_5fuD7vu_5vud5XV3X9bquNzc3Nzc3R0dHR0dHe3t7e3t7BwcHBwcHh4eHh4eHR0dHR0fHx8fHx8cnJycnJyenp6enp2dnZ2dn5-fn5xcXFxcXl5eXl1dXV9fX19c3Nzc3t7e3d3d3d_f39w8PDw-Pj4-PT09PT8_Pzy8vL6-vr29vb-_v7x8fH5-fX19f39_f39_e3t7e3t7e3t_f39_e3t7e3t7e3t_e3t7e3t7e3t_e3t7e3t7e3t8Q",
    source_url: "https://poe.ninja/poe2/builds/rise-of-the-abyssal/character/DemoAccount/DorkSlayer"
  },
  items: [
    { index: 0,  name: "Heatshiver",          group: "equipment", category: "unique", slot: "Helmet",      count: 1, rarity: "Unique", icon: _IC.helm,
      mods: { implicit: ["+25 to maximum Mana"], explicit: ["Freezes Enemies as though dealing 150% more Damage", "+38% to Cold Resistance", "100% increased Cold Damage if you've Shattered an Enemy Recently"], rune: [] } },
    { index: 1,  name: "Dread Aegis",         group: "equipment", category: "rare",   slot: "Body Armour", count: 1, rarity: "Rare", icon: _IC.body,
      mods: { implicit: [], explicit: ["+118 to maximum Life", "+41% to Fire Resistance", "+35% to Cold Resistance", "+28 to Spirit", "524 to maximum Energy Shield"], rune: ["+12% to Chaos Resistance"] } },
    { index: 2,  name: "Phoenix Grip",        group: "equipment", category: "rare",   slot: "Gloves",      count: 1, rarity: "Rare", icon: _IC.gloves,
      mods: { implicit: [], explicit: ["24% increased Attack Speed", "Adds 12 to 30 Fire damage to Attacks", "+62 to maximum Life"], rune: [] } },
    { index: 3,  name: "Seven-League Step",   group: "equipment", category: "unique", slot: "Boots",       count: 1, rarity: "Unique", icon: _IC.boots,
      mods: { implicit: [], explicit: ["50% increased Movement Speed"], rune: [] } },
    { index: 4,  name: "Belt of the Deceiver",group: "equipment", category: "unique", slot: "Belt",        count: 1, rarity: "Unique", icon: _IC.belt,
      mods: { implicit: ["+35 to maximum Life"], explicit: ["You take 30% reduced Extra Damage from Critical Hits", "+25% to Fire Resistance", "Nearby Enemies are Intimidated"], rune: [] } },
    { index: 5,  name: "Hate Collar",         group: "equipment", category: "rare",   slot: "Amulet",      count: 1, rarity: "Rare", icon: _IC.amulet,
      mods: { implicit: ["+12% to all Elemental Resistances"], explicit: ["+1 to Level of all Chaos Skills", "+38% to Chaos Resistance", "+25% to Critical Damage Bonus"], rune: [] } },
    { index: 6,  name: "Ming's Heart",        group: "equipment", category: "unique", slot: "Ring",        count: 1, rarity: "Unique", icon: _IC.ring },
    { index: 7,  name: "Brood Finger",        group: "equipment", category: "rare",   slot: "Ring",        count: 1, rarity: "Rare", icon: _IC.ring2,
      mods: { implicit: ["+18% to Lightning Resistance"], explicit: ["+33% to Cold Resistance", "+55 to maximum Mana"], rune: [] } },
    { index: 8,  name: "The Searing Touch",   group: "equipment", category: "unique", slot: "Weapon",      count: 1, rarity: "Unique", icon: _IC.weapon },
    { index: 9,  name: "Maelström Ward",      group: "equipment", category: "rare",   slot: "Off-hand",    count: 1, rarity: "Rare", icon: _IC.offhand },
    { index: 16, name: "Voltaxic Obliterator", group: "equipment", category: "unique", slot: "Weapon (swap)",    count: 1, rarity: "Unique", icon: _IC.weapon2 },
    { index: 17, name: "Phoenix Barb, Spike Quiver", group: "equipment", category: "rare", slot: "Off-hand (swap)", count: 1, rarity: "Rare", icon: _IC.offhand },
    { index: 10, name: "Ultimate Life Flask", group: "flask",     category: "magic",  slot: "Flask",       count: 1, rarity: "Magic", icon: _IC.flask,
      mods: { implicit: [], explicit: ["Recovers 1870 Life over 4.00 seconds", "25% increased Amount Recovered"], rune: [] } },
    { index: 11, name: "Ultimate Mana Flask", group: "flask",     category: "magic",  slot: "Flask",       count: 1, rarity: "Magic", icon: _IC.flask },
    { index: 21, name: "Golden Charm",        group: "flask",     category: "magic",  slot: "Charm",       count: 1, rarity: "Magic", icon: _IC.flask,
      mods: { implicit: [], explicit: ["20% increased Rarity of Items found during effect"], rune: [] } },
    { index: 22, name: "Thawing Charm",       group: "flask",     category: "magic",  slot: "Charm",       count: 1, rarity: "Magic", icon: _IC.flask },
    { index: 12, name: "Glowing Cobalt Jewel",group: "jewel",     category: "rare",   slot: "Jewel",       count: 1, rarity: "Rare", icon: _IC.jewel,
      mods: { implicit: [], explicit: ["12% increased maximum Life", "9% increased Cast Speed"], rune: [] } },
    { index: 13, name: "Grand Spectrum",      group: "jewel",     category: "unique", slot: "Jewel",       count: 1, rarity: "Unique", icon: _IC.jewel },
    { index: 14, name: "Iron Rune",           group: "rune",      category: "rune",   slot: "Rune",        count: 3, rarity: "Currency", icon: _IC.rune },
    { index: 15, name: "Desert Soul Core",    group: "rune",      category: "rune",   slot: "Rune",        count: 1, rarity: "Currency", icon: _IC.rune },
    { index: 18, name: "Barrage",        group: "gem", category: "gem", slot: "", count: 1, rarity: "Gem", level: 19, sockets: 5, icon: _IC.gem,
      supports: [{name:"Cooldown Recovery II",lineage:false,icon:_IC.gem},{name:"Rapid Casting II",lineage:false,icon:_IC.gem},{name:"Heightened Charges",lineage:false,icon:_IC.gem},{name:"Olroth's Conviction",lineage:true,icon:_IC.lineage},{name:"Efficiency II",lineage:false,icon:_IC.gem}] },
    { index: 19, name: "Herald of Ice",  group: "gem", category: "gem", slot: "", count: 1, rarity: "Gem", level: 19, sockets: 5, icon: _IC.gem,
      supports: [{name:"Elemental Armament II",lineage:false,icon:_IC.gem},{name:"Magnified Area II",lineage:false,icon:_IC.gem},{name:"Elemental Focus",lineage:false,icon:_IC.gem},{name:"Longshot II",lineage:false,icon:_IC.gem},{name:"Ambush",lineage:false,icon:_IC.gem}] },
    { index: 20, name: "Whirling Slash", group: "gem", category: "gem", slot: "", count: 1, rarity: "Gem", level: 1, sockets: 3, icon: _IC.gem, granted: true,
      supports: [{name:"Rage III",lineage:false,icon:_IC.gem},{name:"Rigwald's Ferocity",lineage:true,icon:_IC.lineage},{name:"Blazing Critical",lineage:false,icon:_IC.gem}] }
  ],
  priced: {
    "0":  { exalted: { min: 150, median: 205, high: 340 },  confidence: "high",   note: "",                                              method: "unique",      trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 28, total_found: 412 },
    "1":  { exalted: { min: 30,  median: 47,  high: 95 },   confidence: "medium", note: "matched 4 affixes + total ES",                  method: "rare_default",trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 19, total_found: 240 },
    "2":  { exalted: { min: 5,   median: 9,   high: 22 },   confidence: "medium", note: "",                                              method: "rare_default",trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 22, total_found: 600 },
    "3":  { exalted: { min: 3,   median: 6,   high: 14 },   confidence: "high",   note: "",                                              method: "unique",      trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 30, total_found: 900 },
    "4":  { exalted: { min: 900, median: 1240,high: 2100 }, confidence: "high",   note: "version unique - priced exact variant",         method: "unique",      trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 12, total_found: 70 },
    "5":  { exalted: { min: 40,  median: 66,  high: 130 },  confidence: "medium", note: "",                                              method: "rare_default",trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 17, total_found: 210 },
    "6":  { exalted: { min: 18,  median: 28,  high: 52 },   confidence: "high",   note: "",                                              method: "unique",      trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 26, total_found: 380 },
    "7":  { exalted: { min: 7,   median: 13,  high: 31 },   confidence: "low",    note: "few listings matched",                          method: "rare_default",trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 3,  total_found: 3 },
    "8":  { exalted: { min: 620, median: 815, high: 1500 }, confidence: "high",   note: "",                                              method: "unique",      trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 24, total_found: 150 },
    "9":  { exalted: { min: null,median: null,high: null }, confidence: "none",   note: "no listing matches your affixes (uniquely rolled) - see trade link", method: "rare_default", trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 0, total_found: 0 },
    "16": { exalted: { min: 210, median: 305, high: 540 },  confidence: "high",   note: "",                                              method: "unique",      trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 18, total_found: 95 },
    "17": { exalted: { min: 8,   median: 16,  high: 38 },   confidence: "medium", note: "",                                              method: "rare_default",trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 14, total_found: 130 },
    "10": { exalted: { min: 1,   median: 2,   high: 4 },    confidence: "medium", note: "",                                              method: "magic",       trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 20, total_found: 999 },
    "11": { exalted: { min: 0.5, median: 1,   high: 3 },    confidence: "medium", note: "",                                              method: "magic",       trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 20, total_found: 999 },
    "21": { exalted: { min: 2,   median: 4,   high: 9 },    confidence: "low",    note: "",                                              method: "magic",       trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 12, total_found: 300 },
    "22": { exalted: { min: 1,   median: 2,   high: 5 },    confidence: "low",    note: "",                                              method: "magic",       trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 12, total_found: 300 },
    "12": { exalted: { min: 3,   median: 5,   high: 12 },   confidence: "low",    note: "",                                              method: "rare_default",trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 8,  total_found: 40 },
    "13": { exalted: { min: 60,  median: 92,  high: 170 },  confidence: "high",   note: "",                                              method: "unique",      trade_url: "https://www.pathofexile.com/trade2/search/poe2/x", sample_size: 21, total_found: 110 },
    "14": { exalted: { min: 0.3, median: 0.5, high: 1 },    confidence: "high",   note: "bulk exchange",                                 method: "rune",        trade_url: "", sample_size: 0, total_found: 0 },
    "15": { exalted: { min: 2,   median: 4,   high: 8 },    confidence: "high",   note: "bulk exchange",                                 method: "rune",        trade_url: "", sample_size: 0, total_found: 0 },
    "18": { exalted: { min: 1959, median: 1959, high: 1959 }, confidence: "medium", note: "uncut (poe.ninja): uncut Lv19 + 5 sockets + 1 lineage", method: "skill", trade_url: "https://www.pathofexile.com/trade2/search/poe2/x?q=demo", sample_size: 1, total_found: 1, kind: "skill", source: "poe.ninja", level: 19, sockets: 5, uncut: 80, uncut_total: 1959, cut: null, cut_total: null, lineage: [{ name: "Olroth's Conviction", exalted: { min: 1879, median: 1879, high: 1879 }, trade_url: "https://www.pathofexile.com/trade2/search/poe2/x?q=demo" }] },
    "19": { exalted: { min: 80, median: 80, high: 80 },       confidence: "medium", note: "uncut (poe.ninja): uncut Lv19 + 5 sockets",            method: "skill", trade_url: "https://www.pathofexile.com/trade2/search/poe2/x?q=demo", sample_size: 1, total_found: 1, kind: "skill", source: "poe.ninja", level: 19, sockets: 5, uncut: 80, uncut_total: 80, cut: null, cut_total: null, lineage: [] },
    "20": { exalted: { min: 11092, median: 11092, high: 11092 }, confidence: "medium", note: "uncut (poe.ninja): uncut Lv1 + 3 sockets + 1 lineage", method: "skill", trade_url: "https://www.pathofexile.com/trade2/search/poe2/x?q=demo", sample_size: 1, total_found: 1, kind: "skill", source: "poe.ninja", level: 1, sockets: 3, uncut: 24, uncut_total: 11092, cut: null, cut_total: null, lineage: [{ name: "Rigwald's Ferocity", exalted: { min: 11068, median: 11068, high: 11068 }, trade_url: "https://www.pathofexile.com/trade2/search/poe2/x?q=demo" }] }
  },
  rares: {
    "1": { status: "priced", name: "Dread Aegis", scope: "base: Advanced Vaal Regalia", scope_q: { type: "Advanced Vaal Regalia" }, affixes: [
        { kind: "stat", text: "+118 to maximum Life",        stat_id: "explicit.stat_3299347043", value: 118, searchable: true,  resist: false, priority: "required", reason: "" },
        { kind: "stat", text: "+41% to Fire Resistance",     stat_id: "explicit.stat_3372524247", value: 41,  searchable: true,  resist: true,  priority: "required", reason: "" },
        { kind: "stat", text: "+35% to Cold Resistance",     stat_id: "explicit.stat_4220027924", value: 35,  searchable: true,  resist: true,  priority: "required", reason: "" },
        { kind: "stat", text: "+28 to Spirit",               stat_id: null,                       value: 28,  searchable: false, resist: false, priority: "skip", reason: "no trade filter matches this mod" },
        { kind: "stat", text: "21% reduced Attribute Requirements", stat_id: "explicit.stat_3639275092", value: -21, searchable: true, resist: false, negated: true, priority: "notimp", reason: "" },
        { kind: "equip", key: "es", text: "Total Energy Shield", value: 524, searchable: true, resist: false, priority: "required", reason: "" }
      ], pseudo: [
        { kind: "stat", text: "+76% total Elemental Resistance", stat_id: "pseudo.pseudo_total_elemental_resistance", value: 76, searchable: true, resist: true, priority: "required", reason: "" }
      ] },
    "2": { status: "priced", name: "Phoenix Grip", scope: "base: Gripped Gloves", affixes: [
        { kind: "stat", text: "+24% increased Attack Speed", stat_id: "explicit.stat_210067635", value: 24, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "Adds 12 to 30 Fire damage to Attacks", stat_id: "explicit.stat_1573130764", value: 12, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "+62 to maximum Life",         stat_id: "explicit.stat_3299347043", value: 62, searchable: true, resist: false, reason: "" }
      ], pseudo: [] },
    "5": { status: "priced", name: "Hate Collar", scope: "base: Stellar Amulet", affixes: [
        { kind: "stat", text: "+1 to Level of all Chaos Skills", stat_id: "explicit.stat_2018035480", value: 1, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "+38% to Chaos Resistance",    stat_id: "explicit.stat_2923486259", value: 38, searchable: true, resist: true, reason: "" },
        { kind: "stat", text: "+25% to Critical Damage Bonus", stat_id: "explicit.stat_3556824919", value: 25, searchable: true, resist: false, reason: "" }
      ], pseudo: [
        { kind: "stat", text: "+38% total to Chaos Resistance", stat_id: "pseudo.pseudo_total_chaos_resistance", value: 38, searchable: true, resist: true, reason: "" }
      ] },
    "7": { status: "priced", name: "Brood Finger", scope: "base: Sapphire Ring", affixes: [
        { kind: "stat", text: "+33% to Cold Resistance",     stat_id: "explicit.stat_4220027924", value: 33, searchable: true, resist: true, reason: "" },
        { kind: "stat", text: "+55 to maximum Mana",         stat_id: "explicit.stat_1050105434", value: 55, searchable: true, resist: false, reason: "" }
      ], pseudo: [] },
    "9": { status: "priced", name: "Maelström Ward", scope: "category", affixes: [
        { kind: "stat", text: "+#% increased Spell Damage",  stat_id: "explicit.stat_2974417149", value: 41, searchable: true, resist: false, reason: "" },
        { kind: "equip", key: "es", text: "Total Energy Shield", value: 180, searchable: true, resist: false, reason: "" }
      ], pseudo: [] },
    "12": { status: "priced", name: "Glowing Cobalt Jewel", scope: "category", affixes: [
        { kind: "stat", text: "+12% increased maximum Life", stat_id: "explicit.stat_3299347043", value: 12, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "+9% increased Cast Speed",    stat_id: "explicit.stat_2891184298", value: 9,  searchable: true, resist: false, reason: "" }
      ], pseudo: [] },
    "17": { status: "priced", name: "Phoenix Barb, Spike Quiver", scope: "base: Spike Quiver", affixes: [
        { kind: "stat", text: "Adds 18 to 34 Fire damage to Attacks", stat_id: "explicit.stat_1573130764", value: 18, searchable: true, resist: false, reason: "" },
        { kind: "stat", text: "+29% to Fire Resistance",    stat_id: "explicit.stat_3372524247", value: 29, searchable: true, resist: true, reason: "" }
      ], pseudo: [] },
    "8": { status: "priced", name: "The Searing Touch", scope: "unique: The Searing Touch", kind: "unique", scope_q: { name: "The Searing Touch", type: "Carved Wand" }, affixes: [
        { kind: "stat", text: "+2 to Level of all Fire Skills", stat_id: "explicit.stat_599749213", value: 2, searchable: true, resist: false, prefer: true,  priority: "required", reason: "" },
        { kind: "stat", text: "38% increased Spell Damage",     stat_id: "explicit.stat_2974417149", value: 38, searchable: true, resist: false, prefer: false, priority: "skip", reason: "" },
        { kind: "stat", text: "+15% to Fire Resistance",        stat_id: "explicit.stat_3372524247", value: 15, searchable: true, resist: true,  prefer: false, priority: "skip", reason: "" }
      ], pseudo: [] }
  }
};
