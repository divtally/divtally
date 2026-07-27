"""Vendored, trade-free slice of the `bpc` engine for the PUBLIC serverless function.

This package is a self-contained copy of the parts of `bpc/` the public `api/build`
endpoint needs, with EVERY pathofexile.com trade call removed. See
`docs/notes-public-api.md` for exactly what was vendored, what was adapted, and why.

HARD INVARIANT (D-0008 / B-001): nothing in this package may ever call
pathofexile.com. Item pricing comes ONLY from poe.ninja (gems, currency, uniques by
name); rares/unpriced items get a prebuilt browser trade_url + the exact trade-API
query JSON for a client-side extension to execute. The trade query is BUILT here, never
executed.
"""
