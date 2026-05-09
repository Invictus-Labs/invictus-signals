# invictus-signals — Universal Price Action Engine

Shared library for regime classification, 7-color line detection, pattern matching, and DNT filters. Asset-agnostic — works on SPY, BTC, ETH, SOL, or any asset with OHLCV data.

## Consumers
- Foresight (Polymarket) — Factor 12: structural_regime
- Options Intel (SPY) — replaces local engine modules
- Leverage (Phemex perps) — future

## Stack
- Python 3.12, stdlib only (zero external deps)
- pytest, 90%+ coverage floor

## Key Design
- AssetConfig dataclass with per-symbol presets (SPY, BTC, ETH, SOL)
- TAState uses generic field names (ma_fast, ma_mid, ma_slow)
- All functions accept optional config parameter — defaults preserve SPY behavior

## Commands
```bash
pip install -e ".[dev]"                              # install with dev deps
pytest --cov=invictus_signals --cov-fail-under=90   # run tests (90% floor)
```

## Key Files
- `invictus_signals/config.py` — AssetConfig, ASSET_PRESETS, get_config()
- `invictus_signals/models.py` — All dataclasses and enums
- `invictus_signals/ta_engine.py` — SMA, BB, VWAP, RSI, MACD, ATR, ADX
- `invictus_signals/regime_classifier.py` — 33-regime waterfall
- `invictus_signals/line_detector.py` — 7-color line detection
- `invictus_signals/dnt_filters.py` — 13+ universal filters
- `invictus_signals/event_calendar.py` — FOMC, CPI, NFP, halving dates
- `invictus_signals/candle_patterns.py` — Hammer, Doji, Engulfing
- `invictus_signals/patterns/base.py` — PatternDetector ABC
- `tests/` — one test file per module, `conftest.py` with shared candle fixtures

## Git Workflow
- NEVER commit to `main` — always feature branch → PR → merge
