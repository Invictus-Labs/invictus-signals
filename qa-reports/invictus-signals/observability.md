# Observability Report — invictus-signals PR #8 (feat/bbwp-percentile)

## Scope
`invictus_signals/ta_engine.py`, `invictus_signals/models.py` — the changed files in this PR.

## Verdict: N/A — no findings, and here is why rather than a silent skip

Checked directly (not assumed):
```
$ grep -rn "os\.getenv\|os\.environ" invictus_signals/ta_engine.py invictus_signals/models.py
(no matches)
$ grep -rn "logger\.\|logging\.\|print(" invictus_signals/ta_engine.py invictus_signals/models.py
(no matches)
```

Both changed files are pure, stateless, stdlib-only math functions with **zero logging, zero I/O, zero exception handling of any kind** (confirmed by the Integration Contract Validator's line-by-line purity trace — no `try`/`except` blocks exist anywhere in `bbwp()`, `_rolling_bb_widths()`, or the new `compute_ta_state()` branches). There is nothing to log because there is nothing that can fail silently: every sad path in `bbwp()` is a documented, tested `return None`, not a caught-and-swallowed exception.

- **PII**: N/A — no log statements exist to leak PII into.
- **Log level inversions**: N/A — no logging exists.
- **Silent exception swallow (`except: pass`)**: confirmed absent — no `except` blocks at all in the changed code.
- **Monitoring hooks for critical operations**: N/A at this layer. `bb_width_pct`/`intraday_bb_width_pct`/`intraday_bb_width` are pure return values; observability for the operation they feed (`regime_vol` classification, written to `trades`/`eval_log`) is `invictus-bot`'s responsibility (a separate repo, separate PR — #144), not this library's.

No P0/P1/P2 findings in this domain.
