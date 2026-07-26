"""Render a BuildEstimate as a readable terminal table, JSON, or HTML."""
import html as _html
import json
import math
from typing import List, Optional

from .currency import CurrencyConverter
from .models import BuildMeta, PriceResult

# (group order for the terminal report; web has its own copy)
_GROUP_ORDER = ["equipment", "flask", "jewel", "gem"]
_GROUP_TITLE = {"equipment": "Equipment", "flask": "Flasks",
                "jewel": "Jewels", "gem": "Gems"}


def _row_price(conv: CurrencyConverter, v: Optional[float]) -> str:
    return conv.fmt(v) if v is not None else "-"


def _sum_tier(results: List[PriceResult], attr: str) -> float:
    total = 0.0
    for r in results:
        v = getattr(r.tier, attr)
        if v is not None:
            total += v * max(1, r.item.count)
    return total


def render_text(meta: BuildMeta, results: List[PriceResult],
                conv: CurrencyConverter) -> str:
    div = conv.divine_rate()
    by_group = {g: [] for g in _GROUP_ORDER}
    for r in results:
        by_group.setdefault(r.item.group, []).append(r)

    # Pre-render every cell so column widths fit the actual content (price strings grow
    # to e.g. "166,758 div (22,512,345 ex)" once a divine rate exists).
    NAME_CAP = 44
    rendered = []  # (label, min, med, high, conf, note)
    for r in results:
        label = r.item.display_name
        if r.item.count > 1:
            label = f"{label}  x{r.item.count}"
        if len(label) > NAME_CAP:
            label = label[:NAME_CAP - 2] + ".."
        rendered.append((label,
                         _row_price(conv, r.tier.minimum),
                         _row_price(conv, r.tier.median),
                         _row_price(conv, r.tier.high),
                         r.confidence, r.note))
    name_w = min(max([len("Item")] + [len(x[0]) for x in rendered]), NAME_CAP)
    cmin = max([len("min")] + [len(x[1]) for x in rendered])
    cmed = max([len("median")] + [len(x[2]) for x in rendered])
    chigh = max([len("high")] + [len(x[3]) for x in rendered])
    rmap = {id(r): rendered[i] for i, r in enumerate(results)}

    hdr = (f" {'Item':<{name_w}}  {'min':>{cmin}}  {'median':>{cmed}}  "
           f"{'high':>{chigh}}  conf")
    width = max(len(hdr), 78)

    lines: List[str] = []
    lines.append("=" * width)
    lines.append(f" {meta.character}  -  {meta.char_class} (level {meta.level})")
    lines.append(f" League: {meta.league}"
                 + (f"   |   1 divine = {div:,.0f} chaos" if div else ""))
    if meta.source_url:
        lines.append(f" Source: {meta.source_url}")
    lines.append("=" * width)

    for g in _GROUP_ORDER:
        rs = by_group.get(g)
        if not rs:
            continue
        lines.append("")
        lines.append(_GROUP_TITLE.get(g, g.title()))
        lines.append("-" * width)
        lines.append(hdr)
        for r in rs:
            label, mn, md, hi, conf, note = rmap[id(r)]
            lines.append(f" {label:<{name_w}}  {mn:>{cmin}}  {md:>{cmed}}  "
                         f"{hi:>{chigh}}  {conf}")
            if note:
                lines.append(f"    -> {note}")

    lines.append("")
    lines.append("=" * width)
    tmin, tmed, thigh = (_sum_tier(results, "minimum"),
                         _sum_tier(results, "median"),
                         _sum_tier(results, "high"))
    lines.append(" TOTAL ESTIMATED BUILD COST")
    lines.append(f"   Minimum (budget) : {conv.fmt(tmin)}")
    lines.append(f"   Median  (typical): {conv.fmt(tmed)}")
    lines.append(f"   High    (~90th pct): {conv.fmt(thigh)}")
    unpriced = [r for r in results if r.tier.median is None]
    if unpriced:
        lines.append("")
        lines.append(f" Note: {len(unpriced)} item(s) could not be priced "
                     "(see per-item notes above); totals exclude them.")
    lines.append("=" * width)
    return "\n".join(lines)


def _finite(x):
    """Coerce non-finite floats (inf/nan) to None so the JSON is RFC-valid."""
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def build_payload(meta: BuildMeta, results: List[PriceResult],
                  conv: CurrencyConverter) -> dict:
    """Structured, JSON-serialisable result (per-item tiers + totals). Used by the web
    UI to render an interactive table and recompute totals client-side."""
    def tier(r):
        return {"min": _finite(r.tier.minimum), "median": _finite(r.tier.median),
                "high": _finite(r.tier.high)}

    return {
        "character": meta.character, "class": meta.char_class, "level": meta.level,
        "league": meta.league, "source_url": meta.source_url,
        "divine_to_chaos": _finite(conv.divine_rate()), "currency_unit": "chaos",
        "items": [{
            "name": r.item.display_name, "group": r.item.group,
            "category": r.item.category, "rarity": r.item.rarity,
            "slot": r.item.slot, "count": r.item.count,
            "method": r.method, "confidence": r.confidence,
            "sample_size": r.sample_size, "total_found": r.total_found,
            "note": r.note, "trade_url": r.trade_url,
            "chaos": tier(r),
        } for r in results],
        "totals_chaos": {
            "min": _finite(_sum_tier(results, "minimum")),
            "median": _finite(_sum_tier(results, "median")),
            "high": _finite(_sum_tier(results, "high")),
        },
    }


def render_json(meta: BuildMeta, results: List[PriceResult],
                conv: CurrencyConverter) -> str:
    return json.dumps(build_payload(meta, results, conv), indent=2, allow_nan=False)


def render_html(meta: BuildMeta, results: List[PriceResult],
                conv: CurrencyConverter) -> str:
    """HTML fragment (the results panel) for the web UI."""
    e = _html.escape

    def cell(v):
        return e(_row_price(conv, v))

    by_group = {g: [] for g in _GROUP_ORDER}
    for r in results:
        by_group.setdefault(r.item.group, []).append(r)

    out = []
    div = conv.divine_rate()
    out.append('<div class="meta">')
    out.append(f'<h2>{e(meta.character)} <span class="sub">{e(meta.char_class)} '
               f'&middot; level {meta.level}</span></h2>')
    rate_txt = f' &nbsp;|&nbsp; 1 divine = {div:,.0f} chaos' if div else ''
    out.append(f'<div class="sub">League: {e(meta.league)}{rate_txt}</div>')
    out.append('</div>')

    for g in _GROUP_ORDER:
        rs = by_group.get(g)
        if not rs:
            continue
        out.append(f'<h3>{e(_GROUP_TITLE.get(g, g.title()))}</h3>')
        out.append('<table><thead><tr><th>Item</th><th>min</th><th>median</th>'
                   '<th>high</th><th>conf</th></tr></thead><tbody>')
        for r in rs:
            name = e(r.item.display_name) + (f' &times;{r.item.count}'
                                             if r.item.count > 1 else '')
            if r.trade_url:
                name = f'<a href="{e(r.trade_url)}" target="_blank" rel="noopener">{name}</a>'
            note = f'<div class="note">{e(r.note)}</div>' if r.note else ''
            out.append(
                f'<tr><td>{name}{note}</td>'
                f'<td class="num">{cell(r.tier.minimum)}</td>'
                f'<td class="num">{cell(r.tier.median)}</td>'
                f'<td class="num">{cell(r.tier.high)}</td>'
                f'<td><span class="badge {e(r.confidence)}">{e(r.confidence)}</span></td></tr>')
        out.append('</tbody></table>')

    tmin, tmed, thigh = (_sum_tier(results, "minimum"),
                         _sum_tier(results, "median"), _sum_tier(results, "high"))
    out.append('<div class="totals">')
    out.append('<h3>Total estimated build cost</h3>')
    out.append('<div class="totrow"><span>Minimum (budget)</span>'
               f'<b>{e(conv.fmt(tmin))}</b></div>')
    out.append('<div class="totrow"><span>Median (typical)</span>'
               f'<b>{e(conv.fmt(tmed))}</b></div>')
    out.append('<div class="totrow"><span>High (~90th pct)</span>'
               f'<b>{e(conv.fmt(thigh))}</b></div>')
    unpriced = [r for r in results if r.tier.median is None]
    if unpriced:
        out.append(f'<div class="warn">{len(unpriced)} item(s) could not be priced '
                   '(see notes); totals exclude them.</div>')
    out.append('</div>')
    return "\n".join(out)
