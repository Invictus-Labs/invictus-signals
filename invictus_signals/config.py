"""Asset configuration for invictus-signals.

Provides per-symbol presets for SPY, BTC, ETH, SOL and a factory
function that returns a configured AssetConfig for any symbol.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass
class AssetConfig:
    """Configuration for a single trading asset."""

    symbol: str

    # MA periods
    ma_fast_period: int = 5       # SPY: 5, BTC/ETH/SOL: 12
    ma_mid_period: int = 20       # SPY: 20, BTC/ETH/SOL: 26
    ma_slow_period: int = 200

    # Bollinger Bands
    bb_period: int = 20
    bb_std_dev: float = 2.0

    # Regime thresholds
    intermingling_threshold: float = 0.002   # How close MAs must be for "choppy"
    slope_flat_threshold: float = 0.01

    # Line detection
    swing_lookback: int = 5
    touch_tolerance_pct: float = 0.001
    horizontal_min_touches: int = 2
    round_number_snap: float = 5.0           # Round number interval

    # DNT filters
    choppy_range_threshold: float = 1.0      # Min range for "not choppy"
    chase_threshold_pct: float = 0.001       # Max chase distance as % of price
    min_intraday_adx: float = 30.0           # Min 1H ADX to take momentum entries (chop guard)
    max_trades_per_day: int = 3
    max_consecutive_losses: int = 2

    # Volume
    volume_multiplier: float = 1.5
    volume_ma_period: int = 5

    # Market hours (None = 24/7 like crypto)
    market_open: tuple[int, int] | None = None
    market_close: tuple[int, int] | None = None


ASSET_PRESETS: dict[str, AssetConfig] = {
    "SPY": AssetConfig(
        symbol="SPY",
        ma_fast_period=5,
        ma_mid_period=20,
        intermingling_threshold=0.002,
        touch_tolerance_pct=0.001,
        round_number_snap=5.0,
        choppy_range_threshold=1.0,
        chase_threshold_pct=0.001,
        market_open=(9, 30),
        market_close=(16, 0),
    ),
    "BTC": AssetConfig(
        symbol="BTC",
        ma_fast_period=12,
        ma_mid_period=26,
        intermingling_threshold=0.005,
        slope_flat_threshold=0.02,
        touch_tolerance_pct=0.003,
        round_number_snap=1000.0,
        choppy_range_threshold=500.0,
        chase_threshold_pct=0.003,
    ),
    "ETH": AssetConfig(
        symbol="ETH",
        ma_fast_period=12,
        ma_mid_period=26,
        intermingling_threshold=0.005,
        slope_flat_threshold=0.02,
        touch_tolerance_pct=0.003,
        round_number_snap=100.0,
        choppy_range_threshold=30.0,
        chase_threshold_pct=0.003,
    ),
    "SOL": AssetConfig(
        symbol="SOL",
        ma_fast_period=12,
        ma_mid_period=26,
        intermingling_threshold=0.005,
        slope_flat_threshold=0.02,
        touch_tolerance_pct=0.003,
        round_number_snap=10.0,
        choppy_range_threshold=3.0,
        chase_threshold_pct=0.003,
    ),
}


def get_config(symbol: str, **overrides: object) -> AssetConfig:
    """Get config for symbol. Falls back to BTC preset for unknown crypto.

    Args:
        symbol: Asset symbol (case-insensitive).
        **overrides: Field overrides applied after preset selection.

    Returns:
        AssetConfig with preset values and any requested overrides.
    """
    base = ASSET_PRESETS.get(symbol.upper())
    if base is None:
        base = dataclasses.replace(ASSET_PRESETS["BTC"], symbol=symbol.upper())
    if overrides:
        base = dataclasses.replace(base, **overrides)
    return base
