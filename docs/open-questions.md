# Open questions (owner's call) - RULE 5

Log design forks that are the owner's call here, with a recommended pick marked. Raise in chat at
a natural boundary; prune the moment an answer is in.

## Q-001 (2026-07-26): raise SEARCH_BUDGET above 30?
The per-run live-search cap is 30 (inherited from the PoE2 parent; ban-safety). PoE1 builds can
carry ~19 jewels, so jewel-heavy builds hit the cap on the first run and the overflow prices on
subsequent runs (rows show a trade link, no number, until then).
- **Keep 30 (recommended)** - safest for your IP; repeat runs fill in the rest from cache.
- Raise to ~45-50 - most builds complete in one run; slightly more trade load per run.
- Make it a `--budget` CLI/web option - flexible, tiny bit more surface.
