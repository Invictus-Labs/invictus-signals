"""Tests for invictus_signals.ta_engine."""
from __future__ import annotations

import dataclasses

import pytest

from invictus_signals.config import get_config
from invictus_signals.models import Candle, TAState
from invictus_signals.ta_engine import (
    _rolling_bb_widths,
    bbwp,
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
# bbwp — percentile rank helper (four-layer-order PRD, AC-5)
# ---------------------------------------------------------------------------

class TestBBWP:
    def test_fresh_all_time_high_reads_as_100(self) -> None:
        # Strictly-increasing series -> final element is the unique max of
        # the window -> strictly-less-than convention sends it to 100.0.
        widths = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert bbwp(widths, lookback=5) == pytest.approx(100.0)

    def test_fresh_all_time_low_reads_as_0(self) -> None:
        widths = [5.0, 4.0, 3.0, 2.0, 1.0]
        assert bbwp(widths, lookback=5) == pytest.approx(0.0)

    def test_ranks_last_element_not_some_other_index(self) -> None:
        # Middle-of-the-pack value at the end -> neither 0 nor 100.
        widths = [1.0, 5.0, 2.0, 4.0, 3.0]
        # window [1,5,2,4,3], target=3, comparable=[1,5,2,4] -> 2 (1,2) < 3
        # -> 100 * 2/4 = 50.0
        assert bbwp(widths, lookback=5) == pytest.approx(50.0)

    def test_appending_a_new_max_changes_the_rank(self) -> None:
        # Same window, but the caller passes a longer series ending in a new
        # element -> proves it ranks the FINAL element, not a fixed index.
        base = [1.0, 5.0, 2.0, 4.0, 3.0]
        assert bbwp(base + [10.0], lookback=6) == pytest.approx(100.0)

    def test_none_below_min_samples(self) -> None:
        assert bbwp([1.0, 2.0], lookback=10, min_samples=5) is None

    def test_none_at_exactly_min_samples_boundary_still_ranks(self) -> None:
        # len(widths) == min_samples is NOT below the floor -> must rank.
        assert bbwp([1.0, 2.0], lookback=10, min_samples=2) is not None

    def test_degenerate_all_identical_widths_returns_50(self) -> None:
        widths = [7.0, 7.0, 7.0, 7.0, 7.0]
        assert bbwp(widths, lookback=5) == pytest.approx(50.0)

    def test_ties_with_target_do_not_count_toward_numerator(self) -> None:
        # Not fully degenerate: two ties at the target plus one strictly
        # lower value. Strictly-less-than -> only the 4.0 counts.
        widths = [4.0, 6.0, 6.0, 6.0]
        # comparable=[4.0, 6.0, 6.0], target=6.0 -> only 4.0 < 6.0 -> 1/3
        assert bbwp(widths, lookback=4) == pytest.approx(100.0 / 3.0)

    def test_lookback_le_1_returns_none(self) -> None:
        assert bbwp([1.0, 2.0, 3.0], lookback=1) is None
        assert bbwp([1.0, 2.0, 3.0], lookback=0) is None

    def test_nan_target_returns_none(self) -> None:
        assert bbwp([1.0, 2.0, float("nan")], lookback=3) is None

    def test_nan_elsewhere_in_window_is_excluded_not_counted(self) -> None:
        # One NaN plus one real, lower comparison point. The NaN must not
        # silently deflate the denominator into "1 of 2" (=50); it should be
        # dropped entirely, leaving "1 of 1" (=100).
        widths = [float("nan"), 1.0, 5.0]
        assert bbwp(widths, lookback=3) == pytest.approx(100.0)

    def test_all_other_elements_nan_returns_none(self) -> None:
        widths = [float("nan"), float("nan"), 5.0]
        assert bbwp(widths, lookback=3) is None

    def test_negative_widths_rank_normally(self) -> None:
        widths = [-5.0, -3.0, -1.0]
        assert bbwp(widths, lookback=3) == pytest.approx(100.0)

    def test_fewer_elements_than_lookback_ranks_within_available_window(self) -> None:
        # lookback=252 requested, but only 4 samples exist (>= min_samples).
        # Must degrade to the available window rather than returning None.
        widths = [1.0, 2.0, 3.0, 4.0]
        assert bbwp(widths, lookback=252, min_samples=2) == pytest.approx(100.0)

    def test_default_min_samples_is_the_mathematical_floor_of_2(self) -> None:
        assert bbwp([1.0], lookback=5) is None
        assert bbwp([1.0, 2.0], lookback=5) is not None

    def test_stdlib_only_no_new_imports(self) -> None:
        import invictus_signals.ta_engine as ta_mod

        banned = {"numpy", "scipy", "pandas", "statistics"}
        module_names = {
            getattr(v, "__name__", None)
            for v in vars(ta_mod).values()
            if isinstance(v, type(ta_mod))
        }
        assert not (module_names & banned)


# ---------------------------------------------------------------------------
# _rolling_bb_widths — private helper feeding bbwp() from compute_ta_state
# ---------------------------------------------------------------------------

class TestRollingBBWidths:
    def test_last_element_matches_direct_calculate_bb(self) -> None:
        closes = [100.0, 102.0, 98.0, 101.0, 99.0, 103.0, 97.0, 104.0]
        widths = _rolling_bb_widths(closes, period=4, std_dev=2.0)
        assert widths[-1] == pytest.approx(
            calculate_bb(closes, period=4, std_dev=2.0)["width"]
        )

    def test_length_is_series_len_minus_period_plus_1(self) -> None:
        closes = [float(i) for i in range(10)]
        widths = _rolling_bb_widths(closes, period=4, std_dev=2.0)
        assert len(widths) == 10 - 4 + 1

    def test_returns_empty_for_period_below_2(self) -> None:
        assert _rolling_bb_widths([1.0, 2.0, 3.0], period=1, std_dev=2.0) == []

    def test_returns_empty_when_shorter_than_period(self) -> None:
        assert _rolling_bb_widths([1.0, 2.0], period=5, std_dev=2.0) == []

    def test_zero_mean_window_yields_zero_width_no_crash(self) -> None:
        # A window whose mean is exactly 0 must reuse calculate_bb's
        # middle==0 guard (0.0, never ZeroDivisionError) rather than
        # re-deriving the normalization.
        closes = [-1.0, 1.0, -1.0, 1.0]
        widths = _rolling_bb_widths(closes, period=4, std_dev=2.0)
        assert widths == [pytest.approx(0.0)]


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
        # 15 rising intraday closes 100..114. BTC periods: fast=12, mid=26, bb=20.
        # With n=15 the windows DIFFER (fast caps at 12, mid+bb cap at 15), so
        # fast and mid produce distinct values — a swap of the two fields fails.
        #   intraday_ma_fast = SMA(last 12: 103..114) = 108.5
        #   intraday_ma_mid  = SMA(all 15: 100..114)  = 107.0
        #   intraday BB(15)   : middle 107.0, pop-sigma sqrt(280/15)=4.3205,
        #                       upper 107+2σ=115.641, lower 107-2σ=98.359
        #   OLS slope of last 5 closes (110..114) = 1.0
        intraday = make_candles([100.0 + i for i in range(15)])
        ta = compute_ta_state(intraday, daily, config=get_config("BTC"))
        assert ta.intraday_ma_fast == pytest.approx(108.5)
        assert ta.intraday_ma_mid == pytest.approx(107.0)
        assert ta.intraday_ma_fast != ta.intraday_ma_mid  # distinct windows
        assert ta.intraday_close_slope == pytest.approx(1.0)
        assert ta.intraday_adx >= 0.0  # populated (0.0 until ADX warmup met)
        # Intraday BB computed from the intraday closes (not the ~80k daily ones).
        assert ta.intraday_bb_upper == pytest.approx(115.641, abs=0.05)
        assert ta.intraday_bb_lower == pytest.approx(98.359, abs=0.05)

    def test_intraday_bb_sentinel_with_single_candle(self) -> None:
        # <2 intraday bars cannot form a band -> 0.0 sentinel (dnt_16 falls
        # back to the daily BB).
        daily = make_candles([500.0] * 25)
        intraday = make_candles([500.0])
        ta = compute_ta_state(intraday, daily)
        assert ta.intraday_bb_upper == 0.0
        assert ta.intraday_bb_lower == 0.0

    def test_intraday_adx_populated_on_trending_session(self) -> None:
        """A long, strongly-trending intraday series yields a real (>0) ADX,
        computed from the INTRADAY candles (not the daily ones)."""
        daily = make_candles([80_000 + i * 50 for i in range(30)])
        # 30 strongly-rising intraday closes -> high directional movement.
        intraday = make_candles([100.0 + i for i in range(30)])
        ta = compute_ta_state(intraday, daily, config=get_config("BTC"))
        assert ta.intraday_adx > 0.0

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

    # -----------------------------------------------------------------
    # bb_width_pct / intraday_bb_width / intraday_bb_width_pct (AC-6)
    # -----------------------------------------------------------------

    def test_new_pct_fields_default_none_without_vol_lookback(self) -> None:
        # Today's callers never pass vol_lookback — both percentile fields
        # must stay None so nothing downstream sees a value it didn't ask for.
        daily = make_candles([500.0 + i * 0.3 for i in range(30)])
        intraday = make_candles([500.0] * 10)
        ta = compute_ta_state(intraday, daily)
        assert ta.bb_width_pct is None
        assert ta.intraday_bb_width_pct is None

    def test_intraday_bb_width_populated_independent_of_vol_lookback(self) -> None:
        # Unlike the two _pct fields, intraday_bb_width is a snapshot (no
        # ranking needed) and is populated whether or not vol_lookback is
        # supplied.
        daily = make_candles([80_000 + i * 50 for i in range(30)])
        intraday_prices = [100.0 + i for i in range(15)]
        intraday = make_candles(intraday_prices)
        cfg = get_config("BTC")
        ta = compute_ta_state(intraday, daily, config=cfg)
        expected = calculate_bb(
            intraday_prices,
            period=min(cfg.bb_period, len(intraday_prices)),
            std_dev=cfg.bb_std_dev,
        )["width"]
        assert ta.intraday_bb_width == pytest.approx(expected)
        assert ta.intraday_bb_width > 0.0

    def test_intraday_bb_width_zero_sentinel_with_single_candle(self) -> None:
        # Mirrors the existing intraday_bb_upper/lower sentinel: <2 intraday
        # bars can't form a band, so the width sentinel is 0.0 too.
        daily = make_candles([500.0] * 25)
        intraday = make_candles([500.0])
        ta = compute_ta_state(intraday, daily)
        assert ta.intraday_bb_width == 0.0

    def test_bb_width_pct_matches_manual_bbwp_over_rolling_widths(self) -> None:
        cfg = get_config("BTC", bb_period=5)
        prices = [100.0 + i for i in range(30)]
        daily = make_candles(prices)
        intraday = make_candles([500.0] * 10)
        ta = compute_ta_state(intraday, daily, config=cfg, vol_lookback=10)
        expected = bbwp(_rolling_bb_widths(prices, 5, cfg.bb_std_dev), 10)
        assert expected is not None
        assert ta.bb_width_pct == expected

    def test_intraday_bb_width_pct_matches_manual_bbwp(self) -> None:
        cfg = get_config("BTC", bb_period=5)
        daily = make_candles([80_000 + i * 50 for i in range(30)])
        intraday_prices = [100.0 + i for i in range(20)]
        intraday = make_candles(intraday_prices)
        ta = compute_ta_state(intraday, daily, config=cfg, vol_lookback=10)
        expected = bbwp(_rolling_bb_widths(intraday_prices, 5, cfg.bb_std_dev), 10)
        assert expected is not None
        assert ta.intraday_bb_width_pct == expected

    def test_bb_width_pct_none_when_daily_history_too_short_for_a_band(self) -> None:
        # bb_period caps at n_daily=1 (<2) -> no band at all -> None even
        # though the caller supplied a lookback.
        daily = make_candles([500.0])
        intraday = make_candles([500.0] * 10)
        ta = compute_ta_state(intraday, daily, vol_lookback=50)
        assert ta.bb_width_pct is None

    def test_intraday_bb_width_pct_none_with_single_intraday_candle(self) -> None:
        daily = make_candles([500.0 + i * 0.3 for i in range(30)])
        intraday = make_candles([500.0])
        ta = compute_ta_state(intraday, daily, vol_lookback=50)
        assert ta.intraday_bb_width_pct is None
        assert ta.intraday_bb_width == 0.0

    def test_bb_width_pct_survives_zero_mean_window_in_history(self) -> None:
        # Some historical rolling windows have mean == 0 (calculate_bb's
        # middle==0 guard fires -> 0.0 width for that position). Ranking
        # over the whole rolling series must not crash and must still
        # return a valid 0-100 rank.
        cfg = get_config("BTC", bb_period=4)
        daily = make_candles([-1.0, 1.0, -1.0, 1.0, -1.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        intraday = make_candles([500.0] * 10)
        ta = compute_ta_state(intraday, daily, config=cfg, vol_lookback=10)
        assert ta.bb_width_pct is not None
        assert 0.0 <= ta.bb_width_pct <= 100.0

    def test_additive_only_existing_fields_unchanged_by_vol_lookback(self) -> None:
        # AC-6: every existing TAState field keeps its current value —
        # passing vol_lookback may only populate the three new fields.
        daily = make_candles([500.0 + i * 0.3 for i in range(60)])
        intraday = make_candles([501.0 + (i % 5) * 0.1 for i in range(60)])
        cfg = get_config("SPY")
        without = compute_ta_state(intraday, daily, config=cfg)
        with_lookback = compute_ta_state(intraday, daily, config=cfg, vol_lookback=20)
        new_fields = {"bb_width_pct", "intraday_bb_width", "intraday_bb_width_pct"}
        for f in dataclasses.fields(TAState):
            if f.name in new_fields:
                continue
            assert getattr(without, f.name) == getattr(with_lookback, f.name), f.name
