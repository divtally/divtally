"""Convert trade listing prices (divine / chaos / exalted / mirror / ...) to a single
canonical unit so item costs can be summed and compared.

Canonical unit = Exalted Orb (the PoE2 base currency). We also surface a Divine-Orb
figure for readability because expensive builds are quoted in divine.
"""
from typing import Dict, List, Optional

from . import cache, util
from .trade import TradeClient

# Currencies we never need to look up.
_BASE = "exalted"


class CurrencyConverter:
    def __init__(self, client: TradeClient):
        self.client = client
        self._rates: Dict[str, Optional[float]] = {_BASE: 1.0}

    def rate(self, currency: str) -> Optional[float]:
        """Exalted Orbs per 1 unit of `currency` (None if it can't be priced)."""
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
                    give = ex.get("amount")    # exalted you pay
                    get = it.get("amount")     # units you receive
                    if give and get:
                        ratios.append(give / get)
        return util.median(ratios) if ratios else None

    def to_exalted(self, amount: float, currency: str) -> Optional[float]:
        r = self.rate(currency)
        return amount * r if r is not None else None

    # ---- display ---------------------------------------------------------
    def divine_rate(self) -> Optional[float]:
        return self.rate("divine")

    def fmt(self, exalted: Optional[float]) -> str:
        """Human-friendly amount, e.g. '512 ex (4.1 div)'."""
        if exalted is None:
            return "n/a"
        ex = exalted
        div_rate = self.divine_rate()
        ex_str = f"{ex:,.0f} ex" if ex >= 10 else f"{ex:,.1f} ex"
        if div_rate and ex >= div_rate * 0.5:
            div = ex / div_rate
            div_str = f"{div:,.1f} div" if div < 100 else f"{div:,.0f} div"
            return f"{div_str} ({ex_str})"
        return ex_str
