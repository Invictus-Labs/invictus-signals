"""Offline backtest / replay harness for invictus-signals.

Deterministic replay engine: feeds historical candles through
``compute_ta_state`` -> ``classify_regime`` -> DNT filters, applies a
fill model, and produces per-(pattern, regime) and per-symbol aggregates.
No network, no live exchange calls, no order placement.

Public API
----------
BacktestConfig      -- fee / fill / ladder config
TradeResult         -- single filled trade record
BacktestReport      -- aggregated results + per-(pattern,regime) matrix
ReplayEngine        -- the replay runner (call ``.run()``)
validate_regime_labels -- drift checker against a reference sample
"""
from invictus_signals.backtest.engine import BacktestConfig, ReplayEngine
from invictus_signals.backtest.models import BacktestReport, TradeResult
from invictus_signals.backtest.validation import validate_regime_labels

__all__ = [
    "BacktestConfig",
    "ReplayEngine",
    "TradeResult",
    "BacktestReport",
    "validate_regime_labels",
]
