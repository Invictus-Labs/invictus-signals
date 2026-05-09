# invictus-signals

Universal price action engine for the Invictus trading ecosystem. Asset-agnostic shared library providing regime classification, 7-color line detection, pattern matching, and Do-Not-Trade (DNT) filters. Works on any asset with OHLCV data — SPY, BTC, ETH, SOL, and custom symbols.

## What It Does

- **Regime classification** — 33-regime waterfall (B1-B8 bullish, BR1-BR8 bearish, C1-C8 choppy, T1-T9 transition)
- **TA engine** — SMA, Bollinger Bands, VWAP, RSI, MACD, ATR, ADX computed into a typed `TAState`
- **7-color line detection** — Support/resistance lines with color-coded strength and direction
- **13+ DNT filters** — Universal do-not-trade conditions (volatility, spread, event proximity, etc.)
- **Event calendar** — FOMC, CPI, NFP, halving dates for pre-event filtering
- **Candle patterns** — Hammer, Doji, Engulfing detection
- **PatternDetector ABC** — Extensible base class for custom pattern detectors

## Consumers

| Bot | Usage |
|-----|-------|
| **Foresight** (`polymarket-bot/`) | Factor 12: `structural_regime` |
| **Options Intel** (SPY) | Replaces local engine modules |
| **Leverage** (`phemex-bot/`) | Planned integration |

## Install

```bash
pip install -e ".[dev]"
```

## Run Tests

```bash
pytest --cov=invictus_signals --cov-fail-under=90
```

## Quick Usage

```python
from invictus_signals import (
    get_config, compute_ta_state, classify_regime,
    run_universal_dnt_filters, LineDetector, Candle
)

config = get_config("BTC")          # or "SPY", "ETH", "SOL"
ta = compute_ta_state(candles, config)
regime = classify_regime(ta, config)
dnt = run_universal_dnt_filters(ta, candles[-1], config)
lines = LineDetector(config).detect(candles)
```

## Key Files

| File | Purpose |
|------|---------|
| `invictus_signals/config.py` | `AssetConfig`, `ASSET_PRESETS`, `get_config()` |
| `invictus_signals/models.py` | All dataclasses and enums |
| `invictus_signals/ta_engine.py` | SMA, BB, VWAP, RSI, MACD, ATR, ADX |
| `invictus_signals/regime_classifier.py` | 33-regime waterfall classifier |
| `invictus_signals/line_detector.py` | 7-color support/resistance line detection |
| `invictus_signals/dnt_filters.py` | 13+ universal DNT filters |
| `invictus_signals/event_calendar.py` | FOMC, CPI, NFP, halving dates |
| `invictus_signals/candle_patterns.py` | Hammer, Doji, Engulfing |
| `invictus_signals/patterns/base.py` | `PatternDetector` abstract base class |

## Stack

- Python 3.12, zero external runtime dependencies
- `pytest` + `pytest-cov` for testing (90% coverage floor)
