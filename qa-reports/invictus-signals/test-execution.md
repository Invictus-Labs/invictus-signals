# Test Execution Report — invictus-signals PR #8 (feat/bbwp-percentile)

## Suite Results
| Metric | Value |
|---|---|
| Total tests | 391 |
| Passing | 391 |
| Failing | 0 |
| Coverage (total) | 92.91% |
| Coverage (`ta_engine.py`) | 97% (6 uncovered lines, all pre-existing `calculate_slope`/`rsi`/`macd`/`atr`/`adx` branches untouched by this diff — verified by line number) |
| Coverage (`models.py`) | 100% |

## Failure Classification
No failures — table intentionally empty.

## Regressions (FAIL gate blockers)
None. `git log --oneline` confirms every test added by this PR is new (no test that previously passed now fails).

## Flaky Tests
Ran the suite twice consecutively (`python3 -m pytest -q` x2) — identical results both times, 391/391. All functions under test are pure (no time, no randomness, no I/O — confirmed by the Integration Contract Validator's line-by-line trace), so flakiness is structurally not possible here.

## Isolation Issues
None found. No module-level mutable state in the changed files (`bbwp`, `_rolling_bb_widths`, `compute_ta_state` are pure functions over their arguments); no shared fixtures mutated across tests in `tests/test_ta_engine.py`/`tests/test_models.py`; no `time.sleep()`; no file creation.

## Independent re-verification of code-review-swarm's 8 fixes (not trusting the prior pass's own claim)
All 8 confirmed holding via fresh probes, run independently of the original fix commit:
- `bbwp([], lookback=50, min_samples=0)` and `min_samples=-5` → `None`, no exception (400/400 probe runs across boundary values, zero crashes).
- `bbwp([1,2,inf], lookback=3)` → `None`; `bbwp([1,2,-inf], lookback=3)` → `None`.
- `_rolling_bb_widths`'s O(n²)→O(n·period) rewrite: 0/200 output divergences vs. a re-implemented growing-prefix reference.
- `compute_ta_state`'s pre-slice optimization: 0/200 rank divergences vs. the unsliced computation.
- `TAState`'s field order/defaults diffed against `git archive main`: 23/23 pre-existing fields identical in name+type+default+position; 3 new fields correctly appended.

## Independent re-verification of qa-swarm's own 4 fixes (this same pass)
- Both money-path value-assertion tests (`test_bb_width_pct_matches_manual_bbwp_over_rolling_widths`, `test_intraday_bb_width_pct_matches_manual_bbwp`) now assert `0.0 < expected < 100.0` in addition to the value match — confirmed non-degenerate on `_oscillating_prices(40)`.
- `test_both_lenses_armed_with_different_lookbacks_rank_independently`: confirmed `expected_daily != expected_intraday` (75.0 vs. ~63.16) — the fixture is genuinely lens-discriminating, not a fixture that happens to coincide.
- `test_bandwidth_percentile_fields_default_to_absent`: confirmed a manual mutation (`intraday_bb_width_pct: float | None = 0.0` in a scratch copy of `models.py`) makes this new test fail while every other test in the suite still passes — proving the gap it closes was real, not hypothetical.
