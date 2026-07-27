"""Convert trade listing prices to Chaos Orbs, and provide the Divine display rate.

ADAPTED from bpc/currency.py: the public build is economy-ONLY. The parent kept a trade
`exchange` fallback in `_lookup` for currencies poe.ninja doesn't list; that would call
pathofexile.com, which is forbidden here (D-0008), so it is DELETED. A currency poe.ninja
doesn't price simply returns None (unpriceable) rather than triggering a trade call.
"""
from typing import Dict, Optional

# PoE1 base currency.
_BASE = "chaos"


class CurrencyConverter:
    def __init__(self, economy=None):
        self.economy = economy       # a poeninja.PoeNinjaEconomy (chaos rates), or None
        self._rates: Dict[str, Optional[float]] = {_BASE: 1.0}

    def rate(self, currency: str) -> Optional[float]:
        """Chaos Orbs per 1 unit of `currency` (None if poe.ninja can't price it)."""
        currency = (currency or "").lower()
        if currency in self._rates:
            return self._rates[currency]
        rate = self._lookup(currency)
        self._rates[currency] = rate
        return rate

    def _lookup(self, currency: str) -> Optional[float]:
        # Sole source: poe.ninja Currency economy (line.primaryValue is chaos directly).
        # NO trade exchange fallback (would call pathofexile.com).
        if self.economy is not None:
            try:
                ex = self.economy.chaos_by_id("Currency", currency)
            except Exception:
                ex = None
            if ex is not None and ex > 0:
                return ex
        return None

    def to_chaos(self, amount: float, currency: str) -> Optional[float]:
        r = self.rate(currency)
        return amount * r if r is not None else None

    # ---- display ---------------------------------------------------------
    def divine_rate(self) -> Optional[float]:
        """Chaos per 1 Divine Orb (the Divine display column)."""
        if self.economy is not None:
            try:
                dr = self.economy.chaos_by_id("Currency", "divine")
            except Exception:
                dr = None
            if dr is not None and dr > 0:
                return dr
        return self.rate("divine")

    def fmt(self, chaos: Optional[float]) -> str:
        """Human-friendly amount, e.g. '4.1 div (420 chaos)' or '35 chaos'."""
        if chaos is None:
            return "n/a"
        c = chaos
        div_rate = self.divine_rate()
        c_str = f"{c:,.0f} chaos" if c >= 10 else f"{c:,.1f} chaos"
        if div_rate and c >= div_rate * 0.5:
            div = c / div_rate
            div_str = f"{div:,.1f} div" if div < 100 else f"{div:,.0f} div"
            return f"{div_str} ({c_str})"
        return c_str
