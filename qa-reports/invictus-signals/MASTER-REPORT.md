# QA Swarm Report — invictus-signals — 2026-07-26

**PR:** [Invictus-Labs/invictus-signals#8](https://github.com/Invictus-Labs/invictus-signals/pull/8) — `feat/bbwp-percentile`, 8 commits, `main...HEAD`
**Scope:** diff-scoped to this PR (Phase 1, AC-5/AC-6 of the `four-layer-order` PRD), not a whole-repo audit — mirrors how `/code-review-swarm` was already diff-scoped on this same branch. `code-review-swarm`'s own review (`code-review/REVIEW-2026-07-26-1722.md`) ran first; this is the second, independent CI-of-record gate per CLAUDE.md.

## Run Summary
| Dimension | Result |
|---|---|
| Suite status | **PASS** — 392/392 |
| Coverage | 92.91% total (floor 90%); `ta_engine.py` 97%, `models.py` 100% — every uncovered line pre-existing, none in this diff's new code |
| Regressions found | 0 |
| Edge case risks | 0 remaining unaddressed (6 found across 2 review passes, all fixed or explicitly out-of-territory with reasoning) |
| Contract violations | 0 |
| Mock quality issues | 0 remaining (1 self-referential-oracle pattern found + fixed; not a literal mock, same failure class) |
| Mutation-proxy gaps | 0 remaining (4 real gaps found + fixed of 12 traced mutations; 2 were equivalent mutants, correctly not "fixed") |
| E2E path gaps | 0 — see `e2e-path-matrix.md` |
| Observability gaps | 0 — N/A domain (pure stdlib math, zero I/O/logging), confirmed by grep not assumed |
| Config risks | 0 — N/A domain (zero env/config access in the changed files), confirmed by grep not assumed |
| Cross-model corroborated findings | 6 (across both `code-review-swarm` and `qa-swarm` cross-model passes) |
| **Gate verdict** | **PASS** |

## Gate Verdict: PASS
392/392 tests pass, 0 regressions, 100% line coverage on new code, both PRD-contracted ACs (AC-5, AC-6) independently verified rather than trusted, and every P0/P1 finding from 8 independent review passes (5 code-review-swarm agents + 1 code-review cross-model + 3 qa-swarm agents/strategist + 1 qa-swarm cross-model) is either fixed-with-a-regression-test or explicitly adjudicated with recorded reasoning. One item (the `bbwp` naming convention) is a decision owed to team-lead/Knox, not a gate failure — it does not meet any FAIL criterion (it is not a regression, not a P0, not an untested AC, not a broken contract).

## P0 Findings — Gate Blockers
None.

## P1 Findings — Resolve Before Next Release
None outstanding. 3 were found across this run and the prior code-review pass; all 3 are fixed:

| Priority | Domain | File:Line | Issue | Status |
|---|---|---|---|---|
| P1 | Mutation Proxy | `tests/test_ta_engine.py:617,640` (orig) | The two money-path value-assertion tests used a monotone-linear fixture, making both sides of the assertion evaluate to `0.0` regardless of which window was actually selected — blind to a real wiring regression (e.g. reverting the pre-slice arithmetic). | **FIXED** — `_oscillating_prices()` non-monotone fixture + explicit non-degeneracy guard (`53a8a1a`). |
| P1 | Mutation Proxy | `tests/test_models.py` (new) | `TAState`'s 3 new fields' dataclass-level defaults were never pinned — every `compute_ta_state` test passes them explicitly, so the DEFAULT itself was unguarded. | **FIXED** — `test_bandwidth_percentile_fields_default_to_absent`, using `is None` (`53a8a1a`); mutation manually verified to make the new test fail, then reverted (`391→392` net after also adding a lens-independence test). |
| P1 (docs) | Cross-model (Sol) | `invictus_signals/ta_engine.py:517` (orig) | The `candles` docstring's "pass multi-session history for `intraday_vol_lookback`" advice was incomplete — `calculate_vwap` has no internal windowing (unlike `intraday_ma_fast`/`mid`/`adx`, which all self-bound), so widening `candles` silently widens `vwap` from a session average to a multi-session one. | **FIXED (docs)** — docstring now states the trade-off explicitly; verified this is a pre-existing characteristic of real usage (invictus-bot's 500-bar 1H buffers already span ~20 days), not introduced by this PR (`70aa676`). Not fixing `calculate_vwap` itself — pre-existing, cross-cutting, out of this PR's additive-only scope. |

## P2 Findings — Documented, Non-Blocking
| Priority | Domain | File:Line | Issue | Status |
|---|---|---|---|---|
| P2 | Mutation Proxy | `tests/test_ta_engine.py` | Cross-lens-fallback bug (fixed in `2d0352e`) was only caught by accident (`TypeError`), never by a value-based check with both lookbacks armed to different values. | **FIXED** — `test_both_lenses_armed_with_different_lookbacks_rank_independently` (`53a8a1a`). |
| P2 | Mutation Proxy | `invictus_signals/ta_engine.py` (intraday `bbwp` call) | `vol_min_samples` passthrough coverage was asymmetric — daily lens pinned, intraday lens not. | **FIXED** — `test_vol_min_samples_makes_intraday_lens_abstain_structurally_too` (`53a8a1a`). |
| P2 | Mutation Proxy | `tests/test_ta_engine.py` (zero-mean test) | Weak `0<=x<=100` range assertion on a fixture that hand-verifies to exactly `50.0`. | **FIXED** — tightened to `pytest.approx(50.0)` (`53a8a1a`). |
| P2 | Cross-model (Sol) | `invictus_signals/ta_engine.py` (pre-slice arithmetic) | `vol_lookback<=1` (incl. negative) still ran the full-history rolling-width scan before `bbwp()` rejected it — 8.6x slower measured on 200k candles for `vol_lookback=-19`. | **FIXED** — `> 1` guard added before any work runs, mirroring `bbwp()`'s own rejection; 33ms measured post-fix (`70aa676`). |
| P2 | Cross-model (Sol) | `invictus_signals/ta_engine.py:67` (`calculate_bb`) | `calculate_bb`'s variance step can `OverflowError` on ~1e308-magnitude finite closes — pre-existing math, not modified by this PR, shared by every `calculate_bb` caller repo-wide. This PR increases call frequency (once per rolling position) but doesn't introduce the defect. | **Not fixed — out of territory.** Flagged for a follow-up ticket; fixing float-overflow guarding in a shared primitive has its own repo-wide blast radius. |
| P2 | Cross-model (Sol) | `invictus_signals/config.py:112` (`get_config`) | `get_config(symbol)` with no overrides returns the shared `ASSET_PRESETS[symbol]` object directly — mutating it mutates the global preset. Pre-existing, `config.py` untouched by this PR; every test in this PR that needed a modified config already uses explicit overrides (safe, per `config.py`'s own `dataclasses.replace` path). | **Not fixed — out of territory.** Flagged for a follow-up ticket. |
| P2 (adjudicated) | Consistency Reviewer | `invictus_signals/ta_engine.py:76` | `bbwp` breaks the module's `calculate_*` naming convention. | **Adjudicated exception, not fixed** — matches the PRD's literal AC-5 contract name and `invictus-bot` PR #144's already-built dependency on this exact name. Rationale comment added in-code. **Decision owed to team-lead/Knox**, not a QA gate (see `TEST-PLAN.md` §9). |
| P2 (accepted) | QA Strategist / Mutation Proxy | `models.py` / `ta_engine.py` (backtest) | `backtest/engine.py`/`validation.py` don't thread the new kwargs through (permanently `None` in backtest replay); `TAState` field-order has no contract test (cross-repo exposure only, all in-repo callers are keyword-only). | **Accepted, not fixed** — both out of this PR's `ta_engine.py`/`models.py` territory; reasoning recorded in `integration-contracts.md` and `mock-quality.md`. |
| P2/P3 (informational) | QA Strategist | — | `vol_min_samples=2` default permits a rank from as few as 1 comparison point (result can only be 0.0/50.0/100.0) — 400/400 probe runs confirmed. This is the correct, documented mathematical floor, not a bug; Phase 3 must pass a calibrated value per the PRD's own D-2 deferral. | **Informational, not this PR's to resolve.** |
| — | Cross-model (Sol) MISSING_SAD_PATHS | — | 18 candidate scenarios triaged (duplicate timestamps, out-of-order candles, mixed intervals, NaN in candle closes, extreme `bb_std_dev`, TAState serialization, etc.). | See `cross-model-probe.md`'s full triage table — the large majority are either already covered indirectly, pre-existing/out-of-territory, or accepted low-priority gaps for a future hardening pass; none block this PR. |

## Domain Report Index
- [Test Plan](./TEST-PLAN.md) — the primary artifact: scope, provenance, risk assessment, full 16-happy/32-sad path inventory, 8-point independent re-verification of the prior code-review's fixes, and the AC-5/AC-6 PRD reconciliation.
- [Test Execution](./test-execution.md)
- [Integration Contracts](./integration-contracts.md) — purity confirmed PURE; corrected an assumption about `invictus-bot`'s dependency direction (PR #8 is a *prerequisite* for bot PR #144, not a risk to it).
- [Mock Quality / Mutation Proxy](./mock-quality.md)
- [E2E Path Matrix](./e2e-path-matrix.md)
- [Observability](./observability.md) — N/A domain, confirmed by grep
- [Configuration](./configuration.md) — N/A domain, confirmed by grep
- [Path Verification](./path-verification.md)
- [Cross-Model Probe](./cross-model-probe.md) — gpt-5.6-sol, run twice (code-review + qa-swarm framings)

## What changed as a direct result of this QA pass
Commits `53a8a1a` (mutation-proxy gaps: 2 P1 + 2 P2, all new regression tests) and `70aa676` (cross-model findings: 1 P2 perf fix + 1 P1 docs fix). Net: **392/392 tests passing** (up from 388 at the start of this QA pass), 5 new regression tests, 0 new ruff/mypy issues.

## Sign-off
Generated by `/qa-swarm`, scoped to PR #8's diff, 2026-07-26. Second CI-of-record gate on this branch (after `/code-review-swarm`). Both receipts belong in the PR body per CLAUDE.md's swarm-receipt merge-authorization contract. Knox merges — this report does not.
