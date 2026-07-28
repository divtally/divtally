# D-0019 site half - completion notes (main agent, finishing the user-stopped subagent's work)

State inherited: core.js defining-filter engine + all CSS + all render wiring (vtag on tooltip/
board/manual rows, pvariant picker banner, timeless note, Vilsol deep-link builder w/ DISPLAYED
seed) + test_picker at 98 assertions - all done by the subagent before it was stopped.

Finished inline (2026-07-27): config.js RELEASE_URL; landing one-liner (hero) linking first live
store else the GitHub release; upgrade-card GitHub link; how-it-works Rung-2 download link;
asset version -> 20260727g. SKIPPED deliberately: sample.js mock variant items - the owner's
bug-campaign builds carry REAL variant items (SergoheroGaz: Lethal Pride, Rakiata seed 13032),
which test the feature more honestly than hand-built mocks; revisit if demo-mode coverage is
ever needed.

Verification: test_picker 98/98, test_scanstatus 47/47, node --check clean, live browser check
of the deployed site rendering the real timeless variant (see commit).
