"""Convert trade listing prices (divine / chaos / exalted / mirror / ...) to a single
canonical unit so item costs can be summed and compared.

Canonical unit = Chaos Orb (PoE1's trade index standard). We also surface a Divine-Orb
figure for readability because expensive builds are quoted in divine.

Rates come primarily from poe.ninja's Currency economy (one cheap GET, no trade API ->
no ban risk): a currency line's `primaryValue` is already its price in chaos. The trade
`exchange` endpoint is only a fallback for a currency poe.ninja doesn't list.
"""
from typing import Dict, List, Optional

from . import cache, util
from .trade import TradeClient

# PoE1 base currency.
_BASE = "chaos"


class CurrencyConverter:
    def __init__(self, client: TradeClient, economy=None):
        self.client = client
        self.economy = economy       # a poeninja.PoeNinjaEconomy (chaos rates), or None
        self._rates: Dict[str, Optional[float]] = {_BASE: 1.0}

    def rate(self, currency: str) -> Optional[float]:
        """Chaos Orbs per 1 unit of `currency` (None if it can't be priced)."""
        currency = (currency or "").lower()
        if currency in self._rates:
            return self._rates[currency]

        ckey = f"rate:{self.client.league}:{currency}"
        disk = cache.get(ckey, 1800)  # 30 min TTL; rates move and this self-heals
        if isinstance(disk, dict) and "r" in disk:
            self._rates[currency] = disk["r"]
            return disk["r"]

        rate = self._lookup(currency)
        self._rates[currency] = rate
        # cache successes AND "couldn't price" results so we don't re-query an
        # unpriceable currency every run (wrapped so None is distinguishable from a miss)
        cache.put(ckey, {"r": rate})
        return rate

    def _lookup(self, currency: str) -> Optional[float]:
        # Primary source: poe.ninja Currency economy (line.primaryValue is chaos directly).
        if self.economy is not None:
            try:
                ex = self.economy.chaos_by_id("Currency", currency)
            except Exception:
                ex = None
            if ex is not None and ex > 0:
                return ex
        # Fallback: the trade bulk-exchange endpoint (have chaos, want the currency).
        try:
            data = self.client.exchange(want=currency, have=_BASE)
        except Exception:
            return None
        ratios: List[float] = []
        result = data.get("result", {})
        listings = result.values() if isinstance(result, dict) else result
        for entry in listings:
            for off in entry.get("listing", {}).get("offers", []):
                ex, it = off.get("exchange", {}), off.get("item", {})
                if ex.get("currency") == _BASE and it.get("currency") == currency:
                    give = ex.get("amount")    # chaos you pay
                    get = it.get("amount")     # units you receive
                    if give and get:
                        ratios.append(give / get)
        return util.median(ratios) if ratios else None

    def to_chaos(self, amount: float, currency: str) -> Optional[float]:
        r = self.rate(currency)
        return amount * r if r is not None else None

    # ---- display ---------------------------------------------------------
    def divine_rate(self) -> Optional[float]:
        """Chaos per 1 Divine Orb (the figure used for the Divine display column).
        poe.ninja's Divine currency line carries this as `primaryValue` (~102.5)."""
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
