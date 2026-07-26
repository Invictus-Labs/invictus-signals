# TEST-PLAN — invictus-signals PR #8 (`feat/bbwp-percentile`)

**Run:** 2026-07-26 · **Strategist:** QA Strategist (qa-swarm, scoped)
**Diff:** `main...HEAD` — 6 commits (`9bbc8f6` → `d35b999`)
**Repo:** `/Users/knox/Documents/Dev/invictus-signals`

---

## 1. Scope

This is a **diff-scoped** QA sweep of PR #8 only — Phase 1 (Signal Engineer slice) of the
`four-layer-order` PRD. It is not a repo-wide audit; `line_detector.py` (83% cov),
`regime_classifier.py` (71% cov), and `backtest/*` are untouched by this diff and are
**out of scope** except where this diff's contract crosses into them (see §9, exit-criteria
carve-out E-6).

### In scope — changed units

| File | Unit | What changed |
|---|---|---|
| `invictus_signals/ta_engine.py` | `bbwp(widths, lookback, min_samples=2) -> float \| None` | **new** public percentile-rank helper (AC-5) |
| `invictus_signals/ta_engine.py` | `_rolling_bb_widths(closes, period, std_dev) -> list[float]` | **new** private helper feeding `bbwp()` |
| `invictus_signals/ta_engine.py` | `compute_ta_state(...)` | **+3 params** (`vol_lookback`, `intraday_vol_lookback`, `vol_min_samples`); 2 new conditional blocks; populates 3 new fields (AC-6) |
| `invictus_signals/models.py` | `TAState` | **+3 additive fields** `bb_width_pct`, `intraday_bb_width`, `intraday_bb_width_pct` (AC-6) |
| `tests/test_ta_engine.py` | `TestBBWP` (21), `TestRollingBBWidths` (5), `TestComputeTAState` (+12) | 38 new test nodes |

### Explicitly OUT of scope for this run
- **PRD ACs other than AC-5 / AC-6.** AC-1..AC-4 (Phase 0 backfill, `invictus-bot`),
  AC-7..AC-26 + AC-E1..E3 (Phases 1-bot-side / 2 / 3, `invictus-bot`, other agents).
  AC-8's log-only guarantee is *asserted in `invictus-bot`*, not here — this repo's contribution
  to it is that nothing in this diff can change an existing `TAState` field, which is what
  exit criterion **E-3** proves.
- **Wiring these fields into a live decision.** Nothing in this repo or in `invictus-bot`'s
  merged tree reads `bb_width_pct` yet; consumption arrives via `invictus-bot` PR #144.
  Therefore **no live-money path is reachable from this diff today** — this is instrumentation.
- **Naming (`bbwp` vs `calculate_bbwp`).** Adjudicated in the code review as a documented,
  deliberate exception (PRD AC-5 names it literally; cross-repo contract with bot PR #144).
  QA records it as a **decision owed to Knox/team-lead**, not a defect and not a gate.
- One incidental line — `models.py` dropped an unused `from dataclasses import ... field`
  import. Verified unused on `main` too (0 occurrences of `field(`); benign lint cleanup,
  no behavior surface.

---

## 2. Provenance

**PRD test strategy: FOUND (`invictus-bot/docs/prd/four-layer-order/four-layer-order.md` §5b),
scoped to AC-5/AC-6 rows only — other ACs out of scope for this PR.**

The two contracted rows, verbatim from §5b's coverage matrix:

| AC | Test level | Proven by — *planned* | Automated? |
|---|---|---|---|
| AC-5 | unit | `invictus-signals/tests/test_ta_engine.py :: bbwp ranks last element in trailing window; None below min_samples; no new imports` | ✅ |
| AC-6 | unit | `invictus-signals/tests/test_ta_engine.py :: compute_ta_state populates bb_width_pct and leaves every existing field unchanged` | ✅ |

Supporting §5b clauses that bind this run:
- **Reconciliation clause** — "the *Proven by* column is a **prediction** authored before the
  code… the file and the behavior survive the build, a guessed `::node_id` would not. The build's
  QA agent overwrites each row with the real node id **in the same PR**." → naming divergence
  between a predicted row and the real node is a **reconcile-nit**, never a P0. §11 supplies the
  replacement node ids.
- **Test levels** — "Unit — `bbwp()` percentile maths… ≥3 real test functions per new module."
- **Happy + sad path matrix**, `bbwp()` row — happy: "ranks last element 0–100"; sad:
  "`len < min_samples` → None · all widths identical (degenerate rank) · lookback ≤ 1 ·
  NaN/zero `middle` from `calculate_bb`."
- **Coverage target** — "≥90% on new code — the repo floor (`--cov-fail-under=90`)."
- **E2E** — "no UI surface, so no Playwright." → no Playwright specs in this plan, by spec.

**Secondary provenance:** `code-review/REVIEW-2026-07-26-1722.md` (code-review-swarm, 6 passes
incl. a gpt-5.6-sol cross-model lane) — 9 distinct findings, 8 claimed fixed, 1 adjudicated.
Per this repo's doctrine, **the review's own "FIXED" claims are treated as hypotheses, not
evidence.** Every one is independently re-verified in §10 (R-1…R-8) against the running code.

---

## 3. Risk Assessment

`risk_score = (business_criticality × complexity) + (auth_or_money_touching × 3)`

`business_criticality = 3` and `money_touching = 1` for **every** unit below: all four feed the
live-money `invictus-bot` eval loop indirectly, and a wrong percentile could mis-signal position
sizing once Phase 3 wires it. That the *current* PR is log-only (AC-8's guarantee) reduces
today's blast radius, not the unit's intrinsic risk.

| # | Unit | B.crit | Complexity | Money | Score | Why that complexity |
|---|---|---|---|---|---|---|
| **1** | `bbwp()` | 3 | **4** | 1 | **15** | 5 sequential sad-path guards (empty · `min_samples` · `lookback<=1` · non-finite target · empty-after-filter), a finiteness filter that changes the *denominator*, a degenerate-window special case returning a magic `50.0`, an `effective_lookback` graceful-degrade, and a strictly-less-than tie convention. Public API — other consumers call it directly with unvalidated args. The one unit where a silently-wrong float looks exactly like a right one. |
| **2** | `compute_ta_state()` new branches | 3 | **3** | 1 | **12** | Two near-symmetric blocks (easy to fix one lens and not the other), each with a compound guard (`lookback is not None and period >= 2`), plus `needed = lookback + period - 1` pre-slice arithmetic where a negative/zero `needed` silently changes slice semantics (`closes[-0:]` == whole list). Also the AC-6 blast surface: it constructs the whole `TAState`. |
| **3** | `_rolling_bb_widths()` | 3 | **2** | 1 | **9** | Index arithmetic `closes[i+1-period : i+1]` over `range(period-1, len(closes))` — classic off-by-one territory, and the commit that changed it from a growing prefix was a *performance* rewrite of already-shipped output. Only 2 guards. Private, single call site. |
| **4** | `TAState` ×3 new fields | 3 | **1** | 1 | **6** | Pure data with defaults. Risk is not arithmetic but **sentinel semantics**: `intraday_bb_width == 0.0` is a legitimate deepest-coil reading, *not* an absence marker (the exact confusion class behind the dnt_05/dnt_09/dnt_16 incidents). Risk is realized by a future *consumer*, not by this field. |

**Ranked:** `bbwp()` (15) → `compute_ta_state()` new branches (12) → `_rolling_bb_widths()` (9)
→ `TAState` 3 fields (6).

### Top non-arithmetic risks carried out of this run
| Risk | Severity | Status |
|---|---|---|
| **RK-1** Default `vol_min_samples=2` permits a rank from a single comparison point, which can only ever be 0.0 / 100.0 / 50.0 — a maximally extreme, maximally unreliable reading. Empirically: 400/400 runs at `n_daily = bb_period + 1` returned exactly 0.0 or 100.0 (209/191 split). | **P2** (Phase-3 latent; harmless while log-only) | Open — recommendation to bot PR #144 (§12) |
| **RK-2** A perfectly flat window ranks **50.0 = NORMAL**, i.e. the deepest possible coil maps to the neutral bucket, so a compression lane keyed on `pct <= 20` can never fire on it. Documented + adjudicated in `bbwp()`'s docstring; low real-world probability (real closes rarely produce bit-identical widths). | **P3** (documented design decision) | Accepted, recorded |
| **RK-3** Bucket thresholds are **not derivable from this PR**. A naive 80/20 cut mis-buckets a synthetic 60×-bandwidth expansion as NORMAL (measured 76.27) because a trailing window sitting inside one regime cannot rank across it. | **P2** informational | By design — PRD AC-1/AC-2 (Phase 0) must set the cuts |
| **RK-4** `backtest/engine.py:410` and `backtest/validation.py:127` call `compute_ta_state` positionally with 3 args, so both `_pct` fields are permanently `None` in this repo's only replay path — a future consumer is unvalidatable in backtest. **Independently confirmed.** | **P2** | Out of territory (review finding #9); follow-up ticket owed |
| **RK-5** AC-5's "no new imports" guard is **blind to `from <banned> import <name>`**. Proven by planting both violation forms: `import statistics` → guard fires (RED, correct); `from statistics import mean` → guard **passes** (blind). Actual code imports only `math` — so no live violation, but the guard is weaker than its name. | **P3** test-strength | Open nit (§12) |

---

## 4. Test Strategy by Layer

| Layer | What it covers here | Runner | Verdict source |
|---|---|---|---|
| **Unit — pure maths** | `bbwp()` rank convention, all 5 sad paths, degenerate + tie behavior, graceful degrade, documented-property lock-ins. `_rolling_bb_widths()` window arithmetic + guards. | `pytest tests/test_ta_engine.py::TestBBWP`, `::TestRollingBBWidths` | 26/26 pass |
| **Unit — aggregator wiring** | `compute_ta_state()` populates the 3 fields from the right lens, never cross-feeds lenses, abstains structurally, and leaves all 23 pre-existing fields untouched. | `pytest ...::TestComputeTAState` | 25/25 pass (12 new) |
| **Property / differential (QA-added, this run)** | 2,000 randomized `bbwp()` trials vs. an **independently written reference implementation**; 200 randomized series proving the O(n²)→O(n·period) rewrite is bit-identical; 200 proving the pre-slice optimization leaves the *rank* identical to a full-history rank; 150 proving the ranked target is bit-identical to `TAState.bb_width` / `intraday_bb_width`; 120 randomized configs proving AC-6 additive invariance. | scratchpad probes (§10) | 0 divergences in all 5 |
| **Contract / structural** | `TAState` field signature compared **field-by-field against `main`** (name + type + default + order), not just values. | dataclass-introspection diff vs `git archive main` | 23/23 identical, 3 appended |
| **Regression re-verification** | Each of the review's 8 "FIXED" claims re-executed against the running code as a black-box probe. | scratchpad probes (§10, R-1…R-8) | 8/8 hold |
| **Guard-can-fail (doctrine: make the guard go RED)** | Planted violations against the "no new imports" gate in both import forms. | scratchpad probe | 1 form fires, 1 blind (RK-5) |
| **Static** | `ruff check` on the 3 changed files; `mypy` on `ta_engine.py` + `models.py`. | `ruff`, `mypy` | ruff clean; mypy 0 errors in changed files (6 pre-existing errors live in untouched `config.py` / `line_detector.py`) |
| **E2E / Playwright** | **None, by PRD §5b** — "no UI surface, so no Playwright." E2E for this feature is the deploy-host observation AC-E1/E2 + the dry-run gate AC-E3, all owned by `invictus-bot`. | n/a | out of scope |
| **Integration (bot-side)** | AC-7/AC-8/AC-9 — `regime_vol` persistence and the log-only decision-tuple guarantee. | `invictus-bot` PR #144 | **not this repo's gate** |

**Fixtures / mocks:** none needed and none added — every unit under test is a pure function.
`tests/conftest.py`'s existing `make_candles()` is the only fixture used. No network, no DB, no
Phemex, no mock-quality risk to score. §5b's `runtime_config`-cache isolation note does not apply
to this repo.

---

## 5. Happy Path Inventory

**The chain:** `closes` → `_rolling_bb_widths` → `bbwp` → `TAState.{bb_width_pct,
intraday_bb_width, intraday_bb_width_pct}` → *hypothetical* Phase-3 vol-bucket consumer.

| ID | Happy path | Expected | Covered by | Status |
|---|---|---|---|---|
| H-1 | `bbwp()` on a strictly-rising series — final element is the unique max | exactly `100.0` | `TestBBWP::test_fresh_all_time_high_reads_as_100` | ✅ |
| H-2 | `bbwp()` on a strictly-falling series — unique min | exactly `0.0` | `::test_fresh_all_time_low_reads_as_0` | ✅ |
| H-3 | **Ranks the FINAL element, not a fixed index** (AC-5's core clause) — mid-pack tail | `50.0` for `[1,5,2,4,3]`; appending `10.0` flips it to `100.0` | `::test_ranks_last_element_not_some_other_index` + `::test_appending_a_new_max_changes_the_rank` | ✅ |
| H-4 | Rank formula matches the documented `100 × count_strictly_less / len(finite comparators)` | agreement on every input | **QA differential**: 2,000 randomized trials vs. independent reference → 0 mismatches | ✅ |
| H-5 | Output always in `[0, 100]` | never out of range | QA sweep over series lengths 2…39 → `True` | ✅ |
| H-6 | `_rolling_bb_widths()` last element == a direct `calculate_bb(closes, period)["width"]` | bit-identical | `TestRollingBBWidths::test_last_element_matches_direct_calculate_bb` + QA 150-config sweep | ✅ |
| H-7 | `_rolling_bb_widths()` length == `len(closes) - period + 1` | exact | `::test_length_is_series_len_minus_period_plus_1` | ✅ |
| H-8 | `compute_ta_state(..., vol_lookback=N)` populates `bb_width_pct` and its value equals a hand-rolled `bbwp(_rolling_bb_widths(...))` | equal, not a hardcoded number | `TestComputeTAState::test_bb_width_pct_matches_manual_bbwp_over_rolling_widths` | ✅ |
| H-9 | Same for the intraday lens via `intraday_vol_lookback` | equal | `::test_intraday_bb_width_pct_matches_manual_bbwp` | ✅ |
| H-10 | **The ranked target is the same number the state reports** — last rolling width == `TAState.bb_width` (daily) / `intraday_bb_width` (intraday) | bit-identical, never a second divergent computation | **QA differential**: 150 randomized configs → 0/150 mismatches each lens | ✅ |
| H-11 | `intraday_bb_width` is a snapshot — populated with **or without** any lookback | equals `calculate_bb(intraday, min(bb_period, n))["width"]` | `::test_intraday_bb_width_populated_independent_of_vol_lookback` | ✅ |
| H-12 | Both lenses armed together on realistic depth (300 daily / 200 intraday, `vol_lookback=252`, `intraday_vol_lookback=120`, `vol_min_samples=31`) | two independent floats, correct types | QA probe: `bb_width_pct=0.0`, `intraday_bb_width_pct=71.43`, all `float` | ✅ |
| H-13 | **Downstream consumer simulation** — a Phase-3-shaped `bucket(pct)` reading the field across coiling / expanding / steady / flat / short-history series | a defined bucket for every input; `None` → `INSUFFICIENT`, never the string `"None"`, never a crash | QA probe §10 K — 5/5 scenarios produced a defined bucket | ✅ (see RK-3 on threshold choice) |
| H-14 | Pre-slice performance optimization does not move the answer | rank identical to a full-history rank | **QA differential**: 200 randomized configs → 0 divergences | ✅ |
| H-15 | AC-6 additive: passing all 3 new params leaves every pre-existing field equal | 23/23 fields equal | `::test_additive_only_existing_fields_unchanged_by_vol_lookback` + **QA 120-config randomized sweep** → 0 violations | ✅ |
| H-16 | Default call site (`compute_ta_state(intraday, daily)`) — today's real callers | both `_pct` fields `None`; nothing downstream sees an unrequested value | `::test_new_pct_fields_default_none_without_vol_lookback` | ✅ |

---

## 6. Sad Path Inventory

Every row below is `bbwp()`'s **own documented contract** (its docstring's "Sad paths" +
"Other behavior" + "Caller responsibility" sections) or `compute_ta_state()`'s guard surface.
"QA probe" = independently executed this run, not merely asserted by the suite.

### `bbwp()` — contract sad paths

| ID | Sad path | Contract | Suite node | QA probe result | Status |
|---|---|---|---|---|---|
| S-1 | **Insufficient history** — `len(widths) < min_samples` | `None` | `::test_none_below_min_samples` | `bbwp([1,2], lookback=10, ms=3)` → `None` | ✅ |
| S-1b | Boundary: `len == min_samples` is *not* below the floor | ranks | `::test_none_at_exactly_min_samples_boundary_still_ranks` | `bbwp([1,2], ms=2)` → `100.0` | ✅ |
| S-2 | **`lookback <= 1`** — denominator ≤ 0 | `None` | `::test_lookback_le_1_returns_none` (1 and 0) | `lookback=1` → `None`; `=0` → `None`; **`=-5`** → `None` (negative untested by suite, verified by QA) | ✅ |
| S-3 | **Non-finite target — NaN** | `None` | `::test_nan_target_returns_none` | `None` | ✅ |
| S-3b | **Non-finite target — ±inf** (review fix R-3) | `None` | `::test_positive_infinity_target_returns_none`, `::test_negative_infinity_target_returns_none` | `+inf` → `None`; `-inf` → `None` | ✅ |
| S-4 | **Degenerate all-identical window** | `50.0` (neutral) — *not* 0/100/None | `::test_degenerate_all_identical_widths_returns_50` | `[7]*5` → `50.0`; `[7,7]` → `50.0` | ✅ (RK-2) |
| S-5 | **NaN/inf elsewhere in window** — excluded from numerator **and** denominator | rank over survivors only | `::test_nan_elsewhere_in_window_is_excluded_not_counted` | `[nan,1,5]` → `100.0` (not 50.0); `[inf,1,5]` → `100.0` | ✅ |
| S-6 | **Every other member non-finite** → zero comparators after filtering | `None` | `::test_all_other_elements_nan_returns_none` | `[nan,nan,5]` → `None`; `[inf,-inf,5]` → `None` | ✅ |
| S-7 | **Fewer elements than `lookback`** (but ≥ `min_samples`) | degrade to `effective_lookback = min(lookback, len)` — rank a smaller *real* window, never guess | `::test_fewer_elements_than_lookback_ranks_within_available_window` | `bbwp([1,2,3,4], lookback=252)` → `100.0` | ✅ |
| S-8 | **Negative widths** — not special-cased | rank normally | `::test_negative_widths_rank_normally` | `[-5,-3,-1]` → `100.0`; `[-5,-1,-3]` → `50.0` (mid-rank case, QA-added) | ✅ |
| S-9 | **`min_samples <= 0`** on an empty sequence (review fix R-2 — used to raise `IndexError`) | `None`, unconditionally | `::test_min_samples_le_zero_returns_none_not_indexerror` | `bbwp([], 50, ms=0)` → `None`; `ms=-5` → `None`; `bbwp([], 50)` → `None` | ✅ |
| S-10 | `min_samples=1` with exactly 1 width — passes the floor but has no comparator | `None` (caught by the post-filter guard, not the floor) | *(not directly asserted)* | `bbwp([1.0], lookback=5, ms=1)` → `None` | ✅ behavior correct; **coverage nit N-3** |
| S-11 | Absurd `min_samples` (10,000) vs. 10 widths | `None` | *(covered in spirit by S-1)* | `None` | ✅ |
| S-12 | **Two-lookback no-silent-fallback** — supplying only one lookback must never feed the other lens | the unfed lens stays `None` | `::test_vol_lookback_does_not_silently_feed_the_intraday_lens` **and** `::test_intraday_vol_lookback_does_not_silently_feed_the_daily_lens` (both directions) | daily-only → `(pct, None)`; intraday-only → `(None, pct)` | ✅ |
| S-13 | **Regime-spanning violation** — the one property `bbwp()` cannot detect | documented; a monotonic breakout pins to `100.0` from day one and stays there | `::test_regime_spanning_monotonic_breakout_pins_to_100_from_day_one` (locks the property) + `::test_regime_spanning_prior_cycle_in_lookback_produces_a_graduated_rank` (proves it's window composition, not a formula defect) | reproduced | ✅ documented, locked |
| S-14 | **"A high level is NOT exhaustion"** | caller must add a derivative/duration term; `bbwp()` cannot | docstring only — *behaviorally identical to S-13, so no separate node is possible* | n/a | ✅ documented |

### `_rolling_bb_widths()` — guard surface

| ID | Sad path | Contract | Suite node | QA probe | Status |
|---|---|---|---|---|---|
| S-15 | `period < 2` | `[]`, never raises | `::test_returns_empty_for_period_below_2` | `period=1` → `[]`; **`period=0`** → `[]`; **`period=-3`** → `[]` | ✅ |
| S-16 | `len(closes) < period` | `[]` | `::test_returns_empty_when_shorter_than_period` | `[]`; **empty `closes`** → `[]` | ✅ |
| S-17 | **Zero/near-zero `middle`** from `calculate_bb` (PRD §5b's "NaN/zero `middle`") | reuse `calculate_bb`'s `middle==0` guard → `0.0`, never `ZeroDivisionError` | `::test_zero_mean_window_yields_zero_width_no_crash` | `[-1,1,-1,1]` → `[0.0]` | ✅ |

### `compute_ta_state()` — new-branch sad paths

| ID | Sad path | Expected | Suite node | QA probe | Status |
|---|---|---|---|---|---|
| S-18 | Neither lookback supplied (today's real callers) | both `_pct` = `None` | `::test_new_pct_fields_default_none_without_vol_lookback` | `None, None` | ✅ |
| S-19 | `vol_lookback = 0` / `1` | `None` (no rank from a ≤1 window) | *(not asserted)* | `0` → `None`; `1` → `None`; `2` → `0.0` (min viable) | ✅ behavior correct; **nit N-3** |
| S-20 | **Negative `vol_lookback`**, incl. the `needed == 0` slice trap (`vol_lookback = 1 - bb_period` makes `closes[-0:]` the whole list) | `None`, no crash, no silent full-history scan side effect | *(not asserted)* | `-5` → `None`; `-19` (→`needed=0`) → `None`; intraday `-5` → `None` | ✅ no defect (bbwp's `lookback<=1` catches it); **nit N-3** |
| S-21 | `vol_min_samples <= 0` reaching `bbwp` through the aggregator | must not raise; ranks when data is genuinely sufficient | *(not asserted at this layer)* | `ms=0` → `0.0`; `ms=-3` → `0.0`. No `IndexError` — the empty-guard is what protects it | ✅ |
| S-22 | **`vol_min_samples` structural SPCX abstention — DAILY** | `None` by construction, not by incidental candle count | `::test_vol_min_samples_makes_short_history_abstain_structurally` (proves default ranks, `ms=50` abstains on *identical* history) | `ms=50` → `None`; `ms=2` → not-None | ✅ |
| S-23 | **`vol_min_samples` structural abstention — INTRADAY lens** (the review's own "residual gap") | same abstention | ❌ **no node** | `intraday_vol_lookback=30, ms=50` → `None`; same with `ms=2` → `0.0`. **Behavior is correct** — the lever works on both lenses | ✅ behavior; **nit N-1 (test gap confirmed)** |
| S-24 | `bb_period < 2` (1 daily candle) with a lookback supplied | `None` — no band exists at all | `::test_bb_width_pct_none_when_daily_history_too_short_for_a_band` | `None` | ✅ |
| S-25 | `intraday_bb_period < 2` (1 intraday candle) with `intraday_vol_lookback` supplied | `intraday_bb_width_pct = None` **and** `intraday_bb_width = 0.0` | `::test_intraday_bb_width_pct_none_with_single_intraday_candle`, `::test_intraday_bb_width_zero_sentinel_with_single_candle` | `None`, `0.0` | ✅ |
| S-26 | **`n_daily <= cfg.bb_period`** — produces exactly 1 rolling width, so no comparator exists | `None` (the effective AC-3 "INSUFFICIENT" path for short-history assets like SPCX) | *(not asserted at this boundary)* | 15 candles → `None`; **20 == `bb_period` → `None`**; 21 → a rank. **Hard floor for any rank is `bb_period + 1` daily candles**, which no docstring states | ✅ behavior; **nit N-2** |
| S-27 | Flat daily series (all widths bit-identical `0.0`) | degenerate → `50.0` | `(covered at bbwp layer, S-4)` | `bb_width_pct = 50.0` while `bb_width = 0.0` | ✅ (RK-2) |
| S-28 | Zero-mean windows inside the *history* (not just the tail) | valid 0-100 rank, no crash | `::test_bb_width_pct_survives_zero_mean_window_in_history` | `50.0`, in range | ✅ |
| S-29 | `vol_lookback` >> history (100,000 vs 30 candles) | degrade to available window | *(S-7 at unit layer)* | `0.0`, no crash | ✅ |
| S-30 | Pre-existing raise paths unchanged (`candles=[]`, `daily_candles=[]`) | `ValueError` | `::test_raises_empty_candles`, `::test_raises_empty_daily` | pass | ✅ |

### `TAState` — sentinel-semantics sad path

| ID | Sad path | Expected | Status |
|---|---|---|---|
| S-31 | A consumer gates presence on `intraday_bb_width > 0.0` | **WRONG** — `0.0` is a legitimate deepest-coil reading. Presence for the whole intraday-BB group is keyed **solely** off `intraday_bb_upper > 0.0`. | ✅ Correctly documented in `models.py` (review fix R-4 verified); **not enforceable by a test in this repo** — the misuse would live in a consumer. Carried to §12 as a hard note for bot PR #144. |
| S-32 | A consumer differences `intraday_bb_width - bb_width` | **WRONG** — different `bb_period` caps make the raw magnitudes non-comparable; only the two `_pct` ranks are cross-comparable. | ✅ Documented; consumer-side |

---

## 7. Entry Criteria

| # | Criterion | Status |
|---|---|---|
| EN-1 | PRD test strategy located and the AC-5/AC-6 rows extracted as the contract | ✅ §2 |
| EN-2 | Full diff + full current content of all 3 changed files read | ✅ |
| EN-3 | Branch is `feat/bbwp-percentile`, 6 commits ahead of `main`, no uncommitted changes to the units under test | ✅ |
| EN-4 | Test suite runnable locally (`.venv/bin/pytest`, Python 3.12.13) | ✅ |
| EN-5 | Prior `/code-review-swarm` record read, and its "FIXED" claims enumerated for **independent** re-verification (not accepted on assertion) | ✅ §10 |
| EN-6 | No live-money path reachable from this diff (log-only, Phase 1 / AC-8) — confirmed: zero non-test consumers of the 3 new fields in this repo, and `backtest/*` calls `compute_ta_state` positionally with 3 args so both `_pct` fields are `None` there | ✅ |
| EN-7 | Scope boundary agreed: AC-5/AC-6 only; AC-1..4, AC-7..26, AC-E1..3 out of scope | ✅ §1 |

---

## 8. Exit Criteria

| # | Criterion | Threshold | Measured | Verdict |
|---|---|---|---|---|
| E-1 | Full suite green | 100% | **388 passed**, 0 failed, 0 skipped, 0.42s | ✅ |
| E-2 | Coverage ≥ 90% (repo floor) | ≥90% | **92.91%** total · `ta_engine.py` **97%** · `models.py` **100%** | ✅ |
| E-2b | **New code** at ≥90% line coverage | ≥90% | **100%** — the 6 uncovered `ta_engine.py` lines (329, 338, 404, 433, 473, 484) all sit in pre-existing `calculate_slope`/`rsi`/`macd`/`atr`/`adx` bodies, outside `bbwp()` (76-242), `_rolling_bb_widths()` (243-282), and the new `compute_ta_state` block | ✅ |
| E-3 | **AC-6 additivity proven structurally, not just by value** — all pre-existing `TAState` fields identical in name, type, default, and **order**, vs. `main` | 23/23 | 23/23 identical; 3 new fields appended last, all with defaults; **no positional `TAState(...)` construction anywhere in the repo** | ✅ |
| E-4 | AC-5 behaviors from §5b all asserted: ranks last element · `None` below `min_samples` · no new imports | 3/3 | 3/3 (§11) | ✅ |
| E-5 | AC-6 behaviors from §5b all asserted: populates `bb_width_pct` · every existing field unchanged | 2/2 | 2/2 (§11) | ✅ |
| E-6 | Every §5b `bbwp()` sad path has a node: `len < min_samples` · all-identical · `lookback ≤ 1` · NaN/zero `middle` | 4/4 | 4/4 (S-1, S-4, S-2, S-17) | ✅ |
| E-7 | Each of the review's 8 "FIXED" claims **independently reproduced** as a live probe | 8/8 | 8/8 (§10) | ✅ |
| E-8 | `bbwp()` rank maths verified against an independent reference implementation | 0 divergences | **0 / 2,000** randomized trials | ✅ |
| E-9 | The two performance rewrites are output-neutral | 0 divergences | **0 / 200** (`_rolling_bb_widths` fixed-window vs. growing-prefix) and **0 / 200** (pre-slice vs. full-history rank) | ✅ |
| E-10 | Ranked target == reported width (no second, divergent computation) | 0 mismatches | **0 / 150** each lens | ✅ |
| E-11 | Static gates clean on the changed files | 0 new | `ruff` clean; `mypy` 0 errors in `ta_engine.py` / `models.py` (6 errors pre-exist in untouched `config.py`, `line_detector.py`) | ✅ |
| E-12 | No new dependency | `dependencies = []` | unchanged; `ta_engine.py` imports only `math` + `typing` + internal modules | ✅ |
| E-13 | Every new guard demonstrated able to go **RED** | all | `bbwp` guards: proven by targeted probes. **"No new imports" guard: partially RED-provable** — fires on `import statistics`, blind to `from statistics import mean` → **RK-5 / nit N-4** | ⚠️ 1 nit |
| E-14 | No P0 / P1 defect open against the diff | 0 | **0** — the only P1 in the review is the adjudicated naming decision (a decision owed, not a defect) | ✅ |
| E-15 | Residual items ticketed or explicitly carried | all named | 4 nits + 5 risks recorded in §12 | ✅ |

---

## 9. Verdict

**PASS** — with 0 P0/P1 defects, 4 P3 test-strength nits, and 5 carried risks (all Phase-2/3
consumer-side or out-of-territory). The two PRD-contracted ACs are fully covered; every claimed
review fix independently holds; the new code is at 100% line coverage; and AC-6's additivity is
proven structurally against `main`, not merely value-compared.

**One decision is owed to Knox / team-lead** (not a QA gate): accept `bbwp` as a documented
naming exception, or take the rename + cross-repo re-sync cost on `invictus-bot` PR #144.

---

## 10. Independent Re-verification of the Prior Review's Fixes

Probes executed this run against the live code (`/private/tmp/.../scratchpad/probe*.py`).
**None of these outcomes were taken from the review document.**

| ID | Review claim | Independent probe | Result |
|---|---|---|---|
| R-1 | `bbwp([], lookback=50, min_samples=0)` returns `None` instead of raising `IndexError` | executed with `ms=0`, `ms=-5`, and default | `None`, `None`, `None` — **no exception** ✅ |
| R-2 | `+inf` / `-inf` target now returns `None` (was a confident `100.0` / `0.0`) | both signs | `None`, `None` ✅ |
| R-3 | `models.py` comment corrected — `intraday_bb_width == 0.0` is not an absence sentinel | read current file text | corrected, and additionally documents the non-comparable-periods hazard ✅ |
| R-4 | `_rolling_bb_widths` fixed-window slice is output-identical to the old growing-prefix version | re-implemented the old prefix version, diffed over 200 random series × random periods | **0 divergences** ✅ |
| R-5 | `compute_ta_state` pre-slice (`lookback + period - 1`) does not change the answer | compared against a full-history rank over 200 random configs | **0 divergences** ✅ |
| R-6 | `vol_min_samples` docstring conversion `N - bb_period + 1` is correct | 30 daily candles @ `bb_period=20` → 11 rolling widths; `ms=50` abstains, `ms=2` ranks | matches the stated arithmetic ✅ |
| R-7 | Docstring's rank formula (`count_strictly_less / len(finite comparators)`) matches the code on the filtered path | 2,000 randomized trials vs. an independent reference implementing the docstring literally | **0 mismatches** ✅ |
| R-8 | Review's residual gap — `vol_min_samples` never tested against the intraday lens — was "verified manually correct" | executed the intraday lens with `ms=50` and `ms=2` | `None` / `0.0` — **behavior is correct**; the *test* gap is real (N-1) ✅ |

Plus two QA-originated checks the review did not make:
- **Guard-can-fail:** planted both import-violation forms against `test_stdlib_only_no_new_imports`
  → `import statistics` correctly turns the guard RED; `from statistics import mean` slips through
  (RK-5 / N-4).
- **`TAState` signature diff vs. `main`:** field-by-field name + type + default + order compare
  via `git archive main` → 23/23 identical, 3 appended, no reordering. (The suite's AC-6 test
  compares *values*; AC-6's text also says "and type" — now proven.)

---

## 11. AC-5 / AC-6 Row Reconciliation (§5b's "QA agent overwrites each row" clause)

Both PRD rows named the **file + behavior**, not node ids — exactly as §5b instructed. Every
contracted behavior exists and passes; only the node *names* differ from the prose. Per §5b's
reconciliation clause this is a **reconcile-nit, not a P0**.

**AC-5** — predicted: `test_ta_engine.py :: bbwp ranks last element in trailing window; None below min_samples; no new imports`

| Contracted behavior | Real node id | Result |
|---|---|---|
| ranks last element in trailing window | `tests/test_ta_engine.py::TestBBWP::test_ranks_last_element_not_some_other_index` | PASS |
| ↳ (reinforcing) | `::TestBBWP::test_appending_a_new_max_changes_the_rank` | PASS |
| None below `min_samples` | `::TestBBWP::test_none_below_min_samples` | PASS |
| ↳ boundary + default floor | `::TestBBWP::test_none_at_exactly_min_samples_boundary_still_ranks`, `::TestBBWP::test_default_min_samples_is_the_mathematical_floor_of_2` | PASS |
| no new imports | `::TestBBWP::test_stdlib_only_no_new_imports` | PASS (partial guard — N-4) |
| returns 0–100 | `::TestBBWP::test_fresh_all_time_high_reads_as_100`, `::test_fresh_all_time_low_reads_as_0` | PASS |

**AC-6** — predicted: `test_ta_engine.py :: compute_ta_state populates bb_width_pct and leaves every existing field unchanged`

| Contracted behavior | Real node id | Result |
|---|---|---|
| `compute_ta_state` populates `bb_width_pct` | `::TestComputeTAState::test_bb_width_pct_matches_manual_bbwp_over_rolling_widths` | PASS |
| ↳ intraday counterpart (AC-7's second lens) | `::TestComputeTAState::test_intraday_bb_width_pct_matches_manual_bbwp` | PASS |
| every existing field keeps its **value** | `::TestComputeTAState::test_additive_only_existing_fields_unchanged_by_vol_lookback` | PASS |
| every existing field keeps its **type** | *no node* — proven this run by a dataclass signature diff vs. `main` (23/23) | PASS (nit N-5) |

**Suggested §5b replacement rows** (for whoever owns the PRD edit — `invictus-bot` repo, not this one):

```
| AC-5 | unit | `invictus-signals/tests/test_ta_engine.py::TestBBWP` (21 nodes; ranks last element:
  ::test_ranks_last_element_not_some_other_index · None below min_samples:
  ::test_none_below_min_samples · stdlib-only: ::test_stdlib_only_no_new_imports) | ✅ |
| AC-6 | unit | `invictus-signals/tests/test_ta_engine.py::TestComputeTAState`
  (::test_bb_width_pct_matches_manual_bbwp_over_rolling_widths +
  ::test_additive_only_existing_fields_unchanged_by_vol_lookback) | ✅ |
```

**Test-count note:** `test_ta_engine.py` collects **86** nodes at HEAD vs. **48** on `main` —
**38 new** (21 `TestBBWP` + 5 `TestRollingBBWidths` + 12 added to `TestComputeTAState`, which now
holds 25). Not the 83 the review recorded; its count predates its own fix commit's 3 added tests.
§5b's "≥3 real test functions per new module" is met by a wide margin.

---

## 12. Residual Nits & Carried Items (none blocking)

| ID | Item | Priority | Owner |
|---|---|---|---|
| **N-1** | `vol_min_samples` has no test against the **intraday** lens (`intraday_vol_lookback` + high `ms` → `None`). Behavior verified correct by QA probe; the assertion is missing. One node mirroring `::test_vol_min_samples_makes_short_history_abstain_structurally` closes it. | P3 | this repo, follow-up |
| **N-2** | The **hard floor for any rank is `bb_period + 1` daily candles** (at exactly `bb_period` there is one rolling width and no comparator → `None`). Correct behavior, unstated in any docstring and unasserted at the boundary. Worth one node + one docstring line, since a Phase-3 consumer will want to know why a 20-candle asset never ranks. | P3 | this repo, follow-up |
| **N-3** | No node covers `vol_lookback ∈ {0, 1, negative}` or `vol_min_samples ≤ 0` **at the `compute_ta_state` layer** (all verified safe by QA probe: every one returns `None`/ranks, none raise). Includes the `needed == 0` → `closes[-0:]` whole-list slice quirk, which is harmless only because `bbwp`'s `lookback <= 1` guard catches it — an unasserted dependency between two guards. | P3 | this repo, follow-up |
| **N-4** | `test_stdlib_only_no_new_imports` is blind to `from <banned> import <name>`. Proven by planting both forms. Strengthen by asserting on the module's import lines, or by asserting `pyproject.toml`'s `dependencies == []` (the real invariant). | P3 | this repo, follow-up |
| **N-5** | AC-6 says "value **and type**"; the suite compares values only. The signature diff done this run should become a permanent node (assert the pre-existing 23 field names/types/order). | P3 | this repo, follow-up |
| **RK-1** | **Recommendation to `invictus-bot` PR #144:** pass an explicitly calibrated `vol_min_samples`, never the default `2` — a 2-sample rank is provably only ever 0.0/100.0/50.0 (400/400 extremes measured). Phase 3's bucket should treat a rank derived from fewer than N comparators as `INSUFFICIENT`, not as an extreme. | P2 | bot PR #144 |
| **RK-4** | `backtest/engine.py:410` + `backtest/validation.py:127` don't thread the new kwargs → the `_pct` fields are permanently `None` in this repo's only replay path. Naively wiring `intraday_vol_lookback` at `engine.py:410` would introduce a **look-ahead rank** (it passes the full intraday series per daily bar) — the intraday series must be causally sliced to bar `i` first. | P2 | this repo, separate PR |
| **S-31** | **Hard note for any consumer:** presence of the intraday-BB group is keyed **solely** off `intraday_bb_upper > 0.0`. Never gate on `intraday_bb_width > 0.0`, and never difference `intraday_bb_width - bb_width`. Not enforceable from this repo. | P2 note | bot PR #144 |
| **DEC-1** | `bbwp` vs `calculate_bbwp` naming — accept the documented exception, or rename + re-sync bot PR #144. | decision owed | Knox / team-lead |

---

## 13. Sign-off

| Role | Name | Verdict | Basis |
|---|---|---|---|
| QA Strategist | qa-swarm (scoped, PR #8) | **PASS** | 388/388 green · 92.91% total / 100% new-code coverage · AC-5 + AC-6 fully covered (§11) · 8/8 prior review fixes independently reproduced (§10) · 0 divergences across 5 differential/property sweeps · 16 happy paths + 32 sad paths inventoried, all with a node or an executed probe · 0 P0/P1 defects |
| Code review (prior) | code-review-swarm `REVIEW-2026-07-26-1722.md` | NEEDS_WORK → **1 decision owed** | 8/9 findings fixed; the 9th is the `bbwp` naming adjudication (DEC-1), not an engineering defect |
| Merge gate | — | **CLEARED on the QA axis** | Contingent only on DEC-1 being dispositioned. No GHA check is a gate on this repo (CLAUDE.md). |
| Follow-ups owed | — | 5 nits (N-1…N-5, P3) + 3 carried risks (RK-1, RK-4, S-31) | See §12 |

**Evidence commands (reproducible):**
```bash
cd /Users/knox/Documents/Dev/invictus-signals
.venv/bin/pytest -q                                     # 388 passed, 92.91%
.venv/bin/pytest tests/test_ta_engine.py::TestBBWP \
    tests/test_ta_engine.py::TestRollingBBWidths \
    tests/test_ta_engine.py::TestComputeTAState -q --no-cov   # 51 passed
ruff check invictus_signals/ta_engine.py invictus_signals/models.py tests/test_ta_engine.py
```
