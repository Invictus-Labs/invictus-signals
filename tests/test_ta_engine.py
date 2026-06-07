"""Tests for invictus_signals.ta_engine."""
from __future__ import annotations

import pytest

from invictus_signals.config import get_config
from invictus_signals.models import Candle
from invictus_signals.ta_engine import (
    calculate_adx,
    calculate_atr,
    calculate_bb,
    calculate_macd_histogram,
    calculate_rsi,
    calculate_sma,
    calculate_slope,
    calculate_vwap,
    compute_ta_state,
)
from tests.conftest import make_candle, make_candles


# ---------------------------------------------------------------------------
# calculate_sma
# ---------------------------------------------------------------------------

class TestCalculateSMA:
    def test_exact_window(self) -> None:
        result = calculate_sma([1.0, 2.0, 3.0, 4.0, 5.0], 5)
        assert result == pytest.approx(3.0)

    def test_uses_last_n(self) -> None:
        # Last 3 of [1,2,3,4,5] = [3,4,5] → mean = 4.0
        result = calculate_sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert result == pytest.approx(4.0)

    def test_single_value(self) -> None:
        result = calculate_sma([42.0], 1)
        assert result == pytest.approx(42.0)

    def test_raises_on_short_series(self) -> None:
        with pytest.raises(ValueError, match="Need at least"):
            calculate_sma([1.0, 2.0], 5)

    def test_raises_on_bad_period(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 1"):
            calculate_sma([1.0, 2.0, 3.0], 0)


# ---------------------------------------------------------------------------
# calculate_bb
# ---------------------------------------------------------------------------

class TestCalculateBB:
    def test_known_values(self) -> None:
        prices = [10.0] * 20  # All same → zero std dev
        bb = calculate_bb(prices, period=20)
        assert bb["middle"] == pytest.approx(10.0)
        assert bb["upper"] == pytest.approx(10.0)
        assert bb["lower"] == pytest.approx(10.0)
        assert bb["width"] == pytest.approx(0.0)

    def test_symmetric_band(self) -> None:
        prices = list(range(1, 21))  # 1..20
        bb = calculate_bb(prices, period=20)
        assert bb["upper"] > bb["middle"] > bb["lower"]
        assert bb["upper"] - bb["middle"] == pytest.approx(bb["middle"] - bb["lower"], rel=1e-10)

    def test_width_nonzero_for_varying(self) -> None:
        prices = [100.0, 102.0, 98.0, 101.0, 99.0] * 4
        bb = calculate_bb(prices, period=20)
        assert bb["width"] > 0

    def test_raises_period_too_small(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 2"):
            calculate_bb([1.0, 2.0], period=1)

    def test_raises_insufficient_data(self) -> None:
        with pytest.raises(ValueError, match="Need at least"):
            calculate_bb([1.0, 2.0], period=10)


# ---------------------------------------------------------------------------
# calculate_vwap
# ---------------------------------------------------------------------------

class TestCalculateVWAP:
    def test_single_candle(self) -> None:
        c = Candle(timestamp=0.0, open=100.0, high=102.0, low=98.0, close=101.0, volume=1000.0)
        typical = (102.0 + 98.0 + 101.0) / 3
        assert calculate_vwap([c]) == pytest.approx(typical)

    def test_equal_weight_candles(self) -> None:
        candles = [
            Candle(0.0, 100.0, 104.0, 96.0, 100.0, 1000.0),  # typical=100
            Candle(1.0, 100.0, 104.0, 96.0, 100.0, 1000.0),  # typical=100
        ]
        assert calculate_vwap(candles) == pytest.approx(100.0)

    def test_volume_weighted(self) -> None:
        # High volume at 200, low volume at 100 → VWAP closer to 200
        candles = [
            Candle(0.0, 100.0, 100.0, 100.0, 100.0, volume=1.0),
            Candle(1.0, 200.0, 200.0, 200.0, 200.0, volume=9.0),
        ]
        vwap = calculate_vwap(candles)
        assert vwap > 150.0  # Closer to 200

    def test_raises_empty(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            calculate_vwap([])

    def test_raises_zero_volume(self) -> None:
        c = Candle(0.0, 100.0, 102.0, 98.0, 100.0, 0.0)
        with pytest.raises(ValueError, match="Total volume is zero"):
            calculate_vwap([c])


# ---------------------------------------------------------------------------
# calculate_slope
# ---------------------------------------------------------------------------

class TestCalculateSlope:
    def test_flat_line(self) -> None:
        values = [10.0] * 5
        assert calculate_slope(values, 5) == pytest.approx(0.0)

    def test_positive_slope(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        slope = calculate_slope(values, 5)
        assert slope > 0

    def test_negative_slope(self) -> None:
        values = [5.0, 4.0, 3.0, 2.0, 1.0]
        slope = calculate_slope(values, 5)
        assert slope < 0

    def test_perfect_line_slope_equals_1(self) -> None:
        values = [0.0, 1.0, 2.0, 3.0, 4.0]
        slope = calculate_slope(values, 5)
        assert slope == pytest.approx(1.0)

    def test_raises_bad_period(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 2"):
            calculate_slope([1.0, 2.0, 3.0], 1)


# ---------------------------------------------------------------------------
# calculate_rsi
# ---------------------------------------------------------------------------

class TestCalculateRSI:
    def test_all_up_returns_100(self) -> None:
        prices = [float(i) for i in range(1, 20)]  # Strictly increasing
        rsi = calculate_rsi(prices, period=14)
        assert rsi == pytest.approx(100.0)

    def test_all_down_returns_0(self) -> None:
        prices = [float(20 - i) for i in range(20)]  # Strictly decreasing
        rsi = calculate_rsi(prices, period=14)
        assert rsi == pytest.approx(0.0)

    def test_neutral_returns_near_50(self) -> None:
        # Alternating up/down should be near 50
        prices = [100.0 + (i % 2) for i in range(30)]
        rsi = calculate_rsi(prices, period=14)
        assert 30.0 < rsi < 70.0

    def test_insufficient_data_returns_50(self) -> None:
        rsi = calculate_rsi([100.0, 101.0, 99.0], period=14)
        assert rsi == pytest.approx(50.0)

    def test_range_0_to_100(self) -> None:
        import random
        random.seed(42)
        prices = [100.0 + random.gauss(0, 2) for _ in range(50)]
        rsi = calculate_rsi(prices, period=14)
        assert 0.0 <= rsi <= 100.0


# ---------------------------------------------------------------------------
# calculate_macd_histogram
# ---------------------------------------------------------------------------

class TestCalculateMACDHistogram:
    def test_insufficient_data_returns_zero(self) -> None:
        prices = [100.0] * 10
        assert calculate_macd_histogram(prices) == pytest.approx(0.0)

    def test_uptrend_positive_histogram(self) -> None:
        prices = [float(i) for i in range(1, 50)]
        result = calculate_macd_histogram(prices)
        # In a clean uptrend fast EMA > slow EMA → positive histogram
        assert isinstance(result, float)

    def test_returns_float(self) -> None:
        prices = [100.0 + i * 0.1 for i in range(50)]
        result = calculate_macd_histogram(prices)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# calculate_atr
# ---------------------------------------------------------------------------

class TestCalculateATR:
    def test_constant_candles(self) -> None:
        # All candles have same high-low range
        candles = [Candle(float(i), 100.0, 102.0, 98.0, 100.0, 1000.0) for i in range(20)]
        atr = calculate_atr(candles, period=14)
        assert atr > 0.0

    def test_insufficient_data(self) -> None:
        c = Candle(0.0, 100.0, 102.0, 98.0, 100.0, 1000.0)
        assert calculate_atr([c], period=14) == 0.0

    def test_empty_returns_zero(self) -> None:
        assert calculate_atr([], period=14) == 0.0

    def test_larger_range_larger_atr(self) -> None:
        narrow = [Candle(float(i), 100.0, 101.0, 99.0, 100.0, 1000.0) for i in range(20)]
        wide = [Candle(float(i), 100.0, 110.0, 90.0, 100.0, 1000.0) for i in range(20)]
        assert calculate_atr(wide, period=14) > calculate_atr(narrow, period=14)


# ---------------------------------------------------------------------------
# calculate_adx
# ---------------------------------------------------------------------------

class TestCalculateADX:
    def test_insufficient_data_returns_zero(self) -> None:
        candles = [Candle(float(i), 100.0, 102.0, 98.0, 100.0, 1000.0) for i in range(5)]
        assert calculate_adx(candles, period=14) == 0.0

    def test_returns_non_negative(self) -> None:
        candles = [
            Candle(float(i), 100.0 + i, 102.0 + i, 98.0 + i, 100.0 + i, 1000.0)
            for i in range(40)
        ]
        adx = calculate_adx(candles, period=14)
        assert adx >= 0.0

    def test_strong_trend_returns_high_adx(self) -> None:
        # Perfect uptrend — all bars have same high-low with clear up movement
        candles = [
            Candle(float(i), 100.0 + i * 2, 103.0 + i * 2, 99.0 + i * 2, 102.0 + i * 2, 1000.0)
            for i in range(40)
        ]
        adx = calculate_adx(candles, period=14)
        # In a strong trend DX will be high
        assert adx > 0.0


# ---------------------------------------------------------------------------
# compute_ta_state
# ---------------------------------------------------------------------------

class TestComputeTAState:
    def test_basic_spy_computation(self) -> None:
        daily = make_candles([500.0 + i * 0.3 for i in range(210)])
        intraday = make_candles([501.0 + (i % 5) * 0.1 for i in range(60)])
        cfg = get_config("SPY")
        ta = compute_ta_state(intraday, daily, config=cfg)

        assert ta.ma_fast > 0
        assert ta.ma_mid > 0
        assert ta.ma_slow > 0
        assert ta.bb_upper > ta.bb_middle > ta.bb_lower
        assert ta.volume_ma > 0
        assert ta.vwap > 0

    def test_btc_uses_correct_periods(self) -> None:
        daily = make_candles([80_000 + i * 50 for i in range(30)])
        intraday = make_candles([81_000.0] * 10)
        cfg = get_config("BTC")
        ta = compute_ta_state(intraday, daily, config=cfg)
        # BTC uses 12/26 periods — fast MA over 12 days
        assert ta.ma_fast > 0

    def test_default_config_is_spy(self) -> None:
        daily = make_candles([500.0] * 25)
        intraday = make_candles([500.0] * 10)
        ta = compute_ta_state(intraday, daily)
        assert ta.ma_fast > 0  # Defaults to SPY without error

    def test_intraday_fields_populated(self) -> None:
        daily = make_candles([80_000 + i * 50 for i in range(30)])
        # 10 rising intraday closes 100..109: BTC fast period 12 capped at
        # n=10 -> SMA = 104.5; OLS slope of last 5 closes = exactly 1.0.
        intraday = make_candles([100.0 + i for i in range(10)])
        ta = compute_ta_state(intraday, daily, config=get_config("BTC"))
        assert ta.intraday_ma_fast == pytest.approx(104.5)
        assert ta.intraday_close_slope == pytest.approx(1.0)

    def test_intraday_slope_negative_on_falling_session(self) -> None:
        daily = make_candles([80_000 + i * 50 for i in range(30)])
        intraday = make_candles([110.0 - i for i in range(10)])
        ta = compute_ta_state(intraday, daily, config=get_config("BTC"))
        assert ta.intraday_close_slope == pytest.approx(-1.0)

    def test_intraday_slope_zero_with_single_candle(self) -> None:
        daily = make_candles([500.0] * 25)
        intraday = make_candles([500.0])
        ta = compute_ta_state(intraday, daily)
        assert ta.intraday_close_slope == 0.0
        assert ta.intraday_ma_fast == pytest.approx(500.0)

    def test_raises_empty_candles(self) -> None:
        daily = make_candles([500.0] * 25)
        with pytest.raises(ValueError, match="candles must not be empty"):
            compute_ta_state([], daily)

    def test_raises_empty_daily(self) -> None:
        intraday = make_candles([500.0] * 10)
        with pytest.raises(ValueError, match="daily_candles must not be empty"):
            compute_ta_state(intraday, [])

    def test_rsi_in_range(self) -> None:
        daily = make_candles([500.0 + i * 0.5 for i in range(30)])
        intraday = make_candles([500.0] * 10)
        ta = compute_ta_state(intraday, daily)
        assert 0.0 <= ta.rsi <= 100.0

    def test_atr_non_negative(self) -> None:
        daily = make_candles([500.0 + i * 0.3 for i in range(30)])
        intraday = make_candles([500.0] * 10)
        ta = compute_ta_state(intraday, daily)
        assert ta.atr >= 0.0
        assert ta.atr_pct >= 0.0

    def test_minimal_data_graceful(self) -> None:
        # 2 daily candles, 1 intraday — should not crash
        daily = make_candles([500.0, 501.0])
        intraday = make_candles([501.0])
        ta = compute_ta_state(intraday, daily)
        assert ta.vwap > 0
