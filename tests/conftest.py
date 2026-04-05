"""Shared fixtures for invictus-signals tests."""
from __future__ import annotations

import pytest

from invictus_signals.config import get_config, AssetConfig
from invictus_signals.models import (
    Candle,
    TAState,
    RegimeClass,
    RegimeId,
    RegimeClassification,
    Direction,
    AlgoLine,
    LineColor,
    LineType,
    ValidationStatus,
)


# ---------------------------------------------------------------------------
# Candle factories
# ---------------------------------------------------------------------------


def make_candle(
    close: float,
    *,
    open: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1000.0,
    timestamp: float = 0.0,
) -> Candle:
    """Create a Candle with sane defaults derived from close."""
    o = open if open is not None else close * 0.999
    h = high if high is not None else close * 1.002
    l = low if low is not None else close * 0.998
    return Candle(timestamp=timestamp, open=o, high=h, low=l, close=close, volume=volume)


def make_candles(prices: list[float], volume: float = 1000.0) -> list[Candle]:
    """Create a list of candles from a price series."""
    return [make_candle(p, timestamp=float(i), volume=volume) for i, p in enumerate(prices)]


# ---------------------------------------------------------------------------
# SPY fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def spy_config() -> AssetConfig:
    return get_config("SPY")


@pytest.fixture
def btc_config() -> AssetConfig:
    return get_config("BTC")


@pytest.fixture
def spy_candles_bullish() -> list[Candle]:
    """30 daily candles in a clear uptrend (SPY-scale prices)."""
    base = 500.0
    prices = [base + i * 0.5 for i in range(30)]
    return make_candles(prices)


@pytest.fixture
def spy_candles_bearish() -> list[Candle]:
    """30 daily candles in a clear downtrend."""
    base = 530.0
    prices = [base - i * 0.5 for i in range(30)]
    return make_candles(prices)


@pytest.fixture
def spy_intraday() -> list[Candle]:
    """60 intraday bars for VWAP / volume calculations."""
    base = 500.0
    return [
        make_candle(base + (i % 5) * 0.1, timestamp=float(i), volume=500.0)
        for i in range(60)
    ]


@pytest.fixture
def spy_ta_bullish() -> TAState:
    """Bullish TAState for SPY."""
    return TAState(
        ma_fast=502.0,
        ma_mid=498.0,
        ma_slow=490.0,
        ma_fast_slope=0.5,
        ma_mid_slope=0.3,
        bb_upper=510.0,
        bb_lower=490.0,
        bb_middle=500.0,
        bb_width=0.04,
        bb_upper_slope=0.4,
        volume_ma=1000.0,
        vwap=501.0,
    )


@pytest.fixture
def spy_ta_bearish() -> TAState:
    """Bearish TAState for SPY."""
    return TAState(
        ma_fast=498.0,
        ma_mid=502.0,
        ma_slow=510.0,
        ma_fast_slope=-0.5,
        ma_mid_slope=-0.3,
        bb_upper=508.0,
        bb_lower=492.0,
        bb_middle=500.0,
        bb_width=0.04,
        bb_upper_slope=-0.4,
        volume_ma=1000.0,
        vwap=499.0,
    )


@pytest.fixture
def spy_ta_choppy() -> TAState:
    """Choppy TAState — MAs nearly equal."""
    return TAState(
        ma_fast=500.1,
        ma_mid=500.0,
        ma_slow=500.0,
        ma_fast_slope=0.0,
        ma_mid_slope=0.0,
        bb_upper=502.0,
        bb_lower=498.0,
        bb_middle=500.0,
        bb_width=0.008,
        bb_upper_slope=0.0,
        volume_ma=1000.0,
        vwap=500.0,
    )


# ---------------------------------------------------------------------------
# BTC fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def btc_ta_bullish() -> TAState:
    """Bullish TAState for BTC (large absolute values)."""
    return TAState(
        ma_fast=85_000.0,
        ma_mid=82_000.0,
        ma_slow=75_000.0,
        ma_fast_slope=200.0,
        ma_mid_slope=150.0,
        bb_upper=90_000.0,
        bb_lower=78_000.0,
        bb_middle=84_000.0,
        bb_width=0.14,
        bb_upper_slope=180.0,
        volume_ma=500.0,
        vwap=84_500.0,
    )


@pytest.fixture
def btc_ta_choppy() -> TAState:
    """Choppy TAState for BTC — MAs intermingling at BTC scale."""
    return TAState(
        ma_fast=84_200.0,
        ma_mid=84_000.0,
        ma_slow=80_000.0,
        ma_fast_slope=10.0,
        ma_mid_slope=5.0,
        bb_upper=86_000.0,
        bb_lower=82_000.0,
        bb_middle=84_000.0,
        bb_width=0.05,
        bb_upper_slope=0.0,
        volume_ma=500.0,
        vwap=84_100.0,
    )


# ---------------------------------------------------------------------------
# AlgoLine fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def two_good_lines() -> list[AlgoLine]:
    """Two lines each with 2+ touch points — passes structure check."""
    return [
        AlgoLine(
            color=LineColor.ORANGE,
            line_type=LineType.ASCENDING_SUPPORT,
            touch_points=[(0.0, 500.0), (1.0, 501.0)],
            slope=1.0,
            current_level=502.0,
            session_frequency=0.80,
        ),
        AlgoLine(
            color=LineColor.GREEN,
            line_type=LineType.CHANNEL_UPPER,
            touch_points=[(0.0, 505.0), (1.0, 506.0)],
            slope=1.0,
            current_level=507.0,
            session_frequency=0.72,
        ),
    ]


@pytest.fixture
def regime_bullish() -> RegimeClassification:
    return RegimeClassification(
        regime_id=RegimeId.B1_TRENDING,
        regime_class=RegimeClass.BULLISH,
        bias=Direction.LONG,
        size_multiplier=1.0,
        conditions_met=["price > fast MA"],
        confidence=0.90,
    )


@pytest.fixture
def regime_choppy() -> RegimeClassification:
    return RegimeClassification(
        regime_id=RegimeId.C1_COMPRESSION,
        regime_class=RegimeClass.CHOPPY,
        bias=None,
        size_multiplier=0.25,
        conditions_met=["MA intermingling"],
        confidence=0.80,
    )
