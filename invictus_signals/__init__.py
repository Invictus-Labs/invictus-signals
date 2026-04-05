"""invictus-signals — Universal price action engine.

Regime classification, 7-color line detection, pattern matching,
and Do-Not-Trade filters for any OHLCV asset.
"""
from __future__ import annotations

__version__ = "0.1.0"

from invictus_signals.config import AssetConfig, get_config, ASSET_PRESETS
from invictus_signals.models import (
    Candle,
    TAState,
    RegimeClassification,
    RegimeClass,
    RegimeId,
    Direction,
    AlgoLine,
    LineColor,
    LineType,
    DNTResult,
    PatternMatch,
    ConvictionLevel,
    ValidationStatus,
)
from invictus_signals.ta_engine import compute_ta_state
from invictus_signals.regime_classifier import classify_regime
from invictus_signals.line_detector import LineDetector
from invictus_signals.dnt_filters import run_universal_dnt_filters
from invictus_signals.event_calendar import is_event_day

__all__ = [
    "__version__",
    # Config
    "AssetConfig",
    "get_config",
    "ASSET_PRESETS",
    # Models
    "Candle",
    "TAState",
    "RegimeClassification",
    "RegimeClass",
    "RegimeId",
    "Direction",
    "AlgoLine",
    "LineColor",
    "LineType",
    "DNTResult",
    "PatternMatch",
    "ConvictionLevel",
    "ValidationStatus",
    # Engine
    "compute_ta_state",
    "classify_regime",
    "LineDetector",
    "run_universal_dnt_filters",
    "is_event_day",
]
