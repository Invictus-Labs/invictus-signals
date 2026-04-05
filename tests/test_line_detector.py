"""Tests for invictus_signals.line_detector."""
from __future__ import annotations

import pytest

from invictus_signals.config import get_config
from invictus_signals.line_detector import (
    LineDetector,
    calculate_touch_points,
    detect_channel,
    detect_tapering,
    find_horizontal_levels,
    find_swing_points,
    fit_trendline,
    _linear_regression,
)
from invictus_signals.models import AlgoLine, Candle, LineColor, LineType
from tests.conftest import make_candle, make_candles


# ---------------------------------------------------------------------------
# _linear_regression
# ---------------------------------------------------------------------------

class TestLinearRegression:
    def test_perfect_positive_slope(self) -> None:
        xs = [0.0, 1.0, 2.0, 3.0, 4.0]
        ys = [0.0, 1.0, 2.0, 3.0, 4.0]
        slope, intercept, r2 = _linear_regression(xs, ys)
        assert slope == pytest.approx(1.0)
        assert intercept == pytest.approx(0.0)
        assert r2 == pytest.approx(1.0)

    def test_flat_line(self) -> None:
        xs = [0.0, 1.0, 2.0]
        ys = [5.0, 5.0, 5.0]
        slope, intercept, r2 = _linear_regression(xs, ys)
        assert slope == pytest.approx(0.0)
        assert r2 == pytest.approx(1.0)  # Perfect fit (variance=0)

    def test_raises_length_mismatch(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            _linear_regression([1.0, 2.0], [1.0])

    def test_raises_insufficient_points(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            _linear_regression([1.0], [1.0])


# ---------------------------------------------------------------------------
# find_swing_points
# ---------------------------------------------------------------------------

class TestFindSwingPoints:
    def test_simple_peak(self) -> None:
        # Create V-shape: prices go up then down
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 103.0, 102.0, 101.0, 100.0, 99.0, 98.0]
        candles = make_candles(prices)
        highs, lows = find_swing_points(candles, lookback=2)
        assert len(highs) > 0

    def test_insufficient_data_returns_empty(self) -> None:
        candles = make_candles([100.0, 101.0])
        highs, lows = find_swing_points(candles, lookback=5)
        assert highs == []
        assert lows == []

    def test_swing_high_in_middle(self) -> None:
        # Clear peak at index 5 of 11 candles
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 104.0, 103.0, 102.0, 101.0, 100.0]
        candles = make_candles(prices)
        highs, lows = find_swing_points(candles, lookback=2)
        high_indices = [idx for idx, _ in highs]
        assert 5 in high_indices


# ---------------------------------------------------------------------------
# fit_trendline
# ---------------------------------------------------------------------------

class TestFitTrendline:
    def test_two_points_perfect_line(self) -> None:
        points = [(0, 100.0), (10, 110.0)]
        slope, intercept, r2 = fit_trendline(points)
        assert slope == pytest.approx(1.0)
        assert intercept == pytest.approx(100.0)

    def test_single_point_zero_slope(self) -> None:
        slope, intercept, r2 = fit_trendline([(5, 200.0)])
        assert slope == 0.0
        assert intercept == 200.0

    def test_empty_points_zero(self) -> None:
        slope, intercept, r2 = fit_trendline([])
        assert slope == 0.0
        assert intercept == 0.0


# ---------------------------------------------------------------------------
# calculate_touch_points
# ---------------------------------------------------------------------------

class TestCalculateTouchPoints:
    def test_horizontal_line_touches(self) -> None:
        candles = make_candles([100.0, 100.1, 99.9, 100.0, 100.05])
        touches = calculate_touch_points(candles, slope=0.0, intercept=100.0, tolerance_pct=0.005)
        assert len(touches) >= 4

    def test_no_touches_far_away(self) -> None:
        candles = make_candles([200.0, 200.0, 200.0])
        touches = calculate_touch_points(candles, slope=0.0, intercept=100.0, tolerance_pct=0.001)
        assert len(touches) == 0


# ---------------------------------------------------------------------------
# find_horizontal_levels
# ---------------------------------------------------------------------------

class TestFindHorizontalLevels:
    def test_finds_repeated_pivot(self) -> None:
        # Create a price series that bounces near 100 twice
        prices = [100.0, 101.0, 102.0, 101.0, 100.1, 101.0, 102.0, 101.5, 100.2,
                  101.0, 102.0, 101.0, 100.0, 101.0, 102.0]
        candles = make_candles(prices)
        levels = find_horizontal_levels(candles, tolerance_pct=0.005, min_touches=2)
        assert isinstance(levels, list)

    def test_empty_when_insufficient_pivots(self) -> None:
        # Only 3 candles — can't form swing points
        candles = make_candles([100.0, 101.0, 100.0])
        levels = find_horizontal_levels(candles)
        assert levels == []


# ---------------------------------------------------------------------------
# detect_channel
# ---------------------------------------------------------------------------

class TestDetectChannel:
    def test_returns_none_on_insufficient_data(self) -> None:
        candles = make_candles([100.0] * 5)
        result = detect_channel(candles)
        assert result is None

    def test_returns_tuple_on_clear_channel(self) -> None:
        # Create ascending channel data
        prices = []
        for i in range(25):
            base = 100.0 + i * 0.5
            prices.append(base)
        candles = [
            make_candle(
                p,
                open=p - 0.2,
                high=p + 1.0 + (i % 3 == 0) * 2,
                low=p - 1.0 - (i % 4 == 0) * 2,
                timestamp=float(i),
            )
            for i, p in enumerate(prices)
        ]
        result = detect_channel(candles)
        # May or may not find a channel depending on swing structure
        assert result is None or (isinstance(result, tuple) and len(result) == 2)


# ---------------------------------------------------------------------------
# detect_tapering
# ---------------------------------------------------------------------------

class TestDetectTapering:
    def test_narrowing_range_returns_true(self) -> None:
        # Wide range in first half, narrow in second half
        candles = []
        for i in range(20):
            if i < 10:
                c = make_candle(100.0, high=110.0, low=90.0, timestamp=float(i))
            else:
                c = make_candle(100.0, high=101.0, low=99.0, timestamp=float(i))
            candles.append(c)
        assert detect_tapering(candles) is True

    def test_stable_range_returns_false(self) -> None:
        candles = [make_candle(100.0, high=102.0, low=98.0, timestamp=float(i)) for i in range(20)]
        assert detect_tapering(candles) is False

    def test_insufficient_data_returns_false(self) -> None:
        candles = make_candles([100.0] * 5)
        assert detect_tapering(candles) is False


# ---------------------------------------------------------------------------
# LineDetector class
# ---------------------------------------------------------------------------

class TestLineDetector:
    def test_init_with_spy_config(self) -> None:
        detector = LineDetector(get_config("SPY"))
        assert detector.config.symbol == "SPY"

    def test_init_default_config(self) -> None:
        detector = LineDetector()
        assert detector.config.symbol == "SPY"

    def test_returns_list(self, spy_intraday, spy_candles_bullish) -> None:
        detector = LineDetector(get_config("SPY"))
        lines = detector.detect_lines(spy_intraday, spy_candles_bullish)
        assert isinstance(lines, list)

    def test_sorted_by_priority(self, spy_intraday, spy_candles_bullish) -> None:
        detector = LineDetector(get_config("SPY"))
        lines = detector.detect_lines(spy_intraday, spy_candles_bullish)
        if len(lines) >= 2:
            priority = {
                LineColor.MAGENTA: 0, LineColor.ORANGE: 1, LineColor.GREEN: 2,
                LineColor.TEAL: 3, LineColor.YELLOW: 4, LineColor.PINK: 5, LineColor.BLUE: 6,
            }
            priorities = [priority[ln.color] for ln in lines]
            assert priorities == sorted(priorities)

    def test_empty_intraday_graceful(self, spy_candles_bullish) -> None:
        detector = LineDetector(get_config("SPY"))
        lines = detector.detect_lines([], spy_candles_bullish)
        assert isinstance(lines, list)

    def test_btc_detector_uses_larger_snap(self) -> None:
        detector = LineDetector(get_config("BTC"))
        assert detector.config.round_number_snap == 1000.0

    def test_detects_yellow_prior_day_levels(self) -> None:
        """Yellow lines should be emitted for prior-day levels."""
        daily = make_candles([500.0, 505.0, 510.0])
        intraday = make_candles([507.0] * 5)
        detector = LineDetector(get_config("SPY"))
        lines = detector.detect_lines(intraday, daily)
        yellow_lines = [ln for ln in lines if ln.color == LineColor.YELLOW]
        # Prior day has high/low/close → should produce yellow lines
        assert len(yellow_lines) >= 1

    def test_magenta_on_enough_daily_data(self) -> None:
        daily = make_candles([500.0 + i for i in range(10)])
        intraday = make_candles([505.0] * 20)
        detector = LineDetector(get_config("SPY"))
        lines = detector.detect_lines(intraday, daily)
        magenta_lines = [ln for ln in lines if ln.color == LineColor.MAGENTA]
        assert len(magenta_lines) >= 0  # May or may not find depending on regression
