"""Small helpers: rich-text stripping, number parsing, robust distribution stats.

VENDORED VERBATIM from bpc/util.py (pure functions, no I/O, no trade). Keep in sync.
"""
import re
from typing import List, Optional, Sequence

# PoE rich text markup looks like "[Wind|Wind Skills]" or "[Resistances]".
# The display text is the part after the pipe, or the whole token if there is no pipe.
_RICH = re.compile(r"\[([^\[\]]+?)\]")


def strip_rich(text: str) -> str:
    """Convert PoE rich-text markup to plain display text.

    "[Wind|Wind Skills] deal more damage" -> "Wind Skills deal more damage"
    "+10% to all [Resistances]"           -> "+10% to all Resistances"
    """
    def repl(m: "re.Match[str]") -> str:
        inner = m.group(1)
        return inner.split("|", 1)[1] if "|" in inner else inner

    return _RICH.sub(repl, text)


# Numbers in mod text, including negatives, decimals and ranges like "13 to 16".
_NUM = re.compile(r"[+-]?\d+(?:\.\d+)?")


def mod_to_pattern(text: str) -> str:
    """Normalise a mod line to the trade "stat text" shape (numbers -> '#').

    "+71 to Evasion Rating"        -> "# to Evasion Rating"
    "Adds 13 to 16 Fire Damage"    -> "Adds # to # Fire Damage"
    Trailing/leading whitespace and rich markup are removed first.
    """
    t = strip_rich(text).strip()
    t = _NUM.sub("#", t)
    # The trade stats dictionary stores many flat mods as "+# to ..." while an item
    # line like "+30 to ..." normalises to "# to ..." (the sign is consumed with the
    # number). Drop the residual leading "+" before "#" on BOTH sides so they agree.
    t = t.replace("+#", "#")
    # Trade stat texts are written with the value 1 ("... 1 second later"), so the noun
    # is singular; an item rolled to e.g. 4.1 reads "seconds". Unify "# seconds" -> "#
    # second" on both sides so duration mods match (applied symmetrically, so no collision).
    t = re.sub(r"# seconds\b", "# second", t)
    # collapse internal whitespace / newlines so multi-line mods compare cleanly
    t = re.sub(r"\s+", " ", t)
    return t


def first_number(text: str) -> Optional[float]:
    """Return the first numeric value found in a mod line (for min thresholds)."""
    m = _NUM.search(strip_rich(text))
    return float(m.group()) if m else None


def numbers(text: str) -> List[float]:
    return [float(x) for x in _NUM.findall(strip_rich(text))]


def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    """Linear-interpolation percentile (pct in 0..100). Returns None for empty input."""
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    frac = k - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def median(values: Sequence[float]) -> Optional[float]:
    return percentile(values, 50)


def trim_outliers(values: Sequence[float], lo_mult: float = 0.30, hi_mult: float = 6.0
                  ) -> List[float]:
    """Drop scam / typo listings relative to the median.

    Trade listings frequently include bait prices far below market (to surface a
    whisper) and a few absurd high listings. We keep prices within
    [lo_mult, hi_mult] * median. Median is robust enough to anchor this.
    """
    vals = sorted(v for v in values if v is not None and v > 0)
    if not vals:
        return []
    med = median(vals)
    if not med:
        return vals
    kept = [v for v in vals if lo_mult * med <= v <= hi_mult * med]
    # never return empty just because everything was spread out
    return kept if kept else vals
