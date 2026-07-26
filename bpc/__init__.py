"""buildpricechecker (bpc) - estimate the cost of a PoE2 build from a poe.ninja link.

Pipeline:  poe.ninja build URL  ->  item list (poeninja.py)
           item list            ->  trade2 price distributions (pricing.py + trade.py)
           distributions        ->  min / median / high tiers, converted to a common
                                     currency (currency.py) and printed (report.py).
"""
__version__ = "0.1.0"
