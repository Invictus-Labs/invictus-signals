# Configuration Report — invictus-signals PR #8 (feat/bbwp-percentile)

## Scope
`invictus_signals/ta_engine.py`, `invictus_signals/models.py` — the changed files in this PR.

## Verdict: N/A — no findings, and here is why rather than a silent skip

Checked directly (not assumed):
```
$ grep -rn "os\.getenv\|os\.environ" invictus_signals/ta_engine.py invictus_signals/models.py
(no matches)
$ grep -rn "\.env\b" invictus_signals/ta_engine.py invictus_signals/models.py
(no matches)
```

Neither changed file reads a single environment variable, config file, or secret. This library's only configuration surface is `AssetConfig` (`invictus_signals/config.py`, unchanged by this PR), which is a plain in-memory dataclass with hardcoded static presets (`ASSET_PRESETS`) — not sourced from the environment at all. The new `vol_lookback`/`intraday_vol_lookback`/`vol_min_samples` parameters this PR adds to `compute_ta_state()` are plain function arguments, supplied by the caller (`invictus-bot`, which owns the actual `VOL_BUCKET_LOOKBACK`/`VOL_BUCKET_INTRADAY_LOOKBACK` runtime-config keys per the PRD's API Contracts table — a different repo, different PR, already registered per risk-validator's report).

- **`os.environ["KEY"]` crash-on-missing**: N/A — no env access exists.
- **Undocumented env vars**: N/A — none introduced.
- **Startup validation**: N/A — this is a stateless library with no startup phase; every value is a function parameter validated at call time (`bbwp()`'s own guards).
- **Secrets in committed `.env`**: checked repo-wide, none found; not introduced by this diff.

No P0/P1/P2 findings in this domain.
