# Integration Contract Report — invictus-signals PR #8 (feat/bbwp-percentile)

## Verdict: 0 findings (`[]`). Purity confirmed. One prior assumption corrected.

## Purity: PURE (both `bbwp()` and `compute_ta_state()`)
Traced line-by-line. `ta_engine.py` imports only `math` and `typing.Sequence`. No `time`, `datetime`, `random`, `os`, or I/O modules. `compute_ta_state`'s only non-local call when `config is None` is `get_config("SPY")`, a read-only lookup into the static module-level `ASSET_PRESETS` dict in `config.py` — never mutated. Same input → same output guaranteed; no hidden state, no time-dependence, no randomness, no I/O.

## Corrected finding: invictus-bot pinning direction was inverted in an earlier assumption
`invictus-bot/requirements.txt`: `invictus-signals @ git+https://github.com/Invictus-Labs/invictus-signals.git` — **no branch/tag/commit pin**, resolves to invictus-signals' default-branch HEAD at install time.

- `invictus-bot` **`main`**: zero references to `bbwp`/`vol_lookback`/`bb_width_pct`/`intraday_bb_width*` — completely unaffected by PR #8 merging.
- `invictus-bot` **`feat/regime-vol-phase1-risk`** (PR #144, title literally "DO NOT MERGE (blocked on #2527)"): already calls `compute_ta_state(..., vol_lookback=..., intraday_vol_lookback=...)` and reads the new fields. Because there's no pin, **the causality is the opposite of "PR #8 could break invictus-bot"** — PR #144 is a consumer that is currently non-functional on a fresh install (would fetch invictus-signals `main`, which lacks these symbols, causing `TypeError`/`AttributeError`) until PR #8 merges. **PR #8 merging is a prerequisite for #144, not a risk to it** — consistent with, and now independently confirmed for, board #2528's sequencing call.

## `backtest/engine.py:410` / `backtest/validation.py:127` — confirmed, and assessed as fine for Phase 1
Both call `compute_ta_state()` with exactly 3 positional args, no new kwargs — `bb_width_pct`/`intraday_bb_width_pct` stay permanently `None` in backtest replay. Grepped both files plus `regime_classifier.py` (the sole consumer of the `TAState` they produce) for the new field names — zero hits anywhere. Phase 1 is explicitly log-only and BBWP consumption lives in `invictus-bot`'s `entry.py`, not this library's backtest path. **Scoped correctly for Phase 1, not a defect** — carried forward as a follow-up note (same conclusion code-review-swarm reached independently, at P2).

## Schema/field-order drift — no risk found
`TAState`'s 3 new fields are correctly appended after all existing defaulted fields (valid dataclass ordering). Every `TAState(` call site repo-wide — 14 in invictus-signals, 17 in invictus-bot — uses exclusively keyword arguments; zero positional construction found. Appending trailing defaulted fields cannot break any of them.

## Full call-site inventory (repo-wide, both repos)
- `compute_ta_state(`: def at `ta_engine.py`; 2 non-test call sites in invictus-signals (`backtest/engine.py`, `backtest/validation.py`, both unaffected/inert re: new kwargs); 0 on invictus-bot `main`; 4 production sites on invictus-bot PR #144 (`src/entry.py`) that already depend on this PR's exact interface.
- `bbwp(`: def + 2 call sites in `ta_engine.py`; 0 direct calls anywhere in invictus-bot (only a comment reference documenting the shared `min_samples` floor).
- `TAState(`: def + 1 production call (`ta_engine.py`); all other sites are test fixtures, all keyword-only.
- `_rolling_bb_widths(`: private, module-scoped; 2 production call sites, correctly never imported outside `ta_engine.py`/its own tests.

No P0/P1/P2 findings in this domain.
