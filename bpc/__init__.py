"""buildpricechecker (bpc) - estimate the cost of a PoE1 build from a poe.ninja link.

Pipeline:  poe.ninja build URL  ->  item list (poeninja.py)
           item list            ->  trade price distributions (pricing.py + trade.py)
           distributions        ->  min / median / high tiers, normalised to Chaos Orbs
                                     (currency.py) and printed (report.py).
"""
__version__ = "0.1.0"
