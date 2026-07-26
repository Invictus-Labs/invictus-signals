# E2E Path Matrix — invictus-signals PR #8

**See `TEST-PLAN.md` §5 (Happy Path Inventory) and §6 (Sad Path Inventory)** for the full matrix — the QA Strategist produced these directly against this PR's actual contract (PRD §5b for AC-5/AC-6) rather than a generic template, so they are reproduced there in full rather than duplicated here.

## Summary
- **16 happy paths** (H-1…H-16): rank convention, target-identity (`_rolling_bb_widths`'s last element == `TAState.bb_width`/`intraday_bb_width`, verified 0/150 mismatches per lens), both-lenses-armed independently, additive invariance (0/120 mismatches on existing fields with/without the new params), and a hypothetical Phase-3 vol-bucket consumer exercised over 5 series shapes.
- **32 sad paths** (S-1…S-32): every documented `bbwp()` contract path (insufficient history, `lookback<=1` incl. negative, non-finite target both signs, degenerate all-identical→50.0, non-finite elsewhere, all-others-non-finite, fewer-than-lookback degrade, negative widths, `min_samples<=0`), the two-lookback no-silent-fallback property in **both directions**, regime-spanning, level≠exhaustion, `_rolling_bb_widths`'s own guards, `compute_ta_state`'s 13 new-branch paths, and 2 consumer-side sentinel-misuse paths.

## PROVEN status
All 16 happy + 32 sad paths are either **PROVEN** (a test exists and genuinely exercises the scenario — independently re-verified this run, not taken on the review's word) or explicitly carried as an out-of-territory/Phase-2-3 risk (see `TEST-PLAN.md` §12 "Residual Nits & Carried Items" and `cross-model-probe.md`'s MISSING_SAD_PATHS triage table for the small number of accepted, non-blocking gaps).

## No E2E/smoke test framework applies
This PR has no HTTP endpoints, no user-facing flow, and no UI surface — it is a pure-function library change. "E2E" here means the deploy-host observations the PRD defers to `invictus-bot` (AC-E1/E2) plus the dry-run gate (AC-E3), both out of scope for this repo per `TEST-PLAN.md` §1.
